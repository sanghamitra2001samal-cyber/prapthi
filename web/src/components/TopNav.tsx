import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useStore } from '../state/store';

export function TopNav() {
  const openOverlay = useStore((s) => s.openOverlay);
  const user = useStore((s) => s.user);
  const logout = useStore((s) => s.logout);
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  const navLinks = (
    <>
      <button
        className="rounded-md px-3 py-2 text-sm text-[var(--color-fg)] hover:bg-[var(--color-surface-2)]"
        onClick={() => {
          openOverlay('history');
          setMenuOpen(false);
        }}
      >
        History
      </button>
      <Link
        to="/help"
        className="rounded-md px-3 py-2 text-sm text-[var(--color-fg)] hover:bg-[var(--color-surface-2)]"
        onClick={() => setMenuOpen(false)}
      >
        Help
      </Link>
      <Link
        to="/about"
        className="rounded-md px-3 py-2 text-sm text-[var(--color-fg)] hover:bg-[var(--color-surface-2)]"
        onClick={() => setMenuOpen(false)}
      >
        About
      </Link>
      <button
        className="rounded-md px-3 py-2 text-sm text-[var(--color-muted)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-error)]"
        onClick={async () => {
          setMenuOpen(false);
          await logout();
        }}
        title={user ? `Signed in as ${user}` : undefined}
      >
        Log out{user ? ` (${user})` : ''}
      </button>
    </>
  );

  return (
    <header className="sticky top-0 z-40 border-b border-[var(--color-border)] bg-[var(--color-bg)]/90 backdrop-blur">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
        <button
          onClick={() => navigate('/dashboard')}
          className="flex items-center gap-2 text-lg font-semibold tracking-tight"
          aria-label="Prapthi Ai dashboard"
        >
          <span
            className="grid h-7 w-7 place-items-center rounded-lg bg-[var(--color-accent)] text-white"
            aria-hidden
          >
            ▮
          </span>
          Prapthi Ai
        </button>

        <nav className="hidden items-center gap-1 md:flex">{navLinks}</nav>

        <button
          className="rounded-md p-2 hover:bg-[var(--color-surface-2)] md:hidden"
          aria-label="Menu"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((o) => !o)}
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path
              d="M4 7h16M4 12h16M4 17h16"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </div>

      {menuOpen && (
        <nav className="flex flex-col gap-1 border-t border-[var(--color-border)] px-4 py-2 md:hidden">
          {navLinks}
        </nav>
      )}
    </header>
  );
}
