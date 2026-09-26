import { useRef, useState } from 'react';
import { FileText, Upload, Loader2, Copy } from 'lucide-react';
import { useStore } from '../state/store';
import * as tools from '../lib/tools';

export function SpeechToText() {
  const toast = useStore((s) => s.toast);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<tools.Transcript | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const run = async () => {
    if (!file) {
      toast({ kind: 'error', message: 'Choose an audio or video file first.' });
      return;
    }
    setBusy(true);
    setResult(null);
    try {
      const r = await tools.transcribe(file);
      setResult(r);
      toast({ kind: 'success', message: `Transcribed (${r.language}).` });
    } catch (e) {
      toast({ kind: 'error', message: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const copy = () => {
    if (result) {
      navigator.clipboard.writeText(result.text);
      toast({ kind: 'info', message: 'Transcript copied.' });
    }
  };

  const fmt = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, '0')}`;
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6 md:px-8 md:py-8">
      <div className="mb-2 flex items-center gap-2">
        <FileText size={20} className="text-[var(--color-accent)]" />
        <h2 className="text-xl font-bold tracking-tight">Speech to Text</h2>
      </div>
      <p className="mb-6 text-sm text-[var(--color-muted)]">
        Transcribe any audio or video into text with timestamps — 90+ languages, auto-detected.
      </p>

      <div className="space-y-5">
        <button
          onClick={() => fileRef.current?.click()}
          className="flex w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-[var(--color-border)] px-4 py-8 text-sm text-[var(--color-muted)] hover:border-[var(--color-accent)]"
        >
          <Upload size={18} />
          {file ? file.name : 'Choose audio / video (max 100MB)'}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="audio/*,video/*"
          className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />

        <button
          onClick={run}
          disabled={busy}
          className="flex w-full items-center justify-center gap-2 rounded-full bg-[var(--color-accent)] px-6 py-3.5 text-sm font-semibold text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
        >
          {busy ? <Loader2 size={17} className="animate-spin" /> : <FileText size={17} />}
          {busy ? 'Transcribing…' : 'Transcribe'}
        </button>

        {result && (
          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
                Detected language: {result.language}
              </span>
              <button onClick={copy} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs hover:border-[var(--color-accent)]">
                <Copy size={13} /> Copy
              </button>
            </div>
            <p className="mb-4 text-sm leading-relaxed">{result.text}</p>
            <div className="max-h-72 space-y-1.5 overflow-y-auto border-t border-[var(--color-border)] pt-3">
              {result.segments.map((s, i) => (
                <div key={i} className="flex gap-3 text-xs">
                  <span className="shrink-0 font-mono text-[var(--color-muted)]">
                    {fmt(s.start)}
                  </span>
                  <span>{s.text}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        <p className="text-center text-xs text-[var(--color-muted)]">
          Fully self-hosted transcription — no third-party API.
        </p>
      </div>
    </div>
  );
}
