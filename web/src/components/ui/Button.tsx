import type { ButtonHTMLAttributes, ReactNode } from 'react';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  loading?: boolean;
  /** Reason shown as tooltip when disabled (Website Flow §14 — no dead controls). */
  disabledReason?: string;
  children: ReactNode;
}

const base =
  'inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50';

const variants: Record<Variant, string> = {
  primary:
    'bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)]',
  secondary:
    'border border-[var(--color-border)] bg-transparent text-[var(--color-fg)] hover:bg-[var(--color-surface-2)]',
  ghost: 'bg-transparent text-[var(--color-muted)] hover:text-[var(--color-fg)]',
  danger: 'bg-[var(--color-error)] text-white hover:opacity-90',
};

export function Button({
  variant = 'secondary',
  loading,
  disabled,
  disabledReason,
  children,
  className = '',
  ...rest
}: Props) {
  const isDisabled = disabled || loading;
  return (
    <button
      className={`${base} ${variants[variant]} ${className}`}
      disabled={isDisabled}
      title={isDisabled && disabledReason ? disabledReason : undefined}
      aria-disabled={isDisabled || undefined}
      {...rest}
    >
      {loading && (
        <span
          className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white"
          aria-hidden
        />
      )}
      {children}
    </button>
  );
}
