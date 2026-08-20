window.Storage = (() => {
  const SESSION_KEY = 'dumbbureau_session';
  const LANG_KEY = 'dumbbureau_lang';

  function save(session) {
    localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  }

  function load() {
    try {
      return JSON.parse(localStorage.getItem(SESSION_KEY));
    } catch (e) {
      return null;
    }
  }

  function clear() {
    localStorage.removeItem(SESSION_KEY);
  }

  function token() {
    const s = load();
    return s ? s.session_token : null;
  }

  function isAuthenticated() {
    return !!token();
  }

  function user() {
    const s = load();
    return s || {};
  }

  function isAdmin() {
    return !!user().is_admin;
  }

  function getLanguage() {
    return localStorage.getItem(LANG_KEY) || 'en';
  }

  function setLanguage(lang) {
    localStorage.setItem(LANG_KEY, lang);
  }

  return { save, load, clear, token, isAuthenticated, user, isAdmin, getLanguage, setLanguage };
})();
