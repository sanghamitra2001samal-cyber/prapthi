import { useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { useStore } from '../state/store';

/* ------------------------------------------------------------------ */
/*  Master control — owner only.                                        */
/*  The server refuses this data to anyone who is not an admin, and     */
/*  answers 404 rather than 403 so an ordinary user never learns the    */
/*  page exists. This component only decides what to draw.              */
/* ------------------------------------------------------------------ */

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';

type Row = Record<string, string | number | boolean | null>;
type Stats = {
  totals: Record<string, number>;
  usage: Record<string, number>;
  plans: Row[];
  signups_daily: { day: string; signups: number }[];
  logins_daily: { day: string; logins: number }[];
  /** Counted from login_events, which only exists from the day it was added. */
  login_totals: { all_time: number; today: number; week: number; month: number;
                  people: number; since: string | null };
  top_users: Row[];
  recent_users: Row[];
  revenue: Record<string, number>;
  recent_payments: Row[];
  clones: number;
  songs: number;
};

const n = (v: unknown) => Number(v ?? 0).toLocaleString('en-IN');

function Card({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="text-xs uppercase tracking-wide text-[var(--color-muted)]">{label}</div>
      <div className="mt-1 text-2xl font-bold tabular-nums">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-[var(--color-muted)]">{sub}</div>}
    </div>
  );
}

/** A dependency-free bar chart — 30 numbers do not justify a charting library. */
function Bars({ data, label }: { data: { day: string; v: number }[]; label: string }) {
  const max = Math.max(1, ...data.map((d) => d.v));
  const total = data.reduce((s, d) => s + d.v, 0);
  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-semibold">{label}</span>
        <span className="text-xs text-[var(--color-muted)]">{n(total)} in 30 days</span>
      </div>
      <div className="mt-3 flex h-24 items-end gap-[3px]">
        {data.map((d) => (
          <div
            key={d.day}
            title={`${d.day}: ${d.v}`}
            className="flex-1 rounded-t bg-[var(--color-accent)]/70 hover:bg-[var(--color-accent)]"
            style={{ height: `${Math.max(2, (d.v / max) * 100)}%` }}
          />
        ))}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-[var(--color-muted)]">
        <span>{data[0]?.day.slice(5)}</span>
        <span>{data[data.length - 1]?.day.slice(5)}</span>
      </div>
    </div>
  );
}

function Table({ title, rows, cols }: { title: string; rows: Row[]; cols: [string, string][] }) {
  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="mb-3 text-sm font-semibold">{title}</div>
      {rows.length === 0 ? (
        <p className="text-sm text-[var(--color-muted)]">Nothing yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-[var(--color-muted)]">
                {cols.map(([, h]) => (
                  <th key={h} className="whitespace-nowrap pb-2 pr-4 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-t border-[var(--color-border)]">
                  {cols.map(([k]) => (
                    <td key={k} className="whitespace-nowrap py-2 pr-4 tabular-nums">
                      {k === 'chars_used' || k === 'chars_allowance' || k === 'amount_paise'
                        ? k === 'amount_paise'
                          ? `₹${n(Number(r[k]) / 100)}`
                          : n(r[k])
                        : r[k] === null
                          ? '—'
                          : String(r[k])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function Admin() {
  const isAdmin = useStore((s) => s.isAdmin);
  const authStatus = useStore((s) => s.authStatus);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!isAdmin) return;
    fetch(`${API_BASE}/admin/stats`, { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then(setStats)
      .catch(() => setError('Could not load the statistics.'));
  }, [isAdmin]);

  if (authStatus === 'loading') return null;
  // Not an admin? This page simply does not exist for you.
  if (!isAdmin) return <Navigate to="/dashboard" replace />;

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-10 md:px-8">
      <h1 className="text-2xl font-bold tracking-tight">Master control</h1>
      <p className="mt-1 text-sm text-[var(--color-muted)]">
        Everyone who has signed up, who is actually using Prapthi, and what has been paid.
      </p>

      {error && <p className="mt-6 text-sm text-[var(--color-error)]">{error}</p>}
      {!stats && !error && (
        <p className="mt-6 text-sm text-[var(--color-muted)]">Loading…</p>
      )}

      {stats && (
        <>
          <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
            <Card label="Total accounts" value={n(stats.totals.users)}
                  sub={`${n(stats.totals.verified)} verified`} />
            <Card label="Have signed in" value={n(stats.totals.ever_logged_in)}
                  sub={`${n(stats.totals.active_week)} in the last 7 days`} />
            <Card label="New this week" value={n(stats.totals.new_week)}
                  sub={`${n(stats.totals.new_today)} today`} />
            <Card label="Active today" value={n(stats.totals.active_today)}
                  sub={`${n(stats.totals.active_month)} this month`} />
            <Card label="Sign-ins" value={n(stats.login_totals.all_time)}
                  sub={stats.login_totals.since
                    ? `${n(stats.login_totals.today)} today · ${n(stats.login_totals.week)} this week · counted since ${stats.login_totals.since}`
                    : 'Counting starts with the next sign-in'} />
            <Card label="Characters generated" value={n(stats.usage.chars_used)}
                  sub={`by ${n(stats.usage.users_who_generated)} accounts`} />
            <Card label="Revenue" value={`₹${n(stats.revenue.paise / 100)}`}
                  sub={`${n(stats.revenue.payments)} payments`} />
            <Card label="Cloned voices" value={n(stats.clones)} />
            <Card label="Songs made" value={n(stats.songs)} />
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <Bars label="Sign-ups per day"
                  data={stats.signups_daily.map((d) => ({ day: d.day, v: d.signups }))} />
            <Bars label="Sign-ins per day"
                  data={stats.logins_daily.map((d) => ({ day: d.day, v: d.logins }))} />
          </div>

          <div className="mt-4">
            <Table title="Plans" rows={stats.plans}
                   cols={[['plan', 'Plan'], ['users', 'Accounts'], ['chars_used', 'Characters used']]} />
          </div>

          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            <Table title="Heaviest users" rows={stats.top_users}
                   cols={[['email', 'Account'], ['plan', 'Plan'], ['chars_used', 'Used'],
                          ['last_login_at', 'Last seen']]} />
            <Table title="Newest sign-ups" rows={stats.recent_users}
                   cols={[['email', 'Account'], ['created_at', 'Signed up'],
                          ['last_login_at', 'Last seen'], ['is_verified', 'Verified']]} />
          </div>

          <div className="mt-4">
            <Table title="Payments" rows={stats.recent_payments}
                   cols={[['created_at', 'When'], ['email', 'Account'], ['plan', 'Plan'],
                          ['amount_paise', 'Amount'], ['source', 'Confirmed by']]} />
          </div>
        </>
      )}
    </div>
  );
}
