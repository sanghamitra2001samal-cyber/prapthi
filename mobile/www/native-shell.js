/*
 * Injected by the Prapthi AI app into every prapthi.ai page it shows.
 *
 * A phone's WebView does not save files: an <a download> link, or a blob a
 * page hands to one, simply does nothing. This turns every download on the
 * site and in the studio into the phone's own save/share sheet, so "Download"
 * works the same in the app as it does in a browser. Nothing on the website
 * has to know about the app for this to work.
 */
(function () {
  'use strict';
  if (window.__prapthiShell) return;
  // Android only injects this into our own pages; iOS cannot limit it by
  // address, so the script checks for itself.
  if (!/(^|\.)prapthi\.ai$/i.test(location.hostname)) return;
  window.__prapthiShell = true;

  // This runs before the page itself, when Capacitor's bridge has not been
  // set up yet, so it is looked up at the moment it is needed.
  function bridge() {
    var C = window.Capacitor;
    return C && C.isNativePlatform && C.isNativePlatform() && C.nativePromise ? C : null;
  }
  function call(plugin, method, options) {
    var C = bridge();
    return C ? C.nativePromise(plugin, method, options || {})
             : Promise.reject(new Error('The app bridge is not ready yet'));
  }

  /* ---------------------------------------------------------------- toast */
  var toastEl = null, toastTimer = null;
  function toast(message, ms) {
    if (!toastEl) {
      toastEl = document.createElement('div');
      toastEl.setAttribute('role', 'status');
      toastEl.setAttribute('aria-live', 'polite');
      toastEl.style.cssText = [
        'position:fixed', 'left:50%', 'transform:translateX(-50%)',
        'bottom:calc(24px + env(safe-area-inset-bottom, 0px))',
        'z-index:2147483647', 'max-width:calc(100vw - 32px)',
        'padding:12px 18px', 'border-radius:12px',
        'background:rgba(11,16,32,.92)', 'color:#fff',
        'font:500 14px/1.35 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif',
        'box-shadow:0 12px 32px -12px rgba(0,0,0,.5)', 'pointer-events:none',
        'transition:opacity .2s', 'opacity:0'
      ].join(';');
      (document.body || document.documentElement).appendChild(toastEl);
    }
    toastEl.textContent = message;
    toastEl.style.opacity = '1';
    clearTimeout(toastTimer);
    if (ms) toastTimer = setTimeout(function () { toastEl.style.opacity = '0'; }, ms);
  }

  /* ------------------------------------------------------------- files */
  var DIR = 'CACHE';
  var FOLDER = 'downloads';
  // A multiple of 3 bytes, so each chunk encodes to standalone base64 and
  // the pieces can be appended one after another. Keeps a long WAV from
  // being pushed across the bridge as one enormous string.
  var CHUNK = 3 * 1024 * 1024;

  function safeName(name, type) {
    name = String(name || '').split(/[\\/]/).pop().replace(/[^\w.\-() ]+/g, '_').trim();
    if (!name || name === '.' || name === '..') name = 'prapthi-audio';
    if (!/\.[a-z0-9]{2,5}$/i.test(name)) {
      var ext = { 'audio/mpeg': '.mp3', 'audio/mp3': '.mp3', 'audio/wav': '.wav', 'audio/x-wav': '.wav',
                  'audio/wave': '.wav', 'audio/ogg': '.ogg', 'audio/webm': '.webm', 'audio/mp4': '.m4a',
                  'audio/aac': '.aac', 'audio/flac': '.flac', 'application/pdf': '.pdf',
                  'text/plain': '.txt', 'application/zip': '.zip' }[(type || '').split(';')[0]];
      name += ext || '';
    }
    return name.slice(0, 120);
  }

  function nameFromUrl(url) {
    try {
      var u = new URL(url, location.href);
      if (u.protocol === 'blob:' || u.protocol === 'data:') return '';
      return decodeURIComponent(u.pathname.split('/').pop() || '');
    } catch (e) { return ''; }
  }

  function toBase64(blob) {
    return new Promise(function (resolve, reject) {
      var r = new FileReader();
      r.onload = function () { var s = String(r.result); resolve(s.slice(s.indexOf(',') + 1)); };
      r.onerror = function () { reject(r.error || new Error('Could not read the file')); };
      r.readAsDataURL(blob);
    });
  }

  var busy = false;
  function save(url, filename) {
    if (busy) { toast('Still preparing the last file…', 2000); return Promise.resolve(); }
    busy = true;
    toast('Preparing your file…');
    // Started synchronously: a page may revoke a blob URL a moment after
    // clicking it, and the fetch has to be under way before that happens.
    var fetching = fetch(url, { credentials: 'include' });
    var name, path;
    return fetching
      .then(function (res) {
        if (!res.ok) throw new Error('The server answered ' + res.status);
        return res.blob();
      })
      .then(function (blob) {
        name = safeName(filename || nameFromUrl(url), blob.type);
        path = FOLDER + '/' + Date.now() + '/' + name;
        var chain = Promise.resolve(), first = true;
        if (blob.size === 0) {
          chain = call('Filesystem', 'writeFile', { path: path, data: '', directory: DIR, recursive: true });
        }
        for (var off = 0; off < blob.size; off += CHUNK) {
          (function (part, isFirst) {
            chain = chain.then(function () { return toBase64(part); }).then(function (b64) {
              return call('Filesystem', isFirst ? 'writeFile' : 'appendFile',
                          { path: path, data: b64, directory: DIR, recursive: true });
            });
          })(blob.slice(off, off + CHUNK), first);
          first = false;
        }
        return chain;
      })
      .then(function () { return call('Filesystem', 'getUri', { path: path, directory: DIR }); })
      .then(function (res) {
        toast('', 1);
        return call('Share', 'share', { title: name, files: [res.uri], dialogTitle: 'Save or share ' + name });
      })
      .catch(function (err) {
        var msg = String((err && err.message) || err || '');
        if (/cancel/i.test(msg)) { toast('', 1); return; }   // they closed the sheet: not an error
        toast('Could not save the file. ' + (msg ? msg : 'Please try again.'), 4500);
      })
      .then(function () { busy = false; });
  }
  /* ------------------------------------------------------------- back */
  // Android's back button should close whatever is open on the page before it
  // leaves the page. The native side asks this first; true means "handled".
  function pressEscape() {
    var t = document.activeElement || document.body;
    t.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
  }
  window.__prapthiBack = function () {
    // Website menu (closes on Escape).
    if (document.querySelector('#main-navigation.nav-open')) { pressEscape(); return true; }
    // Studio dialogs: delete account, history, settings, voices (Escape closes them).
    if (document.querySelector('[role="dialog"][aria-modal="true"]')) { pressEscape(); return true; }
    // Studio account menu: a full-screen click-catcher sits behind it.
    var catcher = document.querySelector('div.fixed.inset-0.z-40[aria-hidden="true"]');
    if (catcher) { catcher.click(); return true; }
    // Studio mobile drawer: open when its wrapper is not pointer-events-none.
    var drawers = document.querySelectorAll('div.fixed.inset-0.z-50');
    for (var i = 0; i < drawers.length; i++) {
      var d = drawers[i], backdrop = d.firstElementChild;
      if (!d.classList.contains('pointer-events-none') && backdrop && backdrop.getAttribute('aria-hidden') === 'true'
          && getComputedStyle(d).display !== 'none') {
        backdrop.click(); return true;
      }
    }
    return false;
  };

  // The native side routes downloads that never pass through a link click
  // (a server response sent as an attachment) to the same place.
  window.__prapthiSave = save;

  document.addEventListener('click', function (e) {
    var t = e.target;
    var a = t && t.closest ? t.closest('a[download]') : null;
    if (!a || !a.href || !bridge()) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    save(a.href, a.getAttribute('download'));
  }, true);

  function onReady() {
    if (!bridge()) return;
    document.documentElement.classList.add('prapthi-app');
    // Lets the app drop its splash screen the moment there is a page to see.
    call('PrapthiShell', 'ready').catch(function () {});
    // Old copies are only needed until the share sheet has read them. Clear
    // them once per app session so the cache cannot grow without limit.
    try {
      if (!sessionStorage.getItem('__prapthiCleaned')) {
        sessionStorage.setItem('__prapthiCleaned', '1');
        call('Filesystem', 'rmdir', { path: FOLDER, directory: DIR, recursive: true }).catch(function () {});
      }
    } catch (e) { /* storage blocked: skip the tidy-up, nothing breaks */ }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', onReady, { once: true });
  else onReady();
})();
