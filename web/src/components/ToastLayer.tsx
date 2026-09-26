import { useStore } from '../state/store';

const styles = {
  success: 'border-[var(--color-success)] text-[var(--color-success)]',
  error: 'border-[var(--color-error)] text-[var(--color-error)]',
  info: 'border-[var(--color-border)] text-[var(--color-fg)]',
};

export function ToastLayer() {
  const toasts = useStore((s) => s.toasts);
  const dismiss = useStore((s) => s.dismissToast);

  return (
    <div
      className="pointer-events-none fixed inset-x-0 bottom-6 z-[60] flex flex-col items-center gap-2 px-4"
      aria-live="polite"
      aria-atomic="true"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto flex items-center gap-3 rounded-lg border bg-[var(--color-surface-2)] px-4 py-3 text-sm shadow-lg ${styles[t.kind]}`}
        >
          <span className="text-[var(--color-fg)]">{t.message}</span>
          {t.action && (
            <button
              className="font-semibold text-[var(--color-accent)] hover:underline"
              onClick={() => {
                t.action!.run();
                dismiss(t.id);
              }}
            >
              {t.action.label}
            </button>
          )}
          <button
            aria-label="Dismiss"
            className="text-[var(--color-muted)] hover:text-[var(--color-fg)]"
            onClick={() => dismiss(t.id)}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
