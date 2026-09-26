import { useEffect, useRef, useState } from 'react';
import { Music, Sparkles, Wand2, Download, Loader2, Upload, Play } from 'lucide-react';
import { useStore } from '../state/store';
import * as songApi from '../lib/song';
import * as melodyApi from '../lib/melody';

const GENRES = [
  ['pop', 'Pop'], ['bollywood', 'Bollywood'], ['lofi', 'Lo-Fi'],
  ['hiphop', 'Hip-Hop'], ['rock', 'Rock'], ['edm', 'EDM'],
  ['rnb', 'R&B'], ['classical', 'Classical'],
] as const;
const DURATIONS = [
  [20, '~20s (quick)'], [40, '~40s'], [60, '1 min'], [120, '2 min'], [180, '3 min'],
] as const;
const LANGS = [
  ['en', 'English'], ['hi', 'Hindi'], ['sa', 'Sanskrit'], ['te', 'Telugu'],
  ['ta', 'Tamil'], ['pa', 'Punjabi'], ['hinglish', 'Hinglish (mixed)'],
] as const;
const MOODS = [
  ['', 'Auto (from script)'], ['happy', 'Happy'], ['sad', 'Sad'],
  ['romantic', 'Romantic'], ['motivational', 'Motivational'], ['chill', 'Chill'],
  ['party', 'Party'], ['dreamy', 'Dreamy'], ['dark', 'Dark'], ['epic', 'Epic'],
] as const;
const STYLES = [
  ['', 'Auto'], ['soulful', 'Soulful'], ['powerful', 'Powerful'],
  ['soft', 'Soft & breathy'], ['raspy', 'Raspy'], ['smooth', 'Smooth'],
  ['rap', 'Rap flow'], ['classical', 'Classical'], ['autotune', 'Autotune'],
] as const;
const BPMS = [
  ['', 'Auto'], ['70', 'Slow (70)'], ['90', 'Medium (90)'],
  ['110', 'Upbeat (110)'], ['128', 'Dance (128)'], ['150', 'Fast (150)'],
] as const;
const KEYS = [
  '', 'C major', 'G major', 'D major', 'A major', 'F major',
  'A minor', 'E minor', 'D minor', 'C minor', 'G minor',
] as const;

// Curated instrument palette (a tasteful subset of the full engine taxonomy),
// grouped for the picker. Leaving all unchecked = auto-select by genre/mood.
const INSTRUMENT_GROUPS: Array<[string, string[]]> = [
  ['Percussion', ['drum kit', '808 bass', 'tabla', 'dhol', 'congas', 'cajón', 'electronic drum machine', 'epic drums', 'taiko', 'timpani']],
  ['Bass', ['electric bass', 'acoustic bass', 'upright bass', 'synth bass', 'sub bass']],
  ['Keys', ['grand piano', 'electric piano', 'organ', 'harmonium', 'accordion', 'harp', 'synth pad', 'ambient pads']],
  ['Guitars', ['acoustic guitar', 'classical guitar', 'electric guitar', 'lead guitar', 'ukulele', 'mandolin']],
  ['Strings', ['solo violin', 'string ensemble', 'viola', 'cello', 'double bass']],
  ['Winds & Brass', ['concert flute', 'bansuri flute', 'clarinet', 'saxophone', 'trumpet', 'trombone', 'french horn', 'brass ensemble']],
  ['Indian Classical', ['sitar', 'sarod', 'santoor', 'veena', 'sarangi', 'shehnai', 'tanpura', 'mridangam']],
  ['Electronic', ['synth lead', 'analog synth', 'pluck synth', 'arpeggiator', 'fx synth']],
  ['Choir & Vocals', ['choir', 'backing vocals', 'vocal harmonies', 'vocal chops', 'ad-libs']],
  ['Cinematic', ['full orchestra', 'cinematic percussion', 'bells', 'chimes', 'celesta']],
  ['World', ['oud', 'duduk', 'pan flute', 'steel drums', 'kalimba', 'marimba', 'xylophone']],
  ['Ambient FX', ['rain', 'ocean waves', 'wind', 'vinyl crackle', 'riser', 'downlifter', 'impact', 'whoosh']],
];

export function CreateSong({ onView }: { onView: (v: string) => void }) {
  const toast = useStore((s) => s.toast);
  const pendingMelody = useStore((s) => s.pendingMelody);
  const setPendingMelody = useStore((s) => s.setPendingMelody);

  const [title, setTitle] = useState('');
  const [script, setScript] = useState('');
  const [genre, setGenre] = useState('pop');
  const [language, setLanguage] = useState('en');
  const [vocals, setVocals] = useState('female');
  const [duration, setDuration] = useState(40);
  const [mood, setMood] = useState('');
  const [singerStyle, setSingerStyle] = useState('');
  const [bpm, setBpm] = useState('');
  const [musicalKey, setMusicalKey] = useState('');
  const [refVoiceId, setRefVoiceId] = useState('');
  const [rvcVoice, setRvcVoice] = useState('');
  const [clones, setClones] = useState<songApi.CloneVoice[]>([]);
  const [instruments, setInstruments] = useState<string[]>([]);
  const [instrOpen, setInstrOpen] = useState(false);
  // Melody guide (Sargam → AI vocals follow the tune via audio-to-audio).
  const [melodyOpen, setMelodyOpen] = useState(false);
  const [melOn, setMelOn] = useState(false);
  const [melNotation, setMelNotation] = useState("S R G M P D N S'");
  const [melSystem, setMelSystem] = useState('sargam');
  const [melTonic, setMelTonic] = useState('C');
  const [melBpm, setMelBpm] = useState(90);
  const [melStrength, setMelStrength] = useState(0.6);
  const [melPreviewUrl, setMelPreviewUrl] = useState<string | null>(null);
  const [melPreviewing, setMelPreviewing] = useState(false);
  const [lyrics, setLyrics] = useState('');
  const [emotion, setEmotion] = useState<songApi.EmotionResult | null>(null);
  const [analyzing, setAnalyzing] = useState(false);

  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<songApi.SongRow | null>(null);
  const poll = useRef<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  // Load the user's own cloned voices for "Sing in my voice".
  useEffect(() => {
    songApi.listCloneVoices().then(setClones).catch(() => setClones([]));
  }, []);

  // A melody composed in Sargam Studio → preload the melody guide.
  useEffect(() => {
    if (!pendingMelody) return;
    setMelNotation(pendingMelody.notation);
    setMelSystem(pendingMelody.system);
    setMelTonic(pendingMelody.tonic);
    setMelBpm(pendingMelody.bpm);
    setMelOn(true);
    setMelodyOpen(true);
    setPendingMelody(null);
    toast({ kind: 'info', message: 'Melody guide loaded from Sargam Studio.' });
  }, [pendingMelody, setPendingMelody, toast]);

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setUploading(true);
    try {
      const { text } = await songApi.extractFile(f);
      setScript(text);
      if (!title) setTitle(f.name.replace(/\.[^.]+$/, '').slice(0, 80));
      toast({ kind: 'success', message: 'Script loaded from file.' });
    } catch (err) {
      toast({ kind: 'error', message: (err as Error).message });
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const words = script.trim() ? script.trim().split(/\s+/).length : 0;

  const toggleInstr = (name: string) =>
    setInstruments((cur) =>
      cur.includes(name) ? cur.filter((x) => x !== name) : [...cur, name]
    );

  const previewMelody = async () => {
    if (!melNotation.trim()) return;
    setMelPreviewing(true);
    try {
      const u = await melodyApi.renderMelody({
        notation: melNotation, system: melSystem, tonic: melTonic,
        instrument: 'concert flute', bpm: melBpm,
      });
      if (melPreviewUrl) URL.revokeObjectURL(melPreviewUrl);
      setMelPreviewUrl(u);
    } catch (e) {
      toast({ kind: 'error', message: (e as Error).message });
    } finally {
      setMelPreviewing(false);
    }
  };

  const analyze = async () => {
    if (words < 5) {
      toast({ kind: 'error', message: 'Write a few sentences first.' });
      return;
    }
    setAnalyzing(true);
    try {
      const r = await songApi.analyzeScript(script, title || 'Untitled', {
        language,
        genre,
        mood: mood || undefined,
      });
      setEmotion(r.emotion);
      setLyrics(r.lyrics);
      if (!title) setTitle(r.title);
      toast({ kind: 'success', message: `Detected mood: ${r.emotion.dominant}.` });
    } catch (e) {
      toast({ kind: 'error', message: (e as Error).message });
    } finally {
      setAnalyzing(false);
    }
  };

  const generate = async () => {
    if (words < 5) {
      toast({ kind: 'error', message: 'Write a longer script first.' });
      return;
    }
    try {
      const { id } = await songApi.createSong({
        script, title: title || 'Untitled', genre, language,
        vocals, emotion: emotion?.dominant, lyrics, duration,
        mood: mood || undefined,
        singer_style: singerStyle || undefined,
        bpm: bpm ? Number(bpm) : undefined,
        musical_key: musicalKey || undefined,
        ref_voice_id: refVoiceId || undefined,
        timbre: rvcVoice || undefined,
        instruments: instruments.length ? instruments : undefined,
        melody:
          melOn && melNotation.trim()
            ? {
                notation: melNotation, system: melSystem, tonic: melTonic,
                bpm: melBpm, strength: melStrength,
              }
            : undefined,
      });
      setJobId(id);
      setJob({ id, status: 'queued', progress: 0, current_step: 'Queued' } as songApi.SongRow);
    } catch (e) {
      toast({ kind: 'error', message: (e as Error).message });
    }
  };

  // poll job status
  useEffect(() => {
    if (!jobId) return;
    const tick = async () => {
      try {
        const s = await songApi.getSong(jobId);
        setJob(s);
        if (s.status === 'done') {
          toast({ kind: 'success', message: 'Song generated!' });
          if (poll.current) window.clearInterval(poll.current);
        } else if (s.status === 'failed') {
          toast({ kind: 'error', message: s.error || 'Generation failed.' });
          if (poll.current) window.clearInterval(poll.current);
        }
      } catch {
        /* keep polling */
      }
    };
    poll.current = window.setInterval(tick, 3000);
    void tick();
    return () => {
      if (poll.current) window.clearInterval(poll.current);
    };
  }, [jobId, toast]);

  const busy = job && (job.status === 'queued' || job.status === 'processing');
  const done = job && job.status === 'done';

  const reset = () => {
    setJobId(null);
    setJob(null);
  };

  const label = 'mb-1 block text-sm font-medium';
  const field =
    'w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm focus:border-[var(--color-accent)] focus:outline-none';

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6 md:px-8 md:py-8">
      <div className="mb-6 flex items-center gap-2">
        <Music size={20} className="text-[var(--color-accent)]" />
        <h2 className="text-xl font-bold tracking-tight">Create a Song</h2>
        <span className="rounded-full bg-[var(--color-accent)]/15 px-2 py-0.5 text-[11px] font-semibold text-[var(--color-accent)]">
          EmotionSong
        </span>
      </div>

      {/* Progress / result panel */}
      {job && (
        <div className="mb-6 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          {busy && (
            <>
              <div className="mb-2 flex items-center gap-2 text-sm font-medium">
                <Loader2 size={16} className="animate-spin text-[var(--color-accent)]" />
                {job.current_step}…
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-[var(--color-surface-2)]">
                <div
                  className="h-full rounded-full bg-[var(--color-accent)] transition-[width] duration-500"
                  style={{ width: `${job.progress}%` }}
                />
              </div>
              <p className="mt-2 text-xs text-[var(--color-muted)]">
                Composing music + emotional vocals — this can take a minute.
              </p>
            </>
          )}
          {done && (
            <>
              <p className="mb-1 text-xs uppercase tracking-wide text-[var(--color-muted)]">
                {job.genre} · {job.emotion} · {job.duration_seconds}s
              </p>
              <p className="mb-3 text-lg font-semibold">{job.title}</p>
              <audio controls src={songApi.songAudioUrl(job.id)} className="w-full" />
              <div className="mt-3 flex gap-2">
                <a
                  href={songApi.songAudioUrl(job.id)}
                  download
                  className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--color-accent-hover)]"
                >
                  <Download size={15} /> Download MP3
                </a>
                <button onClick={reset} className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm hover:bg-[var(--color-surface-2)]">
                  Create another
                </button>
                <button onClick={() => onView('mysongs')} className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm hover:bg-[var(--color-surface-2)]">
                  My Songs
                </button>
              </div>
            </>
          )}
          {job.status === 'failed' && (
            <div>
              <p className="text-sm text-[var(--color-error)]">Generation failed.</p>
              <button onClick={reset} className="mt-2 rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm hover:bg-[var(--color-surface-2)]">
                Try again
              </button>
            </div>
          )}
        </div>
      )}

      {!busy && !done && (
        <div className="space-y-5">
          <div>
            <label className={label}>Song title</label>
            <input className={field} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="My new song" />
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <label className="text-sm font-medium">Your script / story / poem</label>
              <button
                onClick={() => fileRef.current?.click()}
                disabled={uploading}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-2.5 py-1 text-xs font-medium text-[var(--color-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-fg)] disabled:opacity-50"
              >
                {uploading ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
                Upload TXT / PDF / DOCX
              </button>
              <input
                ref={fileRef}
                type="file"
                accept=".txt,.pdf,.docx,.doc,text/plain,application/pdf"
                className="hidden"
                onChange={onFile}
              />
            </div>
            <textarea
              className={`${field} min-h-[160px] resize-y`}
              value={script}
              onChange={(e) => setScript(e.target.value)}
              placeholder="Paste a story, poem, dialogue, or idea. The AI turns it into a song…"
            />
            <div className="mt-1 flex items-center justify-between text-xs text-[var(--color-muted)]">
              <span>{words} words</span>
              <button
                onClick={analyze}
                disabled={analyzing}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-1.5 font-medium hover:border-[var(--color-accent)] disabled:opacity-50"
              >
                {analyzing ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                Analyze emotion + draft lyrics
              </button>
            </div>
          </div>

          {emotion && (
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
              <p className="mb-2 text-xs uppercase tracking-wide text-[var(--color-muted)]">
                Detected emotions · dominant: <span className="text-[var(--color-accent)]">{emotion.dominant}</span>
              </p>
              <div className="space-y-1.5">
                {Object.entries(emotion.scores)
                  .filter(([, v]) => v > 0)
                  .sort((a, b) => b[1] - a[1])
                  .slice(0, 5)
                  .map(([k, v]) => (
                    <div key={k} className="flex items-center gap-2 text-xs">
                      <span className="w-24 capitalize text-[var(--color-muted)]">{k}</span>
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--color-surface-2)]">
                        <div className="h-full rounded-full bg-[var(--color-accent)]" style={{ width: `${v}%` }} />
                      </div>
                      <span className="w-10 text-right text-[var(--color-muted)]">{v}%</span>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {lyrics && (
            <div>
              <label className={label}>Lyrics (editable)</label>
              <textarea className={`${field} min-h-[160px] resize-y font-mono text-xs`} value={lyrics} onChange={(e) => setLyrics(e.target.value)} />
            </div>
          )}

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div>
              <label className={label}>Genre</label>
              <select className={field} value={genre} onChange={(e) => setGenre(e.target.value)}>
                {GENRES.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
              </select>
            </div>
            <div>
              <label className={label}>Mood</label>
              <select className={field} value={mood} onChange={(e) => setMood(e.target.value)}>
                {MOODS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
              </select>
            </div>
            <div>
              <label className={label}>Language</label>
              <select className={field} value={language} onChange={(e) => setLanguage(e.target.value)}>
                {LANGS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
              </select>
            </div>
            <div>
              <label className={label}>Vocals</label>
              <select className={field} value={vocals} onChange={(e) => setVocals(e.target.value)}>
                <option value="female">Female</option>
                <option value="male">Male</option>
                <option value="duet">Duet</option>
              </select>
            </div>
            <div>
              <label className={label}>Singer style</label>
              <select className={field} value={singerStyle} onChange={(e) => setSingerStyle(e.target.value)}>
                {STYLES.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
              </select>
            </div>
            <div>
              <label className={label}>Tempo (BPM)</label>
              <select className={field} value={bpm} onChange={(e) => setBpm(e.target.value)}>
                {BPMS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
              </select>
            </div>
            <div>
              <label className={label}>Musical key</label>
              <select className={field} value={musicalKey} onChange={(e) => setMusicalKey(e.target.value)}>
                {KEYS.map((k) => <option key={k} value={k}>{k || 'Auto'}</option>)}
              </select>
            </div>
            <div>
              <label className={label}>Length</label>
              <select className={field} value={duration} onChange={(e) => setDuration(Number(e.target.value))}>
                {DURATIONS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
              </select>
            </div>
          </div>

          {/* Sing in my voice — uses one of the user's own cloned voices. */}
          <div>
            <label className={label}>Sing in my voice (optional)</label>
            <select
              className={field}
              value={refVoiceId}
              onChange={(e) => setRefVoiceId(e.target.value)}
              disabled={clones.length === 0}
            >
              <option value="">Default AI singer</option>
              {clones.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
            <p className="mt-1 text-xs text-[var(--color-muted)]">
              {clones.length === 0
                ? 'Clone a voice in the Studio to make the song sing in that voice.'
                : 'The song will be performed in your chosen cloned voice.'}
            </p>
          </div>

          {/* Indian voice (RVC) — converts the song's vocal timbre. */}
          <div>
            <label className={label}>Indian voice (timbre)</label>
            <select className={field} value={rvcVoice} onChange={(e) => setRvcVoice(e.target.value)}>
              <option value="">Off (default AI voice)</option>
              <option value="indian-female">Indian voice (real, female)</option>
              <option value="indian-male">Indian voice (real, male)</option>
            </select>
            <p className="mt-1 text-xs text-[var(--color-muted)]">
              Re-voices the song in a real Indian voice timbre. Note: this changes the
              voice tone only — Hindi singing fluency is still limited by the AI singer.
            </p>
          </div>

          {/* Instrument arrangement — optional explicit picks. */}
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]">
            <button
              type="button"
              onClick={() => setInstrOpen((o) => !o)}
              className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium"
            >
              <span>
                Instruments
                <span className="ml-2 text-xs font-normal text-[var(--color-muted)]">
                  {instruments.length ? `${instruments.length} selected` : 'Auto (by genre & mood)'}
                </span>
              </span>
              <span className="text-[var(--color-muted)]">{instrOpen ? '−' : '+'}</span>
            </button>
            {instrOpen && (
              <div className="space-y-3 border-t border-[var(--color-border)] px-4 py-3">
                {instruments.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setInstruments([])}
                    className="text-xs text-[var(--color-accent)] hover:underline"
                  >
                    Clear selection (back to auto)
                  </button>
                )}
                {INSTRUMENT_GROUPS.map(([group, items]) => (
                  <div key={group}>
                    <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-[var(--color-muted)]">
                      {group}
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {items.map((name) => {
                        const on = instruments.includes(name);
                        return (
                          <button
                            key={name}
                            type="button"
                            onClick={() => toggleInstr(name)}
                            className={
                              'rounded-full border px-2.5 py-1 text-xs capitalize transition ' +
                              (on
                                ? 'border-[var(--color-accent)] bg-[var(--color-accent)]/15 text-[var(--color-accent)]'
                                : 'border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-fg)]')
                            }
                          >
                            {name}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
                <p className="text-xs text-[var(--color-muted)]">
                  Leave empty to let the engine choose instruments automatically. Picks are blended with smart genre/mood defaults.
                </p>
              </div>
            )}
          </div>

          {/* Melody guide — the AI vocals follow a Sa Re Ga Ma tune. */}
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]">
            <button
              type="button"
              onClick={() => setMelodyOpen((o) => !o)}
              className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium"
            >
              <span>
                Melody guide <span className="ml-1 rounded-full bg-[var(--color-accent)]/15 px-1.5 py-0.5 text-[10px] font-semibold text-[var(--color-accent)]">Sa Re Ga Ma</span>
                <span className="ml-2 text-xs font-normal text-[var(--color-muted)]">
                  {melOn ? 'On — vocals follow your tune' : 'Off'}
                </span>
              </span>
              <span className="text-[var(--color-muted)]">{melodyOpen ? '−' : '+'}</span>
            </button>
            {melodyOpen && (
              <div className="space-y-3 border-t border-[var(--color-border)] px-4 py-3">
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={melOn} onChange={(e) => setMelOn(e.target.checked)} />
                  Make the AI singer follow this melody
                </label>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <div className="col-span-2">
                    <label className={label}>Notation</label>
                    <select className={field} value={melSystem} onChange={(e) => setMelSystem(e.target.value)}>
                      <option value="sargam">Sargam (Sa Re Ga Ma)</option>
                      <option value="solfege">Solfège (Do Re Mi)</option>
                      <option value="western">Letters (C D E)</option>
                    </select>
                  </div>
                  <div>
                    <label className={label}>Key (Sa =)</label>
                    <select className={field} value={melTonic} onChange={(e) => setMelTonic(e.target.value)}>
                      {['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'].map((k) => (
                        <option key={k} value={k}>{k}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className={label}>Tempo</label>
                    <input type="number" min={30} max={300} className={field} value={melBpm} onChange={(e) => setMelBpm(Number(e.target.value) || 90)} />
                  </div>
                </div>
                <div>
                  <label className={label}>Melody</label>
                  <textarea
                    className={`${field} min-h-[80px] resize-y font-mono`}
                    value={melNotation}
                    onChange={(e) => setMelNotation(e.target.value)}
                    placeholder="S R G M P D N S'"
                  />
                </div>
                <div>
                  <label className={label}>Guide strength: {Math.round(melStrength * 100)}%</label>
                  <input
                    type="range" min={0.2} max={0.9} step={0.05} value={melStrength}
                    onChange={(e) => setMelStrength(Number(e.target.value))}
                    className="w-full"
                  />
                  <p className="text-xs text-[var(--color-muted)]">
                    Higher = follows the tune more closely (but less lyrical freedom).
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={previewMelody}
                    disabled={melPreviewing}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium hover:border-[var(--color-accent)] disabled:opacity-50"
                  >
                    {melPreviewing ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
                    Preview tune
                  </button>
                  {melPreviewUrl && <audio controls src={melPreviewUrl} className="h-8 flex-1" />}
                </div>
                <p className="text-xs text-[var(--color-muted)]">
                  Tip: build full melodies in <strong>Sargam Studio</strong>. Guidance is best-effort — the AI follows the contour, it isn't strict note-for-note.
                </p>
              </div>
            )}
          </div>

          <button
            onClick={generate}
            disabled={words < 5}
            className="flex w-full items-center justify-center gap-2 rounded-full bg-[var(--color-accent)] px-6 py-3.5 text-sm font-semibold text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
          >
            <Wand2 size={17} /> Generate Song
          </button>
          <p className="text-center text-xs text-[var(--color-muted)]">
            AI beat + your emotional voice performing the lyrics. Fully private, no third-party API.
          </p>
        </div>
      )}
    </div>
  );
}
