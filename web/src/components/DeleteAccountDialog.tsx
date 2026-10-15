import { useState } from 'react';
import { Overlay } from './ui/Overlay';
import { Button } from './ui/Button';
import { useStore } from '../state/store';

/* Permanent account deletion. Google Play requires it inside the app for
   any app that lets people sign up. The password is asked again so a phone
   left unlocked is not enough to wipe someone's account. */
export function DeleteAccountDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const deleteAccount = useStore((s) => s.deleteAccount);
  const user = useStore((s) => s.user);
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const close = () => {
    if (busy) return;
    setPassword('');
    setError(null);
    onClose();
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password) { setError('Enter your password to confirm.'); return; }
    setBusy(true);
    setError(null);
    const res = await deleteAccount(password);
    // On success the page is already leaving for the confirmation page.
    if (!res.ok) {
      setBusy(false);
      setError(res.error ?? 'Could not delete the account. Please try again.');
    }
  };

  return (
    <Overlay
      open={open}
      onClose={close}
      title="Delete account"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={close} disabled={busy}>Cancel</Button>
          <Button variant="danger" type="submit" form="delete-account-form" loading={busy}>
            Delete my account
          </Button>
        </div>
      }
    >
      <form id="delete-account-form" onSubmit={submit} className="space-y-4 text-sm">
        <p>
          This permanently deletes <span className="font-semibold">{user}</span>. It cannot be undone.
        </p>
        <div>
          <p className="mb-1.5 font-medium">Deleted straight away</p>
          <ul className="list-disc space-y-1 pl-5 text-[var(--color-muted)]">
            <li>Your account and sign-in</li>
            <li>Your cloned voices and their recordings</li>
            <li>Your songs and their audio files</li>
            <li>Your remaining characters and any time left on a paid plan</li>
          </ul>
        </div>
        <div>
          <p className="mb-1.5 font-medium">Kept</p>
          <p className="text-[var(--color-muted)]">
            Records of payments you made, because Indian tax law requires us to keep them.
          </p>
        </div>
        <label className="block">
          <span className="mb-1.5 block font-medium">Your password</span>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={busy}
            className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2.5 text-[var(--color-fg)] outline-none focus:border-[var(--color-error)]"
          />
        </label>
        {error && (
          <p role="alert" className="rounded-lg bg-[var(--color-error)]/10 px-3 py-2 text-[var(--color-error)]">
            {error}
          </p>
        )}
      </form>
    </Overlay>
  );
}
