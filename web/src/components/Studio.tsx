import { Play, Pause, Square, Download, SlidersHorizontal, ChevronDown } from 'lucide-react';
import { useStore } from '../state/store';
import { Editor } from './Editor';
import { ResultPlayer } from './ResultPlayer';

/** ElevenLabs-style studio: a full-height text canvas with a bottom control
 * bar (voice selector + generate). */
export function Studio() {
  const voices = useStore((s) => s.voices);
  const voicesLoaded = useStore((s) => s.voicesLoaded);
  const activeVoice = useStore((s) => s.activeVoice());
  const openOverlay = useStore((s) => s.openOverlay);
  const preview = useStore((s) => s.preview);
  const serverReachable = useStore((s) => s.serverReachable);
  const status = useStore((s) => s.status);
  const emotion = useStore((s) => s.emotion);
  const text = useStore((s) => s.text);
  const play = useStore((s) => s.play);
  const pause = useStore((s) => s.pause);
  const resume = useStore((s) => s.resume);
  const stop = useStore((s) => s.stop);
  const lastGen = useStore((s) => s.lastGen);
  const lastAudioUrl = useStore((s) => s.lastAudioUrl);

  const noVoices = voicesLoaded && voices.length === 0;
  const generating = status === 'loading';
  const hasText = text.trim().length > 0;
  const voiceName = activeVoice?.name ?? (voicesLoaded ? 'No voice' : 'Loading…');
  const avatarChar = (activeVoice?.name ?? 'P').replace(/[^A-Za-z]/g, '').slice(0, 1) || 'P';

  return (
    <div className="flex h-full flex-col">
      {/* Canvas */}
      <div className="flex min-h-0 flex-1 flex-col gap-3 px-4 pt-5 md:px-8 md:pt-6">
        {noVoices && (
          <div className="rounded-xl border border-[var(--color-error)] bg-[var(--color-error)]/10 p-3 text-sm" role="alert">
            <span className="font-medium text-[var(--color-error)]">No voices found.</span>{' '}
            <span className="text-[var(--color-muted)]">Check the voice server — see Help.</span>
          </div>
        )}
        {!serverReachable && voicesLoaded && (
          <p className="text-xs text-[var(--color-muted)]">
            ℹ Voice server offline — using browser voices only.
          </p>
        )}
        <div className="min-h-0 flex-1">
          <Editor />
        </div>
        {lastAudioUrl && lastGen && (
          <div className="shrink-0">
            <ResultPlayer />
          </div>
        )}
      </div>

      {/* Bottom control bar */}
      <div className="mt-4 border-t border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 md:px-8">
        <div className="flex items-center gap-2">
          {/* Voice selector */}
          <button
            onClick={() => openOverlay('voices')}
            disabled={noVoices}
            className="flex min-w-0 items-center gap-2.5 rounded-full border border-[var(--color-border)] bg-[var(--color-bg)] py-1.5 pl-1.5 pr-3 text-sm hover:border-[var(--color-accent)] disabled:opacity-50"
          >
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[var(--color-accent)]/20 text-xs font-bold uppercase text-[var(--color-accent)]">
              {avatarChar}
            </span>
            <span className="truncate font-medium">{voiceName}</span>
            <ChevronDown size={15} className="shrink-0 text-[var(--color-muted)]" />
          </button>

          {/* Preview */}
          <button
            onClick={() => preview()}
            disabled={!activeVoice}
            title="Preview voice"
            className="hidden h-9 w-9 shrink-0 place-items-center rounded-full border border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-fg)] disabled:opacity-50 sm:grid"
          >
            <Play size={15} />
          </button>

          {/* Settings */}
          <button
            onClick={() => openOverlay('settings')}
            className="flex shrink-0 items-center gap-1.5 rounded-full border border-[var(--color-border)] px-3 py-2 text-sm text-[var(--color-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-fg)]"
          >
            <SlidersHorizontal size={15} />
            <span className="hidden sm:inline">Settings</span>
            {emotion !== 'neutral' && (
              <span className="rounded-full bg-[var(--color-accent)]/15 px-2 py-0.5 text-[11px] font-semibold capitalize text-[var(--color-accent)]">
                {emotion}
              </span>
            )}
          </button>

          <div className="ml-auto flex shrink-0 items-center gap-2">
            {(status === 'playing' || status === 'paused') && (
              <button
                onClick={stop}
                title="Stop"
                className="grid h-10 w-10 place-items-center rounded-full border border-[var(--color-border)] text-[var(--color-muted)] hover:text-[var(--color-fg)]"
              >
                <Square size={16} />
              </button>
            )}
            {lastGen && (
              <button
                onClick={() => openOverlay('export')}
                title="Export / download"
                className="grid h-10 w-10 place-items-center rounded-full border border-[var(--color-border)] text-[var(--color-muted)] hover:text-[var(--color-fg)]"
              >
                <Download size={16} />
              </button>
            )}

            {/* Primary generate / play */}
            {status === 'playing' ? (
              <button
                onClick={pause}
                className="flex items-center gap-2 rounded-full bg-[var(--color-accent)] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[var(--color-accent-hover)]"
              >
                <Pause size={16} /> Pause
              </button>
            ) : status === 'paused' ? (
              <button
                onClick={resume}
                className="flex items-center gap-2 rounded-full bg-[var(--color-accent)] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[var(--color-accent-hover)]"
              >
                <Play size={16} /> Resume
              </button>
            ) : (
              <button
                onClick={() => void play()}
                disabled={!hasText || generating || noVoices}
                className="flex items-center gap-2 rounded-full bg-[var(--color-accent)] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[var(--color-accent-hover)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {generating ? (
                  <>
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                    Generating…
                  </>
                ) : (
                  <>
                    <Play size={16} /> Generate
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
