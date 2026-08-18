window.Theme = (() => {
  const KEY = 'dumbbureau_theme';

  function apply(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    document.querySelectorAll('.theme-toggle .moon').forEach((el) => {
      el.style.display = theme === 'dark' ? 'none' : '';
    });
    document.querySelectorAll('.theme-toggle .sun').forEach((el) => {
      el.style.display = theme === 'dark' ? '' : 'none';
    });
  }

  function get() {
    return localStorage.getItem(KEY) ||
      (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  }

  function set(theme) {
    localStorage.setItem(KEY, theme);
    apply(theme);
  }

  function toggle() {
    const current = document.documentElement.getAttribute('data-theme');
    set(current === 'dark' ? 'light' : 'dark');
  }

  function init() {
    apply(get());
    document.querySelectorAll('.theme-toggle').forEach((btn) => {
      btn.addEventListener('click', toggle);
    });
  }

  return { init, toggle, get, set };
})();

Theme.init();
