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

/** Frames of a streamed passage (server/app.py `_synth`, stream branch). */
const STREAM_TYPE = 'application/x-prapthi-stream';
/** Streaming needs a readable response body; very old WebViews lack one. */
const CAN_STREAM =
  typeof ReadableStream !== 'undefined' &&
  typeof Response !== 'undefined' &&
  'body' in Response.prototype;

/** HTMLMediaElement.volume throws outside 0..1; the studio allows up to 1.5. */
const clampVolume = (v: number) => Math.min(1, Math.max(0, v));

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
  private controller: AbortController | null = null;
  private cancelStream: (() => void) | null = null;
  private resumeStream: (() => void) | null = null;
  private userPaused = false;

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
    const res = await this.#request(
      req,
      format,
      false,
      AbortSignal.timeout(SYNTH_TIMEOUT_MS)
    );
    return res.blob();
  }

  /** POST /synthesize and turn every failure into a message a person can act
   *  on. With `stream`, a passage of several sentences comes back as frames
   *  (see #playStream); a cache hit or a single sentence is still plain audio. */
  async #request(
    req: SynthesisRequest,
    format: 'wav' | 'mp3',
    stream: boolean,
    signal: AbortSignal
  ): Promise<Response> {
    // Some voices run on CPU and are genuinely slow — a long passage can take
    // several minutes. Without a ceiling a dropped connection leaves the UI
    // spinning forever, so allow a generous wait but always end in an answer.
    let res: Response;
    try {
      res = await fetch(`${API_BASE}/synthesize`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        signal,
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
          stream,
        }),
      });
    } catch (e) {
      throw this.#networkError(e);
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
        503: 'The server is busy right now — please try again in a moment.',
      };
      // Carry the server's own code so callers can react — a WAV refused on a
      // free plan should quietly become an mp3, not an error in the user's face.
      const err = new Error(
        fromServer || map[res.status] || `Server error (${res.status}).`
      ) as Error & { code?: string };
      err.code = code;
      throw err;
    }
    return res;
  }

  #networkError(e: unknown): Error {
    const name = (e as Error)?.name;
    // Timed out, or the connection was dropped mid-render. Either way the
    // user needs to be told rather than left watching a spinner.
    if (name === 'TimeoutError') {
      return new Error(
        'This voice is taking too long to render. Try a shorter passage, ' +
          'or pick one of the faster voices.'
      );
    }
    if (name === 'AbortError') return new Error('Stopped.');
    return new Error('Lost connection while generating. Please try again.');
  }

  async speak(req: SynthesisRequest, cb: SynthesisCallbacks): Promise<void> {
    this.stop();
    const ctrl = new AbortController();
    this.controller = ctrl;
    const timer = window.setTimeout(
      () => ctrl.abort(new DOMException('timed out', 'TimeoutError')),
      SYNTH_TIMEOUT_MS
    );
    try {
      // Playback uses mp3: it sounds the same through speakers, transfers far
      // less over a phone connection, and WAV is a paid *download* format — a
      // free account must still be able to listen to what it generates.
      const res = await this.#request(req, 'mp3', CAN_STREAM, ctrl.signal);
      if (res.headers.get('Content-Type')?.startsWith(STREAM_TYPE)) {
        await this.#playStream(res, req, cb, ctrl);
        return;
      }
      const blob = await res.blob();
      if (ctrl.signal.aborted) return;
      await this.#playBlob(blob, req, cb);
    } catch (e) {
      if (ctrl.signal.aborted && (e as Error)?.name !== 'TimeoutError' &&
          this.controller !== ctrl) {
        return; // stopped by the user, or replaced by a newer request
      }
      throw e;
    } finally {
      window.clearTimeout(timer);
      if (this.controller === ctrl) this.controller = null;
    }
  }

  /** Play one finished file on the shared element (cache hit, one sentence). */
  #playBlob(blob: Blob, req: SynthesisRequest, cb: SynthesisCallbacks) {
    const url = URL.createObjectURL(blob);
    // Reuse the gesture-unlocked shared element so play() is permitted on
    // Safari/iOS/mobile even though we're past the original click's gesture.
    const audio = sharedAudio();
    audio.src = url;
    audio.volume = clampVolume(req.volume);
    this.audio = audio;

    const words = req.text.split(/\s+/).filter(Boolean);

    return new Promise<void>((resolve, reject) => {
      let started = false;
      audio.onplay = () => {
        cb.onStart?.();
        // The file is whole already; onReady follows onStart so the caller has
        // recorded this generation before it asks for the file again.
        if (!started) cb.onReady?.();
        started = true;
      };
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

  /**
   * Play a streamed passage: each sentence arrives as its own mp3 and plays
   * on the shared element as soon as the one before it ends, while the server
   * is still making the rest. Frames are a 1-byte kind, a 4-byte big-endian
   * length and the payload: M (sentence word counts, JSON), A (one sentence of
   * mp3), D (done — the whole take is cached), E (failed, with a message).
   */
  #playStream(
    res: Response,
    req: SynthesisRequest,
    cb: SynthesisCallbacks,
    ctrl: AbortController
  ): Promise<void> {
    const audio = sharedAudio();
    audio.volume = clampVolume(req.volume);
    this.audio = audio;

    const queue: { url: string; index: number }[] = [];
    let chunkWords: number[] = [];
    let current = -1; // sentence now on the element
    let finished = false; // D received
    let failure: Error | null = null;
    let started = false;
    let ready = false; // D arrived before playback began; report on start
    let settled = false;
    let waiting = false; // element idle until the next sentence arrives
    const clientWords = Math.max(req.text.split(/\s+/).filter(Boolean).length, 1);

    return new Promise<void>((resolve, reject) => {
      const urls: string[] = [];
      const cleanup = () => {
        this.clearTimer();
        urls.forEach((u) => URL.revokeObjectURL(u));
        audio.onended = audio.onerror = audio.onloadedmetadata = null;
        audio.onplay = null;
      };
      const settle = (err: Error | null) => {
        if (settled) return;
        settled = true;
        cleanup();
        if (err) {
          cb.onError?.(err);
          reject(err);
        } else {
          cb.onEnd?.();
          resolve();
        }
      };
      this.cancelStream = () => {
        settled = true;
        cleanup();
        resolve();
      };

      // Highlight: where this sentence sits in the passage, scaled to the
      // words the page shows (the server may have rewritten numbers etc.).
      const highlight = () => {
        if (audio.paused || current < 0 || !chunkWords.length) return;
        const total = chunkWords.reduce((a, b) => a + b, 0) || 1;
        const before = chunkWords.slice(0, current).reduce((a, b) => a + b, 0);
        const frac = audio.duration ? audio.currentTime / audio.duration : 0;
        const pos = (before + frac * (chunkWords[current] ?? 0)) / total;
        cb.onBoundary?.(0, Math.min(Math.floor(pos * clientWords), clientWords - 1));
      };

      const playNext = () => {
        if (settled) return;
        const next = queue.shift();
        if (!next) {
          if (failure) settle(failure);
          else if (finished) settle(null);
          else waiting = true;
          return;
        }
        waiting = false;
        current = next.index;
        audio.src = next.url;
        if (this.userPaused) return; // resume() picks it up
        audio.play().catch(() => {
          settle(
            new Error(
              'Tap anywhere once, then press Play — your browser blocked autoplay.'
            )
          );
        });
      };

      audio.onplay = () => {
        if (!started) {
          started = true;
          cb.onStart?.();
          if (ready) cb.onReady?.();
          this.highlightTimer = window.setInterval(highlight, 120);
        }
      };
      audio.onended = () => playNext();
      audio.onerror = () => settle(new Error('Could not play server audio.'));
      this.resumeStream = () => {
        if (waiting) playNext();
        else void audio.play();
      };

      const enqueue = (mp3: Uint8Array<ArrayBuffer>, index: number) => {
        const url = URL.createObjectURL(new Blob([mp3], { type: 'audio/mpeg' }));
        urls.push(url);
        queue.push({ url, index });
        if (index === 0 || waiting) playNext();
      };

      void (async () => {
        const reader = res.body!.getReader();
        let buf: Uint8Array<ArrayBuffer> = new Uint8Array(0);
        let index = 0;
        try {
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            const merged = new Uint8Array(buf.length + value.length);
            merged.set(buf);
            merged.set(value, buf.length);
            buf = merged;
            while (buf.length >= 5) {
              const len = new DataView(buf.buffer, buf.byteOffset + 1, 4).getUint32(0);
              if (buf.length < 5 + len) break;
              const kind = String.fromCharCode(buf[0]);
              const payload = buf.slice(5, 5 + len);
              buf = buf.slice(5 + len);
              if (kind === 'M') {
                try {
                  chunkWords = (JSON.parse(new TextDecoder().decode(payload)) as {
                    words: number[];
                  }).words;
                } catch {
                  /* highlight falls back to nothing */
                }
              } else if (kind === 'A') {
                enqueue(payload, index++);
              } else if (kind === 'D') {
                finished = true;
                if (started) cb.onReady?.();
                else ready = true;
              } else if (kind === 'E') {
                failure = new Error(
                  new TextDecoder().decode(payload) || 'Server synthesis failed.'
                );
              }
            }
          }
        } catch (e) {
          if (ctrl.signal.aborted && !failure) {
            if ((ctrl.signal.reason as Error)?.name === 'TimeoutError') {
              failure = this.#networkError(ctrl.signal.reason);
            } else {
              return; // stopped by the user
            }
          } else {
            failure = this.#networkError(e);
          }
        }
        if (!finished && !failure) {
          failure = new Error('Lost connection while generating. Please try again.');
        }
        // Nothing playing and nothing left to play: report now; otherwise the
        // queue drains first and playNext() reports.
        if (waiting || current < 0) playNext();
      })();
    });
  }

  private clearTimer() {
    if (this.highlightTimer) {
      window.clearInterval(this.highlightTimer);
      this.highlightTimer = null;
    }
  }

  pause(): void {
    this.userPaused = true;
    this.audio?.pause();
  }

  resume(): void {
    this.userPaused = false;
    if (this.resumeStream) this.resumeStream();
    else void this.audio?.play();
  }

  stop(): void {
    this.clearTimer();
    this.userPaused = false;
    // The server finishes and caches a streamed take even after we leave, so
    // pressing Play again does not pay for it twice.
    this.controller?.abort();
    this.controller = null;
    this.cancelStream?.();
    this.cancelStream = null;
    this.resumeStream = null;
    if (this.audio) {
      this.audio.pause();
      this.audio.currentTime = 0;
      this.audio = null;
    }
  }
}
