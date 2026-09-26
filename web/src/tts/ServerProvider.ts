import type {
  TTSProvider,
  Voice,
  SynthesisRequest,
  SynthesisCallbacks,
} from './types';

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';

/** Longest we wait for a render. The CPU-bound voices (Chatterbox, Parler,
 *  IndicF5) need roughly 0.17s per character, so a full 5,000-character
 *  request can legitimately run for minutes. The proxy allows 900s; stop a
 *  little before that so the user gets our message, not a dropped socket. */
const SYNTH_TIMEOUT_MS = 870_000;

// A single, shared <audio> element reused for all server playback. Safari/iOS
// and mobile Chrome only allow programmatic play() on an element that has been
// "unlocked" by a real user gesture — and since we play AFTER an async fetch
// (which loses the gesture), we pre-unlock this element on the first tap/click.
const SILENT_WAV =
  'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=';
let _sharedAudio: HTMLAudioElement | null = null;

function sharedAudio(): HTMLAudioElement {
  if (!_sharedAudio) _sharedAudio = new Audio();
  return _sharedAudio;
}

if (typeof window !== 'undefined') {
  const unlock = () => {
    const a = sharedAudio();
    a.src = SILENT_WAV;
    a.play()
      .then(() => {
        a.pause();
        a.currentTime = 0;
      })
      .catch(() => {});
    window.removeEventListener('pointerdown', unlock);
    window.removeEventListener('keydown', unlock);
    window.removeEventListener('touchstart', unlock);
  };
  window.addEventListener('pointerdown', unlock);
  window.addEventListener('keydown', unlock);
  window.addEventListener('touchstart', unlock);
}

/**
 * ServerProvider — talks to the self-hosted FastAPI + Piper backend.
 * Returns true audio files (WAV always, MP3 if ffmpeg is present on server),
 * so supportsDownload() is true. Playback uses an <audio> element fed by the
 * returned blob; sentence-level highlighting is estimated client-side since
 * Piper does not emit per-word boundary events.
 */
export class ServerProvider implements TTSProvider {
  id = 'server' as const;
  private audio: HTMLAudioElement | null = null;
  private highlightTimer: number | null = null;
  private reachable = false;

  supportsDownload(): boolean {
    return true;
  }

  /** Probe the backend; returns [] if it isn't running so the UI degrades.
   *  Retries once with a longer timeout so a cold/warming server or a brief
   *  network blip doesn't silently drop a signed-in user to browser voices. */
  async listVoices(): Promise<Voice[]> {
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        return await this.#fetchVoices();
      } catch {
        if (attempt === 0) await new Promise((r) => setTimeout(r, 1200));
      }
    }
    this.reachable = false;
    return [];
  }

  async #fetchVoices(): Promise<Voice[]> {
    const res = await fetch(`${API_BASE}/voices`, {
      credentials: 'include',
      signal: AbortSignal.timeout(12000),
    });
    if (!res.ok) {
      // 401 = not signed in (expected on public pages). No server voices, and
      // a retry won't help, so return empty without throwing.
      this.reachable = false;
      return [];
    }
    const data = (await res.json()) as Array<{
      id: string;
      name: string;
      lang: string;
      gender?: Voice['gender'];
      expressive?: boolean;
      chant?: boolean;
      clone?: boolean;
      premium?: boolean;
      locked?: boolean;
    }>;
    this.reachable = true;
    return data.map((v) => ({
      id: `server:${v.id}`,
      name: v.name,
      lang: v.lang,
      gender: v.gender ?? 'neutral',
      provider: 'server' as const,
      downloadable: true,
      expressive: v.expressive,
      chant: v.chant,
      clone: v.clone,
      premium: v.premium,
      locked: v.locked,
    }));
  }

  isReachable(): boolean {
    return this.reachable;
  }

  async synthesizeToBlob(
    req: SynthesisRequest,
    format: 'wav' | 'mp3'
  ): Promise<Blob> {
    // Some voices run on CPU and are genuinely slow — a long passage can take
    // several minutes. Without a ceiling a dropped connection leaves the UI
    // spinning forever, so allow a generous wait but always end in an answer.
    let res: Response;
    try {
      res = await fetch(`${API_BASE}/synthesize`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        signal: AbortSignal.timeout(SYNTH_TIMEOUT_MS),
        body: JSON.stringify({
          text: req.text,
          voiceId: req.voiceId.replace(/^server:/, ''),
          rate: req.rate,
          pitch: req.pitch,
          volume: req.volume,
          emotion: req.emotion ?? 'neutral',
          intensity: req.intensity ?? 1,
          meter: req.meter,
          format,
        }),
      });
    } catch (e) {
      // Timed out, or the connection was dropped mid-render. Either way the
      // user needs to be told rather than left watching a spinner.
      if ((e as Error)?.name === 'TimeoutError') {
        throw new Error(
          'This voice is taking too long to render. Try a shorter passage, ' +
            'or pick one of the faster voices.'
        );
      }
      throw new Error('Lost connection while generating. Please try again.');
    }
    if (!res.ok) {
      // The server explains a refusal properly — a 402 may be an exhausted
      // allowance OR a voice the plan does not include, and only it knows
      // which. Fall back to a status message when there is no body.
      let fromServer = '';
      let code = '';
      try {
        const body = (await res.json()) as { error?: string; code?: string };
        fromServer = body.error ?? '';
        code = body.code ?? '';
      } catch {
        /* no JSON body */
      }
      const map: Record<number, string> = {
        400: 'Invalid input.',
        402: 'Your plan does not cover this. Check your plan on the Pricing page.',
        413: 'Text is too long for the server voice.',
        429: 'Too many requests — please wait a moment.',
        500: 'Server synthesis failed.',
      };
      // Carry the server's own code so callers can react — a WAV refused on a
      // free plan should quietly become an mp3, not an error in the user's face.
      const err = new Error(
        fromServer || map[res.status] || `Server error (${res.status}).`
      ) as Error & { code?: string };
      err.code = code;
      throw err;
    }
    return res.blob();
  }

  async speak(req: SynthesisRequest, cb: SynthesisCallbacks): Promise<void> {
    this.stop();
    // Playback uses mp3: it sounds the same through speakers, transfers far
    // less over a phone connection, and WAV is a paid *download* format — a
    // free account must still be able to listen to what it generates.
    const blob = await this.synthesizeToBlob(req, 'mp3');
    const url = URL.createObjectURL(blob);
    // Reuse the gesture-unlocked shared element so play() is permitted on
    // Safari/iOS/mobile even though we're past the original click's gesture.
    const audio = sharedAudio();
    audio.src = url;
    audio.volume = req.volume;
    this.audio = audio;

    const words = req.text.split(/\s+/).filter(Boolean);

    return new Promise((resolve, reject) => {
      audio.onplay = () => cb.onStart?.();
      audio.onloadedmetadata = () => {
        // Estimate per-word timing from total duration for highlighting.
        if (this.highlightTimer) window.clearInterval(this.highlightTimer);
        const perWord = (audio.duration * 1000) / Math.max(words.length, 1);
        this.highlightTimer = window.setInterval(() => {
          if (audio.paused) return;
          const idx = Math.min(
            Math.floor((audio.currentTime * 1000) / perWord),
            words.length - 1
          );
          cb.onBoundary?.(0, idx);
        }, Math.max(perWord / 2, 60));
      };
      audio.onended = () => {
        this.clearTimer();
        URL.revokeObjectURL(url);
        cb.onEnd?.();
        resolve();
      };
      audio.onerror = () => {
        this.clearTimer();
        URL.revokeObjectURL(url);
        const err = new Error('Could not play server audio.');
        cb.onError?.(err);
        reject(err);
      };
      audio.play().catch(() => {
        // Autoplay still blocked (no prior gesture this session) — report it
        // instead of failing silently.
        this.clearTimer();
        URL.revokeObjectURL(url);
        const err = new Error(
          'Tap anywhere once, then press Play — your browser blocked autoplay.'
        );
        cb.onError?.(err);
        reject(err);
      });
    });
  }

  private clearTimer() {
    if (this.highlightTimer) {
      window.clearInterval(this.highlightTimer);
      this.highlightTimer = null;
    }
  }

  pause(): void {
    this.audio?.pause();
  }

  resume(): void {
    void this.audio?.play();
  }

  stop(): void {
    this.clearTimer();
    if (this.audio) {
      this.audio.pause();
      this.audio.currentTime = 0;
      this.audio = null;
    }
  }
}
