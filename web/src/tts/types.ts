// TTS abstraction layer — mirrors TRD §4.
// A single interface lets the UI treat browser + self-hosted voices identically.

export interface Voice {
  id: string; // namespaced, e.g. "browser:Samantha" or "server:kokoro-en-1"
  name: string;
  lang: string; // BCP-47, e.g. "en-US"
  gender?: 'male' | 'female' | 'neutral';
  provider: 'browser' | 'server';
  downloadable: boolean; // true => can export a real audio file
  expressive?: boolean; // reacts to emotion/tone shaping
  chant?: boolean; // Sanskrit chant voice (metre controls)
  clone?: boolean; // a user's cloned voice (deletable)
  premium?: boolean; // belongs to the paid plans
  locked?: boolean; // premium, and this account's plan does not include it
}

export interface SynthesisRequest {
  text: string;
  voiceId: string;
  rate: number; // 0.5 - 2.0
  pitch: number; // 0 - 2.0
  volume: number; // 0 - 1.0
  // 20 emotions: core feelings (happy|sad|angry|fear|surprise|disgust|excited|
  // calm|romantic|empathetic) + delivery styles (narration|conversation|news|
  // command|serious|confident|urgent|whisper|sarcastic). Real on Parler,
  // Chatterbox and IndexTTS-2.
  emotion?: string;
  // Free-form emotion description (IndexTTS-2), e.g. "heartbroken but trying
  // to stay strong". Overrides `emotion` when set.
  emotionText?: string;
  intensity?: number; // 0 (subtle) - 2 (dramatic); scales the emotion strength
  meter?: string; // Sanskrit metre for the Vāgdhenu chant voice (e.g. anushtubh)
}

export interface SynthesisCallbacks {
  onStart?(): void;
  /** Server voices: the whole take exists and is cached, so asking for the
   *  file again (the result player, a download) is instant and free. */
  onReady?(): void;
  onBoundary?(charIndex: number, wordIndex: number): void;
  onEnd?(): void;
  onError?(e: Error): void;
}

export interface TTSProvider {
  id: 'browser' | 'server';
  listVoices(): Promise<Voice[]>;
  supportsDownload(): boolean;
  speak(req: SynthesisRequest, cb: SynthesisCallbacks): Promise<void>;
  /** Server-only: returns a true audio file for export. */
  synthesizeToBlob?(
    req: SynthesisRequest,
    format: 'wav' | 'mp3'
  ): Promise<Blob>;
  pause(): void;
  resume(): void;
  stop(): void;
}
