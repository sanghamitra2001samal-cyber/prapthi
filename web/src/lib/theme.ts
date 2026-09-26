/* ------------------------------------------------------------------ */
/*  theme — dark / light for the authenticated app.                    */
/*                                                                    */
/*  The whole UI is built on `--color-*` design tokens, so switching   */
/*  theme is just toggling a class on <html> that overrides those      */
/*  tokens (see index.css `.theme-light`). Zero component changes,     */
/*  zero functional impact. Choice is persisted to localStorage.       */
/* ------------------------------------------------------------------ */
import { useEffect, useState } from 'react';

export type Theme = 'dark' | 'light';
const KEY = 'vf-theme';

export function getTheme(): Theme {
  try {
    const v = localStorage.getItem(KEY);
    if (v === 'light' || v === 'dark') return v;
    // No studio choice yet: follow the public site (same origin, its own key),
    // so the studio opens in the theme the visitor was already reading in.
    const site = localStorage.getItem('prapthi-theme');
    if (site === 'light' || site === 'dark') return site;
    if (site === 'system' || site === null) {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    return 'dark';
  } catch {
    return 'dark';
  }
}

export function applyTheme(t: Theme) {
  document.documentElement.classList.toggle('theme-light', t === 'light');
  try { localStorage.setItem(KEY, t); } catch { /* ignore */ }
  window.dispatchEvent(new CustomEvent('vf-theme', { detail: t }));
}

/** Apply the persisted theme as early as possible (called from main.tsx). */
export function initTheme() {
  applyTheme(getTheme());
}

/** React hook: current theme + a toggle, kept in sync across the app. */
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(getTheme);
  useEffect(() => {
    const on = (e: Event) => setTheme((e as CustomEvent).detail as Theme);
    window.addEventListener('vf-theme', on);
    return () => window.removeEventListener('vf-theme', on);
  }, []);
  const toggle = () => applyTheme(theme === 'dark' ? 'light' : 'dark');
  return [theme, toggle];
}
