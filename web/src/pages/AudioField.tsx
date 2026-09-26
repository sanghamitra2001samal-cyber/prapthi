import { useEffect, useRef } from 'react';

/* ------------------------------------------------------------------ */
/*  AudioField — a bespoke generative background for the hero.         */
/*                                                                    */
/*  Instead of a looping stock video, this renders a living "sound    */
/*  field": layered undulating waveform bands (like a voice           */
/*  spectrogram), a drift of glowing light particles, and a soft      */
/*  reactive glow — all in the Prapthi azure/cyan palette. It is      */
/*  self-contained (no external assets), DPR-aware and pauses for     */
/*  users who prefer reduced motion.                                  */
/* ------------------------------------------------------------------ */

const PALETTE = ['#064eff', '#7ca9ff', '#3265ff'];

type Particle = {
  x: number;
  y: number;
  r: number;
  vx: number;
  vy: number;
  a: number;
  hue: string;
};

export default function AudioField({ className = '' }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const reduced = window.matchMedia(
      '(prefers-reduced-motion: reduce)'
    ).matches;

    let width = 0;
    let height = 0;
    let dpr = Math.min(window.devicePixelRatio || 1, 2);
    let particles: Particle[] = [];

    const seedParticles = () => {
      const count = Math.round((width * height) / 26000);
      particles = Array.from({ length: count }).map(() => ({
        x: Math.random() * width,
        y: Math.random() * height,
        r: 0.6 + Math.random() * 2.2,
        vx: (Math.random() - 0.5) * 0.25,
        vy: -0.1 - Math.random() * 0.35,
        a: 0.15 + Math.random() * 0.5,
        hue: PALETTE[Math.floor(Math.random() * PALETTE.length)],
      }));
    };

    const resize = () => {
      const parent = canvas.parentElement;
      width = parent?.clientWidth ?? window.innerWidth;
      height = parent?.clientHeight ?? window.innerHeight;
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      seedParticles();
    };

    // One undulating waveform band. Each band is a smooth stack of sine
    // components so the crest never repeats mechanically.
    const drawWave = (
      t: number,
      baseY: number,
      amp: number,
      speed: number,
      color: string,
      alpha: number,
      thickness: number
    ) => {
      ctx.beginPath();
      const step = 6;
      for (let x = -step; x <= width + step; x += step) {
        const k = x / width;
        const y =
          baseY +
          Math.sin(k * 6.2 + t * speed) * amp +
          Math.sin(k * 13.1 - t * speed * 1.6) * amp * 0.4 +
          Math.sin(k * 2.3 + t * speed * 0.5) * amp * 0.6;
        if (x === -step) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      const grad = ctx.createLinearGradient(0, 0, width, 0);
      grad.addColorStop(0, 'transparent');
      grad.addColorStop(0.5, color);
      grad.addColorStop(1, 'transparent');
      ctx.strokeStyle = grad;
      ctx.globalAlpha = alpha;
      ctx.lineWidth = thickness;
      ctx.lineCap = 'round';
      ctx.shadowColor = color;
      ctx.shadowBlur = 18;
      ctx.stroke();
      ctx.shadowBlur = 0;
      ctx.globalAlpha = 1;
    };

    let raf = 0;
    const start = performance.now();

    const render = (now: number) => {
      const t = (now - start) / 1000;
      ctx.clearRect(0, 0, width, height);

      // Drifting light particles
      for (const p of particles) {
        if (!reduced) {
          p.x += p.vx;
          p.y += p.vy;
          if (p.y < -10) {
            p.y = height + 10;
            p.x = Math.random() * width;
          }
          if (p.x < -10) p.x = width + 10;
          if (p.x > width + 10) p.x = -10;
        }
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = p.hue;
        ctx.globalAlpha = p.a * (0.6 + 0.4 * Math.sin(t * 2 + p.x));
        ctx.shadowColor = p.hue;
        ctx.shadowBlur = 8;
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      ctx.shadowBlur = 0;

      // Layered waveform bands, anchored toward the lower third
      const anchor = height * 0.62;
      const wt = reduced ? 0 : t;
      drawWave(wt, anchor + height * 0.06, height * 0.05, 0.6, PALETTE[2], 0.35, 1.5);
      drawWave(wt, anchor, height * 0.07, 0.8, PALETTE[0], 0.55, 2);
      drawWave(wt, anchor - height * 0.05, height * 0.05, 1.05, PALETTE[1], 0.7, 2.5);

      if (!reduced) raf = requestAnimationFrame(render);
    };

    resize();
    render(performance.now());
    window.addEventListener('resize', resize);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className={`pointer-events-none ${className}`}
    />
  );
}
