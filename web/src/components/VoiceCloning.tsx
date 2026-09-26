import { useRef, useState } from 'react';
import { Mic, Upload, Loader2, Trash2, Play, Square, UserPlus } from 'lucide-react';
import { useStore } from '../state/store';

const CHATTERBOX_LANGS: Array<[string, string]> = [
  ['en', 'English'], ['hi', 'Hindi'], ['ar', 'Arabic'], ['zh', 'Chinese'],
  ['fr', 'French'], ['de', 'German'], ['es', 'Spanish'], ['it', 'Italian'],
  ['ja', 'Japanese'], ['ko', 'Korean'], ['pt', 'Portuguese'], ['ru', 'Russian'],
];

export function VoiceCloning() {
  const toast = useStore((s) => s.toast);
  const voices = useStore((s) => s.voices);
  const createClone = useStore((s) => s.createClone);
  const deleteClone = useStore((s) => s.deleteClone);
  const preview = useStore((s) => s.preview);

  const [name, setName] = useState('');
  const [lang, setLang] = useState('en');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const recRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);

  const cloned = voices.filter((v) => v.clone);

  const startRec = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : '';
      const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunksRef.current = [];
      rec.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data);
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        setFile(new File([blob], 'recording.webm', { type: 'audio/webm' }));
      };
      rec.start();
      recRef.current = rec;
      setRecording(true);
    } catch {
      toast({ kind: 'error', message: 'Mic access denied or unavailable.' });
    }
  };
  const stopRec = () => {
    recRef.current?.stop();
    setRecording(false);
  };

  const create = async () => {
    if (!name.trim()) return toast({ kind: 'error', message: 'Name your voice.' });
    if (!file) return toast({ kind: 'error', message: 'Record or upload a 5–30s clip.' });
    setBusy(true);
    const r = await createClone(name.trim(), lang, file);
    setBusy(false);
    if (r.ok) {
      toast({ kind: 'success', message: 'Voice cloned! It’s in your list below.' });
      setName(''); setFile(null);
      if (fileRef.current) fileRef.current.value = '';
    } else {
      toast({ kind: 'error', message: r.error ?? 'Clone failed.' });
    }
  };

  const field = 'w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm focus:border-[var(--color-accent)] focus:outline-none';

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6 md:px-8 md:py-8">
      <div className="mb-2 flex items-center gap-2">
        <UserPlus size={20} className="text-[var(--color-accent)]" />
        <h2 className="text-xl font-bold tracking-tight">Voice Cloning</h2>
      </div>
      <p className="mb-6 text-sm text-[var(--color-muted)]">
        Clone any voice from a short clip, then have it speak in the language you
        choose. Works across English, Hindi, Arabic and 9 more. Only clone voices
        you have permission to use.
      </p>

      <div className="space-y-5 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <input className={field} value={name} onChange={(e) => setName(e.target.value)}
          placeholder="Voice name (e.g. My Brand Voice)" />

        <div>
          <label className="mb-1 block text-sm font-medium">Language</label>
          <select className={field} value={lang} onChange={(e) => setLang(e.target.value)}>
            {CHATTERBOX_LANGS.map(([c, n]) => <option key={c} value={c}>{n}</option>)}
          </select>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {!recording ? (
            <button onClick={startRec} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm hover:border-[var(--color-accent)]">
              <Mic size={15} /> Record
            </button>
          ) : (
            <button onClick={stopRec} className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-error)] px-3 py-2 text-sm font-medium text-white">
              <Square size={14} /> Stop recording
            </button>
          )}
          <button onClick={() => fileRef.current?.click()} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm hover:border-[var(--color-accent)]">
            <Upload size={15} /> Upload clip
          </button>
          <input ref={fileRef} type="file" accept="audio/*" className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          {file && <span className="text-xs text-[var(--color-muted)]">✓ {file.name}</span>}
        </div>

        <button onClick={create} disabled={busy}
          className="flex w-full items-center justify-center gap-2 rounded-full bg-[var(--color-accent)] px-6 py-3 text-sm font-semibold text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50">
          {busy ? <Loader2 size={16} className="animate-spin" /> : <UserPlus size={16} />}
          {busy ? 'Cloning…' : 'Create cloned voice'}
        </button>
      </div>

      <h3 className="mb-2 mt-7 text-sm font-semibold">Your cloned voices ({cloned.length})</h3>
      {cloned.length === 0 ? (
        <p className="text-sm text-[var(--color-muted)]">No cloned voices yet.</p>
      ) : (
        <div className="space-y-2">
          {cloned.map((v) => (
            <div key={v.id} className="flex items-center justify-between rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
              <span className="text-sm font-medium">{v.name}</span>
              <div className="flex items-center gap-1">
                <button onClick={() => preview(v.id)} className="rounded-lg p-2 text-[var(--color-muted)] hover:text-[var(--color-fg)]" title="Preview">
                  <Play size={15} />
                </button>
                <button onClick={() => deleteClone(v.id)} className="rounded-lg p-2 text-[var(--color-muted)] hover:text-[var(--color-error)]" title="Delete">
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
