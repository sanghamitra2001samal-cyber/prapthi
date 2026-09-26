import { useState } from 'react';
import { Link } from 'react-router-dom';

const FAQ = [
  {
    q: 'Why do voices differ by browser?',
    a: 'Browser voices come from your operating system via the Web Speech API. Chrome, Safari, Edge, and Firefox each expose a different set, so the list you see depends on your OS and browser.',
  },
  {
    q: "Why can't I download some voices?",
    a: 'Browser voices only speak aloud — the Web Speech API never hands back an audio file. We offer best-effort tab-audio capture for them, but for a guaranteed WAV/MP3 use a "Downloadable" (self-hosted) voice.',
  },
  {
    q: 'Is my text private?',
    a: 'Yes. With browser voices, your text never leaves your device — synthesis happens locally and we make zero network calls with your text. Only the optional self-hosted voice sends text to your own server, which stores nothing.',
  },
  {
    q: 'How do I enable the downloadable voice?',
    a: 'Downloadable voices run on Prapthi\'s own self-hosted speech engine and are available automatically on the hosted app — just pick any voice marked “Downloadable” in the voice picker.',
  },
];

function Accordion({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-[var(--color-border)]">
      <button
        className="flex w-full items-center justify-between py-4 text-left"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className="font-medium">{q}</span>
        <span className="text-[var(--color-muted)]">{open ? '−' : '+'}</span>
      </button>
      {open && <p className="pb-4 text-sm text-[var(--color-muted)]">{a}</p>}
    </div>
  );
}

export default function Help() {
  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <h1 className="text-2xl font-semibold">How it works</h1>
      <ol className="mt-4 space-y-2 text-[var(--color-muted)]">
        <li>1. Type or paste your text in the editor.</li>
        <li>2. Pick a voice (or keep the default) and preview it.</li>
        <li>3. Press Play to hear it with word highlighting.</li>
        <li>4. Export to download an audio file.</li>
      </ol>

      <h2 className="mt-8 text-lg font-semibold">FAQ</h2>
      <div className="mt-2">
        {FAQ.map((f) => (
          <Accordion key={f.q} {...f} />
        ))}
      </div>

      <div className="mt-8 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-sm text-[var(--color-muted)]">
        Prapthi Ai is built with <strong>no third-party TTS APIs</strong>. The free
        path uses your browser's built-in voices; the optional downloadable voice
        runs on a self-hosted open-source engine you control.
      </div>

      <Link
        to="/"
        className="mt-8 inline-block text-[var(--color-accent)] hover:underline"
      >
        ← Back to home
      </Link>
    </main>
  );
}
