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

/* --- per-account scoping ------------------------------------------------ */
/* One shared key meant one user could read another's history on the same
   computer. Every account now gets its own, keyed by a short hash of the email
   so the address itself is not written into browser storage.                */
let currentAccount: string | null = null;

function shortHash(s: string): string {
  // FNV-1a — tiny, stable, and enough to separate accounts. Not a security
  // boundary: the point is isolation between users of one browser, and the
  // real protection is that the server never serves another account's data.
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(36);
}

/** Point storage at one account. Pass null when signed out. */
export function setStorageAccount(email: string | null): void {
  currentAccount = email ? email.trim().toLowerCase() : null;
}

function historyKey(): string {
  return currentAccount ? `${HISTORY_KEY}::${shortHash(currentAccount)}` : HISTORY_KEY;
}
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
    const raw = localStorage.getItem(historyKey());
    return raw ? (JSON.parse(raw) as Generation[]) : [];
  } catch {
    return [];
  }
}

export function saveHistory(items: Generation[]): boolean {
  try {
    // The account's own key. (It used to write the old shared key, which the
    // next sign-in wiped and loadHistory never read: history vanished on every
    // reload and sat where another account on this browser could read it.)
    localStorage.setItem(
      historyKey(),
      JSON.stringify(items.slice(0, HISTORY_CAP))
    );
    return true;
  } catch {
    return false;
  }
}

/** Remove the old shared history key, which every account could read. */
export function purgeSharedHistory(): void {
  try {
    localStorage.removeItem(HISTORY_KEY);
  } catch {
    /* storage blocked — nothing to purge */
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

/** Forget the current account's history on this device (account deletion). */
export function clearAccountHistory(): void {
  try {
    if (currentAccount) localStorage.removeItem(historyKey());
  } catch {
    /* storage blocked — nothing stored to remove */
  }
}
