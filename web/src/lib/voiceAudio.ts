/* ------------------------------------------------------------------ */
/*  voiceAudio — a self-contained Web Audio "voice" engine.            */
/*                                                                    */
/*  The landing page is unauthenticated, so instead of calling the    */
/*  real TTS backend it synthesizes a convincing voice-like signal    */
/*  entirely in the browser (formant-ish detuned oscillators through  */
/*  a syllable-rhythm amplitude envelope) and routes it through an    */
/*  AnalyserNode. The 3D hero reads getLevel()/getBands() every frame */
/*  to drive the avatar mouth, holographic ring and particle cloud —  */
/*  a genuine AudioContext → AnalyserNode → three.js reactive loop.   */
/* ------------------------------------------------------------------ */

type Listener = (speaking: boolean) => void;

class VoiceAudio {
  private ctx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private master: GainNode | null = null;
  private freq: Uint8Array<ArrayBuffer> = new Uint8Array(new ArrayBuffer(0));
  private time: Uint8Array<ArrayBuffer> = new Uint8Array(new ArrayBuffer(0));
  private nodes: AudioNode[] = [];
  private stopAt = 0;
  private raf = 0;
  private listeners = new Set<Listener>();

  speaking = false;
  level = 0; // smoothed 0..1 overall loudness

  private ensure() {
    if (this.ctx) return;
    const AC =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext })
        .webkitAudioContext;
    const ctx = new AC();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    analyser.smoothingTimeConstant = 0.8;
    const master = ctx.createGain();
    master.gain.value = 0.0001;
    master.connect(analyser);
    analyser.connect(ctx.destination);
    this.ctx = ctx;
    this.analyser = analyser;
    this.master = master;
    this.freq = new Uint8Array(new ArrayBuffer(analyser.frequencyBinCount));
    this.time = new Uint8Array(new ArrayBuffer(analyser.fftSize));
    this.loop();
  }

  onChange(fn: Listener) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }
  private emit() {
    this.listeners.forEach((l) => l(this.speaking));
  }

  /** Approximate spoken duration for a phrase (seconds). */
  private durationFor(text: string) {
    const words = Math.max(1, text.trim().split(/\s+/).length);
    return Math.min(9, Math.max(1.6, words * 0.34));
  }

  /** Synthesize a voice-like utterance and start it. Returns duration (s). */
  speak(text: string, opts?: { pitch?: number; speed?: number }) {
    this.ensure();
    const ctx = this.ctx!;
    if (ctx.state === 'suspended') ctx.resume();
    this.stopVoice();

    const pitch = opts?.pitch ?? 1;
    const speed = opts?.speed ?? 1;
    const dur = this.durationFor(text) / speed;
    const t0 = ctx.currentTime + 0.02;
    const base = 130 * pitch; // fundamental (male-ish); modulated below

    // amplitude envelope shaped like syllables so the mouth/particles pulse
    const env = ctx.createGain();
    env.gain.setValueAtTime(0.0001, t0);
    const syl = Math.max(3, Math.round(dur * 4.2)); // ~4 syllables / second
    for (let i = 0; i < syl; i++) {
      const ts = t0 + (dur * i) / syl;
      const tm = ts + (dur / syl) * 0.4;
      const te = ts + (dur / syl) * 0.9;
      const peak = 0.22 + Math.random() * 0.28;
      env.gain.setValueAtTime(0.03, ts);
      env.gain.linearRampToValueAtTime(peak, tm);
      env.gain.exponentialRampToValueAtTime(0.04, te);
    }
    env.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    env.connect(this.master!);

    // three detuned formant oscillators + a breath noise layer
    const oscs: OscillatorNode[] = [];
    const formants = [1, 2.4, 3.7];
    formants.forEach((mult, idx) => {
      const o = ctx.createOscillator();
      o.type = idx === 0 ? 'sawtooth' : 'triangle';
      const g = ctx.createGain();
      g.gain.value = idx === 0 ? 0.6 : 0.22 / idx;
      // pitch drift so it reads as intonation, not a monotone buzz
      o.frequency.setValueAtTime(base * mult, t0);
      const steps = 8;
      for (let s = 1; s <= steps; s++) {
        const tt = t0 + (dur * s) / steps;
        const wobble = 1 + Math.sin(s * 1.7) * 0.08 + (Math.random() - 0.5) * 0.05;
        o.frequency.linearRampToValueAtTime(base * mult * wobble, tt);
      }
      o.connect(g);
      g.connect(env);
      o.start(t0);
      o.stop(t0 + dur + 0.05);
      oscs.push(o);
      this.nodes.push(o, g);
    });

    // subtle breath noise for consonant texture
    const noiseBuf = ctx.createBuffer(1, ctx.sampleRate * dur, ctx.sampleRate);
    const data = noiseBuf.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1) * 0.35;
    const noise = ctx.createBufferSource();
    noise.buffer = noiseBuf;
    const nf = ctx.createBiquadFilter();
    nf.type = 'bandpass';
    nf.frequency.value = 1800;
    nf.Q.value = 0.7;
    const ng = ctx.createGain();
    ng.gain.value = 0.12;
    noise.connect(nf);
    nf.connect(ng);
    ng.connect(env);
    noise.start(t0);
    noise.stop(t0 + dur);
    this.nodes.push(noise, nf, ng, env);

    this.speaking = true;
    this.stopAt = (t0 + dur) * 1000;
    this.emit();
    return dur;
  }

  stopVoice() {
    this.nodes.forEach((n) => {
      try {
        (n as OscillatorNode).stop?.();
      } catch {
        /* already stopped */
      }
      try {
        n.disconnect();
      } catch {
        /* noop */
      }
    });
    this.nodes = [];
    if (this.speaking) {
      this.speaking = false;
      this.emit();
    }
  }

  private loop = () => {
    const a = this.analyser;
    if (a) {
      a.getByteFrequencyData(this.freq);
      a.getByteTimeDomainData(this.time);
      // RMS loudness from the time-domain signal
      let sum = 0;
      for (let i = 0; i < this.time.length; i++) {
        const v = (this.time[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / this.time.length);
      const target = Math.min(1, rms * 3.2);
      this.level += (target - this.level) * 0.35;
      if (this.ctx && this.speaking && performance.now() > this.stopAt + 60) {
        this.stopVoice();
      }
    }
    this.raf = requestAnimationFrame(this.loop);
  };

  /** Smoothed overall loudness 0..1. */
  getLevel() {
    return this.level;
  }

  /** `n` averaged frequency bands, each 0..1 (low → high). */
  getBands(n: number, out: Float32Array) {
    const f = this.freq;
    if (!f.length) {
      for (let i = 0; i < n; i++) out[i] = 0;
      return out;
    }
    const per = Math.floor(f.length / n);
    for (let b = 0; b < n; b++) {
      let s = 0;
      for (let i = 0; i < per; i++) s += f[b * per + i];
      out[b] = s / per / 255;
    }
    return out;
  }

  dispose() {
    cancelAnimationFrame(this.raf);
    this.stopVoice();
    this.ctx?.close();
    this.ctx = null;
  }
}

export const voiceAudio = new VoiceAudio();
