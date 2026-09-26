/* Prapthi.ai — real speech for the public pages.
 *
 * The page's play buttons call Prapthi's own engines (api.prapthi.ai) so
 * visitors hear the actual product: real voices, real languages, real
 * emotion. The browser's built-in speechSynthesis is kept ONLY as a
 * fallback for when the API cannot be reached (offline, blocked, or the
 * page opened from a domain the API does not allow).
 */
'use strict';
window.PRAPTHI_API = (() => {
  const BASE = window.PRAPTHI_API_BASE || (location.hostname.endsWith('prapthi.ai') ? '/api' : 'https://api.prapthi.ai/api');
  // The public demo endpoint caps the text it will speak.
  const DEMO_LIMIT = 300;

  // Site language -> real voice ids (Svara: the engines that act emotion).
  const VOICES = {
    English:   { m: 'svara-en-m', f: 'svara-en-f' },
    Hindi:     { m: 'svara-hi-m', f: 'svara-hi-f' },
    Hinglish:  { m: 'svara-hi-m', f: 'svara-hi-f' }, // backend converts romanised Hindi
    Telugu:    { m: 'svara-te-m', f: 'svara-te-f' },
    Tamil:     { m: 'svara-ta-m', f: 'svara-ta-f' },
    Kannada:   { m: 'svara-kn-m', f: 'svara-kn-f' },
    Malayalam: { m: 'svara-ml-m', f: 'svara-ml-f' },
    Marathi:   { m: 'svara-mr-m', f: 'svara-mr-f' },
    Bengali:   { m: 'svara-bn-m', f: 'svara-bn-f' },
    Gujarati:  { m: 'svara-gu-m', f: 'svara-gu-f' },
    Punjabi:   { m: 'svara-pa-m', f: 'svara-pa-f' },
    Sanskrit:  { m: 'svara-sa-m', f: 'svara-sa-f' },
  };

  const GENDER = {
    Aarav: 'm', Kabir: 'm', Rohan: 'm', Vikram: 'm',
    Meera: 'f', Diya: 'f', Ananya: 'f', Leela: 'f',
  };

  // Site wording -> the backend's feelings (see the studio's Emotion list).
  const EMOTION = {
    Calm: 'calm', Warm: 'reassuring', Confident: 'confident',
    Storytelling: 'narration', Storyteller: 'narration', Professional: 'news',
    Joyful: 'happy', Sarcastic: 'sarcastic', Hopeful: 'hopeful',
    Authoritative: 'command', Gentle: 'empathetic', Energetic: 'excited',
    Expressive: 'excited', Conversational: 'conversation',
    Conversation: 'conversation', Narration: 'narration',
    Natural: 'neutral', Real: 'neutral', Deep: 'serious',
    Sympathetic: 'sympathetic', Auto: 'auto',
  };

  // Pages pass a real voice id (e.g. "svara-gu-f", "af_heart"); the persona
  // table is only a fallback for older markup.
  const IS_VOICE_ID = /^[a-z]{2,6}[-_]/i;
  const voiceId = (language, persona) => {
    if (persona && IS_VOICE_ID.test(persona)) return persona;
    const byLang = VOICES[language] || VOICES.English;
    return byLang[GENDER[persona] || 'f'] || byLang.f;
  };
  const emotionId = name => EMOTION[String(name || '').trim()] || 'neutral';

  /** Speak `text` with Prapthi. Resolves to an object URL for the audio. */
  async function synth(text, language, mood, persona, signal) {
    const res = await fetch(BASE + '/demo/synthesize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        voiceId: voiceId(language, persona),
        text: String(text).slice(0, DEMO_LIMIT),
        emotion: emotionId(mood),
        format: 'mp3',
      }),
      signal,
    });
    if (res.status === 429) throw new Error('Too many previews just now — please wait a moment.');
    if (!res.ok) {
      let detail = '';
      try { detail = (await res.json()).error || ''; } catch { /* not json */ }
      throw new Error(detail || ('HTTP ' + res.status));
    }
    const blob = await res.blob();
    if (!blob.size) throw new Error('empty audio');
    return URL.createObjectURL(blob);
  }

  return { synth, voiceId, emotionId, DEMO_LIMIT, languages: Object.keys(VOICES) };
})();

/* Header account state: if the visitor already has a studio session, the
 * header should say so instead of inviting them to log in again. Silent and
 * best-effort — any failure leaves the designed "Log in / Sign up" pair. */
(() => {
  const login = document.querySelector('.header-login');
  const signup = document.querySelector('header .button');
  // The home page shows only "Log in", so either element may be absent.
  if (!login && !signup) return;
  fetch((window.PRAPTHI_API_BASE || (location.hostname.endsWith('prapthi.ai') ? '/api' : 'https://api.prapthi.ai/api')) + '/auth/me', {
    credentials: 'include',
  })
    .then(r => (r.ok ? r.json() : null))
    .then(user => {
      if (!user || !(user.email || user.user)) return;
      if (login) { login.textContent = 'Studio'; login.href = '/app/dashboard'; }
      if (signup) { signup.textContent = 'Open studio →'; signup.href = '/app/dashboard'; }
    })
    .catch(() => {});
})();
