import { useMemo } from 'react';
import { useStore } from '../state/store';
import { Button } from './ui/Button';
import { wordCount } from '../lib/sanitize';

export function TransportBar() {
  const status = useStore((s) => s.status);
  const text = useStore((s) => s.text);
  const highlightIndex = useStore((s) => s.highlightIndex);
  const play = useStore((s) => s.play);
  const pause = useStore((s) => s.pause);
  const resume = useStore((s) => s.resume);
  const stop = useStore((s) => s.stop);
  const openOverlay = useStore((s) => s.openOverlay);
  const lastGen = useStore((s) => s.lastGen);

  const hasText = text.trim().length > 0;
  const total = useMemo(() => wordCount(text), [text]);
  const progress =
    status === 'idle' || highlightIndex == null || total === 0
      ? 0
      : Math.min(100, ((highlightIndex + 1) / total) * 100);

  const statusLabel =
    status === 'playing'
      ? 'Playing'
      : status === 'paused'
        ? 'Paused'
        : status === 'loading'
          ? 'Preparing…'
          : 'Ready';

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
      <div className="flex flex-wrap items-center gap-2">
        {status === 'playing' ? (
          <Button variant="primary" onClick={pause}>
            ⏸ Pause
          </Button>
        ) : status === 'paused' ? (
          <Button variant="primary" onClick={resume}>
            ▶ Resume
          </Button>
        ) : (
          <Button
            variant="primary"
            onClick={play}
            loading={status === 'loading'}
            disabled={!hasText}
            disabledReason="Add some text first"
          >
            ▶ Play
          </Button>
        )}

        <Button
          variant="secondary"
          onClick={stop}
          disabled={status === 'idle' || status === 'loading'}
          disabledReason="Nothing is playing"
        >
          ⏹ Stop
        </Button>

        <div className="mx-1 hidden flex-1 sm:block">
          <div
            className="h-2 overflow-hidden rounded-full bg-[var(--color-surface-2)]"
            role="progressbar"
            aria-valuenow={Math.round(progress)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Playback progress"
          >
            <div
              className="h-full rounded-full bg-[var(--color-accent)] transition-[width] duration-150"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        <Button
          variant="secondary"
          onClick={() => openOverlay('export')}
          disabled={!lastGen}
          disabledReason="Press Play first to generate audio"
        >
          ⬇ Export
        </Button>
      </div>

      <div className="mt-2 flex items-center justify-between text-xs text-[var(--color-muted)]">
        <span aria-live="polite">{statusLabel}</span>
        {lastGen && status === 'idle' && (
          <span className="text-[var(--color-success)]">Ready to export</span>
        )}
      </div>
    </div>
  );
}
