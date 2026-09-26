import { useEffect, useRef, useState } from 'react';
import { Megaphone, Loader2, Download, Copy } from 'lucide-react';
import { useStore } from '../state/store';
import * as tools from '../lib/tools';

const LANGS: Array<[string, string]> = [
  ['en', 'English'], ['hi', 'Hindi'], ['ta', 'Tamil'], ['te', 'Telugu'],
  ['kn', 'Kannada'], ['ml', 'Malayalam'], ['bn', 'Bengali'], ['mr', 'Marathi'],
  ['gu', 'Gujarati'], ['pa', 'Punjabi'],
];
const TONES = ['energetic', 'warm & friendly', 'premium / luxury', 'urgent (sale)', 'fun & quirky', 'trustworthy'];

export function AdsEngine() {
  const toast = useStore((s) => s.toast);
  const voices = useStore((s) => s.voices);
  const [brief, setBrief] = useState('');
  const [lang, setLang] = useState('hi');
  const [tone, setTone] = useState('energetic');
  const [seconds, setSeconds] = useState(30);
  const [voice, setVoice] = useState('pv_e19261001f');
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<tools.AdsResult | null>(null);
  const poll = useRef<number | null>(null);

  const langVoices = voices.filter((v) => v.lang.slice(0, 2) === lang);
  useEffect(() => {
    if (langVoices.length) setVoice(langVoices[0].id.replace('server:', ''));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang]);

  const start = async () => {
    if (brief.trim().length < 5) return toast({ kind: 'error', message: 'Describe your product.' });
    try {
      const { id } = await tools.createAd(brief, lang, voice, tone, seconds);
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
        const s = await tools.adStatus(jobId);
        setJob(s);
        if (s.status === 'done' || s.status === 'failed') {
          if (poll.current) window.clearInterval(poll.current);
          toast(s.status === 'done'
            ? { kind: 'success', message: 'Ad ready!' }
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
        <Megaphone size={20} className="text-[var(--color-accent)]" />
        <h2 className="text-xl font-bold tracking-tight">Ads Engine</h2>
      </div>
      <p className="mb-6 text-sm text-[var(--color-muted)]">
        Describe your product — AI writes a punchy ad script and voices it, in any Indian language.
      </p>

      <div className="space-y-5">
        <textarea className={`${field} min-h-[100px] resize-y`} value={brief}
          onChange={(e) => setBrief(e.target.value)}
          placeholder="e.g. A new masala chai brand, 100% natural, for busy young professionals." />

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div>
            <label className="mb-1 block text-sm font-medium">Language</label>
            <select className={field} value={lang} onChange={(e) => setLang(e.target.value)}>
              {LANGS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Tone</label>
            <select className={field} value={tone} onChange={(e) => setTone(e.target.value)}>
              {TONES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Length</label>
            <select className={field} value={seconds} onChange={(e) => setSeconds(Number(e.target.value))}>
              {[15, 30, 45, 60].map((s) => <option key={s} value={s}>{s}s</option>)}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Voice</label>
            <select className={field} value={voice} onChange={(e) => setVoice(e.target.value)}>
              {langVoices.map((v) => <option key={v.id} value={v.id.replace('server:', '')}>{v.name}</option>)}
            </select>
          </div>
        </div>

        <button onClick={start} disabled={!!busy}
          className="flex w-full items-center justify-center gap-2 rounded-full bg-[var(--color-accent)] px-6 py-3.5 text-sm font-semibold text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50">
          {busy ? <Loader2 size={17} className="animate-spin" /> : <Megaphone size={17} />}
          {busy ? (job?.step || 'Creating…') : 'Create ad'}
        </button>

        {job?.status === 'done' && jobId && (
          <div className="space-y-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
            <div>
              <div className="mb-1 flex items-center justify-between">
                <p className="text-xs uppercase tracking-wide text-[var(--color-muted)]">Script</p>
                <button onClick={() => { navigator.clipboard.writeText(job.script || ''); toast({ kind: 'info', message: 'Copied!' }); }}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs hover:border-[var(--color-accent)]">
                  <Copy size={13} /> Copy
                </button>
              </div>
              <p className="text-sm leading-relaxed">{job.script}</p>
            </div>
            <audio controls src={tools.adFileUrl(jobId)} className="w-full" />
            <a href={tools.adFileUrl(jobId)} download
              className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--color-accent-hover)]">
              <Download size={15} /> Download ad (MP3)
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
