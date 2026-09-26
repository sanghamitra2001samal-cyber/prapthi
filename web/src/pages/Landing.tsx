import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'motion/react';
import {
  ArrowRight,
  ArrowDown,
  Play as PlayIcon,
  Square,
  Zap,
  ShieldCheck,
  Cpu,
  Sparkles,
  GraduationCap,
  Gamepad2,
  Building2,
  Accessibility,
  AudioLines,
  Lock,
  Download,
  Quote,
  Star,
  Mail,
  Mic,
  Bot,
  UserPlus,
  Music,
  Music2,
  Languages,
  FileText,
  BookOpen,
  Volume2,
  Megaphone,
  Menu as MenuIcon,
  X as CloseIcon,
} from 'lucide-react';
import Lenis from 'lenis';
import { useStore } from '../state/store';
import { voiceAudio } from '../lib/voiceAudio';
import DemoTTS from '../components/DemoTTS';

const WRAP = 'mx-auto max-w-[1600px]';

const reveal = {
  initial: { opacity: 0, y: 40 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: '-80px' },
  transition: { duration: 0.8, ease: [0.22, 1, 0.36, 1] as const },
};

/* Brand social icons (lucide dropped brand glyphs — use inline SVG paths). */
const SOCIALS: { label: string; d: string }[] = [
  { label: 'X', d: 'M18.9 1.153h3.68l-8.04 9.19L24 22.846h-7.406l-5.8-7.584-6.638 7.584H.474l8.6-9.83L0 1.153h7.594l5.243 6.932ZM17.61 20.644h2.039L6.486 3.24H4.298Z' },
  { label: 'GitHub', d: 'M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12' },
  { label: 'LinkedIn', d: 'M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z' },
  { label: 'YouTube', d: 'M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z' },
];

/* ------------------------------------------------------------------ */
/*  Scroll-scrubbed fullscreen video — the concept film that moves      */
/*  forward as the visitor scrolls (its playhead is tied to scroll).    */
/* ------------------------------------------------------------------ */
function VideoScrub() {
  return (
    <div className="fixed inset-0 h-screen w-screen overflow-hidden bg-black" style={{ position: 'fixed', zIndex: 0 }}>
      {/* static gradient backdrop (concept video removed) */}
      <div className="absolute inset-0 bg-[radial-gradient(120%_90%_at_50%_28%,#241546_0%,#0a0713_55%,#05050b_100%)]" />
      {/* cinematic scrims — keep overlaid copy legible */}
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-black/60 via-black/25 to-black/80" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(130%_95%_at_50%_45%,transparent_38%,rgba(3,4,10,0.82))]" />
    </div>
  );
}

/* Thin top scroll-progress line (the film's timeline). */
function ScrollProgress() {
  const bar = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = bar.current;
    if (!el) return;
    let raf = 0;
    const tick = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      const p = max > 0 ? window.scrollY / max : 0;
      el.style.transform = `scaleX(${p.toFixed(4)})`;
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(raf);
  }, []);
  return (
    <div className="fixed inset-x-0 top-0 h-[3px] bg-white/10" style={{ position: 'fixed', zIndex: 60 }}>
      <div ref={bar} className="h-full origin-left bg-gradient-to-r from-[var(--l-a)] via-[var(--l-b)] to-[var(--l-c)]" />
    </div>
  );
}

/* A full-height overlay chapter that drifts into view over the film. */
function Chapter({
  id,
  align = 'center',
  headerSafe = false,
  children,
}: {
  id?: string;
  align?: 'center' | 'left' | 'right';
  /* Pads the top so content clears the fixed Navbar at rest (hero only). */
  headerSafe?: boolean;
  children: ReactNode;
}) {
  const justify = align === 'left' ? 'justify-start text-left' : align === 'right' ? 'justify-end text-right' : 'justify-center text-center';
  return (
    <section id={id} className={`relative flex min-h-screen items-center ${justify} px-6 md:px-14 ${headerSafe ? 'pt-32 md:pt-36' : ''}`}>
      <motion.div
        initial={{ opacity: 0, y: 44, filter: 'blur(6px)' }}
        whileInView={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
        viewport={{ margin: '-35% 0px -35% 0px' }}
        transition={{ duration: 1, ease: [0.22, 1, 0.36, 1] }}
        className="w-full max-w-3xl [text-shadow:0_2px_24px_rgba(0,0,0,0.6)]"
      >
        {children}
      </motion.div>
    </section>
  );
}

function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <div className="vf-mont mb-5 text-xs font-semibold uppercase tracking-[0.35em] text-white/55">
      {children}
    </div>
  );
}

/* Counts a numeric stat up from zero when it scrolls into view, keeping any
   non-numeric prefix/suffix (~, +, %, s) so the final label is unchanged. */
function CountUp({ value }: { value: string }) {
  const m = value.match(/^(\D*)(\d+)(.*)$/);
  const ref = useRef<HTMLSpanElement>(null);
  const [display, setDisplay] = useState(m ? `${m[1]}0${m[3]}` : value);
  useEffect(() => {
    if (!m) return;
    const el = ref.current;
    if (!el) return;
    const target = parseInt(m[2], 10);
    const prefix = m[1];
    const suffix = m[3];
    let raf = 0;
    let started = false;
    const run = () => {
      const t0 = performance.now();
      const dur = 1500;
      const tick = (now: number) => {
        const p = Math.min(1, (now - t0) / dur);
        const eased = 1 - Math.pow(1 - p, 3);
        setDisplay(`${prefix}${Math.round(eased * target)}${suffix}`);
        if (p < 1) raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    };
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !started) { started = true; run(); io.disconnect(); }
      },
      { threshold: 0.4 },
    );
    io.observe(el);
    return () => { cancelAnimationFrame(raf); io.disconnect(); };
  }, [value]);
  return <span ref={ref}>{display}</span>;
}

/* ------------------------------------------------------------------ */
/*  Root                                                               */
/* ------------------------------------------------------------------ */
export default function Landing() {
  const authed = useStore((s) => s.authStatus) === 'in';
  useEffect(() => () => voiceAudio.stopVoice(), []);

  // Momentum smooth-scroll (Lenis) — glides the page + the video playhead
  // instead of stepping. Disabled for reduced-motion users.
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const lenis = new Lenis({
      duration: 1.15,
      easing: (t) => 1 - Math.pow(1 - t, 3),
      smoothWheel: true,
      wheelMultiplier: 1,
      touchMultiplier: 1.5,
    });
    let raf = 0;
    const loop = (time: number) => { lenis.raf(time); raf = requestAnimationFrame(loop); };
    raf = requestAnimationFrame(loop);
    // smooth in-page anchor navigation
    const onClick = (e: MouseEvent) => {
      const a = (e.target as HTMLElement).closest?.('a[href^="#"]') as HTMLAnchorElement | null;
      const href = a?.getAttribute('href');
      if (a && href && href.length > 1) {
        const el = document.querySelector(href);
        if (el) { e.preventDefault(); lenis.scrollTo(el as HTMLElement, { offset: 0, duration: 1.4 }); }
      }
    };
    document.addEventListener('click', onClick);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener('click', onClick);
      lenis.destroy();
    };
  }, []);

  return (
    <div className="vf-landing relative bg-black text-white antialiased">
      <VideoScrub />
      <ScrollProgress />
      <Navbar authed={authed} />

      <main className="relative z-10">
        {/* 1 — Hero */}
        <Chapter align="left" headerSafe>
          <div className="flex items-center gap-3">
            <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--l-b)]" />
            <span className="text-xs font-semibold uppercase tracking-[0.3em] text-white/60">The most realistic AI voice platform</span>
          </div>
          <h1 className="mt-6 text-5xl font-bold leading-[0.98] tracking-tight sm:text-6xl md:text-7xl lg:text-8xl">
            Give every story
            <br />
            an unforgettable <span className="vf-gradient-text">voice.</span>
          </h1>
          <p className="mt-7 max-w-xl text-lg leading-relaxed text-white/75">
            Prapthi Ai turns any text into stunningly human speech — 280+ voices
            across 50+ languages, rendered in seconds. Private, API-free, and
            powered by your own GPU.
          </p>
          <div className="mt-10 flex flex-wrap items-center gap-4">
            <Link
              to={authed ? '/dashboard' : '/signup'}
              className="vf-btn-primary group inline-flex items-center gap-2 rounded-full px-7 py-4 text-sm font-semibold text-white"
            >
              {authed ? 'Open Dashboard' : 'Start for free'}
              <ArrowRight size={18} className="transition-transform group-hover:translate-x-1" />
            </Link>
            <HearButton phrase="Prapthi AI turns any text into stunningly human speech." label="Hear it speak" />
          </div>
          <div className="mt-16 flex items-center gap-2 text-white/50">
            <span className="text-[11px] uppercase tracking-[0.3em]">Scroll to begin</span>
            <ArrowDown size={16} className="vf-bounce-down" />
          </div>
        </Chapter>

        {/* 2 — Value proposition */}
        <Chapter id="realism">
          <Eyebrow>Experience Prapthi Ai</Eyebrow>
          <h2 className="text-4xl font-bold leading-[1.04] tracking-tight md:text-6xl">
            Captivate every listener. Speak any language.{' '}
            <span className="vf-gradient-text">Sound completely human.</span>
          </h2>
          <p className="mx-auto mt-6 max-w-xl text-lg leading-relaxed text-white/75">
            Robotic narration breaks the spell. Prapthi Ai delivers studio-grade
            speech with natural intonation, emotion and pacing — so every word
            feels alive.
          </p>
        </Chapter>

        {/* 3 — Under the hood (the engine) */}
        <section id="engine" className="relative flex min-h-screen items-center px-6 py-24 md:px-14">
          <div className="mx-auto w-full max-w-6xl">
            <motion.div {...reveal} className="mb-12 max-w-2xl [text-shadow:0_2px_24px_rgba(0,0,0,0.6)]">
              <Eyebrow>Under the hood</Eyebrow>
              <h2 className="mt-4 text-4xl font-bold tracking-tight md:text-5xl">
                A serious engine behind a{' '}
                <span className="vf-gradient-text">simple studio.</span>
              </h2>
              <p className="mt-5 text-lg leading-relaxed text-white/75">
                Prapthi Ai is engineered for quality, speed and privacy from the
                ground up. Here's exactly what powers it.
              </p>
            </motion.div>
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {ENGINE.map((f, i) => (
                <motion.div
                  key={f.title}
                  initial={{ opacity: 0, y: 30 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: '-40px' }}
                  transition={{ delay: (i % 3) * 0.08, duration: 0.55 }}
                  className="vf-glass-strong rounded-3xl p-6"
                >
                  <span className="inline-grid h-11 w-11 place-items-center rounded-xl bg-[var(--l-a)]/15 text-[var(--l-b)] ring-1 ring-[var(--l-a)]/30">
                    <f.Icon size={20} />
                  </span>
                  <h3 className="mt-4 text-lg font-bold tracking-tight">{f.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-white/70">{f.body}</p>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* 4 — Results / stats */}
        <Chapter>
          <Eyebrow>When every word matters</Eyebrow>
          <h2 className="text-4xl font-bold tracking-tight md:text-6xl">
            We <span className="vf-gradient-text">deliver.</span>
          </h2>
          <div className="mx-auto mt-12 grid max-w-3xl grid-cols-2 gap-4 md:grid-cols-4">
            {[
              ['280+', 'Studio voices'],
              ['40', 'Languages'],
              ['~2s', 'Average render'],
              ['100%', 'Private & API-free'],
            ].map(([n, l], i) => (
              <motion.div
                key={l}
                initial={{ opacity: 0, y: 26, scale: 0.96 }}
                whileInView={{ opacity: 1, y: 0, scale: 1 }}
                viewport={{ once: true, margin: '-40px' }}
                transition={{ delay: i * 0.08, duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
                className="vf-glass-strong vf-glow-hover vf-float rounded-2xl px-4 py-8 text-center"
                style={{ animationDelay: `${i * 0.7}s` }}
              >
                <div className="text-4xl font-bold tracking-tight md:text-5xl">
                  <CountUp value={n} />
                </div>
                <div className="mt-2 text-[11px] uppercase tracking-[0.18em] text-white/55">{l}</div>
              </motion.div>
            ))}
          </div>
        </Chapter>

        {/* 5 — Live demo studio (below "When every word matters") */}
        <section id="demo" className="relative flex min-h-screen items-center px-6 py-24 md:px-14">
          <div className="mx-auto w-full max-w-5xl">
            <motion.div {...reveal} className="mb-10 text-center [text-shadow:0_2px_24px_rgba(0,0,0,0.6)]">
              <Eyebrow>Live demo</Eyebrow>
              <h2 className="mt-4 text-4xl font-bold tracking-tight md:text-6xl">
                Type it. <span className="vf-gradient-text">Hear it.</span> Right now.
              </h2>
              <p className="mx-auto mt-5 max-w-xl text-lg text-white/75">
                Pick one of our best voices, type any line, and press play — no
                sign-up needed to try.
              </p>
            </motion.div>
            <motion.div
              initial={{ opacity: 0, y: 40, scale: 0.98 }}
              whileInView={{ opacity: 1, y: 0, scale: 1 }}
              viewport={{ once: true, margin: '-60px' }}
              transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
            >
              <DemoTTS />
            </motion.div>
          </div>
        </section>

        {/* 4b — Everything in the platform. Mirrors the real studio nav, so the
            page advertises exactly what a visitor gets after signing up. */}
        <section id="services" className="relative flex min-h-screen items-center px-6 py-24 md:px-14">
          <div className="mx-auto w-full max-w-6xl">
            <motion.div {...reveal} className="mb-12 text-center [text-shadow:0_2px_24px_rgba(0,0,0,0.6)]">
              <Eyebrow>Everything inside</Eyebrow>
              <h2 className="mt-4 text-4xl font-bold tracking-tight md:text-6xl">
                One account. <span className="vf-gradient-text">Thirteen studios.</span>
              </h2>
              <p className="mx-auto mt-5 max-w-2xl text-lg text-white/75">
                Speech, music and post-production in one place — all running on our
                own GPUs, with no third-party API in the path.
              </p>
            </motion.div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {SERVICES.map(({ icon: I, title, body }, i) => (
                <motion.div
                  key={title}
                  initial={{ opacity: 0, y: 26 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: '-40px' }}
                  transition={{ duration: 0.5, delay: (i % 3) * 0.07, ease: [0.22, 1, 0.36, 1] }}
                  className="vf-glass-strong rounded-2xl p-5"
                >
                  <div className="mb-3 inline-grid h-11 w-11 place-items-center rounded-xl bg-[var(--l-a)]/18 ring-1 ring-[var(--l-b)]/35">
                    <I size={20} className="text-[var(--l-b)]" />
                  </div>
                  <h3 className="text-base font-bold text-white">{title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-white/65">{body}</p>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* 5 — Use cases */}
        <Chapter id="usecases">
          <Eyebrow>Where teams use it</Eyebrow>
          <h2 className="text-4xl font-bold tracking-tight md:text-6xl">
            One studio, <span className="vf-gradient-text">every use case.</span>
          </h2>
          <div className="mx-auto mt-12 grid max-w-4xl grid-cols-2 gap-4 md:grid-cols-5">
            {([
              [Sparkles, 'Content'],
              [GraduationCap, 'Education'],
              [Gamepad2, 'Gaming'],
              [Building2, 'Enterprise'],
              [Accessibility, 'Accessibility'],
            ] as [typeof Sparkles, string][]).map(([I, label], i) => (
              <div key={i} className="vf-glass-strong flex flex-col items-center gap-3 rounded-2xl px-3 py-6">
                <I size={26} className="text-[var(--l-b)]" />
                <span className="text-sm font-semibold">{label}</span>
              </div>
            ))}
          </div>
        </Chapter>

        {/* 6 — Testimonials */}
        <section className="relative flex min-h-screen flex-col justify-center py-24">
          <div className="mb-12 px-6 md:px-14">
            <motion.div {...reveal} className="mx-auto max-w-3xl text-center [text-shadow:0_2px_24px_rgba(0,0,0,0.6)]">
              <Eyebrow>Loved by builders</Eyebrow>
              <h2 className="mt-4 text-4xl font-bold tracking-tight md:text-6xl">
                Trusted to <span className="vf-gradient-text">speak for teams.</span>
              </h2>
            </motion.div>
          </div>
          <div className="relative flex overflow-hidden [mask-image:linear-gradient(90deg,transparent,#000_8%,#000_92%,transparent)]">
            <div className="vf-marquee flex shrink-0 gap-6 pr-6">
              {[...QUOTES, ...QUOTES].map((q, i) => (
                <figure key={i} className="vf-glass-strong w-[340px] shrink-0 rounded-3xl p-6">
                  <Quote size={22} className="text-[var(--l-b)]" />
                  <blockquote className="mt-4 text-sm leading-relaxed text-white/85">{q.text}</blockquote>
                  <div className="mt-5 flex items-center justify-between">
                    <figcaption>
                      <div className="text-sm font-semibold text-white">{q.name}</div>
                      <div className="text-xs text-white/55">{q.org}</div>
                    </figcaption>
                    <div className="flex gap-0.5 text-[var(--l-b)]">
                      {Array.from({ length: 5 }).map((_, s) => <Star key={s} size={13} fill="currentColor" />)}
                    </div>
                  </div>
                </figure>
              ))}
            </div>
          </div>
        </section>

        {/* 7 — Final CTA */}
        <section className="relative flex min-h-screen flex-col items-center justify-center px-6 text-center md:px-14">
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ margin: '-30% 0px -30% 0px' }}
            transition={{ duration: 1.1, ease: [0.22, 1, 0.36, 1] }}
            className="max-w-2xl [text-shadow:0_2px_24px_rgba(0,0,0,0.6)]"
          >
            <h2 className="text-5xl font-bold leading-[0.98] tracking-tight md:text-8xl">
              It's time to give your <br /> words a <span className="vf-gradient-text">voice.</span>
            </h2>
            <div className="mt-11 flex flex-wrap items-center justify-center gap-4">
              <Link
                to={authed ? '/dashboard' : '/signup'}
                className="vf-btn-primary vf-pulse group inline-flex items-center gap-2 rounded-full px-9 py-4 text-sm font-semibold text-white"
              >
                {authed ? 'Open Dashboard' : 'Start for free'}
                <ArrowRight size={18} className="transition-transform group-hover:translate-x-1" />
              </Link>
              <HearButton phrase="Your words deserve a voice." label="Hear it" ghost />
            </div>
          </motion.div>
        </section>
      </main>

      <Footer authed={authed} />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Under-the-hood engine features (real platform capabilities)        */
/* ------------------------------------------------------------------ */
const ENGINE = [
  {
    Icon: Cpu,
    title: 'Multi-engine speech core',
    body: 'Our proprietary multi-engine core routes every request to the best-matched neural voice — tuned separately for fast, natural reads across 50+ languages, premium English, Chinese, Hindi and Sanskrit, and studio-HD delivery for 18 Indian languages.',
  },
  {
    Icon: AudioLines,
    title: 'Studio-grade audio polishing',
    body: 'Every clip is loudness-matched, de-clicked and peak-limited automatically, so output is clean, consistent and ready to publish.',
  },
  {
    Icon: Zap,
    title: 'GPU acceleration + caching',
    body: 'Models run on your own GPU with CUDA acceleration, and a content-addressed cache replays identical phrases instantly.',
  },
  {
    Icon: ShieldCheck,
    title: 'Security built in',
    body: 'Scrypt-hashed passwords, signed sessions, email verification, password reset and per-IP rate limiting protect every account.',
  },
  {
    Icon: Lock,
    title: 'Private & API-free',
    body: 'No third-party TTS services. Your scripts, voices and generated audio stay entirely within your infrastructure.',
  },
  {
    Icon: Download,
    title: 'Export anywhere',
    body: 'Download broadcast-ready WAV or MP3 with a single click, and keep a re-playable history of everything you create.',
  },
];

/* Every studio in the product, mirroring the signed-in navigation so the
   landing page promises exactly what the account delivers. */
const SERVICES = [
  { icon: Mic, title: 'Text to Speech',
    body: '280+ voices across 50+ languages, with 20 emotions from happy and sad to empathetic and urgent.' },
  { icon: UserPlus, title: 'Voice Cloning',
    body: 'Clone a voice from a short recording. Background noise is filtered out automatically.' },
  { icon: Bot, title: 'Voice Agent',
    body: 'A conversational agent that listens and answers out loud, in the voice you choose.' },
  { icon: Languages, title: 'AI Dubbing',
    body: 'Dub video into another language — speakers detected separately, emotion carried across, and the original voices optionally preserved.' },
  { icon: Music, title: 'Song Creation',
    body: 'Turn a script into a finished song with vocals, instruments and arrangement.' },
  { icon: Music2, title: 'Sargam Studio',
    body: 'Indian classical notation rendered to audio, with proper swaras and meter.' },
  { icon: AudioLines, title: 'Voice Isolator',
    body: 'Split any recording into clean vocals and instrumental stems.' },
  { icon: FileText, title: 'Speech to Text',
    body: 'Accurate transcription with timestamps, across every language we speak.' },
  { icon: BookOpen, title: 'Audiobook Studio',
    body: 'Long-form narration with consistent voice and pacing across chapters.' },
  { icon: Sparkles, title: 'Sound Effects',
    body: 'Generate effects and ambience from a text description.' },
  { icon: Volume2, title: 'Audio Native',
    body: 'An embeddable player that reads any page of your site aloud.' },
  { icon: Megaphone, title: 'Ads Engine',
    body: 'Scripted ad reads with the pacing and emphasis a campaign needs.' },
  { icon: ShieldCheck, title: 'Self-hosted',
    body: 'Every model runs on our own GPUs. Your text and audio never touch a third-party API.' },
];

const QUOTES = [
  { text: 'We narrated an entire course library in a weekend. The voices are so natural our learners thought we hired actors.', name: 'Aarav Mehta', org: 'Head of Content, SkillBridge' },
  { text: 'The most natural multilingual TTS we have shipped. Latency is unreal.', name: 'Lena Fischer', org: 'Northwind Media' },
  { text: 'Voice cloning gave our game characters real personality overnight.', name: 'Diego Santos', org: 'Pixel Forge' },
  { text: 'Private, on our own GPU, with zero data leaving. Compliance loved it.', name: 'Priya Nair', org: 'Cerner Health' },
  { text: 'Our support IVR finally sounds human. Call satisfaction jumped.', name: 'Tom Whitaker', org: 'Helio Bank' },
];

/* ------------------------------------------------------------------ */
/*  Professional footer (solid, grounded — sits over the fixed video)  */
/* ------------------------------------------------------------------ */
const FOOTER_COLS: { title: string; links: [string, string][] }[] = [
  { title: 'Product', links: [['Studio', '#'], ['Voices', '#usecases'], ['Realism', '#realism'], ['The engine', '#engine']] },
  { title: 'Company', links: [['About', '#'], ['Blog', '#'], ['Careers', '#'], ['Contact', '#']] },
  { title: 'Resources', links: [['Help Center', '/help'], ['Documentation', '#'], ['Status', '#'], ['Changelog', '#']] },
  { title: 'Legal', links: [['Privacy', '#'], ['Terms', '#'], ['Security', '#']] },
];

const fadeItem = {
  hidden: { opacity: 0, y: 22 },
  show: { opacity: 1, y: 0, transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] as const } },
};

function Footer({ authed }: { authed: boolean }) {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const onSubmit = (e: React.FormEvent) => { e.preventDefault(); navigate('/signup'); };
  const isRoute = (h: string) => h.startsWith('/');
  return (
    <footer className="relative z-10 overflow-hidden border-t border-white/10 bg-[rgba(6,9,20,0.5)] shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-2xl backdrop-saturate-150">
      {/* animated flowing gradient divider along the top edge */}
      <div className="vf-flowline pointer-events-none absolute inset-x-0 top-0 h-px" />
      {/* drifting aurora glow + floating orbs (glassmorphism depth) */}
      <div className="vf-aurora pointer-events-none absolute -top-28 left-1/2 h-[380px] w-[860px] -translate-x-1/2 opacity-20" />
      <div className="vf-orb vf-orb-b pointer-events-none absolute -right-10 top-10 h-32 w-32 opacity-30" />
      <div className="vf-orb vf-orb-c pointer-events-none absolute bottom-16 left-8 h-24 w-24 opacity-20" />

      <motion.div
        variants={{ hidden: {}, show: { transition: { staggerChildren: 0.08 } } }}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: '-60px' }}
        className={`${WRAP} relative px-6 py-16 md:px-10 md:py-20`}
      >
        <div className="grid gap-12 lg:grid-cols-[1.6fr_1fr_1fr_1fr_1fr]">
          {/* brand + newsletter + social */}
          <motion.div variants={fadeItem}>
            <Link to="/" className="group flex items-center gap-2">
              <img src="/logo.png" alt="" className="h-8 w-8 rounded-md bg-white/95 object-contain p-0.5 transition-all group-hover:drop-shadow-[0_0_12px_rgba(124,169,255,0.7)]" />
              <span className="text-lg font-bold tracking-tight">Prapthi Ai</span>
            </Link>
            <p className="mt-5 max-w-xs text-sm leading-relaxed text-white/60">
              Human-like AI voices — 280+ voices across 50+ languages, rendered in
              seconds. Private, API-free, and powered by your own GPU.
            </p>
            <form onSubmit={onSubmit} className="mt-6 flex max-w-sm items-center gap-2">
              <div className="relative flex-1">
                <Mail size={15} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-white/40" />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Enter your email"
                  className="w-full rounded-full border border-white/15 bg-white/[0.05] py-3 pl-10 pr-4 text-sm text-white backdrop-blur-md transition-all placeholder:text-white/40 focus:border-[var(--l-b)] focus:bg-white/[0.08] focus:outline-none"
                />
              </div>
              <button type="submit" aria-label="Subscribe" className="vf-btn-primary grid h-11 w-11 shrink-0 place-items-center rounded-full text-white">
                <ArrowRight size={18} />
              </button>
            </form>
            <div className="mt-6 flex items-center gap-3">
              {SOCIALS.map((s) => (
                <a
                  key={s.label}
                  href="#"
                  aria-label={s.label}
                  className="grid h-9 w-9 place-items-center rounded-full border border-white/12 bg-white/[0.04] text-white/70 backdrop-blur-md transition-all duration-300 hover:-translate-y-0.5 hover:scale-110 hover:border-[var(--l-b)]/60 hover:text-white hover:shadow-[0_0_20px_rgba(124,169,255,0.45)]"
                >
                  <svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor" aria-hidden><path d={s.d} /></svg>
                </a>
              ))}
            </div>
          </motion.div>

          {/* link columns */}
          {FOOTER_COLS.map((col) => (
            <motion.div key={col.title} variants={fadeItem}>
              <div className="text-sm font-semibold text-white">{col.title}</div>
              <ul className="mt-4 space-y-3">
                {col.links.map(([label, href]) => (
                  <li key={label}>
                    {isRoute(href) ? (
                      <Link to={href} className="group inline-flex items-center text-sm text-white/60 transition-all hover:translate-x-1 hover:text-white">
                        <span className="mr-0 h-px w-0 bg-[var(--l-b)] transition-all duration-300 group-hover:mr-2 group-hover:w-3" />
                        {label}
                      </Link>
                    ) : (
                      <a href={href} className="group inline-flex items-center text-sm text-white/60 transition-all hover:translate-x-1 hover:text-white">
                        <span className="mr-0 h-px w-0 bg-[var(--l-b)] transition-all duration-300 group-hover:mr-2 group-hover:w-3" />
                        {label}
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            </motion.div>
          ))}
        </div>

        {/* Attribution — required by the CC-BY-4.0 licences of the open datasets
            some voices and models are derived from. */}
        <motion.div variants={fadeItem} className="mt-14 border-t border-white/10 pt-8 text-[11px] leading-relaxed text-white/35">
          <p>
            Some voices are built with open speech resources:{' '}
            <a href="https://huggingface.co/datasets/google/fleurs" target="_blank" rel="noreferrer noopener" className="underline transition-colors hover:text-white/60">Google FLEURS</a>{' '}and{' '}
            <a href="https://huggingface.co/datasets/ai4bharat/Rasa" target="_blank" rel="noreferrer noopener" className="underline transition-colors hover:text-white/60">AI4Bharat Rasa</a>, used under{' '}
            <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer noopener" className="underline transition-colors hover:text-white/60">CC BY 4.0</a>.
          </p>
        </motion.div>

        <motion.div variants={fadeItem} className="mt-6 flex flex-col items-center justify-between gap-4 border-t border-white/10 pt-8 text-xs text-white/45 md:flex-row">
          <p>© {new Date().getFullYear()} Prapthi Ai. All rights reserved.</p>
          <p className="flex items-center gap-2">
            <Lock size={12} className="text-[var(--l-b)]" /> Private · API-free · Powered by your own GPU
          </p>
          <div className="flex items-center gap-5">
            <Link to="/pricing" className="transition-colors hover:text-white">Pricing</Link>
            <Link to="/login" className="transition-colors hover:text-white">Login</Link>
            <Link to={authed ? '/dashboard' : '/signup'} className="transition-colors hover:text-white">
              {authed ? 'Dashboard' : 'Start for free'}
            </Link>
          </div>
        </motion.div>
      </motion.div>
    </footer>
  );
}

/* ------------------------------------------------------------------ */
/*  Floating glass navigation                                          */
/* ------------------------------------------------------------------ */
const NAV_LINKS: [string, string][] = [
  ['Demo', '#demo'],
  ['The engine', '#engine'],
  ['Use cases', '#usecases'],
];

function Navbar({ authed }: { authed: boolean }) {
  const [scrolled, setScrolled] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => {
    let last = window.scrollY;
    const onScroll = () => {
      const y = window.scrollY;
      setScrolled(y > 40);
      setHidden(y > last && y > 200);
      last = y;
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);
  // The bar slides away on scroll-down; don't leave an orphaned menu behind it.
  useEffect(() => { if (hidden) setMenuOpen(false); }, [hidden]);
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenuOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [menuOpen]);
  const muted = 'text-white/75';
  return (
    <header
      style={{ position: 'fixed', zIndex: 50 }}
      className={`fixed inset-x-0 top-0 px-3 pt-4 transition-all duration-500 md:px-6 md:pt-6 ${
        hidden ? '-translate-y-[130%] opacity-0' : 'translate-y-0 opacity-100'
      }`}
    >
      <div className={`${WRAP} mx-auto flex items-center justify-between rounded-[22px] px-5 py-3.5 transition-all duration-300 md:px-7 ${scrolled ? 'vf-glass-strong' : 'bg-transparent'}`}>
        <Link to="/" className="flex items-center gap-2 text-white">
          <img src="/logo.png" alt="" className="h-8 w-8 rounded-md bg-white/95 object-contain p-0.5" />
          <span className="text-lg font-bold tracking-tight">Prapthi Ai</span>
        </Link>
        <nav className="hidden items-center gap-9 lg:flex">
          {NAV_LINKS.map(([label, href]) => (
            <a key={label} href={href} className={`text-sm font-medium transition-colors hover:text-white ${muted}`}>{label}</a>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          {authed ? (
            <Link to="/dashboard" className="vf-btn-primary rounded-full px-5 py-2.5 text-sm font-semibold text-white">Dashboard</Link>
          ) : (
            <>
              <Link to="/login" className={`hidden text-sm font-medium sm:block ${muted}`}>Login</Link>
              <Link to="/signup" className="vf-btn-primary rounded-full px-5 py-2.5 text-sm font-semibold text-white">Start for free</Link>
            </>
          )}
          <button
            type="button"
            onClick={() => setMenuOpen((o) => !o)}
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen}
            aria-controls="vf-mobile-nav"
            className={`-mr-1 rounded-full p-2 transition-colors hover:text-white lg:hidden ${muted}`}
          >
            {menuOpen ? <CloseIcon size={20} /> : <MenuIcon size={20} />}
          </button>
        </div>
      </div>

      {/* Below lg the inline nav collapses; this keeps every destination —
          Login included — reachable instead of silently dropping them. */}
      <div
        id="vf-mobile-nav"
        hidden={!menuOpen}
        className={`${WRAP} mx-auto mt-2 overflow-hidden rounded-[22px] lg:hidden ${menuOpen ? 'vf-glass-strong' : ''}`}
      >
        <nav className="flex flex-col px-5 py-2">
          {NAV_LINKS.map(([label, href]) => (
            <a
              key={label}
              href={href}
              onClick={() => setMenuOpen(false)}
              className={`border-b border-white/10 py-3.5 text-sm font-medium transition-colors last:border-b-0 hover:text-white ${muted}`}
            >
              {label}
            </a>
          ))}
          {!authed && (
            <Link
              to="/login"
              onClick={() => setMenuOpen(false)}
              className={`py-3.5 text-sm font-medium transition-colors hover:text-white sm:hidden ${muted}`}
            >
              Login
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}

/* Play/stop the live voice-engine demo. */
function HearButton({ phrase, label, ghost = false }: { phrase: string; label: string; ghost?: boolean }) {
  const [speaking, setSpeaking] = useState(false);
  useEffect(() => {
    const off = voiceAudio.onChange(setSpeaking);
    return () => { off(); };
  }, []);
  return (
    <button
      onClick={() => (speaking ? voiceAudio.stopVoice() : voiceAudio.speak(phrase))}
      className={`inline-flex items-center gap-2 rounded-full px-7 py-4 text-sm font-semibold text-white ${ghost ? 'vf-btn-ghost' : 'vf-btn-ghost'}`}
    >
      {speaking ? <Square size={16} /> : <PlayIcon size={16} />}
      {speaking ? 'Stop' : label}
    </button>
  );
}
