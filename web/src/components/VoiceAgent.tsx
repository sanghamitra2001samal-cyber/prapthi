import { useRef, useState } from 'react';
import { Bot, Mic, Square, Send, Loader2, User } from 'lucide-react';
import { useStore } from '../state/store';
import * as tools from '../lib/tools';

export function VoiceAgent() {
  const toast = useStore((s) => s.toast);
  const [history, setHistory] = useState<tools.ChatMsg[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const recRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const play = (uri: string) => {
    if (!audioRef.current) audioRef.current = new Audio();
    audioRef.current.src = uri;
    void audioRef.current.play();
  };

  const sendText = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput('');
    setHistory((h) => [...h, { role: 'user', content: text }]);
    setBusy(true);
    try {
      const r = await tools.agentChat(text, history);
      setHistory((h) => [...h, { role: 'assistant', content: r.reply }]);
      play(r.audio);
    } catch (e) {
      toast({ kind: 'error', message: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const startRec = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      chunksRef.current = [];
      rec.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        const file = new File([blob], 'turn.webm', { type: 'audio/webm' });
        setBusy(true);
        try {
          const r = await tools.agentVoice(file, history);
          setHistory((h) => [
            ...h,
            { role: 'user', content: r.transcript },
            { role: 'assistant', content: r.reply },
          ]);
          play(r.audio);
        } catch (e) {
          toast({ kind: 'error', message: (e as Error).message });
        } finally {
          setBusy(false);
        }
      };
      rec.start();
      recRef.current = rec;
      setRecording(true);
    } catch {
      toast({ kind: 'error', message: 'Mic access denied or unavailable.' });
    }
  };
  const stopRec = () => {
    recRef.current?.stop();
    setRecording(false);
  };

  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col px-4 py-6 md:px-8">
      <div className="mb-2 flex items-center gap-2">
        <Bot size={20} className="text-[var(--color-accent)]" />
        <h2 className="text-xl font-bold tracking-tight">Voice Agent</h2>
        <span className="rounded-full bg-[var(--color-accent)]/15 px-2 py-0.5 text-[11px] font-semibold text-[var(--color-accent)]">
          Hindi + English
        </span>
      </div>
      <p className="mb-4 text-sm text-[var(--color-muted)]">
        Talk or type — Prapthi listens, thinks, and replies in your language with a real voice.
        Fully self-hosted, private, and API-free.
      </p>

      <div className="mb-4 flex-1 space-y-3 overflow-y-auto rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
        {history.length === 0 && (
          <p className="py-10 text-center text-sm text-[var(--color-muted)]">
            Say “नमस्ते” or ask anything to begin.
          </p>
        )}
        {history.map((m, i) => (
          <div key={i} className={`flex gap-2 ${m.role === 'user' ? 'justify-end' : ''}`}>
            {m.role === 'assistant' && <Bot size={18} className="mt-1 shrink-0 text-[var(--color-accent)]" />}
            <div className={`max-w-[80%] rounded-2xl px-3.5 py-2 text-sm ${
              m.role === 'user'
                ? 'bg-[var(--color-accent)] text-white'
                : 'bg-[var(--color-surface-2)]'
            }`}>{m.content}</div>
            {m.role === 'user' && <User size={18} className="mt-1 shrink-0 text-[var(--color-muted)]" />}
          </div>
        ))}
        {busy && (
          <div className="flex items-center gap-2 text-sm text-[var(--color-muted)]">
            <Loader2 size={16} className="animate-spin" /> Prapthi is thinking…
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        {!recording ? (
          <button onClick={startRec} disabled={busy}
            className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50" title="Hold to talk">
            <Mic size={18} />
          </button>
        ) : (
          <button onClick={stopRec}
            className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[var(--color-error)] text-white animate-pulse" title="Stop">
            <Square size={16} />
          </button>
        )}
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && sendText()}
          placeholder={recording ? 'Listening…' : 'Type a message, or tap the mic…'}
          disabled={busy || recording}
          className="flex-1 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2.5 text-sm focus:border-[var(--color-accent)] focus:outline-none"
        />
        <button onClick={sendText} disabled={busy || !input.trim()}
          className="grid h-11 w-11 shrink-0 place-items-center rounded-full border border-[var(--color-border)] hover:border-[var(--color-accent)] disabled:opacity-40">
          <Send size={17} />
        </button>
      </div>
    </div>
  );
}
