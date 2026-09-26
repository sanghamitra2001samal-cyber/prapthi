import { Link } from 'react-router-dom';

export default function About() {
  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <h1 className="text-2xl font-semibold">About &amp; Privacy</h1>
      <p className="mt-4 text-[var(--color-muted)]">
        Prapthi Ai is a free, no-signup text-to-speech studio that runs in your
        browser. It is built deliberately <strong>without any third-party TTS
        API</strong> — no per-character fees, no vendor lock-in, no sending your
        words to someone else's cloud.
      </p>

      <h2 className="mt-8 text-lg font-semibold">Your privacy</h2>
      <ul className="mt-2 list-disc space-y-2 pl-5 text-[var(--color-muted)]">
        <li>Browser voices run entirely on your device — your text never leaves it.</li>
        <li>No accounts, no logins, no tracking of what you type.</li>
        <li>History is stored only in your browser's local storage, never on a server.</li>
        <li>
          The optional self-hosted voice sends text to a server <em>you</em> run,
          which keeps nothing after returning your audio.
        </li>
      </ul>

      <h2 className="mt-8 text-lg font-semibold">Honest expectations</h2>
      <p className="mt-2 text-[var(--color-muted)]">
        Commercial tools like ElevenLabs lead on proprietary, emotive voice
        realism — all API-driven. Prapthi Ai competes on being free, private, and
        instant instead. Voice quality depends on your OS voices and the
        open-source engine, not paid models.
      </p>

      <Link
        to="/"
        className="mt-8 inline-block text-[var(--color-accent)] hover:underline"
      >
        ← Back to home
      </Link>
    </main>
  );
}
