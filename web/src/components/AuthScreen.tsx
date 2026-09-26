import { useState, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'motion/react';
import { Globe, Code2, Eye, EyeOff, Check } from 'lucide-react';
import { useStore } from '../state/store';

type View = 'login' | 'signup' | 'verify' | 'forgot' | 'reset';

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.15, delayChildren: 0.2 },
  },
};
const item = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5 } },
};

export function AuthScreen({ initialView = 'login' }: { initialView?: View }) {
  const { login, signup, verifyEmail, resendCode, forgotPassword, resetPassword, toast } =
    useStore.getState();
  const navigate = useNavigate();

  const [view, setView] = useState<View>(initialView);
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const go = (v: View) => {
    setView(v);
    setError(null);
    setNotice(null);
    setPassword('');
    setCode('');
  };

  type Res = { ok: boolean; error?: string; message?: string; unverified?: boolean };
  const run = async (fn: () => Promise<Res>): Promise<Res> => {
    setBusy(true);
    setError(null);
    setNotice(null);
    const res = await fn();
    setBusy(false);
    return res;
  };

  // ---- handlers (unchanged auth logic) -----------------------------------
  const onLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    const res = await run(() => login(email.trim().toLowerCase(), password));
    if (res.ok) {
      navigate('/dashboard');
      return;
    }
    if (res.unverified) {
      setNotice('Please verify your email. Enter the code we sent you.');
      setView('verify');
    } else setError(res.error ?? 'Login failed.');
  };

  const onSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    const res = await run(() => signup(email.trim().toLowerCase(), password));
    if (res.ok) {
      setNotice('Account created. Enter the 6-digit code we emailed you.');
      setView('verify');
    } else setError(res.error ?? 'Sign up failed.');
  };

  const onVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    const res = await run(() => verifyEmail(email.trim().toLowerCase(), code.trim()));
    if (res.ok) {
      setView('login');
      setNotice('Email verified — please sign in.');
      setCode('');
    } else setError(res.error ?? 'Verification failed.');
  };

  const onForgot = async (e: React.FormEvent) => {
    e.preventDefault();
    const res = await run(() => forgotPassword(email.trim().toLowerCase()));
    if (res.ok) {
      setNotice('If that email exists, a reset code was sent.');
      setView('reset');
    } else setError(res.error ?? 'Request failed.');
  };

  const onReset = async (e: React.FormEvent) => {
    e.preventDefault();
    const res = await run(() =>
      resetPassword(email.trim().toLowerCase(), code.trim(), password)
    );
    if (res.ok) {
      setView('login');
      setNotice('Password updated — please sign in.');
      setPassword('');
      setCode('');
    } else setError(res.error ?? 'Reset failed.');
  };

  const onResend = async () => {
    const res = await run(() => resendCode(email.trim().toLowerCase()));
    if (res.ok) setNotice('A new code was sent.');
    else setError(res.error ?? 'Could not resend.');
  };

  const social = () =>
    toast({ kind: 'info', message: 'Social sign-in is coming soon — use email for now.' });

  const headers: Record<View, [string, string]> = {
    login: ['Welcome back', 'Sign in to your Prapthi Ai studio.'],
    signup: ['Create New Profile', 'Input your basic details to begin the journey.'],
    verify: ['Verify your email', 'Enter the 6-digit code we sent you.'],
    forgot: ['Reset your password', "We'll email you a reset code."],
    reset: ['Set a new password', 'Enter the code and choose a new password.'],
  };
  const activeStep = view === 'verify' ? 2 : view === 'reset' ? 3 : 1;
  const eyeToggle = (
    <button
      type="button"
      onClick={() => setShowPw((s) => !s)}
      className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--color-muted)] hover:text-[var(--color-fg)]"
      aria-label={showPw ? 'Hide password' : 'Show password'}
    >
      {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
    </button>
  );

  return (
    <main className="flex min-h-screen w-full bg-[var(--color-bg)] text-[var(--color-fg)] selection:bg-[var(--color-accent)]/30 p-2 transition-all duration-500 lg:h-screen lg:overflow-hidden lg:p-4">
      {/* ---- Left: hero + background video ---- */}
      <section className="relative hidden w-[52%] flex-col items-center justify-end overflow-hidden rounded-3xl px-12 pb-32 text-white shadow-2xl lg:flex">
        <div className="absolute inset-0 h-full w-full bg-[radial-gradient(120%_100%_at_50%_20%,#10305e_0%,#061b37_55%,#030d1c_100%)]" />

        <motion.div
          variants={container}
          initial="hidden"
          animate="show"
          className="z-10 w-full max-w-xs space-y-8"
        >
          <motion.div variants={item} className="flex items-center gap-2.5">
            <img src="/logo.png" alt="" className="h-9 w-9 rounded-lg bg-white object-contain p-0.5" />
            <span className="text-xl font-semibold tracking-tight">Prapthi Ai</span>
          </motion.div>

          <motion.div variants={item} className="space-y-3">
            <h2 className="whitespace-nowrap text-4xl font-medium tracking-tight">
              Join Prapthi Ai
            </h2>
            <p className="px-4 text-sm leading-relaxed text-white/70">
              Follow these 3 quick phases to activate your space.
            </p>
          </motion.div>

          <motion.div variants={item} className="space-y-3">
            <StepItem number={1} text="Register your identity" active={activeStep === 1} />
            <StepItem number={2} text="Verify your email" active={activeStep === 2} />
            <StepItem number={3} text="Finalize your profile" active={activeStep === 3} />
          </motion.div>
        </motion.div>
      </section>

      {/* ---- Right: form ---- */}
      <section className="flex flex-1 flex-col items-center justify-center overflow-y-auto px-4 py-12 sm:px-12 lg:overflow-hidden lg:py-6 lg:px-16 xl:px-24">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
          className="w-full max-w-xl space-y-8 sm:space-y-10 lg:space-y-6"
        >
          {/* mobile brand */}
          <Link to="/" className="flex items-center gap-2 lg:hidden">
            <img src="/logo.png" alt="" className="h-8 w-8 rounded-lg bg-white object-contain p-0.5" />
            <span className="text-lg font-semibold tracking-tight">Prapthi Ai</span>
          </Link>

          <div className="space-y-1">
            <h1 className="text-3xl font-medium tracking-tight">{headers[view][0]}</h1>
            <p className="text-sm text-[var(--color-muted)]">{headers[view][1]}</p>
          </div>

          {notice && (
            <p className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] px-4 py-3 text-sm text-[var(--color-fg)]">
              {notice}
            </p>
          )}
          {error && (
            <p
              className="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-300"
              role="alert"
            >
              {error}
            </p>
          )}

          {/* social + divider only on login/signup */}
          {(view === 'login' || view === 'signup') && (
            <>
              <div className="grid grid-cols-2 gap-4">
                <SocialButton icon={<Globe size={18} />} label="Google" onClick={social} />
                <SocialButton icon={<Code2 size={18} />} label="Github" onClick={social} />
              </div>
              <div className="relative flex items-center">
                <div className="flex-1 border-t border-[var(--color-border)]" />
                <span className="bg-[var(--color-bg)] px-4 text-xs font-medium uppercase tracking-widest text-[var(--color-muted)]">
                  Or
                </span>
                <div className="flex-1 border-t border-[var(--color-border)]" />
              </div>
            </>
          )}

          {/* ---- forms ---- */}
          {view === 'login' && (
            <form onSubmit={onLogin} className="space-y-5">
              <InputGroup label="Email" type="email" value={email} onChange={setEmail} placeholder="you@example.com" autoComplete="username" />
              <InputGroup label="Password" type={showPw ? 'text' : 'password'} value={password} onChange={setPassword} placeholder="••••••••" autoComplete="current-password" trailing={eyeToggle} />
              <SubmitButton busy={busy}>Sign in</SubmitButton>
              <div className="flex justify-between text-sm text-[var(--color-muted)]">
                <button type="button" className="hover:text-[var(--color-fg)]" onClick={() => go('forgot')}>Forgot password?</button>
                <button type="button" className="hover:text-[var(--color-fg)]" onClick={() => go('signup')}>Create account</button>
              </div>
            </form>
          )}

          {view === 'signup' && (
            <form onSubmit={onSignup} className="space-y-5">
              <div className="grid grid-cols-2 gap-4">
                <InputGroup label="First Name" type="text" value={firstName} onChange={setFirstName} placeholder="Ayaan" required={false} />
                <InputGroup label="Last Name" type="text" value={lastName} onChange={setLastName} placeholder="Sharma" required={false} />
              </div>
              <InputGroup label="Email" type="email" value={email} onChange={setEmail} placeholder="you@example.com" autoComplete="username" />
              <InputGroup label="Password" type={showPw ? 'text' : 'password'} value={password} onChange={setPassword} placeholder="••••••••" autoComplete="new-password" trailing={eyeToggle} helper="Requires at least 8 symbols." />
              <SubmitButton busy={busy}>Create Account</SubmitButton>
              <p className="text-center text-sm text-[var(--color-muted)]">
                Member of the team?{' '}
                <button type="button" className="text-[var(--color-accent)] hover:underline" onClick={() => go('login')}>Log in</button>
              </p>
            </form>
          )}

          {view === 'verify' && (
            <form onSubmit={onVerify} className="space-y-5">
              <InputGroup label="Email" type="email" value={email} onChange={setEmail} placeholder="you@example.com" autoComplete="username" />
              <InputGroup label="6-digit code" type="text" value={code} onChange={setCode} placeholder="123456" inputMode="numeric" />
              <SubmitButton busy={busy}>Verify</SubmitButton>
              <div className="flex justify-between text-sm text-[var(--color-muted)]">
                <button type="button" className="hover:text-[var(--color-fg)]" onClick={onResend}>Resend code</button>
                <button type="button" className="hover:text-[var(--color-fg)]" onClick={() => go('login')}>Back to sign in</button>
              </div>
            </form>
          )}

          {view === 'forgot' && (
            <form onSubmit={onForgot} className="space-y-5">
              <InputGroup label="Email" type="email" value={email} onChange={setEmail} placeholder="you@example.com" autoComplete="username" />
              <SubmitButton busy={busy}>Send reset code</SubmitButton>
              <p className="text-center text-sm text-[var(--color-muted)]">
                <button type="button" className="hover:text-[var(--color-fg)]" onClick={() => go('login')}>Back to sign in</button>
              </p>
            </form>
          )}

          {view === 'reset' && (
            <form onSubmit={onReset} className="space-y-5">
              <InputGroup label="Email" type="email" value={email} onChange={setEmail} placeholder="you@example.com" autoComplete="username" />
              <InputGroup label="6-digit code" type="text" value={code} onChange={setCode} placeholder="123456" inputMode="numeric" />
              <InputGroup label="New password" type={showPw ? 'text' : 'password'} value={password} onChange={setPassword} placeholder="••••••••" autoComplete="new-password" trailing={eyeToggle} helper="Requires at least 8 symbols." />
              <SubmitButton busy={busy}>Update password</SubmitButton>
              <p className="text-center text-sm text-[var(--color-muted)]">
                <button type="button" className="hover:text-[var(--color-fg)]" onClick={() => go('login')}>Back to sign in</button>
              </p>
            </form>
          )}
        </motion.div>
      </section>
    </main>
  );
}

// ---- reusable components ---------------------------------------------------
function StepItem({ number, text, active }: { number: number; text: string; active?: boolean }) {
  return (
    <div
      className={`flex items-center gap-3 rounded-2xl px-4 py-3 ${
        active
          ? 'border border-[var(--color-accent)] bg-[var(--color-accent)] text-white'
          : 'border-none bg-white/10 text-white/70'
      }`}
    >
      <span
        className={`grid h-7 w-7 shrink-0 place-items-center rounded-full text-sm font-semibold ${
          active ? 'bg-white text-[var(--color-accent)]' : 'bg-white/15 text-white/70'
        }`}
      >
        {active ? <Check size={15} /> : number}
      </span>
      <span className="text-sm font-medium">{text}</span>
    </div>
  );
}

function SocialButton({ icon, label, onClick }: { icon: ReactNode; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex h-12 items-center justify-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] text-sm font-medium hover:bg-[var(--color-surface-2)]"
    >
      {icon}
      {label}
    </button>
  );
}

function InputGroup({
  label,
  type,
  value,
  onChange,
  placeholder,
  autoComplete,
  inputMode,
  trailing,
  helper,
  required = true,
}: {
  label: string;
  type: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  autoComplete?: string;
  inputMode?: 'numeric';
  trailing?: ReactNode;
  helper?: string;
  required?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium text-[var(--color-fg)]">{label}</label>
      <div className="relative">
        <input
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          autoComplete={autoComplete}
          inputMode={inputMode}
          required={required}
          className="h-11 w-full rounded-xl border-none bg-[var(--color-surface-2)] px-4 pr-11 text-[var(--color-fg)] placeholder:text-[var(--color-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]/40"
        />
        {trailing}
      </div>
      {helper && <p className="text-xs text-[var(--color-muted)]">{helper}</p>}
    </div>
  );
}

function SubmitButton({ busy, children }: { busy: boolean; children: ReactNode }) {
  return (
    <button
      type="submit"
      disabled={busy}
      className="mt-4 flex h-14 w-full items-center justify-center gap-2 rounded-xl bg-[var(--color-accent)] font-semibold text-white transition hover:bg-[var(--color-accent-hover)] active:scale-[0.98] disabled:opacity-60"
    >
      {busy && (
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-black/30 border-t-black" aria-hidden />
      )}
      {children}
    </button>
  );
}
