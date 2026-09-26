import { Link } from 'react-router-dom';

export function Footer() {
  return (
    <footer className="border-t border-[var(--color-border)] px-4 py-5 text-center text-xs text-[var(--color-muted)]">
      <p>Runs in your browser. No API. Your text stays on your device.</p>
      <p className="mt-1 flex justify-center gap-4">
        <Link to="/pricing" className="hover:text-[var(--color-fg)]">
          Pricing
        </Link>
        <Link to="/help" className="hover:text-[var(--color-fg)]">
          Help
        </Link>
        <Link to="/about" className="hover:text-[var(--color-fg)]">
          About / Privacy
        </Link>
      </p>
      {/* Required by the CC-BY-4.0 licences of the open speech resources
          some voices and models are derived from. */}
      <p className="mt-2 text-[11px] opacity-70">
        Some voices built with{' '}
        <a href="https://huggingface.co/datasets/google/fleurs" target="_blank" rel="noreferrer noopener" className="underline hover:text-[var(--color-fg)]">Google FLEURS</a>{' '}and{' '}
        <a href="https://huggingface.co/datasets/ai4bharat/Rasa" target="_blank" rel="noreferrer noopener" className="underline hover:text-[var(--color-fg)]">AI4Bharat Rasa</a>{' '}·{' '}
        <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer noopener" className="underline hover:text-[var(--color-fg)]">CC BY 4.0</a>
      </p>
    </footer>
  );
}
