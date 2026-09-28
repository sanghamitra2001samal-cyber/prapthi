import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, Check, Loader2, Sparkles } from 'lucide-react';
import { useStore } from '../state/store';

/* ------------------------------------------------------------------ */
/*  Pricing — plans come from the server so the page can never quote a  */
/*  price the backend would not charge. Checkout runs through Razorpay; */
/*  the plan is granted only after the server verifies the payment      */
/*  signature, never on this page's say-so.                            */
/*                                                                      */
/*  Copy, plan features and CTA wording are kept identical to           */
/*  prapthi.ai/pricing.html — a customer must not meet two different    */
/*  descriptions of the same plan.                                      */
/* ------------------------------------------------------------------ */

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';
const SITE = 'https://prapthi.ai';

type Plan = {
  id: string; name: string; price: number; chars: number; blurb: string;
};
type Account = {
  plan?: string;
  /** null for the owner, who has no allowance to spend */
  chars_allowance?: number | null;
  chars_used?: number;
  expires_at?: string | null;
};

const inr = (n: number) => n.toLocaleString('en-IN');

/** Exactly what the public pricing page promises for each plan. */
const FEATURES: Record<string, string[]> = {
  free: [
    '12,000 characters / month',
    '30+ standard voices',
    'MP3 downloads',
    'Community support',
  ],
  mid: [
    '35,000 characters / month',
    'All 280+ premium voices',
    'Voice cloning (3 voices)',
    'WAV + MP3, commercial rights',
    'Priority rendering',
  ],
  elite: [
    '300,000 characters / month',
    'All 280+ premium voices',
    'Voice cloning (10 voices)',
    'WAV + MP3, commercial rights',
    'Priority rendering',
  ],
};

/** The site's own button wording, so both pages read the same. */
const CTA: Record<string, string> = {
  free: 'Start Free', mid: 'Get Mid', elite: 'Unlock Elite',
};

const FAQ: [string, string][] = [
  ['Is the free plan really free forever?',
    'Yes. The Free plan gives you 12,000 characters every month with no credit card and no expiry. Upgrade only when you need more.'],
  ['Do I own the audio I generate?',
    'On paid plans you get full commercial rights to everything you generate — use it in videos, ads, products and client work.'],
  ['How does voice cloning work?',
    'Upload a short clean recording (about 30 seconds). We filter background noise automatically and build a private clone only you can use.'],
  ['Can I self-host Prapthi.ai?',
    'Yes — Enterprise runs entirely on your own GPUs, so your scripts, voices and audio never touch a third-party API.'],
  ['Can I cancel anytime?',
    'Absolutely. Cancel in one click from your dashboard and keep access until the end of your billing period.'],
];

declare global {
  interface Window { Razorpay?: new (o: Record<string, unknown>) => { open: () => void } }
}

/** Load Razorpay's checkout script once, on demand. */
function loadCheckout(): Promise<boolean> {
  if (window.Razorpay) return Promise.resolve(true);
  return new Promise((resolve) => {
    const s = document.createElement('script');
    s.src = 'https://checkout.razorpay.com/v1/checkout.js';
    s.onload = () => resolve(true);
    s.onerror = () => resolve(false);
    document.body.appendChild(s);
  });
}

export default function Pricing() {
  const user = useStore((s) => s.user);
  const toast = useStore((s) => s.toast);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [account, setAccount] = useState<Account | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = () =>
    fetch(`${API_BASE}/billing/plans`, { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!d) return;
        setPlans(d.plans ?? []);
        setEnabled(Boolean(d.enabled));
        setAccount(d.account ?? null);
      })
      .catch(() => {});

  useEffect(() => { void refresh(); }, [user]);

  const buy = async (plan: Plan) => {
    if (!user) { toast({ kind: 'error', message: 'Please sign in first.' }); return; }
    if (!enabled) {
      toast({ kind: 'error', message: 'Payments are not switched on yet.' });
      return;
    }
    setBusy(plan.id);
    try {
      const res = await fetch(`${API_BASE}/billing/order`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ plan: plan.id }),
      });
      const order = await res.json();
      if (!res.ok) throw new Error(order?.error || 'Could not start payment');
      if (!(await loadCheckout())) throw new Error('Could not load checkout');

      const rzp = new window.Razorpay!({
        key: order.key_id,
        order_id: order.order_id,
        amount: order.amount,
        currency: order.currency,
        name: 'Prapthi AI',
        // Razorpay shows a placeholder initial without this; a small square
        // copy of the logo keeps the modal on-brand without a slow download.
        image: `${window.location.origin}${import.meta.env.BASE_URL}checkout-logo.png`,
        description: `${order.name} plan — ${inr(plan.chars)} characters a month`,
        prefill: { email: user },   // store keeps the signed-in email as a string
        theme: { color: '#064eff' },
        // The server re-computes the signature before granting anything.
        handler: async (resp: Record<string, string>) => {
          try {
            const v = await fetch(`${API_BASE}/billing/verify`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              credentials: 'include',
              body: JSON.stringify(resp),
            });
            const out = await v.json();
            if (!v.ok) throw new Error(out?.error || 'Verification failed');
            setAccount(out.account ?? null);
            toast({ kind: 'success', message: `${order.name} is active.` });
            void refresh();
          } catch (e) {
            // The webhook is the authoritative path and still credits the
            // account, so this is a "check back shortly", not a lost payment.
            toast({
              kind: 'error',
              message: `Payment received — activation is taking a moment. ${(e as Error).message}`,
            });
          }
        },
        modal: { ondismiss: () => setBusy(null) },
      });
      rzp.open();
    } catch (e) {
      toast({ kind: 'error', message: (e as Error).message });
    } finally {
      setBusy(null);
    }
  };

  const current = (account?.plan ?? 'free').toLowerCase();
  const allowance = account?.chars_allowance ?? 0;
  const used = Math.min(account?.chars_used ?? 0, allowance);
  const left = Math.max(allowance - used, 0);
  const pct = allowance > 0 ? Math.min((used / allowance) * 100, 100) : 0;
  const renews = account?.expires_at
    ? new Date(account.expires_at).toLocaleDateString('en-IN',
        { day: 'numeric', month: 'short', year: 'numeric' })
    : null;

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-14 md:px-8">
      {/* ---------------------------------------------------------- head */}
      <div className="text-center">
        <span className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--color-accent)]">
          Pricing
        </span>
        <h1 className="mt-3 text-4xl font-bold tracking-tight md:text-5xl">
          Simple pricing that scales with you.
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-[var(--color-muted)]">
          Start free. Upgrade when you need more characters, premium voices and
          commercial rights.
        </p>
      </div>

      {/* ------------------------------------------- what you have left */}
      {account && current === 'owner' && (
        <div className="mx-auto mt-9 max-w-lg rounded-2xl border border-[var(--color-accent)] bg-[var(--color-surface)] p-5 text-center">
          <div className="text-sm font-semibold">Owner account</div>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            Every voice and format, with no character limit. Plans below are what
            your customers see.
          </p>
        </div>
      )}

      {account && current !== 'owner' && (
        <div className="mx-auto mt-9 max-w-lg rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-sm text-[var(--color-muted)]">
              Your plan
              <span className="ml-2 rounded-full bg-[var(--color-accent)]/10 px-2.5 py-0.5 text-xs font-semibold capitalize text-[var(--color-accent)]">
                {current === 'free' ? 'No Cap' : current}
              </span>
            </span>
            <span className="text-sm font-semibold">
              {inr(left)} <span className="font-normal text-[var(--color-muted)]">left</span>
            </span>
          </div>
          <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-surface-2)]">
            <div
              className="h-full rounded-full bg-[var(--color-accent)] transition-[width] duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
          <p className="mt-2 text-xs text-[var(--color-muted)]">
            {inr(used)} of {inr(allowance)} characters used this month
            {renews && ` · renews ${renews}`}
          </p>
        </div>
      )}

      {!enabled && (
        <p className="mx-auto mt-6 max-w-xl rounded-xl border border-[var(--color-warning)]/40 bg-[var(--color-warning)]/10 px-4 py-3 text-center text-sm text-[var(--color-warning)]">
          Payments are not switched on yet — plans are shown for reference.
        </p>
      )}

      {/* --------------------------------------------------------- plans */}
      <div className="mt-10 grid grid-cols-1 items-stretch gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {plans.map((p) => {
          const isCurrent = p.id === current;
          const featured = p.id === 'mid';
          return (
            <div
              key={p.id}
              className={`relative flex flex-col rounded-2xl border p-6 transition-shadow ${
                featured
                  ? 'border-[var(--color-accent)] bg-[var(--color-surface)] shadow-xl shadow-[var(--color-accent)]/10 lg:-mt-3 lg:mb-[-0.75rem]'
                  : 'border-[var(--color-border)] bg-[var(--color-surface)] hover:shadow-lg'
              }`}
            >
              {featured && (
                <span className="absolute -top-3 left-6 inline-flex items-center gap-1 rounded-full bg-[var(--color-accent)] px-2.5 py-1 text-[11px] font-semibold text-white shadow-sm">
                  <Sparkles size={11} /> Most popular
                </span>
              )}

              <h2 className="text-lg font-bold">{p.name}</h2>
              <p className="mt-1 min-h-[2.75rem] text-sm leading-snug text-[var(--color-muted)]">
                {p.blurb}
              </p>

              <div className="mt-4 flex items-baseline gap-1 border-b border-[var(--color-border)] pb-5">
                <span className="text-4xl font-bold tracking-tight">₹{inr(p.price)}</span>
                <span className="text-sm text-[var(--color-muted)]">/month</span>
              </div>

              <ul className="mt-5 flex-1 space-y-2.5 text-sm">
                {(FEATURES[p.id] ?? [`${inr(p.chars)} characters / month`]).map((f) => (
                  <li key={f} className="flex gap-2.5">
                    <Check size={15} className="mt-0.5 shrink-0 text-[var(--color-accent)]" />
                    <span className="text-[var(--color-muted)]">{f}</span>
                  </li>
                ))}
              </ul>

              {p.price === 0 ? (
                <Link
                  to={user ? '/dashboard' : '/signup'}
                  className="mt-6 rounded-full border border-[var(--color-border)] px-4 py-2.5 text-center text-sm font-semibold transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]"
                >
                  {isCurrent && user ? 'Current plan'
                    : user ? 'Go to studio'
                    : CTA[p.id] ?? 'Choose'}
                </Link>
              ) : (
                <button
                  onClick={() => void buy(p)}
                  disabled={busy === p.id || isCurrent}
                  className={`mt-6 inline-flex items-center justify-center gap-2 rounded-full px-4 py-2.5 text-sm font-semibold transition-colors disabled:cursor-default disabled:opacity-60 ${
                    featured
                      ? 'bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)]'
                      : 'border border-[var(--color-border)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]'
                  }`}
                >
                  {busy === p.id && <Loader2 size={14} className="animate-spin" />}
                  {isCurrent ? 'Current plan'
                    : busy === p.id ? 'Opening…'
                    : CTA[p.id] ?? 'Choose'}
                </button>
              )}
            </div>
          );
        })}

        {/* Enterprise is a conversation, not a checkout — same as the site. */}
        {plans.length > 0 && (
          <div className="flex flex-col rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-6">
            <h2 className="text-lg font-bold">Custom</h2>
            <p className="mt-1 min-h-[2.75rem] text-sm leading-snug text-[var(--color-muted)]">
              For teams that need scale, privacy and self-hosting.
            </p>
            <div className="mt-4 flex items-baseline border-b border-[var(--color-border)] pb-5">
              <span className="text-3xl font-bold tracking-tight">Contact us</span>
            </div>
            <ul className="mt-5 flex-1 space-y-2.5 text-sm">
              {['Unlimited characters', 'Self-hosted on your GPUs',
                'Unlimited voice clones', 'SSO, audit logs, SLA',
                'Dedicated support'].map((f) => (
                <li key={f} className="flex gap-2.5">
                  <Check size={15} className="mt-0.5 shrink-0 text-[var(--color-accent)]" />
                  <span className="text-[var(--color-muted)]">{f}</span>
                </li>
              ))}
            </ul>
            <a
              href={`${SITE}/about.html#contact`}
              className="mt-6 inline-flex items-center justify-center gap-1.5 rounded-full border border-[var(--color-border)] px-4 py-2.5 text-sm font-semibold transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]"
            >
              Talk to us <ArrowUpRight size={14} />
            </a>
          </div>
        )}
      </div>

      <p className="mt-6 text-center text-xs text-[var(--color-muted)]">
        Prices in Indian rupees, inclusive of applicable taxes. One character of
        text uses one character of your monthly allowance. Allowances renew every
        30 days and unused characters do not roll over.
      </p>

      {/* ----------------------------------------------------------- FAQ */}
      <div className="mx-auto mt-16 max-w-3xl">
        <h2 className="text-center text-2xl font-bold tracking-tight">
          Questions, answered.
        </h2>
        <div className="mt-6 divide-y divide-[var(--color-border)] overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)]">
          {FAQ.map(([q, a]) => (
            <details key={q} className="group">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-4 text-sm font-semibold hover:text-[var(--color-accent)]">
                {q}
                <span className="shrink-0 text-lg leading-none text-[var(--color-muted)] transition-transform group-open:rotate-45">
                  +
                </span>
              </summary>
              <p className="px-5 pb-4 text-sm leading-relaxed text-[var(--color-muted)]">
                {a}
              </p>
            </details>
          ))}
        </div>
      </div>
    </div>
  );
}
