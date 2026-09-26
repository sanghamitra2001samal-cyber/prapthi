import { create } from 'zustand';
import { tts } from '../tts/manager';
import type { Voice } from '../tts/types';
import {
  loadHistory,
  saveHistory,
  loadPrefs,
  savePrefs,
  storageAvailable,
  DEFAULT_PREFS,
  type Generation,
} from '../lib/storage';
import * as authApi from '../lib/auth';
import * as cloneApi from '../lib/clone';
import { timestamp, safeFilenamePart } from '../lib/format';

export type Status = 'idle' | 'loading' | 'playing' | 'paused' | 'error';
export type AuthStatus = 'loading' | 'in' | 'out';
export type Overlay = null | 'voices' | 'history' | 'export' | 'settings';

export interface Toast {
  id: string;
  kind: 'success' | 'error' | 'info';
  message: string;
  action?: { label: string; run: () => void };
}

export interface PendingMelody {
  notation: string;
  system: string;
  tonic: string;
  bpm: number;
}

interface AppState {
  // content + settings
  text: string;
  voiceId: string | null;
  rate: number;
  pitch: number;
  volume: number;
  emotion: string;
  intensity: number;
  meter: string; // Sanskrit metre for the Vāgdhenu chant voice

  // auth
  authStatus: AuthStatus;
  user: string | null;
  isAdmin: boolean;

  // runtime
  status: Status;
  highlightIndex: number | null;
  voices: Voice[];
  voicesLoaded: boolean;
  serverReachable: boolean;
  storageOk: boolean;

  // overlays + toasts
  overlay: Overlay;
  toasts: Toast[];

  // history + last successful generation (for export)
  history: Generation[];
  lastGen: Generation | null;

  // latest result audio (server voices) for the inline player + download
  lastAudioUrl: string | null;
  lastAudioFilename: string | null;
  loadResultAudio: () => Promise<void>;

  // a melody composed in Sargam Studio, handed off to Create Song's guide
  pendingMelody: PendingMelody | null;
  setPendingMelody: (m: PendingMelody | null) => void;

  // derived helpers
  activeVoice: () => Voice | undefined;
  canDownloadActive: () => boolean;

  // auth actions
  checkAuth: () => Promise<void>;
  login: (email: string, password: string) => Promise<authApi.AuthResult>;
  signup: (email: string, password: string) => Promise<authApi.AuthResult>;
  verifyEmail: (email: string, code: string) => Promise<authApi.AuthResult>;
  resendCode: (email: string) => Promise<authApi.AuthResult>;
  forgotPassword: (email: string) => Promise<authApi.AuthResult>;
  resetPassword: (
    email: string,
    code: string,
    password: string
  ) => Promise<authApi.AuthResult>;
  logout: () => Promise<void>;

  // actions
  init: () => Promise<void>;
  setText: (t: string) => void;
  clearText: () => void;
  setVoice: (id: string) => void;
  setRate: (n: number) => void;
  setPitch: (n: number) => void;
  setVolume: (n: number) => void;
  setEmotion: (e: string) => void;
  setIntensity: (n: number) => void;
  setMeter: (m: string) => void;
  saveSettings: () => void;
  resetSettings: () => void;

  play: () => Promise<void>;
  pause: () => void;
  resume: () => void;
  stop: () => void;
  preview: (voiceId?: string) => Promise<void>;

  openOverlay: (o: Overlay) => void;
  closeOverlay: () => void;

  toast: (t: Omit<Toast, 'id'>) => void;
  dismissToast: (id: string) => void;

  loadFromHistory: (id: string, autoplay: boolean) => void;
  deleteHistory: (id: string) => void;
  clearHistory: () => void;

  // voice cloning
  refreshVoices: () => Promise<void>;
  createClone: (
    name: string,
    lang: string,
    file: File
  ) => Promise<cloneApi.CloneResult>;
  createIF5Clone: (name: string, file: File) => Promise<cloneApi.CloneResult>;
  deleteClone: (voiceId: string) => Promise<void>;
}

const clamp = (n: number, lo: number, hi: number) =>
  Math.min(hi, Math.max(lo, n));

// Preview = each voice introduces itself by name in its OWN language. (A voice
// can only read its own script — English text through a Hindi/Tamil model is
// silent/garbled — so the template is localized; the brand "Prapthi Ai" is
// transliterated per language.)
const PREVIEW_TEMPLATES: Record<string, (name: string) => string> = {
  en: (n) => `I am ${n}. I am the voice from Prapthi Ai. How are you?`,
  hi: (n) => `मैं ${n} हूँ। मैं Prapthi Ai की आवाज़ हूँ। आप कैसे हैं?`,
  ta: (n) => `நான் ${n}. நான் Prapthi Ai இன் குரல். நீங்கள் எப்படி இருக்கிறீர்கள்?`,
  te: (n) => `నేను ${n}. నేను Prapthi Ai నుండి వచ్చిన స్వరం. మీరు ఎలా ఉన్నారు?`,
  bn: (n) => `আমি ${n}। আমি Prapthi Ai-এর কণ্ঠস্বর। আপনি কেমন আছেন?`,
  kn: (n) => `ನಾನು ${n}. ನಾನು Prapthi Ai ಧ್ವನಿ. ನೀವು ಹೇಗಿದ್ದೀರಿ?`,
  gu: (n) => `હું ${n} છું. હું Prapthi Aiનો અવાજ છું. તમે કેમ છો?`,
  mr: (n) => `मी ${n} आहे. मी Prapthi Aiचा आवाज आहे. तुम्ही कसे आहात?`,
  pa: (n) => `ਮੈਂ ${n} ਹਾਂ। ਮੈਂ Prapthi Ai ਦੀ ਆਵਾਜ਼ ਹਾਂ। ਤੁਸੀਂ ਕਿਵੇਂ ਹੋ?`,
  ml: (n) => `ഞാൻ ${n} ആണ്. ഞാൻ Prapthi Ai യുടെ ശബ്ദമാണ്. സുഖമാണോ?`,
  // Chatterbox multilingual languages
  es: (n) => `Soy ${n}. Soy la voz de Prapthi Ai. ¿Cómo estás?`,
  fr: (n) => `Je suis ${n}. Je suis la voix de Prapthi Ai. Comment allez-vous ?`,
  de: (n) => `Ich bin ${n}. Ich bin die Stimme von Prapthi Ai. Wie geht es dir?`,
  it: (n) => `Sono ${n}. Sono la voce di Prapthi Ai. Come stai?`,
  pt: (n) => `Eu sou ${n}. Sou a voz da Prapthi Ai. Como você está?`,
  ru: (n) => `Я ${n}. Я голос Prapthi Ai. Как дела?`,
  zh: (n) => `我是${n}。我是 Prapthi Ai 的声音。你好吗？`,
  ja: (n) => `私は${n}です。Prapthi Ai の声です。お元気ですか？`,
  ko: (n) => `저는 ${n}입니다. 저는 Prapthi Ai의 목소리입니다. 어떻게 지내세요?`,
  ar: (n) => `أنا ${n}. أنا صوت Prapthi Ai. كيف حالك؟`,
  tr: (n) => `Ben ${n}. Ben Prapthi Ai'nin sesiyim. Nasılsın?`,
  pl: (n) => `Jestem ${n}. Jestem głosem Prapthi Ai. Jak się masz?`,
  nl: (n) => `Ik ben ${n}. Ik ben de stem van Prapthi Ai. Hoe gaat het?`,
  sv: (n) => `Jag är ${n}. Jag är rösten från Prapthi Ai. Hur mår du?`,
  da: (n) => `Jeg er ${n}. Jeg er stemmen fra Prapthi Ai. Hvordan har du det?`,
  no: (n) => `Jeg er ${n}. Jeg er stemmen til Prapthi Ai. Hvordan går det?`,
  fi: (n) => `Olen ${n}. Olen Prapthi Ai:n ääni. Mitä kuuluu?`,
  el: (n) => `Είμαι ο ${n}. Είμαι η φωνή του Prapthi Ai. Τι κάνεις;`,
  he: (n) => `אני ${n}. אני הקול של Prapthi Ai. מה שלומך?`,
  ms: (n) => `Saya ${n}. Saya suara Prapthi Ai. Apa khabar?`,
  sw: (n) => `Mimi ni ${n}. Mimi ni sauti ya Prapthi Ai. Habari yako?`,
};

// Strip the "(Engine, tier)" and "· Language" decorations from a display name.
function cleanVoiceName(display: string): string {
  return display.split(' (')[0].split(' · ')[0].trim();
}

function previewTextFor(name: string, lang: string | undefined): string {
  const code = (lang ?? 'en').split('-')[0].toLowerCase();
  return (PREVIEW_TEMPLATES[code] ?? PREVIEW_TEMPLATES.en)(name);
}

export const useStore = create<AppState>((set, get) => ({
  text: '',
  voiceId: null,
  rate: DEFAULT_PREFS.rate,
  pitch: DEFAULT_PREFS.pitch,
  volume: DEFAULT_PREFS.volume,
  emotion: 'neutral',
  intensity: 1,
  meter: 'anushtubh',

  authStatus: 'loading',
  user: null,
  isAdmin: false,

  status: 'idle',
  highlightIndex: null,
  voices: [],
  voicesLoaded: false,
  serverReachable: false,
  storageOk: true,

  overlay: null,
  toasts: [],

  history: [],
  lastGen: null,
  lastAudioUrl: null,
  lastAudioFilename: null,

  pendingMelody: null,
  setPendingMelody: (m) => set({ pendingMelody: m }),

  async loadResultAudio() {
    const gen = get().lastGen;
    if (!gen) return;
    const provider = tts.get(gen.voiceId);
    if (!provider.synthesizeToBlob) return; // browser voices have no file
    const request = {
      text: gen.text,
      voiceId: gen.voiceId,
      rate: gen.rate,
      pitch: gen.pitch,
      volume: gen.volume,
      emotion: gen.emotion ?? 'neutral',
      intensity: gen.intensity ?? 1,
      meter: get().meter,
    };
    try {
      // WAV is a paid download format. Ask for it, and if this plan does not
      // include it, fall back to mp3 — every plan includes mp3 downloads, so
      // the user still gets their file instead of an error.
      let format: 'wav' | 'mp3' = 'wav';
      let blob: Blob;
      try {
        blob = await provider.synthesizeToBlob(request, 'wav');
      } catch (e) {
        if ((e as { code?: string })?.code !== 'upgrade_required') throw e;
        format = 'mp3';
        blob = await provider.synthesizeToBlob(request, 'mp3');
      }
      const url = URL.createObjectURL(blob);
      const prev = get().lastAudioUrl;
      if (prev) URL.revokeObjectURL(prev);
      set({
        lastAudioUrl: url,
        lastAudioFilename: `prapthiai_${safeFilenamePart(
          gen.voiceName
        )}_${timestamp(new Date(gen.createdAt))}.${format}`,
      });
    } catch {
      /* leave player hidden on failure */
    }
  },

  activeVoice: () => get().voices.find((v) => v.id === get().voiceId),
  canDownloadActive: () => {
    const v = get().activeVoice();
    return !!v && v.downloadable;
  },

  async checkAuth() {
    const who = await authApi.checkAuth();
    if (who) {
      set({ authStatus: 'in', user: who.user, isAdmin: who.isAdmin });
      await get().init();
    } else {
      set({ authStatus: 'out', user: null, isAdmin: false });
    }
  },

  async login(email, password) {
    const res = await authApi.login(email, password);
    if (res.ok) {
      set({ authStatus: 'in', user: res.user ?? email, isAdmin: !!res.isAdmin });
      await get().init();
    }
    return res;
  },

  signup: (email, password) => authApi.signup(email, password),
  verifyEmail: (email, code) => authApi.verifyEmail(email, code),
  resendCode: (email) => authApi.resendCode(email),
  forgotPassword: (email) => authApi.forgotPassword(email),
  resetPassword: (email, code, password) =>
    authApi.resetPassword(email, code, password),

  async logout() {
    await authApi.logout();
    get().stop();
    set({ authStatus: 'out', user: null, isAdmin: false, voices: [], voicesLoaded: false });
    // Leave the studio entirely and land on the site's current sign-in page.
    // A full load (not a client-side route) guarantees no signed-in state or
    // cached view survives, and avoids the studio's own landing page.
    try {
      window.location.replace('/login');
    } catch {
      /* non-browser context (tests) */
    }
  },

  async init() {
    const prefs = loadPrefs();
    const storageOk = storageAvailable();
    set({
      rate: clamp(prefs.rate, 0.5, 1.5),
      pitch: prefs.pitch,
      volume: prefs.volume,
      emotion: prefs.emotion ?? 'neutral',
      intensity: prefs.intensity ?? 1,
      meter: prefs.meter ?? 'anushtubh',
      history: loadHistory(),
      storageOk,
    });

    const voices = await tts.listVoices();
    const reachable = tts.serverReachable();
    // Pick last-used voice if still present, else first downloadable, else first.
    let voiceId = get().voiceId;
    if (!voiceId) {
      const remembered = voices.find((v) => v.id === prefs.lastVoiceId);
      voiceId =
        remembered?.id ??
        voices.find((v) => v.downloadable)?.id ??
        voices[0]?.id ??
        null;
    }
    set({
      voices,
      voicesLoaded: true,
      serverReachable: reachable,
      voiceId,
    });
  },

  setText: (t) => set({ text: t }),

  clearText: () => {
    get().stop();
    set({ text: '', highlightIndex: null });
  },

  setVoice: (id) => {
    set({ voiceId: id });
    persist(get());
  },

  setRate: (n) => {
    set({ rate: clamp(n, 0.5, 1.5) });
    persist(get());
  },
  setPitch: (n) => {
    set({ pitch: clamp(n, 0.5, 2.0) });
    persist(get());
  },
  setVolume: (n) => {
    set({ volume: clamp(n, 0, 1.5) });
    persist(get());
  },
  setEmotion: (e) => {
    set({ emotion: e });
  },
  setIntensity: (n) => {
    set({ intensity: clamp(n, 0, 2) });
  },
  setMeter: (m) => {
    set({ meter: m });
    persist(get());
  },
  resetSettings: () => {
    set({ rate: 1.0, pitch: 1.0, volume: 1.0, emotion: 'neutral', intensity: 1 });
    persist(get());
  },
  saveSettings: () => {
    persist(get());
    get().toast({ kind: 'success', message: 'Settings saved as your default.' });
  },

  async play() {
    const s = get();
    const text = s.text.trim();
    if (!text || !s.voiceId) return;
    const provider = tts.get(s.voiceId);
    set({ status: 'loading', highlightIndex: null });
    try {
      await provider.speak(
        {
          text,
          voiceId: s.voiceId,
          rate: s.rate,
          pitch: s.pitch,
          volume: s.volume,
          emotion: s.emotion,
          intensity: s.intensity,
          meter: s.meter,
        },
        {
          onStart: () => {
            // Record as soon as audio begins so Export/history work even if
            // the user stops early.
            set({ status: 'playing' });
            recordGeneration(get(), set);
            // Populate the inline result player (server voices; cache hit).
            void get().loadResultAudio();
          },
          onBoundary: (_c, wordIndex) => set({ highlightIndex: wordIndex }),
          onEnd: () => set({ status: 'idle', highlightIndex: null }),
          onError: () => {
            set({ status: 'error', highlightIndex: null });
            get().toast({
              kind: 'error',
              message: "Couldn't generate audio. Please try again.",
            });
            set({ status: 'idle' });
          },
        }
      );
    } catch {
      /* handled in onError */
    }
  },

  pause() {
    const s = get();
    if (s.status !== 'playing' || !s.voiceId) return;
    tts.get(s.voiceId).pause();
    set({ status: 'paused' });
  },

  resume() {
    const s = get();
    if (s.status !== 'paused' || !s.voiceId) return;
    tts.get(s.voiceId).resume();
    set({ status: 'playing' });
  },

  stop() {
    const s = get();
    if (s.voiceId) tts.get(s.voiceId).stop();
    set({ status: 'idle', highlightIndex: null });
  },

  async preview(voiceId) {
    const id = voiceId ?? get().voiceId;
    if (!id) return;
    const provider = tts.get(id);
    provider.stop();
    const voice = get().voices.find((v) => v.id === id);
    const name = cleanVoiceName(voice?.name ?? 'this voice');
    try {
      await provider.speak(
        {
          text: previewTextFor(name, voice?.lang),
          voiceId: id,
          rate: get().rate,
          pitch: get().pitch,
          volume: get().volume,
          meter: get().meter,
        },
        {}
      );
    } catch {
      get().toast({
        kind: 'error',
        message: 'Preview unavailable for this voice.',
      });
    }
  },

  openOverlay: (o) => set({ overlay: o }),
  closeOverlay: () => set({ overlay: null }),

  toast: (t) => {
    const id = crypto.randomUUID();
    set((st) => ({ toasts: [...st.toasts, { ...t, id }] }));
    setTimeout(() => get().dismissToast(id), 4500);
  },
  dismissToast: (id) =>
    set((st) => ({ toasts: st.toasts.filter((t) => t.id !== id) })),

  loadFromHistory: (id, autoplay) => {
    const item = get().history.find((h) => h.id === id);
    if (!item) return;
    const voiceExists = get().voices.some((v) => v.id === item.voiceId);
    set({
      text: item.text,
      voiceId: voiceExists ? item.voiceId : get().voiceId,
      rate: item.rate,
      pitch: item.pitch,
      volume: item.volume,
      emotion: item.emotion ?? 'neutral',
      intensity: item.intensity ?? 1,
      overlay: null,
    });
    if (autoplay) void get().play();
  },

  deleteHistory: (id) => {
    const prev = get().history;
    const next = prev.filter((h) => h.id !== id);
    set({ history: next });
    saveHistory(next);
    get().toast({
      kind: 'info',
      message: 'Deleted',
      action: {
        label: 'Undo',
        run: () => {
          set({ history: prev });
          saveHistory(prev);
        },
      },
    });
  },

  clearHistory: () => {
    set({ history: [] });
    saveHistory([]);
  },

  async refreshVoices() {
    const voices = await tts.listVoices();
    set({ voices });
  },

  async createClone(name, lang, file) {
    const res = await cloneApi.createClone(name, lang, file);
    if (res.ok) await get().refreshVoices();
    return res;
  },

  async createIF5Clone(name, file) {
    const res = await cloneApi.createIF5Clone(name, file);
    if (res.ok) await get().refreshVoices();
    return res;
  },

  async deleteClone(voiceId) {
    const ok = await cloneApi.deleteClone(voiceId);
    if (ok) {
      if (get().voiceId === voiceId) set({ voiceId: null });
      await get().refreshVoices();
    }
  },
}));

function persist(s: AppState) {
  savePrefs({
    lastVoiceId: s.voiceId,
    rate: s.rate,
    pitch: s.pitch,
    volume: s.volume,
    emotion: s.emotion,
    intensity: s.intensity,
    meter: s.meter,
  });
}

function recordGeneration(
  s: AppState,
  set: (partial: Partial<AppState>) => void
) {
  const voice = s.voices.find((v) => v.id === s.voiceId);
  const gen: Generation = {
    id: crypto.randomUUID(),
    text: s.text.trim(),
    voiceId: s.voiceId ?? '',
    voiceName: voice?.name ?? 'Unknown',
    rate: s.rate,
    pitch: s.pitch,
    volume: s.volume,
    emotion: s.emotion,
    intensity: s.intensity,
    createdAt: Date.now(),
  };
  const history = [gen, ...s.history].slice(0, 20);
  const ok = saveHistory(history);
  set({ history, lastGen: gen, storageOk: ok ? s.storageOk : false });
}
