// Client for the AI tools: Dubbing, Voice Isolator, Speech-to-Text.
const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';

async function uploadForm<T>(
  path: string,
  file: File,
  fields: Record<string, string | number> = {}
): Promise<T> {
  const fd = new FormData();
  fd.append('file', file);
  for (const k of Object.keys(fields)) fd.append(k, String(fields[k]));
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    body: fd,
  });
  if (!res.ok) {
    let m = `Error ${res.status}`;
    try {
      m = (await res.json()).error ?? m;
    } catch {
      /* ignore */
    }
    throw new Error(m);
  }
  return res.json() as Promise<T>;
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Error ${res.status}`);
  return res.json() as Promise<T>;
}

export interface JobStatus {
  status: 'queued' | 'processing' | 'done' | 'failed';
  step?: string;
  progress?: number;
  error?: string;
}

/* ---------------- Dubbing ---------------- */
export const DUB_LANGS: Array<[string, string]> = [
  ['hi', 'Hindi'], ['ta', 'Tamil'], ['te', 'Telugu'], ['kn', 'Kannada'],
  ['ml', 'Malayalam'], ['bn', 'Bengali'], ['mr', 'Marathi'], ['gu', 'Gujarati'],
  ['pa', 'Punjabi'], ['or', 'Odia'], ['as', 'Assamese'], ['ne', 'Nepali'],
  ['en', 'English'],
];
export interface DubResult extends JobStatus {
  is_video?: boolean;
  /** How many distinct speakers were detected in the source. */
  speakers?: number;
  /** spk = which speaker said it, emo = the emotion it is performed with. */
  transcript?: Array<{ t: string; tr: string; spk?: number; emo?: string }>;
}
export const createDub = (
  file: File, target_lang: string, keep_bg = 0, voice = '', preserve_voice = false,
) =>
  uploadForm<{ id: string }>('/dub', file, {
    target_lang,
    keep_bg,
    ...(voice ? { voice } : {}),
    ...(preserve_voice ? { preserve_voice: '1' } : {}),
  });
export const dubStatus = (id: string) => getJSON<DubResult>(`/dub/${id}`);
export const dubFileUrl = (id: string) => `${API_BASE}/dub/${id}/file`;

/* ---------------- Voice Isolator ---------------- */
export interface IsolateResult extends JobStatus {
  kinds?: string[];
}
export const createIsolate = (file: File) =>
  uploadForm<{ id: string }>('/isolate', file, {});
export const isolateStatus = (id: string) => getJSON<IsolateResult>(`/isolate/${id}`);
export const isolateFileUrl = (id: string, kind: string) =>
  `${API_BASE}/isolate/${id}/file/${kind}`;

/* ---------------- Voices (for dubbing / audiobook pickers) ---------------- */
export interface ServerVoice { id: string; name: string; lang: string; gender?: string }
export const listVoices = () => getJSON<ServerVoice[]>('/voices');

/* ---------------- Audiobook / Long-form ---------------- */
export interface BookResult extends JobStatus { chunks?: number }
export const createAudiobook = (text: string, voice: string, gap_ms = 400) =>
  fetch(`${API_BASE}/audiobook`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, voice, gap_ms }),
  }).then(async (r) => {
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `Error ${r.status}`);
    return r.json() as Promise<{ id: string }>;
  });
export const audiobookStatus = (id: string) => getJSON<BookResult>(`/audiobook/${id}`);
export const audiobookFileUrl = (id: string) => `${API_BASE}/audiobook/${id}/file`;

/* ---------------- Audio Native (embeddable player) ---------------- */
export interface AudioNativeResult extends JobStatus { embed_url?: string }
export const createAudioNative = (text: string, title: string, voice: string) =>
  fetch(`${API_BASE}/audionative`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, title, voice }),
  }).then(async (r) => {
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `Error ${r.status}`);
    return r.json() as Promise<{ id: string; embed_url: string }>;
  });
export const audioNativeStatus = (id: string) => getJSON<AudioNativeResult>(`/audionative/${id}`);

/* ---------------- Ads Engine ---------------- */
export interface AdsResult extends JobStatus { script?: string }
export const createAd = (brief: string, language: string, voice: string, tone: string, seconds: number) =>
  fetch(`${API_BASE}/ads`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ brief, language, voice, tone, seconds }),
  }).then(async (r) => {
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `Error ${r.status}`);
    return r.json() as Promise<{ id: string }>;
  });
export const adStatus = (id: string) => getJSON<AdsResult>(`/ads/${id}`);
export const adFileUrl = (id: string) => `${API_BASE}/ads/${id}/file`;

/* ---------------- Sound Effects ---------------- */
export interface SfxResult extends JobStatus {}
export const createSfx = (prompt: string, duration: number) =>
  fetch(`${API_BASE}/sfx`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, duration }),
  }).then(async (r) => {
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `Error ${r.status}`);
    return r.json() as Promise<{ id: string }>;
  });
export const sfxStatus = (id: string) => getJSON<SfxResult>(`/sfx/${id}`);
export const sfxFileUrl = (id: string) => `${API_BASE}/sfx/${id}/file`;

/* ---------------- Conversational Voice Agent ---------------- */
export interface ChatMsg { role: 'user' | 'assistant'; content: string }
export interface AgentTurn { transcript: string; reply: string; audio: string }

export const agentChat = (text: string, history: ChatMsg[]) =>
  fetch(`${API_BASE}/agent/chat`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, history }),
  }).then(async (r) => {
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `Error ${r.status}`);
    return r.json() as Promise<AgentTurn>;
  });

export const agentVoice = (file: File, history: ChatMsg[]) =>
  uploadForm<AgentTurn>('/agent/voice', file, { history: JSON.stringify(history) });

/* ---------------- Speech to Text ---------------- */
export interface Transcript {
  language: string;
  text: string;
  segments: Array<{ start: number; end: number; text: string }>;
}
export const transcribe = (file: File) =>
  uploadForm<Transcript>('/transcribe', file, {});
