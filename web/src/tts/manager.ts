import { BrowserProvider } from './BrowserProvider';
import { ServerProvider } from './ServerProvider';
import type { Voice, TTSProvider } from './types';

/**
 * TTSManager — single entry point the UI uses. Aggregates voices from both
 * providers and routes speak/stop/export to whichever provider owns the
 * active voice.
 */
export class TTSManager {
  readonly browser = new BrowserProvider();
  readonly server = new ServerProvider();

  private providerFor(voiceId: string): TTSProvider {
    return voiceId.startsWith('server:') ? this.server : this.browser;
  }

  async listVoices(): Promise<Voice[]> {
    // Only the self-hosted neural voices are part of the product. The browser's
    // built-in speechSynthesis voices used to be merged in as a fallback, but
    // on phones they flooded the picker with dozens of raw locale codes and
    // unsupported languages (Danish, Greek…) and were far lower quality, while
    // on desktop the browser exposes almost none — so the two views looked
    // completely different. They're now intentionally excluded from the picker.
    return this.server.listVoices();
  }

  serverReachable(): boolean {
    return this.server.isReachable();
  }

  get(voiceId: string): TTSProvider {
    return this.providerFor(voiceId);
  }
}

export const tts = new TTSManager();
