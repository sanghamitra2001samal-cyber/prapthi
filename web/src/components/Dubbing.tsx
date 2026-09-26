import { useEffect, useRef, useState } from 'react';
import { Languages, Upload, Loader2, Download } from 'lucide-react';
import { useStore } from '../state/store';
import * as tools from '../lib/tools';

export function Dubbing() {
  const toast = useStore((s) => s.toast);
  const [file, setFile] = useState<File | null>(null);
  const [lang, setLang] = useState('hi');
  const [keepBg, setKeepBg] = useState(0.15);
  const [preserveVoice, setPreserveVoice] = useState(false);
  const [voices, setVoices] = useState<tools.ServerVoice[]>([]);
  const [voice, setVoice] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<tools.DubResult | null>(null);
  const poll = useRef<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const start = async () => {
    if (!file) {
      toast({ kind: 'error', message: 'Choose a video or audio file first.' });
      return;
    }
    try {
      const { id } = await tools.createDub(file, lang, keepBg, voice, preserveVoice);
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
        const s = await tools.dubStatus(jobId);
        setJob(s);
        if (s.status === 'done' || s.status === 'failed') {
          if (poll.current) window.clearInterval(poll.current);
          if (s.status === 'done') toast({ kind: 'success', message: 'Dubbing complete!' });
          else toast({ kind: 'error', message: s.error || 'Dubbing failed.' });
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

  // load voices once; reset selection when language changes
  useEffect(() => {
    tools.listVoices().then(setVoices).catch(() => setVoices([]));
  }, []);
  useEffect(() => { setVoice(''); }, [lang]);
  const langVoices = voices.filter((v) => v.lang.slice(0, 2) === lang);

  const busy = job && (job.status === 'queued' || job.status === 'processing');
  const field =
    'w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm focus:border-[var(--color-accent)] focus:outline-none';

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6 md:px-8 md:py-8">
      <div className="mb-2 flex items-center gap-2">
        <Languages size={20} className="text-[var(--color-accent)]" />
        <h2 className="text-xl font-bold tracking-tight">AI Dubbing</h2>
        <span className="rounded-full bg-[var(--color-accent)]/15 px-2 py-0.5 text-[11px] font-semibold text-[var(--color-accent)]">
          Indian languages
        </span>
      </div>
      <p className="mb-6 text-sm text-[var(--color-muted)]">
        Upload a video or audio and auto-dub it into an Indian language — transcribed,
        translated, re-voiced and timed to the original.
      </p>

      <div className="space-y-5">
        <button
          onClick={() => fileRef.current?.click()}
          className="flex w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-[var(--color-border)] px-4 py-8 text-sm text-[var(--color-muted)] hover:border-[var(--color-accent)]"
        >
          <Upload size={18} />
          {file ? file.name : 'Choose video / audio (max 200MB)'}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="video/*,audio/*"
          className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm font-medium">Dub into</label>
            <select className={field} value={lang} onChange={(e) => setLang(e.target.value)}>
              {tools.DUB_LANGS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Dubbing voice</label>
            <select className={field} value={voice} onChange={(e) => setVoice(e.target.value)}>
              <option value="">Auto (best for language)</option>
              {langVoices.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </div>
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">
            Keep background music: {Math.round(keepBg * 100)}%
          </label>
          <input
            type="range" min={0} max={0.6} step={0.05} value={keepBg}
            onChange={(e) => setKeepBg(Number(e.target.value))}
            className="w-full"
          />
          <p className="text-xs text-[var(--color-muted)]">
            Keeps the original music/background (speech removed) under the new voice.
          </p>
        </div>

        <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
          <input
            type="checkbox"
            checked={preserveVoice}
            onChange={(e) => setPreserveVoice(e.target.checked)}
            className="mt-0.5 h-4 w-4 accent-[var(--color-accent)]"
          />
          <span className="text-sm">
            <span className="font-medium">Keep the original speakers&rsquo; voices</span>
            <span className="block text-xs text-[var(--color-muted)]">
              Each speaker is detected separately and dubbed in their own voice, now
              speaking the new language. Takes noticeably longer, and can slightly
              soften pronunciation — leave it off if crispness matters most.
            </span>
          </span>
        </label>

        <button
          onClick={start}
          disabled={!!busy}
          className="flex w-full items-center justify-center gap-2 rounded-full bg-[var(--color-accent)] px-6 py-3.5 text-sm font-semibold text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
        >
          {busy ? <Loader2 size={17} className="animate-spin" /> : <Languages size={17} />}
          {busy ? (job?.step || 'Working…') : 'Dub it'}
        </button>

        {busy && (
          <div className="h-2 overflow-hidden rounded-full bg-[var(--color-surface-2)]">
            <div className="h-full rounded-full bg-[var(--color-accent)] transition-[width]"
                 style={{ width: `${job?.progress ?? 0}%` }} />
          </div>
        )}

        {job?.status === 'done' && jobId && (
          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
            {job.is_video ? (
              <video controls src={tools.dubFileUrl(jobId)} className="w-full rounded-lg" />
            ) : (
              <audio controls src={tools.dubFileUrl(jobId)} className="w-full" />
            )}
            <a
              href={tools.dubFileUrl(jobId)} download
              className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--color-accent-hover)]"
            >
              <Download size={15} /> Download dubbed {job.is_video ? 'video' : 'audio'}
            </a>
            {job.transcript && job.transcript.length > 0 && (
              <div className="mt-4 max-h-60 overflow-y-auto rounded-lg border border-[var(--color-border)] p-3 text-xs">
                {(job.speakers ?? 1) > 1 && (
                  <p className="mb-2 font-medium text-[var(--color-accent)]">
                    {job.speakers} speakers detected — each dubbed with its own voice
                  </p>
                )}
                {job.transcript.map((seg, i) => (
                  <div key={i} className="mb-2">
                    <p className="mb-0.5 flex gap-1.5 text-[10px] uppercase tracking-wide text-[var(--color-muted)]">
                      {(job.speakers ?? 1) > 1 && <span>Speaker {(seg.spk ?? 0) + 1}</span>}
                      {seg.emo && seg.emo !== 'neutral' && (
                        <span className="text-[var(--color-accent)]">{seg.emo}</span>
                      )}
                    </p>
                    <p className="text-[var(--color-muted)]">{seg.t}</p>
                    <p className="font-medium">{seg.tr}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        <p className="text-center text-xs text-[var(--color-muted)]">
          Fully self-hosted — transcription + translation + your Indian voices. No third-party API.
        </p>
      </div>
    </div>
  );
}
