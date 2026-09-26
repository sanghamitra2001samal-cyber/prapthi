'use strict';
(() => {
  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const { phrases, codes, people } = window.PRAPTHI;
  let chosenLanguage = 'Hinglish', activeButton = null, utterance = null, token = 0, audio = null;
  const text = $('textarea'), generate = $('.editor-bottom .button');
  const value = (name, fallback) => $('#pick-' + name)?.value || fallback;
  const status = message => { const output = $('.play-status'); if (output) output.textContent = message; };
  function stop() {
    token++;
    try { window.speechSynthesis?.cancel(); } catch {}
    if (audio) { try { audio.pause(); } catch {} try { URL.revokeObjectURL(audio.src); } catch {} audio = null; }
    if (activeButton) { activeButton.innerHTML = activeButton.dataset.originalHtml; activeButton.classList.remove('is-playing'); }
    activeButton = null; utterance = null;
  }
  function hold(button) {
    button.dataset.originalHtml = button.innerHTML;
    activeButton = button; button.classList.add('is-playing');
    if (button.classList.contains('play') || button.classList.contains('hero-play')) button.textContent = 'Ⅱ';
    if (button === generate) button.textContent = 'Stop speech';
  }
  function release(ownToken, message) {
    if (token !== ownToken) return;
    if (activeButton) { activeButton.innerHTML = activeButton.dataset.originalHtml; activeButton.classList.remove('is-playing'); }
    activeButton = null; utterance = null; audio = null; status(message);
  }
  /** Speak with Prapthi's own engines; fall back to a browser voice only if
   *  the service cannot be reached. */
  async function speak(button, words, lang = 'English', mood = 'Confident', voice = 'Aarav') {
    const stopping = activeButton === button;
    stop();
    if (stopping) { status('Playback stopped'); return; }
    if (!words.trim()) { status('Write a few words to hear your voice.'); return; }
    const ownToken = token;
    hold(button);
    const api = window.PRAPTHI_API;
    if (!api) { speakInBrowser(button, words, lang, mood, voice, ownToken); return; }
    const long = words.trim().length > api.DEMO_LIMIT;
    status('Generating with Prapthi voices…');
    try {
      const url = await api.synth(words, lang, mood, voice);
      if (token !== ownToken) { URL.revokeObjectURL(url); return; }
      audio = new Audio(url);
      audio.onended = () => release(ownToken, 'Preview finished · Ready to play again');
      audio.onerror = () => release(ownToken, 'Playback could not start. Please try again.');
      await audio.play();
      if (token !== ownToken) return;
      status(long
        ? 'Playing ' + lang + ' · ' + mood + ' — preview limited to the first ' + api.DEMO_LIMIT + ' characters'
        : 'Playing ' + lang + ' · ' + mood + ' with a Prapthi voice');
    } catch (error) {
      if (token !== ownToken) return;
      if (/wait a moment/i.test(error.message)) { release(ownToken, error.message); return; }
      status('Prapthi voices unavailable here — using your browser voice.');
      speakInBrowser(button, words, lang, mood, voice, ownToken);
    }
  }
  function speakInBrowser(button, words, lang, mood, voice, ownToken) {
    if (!window.speechSynthesis || !window.SpeechSynthesisUtterance) { release(ownToken, 'Speech playback is unavailable in this browser. Try Chrome or Safari.'); return; }
    try {
      utterance = new SpeechSynthesisUtterance(words);
      utterance.lang = codes[lang] || 'en-IN';
      const voices = speechSynthesis.getVoices().filter(v => v.lang.startsWith(utterance.lang.split('-')[0]));
      if (voices.length) utterance.voice = voices[Math.max(0, people.indexOf(voice)) % voices.length];
      utterance.rate = value('style', 'Natural') === 'Narration' ? .86 : mood === 'Calm' ? .8 : mood === 'Joyful' ? 1.12 : .95;
      utterance.pitch = mood === 'Sarcastic' ? 1.2 : mood === 'Authoritative' ? .8 : 1;
      utterance.onend = () => release(ownToken, 'Preview finished · Ready to play again');
      utterance.onerror = () => release(ownToken, 'Playback unavailable. Check that a voice is installed for this language.');
      speechSynthesis.speak(utterance);
    } catch { release(ownToken, 'Your browser could not start playback. Please try again.'); }
  }
  $('#theme-select')?.addEventListener('change', e => window.setPrapthiTheme(e.target.value));
  const nav = $('#main-navigation');
  const toggle = $('.menu-toggle');
  const setMenu = open => {
    if (!nav || !toggle) return;
    nav.classList.toggle('nav-open', open);
    toggle.setAttribute('aria-expanded', String(open));
    toggle.textContent = open ? '×' : '☰';
    document.body.classList.toggle('nav-locked', open);
    if (open) syncAccountLinks();
  };
  // The header bar already shows Log in / Sign up at most widths; only add
  // them to the menu when they are actually hidden, so they never appear twice.
  function syncAccountLinks() {
    const shown = $('.header-login') && getComputedStyle($('.header-login')).display !== 'none';
    $$('.mobile-account').forEach(a => { a.style.display = shown ? 'none' : ''; });
  }
  toggle?.addEventListener('click', e => { e.stopPropagation(); setMenu(!nav.classList.contains('nav-open')); });
  nav?.addEventListener('click', e => { if (e.target.closest('a')) setMenu(false); });
  document.addEventListener('click', e => {
    if (nav?.classList.contains('nav-open') && !e.target.closest('#main-navigation,.menu-toggle')) setMenu(false);
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') setMenu(false); });
  window.addEventListener('resize', () => {
    if (toggle && getComputedStyle(toggle).display === 'none') setMenu(false); else syncAccountLinks();
  });
  if (nav) for (const [label, url] of [['Log in','login.html'],['Sign up','signup.html']]) {
    const a = document.createElement('a'); a.textContent = label; a.href = url; a.className = 'mobile-account'; nav.append(a);
  }
  syncAccountLinks();
  $('.motion-toggle')?.addEventListener('click', e => {
    const main = $('main'); const paused = main.dataset.motion !== 'paused'; main.dataset.motion = paused ? 'paused' : 'playing';
    e.currentTarget.textContent = paused ? '▶ Resume motion' : 'Ⅱ Pause motion'; e.currentTarget.setAttribute('aria-pressed', String(paused));
  });
  const visible = new Set(); const motion = $$('.motion-art, .waveform, .spectrum, .hero-play');
  const updateMotion = () => motion.forEach(el => el.dataset.visibleMotion = String(!document.hidden && visible.has(el)));
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => { entries.forEach(entry => entry.isIntersecting ? visible.add(entry.target) : visible.delete(entry.target)); updateMotion(); });
    motion.forEach(el => observer.observe(el)); document.addEventListener('visibilitychange', updateMotion);
  }
  function updateText() { if (!text) return; $('.editor-bottom small').textContent = text.value.length + ' / 500 characters'; generate.disabled = !text.value.trim(); }
  text?.addEventListener('input', updateText);
  $('.clear')?.addEventListener('click', () => { stop(); text.value = ''; updateText(); text.focus(); });
  $('#pick-language')?.addEventListener('change', e => { stop(); text.value = phrases[e.target.value]; updateText(); });
  const queryVoice = new URLSearchParams(location.search).get('voice');
  if ($('#pick-voice') && people.includes(queryVoice)) $('#pick-voice').value = queryVoice;
  function updateEmotion() { $$('.presets button').forEach(b => { const selected = b.textContent.trim() === value('emotion','Confident'); b.classList.toggle('selected',selected); b.setAttribute('aria-pressed',String(selected)); }); }
  $('#pick-emotion')?.addEventListener('change', updateEmotion);
  $$('.presets button').forEach(b => b.addEventListener('click', () => { $('#pick-emotion').value = b.textContent.trim(); updateEmotion(); }));
  $$('.language-list button').forEach(b => b.addEventListener('click', () => {
    chosenLanguage = b.textContent.trim(); $$('.language-list button').forEach(item => { const selected = item === b; item.classList.toggle('selected',selected); item.setAttribute('aria-pressed', String(selected)); });
    $('.language-sample p').textContent = '“' + phrases[chosenLanguage] + '”';
  }));
  const search = $('#voice-search');
  if (search) {
    const empty = document.createElement('p'); empty.className = 'card voice-empty'; empty.textContent = 'No matching voices. Try another name, language or tone.'; empty.hidden = true; $('.voices-grid').append(empty);
    search.addEventListener('input', () => { let count = 0; $$('.voice').forEach(card => { const match = card.textContent.toLowerCase().includes(search.value.trim().toLowerCase()); card.hidden = !match; if (match) count++; }); $('.voice-toolbar small').textContent = count + ' personas'; empty.hidden = count > 0; });
  }
  $$('[role="tab"]').forEach((tab, i, tabs) => {
    function select() { tabs.forEach(t => { const selected = t === tab; t.setAttribute('aria-selected',String(selected)); t.dataset.state = selected ? 'active' : 'inactive'; const panel = document.getElementById(t.getAttribute('aria-controls')); if (panel) { panel.hidden = !selected; panel.dataset.state = selected ? 'active' : 'inactive'; } }); }
    tab.addEventListener('click', select);
    tab.addEventListener('keydown', e => { if (['ArrowRight','ArrowLeft','Home','End'].includes(e.key)) { e.preventDefault(); const next = e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length-1 : (i + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length; tabs[next].click(); tabs[next].focus(); } });
  });
  $$('button').forEach(button => {
    if (!(button.matches('.play,.hero-play,.listen-link,.stories-grid button,.emotion-card') || button.closest('.context') || button === generate)) return;
    if (button.closest('.language-list,.presets')) return;
    button.addEventListener('click', () => {
      let words = text?.value || phrases.English, lang = value('language','English'), mood = value('emotion','Confident'), voice = value('voice','Aarav');
      if (button.closest('.language-sample') || button.matches('.listen-link')) { lang = chosenLanguage; words = phrases[lang]; }
      const sample = button.closest('.sample');
      if (sample) { voice = sample.dataset.voiceid || voice; lang = sample.dataset.phrase || lang; words = phrases[lang] || phrases.English; }
      const card = button.closest('.voice');
      if (card) { voice = card.dataset.voiceid || voice; lang = card.dataset.phrase || lang; words = phrases[lang] || phrases.English;
        const character = (card.querySelector('small').textContent || '').match(/Warm|Conversational|Authoritative|Gentle|Energetic|Storytelling|Deep|Calm|Confident|Bright|Soft|Emotional/);
        if (character) mood = character[0] === 'Emotional' ? 'Warm' : character[0]; }
      if (button.matches('.hero-play')) words = 'Give your ideas a voice. Natural, expressive, multilingual speech. Built in India, for voices everywhere.';
      if (/Sarcastic|Hopeful|Authoritative/.test(button.textContent)) { mood = button.textContent.match(/Sarcastic|Hopeful|Authoritative/)[0]; words = phrases.English; }
      const story = button.getAttribute('aria-label'); if (button.closest('.stories-grid') && story) words = story.replace(/^Play /,'') + '. ' + phrases.English;
      speak(button, words, lang, mood, voice);
    });
  });
  window.addEventListener('pagehide',stop);
  updateText(); updateEmotion();
})();
