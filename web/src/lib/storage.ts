// localStorage wrappers (TRD §8.1). All access is guarded so a blocked or
// full storage degrades gracefully instead of throwing.

export interface Generation {
  id: string;
  text: string;
  voiceId: string;
  voiceName: string;
  rate: number;
  pitch: number;
  volume: number;
  emotion?: string; // Parler HD emotion preset; absent = neutral (legacy)
  intensity?: number; // emotion strength 0-2; absent = 1 (legacy)
  createdAt: number; // epoch ms
}

export interface Prefs {
  lastVoiceId: string | null;
  rate: number;
  pitch: number;
  volume: number;
  emotion?: string;
  intensity?: number;
  meter?: string;
}

const HISTORY_KEY = 'vf_history';
const PREFS_KEY = 'vf_prefs';
const HISTORY_CAP = 20;

export const DEFAULT_PREFS: Prefs = {
  lastVoiceId: null,
  rate: 1.0,
  pitch: 1.0,
  volume: 1.0,
};

export function storageAvailable(): boolean {
  try {
    const k = '__vf_test__';
    localStorage.setItem(k, '1');
    localStorage.removeItem(k);
    return true;
  } catch {
    return false;
  }
}

export function loadHistory(): Generation[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? (JSON.parse(raw) as Generation[]) : [];
  } catch {
    return [];
  }
}

export function saveHistory(items: Generation[]): boolean {
  try {
    localStorage.setItem(
      HISTORY_KEY,
      JSON.stringify(items.slice(0, HISTORY_CAP))
    );
    return true;
  } catch {
    return false;
  }
}

export function loadPrefs(): Prefs {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    return raw ? { ...DEFAULT_PREFS, ...JSON.parse(raw) } : { ...DEFAULT_PREFS };
  } catch {
    return { ...DEFAULT_PREFS };
  }
}

export function savePrefs(prefs: Prefs): void {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    /* ignore — best effort */
  }
}
