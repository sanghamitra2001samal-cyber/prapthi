import { Save } from 'lucide-react';
import { useStore } from '../state/store';
import { Overlay } from './ui/Overlay';
import { Button } from './ui/Button';

interface SliderProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (n: number) => void;
  hint?: string;
}

function Slider({ label, value, min, max, step, onChange, hint }: SliderProps) {
  return (
    <div className="py-3">
      <div className="mb-1 flex items-center justify-between">
        <label className="text-sm font-medium">{label}</label>
        <span className="font-mono text-sm text-[var(--color-accent)]">
          {value.toFixed(2)}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label={label}
        aria-valuenow={value}
        aria-valuemin={min}
        aria-valuemax={max}
        className="w-full"
      />
      {hint && <p className="mt-1 text-xs text-[var(--color-muted)]">{hint}</p>}
    </div>
  );
}

/** The actual voice controls — reused by the modal (mobile) and the inline
 * right-rail (desktop, ElevenLabs-style). */
export function SettingsControls() {
  const rate = useStore((s) => s.rate);
  const pitch = useStore((s) => s.pitch);
  const volume = useStore((s) => s.volume);
  const setRate = useStore((s) => s.setRate);
  const setPitch = useStore((s) => s.setPitch);
  const setVolume = useStore((s) => s.setVolume);
  const emotion = useStore((s) => s.emotion);
  const setEmotion = useStore((s) => s.setEmotion);
  const intensity = useStore((s) => s.intensity);
  const setIntensity = useStore((s) => s.setIntensity);
  const meter = useStore((s) => s.meter);
  const setMeter = useStore((s) => s.setMeter);
  const activeVoice = useStore((s) => s.activeVoice());

  const serverVoice = activeVoice?.provider === 'server';
  // Vāgdhenu chant voice: expose the Sanskrit metre; hide emotion (n/a).
  const isChant = !!activeVoice?.chant;
  const supportsEmotion = serverVoice && !isChant;
  const expressive = !!activeVoice?.expressive;

  return (
    <div>
      {isChant && (
        <div className="py-3">
          <label className="mb-1 block text-sm font-medium">Sanskrit metre (chandas)</label>
          <select
            value={meter}
            onChange={(e) => setMeter(e.target.value)}
            aria-label="Sanskrit metre"
            className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm focus:border-[var(--color-accent)] focus:outline-none"
          >
            <option value="anushtubh">Anuṣṭubh / Śloka (most common)</option>
            <option value="upajāti">Upajāti</option>
            <option value="indravajrā">Indravajrā</option>
            <option value="vasantatilakā">Vasantatilakā</option>
            <option value="mālinī">Mālinī</option>
            <option value="drutavilambita">Drutavilambita</option>
            <option value="bhujaṅgaprayāta">Bhujaṅgaprayāta</option>
            <option value="śārdūlavikrīḍita">Śārdūlavikrīḍita</option>
            <option value="sragdharā">Sragdharā</option>
            <option value="gadya">Gadya (prose — non-metered)</option>
          </select>
          <p className="mt-1 text-xs text-[var(--color-muted)]">
            Vāgdhenu chants metered verse — enter Devanagari ślokas, one pāda per
            line. Use <span className="font-medium">Gadya</span> for prose.
            Unknown metres fall back to Vasantatilakā.
          </p>
        </div>
      )}
      {supportsEmotion && (
        <div className="py-3">
          <label className="mb-1 block text-sm font-medium">Emotion</label>
          <select
            value={emotion}
            onChange={(e) => setEmotion(e.target.value)}
            aria-label="Emotion"
            className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm focus:border-[var(--color-accent)] focus:outline-none"
          >
            <option value="auto">✨ Auto — match the scenario</option>
            <option value="neutral">Neutral</option>
            <optgroup label="Caring">
              <option value="sympathetic">Sympathetic</option>
              <option value="empathetic">Empathetic</option>
              <option value="reassuring">Reassuring</option>
              <option value="apologetic">Apologetic</option>
              <option value="grateful">Grateful</option>
              <option value="hopeful">Hopeful</option>
            </optgroup>
            <optgroup label="Feelings">
              <option value="happy">Happy</option>
              <option value="sad">Sad</option>
              <option value="angry">Angry</option>
              <option value="fear">Fearful</option>
              <option value="surprise">Surprised</option>
              <option value="disgust">Disgusted</option>
              <option value="excited">Excited</option>
              <option value="calm">Calm</option>
              <option value="romantic">Romantic</option>
            </optgroup>
            <optgroup label="Delivery style">
              <option value="narration">Narration</option>
              <option value="conversation">Conversational</option>
              <option value="news">News anchor</option>
              <option value="command">Commanding</option>
              <option value="serious">Serious</option>
              <option value="confident">Confident</option>
              <option value="urgent">Urgent</option>
              <option value="whisper">Whisper</option>
              <option value="sarcastic">Sarcastic</option>
            </optgroup>
          </select>
          <p className="mt-1 text-xs text-[var(--color-muted)]">
            {emotion === 'auto'
              ? 'Reads each sentence and picks the feeling it calls for — e.g. a condolence is spoken with sympathy, the reassurance after it warmly.'
              : expressive
                ? 'Shapes delivery + tone (strongest on these Expressive voices).'
                : 'Shapes delivery on this voice. Expressive voices react most.'}
          </p>
          {emotion !== 'neutral' && (
            <div className="mt-3">
              <Slider
                label="Emotion intensity"
                value={intensity}
                min={0}
                max={2}
                step={0.1}
                onChange={setIntensity}
                hint="0 = subtle, 1 = normal, 2 = dramatic"
              />
            </div>
          )}
        </div>
      )}
      <Slider
        label="Rate (speed)"
        value={rate}
        min={0.5}
        max={1.5}
        step={0.05}
        onChange={setRate}
        hint="Capped at 1.5× — higher speeds clip word endings."
      />
      <Slider label="Pitch" value={pitch} min={0.5} max={2} step={0.05} onChange={setPitch} />
      <Slider label="Volume" value={volume} min={0} max={1.5} step={0.05} onChange={setVolume} />
      <p className="mt-2 text-xs text-[var(--color-muted)]">
        Applies on next generate. Out-of-range values are clamped automatically.
      </p>
    </div>
  );
}

/** Inline rail shown on large screens (right side of the studio). */
export function SettingsRail() {
  const reset = useStore((s) => s.resetSettings);
  const save = useStore((s) => s.saveSettings);
  return (
    <aside className="hidden w-80 shrink-0 flex-col overflow-y-auto border-l border-[var(--color-border)] bg-[var(--color-surface)] xl:flex">
      <div className="flex items-center justify-between border-b border-[var(--color-border)] px-5 py-4">
        <h2 className="text-sm font-semibold tracking-tight">Voice settings</h2>
        <button
          onClick={reset}
          className="text-xs text-[var(--color-muted)] hover:text-[var(--color-accent)]"
        >
          Reset
        </button>
      </div>
      <div className="px-5 py-2">
        <SettingsControls />
        <button
          onClick={save}
          className="mt-2 mb-4 flex w-full items-center justify-center gap-2 rounded-lg bg-[var(--color-accent)] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[var(--color-accent-hover)]"
        >
          <Save size={15} /> Save as default
        </button>
      </div>
    </aside>
  );
}

/** Modal version — used on small screens (gear button in the studio bar). */
export function SettingsPanel() {
  const open = useStore((s) => s.overlay === 'settings');
  const close = useStore((s) => s.closeOverlay);
  const reset = useStore((s) => s.resetSettings);
  const save = useStore((s) => s.saveSettings);

  return (
    <Overlay
      open={open}
      onClose={close}
      title="Voice settings"
      footer={
        <div className="flex items-center justify-between gap-2">
          <Button variant="ghost" onClick={reset}>
            Reset
          </Button>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={save}>
              Save as default
            </Button>
            <Button variant="primary" onClick={close}>
              Done
            </Button>
          </div>
        </div>
      }
    >
      <SettingsControls />
    </Overlay>
  );
}
