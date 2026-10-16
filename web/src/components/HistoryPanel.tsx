import { useStore } from '../state/store';
import { Overlay } from './ui/Overlay';
import { Button } from './ui/Button';
import { relativeTime } from '../lib/format';

export function HistoryPanel() {
  const open = useStore((s) => s.overlay === 'history');
  const close = useStore((s) => s.closeOverlay);
  const history = useStore((s) => s.history);
  // Show each voice's current name: history stores the name it had when the
  // audio was made, so a renamed voice would otherwise keep its old label.
  const voices = useStore((s) => s.voices);
  const nameOf = (id: string, saved: string) => voices.find((v) => v.id === id)?.name ?? saved;
  const storageOk = useStore((s) => s.storageOk);
  const loadFromHistory = useStore((s) => s.loadFromHistory);
  const deleteHistory = useStore((s) => s.deleteHistory);
  const clearHistory = useStore((s) => s.clearHistory);
  const openOverlay = useStore((s) => s.openOverlay);

  return (
    <Overlay
      open={open}
      onClose={close}
      title="History"
      kind="drawer"
      footer={
        history.length > 0 ? (
          <Button
            variant="ghost"
            onClick={() => {
              if (confirm('Clear all history?')) clearHistory();
            }}
          >
            Clear all
          </Button>
        ) : undefined
      }
    >
      {!storageOk && (
        <div className="mb-3 rounded-lg border border-[var(--color-warning)] bg-[var(--color-warning)]/10 p-3 text-xs text-[var(--color-warning)]">
          Can't save history in this browser (storage blocked). Generations still
          work for this session.
        </div>
      )}

      {history.length === 0 ? (
        <div className="py-16 text-center text-sm text-[var(--color-muted)]">
          <div className="mb-3 text-4xl" aria-hidden>
            🗒️
          </div>
          <p>Your recent voiceovers will appear here.</p>
          <button
            className="mt-3 text-[var(--color-accent)] hover:underline"
            onClick={close}
          >
            Go to editor
          </button>
        </div>
      ) : (
        <ul className="flex flex-col gap-2">
          {history.map((h) => (
            <li
              key={h.id}
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3"
            >
              <button
                className="block w-full text-left"
                onClick={() => loadFromHistory(h.id, false)}
                title="Load into editor"
              >
                <p className="line-clamp-2 text-sm">{h.text}</p>
                <p className="mt-1 text-xs text-[var(--color-muted)]">
                  {nameOf(h.voiceId, h.voiceName)} · {relativeTime(h.createdAt)}
                </p>
              </button>
              <div className="mt-2 flex gap-2">
                <button
                  className="text-xs text-[var(--color-accent)] hover:underline"
                  onClick={() => loadFromHistory(h.id, true)}
                >
                  Replay
                </button>
                <button
                  className="text-xs text-[var(--color-accent)] hover:underline"
                  onClick={() => {
                    loadFromHistory(h.id, false);
                    openOverlay('export');
                  }}
                >
                  Re-export
                </button>
                <button
                  className="ml-auto text-xs text-[var(--color-error)] hover:underline"
                  onClick={() => deleteHistory(h.id)}
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Overlay>
  );
}
