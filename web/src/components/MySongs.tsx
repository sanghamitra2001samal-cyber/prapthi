import { useEffect, useMemo, useState } from 'react';
import {
  Music, Download, Trash2, Loader2, RefreshCw, Wand2, Scissors, Mic, FileText,
} from 'lucide-react';
import { useStore } from '../state/store';
import * as songApi from '../lib/song';

const STEMS: Array<[string, string]> = [
  ['instrumental', 'Karaoke / Instrumental'],
  ['vocals', 'Vocals only'],
  ['drums', 'Drums'],
  ['bass', 'Bass'],
  ['other', 'Other'],
];

export function MySongs({ onView }: { onView: (v: string) => void }) {
  const toast = useStore((s) => s.toast);
  const [songs, setSongs] = useState<songApi.SongRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<Record<string, boolean>>({});

  const load = async () => {
    setLoading(true);
    try {
      setSongs(await songApi.listSongs());
    } catch (e) {
      toast({ kind: 'error', message: (e as Error).message });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // refresh while anything is still processing (songs or stems)
    const t = window.setInterval(async () => {
      try {
        setSongs(await songApi.listSongs());
      } catch {
        /* ignore */
      }
    }, 5000);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const remove = async (id: string) => {
    if (!confirm('Delete this song?')) return;
    try {
      await songApi.deleteSong(id);
      setSongs((s) => s.filter((x) => x.id !== id));
      toast({ kind: 'info', message: 'Song deleted.' });
    } catch (e) {
      toast({ kind: 'error', message: (e as Error).message });
    }
  };

  const regenerate = async (id: string, newLyrics: boolean) => {
    setBusy((b) => ({ ...b, [id]: true }));
    try {
      await songApi.regenerateSong(id, newLyrics);
      toast({ kind: 'success', message: newLyrics ? 'New lyrics + take started.' : 'New take started.' });
      await load();
    } catch (e) {
      toast({ kind: 'error', message: (e as Error).message });
    } finally {
      setBusy((b) => ({ ...b, [id]: false }));
    }
  };

  const exportStems = async (id: string) => {
    try {
      await songApi.startStems(id);
      toast({ kind: 'info', message: 'Splitting into stems — this takes a minute.' });
      setSongs((s) => s.map((x) => (x.id === id ? { ...x, stems_status: 'processing' } : x)));
    } catch (e) {
      toast({ kind: 'error', message: (e as Error).message });
    }
  };

  // Group songs into version trees: a song's root is its parent_id (the
  // original) or its own id. Each tree shows the original + its takes.
  const trees = useMemo(() => {
    const byRoot = new Map<string, songApi.SongRow[]>();
    for (const s of songs) {
      const root = s.parent_id || s.id;
      (byRoot.get(root) ?? byRoot.set(root, []).get(root)!).push(s);
    }
    const out = [...byRoot.values()].map((group) =>
      [...group].sort(
        (a, b) => (a.created_at ?? '').localeCompare(b.created_at ?? '')
      )
    );
    // newest tree first (by its latest take)
    out.sort((a, b) =>
      (b[b.length - 1].created_at ?? '').localeCompare(a[a.length - 1].created_at ?? '')
    );
    return out;
  }, [songs]);

  const renderSong = (s: songApi.SongRow, take: number, total: number) => (
    <div key={s.id} className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-2 truncate font-semibold">
            {s.title}
            {total > 1 && (
              <span className="shrink-0 rounded-full bg-[var(--color-surface-2)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-muted)]">
                Take {take}
              </span>
            )}
          </p>
          <p className="text-xs capitalize text-[var(--color-muted)]">
            {s.genre} · {s.emotion} · {s.language}
            {s.duration_seconds ? ` · ${s.duration_seconds}s` : ''}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {s.status === 'done' ? (
            <a href={songApi.songAudioUrl(s.id)} download className="rounded-lg p-2 text-[var(--color-muted)] hover:text-[var(--color-fg)]" title="Download MP3">
              <Download size={16} />
            </a>
          ) : s.status === 'failed' ? (
            <span className="text-xs text-[var(--color-error)]">failed</span>
          ) : (
            <span className="flex items-center gap-1 text-xs text-[var(--color-muted)]">
              <Loader2 size={13} className="animate-spin" /> {s.progress}%
            </span>
          )}
          <button onClick={() => remove(s.id)} className="rounded-lg p-2 text-[var(--color-muted)] hover:text-[var(--color-error)]" title="Delete">
            <Trash2 size={16} />
          </button>
        </div>
      </div>

      {s.status === 'done' && (
        <>
          <audio controls src={songApi.songAudioUrl(s.id)} className="mt-3 h-9 w-full" />

          {/* Regenerate + stems actions */}
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              onClick={() => regenerate(s.id, false)}
              disabled={busy[s.id]}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium hover:border-[var(--color-accent)] disabled:opacity-50"
            >
              {busy[s.id] ? <Loader2 size={13} className="animate-spin" /> : <Wand2 size={13} />}
              New take
            </button>
            <button
              onClick={() => regenerate(s.id, true)}
              disabled={busy[s.id]}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium hover:border-[var(--color-accent)] disabled:opacity-50"
              title="Rewrite the lyrics and generate again"
            >
              <FileText size={13} /> New lyrics
            </button>

            {s.stems_status === 'done' ? null : s.stems_status === 'processing' ? (
              <span className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-muted)]">
                <Loader2 size={13} className="animate-spin" /> Splitting stems…
              </span>
            ) : (
              <button
                onClick={() => exportStems(s.id)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium hover:border-[var(--color-accent)]"
              >
                <Scissors size={13} /> Export stems / karaoke
              </button>
            )}
          </div>

          {/* Stem downloads */}
          {s.stems_status === 'done' && (
            <div className="mt-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
              <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-[var(--color-muted)]">
                <Mic size={13} /> Stems
              </p>
              <div className="flex flex-wrap gap-2">
                {STEMS.map(([kind, label]) => (
                  <a
                    key={kind}
                    href={songApi.stemUrl(s.id, kind)}
                    download
                    className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-xs font-medium hover:border-[var(--color-accent)]"
                  >
                    <Download size={12} /> {label}
                  </a>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-6 md:px-8 md:py-8">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Music size={20} className="text-[var(--color-accent)]" />
          <h2 className="text-xl font-bold tracking-tight">My Songs</h2>
        </div>
        <button onClick={load} className="rounded-lg border border-[var(--color-border)] p-2 text-[var(--color-muted)] hover:text-[var(--color-fg)]" aria-label="Refresh">
          <RefreshCw size={16} />
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><Loader2 className="animate-spin text-[var(--color-muted)]" /></div>
      ) : songs.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-[var(--color-border)] py-16 text-center">
          <p className="text-[var(--color-muted)]">No songs yet.</p>
          <button onClick={() => onView('createsong')} className="mt-3 rounded-full bg-[var(--color-accent)] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[var(--color-accent-hover)]">
            Create your first song
          </button>
        </div>
      ) : (
        <div className="space-y-5">
          {trees.map((group) => (
            <div
              key={group[0].id}
              className={group.length > 1 ? 'space-y-2 rounded-2xl border border-[var(--color-border)]/60 p-2' : ''}
            >
              {group.map((s, i) => renderSong(s, i + 1, group.length))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
