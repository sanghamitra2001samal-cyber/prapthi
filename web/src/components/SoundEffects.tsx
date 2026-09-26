import { useEffect, useRef, useState } from 'react';
import { Sparkles, Loader2, Download } from 'lucide-react';
import { useStore } from '../state/store';
import * as tools from '../lib/tools';

const EXAMPLES = [
  'Heavy rain with distant thunder',
  'Footsteps on gravel',
  'Crowd cheering in a stadium',
  'Birds chirping in a forest at dawn',
  'Sci-fi spaceship door opening',
  'Ocean waves on a calm beach',
];

export function SoundEffects() {
  const toast = useStore((s) => s.toast);
  const [prompt, setPrompt] = useState('');
  const [duration, setDuration] = useState(6);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<tools.SfxResult | null>(null);
  const poll = useRef<number | null>(null);

  const start = async () => {
    if (!prompt.trim()) {
      toast({ kind: 'error', message: 'Describe the sound first.' });
      return;
    }
    try {
      const { id } = await tools.createSfx(prompt, duration);
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
        const s = await tools.sfxStatus(jobId);
        setJob(s);
        if (s.status === 'done' || s.status === 'failed') {
          if (poll.current) window.clearInterval(poll.current);
          toast(s.status === 'done'
            ? { kind: 'success', message: 'Sound effect ready!' }
            : { kind: 'error', message: s.error || 'Failed.' });
        }
      } catch {
        /* keep polling */
      }
    };
    poll.current = window.setInterval(tick, 2500);
    void tick();
    return () => { if (poll.current) window.clearInterval(poll.current); };
  }, [jobId, toast]);

  const busy = job && (job.status === 'queued' || job.status === 'processing');
  const field = 'w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm focus:border-[var(--color-accent)] focus:outline-none';

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6 md:px-8 md:py-8">
      <div className="mb-2 flex items-center gap-2">
        <Sparkles size={20} className="text-[var(--color-accent)]" />
        <h2 className="text-xl font-bold tracking-tight">Sound Effects</h2>
      </div>
      <p className="mb-6 text-sm text-[var(--color-muted)]">
        Generate any sound effect or ambience from a text description.
      </p>

      <div className="space-y-5">
        <div>
          <label className="mb-1 block text-sm font-medium">Describe the sound</label>
          <input className={field} value={prompt} onChange={(e) => setPrompt(e.target.value)}
            placeholder="e.g. Heavy rain with distant thunder" />
        </div>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button key={ex} onClick={() => setPrompt(ex)}
              className="rounded-full border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-fg)]">
              {ex}
            </button>
          ))}
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">Length: {duration}s</label>
          <input type="range" min={2} max={20} step={1} value={duration}
            onChange={(e) => setDuration(Number(e.target.value))} className="w-full" />
        </div>

        <button onClick={start} disabled={!!busy}
          className="flex w-full items-center justify-center gap-2 rounded-full bg-[var(--color-accent)] px-6 py-3.5 text-sm font-semibold text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50">
          {busy ? <Loader2 size={17} className="animate-spin" /> : <Sparkles size={17} />}
          {busy ? 'Generating…' : 'Generate sound'}
        </button>

        {job?.status === 'done' && jobId && (
          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
            <audio controls src={tools.sfxFileUrl(jobId)} className="w-full" autoPlay />
            <a href={tools.sfxFileUrl(jobId)} download
              className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--color-accent-hover)]">
              <Download size={15} /> Download
            </a>
          </div>
        )}
        <p className="text-center text-xs text-[var(--color-muted)]">
          Powered by AudioLDM2 — fully self-hosted, no third-party API.
        </p>
      </div>
    </div>
  );
}
