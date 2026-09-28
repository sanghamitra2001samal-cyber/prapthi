import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useStore } from '../state/store';

/* ------------------------------------------------------------------ */
/*  How many characters are left this month.                           */
/*                                                                      */
/*  Sits above the editor so nobody discovers their limit by having a   */
/*  generation refused. It re-reads after every generation, because the */
/*  number changes as you work.                                         */
/*  The owner has no allowance, so it shows nothing for them.           */
/* ------------------------------------------------------------------ */

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';

type Account = {
  plan?: string;
  chars_allowance?: number | null;
  chars_used?: number;
  expires_at?: string | null;
};

const inr = (n: number) => n.toLocaleString('en-IN');

export function AllowanceBar() {
  const user = useStore((s) => s.user);
  const status = useStore((s) => s.status);
  const [account, setAccount] = useState<Account | null>(null);

  const refresh = () =>
    fetch(`${API_BASE}/billing/plans`, { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setAccount(d.account ?? null))
      .catch(() => {});

  useEffect(() => { if (user) void refresh(); }, [user]);
  // after a generation finishes, the count has moved — pick it up
  useEffect(() => { if (user && status === 'idle') void refresh(); }, [status, user]);

  if (!user || !account) return null;
  // The owner is not metered; a bar reading "0 of nothing" would be nonsense.
  if (account.plan === 'owner' || account.chars_allowance == null) return null;

  const allowance = account.chars_allowance ?? 0;
  const used = Math.min(account.chars_used ?? 0, allowance);
  const left = Math.max(allowance - used, 0);
  const pct = allowance > 0 ? Math.min((used / allowance) * 100, 100) : 0;

  // Warn before it bites, not after.
  const low = left <= allowance * 0.1;
  const empty = left === 0;
  const colour = empty
    ? 'var(--color-error)'
    : low
      ? 'var(--color-warning)'
      : 'var(--color-accent)';

  return (
    <div className="shrink-0 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2">
      <div className="flex items-baseline justify-between gap-3 text-xs">
        <span className="text-[var(--color-muted)]">
          {empty ? (
            <span className="font-medium text-[var(--color-error)]">
              You have used all your characters this month.
            </span>
          ) : (
            <>
              <span className="font-semibold text-[var(--color-fg)]">{inr(left)}</span>
              <span> characters left</span>
            </>
          )}
        </span>
        <span className="flex items-center gap-2 text-[var(--color-muted)]">
          <span className="tabular-nums">{inr(used)} / {inr(allowance)}</span>
          {(low || empty) && (
            <Link
              to="/pricing"
              className="font-semibold text-[var(--color-accent)] hover:underline"
            >
              Get more
            </Link>
          )}
        </span>
      </div>
      <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-surface-2)]">
        <div
          className="h-full rounded-full transition-[width] duration-500"
          style={{ width: `${pct}%`, background: colour }}
        />
      </div>
    </div>
  );
}
