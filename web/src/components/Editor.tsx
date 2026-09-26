import { useMemo, useRef, useEffect } from 'react';
import { useStore } from '../state/store';
import { sanitizePaste, CHAR_CAP, wordCount } from '../lib/sanitize';
import { Button } from './ui/Button';

export function Editor() {
  const text = useStore((s) => s.text);
  const setText = useStore((s) => s.setText);
  const clearText = useStore((s) => s.clearText);
  const status = useStore((s) => s.status);
  const highlightIndex = useStore((s) => s.highlightIndex);
  const taRef = useRef<HTMLTextAreaElement>(null);

  const chars = text.length;
  const words = wordCount(text);
  const over = chars > CHAR_CAP;
  const speaking = status === 'playing' || status === 'paused';

  // Split into word tokens for highlight rendering.
  const tokens = useMemo(() => text.split(/(\s+)/), [text]);

  // Keep the active word scrolled into view while reading.
  const activeRef = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (speaking) activeRef.current?.scrollIntoView({ block: 'nearest' });
  }, [highlightIndex, speaking]);

  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    e.preventDefault();
    const pasted = sanitizePaste(e.clipboardData.getData('text/plain'));
    const el = e.currentTarget;
    const next =
      text.slice(0, el.selectionStart) + pasted + text.slice(el.selectionEnd);
    setText(next.slice(0, CHAR_CAP));
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const v = e.target.value;
    if (v.length > CHAR_CAP) {
      setText(v.slice(0, CHAR_CAP));
    } else {
      setText(v);
    }
  };

  const handleClear = () => {
    if (text.length > 200) {
      if (!confirm('Clear all text? This cannot be undone.')) return;
    }
    clearText();
    taRef.current?.focus();
  };

  let wordCounter = -1;

  return (
    <div className="flex h-full flex-col">
      <div className="relative min-h-0 flex-1 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)]">
        {speaking ? (
          <div
            className="h-full w-full overflow-y-auto whitespace-pre-wrap px-5 py-4 text-lg leading-relaxed"
            aria-hidden
          >
            {tokens.map((tok, i) => {
              if (/^\s+$/.test(tok)) return <span key={i}>{tok}</span>;
              wordCounter += 1;
              const isActive = wordCounter === highlightIndex;
              return (
                <span
                  key={i}
                  ref={isActive ? activeRef : undefined}
                  className={isActive ? 'vf-word-active' : undefined}
                >
                  {tok}
                </span>
              );
            })}
          </div>
        ) : (
          <textarea
            ref={taRef}
            value={text}
            onChange={handleChange}
            onPaste={handlePaste}
            placeholder="Start typing here or paste any text you want to turn into lifelike speech…"
            aria-label="Text to speak"
            className="h-full w-full resize-none bg-transparent px-5 py-4 text-lg leading-relaxed text-[var(--color-fg)] placeholder:text-[var(--color-muted)] focus:outline-none"
          />
        )}
      </div>

      <div className="mt-2 flex items-center justify-between text-sm">
        <span
          className={over ? 'font-medium text-[var(--color-error)]' : 'text-[var(--color-muted)]'}
          aria-live="polite"
        >
          {words} words · {chars} / {CHAR_CAP} chars
          {over && ' — over limit'}
        </span>
        <Button
          variant="ghost"
          onClick={handleClear}
          disabled={!text}
          disabledReason="Nothing to clear"
        >
          Clear
        </Button>
      </div>

      {over && (
        <p className="mt-1 text-sm text-[var(--color-error)]" role="alert">
          Text exceeds the {CHAR_CAP.toLocaleString()} character cap. Extra input
          is blocked — trim or split your text.
        </p>
      )}
    </div>
  );
}
