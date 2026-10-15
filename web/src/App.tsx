import { useEffect, type ReactNode } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useStore } from './state/store';
import { ToastLayer } from './components/ToastLayer';
import { AuthScreen } from './components/AuthScreen';
import { Dashboard } from './components/Dashboard';
import Landing from './pages/Landing';
import Help from './pages/Help';
import About from './pages/About';
import Admin from './pages/Admin';
import Pricing from './pages/Pricing';
import NotFound from './pages/NotFound';

function Spinner() {
  return (
    <div className="flex min-h-full items-center justify-center">
      <span
        className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--color-border)] border-t-[var(--color-accent)]"
        aria-label="Loading"
      />
    </div>
  );
}

/* The studio is mounted under /app on the live site, where the public pages
   (home, login, sign up, about, pricing) are the real ones. The app's own
   copies of those screens are therefore never shown there: each redirects to
   the site page with a full page load. In local development the app is served
   at the root with no site around it, so the built-in screens still render. */
const UNDER_SITE = import.meta.env.BASE_URL !== '/';

function SiteRedirect({ to }: { to: string }) {
  useEffect(() => {
    window.location.replace(to);
  }, [to]);
  return <Spinner />;
}

/** Gates the dashboard: wait while checking, redirect to /login if signed out. */
function RequireAuth({ children }: { children: ReactNode }) {
  const authStatus = useStore((s) => s.authStatus);
  if (authStatus === 'loading') return <Spinner />;
  if (authStatus === 'out')
    return UNDER_SITE ? <SiteRedirect to="/login" /> : <Navigate to="/login" replace />;
  return <>{children}</>;
}

/** Auth pages redirect to the dashboard if the user is already signed in. */
function AuthRoute({ view }: { view: 'login' | 'signup' }) {
  const authStatus = useStore((s) => s.authStatus);
  if (authStatus === 'loading') return <Spinner />;
  if (authStatus === 'in') return <Navigate to="/dashboard" replace />;
  if (UNDER_SITE) return <SiteRedirect to={view === 'signup' ? '/signup' : '/login'} />;
  return <AuthScreen initialView={view} />;
}

/* The Android/iOS app opens here (/app/) and identifies itself with
   "PrapthiApp" in its user agent (mobile/capacitor.config.json). */
const IN_APP = typeof navigator !== 'undefined' && /PrapthiApp\//.test(navigator.userAgent);

/** The app's own landing page: signed in -> straight to work. Signed out, a
 *  browser goes to the site's sign-in page; the phone app goes to the site's
 *  home page instead, so a first-time user meets the product before a login
 *  form. It is never rendered on the live site. */
function HomeRoute() {
  const authStatus = useStore((s) => s.authStatus);
  if (authStatus === 'loading') return <Spinner />;
  if (authStatus === 'in') return <Navigate to="/dashboard" replace />;
  if (!UNDER_SITE) return <Landing />;
  return <SiteRedirect to={IN_APP ? '/' : '/login'} />;
}

export default function App() {
  const checkAuth = useStore((s) => s.checkAuth);

  useEffect(() => {
    void checkAuth();
  }, [checkAuth]);

  return (
    <>
      <Routes>
        <Route path="/" element={<HomeRoute />} />
        <Route path="/login" element={<AuthRoute view="login" />} />
        <Route path="/signup" element={<AuthRoute view="signup" />} />
        <Route path="/help" element={<Help />} />
        <Route path="/about" element={UNDER_SITE ? <SiteRedirect to="/about" /> : <About />} />
        {/* Checkout lives here — it must NOT redirect to the marketing page. */}
        <Route path="/pricing" element={<Pricing />} />
        {/* Owner only. The component sends non-admins away, and the server
            answers 404 to them regardless, so the route leaks nothing. */}
        <Route
          path="/admin"
          element={
            <RequireAuth>
              <Admin />
            </RequireAuth>
          }
        />
        <Route
          path="/dashboard"
          element={
            <RequireAuth>
              <Dashboard />
            </RequireAuth>
          }
        />
        <Route path="*" element={<NotFound />} />
      </Routes>
      <ToastLayer />
    </>
  );
}
