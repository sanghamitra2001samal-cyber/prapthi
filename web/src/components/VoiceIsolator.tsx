import { useEffect, useRef, useState } from 'react';
import { AudioLines, Upload, Loader2, Download } from 'lucide-react';
import { useStore } from '../state/store';
import * as tools from '../lib/tools';

const STEM_LABELS: Record<string, string> = {
  vocals: 'Vocals only',
  instrumental: 'Instrumental (karaoke)',
  drums: 'Drums',
  bass: 'Bass',
  other: 'Other',
};

export function VoiceIsolator() {
  const toast = useStore((s) => s.toast);
  const [file, setFile] = useState<File | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<tools.IsolateResult | null>(null);
  const poll = useRef<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const start = async () => {
    if (!file) {
      toast({ kind: 'error', message: 'Choose an audio file first.' });
      return;
    }
    try {
      const { id } = await tools.createIsolate(file);
      setJobId(id);
      setJob({ status: 'queued', step: 'Queued', progress: 0 });
    } catch (e) {
      toast({ kind: 'error', message: (e as Error).message });
    }
  };

  useEffect(() => {
    if (!jobId) return;
    const tick = async () => {
      try {
        const s = await tools.isolateStatus(jobId);
        setJob(s);
        if (s.status === 'done' || s.status === 'failed') {
          if (poll.current) window.clearInterval(poll.current);
          if (s.status === 'done') toast({ kind: 'success', message: 'Separation complete!' });
          else toast({ kind: 'error', message: s.error || 'Separation failed.' });
        }
      } catch {
        /* keep polling */
      }
    };
    poll.current = window.setInterval(tick, 3000);
    void tick();
    return () => {
      if (poll.current) window.clearInterval(poll.current);
    };
  }, [jobId, toast]);

  const busy = job && (job.status === 'queued' || job.status === 'processing');

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6 md:px-8 md:py-8">
      <div className="mb-2 flex items-center gap-2">
        <AudioLines size={20} className="text-[var(--color-accent)]" />
        <h2 className="text-xl font-bold tracking-tight">Voice Isolator</h2>
      </div>
      <p className="mb-6 text-sm text-[var(--color-muted)]">
        Split any song or recording into separate tracks — vocals, instrumental (karaoke),
        drums, bass and more.
      </p>

      <div className="space-y-5">
        <button
          onClick={() => fileRef.current?.click()}
          className="flex w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-[var(--color-border)] px-4 py-8 text-sm text-[var(--color-muted)] hover:border-[var(--color-accent)]"
        >
          <Upload size={18} />
          {file ? file.name : 'Choose audio (max 100MB)'}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="audio/*,video/*"
          className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />

        <button
          onClick={start}
          disabled={!!busy}
          className="flex w-full items-center justify-center gap-2 rounded-full bg-[var(--color-accent)] px-6 py-3.5 text-sm font-semibold text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
        >
          {busy ? <Loader2 size={17} className="animate-spin" /> : <AudioLines size={17} />}
          {busy ? (job?.step || 'Separating…') : 'Separate tracks'}
        </button>

        {busy && (
          <div className="h-2 overflow-hidden rounded-full bg-[var(--color-surface-2)]">
            <div className="h-full rounded-full bg-[var(--color-accent)] transition-[width]"
                 style={{ width: `${job?.progress ?? 0}%` }} />
          </div>
        )}

        {job?.status === 'done' && jobId && job.kinds && (
          <div className="space-y-3 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
            {job.kinds.map((kind) => (
              <div key={kind} className="flex items-center gap-3">
                <span className="w-44 text-sm font-medium">{STEM_LABELS[kind] || kind}</span>
                <audio controls src={tools.isolateFileUrl(jobId, kind)} className="h-9 flex-1" />
                <a href={tools.isolateFileUrl(jobId, kind)} download
                   className="rounded-lg p-2 text-[var(--color-muted)] hover:text-[var(--color-fg)]" title="Download">
                  <Download size={16} />
                </a>
              </div>
            ))}
          </div>
        )}
        <p className="text-center text-xs text-[var(--color-muted)]">
          Studio-grade source separation — fully self-hosted, no third-party API.
        </p>
      </div>
    </div>
  );
}
