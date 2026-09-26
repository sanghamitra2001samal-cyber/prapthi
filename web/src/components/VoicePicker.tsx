import { useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useStore } from '../state/store';
import { Overlay } from './ui/Overlay';
import { langLabel } from '../lib/langNames';

const CLONE_LANGS: [string, string][] = [
  ['en', 'English'], ['hi', 'Hindi'], ['es', 'Spanish'], ['fr', 'French'],
  ['de', 'German'], ['it', 'Italian'], ['pt', 'Portuguese'], ['ru', 'Russian'],
  ['zh', 'Chinese'], ['ja', 'Japanese'], ['ko', 'Korean'], ['ar', 'Arabic'],
  ['tr', 'Turkish'], ['pl', 'Polish'], ['nl', 'Dutch'], ['sv', 'Swedish'],
  ['da', 'Danish'], ['no', 'Norwegian'], ['fi', 'Finnish'], ['el', 'Greek'],
  ['he', 'Hebrew'], ['ms', 'Malay'], ['sw', 'Swahili'],
];

export function VoicePicker() {
  const open = useStore((s) => s.overlay === 'voices');
  const close = useStore((s) => s.closeOverlay);
  const voices = useStore((s) => s.voices);
  const voiceId = useStore((s) => s.voiceId);
  const setVoice = useStore((s) => s.setVoice);
  const preview = useStore((s) => s.preview);
  const toast = useStore((s) => s.toast);
  const createClone = useStore((s) => s.createClone);
  const createIF5Clone = useStore((s) => s.createIF5Clone);
  const deleteClone = useStore((s) => s.deleteClone);

  const [query, setQuery] = useState('');
  const [gender, setGender] = useState<'all' | 'male' | 'female'>('all');
  const [lang, setLang] = useState('all');
  const [downloadableOnly, setDownloadableOnly] = useState(false);

  // Voice cloning form
  const [cloneOpen, setCloneOpen] = useState(false);
  const [cloneName, setCloneName] = useState('');
  const [cloneLang, setCloneLang] = useState('en');
  const [cloneEngine, setCloneEngine] = useState<'expressive' | 'indic'>('expressive');
  const [cloneBusy, setCloneBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const onUpload = async () => {
    const f = fileRef.current?.files?.[0];
    if (!cloneName.trim()) {
      toast({ kind: 'error', message: 'Give your voice a name.' });
      return;
    }
    if (!f) {
      toast({ kind: 'error', message: 'Choose an audio file (5–30s).' });
      return;
    }
    setCloneBusy(true);
    const r =
      cloneEngine === 'indic'
        ? await createIF5Clone(cloneName.trim(), f)
        : await createClone(cloneName.trim(), cloneLang, f);
    setCloneBusy(false);
    if (r.ok) {
      toast({ kind: 'success', message: 'Voice cloned! It’s in the list below.' });
      setCloneName('');
      if (fileRef.current) fileRef.current.value = '';
      setCloneOpen(false);
    } else {
      toast({ kind: 'error', message: r.error ?? 'Clone failed.' });
    }
  };

  const langs = useMemo(
    () =>
      Array.from(new Set(voices.map((v) => v.lang.split('-')[0]))).sort((a, b) =>
        langLabel(a).localeCompare(langLabel(b))
      ),
    [voices]
  );

  const filtered = voices.filter((v) => {
    if (query && !v.name.toLowerCase().includes(query.toLowerCase()))
      return false;
    if (gender !== 'all' && v.gender !== gender) return false;
    if (lang !== 'all' && !v.lang.startsWith(lang)) return false;
    if (downloadableOnly && !v.downloadable) return false;
    return true;
  });

  const clearFilters = () => {
    setQuery('');
    setGender('all');
    setLang('all');
    setDownloadableOnly(false);
  };

  const chip = (active: boolean) =>
    `rounded-full border px-3 py-1 text-xs ${
      active
        ? 'border-[var(--color-accent)] bg-[var(--color-accent)]/20 text-[var(--color-accent)]'
        : 'border-[var(--color-border)] text-[var(--color-muted)] hover:text-[var(--color-fg)]'
    }`;

  return (
    <Overlay open={open} onClose={close} title="Choose a voice">
      <input
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search voices by name…"
        aria-label="Search voices"
        className="mb-3 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm focus:outline-none"
      />

      <div className="mb-4 flex flex-wrap gap-2">
        <button className={chip(downloadableOnly)} onClick={() => setDownloadableOnly((v) => !v)}>
          ⬇ Downloadable
        </button>
        <button className={chip(gender === 'male')} onClick={() => setGender(gender === 'male' ? 'all' : 'male')}>
          Male
        </button>
        <button className={chip(gender === 'female')} onClick={() => setGender(gender === 'female' ? 'all' : 'female')}>
          Female
        </button>
        <select
          value={lang}
          onChange={(e) => setLang(e.target.value)}
          aria-label="Filter by language"
          className={chip(lang !== 'all')}
        >
          <option value="all">All languages</option>
          {langs.map((l) => (
            <option key={l} value={l}>
              {langLabel(l)}
            </option>
          ))}
        </select>
      </div>

      {/* Clone a voice */}
      <div className="mb-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)]/40">
        <button
          onClick={() => setCloneOpen((v) => !v)}
          className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium"
        >
          <span>✨ Clone a voice</span>
          <span className="text-[var(--color-muted)]">{cloneOpen ? '−' : '+'}</span>
        </button>
        {cloneOpen && (
          <div className="space-y-2 border-t border-[var(--color-border)] p-3">
            <p className="text-xs text-[var(--color-muted)]">
              Upload a clean 5–30s audio sample of one speaker. Only upload voices
              you have the right to use.
            </p>
            <input
              type="text"
              value={cloneName}
              onChange={(e) => setCloneName(e.target.value)}
              placeholder="Voice name (e.g. My Brand Voice)"
              className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm focus:outline-none"
            />
            <select
              value={cloneEngine}
              onChange={(e) => setCloneEngine(e.target.value as 'expressive' | 'indic')}
              aria-label="Clone engine"
              className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm focus:outline-none"
            >
              <option value="expressive">Prapthi Expressive — 23 languages</option>
              <option value="indic">Prapthi Indic HD — 11 Indian languages</option>
            </select>
            {cloneEngine === 'expressive' && (
              <select
                value={cloneLang}
                onChange={(e) => setCloneLang(e.target.value)}
                aria-label="Clone language"
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm focus:outline-none"
              >
                {CLONE_LANGS.map(([c, n]) => (
                  <option key={c} value={c}>
                    {n}
                  </option>
                ))}
              </select>
            )}
            {cloneEngine === 'indic' && (
              <p className="text-xs text-[var(--color-muted)]">
                Speaks Hindi, Tamil, Telugu, Kannada, Malayalam, Bengali, Marathi,
                Gujarati, Punjabi, Odia & Assamese in the cloned voice. The clip is
                auto-transcribed for you.
              </p>
            )}
            <input
              ref={fileRef}
              type="file"
              accept="audio/*"
              className="w-full text-xs text-[var(--color-muted)] file:mr-3 file:rounded-md file:border-0 file:bg-[var(--color-surface)] file:px-3 file:py-1.5 file:text-[var(--color-fg)]"
            />
            <button
              onClick={onUpload}
              disabled={cloneBusy}
              className="w-full rounded-lg bg-[var(--color-accent)] px-3 py-2 text-sm font-medium text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-60"
            >
              {cloneBusy ? 'Cloning…' : 'Create cloned voice'}
            </button>
          </div>
        )}
      </div>

      {filtered.length === 0 ? (
        <div className="py-10 text-center text-sm text-[var(--color-muted)]">
          {voices.length === 0 ? (
            <p>
              No voices available in this browser. The downloadable voice still
              works for export once the server is running.
            </p>
          ) : (
            <>
              <p>No voices match. Clear filters to see all voices.</p>
              <button
                className="mt-3 text-[var(--color-accent)] hover:underline"
                onClick={clearFilters}
              >
                Clear filters
              </button>
            </>
          )}
        </div>
      ) : (
        <ul className="flex flex-col gap-1">
          {filtered.map((v) => {
            const selected = v.id === voiceId;
            return (
              <li
                key={v.id}
                className={`flex items-center gap-2 rounded-lg border px-3 py-2 ${
                  selected
                    ? 'border-[var(--color-accent)] bg-[var(--color-accent)]/10'
                    : 'border-transparent hover:bg-[var(--color-surface-2)]'
                }`}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium">{v.name}</span>
                    {selected && <span className="text-[var(--color-accent)]">✓</span>}
                  </div>
                  <div className="flex items-center gap-2 text-xs text-[var(--color-muted)]">
                    <span>{langLabel(v.lang)}</span>
                    {/* Say up front which voices the plan does not cover, so
                        nobody discovers it by having a render refused. */}
                    {v.locked && (
                      <Link
                        to="/pricing"
                        title="Included with Mid and Elite"
                        className="rounded bg-[var(--color-warning)]/20 px-1.5 text-[10px] font-semibold text-[var(--color-warning)] hover:underline"
                      >
                        🔒 PAID PLAN
                      </Link>
                    )}
                    {v.downloadable && (
                      <span className="rounded bg-[var(--color-accent)]/20 px-1.5 text-[10px] font-semibold text-[var(--color-accent)]">
                        DOWNLOADABLE
                      </span>
                    )}
                  </div>
                </div>
                {v.clone && (
                  <button
                    aria-label={`Delete ${v.name}`}
                    title="Delete cloned voice"
                    className="rounded-md p-2 text-[var(--color-muted)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-error)]"
                    onClick={async () => {
                      await deleteClone(v.id);
                      toast({ kind: 'info', message: `Deleted ${v.name}.` });
                    }}
                  >
                    🗑
                  </button>
                )}
                <button
                  aria-label={`Preview ${v.name}`}
                  className="rounded-md p-2 text-[var(--color-muted)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-fg)]"
                  onClick={() => preview(v.id)}
                >
                  ▶
                </button>
                <button
                  className="rounded-md bg-[var(--color-accent)] px-3 py-1.5 text-xs font-medium text-white hover:bg-[var(--color-accent-hover)]"
                  onClick={() => {
                    setVoice(v.id);
                    toast({ kind: 'success', message: `Voice set to ${v.name}.` });
                    close();
                  }}
                >
                  Select
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </Overlay>
  );
}
