import { useState } from 'react';
import { useStore } from '../state/store';
import { Overlay } from './ui/Overlay';
import { Button } from './ui/Button';
import { tts } from '../tts/manager';
import { ServerProvider } from '../tts/ServerProvider';
import { downloadBlob } from '../lib/download';
import { captureSupported, captureBrowserSpeech } from '../lib/recorder';
import { timestamp, safeFilenamePart } from '../lib/format';

export function ExportDialog() {
  const open = useStore((s) => s.overlay === 'export');
  const close = useStore((s) => s.closeOverlay);
  const lastGen = useStore((s) => s.lastGen);
  const voices = useStore((s) => s.voices);
  const toast = useStore((s) => s.toast);
  const openOverlay = useStore((s) => s.openOverlay);

  const [format, setFormat] = useState<'wav' | 'mp3'>('wav');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const voice = lastGen
    ? voices.find((v) => v.id === lastGen.voiceId)
    : undefined;
  const isServer = voice?.provider === 'server';
  const ext = isServer ? format : 'webm';
  const filename = lastGen
    ? `prapthiai_${safeFilenamePart(lastGen.voiceName)}_${timestamp(
        new Date(lastGen.createdAt)
      )}.${ext}`
    : '';

  const reset = () => {
    setBusy(false);
    setError(null);
  };

  const handleDownload = async () => {
    if (!lastGen) return;
    setBusy(true);
    setError(null);
    try {
      const req = {
        text: lastGen.text,
        voiceId: lastGen.voiceId,
        rate: lastGen.rate,
        pitch: lastGen.pitch,
        volume: lastGen.volume,
        emotion: lastGen.emotion ?? 'neutral',
      };

      if (isServer) {
        const server = tts.get(lastGen.voiceId) as ServerProvider;
        const blob = await server.synthesizeToBlob(req, format);
        downloadBlob(blob, filename);
      } else {
        // Browser voice — best-effort tab-audio capture.
        if (!captureSupported()) {
          throw new Error('UNSUPPORTED');
        }
        const provider = tts.get(lastGen.voiceId);
        const { blob } = await captureBrowserSpeech(
          () => provider.speak(req, {})
        );
        downloadBlob(blob, filename);
      }
      toast({ kind: 'success', message: `Downloaded ${filename}` });
      close();
      reset();
    } catch (e) {
      const msg = (e as Error).message;
      if (msg === 'UNSUPPORTED') {
        setError(
          "This browser can't save browser-voice audio. Switch to the downloadable voice for a real file."
        );
      } else {
        setError(msg || 'Download failed. Please try again.');
      }
    } finally {
      setBusy(false);
    }
  };

  if (!lastGen) {
    return (
      <Overlay open={open} onClose={close} title="Export audio">
        <div className="py-10 text-center text-sm text-[var(--color-muted)]">
          <p>Nothing to export yet. Press Play first.</p>
          <button
            className="mt-3 text-[var(--color-accent)] hover:underline"
            onClick={close}
          >
            Back to editor
          </button>
        </div>
      </Overlay>
    );
  }

  return (
    <Overlay
      open={open}
      onClose={() => {
        close();
        reset();
      }}
      title="Export audio"
      footer={
        <div className="flex justify-end gap-2">
          <Button
            variant="ghost"
            onClick={() => {
              close();
              reset();
            }}
          >
            Cancel
          </Button>
          <Button variant="primary" onClick={handleDownload} loading={busy}>
            Download
          </Button>
        </div>
      }
    >
      {isServer ? (
        <fieldset className="mb-4">
          <legend className="mb-2 text-sm font-medium">Format</legend>
          <div className="flex gap-2">
            {(['wav', 'mp3'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFormat(f)}
                className={`rounded-lg border px-4 py-2 text-sm uppercase ${
                  format === f
                    ? 'border-[var(--color-accent)] bg-[var(--color-accent)]/15 text-[var(--color-accent)]'
                    : 'border-[var(--color-border)] text-[var(--color-muted)]'
                }`}
              >
                {f}
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-[var(--color-muted)]">
            WAV is always available. MP3 requires ffmpeg on the server; if it's
            missing, the server returns WAV.
          </p>
        </fieldset>
      ) : (
        <div className="mb-4 rounded-lg border border-[var(--color-warning)] bg-[var(--color-warning)]/10 p-3 text-xs text-[var(--color-warning)]">
          This is a browser voice. There's no audio file to fetch, so export uses
          best-effort tab-audio capture: you'll be asked to share this tab
          <strong> with "Share tab audio" enabled</strong>. For a guaranteed file,
          use a downloadable (server) voice.
        </div>
      )}

      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2">
        <p className="text-xs text-[var(--color-muted)]">Filename</p>
        <p className="truncate font-mono text-sm">{filename}</p>
      </div>

      {error && (
        <div className="mt-3 text-sm text-[var(--color-error)]" role="alert">
          <p>{error}</p>
          <button
            className="mt-2 text-[var(--color-accent)] hover:underline"
            onClick={() => {
              close();
              reset();
              openOverlay('voices');
            }}
          >
            Switch voice →
          </button>
        </div>
      )}
    </Overlay>
  );
}
