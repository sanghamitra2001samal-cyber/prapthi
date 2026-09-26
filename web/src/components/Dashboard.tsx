import { useEffect, useMemo, useRef, useState, lazy, Suspense, type ComponentType } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AudioLines,
  Mic,
  History,
  SlidersHorizontal,
  HelpCircle,
  Info,
  LogOut,
  Menu,
  X,
  Music,
  ListMusic,
  Music2,
  Languages,
  FileText,
  BookOpen,
  Sparkles,
  UserPlus,
  Bot,
  Volume2,
  Megaphone,
  Search,
  Moon,
  Sun,
  CornerDownLeft,
  Users,
} from 'lucide-react';
import { useStore } from '../state/store';
import { useTheme } from '../lib/theme';
import { Studio } from './Studio';
import { CreateSong } from './CreateSong';
import { MySongs } from './MySongs';
import { SargamStudio } from './SargamStudio';
import { Dubbing } from './Dubbing';
import { VoiceIsolator } from './VoiceIsolator';
import { SpeechToText } from './SpeechToText';
import { Audiobook } from './Audiobook';
import { SoundEffects } from './SoundEffects';
import { VoiceCloning } from './VoiceCloning';
import { VoiceAgent } from './VoiceAgent';
import { AudioNative } from './AudioNative';
import { AdsEngine } from './AdsEngine';
import { AdminPanel } from './AdminPanel';
import { VoicePicker } from './VoicePicker';
import { SettingsPanel, SettingsRail } from './SettingsPanel';
import { HistoryPanel } from './HistoryPanel';
import { ExportDialog } from './ExportDialog';

// Live Three.js backdrop, lazy-loaded so three.js ships only with the app.
const DashboardBG = lazy(() => import('./DashboardBG'));

type View = 'studio' | 'createsong' | 'mysongs' | 'sargam' | 'dubbing' | 'isolator'
  | 'stt' | 'audiobook' | 'sfx' | 'cloning' | 'agent' | 'audionative' | 'ads' | 'admin';
const TITLES: Record<View, string> = {
  admin: 'Users & Logins',
  studio: 'Text to Speech',
  createsong: 'Create a Song',
  mysongs: 'My Songs',
  sargam: 'Sargam Studio',
  dubbing: 'AI Dubbing',
  isolator: 'Voice Isolator',
  stt: 'Speech to Text',
  audiobook: 'Audiobook Studio',
  sfx: 'Sound Effects',
  cloning: 'Voice Cloning',
  agent: 'Voice Agent',
  audionative: 'Audio Native',
  ads: 'Ads Engine',
};

type Icon = ComponentType<{ size?: number; className?: string }>;
type NavGroup = { label: string; items: { icon: Icon; label: string; view: View }[] };

const GROUPS: NavGroup[] = [
  {
    label: 'Studio',
    items: [
      { icon: Mic, label: 'Text to Speech', view: 'studio' },
      { icon: Bot, label: 'Voice Agent', view: 'agent' },
      { icon: UserPlus, label: 'Voice Cloning', view: 'cloning' },
    ],
  },
  {
    label: 'Music',
    items: [
      { icon: Music, label: 'Create Song', view: 'createsong' },
      { icon: Music2, label: 'Sargam Studio', view: 'sargam' },
      { icon: ListMusic, label: 'My Songs', view: 'mysongs' },
    ],
  },
  {
    label: 'Tools',
    items: [
      { icon: Languages, label: 'AI Dubbing', view: 'dubbing' },
      { icon: AudioLines, label: 'Voice Isolator', view: 'isolator' },
      { icon: FileText, label: 'Speech to Text', view: 'stt' },
      { icon: BookOpen, label: 'Audiobook Studio', view: 'audiobook' },
      { icon: Sparkles, label: 'Sound Effects', view: 'sfx' },
      { icon: Volume2, label: 'Audio Native', view: 'audionative' },
      { icon: Megaphone, label: 'Ads Engine', view: 'ads' },
    ],
  },
];

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';

/** Backend capability each studio needs. Studios not listed only use the core
 * TTS engine and always work. Keys match GET /capabilities on the server. */
const NEEDS: Partial<Record<View, 'stt' | 'llm' | 'agent' | 'ace' | 'sargam'>> = {
  stt: 'stt', cloning: 'stt', dubbing: 'stt',
  agent: 'agent', ads: 'llm',
  createsong: 'ace', sfx: 'ace', isolator: 'ace',
  sargam: 'sargam',
};

// Admin-only group, appended to the nav for administrator accounts.
const ADMIN_GROUP: NavGroup = {
  label: 'Admin',
  items: [{ icon: Users, label: 'Users & Logins', view: 'admin' }],
};

/** The authenticated app — a floating "workspace OS" shell: an ambient stage,
 * a glass icon dock, a ⌘K command palette, and floating panels wrapping every
 * studio view. All views, overlays and shortcuts are preserved. */
export function Dashboard() {
  const overlay = useStore((s) => s.overlay);
  const status = useStore((s) => s.status);
  const play = useStore((s) => s.play);
  const pause = useStore((s) => s.pause);
  const resume = useStore((s) => s.resume);
  const openOverlay = useStore((s) => s.openOverlay);
  const isAdmin = useStore((s) => s.isAdmin);
  const navigate = useNavigate();
  const [navOpen, setNavOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [view, setView] = useState<View>('studio');

  const go = (v: View) => { setView(v); setNavOpen(false); setPaletteOpen(false); };

  // Which studios the server can actually run right now. Until this answers
  // (or if it fails) every studio stays available.
  const [caps, setCaps] = useState<Record<string, boolean> | null>(null);
  useEffect(() => {
    fetch(`${API_BASE}/capabilities`, { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d && typeof d === 'object') setCaps(d); })
      .catch(() => {});
  }, []);
  const ready = (v: View) => { const k = NEEDS[v]; return !k || !caps || caps[k] !== false; };

  // Flat command list (tools + overlays + pages) for the ⌘K palette.
  const commands = useMemo(() => {
    const list: { icon: Icon; label: string; group: string; run: () => void }[] = [];
    for (const g of GROUPS)
      for (const it of g.items)
        list.push({ icon: it.icon, label: it.label, group: g.label, run: () => go(it.view) });
    list.push({ icon: AudioLines, label: 'Browse Voices', group: 'Panel', run: () => { openOverlay('voices'); setPaletteOpen(false); } });
    list.push({ icon: SlidersHorizontal, label: 'Settings', group: 'Panel', run: () => { openOverlay('settings'); setPaletteOpen(false); } });
    list.push({ icon: History, label: 'History', group: 'Panel', run: () => { openOverlay('history'); setPaletteOpen(false); } });
    list.push({ icon: HelpCircle, label: 'Help', group: 'Page', run: () => navigate('/help') });
    list.push({ icon: Info, label: 'About', group: 'Page', run: () => navigate('/about') });
    if (isAdmin)
      list.push({ icon: Users, label: 'Users & Logins', group: 'Admin', run: () => go('admin') });
    return list;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openOverlay, navigate, isAdmin]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const typing =
        target.tagName === 'TEXTAREA' ||
        target.tagName === 'INPUT' ||
        target.isContentEditable;
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      } else if (mod && e.key === 'Enter') {
        e.preventDefault();
        void play();
      } else if (mod && e.key.toLowerCase() === 's') {
        e.preventDefault();
        openOverlay('export');
      } else if (e.key === 'Escape' && paletteOpen) {
        setPaletteOpen(false);
      } else if (e.code === 'Space' && !typing && !overlay && !paletteOpen) {
        e.preventDefault();
        if (status === 'playing') pause();
        else if (status === 'paused') resume();
        else void play();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [play, pause, resume, openOverlay, status, overlay, paletteOpen]);

  return (
    <div className="vf-theme-anim relative h-screen overflow-hidden bg-[var(--color-bg)] text-[var(--color-fg)]">
      <div className="vf-dash-aura pointer-events-none fixed inset-0 z-0 opacity-60" />
      <Suspense fallback={null}>
        <DashboardBG />
      </Suspense>

      <Dock view={view} ready={ready} onView={go} openOverlay={(o) => { openOverlay(o); }} navigate={navigate} />
      <MobileMenu open={navOpen} view={view} ready={ready} onView={go} onClose={() => setNavOpen(false)} openOverlay={(o) => { openOverlay(o); setNavOpen(false); }} navigate={navigate} />

      <div className="relative z-10 flex h-screen flex-col gap-3 p-3 md:pl-[84px]">
        <Topbar
          title={TITLES[view]}
          onMenu={() => setNavOpen(true)}
          onSearch={() => setPaletteOpen(true)}
        />
        <div className="flex min-h-0 flex-1 gap-3">
          <main
            className={`vf-theme-anim min-h-0 flex-1 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)]/82 shadow-[0_24px_60px_-40px_rgba(0,0,0,0.7)] backdrop-blur-2xl ${
              view === 'studio' || view === 'agent' ? 'overflow-hidden' : 'overflow-y-auto'
            }`}
          >
            {!ready(view) ? <ComingSoon label={TITLES[view]} /> : (<>
              {view === 'studio' && <Studio />}
              {view === 'createsong' && <CreateSong onView={(v) => setView(v as View)} />}
              {view === 'mysongs' && <MySongs onView={(v) => setView(v as View)} />}
              {view === 'sargam' && <SargamStudio onView={(v) => setView(v as View)} />}
              {view === 'dubbing' && <Dubbing />}
              {view === 'isolator' && <VoiceIsolator />}
              {view === 'stt' && <SpeechToText />}
              {view === 'audiobook' && <Audiobook />}
              {view === 'sfx' && <SoundEffects />}
              {view === 'cloning' && <VoiceCloning />}
              {view === 'audionative' && <AudioNative />}
              {view === 'ads' && <AdsEngine />}
              {view === 'agent' && <VoiceAgent />}
            </>)}
            {view === 'admin' && isAdmin && <AdminPanel />}
          </main>
          {view === 'studio' && <SettingsRail />}
        </div>
      </div>

      {paletteOpen && <CommandPalette commands={commands} onClose={() => setPaletteOpen(false)} />}

      <VoicePicker />
      <SettingsPanel />
      <HistoryPanel />
      <ExportDialog />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Floating glass icon dock (desktop)                                 */
/* ------------------------------------------------------------------ */
function DockButton({ icon: Icon, label, active, soon, onClick }: { icon: Icon; label: string; active?: boolean; soon?: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`group relative grid h-11 w-11 shrink-0 place-items-center rounded-xl transition-all duration-200 ${
        active
          ? 'bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-hover)] text-white shadow-[0_8px_22px_-8px_var(--color-accent)]'
          : 'text-[var(--color-muted)] hover:-translate-y-0.5 hover:bg-[var(--color-surface-2)] hover:text-[var(--color-fg)]'
      } ${soon && !active ? 'opacity-45' : ''}`}
    >
      <Icon size={19} />
      <span className="pointer-events-none absolute left-full z-50 ml-3 hidden whitespace-nowrap rounded-lg bg-[var(--color-surface-2)] px-2.5 py-1.5 text-xs font-medium text-[var(--color-fg)] shadow-lg ring-1 ring-[var(--color-border)] group-hover:block">
        {soon ? `${label} · Coming soon` : label}
      </span>
    </button>
  );
}

function Dock({
  view, ready, onView, openOverlay, navigate,
}: {
  view: View;
  ready: (v: View) => boolean;
  onView: (v: View) => void;
  openOverlay: (o: 'voices' | 'settings' | 'history') => void;
  navigate: (p: string) => void;
}) {
  const user = useStore((s) => s.user);
  const isAdmin = useStore((s) => s.isAdmin);
  const logout = useStore((s) => s.logout);
  const [menu, setMenu] = useState(false);
  const groups = isAdmin ? [...GROUPS, ADMIN_GROUP] : GROUPS;

  return (
    <aside className="vf-theme-anim fixed inset-y-3 left-3 z-40 hidden w-[68px] flex-col items-center rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)]/85 p-2 shadow-[0_24px_60px_-40px_rgba(0,0,0,0.7)] backdrop-blur-xl md:flex">
      <button onClick={() => navigate('/dashboard')} className="mb-1 grid h-11 w-11 place-items-center rounded-xl" aria-label="Home">
        <img src="/logo.png" alt="Prapthi Ai" className="h-9 w-9 rounded-lg bg-white object-contain p-0.5 shadow-[0_4px_16px_-6px_var(--color-accent)] ring-1 ring-[var(--color-accent)]/30" />
      </button>

      <div className="my-1 h-px w-8 bg-[var(--color-border)]" />

      <nav className="flex min-h-0 flex-1 flex-col items-center gap-1 overflow-y-auto py-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {groups.map((g, gi) => (
          <div key={g.label} className="flex flex-col items-center gap-1">
            {gi > 0 && <div className="my-1 h-px w-8 bg-[var(--color-border)]" />}
            {g.items.map((it) => (
              <DockButton key={it.view} icon={it.icon} label={it.label} active={view === it.view} soon={!ready(it.view)} onClick={() => onView(it.view)} />
            ))}
          </div>
        ))}
        <div className="my-1 h-px w-8 bg-[var(--color-border)]" />
        <DockButton icon={AudioLines} label="Voices" onClick={() => openOverlay('voices')} />
        <DockButton icon={SlidersHorizontal} label="Settings" onClick={() => openOverlay('settings')} />
        <DockButton icon={History} label="History" onClick={() => openOverlay('history')} />
      </nav>

      <div className="my-1 h-px w-8 bg-[var(--color-border)]" />
      <div className="relative">
        <button
          onClick={() => setMenu((m) => !m)}
          className="grid h-11 w-11 place-items-center rounded-xl"
          aria-label="Account"
        >
          <span className="grid h-9 w-9 place-items-center rounded-full bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-hover)] text-xs font-bold uppercase text-white">
            {(user ?? '?').slice(0, 1)}
          </span>
        </button>
        {menu && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setMenu(false)} aria-hidden />
            <div className="absolute bottom-0 left-full z-50 ml-3 w-52 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-1.5 shadow-2xl">
              <div className="truncate px-3 py-2 text-xs text-[var(--color-muted)]" title={user ?? ''}>{user ?? 'Signed in'}</div>
              <MenuRow icon={HelpCircle} label="Help" onClick={() => { setMenu(false); navigate('/help'); }} />
              <MenuRow icon={Info} label="About" onClick={() => { setMenu(false); navigate('/about'); }} />
              <div className="my-1 h-px bg-[var(--color-border)]" />
              <MenuRow icon={LogOut} label="Log out" danger onClick={async () => { setMenu(false); await logout(); }} />
            </div>
          </>
        )}
      </div>
    </aside>
  );
}

function MenuRow({ icon: Icon, label, onClick, danger }: { icon: Icon; label: string; onClick: () => void; danger?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
        danger
          ? 'text-[var(--color-muted)] hover:bg-[var(--color-error)]/12 hover:text-[var(--color-error)]'
          : 'text-[var(--color-fg)] hover:bg-[var(--color-surface-2)]'
      }`}
    >
      <Icon size={16} /> {label}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  Mobile menu (labeled drawer)                                       */
/* ------------------------------------------------------------------ */
function MobileMenu({
  open, view, ready, onView, onClose, openOverlay, navigate,
}: {
  open: boolean;
  view: View;
  ready: (v: View) => boolean;
  onView: (v: View) => void;
  onClose: () => void;
  openOverlay: (o: 'voices' | 'settings' | 'history') => void;
  navigate: (p: string) => void;
}) {
  const logout = useStore((s) => s.logout);
  const isAdmin = useStore((s) => s.isAdmin);
  const groups = isAdmin ? [...GROUPS, ADMIN_GROUP] : GROUPS;
  return (
    <div className={`fixed inset-0 z-50 md:hidden ${open ? '' : 'pointer-events-none'}`}>
      <div className={`absolute inset-0 bg-black/60 transition-opacity ${open ? 'opacity-100' : 'opacity-0'}`} onClick={onClose} aria-hidden />
      <aside className={`absolute inset-y-0 left-0 flex w-72 flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)] p-3 transition-transform ${open ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="mb-2 flex items-center justify-between px-1">
          <div className="flex items-center gap-2">
            <img src="/logo.png" alt="" className="h-9 w-9 rounded-lg bg-white object-contain p-0.5" />
            <span className="font-bold tracking-tight">Prapthi Ai</span>
          </div>
          <button onClick={onClose} className="rounded-md p-1.5 text-[var(--color-muted)] hover:bg-[var(--color-surface-2)]"><X size={18} /></button>
        </div>
        <nav className="flex-1 space-y-1 overflow-y-auto">
          {groups.map((g) => (
            <div key={g.label}>
              <p className="px-3 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-[var(--color-muted)]">{g.label}</p>
              {g.items.map((it) => (
                <button key={it.view} onClick={() => onView(it.view)} className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium ${view === it.view ? 'bg-[var(--color-accent)]/12 text-[var(--color-accent)]' : 'text-[var(--color-muted)] hover:bg-[var(--color-surface-2)]'}`}>
                  <it.icon size={18} /> {it.label}
                  {!ready(it.view) && <span className="ml-auto rounded-full bg-[var(--color-surface-2)] px-2 py-0.5 text-[10px] font-semibold text-[var(--color-muted)]">Soon</span>}
                </button>
              ))}
            </div>
          ))}
          <p className="px-3 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-[var(--color-muted)]">Panels</p>
          <button onClick={() => openOverlay('voices')} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-[var(--color-muted)] hover:bg-[var(--color-surface-2)]"><AudioLines size={18} /> Voices</button>
          <button onClick={() => openOverlay('settings')} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-[var(--color-muted)] hover:bg-[var(--color-surface-2)]"><SlidersHorizontal size={18} /> Settings</button>
          <button onClick={() => openOverlay('history')} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-[var(--color-muted)] hover:bg-[var(--color-surface-2)]"><History size={18} /> History</button>
          <button onClick={() => { onClose(); navigate('/help'); }} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-[var(--color-muted)] hover:bg-[var(--color-surface-2)]"><HelpCircle size={18} /> Help</button>
        </nav>
        <button onClick={async () => { onClose(); await logout(); }} className="mt-2 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-[var(--color-muted)] hover:bg-[var(--color-error)]/10 hover:text-[var(--color-error)]">
          <LogOut size={18} /> Log out
        </button>
      </aside>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Floating command bar                                               */
/* ------------------------------------------------------------------ */
function ThemeToggle() {
  const [theme, toggle] = useTheme();
  return (
    <button
      onClick={toggle}
      aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
      className="relative grid h-9 w-9 place-items-center overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-muted)] transition-all hover:border-[var(--color-accent)] hover:text-[var(--color-fg)]"
    >
      <Moon size={16} className={`absolute transition-all duration-500 ${theme === 'dark' ? 'rotate-0 opacity-100' : '-rotate-90 opacity-0'}`} />
      <Sun size={16} className={`absolute transition-all duration-500 ${theme === 'light' ? 'rotate-0 opacity-100' : 'rotate-90 opacity-0'}`} />
    </button>
  );
}

function Topbar({ title, onMenu, onSearch }: { title: string; onMenu: () => void; onSearch: () => void }) {
  const openOverlay = useStore((s) => s.openOverlay);
  return (
    <header className="vf-theme-anim flex items-center gap-3 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)]/80 px-3 py-2.5 shadow-[0_18px_50px_-38px_rgba(0,0,0,0.7)] backdrop-blur-xl md:px-4">
      <button onClick={onMenu} className="rounded-lg p-2 text-[var(--color-muted)] hover:bg-[var(--color-surface-2)] md:hidden" aria-label="Open menu">
        <Menu size={20} />
      </button>

      <div className="min-w-0">
        <p className="text-[10px] font-medium uppercase tracking-[0.22em] text-[var(--color-muted)]">Workspace</p>
        <h1 className="truncate text-base font-semibold tracking-tight">{title}</h1>
      </div>

      <button
        onClick={onSearch}
        className="mx-auto hidden items-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm text-[var(--color-muted)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-fg)] sm:flex"
      >
        <Search size={15} /> Search tools…
        <kbd className="ml-6 rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-1.5 py-0.5 text-[10px] font-semibold">⌘K</kbd>
      </button>

      <div className="ml-auto flex items-center gap-2">
        <span className="hidden items-center gap-1.5 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-xs text-[var(--color-muted)] lg:flex">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-success)]" />
          <AudioLines size={13} /> Prapthi Multilingual v1
        </span>
        <button onClick={onSearch} className="grid h-9 w-9 place-items-center rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-fg)] sm:hidden" aria-label="Search">
          <Search size={16} />
        </button>
        <ThemeToggle />
        <button
          onClick={() => openOverlay('history')}
          className="flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]"
        >
          <History size={15} /> <span className="hidden md:inline">History</span>
        </button>
      </div>
    </header>
  );
}

/* ------------------------------------------------------------------ */
/*  Command palette (⌘K)                                               */
/* ------------------------------------------------------------------ */
function CommandPalette({
  commands, onClose,
}: {
  commands: { icon: Icon; label: string; group: string; run: () => void }[];
  onClose: () => void;
}) {
  const [q, setQ] = useState('');
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const filtered = useMemo(
    () => commands.filter((c) => c.label.toLowerCase().includes(q.toLowerCase()) || c.group.toLowerCase().includes(q.toLowerCase())),
    [commands, q],
  );
  useEffect(() => { inputRef.current?.focus(); }, []);
  useEffect(() => { setActive(0); }, [q]);

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, filtered.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === 'Enter') { e.preventDefault(); filtered[active]?.run(); }
    else if (e.key === 'Escape') { e.preventDefault(); onClose(); }
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-start justify-center bg-black/50 px-4 pt-[14vh] backdrop-blur-sm" onClick={onClose}>
      <div
        className="w-full max-w-lg overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={onKey}
      >
        <div className="flex items-center gap-3 border-b border-[var(--color-border)] px-4">
          <Search size={18} className="text-[var(--color-muted)]" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search tools & actions…"
            className="w-full bg-transparent py-4 text-sm text-[var(--color-fg)] placeholder:text-[var(--color-muted)] focus:outline-none"
          />
          <kbd className="rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--color-muted)]">Esc</kbd>
        </div>
        <ul className="max-h-80 overflow-y-auto p-2">
          {filtered.map((c, i) => (
            <li key={c.label}>
              <button
                onMouseEnter={() => setActive(i)}
                onClick={() => c.run()}
                className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition-colors ${
                  i === active ? 'bg-[var(--color-accent)]/14 text-[var(--color-fg)]' : 'text-[var(--color-muted)] hover:bg-[var(--color-surface-2)]'
                }`}
              >
                <c.icon size={16} className="text-[var(--color-accent)]" />
                <span className="text-[var(--color-fg)]">{c.label}</span>
                <span className="ml-auto text-[11px] uppercase tracking-wide text-[var(--color-muted)]">{c.group}</span>
                {i === active && <CornerDownLeft size={13} className="ml-2 text-[var(--color-muted)]" />}
              </button>
            </li>
          ))}
          {filtered.length === 0 && (
            <li className="px-4 py-6 text-center text-sm text-[var(--color-muted)]">No matches for “{q}”.</li>
          )}
        </ul>
      </div>
    </div>
  );
}

/** Shown in place of a studio whose backend is not switched on yet, so users
 * see a clear message instead of a tool that fails when they use it. */
function ComingSoon({ label }: { label: string }) {
  return (
    <div className="grid h-full min-h-[320px] place-items-center p-8 text-center">
      <div className="max-w-sm">
        <Sparkles size={28} className="mx-auto text-[var(--color-accent)]" />
        <h2 className="mt-4 text-xl font-bold">{label} is coming soon</h2>
        <p className="mt-2 text-sm text-[var(--color-muted)]">
          This studio is being switched on. Everything else in your workspace works as usual.
        </p>
      </div>
    </div>
  );
}
