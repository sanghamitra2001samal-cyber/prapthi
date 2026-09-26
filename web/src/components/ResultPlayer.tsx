import { useStore } from '../state/store';
import { relativeTime } from '../lib/format';

/** Inline player for the most recent generated audio (server voices): replay,
 * scrub/seek, volume via the native controls, plus a one-click download — no
 * need to re-generate to hear it again. */
export function ResultPlayer() {
  const url = useStore((s) => s.lastAudioUrl);
  const filename = useStore((s) => s.lastAudioFilename);
  const lastGen = useStore((s) => s.lastGen);

  if (!url || !lastGen) return null;

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
            Latest result
          </p>
          <p className="truncate text-sm font-medium">
            {lastGen.voiceName}
            <span className="text-[var(--color-muted)]">
              {' '}· {relativeTime(lastGen.createdAt)}
            </span>
          </p>
        </div>
        <a
          href={url}
          download={filename ?? 'ayaanvoice.wav'}
          className="shrink-0 rounded-lg bg-[var(--color-accent)] px-3 py-2 text-sm font-medium text-white hover:bg-[var(--color-accent-hover)]"
        >
          ⬇ Download
        </a>
      </div>
      <audio
        controls
        src={url}
        className="w-full"
        aria-label="Generated audio result"
      />
      <p className="mt-1 line-clamp-1 text-xs text-[var(--color-muted)]">
        “{lastGen.text}”
      </p>
    </div>
  );
}
