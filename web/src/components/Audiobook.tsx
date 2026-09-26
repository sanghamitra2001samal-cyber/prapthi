import { useEffect, useRef, useState } from 'react';
import { BookOpen, Loader2, Download, Upload } from 'lucide-react';
import { useStore } from '../state/store';
import * as tools from '../lib/tools';
import { langLabel } from '../lib/langNames';

export function Audiobook() {
  const toast = useStore((s) => s.toast);
  const [text, setText] = useState('');
  const [voices, setVoices] = useState<tools.ServerVoice[]>([]);
  const [voice, setVoice] = useState('pv_e19261001f');
  const [gap, setGap] = useState(400);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<tools.BookResult | null>(null);
  const poll = useRef<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    tools.listVoices().then(setVoices).catch(() => setVoices([]));
  }, []);

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) setText(await f.text());
  };

  const start = async () => {
    if (text.trim().length < 20) {
      toast({ kind: 'error', message: 'Add more text.' });
      return;
    }
    try {
      const { id } = await tools.createAudiobook(text, voice, gap);
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
        const s = await tools.audiobookStatus(jobId);
        setJob(s);
        if (s.status === 'done' || s.status === 'failed') {
          if (poll.current) window.clearInterval(poll.current);
          toast(s.status === 'done'
            ? { kind: 'success', message: 'Audiobook ready!' }
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
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  const field = 'w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm focus:border-[var(--color-accent)] focus:outline-none';

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6 md:px-8 md:py-8">
      <div className="mb-2 flex items-center gap-2">
        <BookOpen size={20} className="text-[var(--color-accent)]" />
        <h2 className="text-xl font-bold tracking-tight">Audiobook Studio</h2>
      </div>
      <p className="mb-6 text-sm text-[var(--color-muted)]">
        Turn long text — a chapter, article or whole book — into a narrated audiobook in any voice.
      </p>

      <div className="space-y-5">
        <div>
          <div className="mb-1 flex items-center justify-between">
            <label className="text-sm font-medium">Your text</label>
            <button onClick={() => fileRef.current?.click()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-2.5 py-1 text-xs text-[var(--color-muted)] hover:border-[var(--color-accent)]">
              <Upload size={13} /> Load .txt
            </button>
            <input ref={fileRef} type="file" accept=".txt,text/plain" className="hidden" onChange={onFile} />
          </div>
          <textarea
            className={`${field} min-h-[220px] resize-y`}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste your chapter or book text here…"
          />
          <p className="mt-1 text-xs text-[var(--color-muted)]">{words} words</p>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm font-medium">Narrator voice</label>
            <select className={field} value={voice} onChange={(e) => setVoice(e.target.value)}>
              {voices.map((v) => <option key={v.id} value={v.id}>{v.name} · {langLabel(v.lang)}</option>)}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Pause between paragraphs: {gap}ms</label>
            <input type="range" min={0} max={1200} step={50} value={gap}
              onChange={(e) => setGap(Number(e.target.value))} className="w-full" />
          </div>
        </div>

        <button onClick={start} disabled={!!busy}
          className="flex w-full items-center justify-center gap-2 rounded-full bg-[var(--color-accent)] px-6 py-3.5 text-sm font-semibold text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50">
          {busy ? <Loader2 size={17} className="animate-spin" /> : <BookOpen size={17} />}
          {busy ? (job?.step || 'Narrating…') : 'Create audiobook'}
        </button>

        {busy && (
          <div className="h-2 overflow-hidden rounded-full bg-[var(--color-surface-2)]">
            <div className="h-full rounded-full bg-[var(--color-accent)] transition-[width]"
              style={{ width: `${job?.progress ?? 0}%` }} />
          </div>
        )}

        {job?.status === 'done' && jobId && (
          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
            <p className="mb-2 text-xs uppercase tracking-wide text-[var(--color-muted)]">
              {job.chunks} sections narrated
            </p>
            <audio controls src={tools.audiobookFileUrl(jobId)} className="w-full" />
            <a href={tools.audiobookFileUrl(jobId)} download
              className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--color-accent-hover)]">
              <Download size={15} /> Download audiobook (MP3)
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
