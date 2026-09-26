// EmotionSong API client (script -> AI song, API-free backend).
const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';

export interface EmotionResult {
  scores: Record<string, number>;
  dominant: string;
}
export interface AnalyzeResult {
  emotion: EmotionResult;
  lyrics: string;
  title: string;
}
export interface SongRow {
  id: string;
  title: string;
  genre: string;
  language: string;
  voice_id?: string;
  emotion: string;
  emotion_json?: string;
  lyrics?: string;
  status: 'queued' | 'processing' | 'done' | 'failed';
  progress: number;
  current_step: string;
  duration_seconds?: number;
  error?: string | null;
  created_at?: string;
  parent_id?: string | null;
  stems_status?: 'none' | 'processing' | 'done' | 'failed';
}

export interface CloneVoice {
  id: string; // e.g. "clone:uuid"
  name: string;
  lang: string;
}

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    ...opts,
  });
  if (!res.ok) {
    let msg = `Error ${res.status}`;
    try {
      msg = (await res.json()).error ?? msg;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export const analyzeScript = (
  script: string,
  title: string,
  opts?: { language?: string; genre?: string; mood?: string }
) =>
  req<AnalyzeResult>('/song/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ script, title, ...opts }),
  });

export const createSong = (payload: {
  script: string;
  title: string;
  genre: string;
  language: string;
  vocals: string;
  emotion?: string;
  mood?: string;
  singer_style?: string;
  bpm?: number;
  musical_key?: string;
  lyrics?: string;
  duration: number;
  ref_voice_id?: string;
  timbre?: string;
  instruments?: string[];
  melody?: {
    notation: string;
    system: string;
    tonic: string;
    bpm: number;
    instrument?: string;
    strength?: number;
  };
}) =>
  req<{ id: string }>('/song/create', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

export async function extractFile(file: File): Promise<{ text: string }> {
  const ext = (file.name.split('.').pop() || '').toLowerCase();
  const type = ext === 'pdf' ? 'pdf' : ext === 'docx' || ext === 'doc' ? 'docx' : 'txt';
  if (type === 'txt') return { text: await file.text() };
  const res = await fetch(`${API_BASE}/song/extract?type=${type}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: file,
  });
  if (!res.ok) {
    let m = 'Could not read file.';
    try {
      m = (await res.json()).error ?? m;
    } catch {
      /* ignore */
    }
    throw new Error(m);
  }
  return res.json();
}

export const getSong = (id: string) => req<SongRow>(`/song/${id}`);
export const listSongs = () => req<SongRow[]>('/song/list');
export const deleteSong = (id: string) =>
  req<{ ok: boolean }>(`/song/${id}`, { method: 'DELETE' });
export const songAudioUrl = (id: string) => `${API_BASE}/song/${id}/audio`;

// --- Regenerate (new take) + versioning ---
export const regenerateSong = (id: string, newLyrics = false) =>
  req<{ id: string }>(`/song/${id}/regenerate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_lyrics: newLyrics }),
  });

// --- Stems / karaoke / instrumental (Demucs) ---
export const startStems = (id: string) =>
  req<{ stems_status: string }>(`/song/${id}/stems`, { method: 'POST' });
export const stemUrl = (id: string, kind: string) =>
  `${API_BASE}/song/${id}/stem/${kind}`;

// --- "Sing in my voice" — user's own cloned voices ---
export async function listCloneVoices(): Promise<CloneVoice[]> {
  const all = await req<Array<{ id: string; name: string; lang: string; clone?: boolean }>>('/voices');
  return all.filter((v) => v.clone);
}
