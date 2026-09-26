import { useEffect, useState } from 'react';
import { RefreshCw, Users, ShieldCheck, LogIn, XCircle } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';

type UserRow = {
  id: number;
  email: string;
  is_verified: boolean;
  is_admin: boolean;
  created_at: string | null;
  last_login_at: string | null;
  login_count: number;
  failed_count: number;
  last_ip: string | null;
  clones: number;
  songs: number;
};
type EventRow = {
  email: string;
  success: boolean;
  ip: string | null;
  user_agent: string | null;
  created_at: string | null;
};
type Overview = {
  stats: {
    total_users: number;
    verified_users: number;
    active_users: number;
    total_logins: number;
    failed_logins: number;
  };
  users: UserRow[];
  events: EventRow[];
};

function fmt(ts: string | null): string {
  if (!ts) return '—';
  const d = new Date(ts);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
}

export function AdminPanel() {
  const [data, setData] = useState<Overview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'users' | 'logins'>('users');

  const load = async () => {
    setLoading(true);
    setErr(null);
    try {
      const res = await fetch(`${API_BASE}/admin/overview`, { credentials: 'include' });
      if (res.status === 403) throw new Error('Your account is not an administrator.');
      if (res.status === 401) throw new Error('Please sign in again.');
      if (!res.ok) throw new Error(`Request failed (${res.status}).`);
      setData((await res.json()) as Overview);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to load.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const stat = data?.stats;

  return (
    <div className="mx-auto w-full max-w-6xl px-1 py-2">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-[var(--color-fg)]">Users &amp; Logins</h1>
          <p className="text-sm text-[var(--color-muted)]">Everyone registered, and who has signed in.</p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm font-medium hover:bg-[var(--color-surface)] disabled:opacity-50"
        >
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {/* stat cards */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard icon={Users} label="Registered" value={stat?.total_users} />
        <StatCard icon={ShieldCheck} label="Verified" value={stat?.verified_users} />
        <StatCard icon={LogIn} label="Ever logged in" value={stat?.active_users} accent />
        <StatCard icon={LogIn} label="Logins (tracked)" value={stat?.total_logins} />
        <StatCard icon={XCircle} label="Failed logins" value={stat?.failed_logins} danger />
      </div>

      {/* tabs */}
      <div className="mb-3 flex gap-2">
        {(['users', 'logins'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-full px-4 py-1.5 text-sm font-medium ${
              tab === t
                ? 'bg-[var(--color-accent)] text-white'
                : 'border border-[var(--color-border)] text-[var(--color-muted)] hover:text-[var(--color-fg)]'
            }`}
          >
            {t === 'users' ? 'All users' : 'Recent logins'}
          </button>
        ))}
      </div>

      {err && (
        <div className="rounded-lg border border-[var(--color-error)]/40 bg-[var(--color-error)]/10 px-4 py-3 text-sm text-[var(--color-error)]">
          {err}
        </div>
      )}
      {loading && !data && <p className="py-8 text-center text-sm text-[var(--color-muted)]">Loading…</p>}

      {data && tab === 'users' && (
        <div className="overflow-x-auto rounded-xl border border-[var(--color-border)]">
          <table className="w-full min-w-[820px] text-left text-sm">
            <thead className="bg-[var(--color-surface-2)] text-xs uppercase tracking-wide text-[var(--color-muted)]">
              <tr>
                <Th>Email</Th><Th>Status</Th><Th>Signed up</Th><Th>Last login</Th>
                <Th right>Logins</Th><Th right>Failed</Th><Th>Last IP</Th><Th right>Songs</Th><Th right>Clones</Th>
              </tr>
            </thead>
            <tbody>
              {data.users.map((u) => (
                <tr key={u.id} className="border-t border-[var(--color-border)] hover:bg-[var(--color-surface-2)]/50">
                  <Td>
                    <span className="font-medium text-[var(--color-fg)]">{u.email}</span>
                    {u.is_admin && <span className="ml-2 rounded bg-[var(--color-accent)]/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-[var(--color-accent)]">admin</span>}
                  </Td>
                  <Td>
                    {u.is_verified
                      ? <span className="text-[var(--color-success,#16a34a)]">✓ verified</span>
                      : <span className="text-[var(--color-muted)]">unverified</span>}
                  </Td>
                  <Td muted>{fmt(u.created_at)}</Td>
                  <Td>{u.last_login_at ? fmt(u.last_login_at) : <span className="text-[var(--color-muted)]">never</span>}</Td>
                  <Td right>{u.login_count}</Td>
                  <Td right muted>{u.failed_count}</Td>
                  <Td muted>{u.last_ip ?? '—'}</Td>
                  <Td right>{u.songs}</Td>
                  <Td right>{u.clones}</Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && tab === 'logins' && (
        <div className="overflow-x-auto rounded-xl border border-[var(--color-border)]">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="bg-[var(--color-surface-2)] text-xs uppercase tracking-wide text-[var(--color-muted)]">
              <tr><Th>When</Th><Th>Email</Th><Th>Result</Th><Th>IP</Th><Th>Device</Th></tr>
            </thead>
            <tbody>
              {data.events.length === 0 && (
                <tr><Td muted>No login events recorded yet.</Td><Td /><Td /><Td /><Td /></tr>
              )}
              {data.events.map((e, i) => (
                <tr key={i} className="border-t border-[var(--color-border)] hover:bg-[var(--color-surface-2)]/50">
                  <Td muted>{fmt(e.created_at)}</Td>
                  <Td><span className="font-medium text-[var(--color-fg)]">{e.email}</span></Td>
                  <Td>{e.success
                    ? <span className="text-[var(--color-success,#16a34a)]">✓ success</span>
                    : <span className="text-[var(--color-error)]">✕ failed</span>}</Td>
                  <Td muted>{e.ip ?? '—'}</Td>
                  <Td muted><span className="line-clamp-1 max-w-[260px]" title={e.user_agent ?? ''}>{e.user_agent || '—'}</span></Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="mt-4 text-xs text-[var(--color-muted)]">
        “Last login” is the most recent sign-in (all-time). “Logins / Failed” count events tracked since this
        feature went live. Times shown in your local timezone.
      </p>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, accent, danger }: {
  icon: typeof Users; label: string; value?: number; accent?: boolean; danger?: boolean;
}) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)]/50 p-4">
      <div className="mb-2 flex items-center gap-2 text-[var(--color-muted)]">
        <Icon size={15} className={accent ? 'text-[var(--color-accent)]' : danger ? 'text-[var(--color-error)]' : ''} />
        <span className="text-xs">{label}</span>
      </div>
      <div className={`text-2xl font-bold tabular-nums ${accent ? 'text-[var(--color-accent)]' : 'text-[var(--color-fg)]'}`}>
        {value ?? '—'}
      </div>
    </div>
  );
}

const Th = ({ children, right }: { children?: React.ReactNode; right?: boolean }) => (
  <th className={`px-3 py-2.5 font-semibold ${right ? 'text-right' : ''}`}>{children}</th>
);
const Td = ({ children, right, muted }: { children?: React.ReactNode; right?: boolean; muted?: boolean }) => (
  <td className={`px-3 py-2.5 ${right ? 'text-right tabular-nums' : ''} ${muted ? 'text-[var(--color-muted)]' : ''}`}>{children}</td>
);
