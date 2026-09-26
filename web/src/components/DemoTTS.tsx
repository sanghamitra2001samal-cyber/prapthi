import { useEffect, useRef, useState } from 'react';
import { Play as PlayIcon, Square, Loader2, Sparkles, Volume2 } from 'lucide-react';

/* ------------------------------------------------------------------ */
/*  DemoTTS — a live, on-page "try it" studio.                         */
/*                                                                    */
/*  It synthesises with the real self-hosted neural engine through a   */
/*  PUBLIC, rate-limited demo endpoint (no login needed), so every     */
/*  visitor hears our actual voices. The browser's built-in speech     */
/*  engine is used ONLY if that network call genuinely fails, so the   */
/*  demo always speaks and never surfaces an error to the visitor.     */
/* ------------------------------------------------------------------ */

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';

// Keep in step with VOXFORGE_DEMO_CHAR_CAP on the server — if this is larger,
// the server truncates and the visitor hears less than they typed.
const DEMO_MAX = 1000;

/* This browser's own id, so the free demo allowance is per DEVICE. Without it
   the server can only key on IP address, which would make everyone sharing a
   router — a household, an office, a mobile carrier — share one allowance. */
function deviceId(): string {
  const KEY = 'prapthi_demo_device';
  try {
    let id = localStorage.getItem(KEY);
    if (!id) {
      id = (crypto?.randomUUID?.() ??
        `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`);
      localStorage.setItem(KEY, id);
    }
    return id;
  } catch {
    return '';   // private mode / storage blocked: server falls back to IP
  }
}

const demoHeaders = (): Record<string, string> => {
  const id = deviceId();
  return id ? { 'X-Demo-Device': id } : {};
};

type Voice = { id: string; name: string; lang: string; gender?: string };

// The catalogue comes from the server (`/demo/catalog`) so this page always
// offers what actually exists. Hard-coding voices here once meant that when the
// demo set was rebuilt every id 404'd, the call fell through to the browser's
// built-in speech engine, and every sample played in the same voice.
const LANG_LABEL: Record<string, string> = {
  en: 'English', hi: 'Hindi', ta: 'Tamil', te: 'Telugu', gu: 'Gujarati',
  bn: 'Bengali', mr: 'Marathi', kn: 'Kannada', ml: 'Malayalam', pa: 'Punjabi',
  or: 'Odia', as: 'Assamese', ne: 'Nepali', sa: 'Sanskrit', doi: 'Dogri',
  brx: 'Bodo', mni: 'Manipuri', bho: 'Bhojpuri', hne: 'Chhattisgarhi',
  zh: 'Chinese', es: 'Spanish', fr: 'French', de: 'German', ja: 'Japanese',
  ko: 'Korean', ru: 'Russian', ar: 'Arabic', he: 'Hebrew', it: 'Italian',
  pt: 'Portuguese', nl: 'Dutch', pl: 'Polish', tr: 'Turkish', el: 'Greek',
  sv: 'Swedish', da: 'Danish', nb: 'Norwegian', fi: 'Finnish', ms: 'Malay',
  sw: 'Swahili',
};

// "bho-IN" -> "bho". Slicing to 2 chars would turn Bhojpuri into "bh",
// Bodo into "br" and Manipuri into "mn" — none of which are those languages.
const baseLang = (l: string) => String(l ?? '').split('-')[0].toLowerCase();
const langName = (l: string) => LANG_LABEL[baseLang(l)] ?? baseLang(l).toUpperCase();

const SAMPLES: Record<string, string> = {
  en: 'Welcome to Prapthi AI — where every word finds its perfect voice.',
  hi: 'नमस्ते! प्रप्ति ए आई में आपका स्वागत है।',
  te: 'నమస్కారం! ప్రాప్తి ఏఐ కి స్వాగతం.',
  ta: 'வணக்கம்! பிராப்தி ஏஐ க்கு வரவேற்கிறோம்.',
  gu: 'નમસ્તે! પ્રાપ્તિ એઆઈ માં આપનું સ્વાગત છે.',
  bn: 'নমস্কার! প্রাপ্তি এআই-এ আপনাকে স্বাগতম।',
  zh: '欢迎来到 Prapthi AI，让每个字都拥有完美的声音。',
  es: 'Bienvenido a Prapthi AI, donde cada palabra encuentra su voz perfecta.',
};

const sampleFor = (lang: string) => SAMPLES[lang.slice(0, 2)] ?? SAMPLES.en;

export default function DemoTTS() {
  const [catalog, setCatalog] = useState<Voice[]>([]);
  const [lang, setLang] = useState('en');
  const [voiceId, setVoiceId] = useState('');
  // Characters left before the visitor has to sign up. Server-enforced; this
  // is only the display of it.
  const [remaining, setRemaining] = useState<number | null>(null);
  const [limit, setLimit] = useState(DEMO_MAX);
  const [text, setText] = useState(SAMPLES.en);
  const [status, setStatus] = useState<'idle' | 'loading' | 'playing'>('idle');
  // 'server' only after a real clip has played — never claim the neural engine
  // on the strength of a probe when the audio actually came from the browser.
  const [engine, setEngine] = useState<'server' | 'browser' | 'unknown'>('unknown');
  // Long lines take roughly their own duration to synthesize, so show the
  // visitor a running count rather than an unexplained wait.
  const [elapsed, setElapsed] = useState(0);
  const bVoices = useRef<SpeechSynthesisVoice[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);
  const editedRef = useRef(false);

  // Load the full catalogue the server is actually offering, plus our budget.
  useEffect(() => {
    let alive = true;
    fetch(`${API_BASE}/demo/catalog`, {
      headers: demoHeaders(),
      signal: AbortSignal.timeout(10000),
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!alive || !d || !Array.isArray(d.voices) || !d.voices.length) return;
        // Parentheses carry internal detail ("(HD, Natural)", "(Neural,
        // Medium)") that means nothing to a visitor.
        const rows: Voice[] = d.voices.map((v: Voice) => ({
          ...v,
          name: String(v.name ?? '')
            .replace(/\s*\([^)]*\)\s*/g, ' ')
            .split('·')[0]
            .trim() || 'Voice',
        }));
        setCatalog(rows);
        if (typeof d.remaining === 'number') setRemaining(d.remaining);
        if (typeof d.limit === 'number') setLimit(d.limit);
        const en = rows.find((v) => v.lang.startsWith('en')) ?? rows[0];
        setLang(baseLang(en.lang));
        setVoiceId(en.id);
      })
      .catch(() => {});
    const load = () => { bVoices.current = window.speechSynthesis?.getVoices?.() ?? []; };
    load();
    window.speechSynthesis?.addEventListener?.('voiceschanged', load);
    return () => {
      alive = false;
      window.speechSynthesis?.removeEventListener?.('voiceschanged', load);
      stopAll();
    };
  }, []);

  // Languages present in the catalogue, and the voices within the chosen one.
  const languages = Array.from(new Set(catalog.map((v) => baseLang(v.lang))))
    .sort((a, b) => langName(a).localeCompare(langName(b)));
  const langVoices = catalog
    .filter((v) => baseLang(v.lang) === lang)
    .sort((a, b) => a.name.localeCompare(b.name));
  const voice: Voice | undefined =
    langVoices.find((v) => v.id === voiceId) ?? langVoices[0];

  const outOfBudget = remaining !== null && remaining <= 0;
  const tooLong = remaining !== null && text.trim().length > remaining;

  // Tick the elapsed counter while a clip is being generated.
  useEffect(() => {
    if (status !== 'loading') { setElapsed(0); return; }
    const t0 = Date.now();
    const id = window.setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 500);
    return () => window.clearInterval(id);
  }, [status]);

  const releaseAudio = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = '';
      audioRef.current = null;
    }
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    }
  };

  const stopAll = () => {
    releaseAudio();
    try { window.speechSynthesis?.cancel(); } catch { /* noop */ }
    setStatus('idle');
  };

  // Synthesize one clip through the public neural demo endpoint and play it.
  const speakServer = (t: string, v: Voice) =>
    new Promise<void>((resolve, reject) => {
      (async () => {
        // Synthesis runs roughly in real time, so a 1000-character line takes
        // ~50s. A fixed 30s timeout would abort every long request and fall
        // back to the browser voice — allow generous headroom instead.
        const budgetMs = Math.min(240000, 30000 + t.length * 120);
        const res = await fetch(`${API_BASE}/demo/synthesize`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...demoHeaders() },
          body: JSON.stringify({ text: t, voiceId: v.id }),
          signal: AbortSignal.timeout(budgetMs),
        });
        // 402 = the free character budget is spent. That is a real answer, not
        // a failure to paper over with the browser's voice.
        if (res.status === 402) {
          setRemaining(0);
          throw new Error('demo budget exhausted');
        }
        if (!res.ok) throw new Error(`demo synth ${res.status}`);
        setRemaining((r) => (r === null ? r : Math.max(0, r - t.length)));
        const blob = await res.blob();
        releaseAudio();
        const url = URL.createObjectURL(blob);
        urlRef.current = url;
        const audio = new Audio(url);
        audioRef.current = audio;
        audio.onplay = () => {
          setStatus('playing');
          setEngine('server');   // real audio is playing — now the claim is true
        };
        audio.onended = () => { releaseAudio(); resolve(); };
        audio.onerror = () => { releaseAudio(); reject(new Error('playback failed')); };
        void audio.play().catch(reject);
      })().catch(reject);
    });

  const speakBrowser = (t: string, v: Voice) =>
    new Promise<void>((resolve) => {
      const synth = window.speechSynthesis;
      if (!synth) { resolve(); return; }
      synth.cancel();
      const u = new SpeechSynthesisUtterance(t);
      const pref =
        bVoices.current.find((x) => x.lang?.toLowerCase() === v.lang.toLowerCase()) ||
        bVoices.current.find((x) => x.lang?.toLowerCase().startsWith(v.lang.slice(0, 2)));
      if (pref) u.voice = pref;
      u.lang = v.lang;
      u.rate = 1; u.pitch = 1;
      u.onend = () => resolve();
      u.onerror = () => resolve();
      setStatus('playing');
      synth.speak(u);
    });

  const play = async () => {
    if (status !== 'idle') { stopAll(); return; }
    if (!voice || outOfBudget) return;
    const t = (text || sampleFor(voice.lang)).trim();
    setStatus('loading');
    try {
      await speakServer(t, voice);
      setStatus('idle');
      return;
    } catch (e) {
      // Out of budget is a real limit — never disguise it as a working demo by
      // quietly playing the browser's own voice instead.
      if ((e as Error)?.message === 'demo budget exhausted') {
        setStatus('idle');
        return;
      }
      setEngine('browser');
    }
    await speakBrowser(t, voice);
    setStatus('idle');
  };

  // Switching language moves to that language's first voice and, unless the
  // visitor has typed their own text, loads a sample they can actually read.
  const pickLang = (l: string) => {
    setLang(l);
    const first = catalog.find((v) => baseLang(v.lang) === l);
    if (first) setVoiceId(first.id);
    if (!editedRef.current) setText(sampleFor(l));
  };

  return (
    <div className="vf-glass-strong grid grid-cols-1 overflow-hidden rounded-[28px] lg:grid-cols-[1.15fr_1fr]">
      {/* editor */}
      <div className="p-6 md:p-8">
        <textarea
          value={text}
          onChange={(e) => { editedRef.current = true; setText(e.target.value); }}
          rows={6}
          maxLength={DEMO_MAX}
          className="w-full resize-none rounded-2xl border border-white/20 bg-black/45 p-4 text-base leading-relaxed text-white placeholder:text-white/40 focus:border-[var(--l-b)] focus:outline-none"
          placeholder="Type something to hear it spoken…"
        />
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-white/45">
          <span className={tooLong ? 'text-amber-300' : undefined}>
            {text.length} characters
            {remaining !== null && (
              <> · <span className={outOfBudget ? 'text-rose-300' : 'text-white/70'}>
                {remaining} of {limit} free left
              </span></>
            )}
          </span>
          <span className="inline-flex items-center gap-1">
            <Sparkles size={12} className="text-[var(--l-b)]" />
            {engine === 'server'
              ? 'Neural engine · our GPU'
              : engine === 'browser'
                ? 'Browser preview voice (engine unreachable)'
                : `${catalog.length || '…'} voices · ${languages.length || '…'} languages`}
          </span>
        </div>

        {/* language + voice pickers */}
        <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1.5 block text-xs font-medium text-white/60">Language</span>
            <select
              value={lang}
              onChange={(e) => pickLang(e.target.value)}
              className="w-full rounded-xl border border-white/20 bg-black/50 px-3 py-2.5 text-sm text-white focus:border-[var(--l-b)] focus:outline-none"
            >
              {languages.map((l) => (
                <option key={l} value={l} className="bg-[var(--color-surface)] text-[var(--color-fg)]">
                  {langName(l)} ({catalog.filter((v) => baseLang(v.lang) === l).length})
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1.5 block text-xs font-medium text-white/60">Voice</span>
            <select
              value={voice?.id ?? ''}
              onChange={(e) => setVoiceId(e.target.value)}
              className="w-full rounded-xl border border-white/20 bg-black/50 px-3 py-2.5 text-sm text-white focus:border-[var(--l-b)] focus:outline-none"
            >
              {langVoices.map((v) => (
                <option key={v.id} value={v.id} className="bg-[var(--color-surface)] text-[var(--color-fg)]">
                  {v.name}{v.gender && v.gender !== 'neutral' ? ` · ${v.gender}` : ''}
                </option>
              ))}
            </select>
          </label>
        </div>

        {outOfBudget && (
          <p className="mt-4 rounded-xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
            You have used all {limit} free demo characters.{' '}
            <a href="/signup" className="font-semibold underline">Create a free account</a>{' '}
            to keep generating with every voice.
          </p>
        )}
        {!outOfBudget && tooLong && (
          <p className="mt-4 text-sm text-amber-200">
            Only {remaining} free characters left — the rest of this text will not be spoken.
          </p>
        )}

        <button
          onClick={play}
          disabled={!voice || outOfBudget}
          className="vf-btn-primary mt-6 inline-flex w-full items-center justify-center gap-2 rounded-full px-8 py-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
        >
          {status === 'loading' ? (
            <>
              <Loader2 size={16} className="animate-spin" />
              Generating{elapsed ? ` — ${elapsed}s` : '…'}
            </>
          ) : status === 'playing' ? (
            <><Square size={16} /> Stop</>
          ) : (
            <><PlayIcon size={16} /> Generate &amp; play</>
          )}
        </button>
      </div>

      {/* live preview panel */}
      <div className="relative flex flex-col items-center justify-center gap-5 border-t border-white/10 bg-black/25 p-8 lg:border-l lg:border-t-0">
        <div className={`grid h-24 w-24 place-items-center rounded-full bg-[var(--l-a)]/15 ring-1 ring-[var(--l-b)]/40 transition-transform ${status === 'playing' ? 'scale-110' : ''}`}>
          <Volume2 size={40} className="text-[var(--l-b)]" />
        </div>
        <div className="text-center">
          <div className="text-lg font-bold text-white">{voice?.name ?? 'Loading voices…'}</div>
          <div className="text-xs text-white/55">{voice ? langName(voice.lang) : ''}</div>
        </div>
        {/* equalizer */}
        <div className="flex h-14 items-end gap-[3px]" aria-hidden>
          {Array.from({ length: 28 }).map((_, i) => (
            <span
              key={i}
              className="w-[3px] rounded-full"
              style={{
                height: '100%',
                transformOrigin: 'bottom',
                background: 'linear-gradient(180deg, var(--l-b), var(--l-a) 60%, var(--l-c))',
                transform: status === 'playing' ? undefined : 'scaleY(0.12)',
                animation: status === 'playing'
                  ? `vf-eq ${0.6 + (i % 5) * 0.14}s ease-in-out ${(i % 7) * 0.06}s infinite`
                  : 'none',
              }}
            />
          ))}
        </div>
        <div className="px-2 text-center text-xs text-white/45">
          {status === 'playing'
            ? 'Speaking…'
            : status === 'loading'
              ? `Generating about ${Math.max(1, Math.round(text.length / 17))}s of speech — this runs on our own GPU`
              : 'Ready to speak'}
        </div>
      </div>
    </div>
  );
}
