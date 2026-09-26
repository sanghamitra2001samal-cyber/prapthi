// Notation -> audio (Sargam / solfège / letter notes), exact-note rendering.
const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';

export interface MelodySummary {
  system: 'sargam' | 'western' | 'solfege';
  notes: number;
  beats: number;
}

export interface MelodyParams {
  notation: string;
  system: string; // 'auto' | 'sargam' | 'western' | 'solfege'
  tonic: string;
  instrument: string;
  bpm: number;
}

export async function summarizeMelody(
  notation: string,
  system: string,
  tonic: string
): Promise<MelodySummary> {
  const res = await fetch(`${API_BASE}/melody/summary`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ notation, system, tonic }),
  });
  if (!res.ok) {
    let m = 'Invalid notation.';
    try {
      m = (await res.json()).error ?? m;
    } catch {
      /* ignore */
    }
    throw new Error(m);
  }
  return res.json();
}

/** Render a melody and return an object URL for playback/download. */
export async function renderMelody(p: MelodyParams): Promise<string> {
  const res = await fetch(`${API_BASE}/melody/render`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(p),
  });
  if (!res.ok) {
    let m = 'Render failed.';
    try {
      m = (await res.json()).error ?? m;
    } catch {
      /* ignore */
    }
    throw new Error(m);
  }
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}
