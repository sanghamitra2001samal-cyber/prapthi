import type { ReactNode } from 'react';
import { useOverlayA11y } from './useOverlayA11y';

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** 'modal' centers; 'drawer' slides from the right. */
  kind?: 'modal' | 'drawer';
  footer?: ReactNode;
}

export function Overlay({
  open,
  onClose,
  title,
  children,
  kind = 'modal',
  footer,
}: Props) {
  const ref = useOverlayA11y(open, onClose);
  if (!open) return null;

  const panel =
    kind === 'drawer'
      ? 'ml-auto h-full w-full max-w-md border-l border-[var(--color-border)]'
      : 'm-auto w-full max-w-2xl rounded-2xl border border-[var(--color-border)]';

  return (
    <div
      className="fixed inset-0 z-50 flex bg-black/60 backdrop-blur-sm"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`flex flex-col bg-[var(--color-surface)] shadow-2xl ${panel} ${
          kind === 'modal' ? 'max-h-[85vh]' : ''
        } md:m-auto max-md:m-0 max-md:h-full max-md:w-full max-md:max-w-none max-md:rounded-none`}
      >
        <header className="flex items-center justify-between border-b border-[var(--color-border)] px-5 py-4">
          <h2 className="text-base font-semibold">{title}</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-md p-1 text-[var(--color-muted)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-fg)]"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path
                d="M6 6l12 12M18 6L6 18"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && (
          <footer className="border-t border-[var(--color-border)] px-5 py-3">
            {footer}
          </footer>
        )}
      </div>
    </div>
  );
}
