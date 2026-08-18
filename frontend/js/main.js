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

  function renderNav() {
    const nav = document.getElementById('nav');
    nav.innerHTML = '';
    navItems.forEach((item) => {
      const a = Utils.el('a', { class: 'nav-link', href: item.hash, 'data-i18n': item.key });
      nav.appendChild(a);
    });
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
    container.innerHTML = '<div class="card"><span data-i18n="loading">Lade…</span></div>';
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

  renderNav();
  I18n.apply();
  router();
})();
