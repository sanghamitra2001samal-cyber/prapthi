import { useEffect, useRef, useState } from 'react';
import { Code2, Loader2, Copy, Volume2 } from 'lucide-react';
import { useStore } from '../state/store';
import * as tools from '../lib/tools';
import { langLabel } from '../lib/langNames';

export function AudioNative() {
  const toast = useStore((s) => s.toast);
  const voices = useStore((s) => s.voices);
  const [title, setTitle] = useState('');
  const [text, setText] = useState('');
  const [voice, setVoice] = useState('pv_e19261001f');
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<tools.AudioNativeResult | null>(null);
  const poll = useRef<number | null>(null);

  useEffect(() => {
    if (voices.length && !voices.find((v) => v.id.replace('server:', '') === voice)) {
      // keep default
    }
  }, [voices, voice]);

  const start = async () => {
    if (text.trim().length < 20) return toast({ kind: 'error', message: 'Add more text.' });
    try {
      const { id } = await tools.createAudioNative(text, title || 'Listen to this article', voice);
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
        const s = await tools.audioNativeStatus(jobId);
        setJob(s);
        if (s.status === 'done' || s.status === 'failed') {
          if (poll.current) window.clearInterval(poll.current);
          toast(s.status === 'done'
            ? { kind: 'success', message: 'Embed player ready!' }
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
  const embedUrl = job?.embed_url;
  const embedCode = embedUrl
    ? `<iframe src="${embedUrl}" width="100%" height="64" frameborder="0" style="border:0;max-width:680px"></iframe>`
    : '';
  const field = 'w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm focus:border-[var(--color-accent)] focus:outline-none';

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6 md:px-8 md:py-8">
      <div className="mb-2 flex items-center gap-2">
        <Volume2 size={20} className="text-[var(--color-accent)]" />
        <h2 className="text-xl font-bold tracking-tight">Audio Native</h2>
      </div>
      <p className="mb-6 text-sm text-[var(--color-muted)]">
        Turn any article into an embeddable “Listen” player. Generate it, then paste one
        line of code into your website or blog.
      </p>

      <div className="space-y-5">
        <input className={field} value={title} onChange={(e) => setTitle(e.target.value)}
          placeholder="Player title (e.g. Listen to this article)" />
        <textarea className={`${field} min-h-[180px] resize-y`} value={text}
          onChange={(e) => setText(e.target.value)} placeholder="Paste your article text here…" />
        <div>
          <label className="mb-1 block text-sm font-medium">Narrator voice</label>
          <select className={field} value={voice} onChange={(e) => setVoice(e.target.value)}>
            {voices.map((v) => (
              <option key={v.id} value={v.id.replace('server:', '')}>{v.name} · {langLabel(v.lang)}</option>
            ))}
          </select>
        </div>

        <button onClick={start} disabled={!!busy}
          className="flex w-full items-center justify-center gap-2 rounded-full bg-[var(--color-accent)] px-6 py-3.5 text-sm font-semibold text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50">
          {busy ? <Loader2 size={17} className="animate-spin" /> : <Code2 size={17} />}
          {busy ? 'Generating…' : 'Generate embed player'}
        </button>

        {job?.status === 'done' && embedUrl && (
          <div className="space-y-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
            <div>
              <p className="mb-2 text-xs uppercase tracking-wide text-[var(--color-muted)]">Live preview</p>
              <iframe src={embedUrl} className="w-full" height={64} style={{ border: 0 }} title="player" />
            </div>
            <div>
              <div className="mb-1 flex items-center justify-between">
                <p className="text-xs uppercase tracking-wide text-[var(--color-muted)]">Embed code</p>
                <button onClick={() => { navigator.clipboard.writeText(embedCode); toast({ kind: 'info', message: 'Copied!' }); }}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs hover:border-[var(--color-accent)]">
                  <Copy size={13} /> Copy
                </button>
              </div>
              <pre className="overflow-x-auto rounded-lg bg-[var(--color-surface-2)] p-3 text-xs">{embedCode}</pre>
              <p className="mt-2 text-xs text-[var(--color-muted)]">Paste this into any website or blog — the player works anywhere.</p>
            </div>
          </div>
        )}
        <p className="text-center text-xs text-[var(--color-muted)]">Self-hosted player — your audio, your domain, no third-party API.</p>
      </div>
    </div>
  );
}
