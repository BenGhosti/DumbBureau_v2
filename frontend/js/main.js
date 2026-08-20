(function () {
  if (!Storage.isAuthenticated()) {
    window.location.replace('pages/login.html');
    return;
  }

  const user = Storage.user();

  const routes = {
    '#/dashboard': Views.dashboard,
    '#/categories': Views.categories,
    '#/templates': Views.templates,
    '#/export': Views.export,
    '#/admin': Views.admin,
    '#/profile': Views.profile,
  };

  const navItems = [
    { hash: '#/dashboard', key: 'nav_dashboard' },
    { hash: '#/categories', key: 'nav_categories' },
    { hash: '#/templates', key: 'nav_templates' },
    { hash: '#/export', key: 'nav_export' },
  ];
  if (user.is_admin) {
    navItems.push({ hash: '#/admin', key: 'nav_admin' });
  }
  navItems.push({ hash: '#/profile', key: 'nav_profile' });

  function timeOfDayGreetingKey() {
    const hour = new Date().getHours();
    if (hour < 5) return 'welcome_night';
    if (hour < 12) return 'welcome_morning';
    if (hour < 18) return 'welcome_afternoon';
    if (hour < 22) return 'welcome_evening';
    return 'welcome_night';
  }

  function renderWelcome() {
    let el = document.getElementById('welcome-message');
    if (!el) {
      el = Utils.el('div', { id: 'welcome-message', class: 'welcome-message' });
      const nav = document.getElementById('nav');
      nav.parentNode.insertBefore(el, nav);
    }
    el.textContent = I18n.t(timeOfDayGreetingKey(), { user: user.username });
  }

  const navIcons = {
    '#/dashboard': '<path d="M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z"/>',
    '#/categories': '<path d="M3 7l9-4 9 4-9 4-9-4z"/><path d="M3 7v10l9 4 9-4V7"/>',
    '#/templates': '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
    '#/export': '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/>',
    '#/admin': '<path d="M12 2l8 4v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V6z"/>',
    '#/profile': '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  };

  function navIconSvg(hash) {
    const path = navIcons[hash] || '';
    return '<svg class="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + path + '</svg>';
  }

  function renderNav() {
    const nav = document.getElementById('nav');
    nav.innerHTML = '';
    navItems.forEach((item) => {
      const a = Utils.el('a', { class: 'nav-link', href: item.hash });
      a.innerHTML = navIconSvg(item.hash) + '<span data-i18n="' + item.key + '"></span>';
      nav.appendChild(a);
    });
  }

  async function renderLangToggle() {
    // Off by default (SHOW_LANGUAGE_TOGGLE env flag) - fetched from the
    // backend since this is a static frontend with no build-time env
    // injection. Mirrors the same check on the login page.
    let cfg;
    try {
      cfg = await Api.get('/config');
    } catch {
      return;
    }
    if (!cfg.show_language_toggle) return;
    const nav = document.getElementById('nav');
    const langWrap = Utils.el('div', { class: 'lang-toggle', style: 'margin-top:auto;display:flex;gap:0.3em;' });
    ['de', 'en'].forEach((l) => {
      const b = Utils.el('button', { class: 'lang-btn', text: l.toUpperCase() });
      b.addEventListener('click', () => I18n.setLanguage(l));
      langWrap.appendChild(b);
    });
    nav.appendChild(langWrap);
  }

  async function router() {
    const hash = location.hash || '#/dashboard';
    const view = routes[hash];
    if (!view || (hash === '#/admin' && !user.is_admin)) {
      location.hash = '#/dashboard';
      return;
    }
    document.querySelectorAll('.nav-link').forEach((a) => {
      a.classList.toggle('active', a.getAttribute('href') === hash);
    });
    const container = document.getElementById('view');
    container.innerHTML = '<div class="card"><span data-i18n="loading">Loading…</span></div>';
    I18n.apply();
    try {
      await view(container);
    } catch (e) {
      container.innerHTML = '<div class="card message error">' + Utils.escapeHtml(e.message) + '</div>';
    }
    if (initialLoad) {
      initialLoad = false;
    } else {
      const heading = container.querySelector('h1, h2, h3');
      if (heading) {
        heading.setAttribute('tabindex', '-1');
        heading.focus();
      }
    }
  }

  let initialLoad = true;

  document.getElementById('logout-btn').addEventListener('click', () => {
    Auth.logout();
    window.location.replace('pages/login.html');
  });

  window.addEventListener('hashchange', router);

  renderWelcome();
  renderNav();
  renderLangToggle();
  I18n.apply();
  router();
})();
