window.Api = (() => {
  const BASE = window.API_BASE_URL || '/api';

  async function request(method, path, body, isForm = false) {
    const headers = {};
    const token = Storage.token();
    if (token) headers['Authorization'] = 'Bearer ' + token;

    let payload;
    if (isForm) {
      payload = body;
    } else {
      headers['Content-Type'] = 'application/json';
      payload = body !== undefined ? JSON.stringify(body) : undefined;
    }

    let res;
    try {
      res = await fetch(BASE + path, { method, headers, body: payload });
    } catch (e) {
      throw new Error(I18n.t('network_error'));
    }

    let data = null;
    try {
      data = await res.json();
    } catch (e) { /* non-JSON response */ }

    if (!res.ok) {
      if (res.status === 401 && path.indexOf('/auth/login') === -1 && path.indexOf('/auth/register') === -1) {
        Storage.clear();
        if (window.location.pathname.indexOf('login.html') === -1) {
          window.location.replace('pages/login.html');
        }
        throw new Error(I18n.t('login'));
      }
      const detail = typeof data?.detail === 'string' ? data.detail : null;
      const err = new Error(detail || `${res.status} ${res.statusText}`);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  async function download(path) {
    const headers = {};
    const token = Storage.token();
    if (token) headers['Authorization'] = 'Bearer ' + token;
    const res = await fetch(BASE + path, { headers });
    if (!res.ok) {
      throw new Error(I18n.t('download_error'));
    }
    return res.blob();
  }

  return {
    get: (path) => request('GET', path),
    post: (path, body) => request('POST', path, body),
    put: (path, body) => request('PUT', path, body),
    del: (path) => request('DELETE', path),
    upload: (method, path, formData) => request(method, path, formData, true),
    download,
  };
})();
