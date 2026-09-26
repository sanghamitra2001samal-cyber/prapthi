import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <main className="mx-auto flex max-w-2xl flex-col items-center px-4 py-24 text-center">
      <p className="text-5xl font-bold text-[var(--color-accent)]">404</p>
      <h1 className="mt-4 text-xl font-semibold">This page doesn't exist.</h1>
      <div className="mt-6 flex gap-3">
        <Link
          to="/"
          className="rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--color-accent-hover)]"
        >
          Back to home
        </Link>
        <Link
          to="/help"
          className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm hover:bg-[var(--color-surface-2)]"
        >
          Help
        </Link>
      </div>
    </main>
  );
}
