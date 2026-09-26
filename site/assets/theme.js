(() => {
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  const valid = value => ['light', 'dark', 'system'].includes(value);
  let theme = 'system';
  try { const stored = localStorage.getItem('prapthi-theme'); if (valid(stored)) theme = stored; } catch {}
  function apply() {
    const dark = theme === 'dark' || (theme === 'system' && media.matches);
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    document.documentElement.classList.toggle('dark', dark);
    document.documentElement.style.colorScheme = dark ? 'dark' : 'light';
    const select = document.getElementById('theme-select'); if (select) select.value = theme;
  }
  window.setPrapthiTheme = value => { if (!valid(value)) return; theme = value; try { localStorage.setItem('prapthi-theme', theme); } catch {} apply(); };
  window.addEventListener('storage', event => { if (event.key === 'prapthi-theme') { theme = valid(event.newValue) ? event.newValue : 'system'; apply(); } });
  media.addEventListener('change', apply);
  document.addEventListener('DOMContentLoaded', apply);
  apply();
})();
