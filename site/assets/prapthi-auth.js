/* Prapthi.ai — sign in / sign up on the site itself, in the site's own design.
 *
 * Talks to the existing account API (no backend changes):
 *   POST /auth/login   {email,password}  -> session cookie  | 401 wrong | 403 unverified
 *   POST /auth/signup  {email,password}  -> emails a code
 *   POST /auth/verify  {email,code}      -> account verified
 *   POST /auth/resend  {email}           -> new code
 *   POST /auth/forgot  {email}           -> emails a reset code
 *   POST /auth/reset   {email,code,password}
 * The session cookie is set by the API (httpOnly, SameSite=Strict) and is
 * shared with the studio at /app, so a sign-in here lands you straight in.
 */
'use strict';
(() => {
  const BASE = window.PRAPTHI_API_BASE || (location.hostname.endsWith('prapthi.ai') ? '/api' : 'https://api.prapthi.ai/api');
  const STUDIO = '/app/dashboard';  // skip the studio's own landing page
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const forms = $$('[data-auth-step]');
  if (!forms.length) return;

  const show = step => forms.forEach(f => { f.hidden = f.dataset.authStep !== step; });
  const say = (form, message, kind = 'info') => {
    const el = $('[data-auth-status]', form);
    if (!el) return;
    el.textContent = message || '';
    el.dataset.kind = message ? kind : '';
  };
  const busy = (form, on) => {
    const b = $('button[type=submit]', form);
    if (b) { b.disabled = on; b.dataset.busyLabel = b.dataset.busyLabel || b.textContent; b.textContent = on ? 'Please wait…' : b.dataset.busyLabel; }
  };

  async function call(path, payload) {
    let res;
    try {
      res = await fetch(BASE + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      });
    } catch {
      throw Object.assign(new Error('Could not reach the account service. Check your connection and try again.'), { offline: true });
    }
    let data = {};
    try { data = await res.json(); } catch { /* empty body */ }
    if (!res.ok) throw Object.assign(new Error(data.message || data.error || ('Request failed (' + res.status + ')')), { status: res.status, code: data.error });
    return data;
  }

  // remember the email across steps (verify / reset need it)
  let email = '';

  const value = (form, name) => ($(`[name=${name}]`, form)?.value || '').trim();

  /* ---------------------------------------------------------------- sign in */
  const loginForm = $('[data-auth-step=login]');
  loginForm?.addEventListener('submit', async e => {
    e.preventDefault();
    email = value(loginForm, 'email').toLowerCase();
    const password = $('[name=password]', loginForm).value;
    if (!email || !password) return say(loginForm, 'Enter your email and password.', 'error');
    busy(loginForm, true); say(loginForm, '');
    try {
      await call('/auth/login', { email, password });
      say(loginForm, 'Signed in. Taking you to the studio…', 'ok');
      location.assign(STUDIO);
    } catch (err) {
      busy(loginForm, false);
      if (err.status === 403 || err.code === 'unverified') {
        show('verify');
        const vf = $('[data-auth-step=verify]');
        say(vf, 'This email is not verified yet. We have sent you a code.', 'info');
        call('/auth/resend', { email }).catch(() => {});
        return;
      }
      say(loginForm, err.message, 'error');
    }
  });

  /* --------------------------------------------------------------- sign up */
  const signupForm = $('[data-auth-step=signup]');
  signupForm?.addEventListener('submit', async e => {
    e.preventDefault();
    email = value(signupForm, 'email').toLowerCase();
    const password = $('[name=password]', signupForm).value;
    if (!email) return say(signupForm, 'Enter your email address.', 'error');
    if (password.length < 8 || !/[A-Za-z]/.test(password) || !/\d/.test(password))
      return say(signupForm, 'Password must be at least 8 characters and include a letter and a number.', 'error');
    busy(signupForm, true); say(signupForm, '');
    try {
      await call('/auth/signup', { email, password });
      busy(signupForm, false);
      show('verify');
      say($('[data-auth-step=verify]'), 'Check your inbox — we sent a 6-digit code to ' + email + '.', 'ok');
    } catch (err) {
      busy(signupForm, false);
      say(signupForm, err.message, 'error');
    }
  });

  /* ---------------------------------------------------------------- verify */
  const verifyForm = $('[data-auth-step=verify]');
  verifyForm?.addEventListener('submit', async e => {
    e.preventDefault();
    const code = value(verifyForm, 'code');
    if (!code) return say(verifyForm, 'Enter the code from your email.', 'error');
    busy(verifyForm, true);
    try {
      await call('/auth/verify', { email, code });
      busy(verifyForm, false);
      show('login');
      const lf = $('[data-auth-step=login]');
      if (lf) { $('[name=email]', lf).value = email; say(lf, 'Email verified. Sign in to continue.', 'ok'); }
      else say(verifyForm, 'Email verified. You can sign in now.', 'ok');
    } catch (err) { busy(verifyForm, false); say(verifyForm, err.message, 'error'); }
  });
  $('[data-auth-resend]')?.addEventListener('click', async () => {
    if (!email) return say(verifyForm, 'Enter your email on the previous step first.', 'error');
    try { await call('/auth/resend', { email }); say(verifyForm, 'If that email is eligible, a new code is on its way.', 'ok'); }
    catch (err) { say(verifyForm, err.message, 'error'); }
  });

  /* ------------------------------------------------------- forgot password */
  $$('[data-auth-forgot]').forEach(b => b.addEventListener('click', () => {
    show('forgot');
    const ff = $('[data-auth-step=forgot]');
    const guess = $('[name=email]', loginForm || document.createElement('form'))?.value;
    if (guess && $('[name=email]', ff)) $('[name=email]', ff).value = guess;
  }));
  const forgotForm = $('[data-auth-step=forgot]');
  forgotForm?.addEventListener('submit', async e => {
    e.preventDefault();
    email = value(forgotForm, 'email').toLowerCase();
    if (!email) return say(forgotForm, 'Enter your email address.', 'error');
    busy(forgotForm, true);
    try {
      await call('/auth/forgot', { email });
      busy(forgotForm, false);
      show('reset');
      say($('[data-auth-step=reset]'), 'If that email has an account, a reset code is on its way.', 'ok');
    } catch (err) { busy(forgotForm, false); say(forgotForm, err.message, 'error'); }
  });

  const resetForm = $('[data-auth-step=reset]');
  resetForm?.addEventListener('submit', async e => {
    e.preventDefault();
    const code = value(resetForm, 'code');
    const password = $('[name=password]', resetForm).value;
    if (!code) return say(resetForm, 'Enter the code from your email.', 'error');
    if (password.length < 8 || !/[A-Za-z]/.test(password) || !/\d/.test(password))
      return say(resetForm, 'Password must be at least 8 characters and include a letter and a number.', 'error');
    busy(resetForm, true);
    try {
      await call('/auth/reset', { email, code, password });
      busy(resetForm, false);
      show('login');
      const lf = $('[data-auth-step=login]');
      if (lf) { $('[name=email]', lf).value = email; say(lf, 'Password updated. Sign in with your new password.', 'ok'); }
    } catch (err) { busy(resetForm, false); say(resetForm, err.message, 'error'); }
  });

  /* ------------------------------------------------------------- niceties */
  $$('[data-auth-back]').forEach(b => b.addEventListener('click', () => show(b.dataset.authBack)));
  $$('[data-auth-reveal]').forEach(b => b.addEventListener('click', () => {
    const input = $('[name=password]', b.closest('form'));
    const shown = input.type === 'text';
    input.type = shown ? 'password' : 'text';
    b.textContent = shown ? 'Show' : 'Hide';
    b.setAttribute('aria-label', shown ? 'Show password' : 'Hide password');
  }));
  // already signed in? skip the form
  fetch(BASE + '/auth/me', { credentials: 'include' })
    .then(r => (r.ok ? r.json() : null))
    .then(u => { if (u && (u.user || u.email)) location.replace(STUDIO); })
    .catch(() => {});
})();
