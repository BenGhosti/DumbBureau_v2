window.UI = (() => {
  function toast(text, isError = false) {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.style.cssText = 'position:fixed;bottom:1em;right:1em;z-index:9999;display:flex;flex-direction:column;gap:0.5em;';
      document.body.appendChild(container);
    }
    const node = document.createElement('div');
    node.className = 'message ' + (isError ? 'error' : 'success');
    node.textContent = text;
    container.appendChild(node);
    setTimeout(() => node.remove(), 4000);
  }

  function showMessage(el, text, isError) {
    if (!el) return;
    el.textContent = text;
    el.classList.toggle('error', !!isError);
    el.classList.remove('hidden');
  }

  function hideMessage(el) {
    if (el) el.classList.add('hidden');
  }

  function setBusy(btn, busy, busyText) {
    if (busy) {
      btn.dataset.orig = btn.textContent;
      btn.textContent = busyText || '…';
      btn.disabled = true;
    } else {
      btn.textContent = btn.dataset.orig || btn.textContent;
      btn.disabled = false;
    }
  }

  function confirmDialog(text) {
    return window.confirm(text);
  }

  function run(fn) {
    Promise.resolve()
      .then(fn)
      .catch((err) => toast(err.message || String(err), true));
  }

  function openModal({ title, html, onSubmit, onClose }) {
    const trigger = document.activeElement;
    const overlay = Utils.el('div', { class: 'modal-overlay' });
    const form = Utils.el('form', { class: 'modal-card' });
    const titleId = 'modal-title-' + Date.now();
    form.setAttribute('role', 'dialog');
    form.setAttribute('aria-modal', 'true');
    form.setAttribute('aria-labelledby', titleId);
    form.appendChild(Utils.el('h3', { id: titleId, text: title }));
    const body = Utils.el('div');
    body.innerHTML = html;
    form.appendChild(body);
    overlay.appendChild(form);
    document.body.appendChild(overlay);

    function close() {
      document.removeEventListener('keydown', onKeydown);
      overlay.remove();
      if (trigger && document.contains(trigger)) trigger.focus();
      if (onClose) onClose();
    }

    function onKeydown(e) {
      if (e.key === 'Escape') {
        e.preventDefault();
        close();
        return;
      }
      if (e.key !== 'Tab') return;
      const focusables = form.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
      if (focusables.length === 0) {
        e.preventDefault();
        form.focus();
        return;
      }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first || document.activeElement === form) {
          e.preventDefault();
          last.focus();
        }
      } else if (document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }

    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) close();
    });
    form.querySelectorAll('.m-cancel').forEach((b) => b.addEventListener('click', close));

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      try {
        if (await onSubmit(form) === true) close();
      } catch (err) {
        toast(err.message || String(err), true);
      }
    });

    const firstFocusable = form.querySelector('input, select, textarea, button');
    if (firstFocusable) firstFocusable.focus();
    document.addEventListener('keydown', onKeydown);

    return { close, overlay, form };
  }

  return { toast, showMessage, hideMessage, setBusy, confirmDialog, run, openModal };
})();
