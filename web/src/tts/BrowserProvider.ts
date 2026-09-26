import type {
  TTSProvider,
  Voice,
  SynthesisRequest,
  SynthesisCallbacks,
} from './types';

// Heuristic gender guess from common voice names (browser voices rarely
// expose gender metadata). Best-effort only — used for the filter chips.
const FEMALE = /samantha|victoria|karen|moira|tessa|fiona|zira|susan|allison|ava|serena|kate|amelie|anna|female|woman|girl|zoe|nora|sandy/i;
const MALE = /daniel|alex|fred|tom|david|mark|oliver|rishi|aaron|male|man|boy|diego|jorge|luca|thomas|gordon/i;

function guessGender(name: string): Voice['gender'] {
  if (FEMALE.test(name)) return 'female';
  if (MALE.test(name)) return 'male';
  return 'neutral';
}

const countWords = (s: string): number =>
  s.trim() ? s.trim().split(/\s+/).length : 0;

/**
 * Split text into short, sentence-sized chunks.
 *
 * Chrome's SpeechSynthesis stops or stutters on long utterances (it silently
 * cuts out after ~15s, and truncates very long strings). Speaking short chunks
 * back-to-back sidesteps that entirely — each utterance finishes well within
 * the limit — and avoids the glitchy pause()/resume() keep-alive hack that
 * itself causes audible clicks. Chunks break on sentence boundaries, with long
 * sentences further split at clause/space boundaries so no chunk exceeds ~200
 * characters. Boundaries always fall on whitespace so word counts stay aligned
 * with the editor's highlighting.
 */
function chunkText(text: string, maxLen = 200): string[] {
  const sentences = text.match(/[^.!?\n]+[.!?]*\n*\s*|\s+/g) ?? [text];
  const chunks: string[] = [];
  let buf = '';

  const flush = () => {
    if (buf.trim()) chunks.push(buf);
    buf = '';
  };

  for (const piece of sentences) {
    if (piece.length > maxLen) {
      // Very long sentence — split on spaces into <=maxLen windows.
      flush();
      const words = piece.split(/(\s+)/);
      for (const w of words) {
        if ((buf + w).length > maxLen && buf.trim()) flush();
        buf += w;
      }
      flush();
    } else if ((buf + piece).length > maxLen && buf.trim()) {
      flush();
      buf = piece;
    } else {
      buf += piece;
    }
  }
  flush();
  return chunks.length ? chunks : [text];
}

/**
 * BrowserProvider — wraps window.speechSynthesis.
 * Free, on-device, zero network. Cannot return an audio file on its own
 * (export goes through MediaRecorder best-effort; see lib/recorder.ts).
 */
export class BrowserProvider implements TTSProvider {
  id = 'browser' as const;
  private synth = window.speechSynthesis;
  private runId = 0;

  supportsDownload(): boolean {
    // No direct file. Export is handled best-effort via MediaRecorder.
    return false;
  }

  listVoices(): Promise<Voice[]> {
    return new Promise((resolve) => {
      if (!('speechSynthesis' in window)) {
        resolve([]);
        return;
      }
      const map = (vs: SpeechSynthesisVoice[]): Voice[] =>
        vs.map((v) => ({
          id: `browser:${v.voiceURI}`,
          name: v.name,
          lang: v.lang || 'en-US',
          gender: guessGender(v.name),
          provider: 'browser' as const,
          downloadable: false,
        }));

      const existing = this.synth.getVoices();
      if (existing.length) {
        resolve(map(existing));
        return;
      }
      // Voices often load async — listen for voiceschanged, with a timeout
      // fallback so we never hang if the event never fires.
      let settled = false;
      const done = () => {
        if (settled) return;
        settled = true;
        resolve(map(this.synth.getVoices()));
      };
      this.synth.addEventListener('voiceschanged', done, { once: true });
      setTimeout(done, 1500);
    });
  }

  private resolveVoice(voiceId: string): SpeechSynthesisVoice | undefined {
    const uri = voiceId.replace(/^browser:/, '');
    return this.synth.getVoices().find((v) => v.voiceURI === uri);
  }

  speak(req: SynthesisRequest, cb: SynthesisCallbacks): Promise<void> {
    return new Promise((resolve, reject) => {
      this.stop();
      // Each speak() call gets a token; a later stop()/speak() invalidates this
      // run so stale utterance callbacks can't resume a cancelled queue.
      const token = ++this.runId;
      const voice = this.resolveVoice(req.voiceId);
      const chunks = chunkText(req.text);
      let wordOffset = 0;
      let started = false;

      const makeUtterance = (chunk: string): SpeechSynthesisUtterance => {
        const u = new SpeechSynthesisUtterance(chunk);
        if (voice) {
          u.voice = voice;
          u.lang = voice.lang;
        }
        u.rate = req.rate;
        u.pitch = req.pitch;
        u.volume = req.volume;
        return u;
      };

      const speakChunk = (i: number) => {
        if (token !== this.runId) return; // cancelled
        if (i >= chunks.length) {
          cb.onEnd?.();
          resolve();
          return;
        }
        const chunk = chunks[i];
        const u = makeUtterance(chunk);

        u.onstart = () => {
          if (!started) {
            started = true;
            cb.onStart?.();
          }
        };
        u.onboundary = (e: SpeechSynthesisEvent) => {
          const upto = chunk.slice(0, e.charIndex);
          const localWord = (upto.match(/\S+\s+/g) || []).length;
          cb.onBoundary?.(e.charIndex, wordOffset + localWord);
        };
        u.onend = () => {
          if (token !== this.runId) return;
          wordOffset += countWords(chunk);
          speakChunk(i + 1);
        };
        u.onerror = (e: SpeechSynthesisErrorEvent) => {
          // "interrupted"/"canceled" are normal when the user hits Stop.
          if (e.error === 'interrupted' || e.error === 'canceled') {
            resolve();
            return;
          }
          if (token !== this.runId) return;
          const err = new Error(`Speech synthesis failed: ${e.error}`);
          cb.onError?.(err);
          reject(err);
        };

        this.synth.speak(u);
      };

      speakChunk(0);
    });
  }

  pause(): void {
    if (this.synth.speaking && !this.synth.paused) this.synth.pause();
  }

  resume(): void {
    if (this.synth.paused) this.synth.resume();
  }

  stop(): void {
    // Invalidate any in-flight chunk queue before cancelling so its onend
    // callback can't kick off the next chunk.
    this.runId++;
    if ('speechSynthesis' in window) this.synth.cancel();
  }
}
