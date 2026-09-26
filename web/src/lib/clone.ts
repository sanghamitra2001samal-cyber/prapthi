// Voice-cloning API calls (premium expressive clones via Chatterbox).
const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';

export interface CloneResult {
  ok: boolean;
  error?: string;
}

/** Upload an audio sample (raw body) + name/lang as query params. */
export async function createClone(
  name: string,
  lang: string,
  file: File
): Promise<CloneResult> {
  const url =
    `${API_BASE}/voices/clone?name=${encodeURIComponent(name)}` +
    `&lang=${encodeURIComponent(lang)}`;
  try {
    const res = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': file.type || 'application/octet-stream' },
      body: file,
    });
    if (!res.ok) {
      let msg = 'Upload failed.';
      try {
        msg = (await res.json()).error ?? msg;
      } catch {
        /* ignore */
      }
      return { ok: false, error: msg };
    }
    return { ok: true };
  } catch {
    return { ok: false, error: 'Network error.' };
  }
}

/** Clone a voice with IndicF5 (Indian HD — speaks 11 Indian languages).
 *  Auto-transcribes the reference clip server-side (Whisper). */
export async function createIF5Clone(name: string, file: File): Promise<CloneResult> {
  const url = `${API_BASE}/voices/clone-hd?name=${encodeURIComponent(name)}`;
  try {
    const res = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': file.type || 'application/octet-stream' },
      body: file,
    });
    if (!res.ok) {
      let msg = 'Upload failed.';
      try {
        msg = (await res.json()).error ?? msg;
      } catch {
        /* ignore */
      }
      return { ok: false, error: msg };
    }
    return { ok: true };
  } catch {
    return { ok: false, error: 'Network error.' };
  }
}

/** Delete a cloned voice. Accepts the full frontend id (e.g. server:clone:uuid). */
export async function deleteClone(voiceId: string): Promise<boolean> {
  const uuid = voiceId.split('clone:').pop() ?? '';
  try {
    const res = await fetch(`${API_BASE}/voices/clone/${uuid}`, {
      method: 'DELETE',
      credentials: 'include',
    });
    return res.ok;
  } catch {
    return false;
  }
}
