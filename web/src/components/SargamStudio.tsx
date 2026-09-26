import { useState } from 'react';
import { Music2, Play, Download, Loader2, Wand2, Mic } from 'lucide-react';
import { useStore } from '../state/store';
import * as melody from '../lib/melody';

const SYSTEMS: Array<[string, string]> = [
  ['sargam', 'Sargam (Sa Re Ga Ma)'],
  ['solfege', 'Solfège (Do Re Mi)'],
  ['western', 'Letter notes (C D E)'],
];

const TONICS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];

// Pitched instruments the engine can render (General-MIDI soundfont).
const INSTRUMENTS: Array<[string, string[]]> = [
  ['Indian', ['sitar', 'bansuri', 'santoor', 'veena', 'sarangi', 'shehnai', 'sarod', 'harmonium', 'tanpura']],
  ['Keys', ['grand piano', 'electric piano', 'organ', 'accordion', 'harp', 'celesta']],
  ['Strings', ['solo violin', 'viola', 'cello', 'string ensemble', 'double bass']],
  ['Guitars', ['acoustic guitar', 'classical guitar', 'electric guitar', 'ukulele', 'mandolin']],
  ['Winds & Brass', ['concert flute', 'clarinet', 'oboe', 'saxophone', 'trumpet', 'trombone', 'french horn', 'brass ensemble']],
  ['Mallets & World', ['marimba', 'xylophone', 'kalimba', 'steel drums', 'oud', 'pan flute', 'bells']],
  ['Synth', ['synth lead', 'synth pad', 'analog synth', 'pluck synth']],
  ['Voice', ['choir', 'vocal pads']],
];

const REFERENCE: Record<string, { title: string; rows: Array<[string, string]>; help: string }> = {
  sargam: {
    title: 'Sargam reference (Sa = your key)',
    rows: [
      ['S', 'Sa'], ['r / R', 'komal / shuddha Re'], ['g / G', 'komal / shuddha Ga'],
      ['M / m', 'shuddha / tivra Ma'], ['P', 'Pa'], ['d / D', 'komal / shuddha Dha'],
      ['n / N', 'komal / shuddha Ni'],
    ],
    help: "Octave: add ' for higher (S') or , for lower (S,). Hold a note with - (S-- = 3 beats). Rest with _ . Bar lines | are ignored.",
  },
  solfege: {
    title: 'Solfège reference',
    rows: [['do re mi fa', 'sol la ti'], ['di ri fi si li', 'chromatic (sharps)'], ['ra me se le te', 'chromatic (flats)']],
    help: "Octave: do' higher, do, lower. Hold with - , rest with _ .",
  },
  western: {
    title: 'Letter-note reference',
    rows: [['C D E F G A B', 'natural notes'], ['C# / Db', 'sharp / flat'], ['C4 / C5', 'octave number (default 4)']],
    help: 'Example: C D E F G A B C5. Hold with - , rest with _ .',
  },
};

const EXAMPLES: Record<string, Array<[string, string]>> = {
  sargam: [
    ['Aaroh–Avroh (scale up & down)', "S R G M P D N S'  S' N D P M G R S"],
    ['Sa Re Ga Ma phrase', 'S R G M G R S -  P M G R S -'],
    ['Bhajan-style', "S R G - M G R S -  G M P - D P M G -"],
  ],
  solfege: [['C-major scale', "do re mi fa sol la ti do'"], ['Twinkle Twinkle', 'do do sol sol la la sol -  fa fa mi mi re re do -']],
  western: [['C-major scale', 'C D E F G A B C5'], ['Arpeggio', 'C E G C5 G E C -']],
};

export function SargamStudio({ onView }: { onView?: (v: string) => void }) {
  const toast = useStore((s) => s.toast);
  const setPendingMelody = useStore((s) => s.setPendingMelody);
  const [system, setSystem] = useState('sargam');
  const [tonic, setTonic] = useState('C');
  const [instrument, setInstrument] = useState('sitar');
  const [bpm, setBpm] = useState(90);
  const [notation, setNotation] = useState("S R G M P D N S'");
  const [busy, setBusy] = useState(false);
  const [url, setUrl] = useState<string | null>(null);

  const ref = REFERENCE[system];

  const render = async () => {
    if (!notation.trim()) {
      toast({ kind: 'error', message: 'Enter a melody first.' });
      return;
    }
    setBusy(true);
    try {
      const u = await melody.renderMelody({ notation, system, tonic, instrument, bpm });
      if (url) URL.revokeObjectURL(url);
      setUrl(u);
      toast({ kind: 'success', message: 'Melody rendered!' });
    } catch (e) {
      toast({ kind: 'error', message: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const sendToSong = () => {
    if (!notation.trim()) {
      toast({ kind: 'error', message: 'Enter a melody first.' });
      return;
    }
    setPendingMelody({ notation, system, tonic, bpm });
    toast({ kind: 'success', message: 'Melody sent to Create Song’s melody guide.' });
    onView?.('createsong');
  };

  const label = 'mb-1 block text-sm font-medium';
  const field =
    'w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm focus:border-[var(--color-accent)] focus:outline-none';

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6 md:px-8 md:py-8">
      <div className="mb-2 flex items-center gap-2">
        <Music2 size={20} className="text-[var(--color-accent)]" />
        <h2 className="text-xl font-bold tracking-tight">Sargam Studio</h2>
        <span className="rounded-full bg-[var(--color-accent)]/15 px-2 py-0.5 text-[11px] font-semibold text-[var(--color-accent)]">
          exact notes
        </span>
      </div>
      <p className="mb-6 text-sm text-[var(--color-muted)]">
        Compose an exact melody in Sa Re Ga Ma, solfège, or letter notes — rendered perfectly in tune
        in any instrument. The notes are universal; only the notation changes.
      </p>

      <div className="space-y-5">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div className="col-span-2">
            <label className={label}>Notation system</label>
            <select className={field} value={system} onChange={(e) => setSystem(e.target.value)}>
              {SYSTEMS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
            </select>
          </div>
          <div>
            <label className={label}>Key (Sa =)</label>
            <select className={field} value={tonic} onChange={(e) => setTonic(e.target.value)}>
              {TONICS.map((k) => <option key={k} value={k}>{k}</option>)}
            </select>
          </div>
          <div>
            <label className={label}>Tempo (BPM)</label>
            <input
              type="number" min={30} max={300} className={field}
              value={bpm} onChange={(e) => setBpm(Number(e.target.value) || 90)}
            />
          </div>
          <div className="col-span-2 sm:col-span-4">
            <label className={label}>Instrument</label>
            <select className={field} value={instrument} onChange={(e) => setInstrument(e.target.value)}>
              {INSTRUMENTS.map(([group, items]) => (
                <optgroup key={group} label={group}>
                  {items.map((it) => <option key={it} value={it}>{it}</option>)}
                </optgroup>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label className={label}>Melody</label>
          <textarea
            className={`${field} min-h-[120px] resize-y font-mono`}
            value={notation}
            onChange={(e) => setNotation(e.target.value)}
            placeholder="S R G M P D N S'"
          />
        </div>

        {/* Examples */}
        <div className="flex flex-wrap gap-2">
          {(EXAMPLES[system] ?? []).map(([name, val]) => (
            <button
              key={name}
              onClick={() => setNotation(val)}
              className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-fg)]"
            >
              <Wand2 size={12} /> {name}
            </button>
          ))}
        </div>

        <button
          onClick={render}
          disabled={busy}
          className="flex w-full items-center justify-center gap-2 rounded-full bg-[var(--color-accent)] px-6 py-3.5 text-sm font-semibold text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
        >
          {busy ? <Loader2 size={17} className="animate-spin" /> : <Play size={17} />}
          {busy ? 'Rendering…' : 'Render melody'}
        </button>

        {onView && (
          <button
            onClick={sendToSong}
            className="flex w-full items-center justify-center gap-2 rounded-full border border-[var(--color-border)] px-6 py-3 text-sm font-semibold hover:border-[var(--color-accent)]"
          >
            <Mic size={16} /> Use as song melody (Create Song)
          </button>
        )}

        {url && (
          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
            <p className="mb-2 text-xs uppercase tracking-wide text-[var(--color-muted)]">
              {instrument} · key of {tonic} · {bpm} BPM
            </p>
            <audio controls src={url} className="w-full" autoPlay />
            <div className="mt-3 flex flex-wrap gap-2">
              <a
                href={url}
                download={`melody-${instrument.replace(/\s+/g, '-')}.mp3`}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--color-accent-hover)]"
              >
                <Download size={15} /> Download MP3
              </a>
              {onView && (
                <button
                  onClick={sendToSong}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm font-medium hover:border-[var(--color-accent)]"
                >
                  <Mic size={15} /> Use as song melody
                </button>
              )}
            </div>
          </div>
        )}

        {/* Reference */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
            {ref.title}
          </p>
          <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
            {ref.rows.map(([k, v]) => (
              <div key={k} className="flex items-center gap-2 text-xs">
                <code className="rounded bg-[var(--color-surface-2)] px-1.5 py-0.5 font-mono text-[var(--color-accent)]">{k}</code>
                <span className="text-[var(--color-muted)]">{v}</span>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-[var(--color-muted)]">{ref.help}</p>
        </div>

        <p className="text-center text-xs text-[var(--color-muted)]">
          Deterministic, perfectly in-tune playback — fully self-hosted, no third-party API.
        </p>
      </div>
    </div>
  );
}
