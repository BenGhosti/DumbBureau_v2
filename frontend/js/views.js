window.Views = (() => {
  let currentMonth = Utils.monthNow();
  let cachedCategories = null;
  let cachedTemplates = null;

  function getById(list, id) {
    return (list || []).find((x) => String(x.id) === String(id));
  }

  function safeChipColor(c) {
    return /^#[0-9a-fA-F]{6}$/.test(c) ? c : '#4B5563';
  }

  function categoryOptions(categories, selectedId) {
    return '<option value="">' + I18n.t('category') + '</option>' +
      categories.map((c) => {
        const sel = c.id === selectedId ? 'selected' : '';
        return '<option value="' + Utils.escapeHtml(c.id) + '" ' + sel + '>' +
          Utils.escapeHtml(c.name) + '</option>';
      }).join('');
  }

  function openTaskModal(categories, task) {
    const isEdit = !!task;
    UI.openModal({
      title: isEdit ? I18n.t('edit_task') : I18n.t('add_task'),
      html:
        '<label for="m-date">' + I18n.t('date') + '</label>' +
        '<input type="date" id="m-date" required value="' + (task ? task.date : Utils.todayIso()) + '">' +
        '<label for="m-category">' + I18n.t('category') + '</label>' +
        '<select id="m-category">' + categoryOptions(categories, task && task.category_id) + '</select>' +
        '<label for="m-desc">' + I18n.t('description') + '</label>' +
        '<textarea id="m-desc" required>' + (task ? Utils.escapeHtml(task.description) : '') + '</textarea>' +
        '<label for="m-fisi">' + I18n.t('fisi_area') + '</label>' +
        '<input type="text" id="m-fisi" value="' + (task ? Utils.escapeHtml(task.fisi_area || '') : '') + '">' +
        '<div class="modal-actions">' +
          '<button type="button" class="btn-secondary m-cancel">' + I18n.t('cancel') + '</button>' +
          '<button type="submit" class="btn-primary">' + I18n.t('save') + '</button>' +
        '</div>',
      onSubmit: async (form) => {
        const date = form.querySelector('#m-date').value;
        const description = form.querySelector('#m-desc').value;
        if (!date || !description.trim()) {
          UI.toast(I18n.t('fill_required_fields'), true);
          return false;
        }
        const payload = {
          date,
          category_id: form.querySelector('#m-category').value || null,
          description,
          fisi_area: form.querySelector('#m-fisi').value || null,
        };
        if (isEdit) await Api.put('/tasks/' + task.id, payload);
        else await Api.post('/tasks', payload);
        Views.dashboard(document.getElementById('view'));
        return true;
      },
    });
  }

  async function copyLastWeek(container) {
    const thisMonday = Utils.startOfWeek(new Date());
    const lastMonday = new Date(thisMonday);
    lastMonday.setDate(lastMonday.getDate() - 7);
    const resp = await Api.get('/tasks?start=' + Utils.isoDate(lastMonday) + '&end=' + Utils.isoDate(thisMonday));
    const tasks = resp.tasks;
    if (tasks.length === 0) {
      UI.toast(I18n.t('no_tasks'));
      return;
    }
    if (!UI.confirmDialog(I18n.t('confirm_copy', { n: tasks.length }))) return;
    const btn = container.querySelector('#copy-last-week');
    UI.setBusy(btn, true);
    try {
      await Promise.all(tasks.map((t) => Api.post('/tasks', {
        date: Utils.addDays(t.date, 7),
        category_id: t.category_id,
        description: t.description,
        fisi_area: t.fisi_area,
      })));
      UI.toast(I18n.t('copied_tasks', { n: tasks.length }));
    } finally {
      UI.setBusy(btn, false);
    }
    dashboard(container);
  }

  async function deleteTask(container, id) {
    if (!UI.confirmDialog(I18n.t('confirm_delete'))) return;
    await Api.del('/tasks/' + id);
    dashboard(container);
  }

  async function dashboard(container) {
    const taskResp = await Api.get('/tasks?month=' + encodeURIComponent(currentMonth));
    const tasks = taskResp.tasks;
    if (!cachedCategories) {
      const catResp = await Api.get('/categories');
      cachedCategories = catResp.categories;
    }
    const categories = cachedCategories;

    const rows = tasks.map((t) => {
      const chip = t.category
        ? '<span class="category-chip" style="background:' + safeChipColor(t.category_color) + '">' + Utils.escapeHtml(t.category) + '</span>'
        : '';
      return '<tr>' +
        '<td>' + Utils.escapeHtml(t.date) + '</td>' +
        '<td>' + chip + '</td>' +
        '<td>' + Utils.escapeHtml(t.description) + '</td>' +
        '<td>' + Utils.escapeHtml(t.fisi_area || '') + '</td>' +
        '<td style="white-space:nowrap">' +
          '<button class="edit-task btn-secondary" data-id="' + t.id + '">' + I18n.t('edit_task') + '</button> ' +
          '<button class="del-task btn-danger" data-id="' + t.id + '">' + I18n.t('delete_task') + '</button>' +
        '</td></tr>';
    }).join('');

    container.innerHTML =
      '<div class="toolbar">' +
        '<button id="prev-month" class="btn-secondary">‹</button>' +
        '<strong id="month-label">' + Utils.monthLabel(currentMonth) + '</strong>' +
        '<button id="next-month" class="btn-secondary">›</button>' +
        '<button id="copy-last-week" class="btn-secondary">' + I18n.t('copy_last_week') + '</button>' +
        '<div class="spacer"></div>' +
        '<button id="add-task" class="btn-primary">' + I18n.t('add_task') + '</button>' +
      '</div>' +
      '<div class="card">' +
        '<h3>' + I18n.t('quick_add') + '</h3>' +
        '<form id="quick-add">' +
          '<div class="form-grid">' +
            '<div><label for="qa-date">' + I18n.t('date') + '</label><input type="date" id="qa-date" value="' + Utils.todayIso() + '"></div>' +
            '<div><label for="qa-category">' + I18n.t('category') + '</label><select id="qa-category">' + categoryOptions(categories) + '</select></div>' +
            '<div><label for="qa-fisi">' + I18n.t('fisi_area') + '</label><input type="text" id="qa-fisi"></div>' +
          '</div>' +
          '<label for="qa-desc">' + I18n.t('description') + '</label>' +
          '<textarea id="qa-desc"></textarea>' +
          '<button type="submit" class="btn-primary" style="margin-top:0.75em">' + I18n.t('save') + '</button>' +
        '</form>' +
      '</div>' +
      '<div class="card">' +
        (tasks.length === 0
          ? '<p class="muted">' + I18n.t('no_tasks') + '</p>'
          : '<table class="table"><thead><tr>' +
            '<th>' + I18n.t('date') + '</th>' +
            '<th>' + I18n.t('category') + '</th>' +
            '<th>' + I18n.t('description') + '</th>' +
            '<th>' + I18n.t('fisi_area') + '</th>' +
            '<th></th></tr></thead><tbody>' + rows + '</tbody></table>') +
      '</div>';

    container.querySelector('#prev-month').addEventListener('click', () => {
      UI.run(() => {
        currentMonth = Utils.shiftMonth(currentMonth, -1);
        dashboard(container);
      });
    });
    container.querySelector('#next-month').addEventListener('click', () => {
      UI.run(() => {
        currentMonth = Utils.shiftMonth(currentMonth, 1);
        dashboard(container);
      });
    });
    container.querySelector('#add-task').addEventListener('click', () => openTaskModal(categories, null));
    container.querySelector('#copy-last-week').addEventListener('click', () => UI.run(() => copyLastWeek(container)));

    container.querySelector('#quick-add').addEventListener('submit', (e) => {
      e.preventDefault();
      UI.run(async () => {
        const date = container.querySelector('#qa-date').value;
        const category_id = container.querySelector('#qa-category').value || null;
        const description = container.querySelector('#qa-desc').value;
        const fisi_area = container.querySelector('#qa-fisi').value || null;
        if (!date || !description.trim()) return;
        await Api.post('/tasks', { date, category_id, description, fisi_area });
        dashboard(container);
      });
    });

    container.querySelectorAll('.edit-task').forEach((b) => {
      b.addEventListener('click', () => {
        const task = getById(tasks, b.dataset.id);
        openTaskModal(categories, task);
      });
    });
    container.querySelectorAll('.del-task').forEach((b) => {
      b.addEventListener('click', () => UI.run(() => deleteTask(container, b.dataset.id)));
    });
  }

  function openCategoryModal(cat) {
    const isEdit = !!cat;
    UI.openModal({
      title: isEdit ? I18n.t('edit_category') : I18n.t('add_category'),
      html:
        '<label for="c-name">' + I18n.t('category_name') + '</label>' +
        '<input id="c-name" required value="' + (cat ? Utils.escapeHtml(cat.name) : '') + '">' +
        '<label for="c-desc">' + I18n.t('category_description') + '</label>' +
        '<input id="c-desc" value="' + (cat ? Utils.escapeHtml(cat.description || '') : '') + '">' +
        '<label for="c-color">' + I18n.t('category_color') + '</label>' +
        '<input type="color" id="c-color" value="' + (cat ? Utils.escapeHtml(cat.color) : '#4B5563') + '">' +
        '<div class="modal-actions">' +
          '<button type="button" class="btn-secondary m-cancel">' + I18n.t('cancel') + '</button>' +
          '<button type="submit" class="btn-primary">' + I18n.t('save') + '</button>' +
        '</div>',
      onSubmit: async (form) => {
        const payload = {
          name: form.querySelector('#c-name').value,
          description: form.querySelector('#c-desc').value || null,
          color: form.querySelector('#c-color').value,
        };
        if (isEdit) await Api.put('/categories/' + cat.id, payload);
        else await Api.post('/categories', payload);
        cachedCategories = null;
        Views.categories(document.getElementById('view'));
        return true;
      },
    });
  }

  async function categories(container) {
    const resp = await Api.get('/categories');
    const cats = resp.categories;
    cachedCategories = cats;

    const rows = cats.map((c) =>
      '<tr>' +
        '<td><span class="category-chip" style="background:' + safeChipColor(c.color) + '">&nbsp;&nbsp;</span> ' + Utils.escapeHtml(c.name) + '</td>' +
        '<td>' + Utils.escapeHtml(c.description || '') + '</td>' +
        '<td style="white-space:nowrap">' +
          '<button class="edit-cat btn-secondary" data-id="' + c.id + '">' + I18n.t('edit_category') + '</button> ' +
          '<button class="del-cat btn-danger" data-id="' + c.id + '">' + I18n.t('delete_category') + '</button>' +
        '</td>' +
      '</tr>'
    ).join('');

    container.innerHTML =
      '<div class="toolbar"><h2>' + I18n.t('categories_title') + '</h2>' +
        '<div class="spacer"></div>' +
        '<button id="add-cat" class="btn-primary">' + I18n.t('add_category') + '</button>' +
      '</div>' +
      '<div class="card">' +
        (cats.length === 0
          ? '<p class="muted">' + I18n.t('no_categories') + '</p>'
          : '<table class="table"><thead><tr><th>' + I18n.t('category_name') + '</th><th>' + I18n.t('category_description') + '</th><th></th></tr></thead><tbody>' + rows + '</tbody></table>') +
      '</div>';

    container.querySelector('#add-cat').addEventListener('click', () => openCategoryModal(null));
    container.querySelectorAll('.edit-cat').forEach((b) => {
      b.addEventListener('click', () => openCategoryModal(getById(cats, b.dataset.id)));
    });
    container.querySelectorAll('.del-cat').forEach((b) => {
      b.addEventListener('click', () => UI.run(async () => {
        if (!UI.confirmDialog(I18n.t('confirm_delete'))) return;
        await Api.del('/categories/' + b.dataset.id);
        cachedCategories = null;
        Views.categories(container);
      }));
    });
  }

  function openTemplateModal(tpl) {
    const isEdit = !!tpl;
    UI.openModal({
      title: isEdit ? I18n.t('edit_template') : I18n.t('upload_template'),
      html:
        '<label for="t-name">' + I18n.t('template_name') + '</label>' +
        '<input id="t-name" value="' + (tpl ? Utils.escapeHtml(tpl.name) : '') + '">' +
        '<label for="t-desc">' + I18n.t('template_description') + '</label>' +
        '<input id="t-desc" value="' + (tpl ? Utils.escapeHtml(tpl.description || '') : '') + '">' +
        '<label for="t-file">' + I18n.t('html_file') + '</label>' +
        '<input type="file" id="t-file" accept=".html,.htm">' +
        '<label for="t-default" style="display:flex;align-items:center;gap:0.5em;margin-top:0.75em">' +
          '<input type="checkbox" id="t-default" style="width:auto"' + (tpl && tpl.is_default ? ' checked' : '') + '>' +
          '<span>' + I18n.t('is_default') + '</span>' +
        '</label>' +
        '<div class="modal-actions">' +
          '<button type="button" class="btn-secondary m-cancel">' + I18n.t('cancel') + '</button>' +
          '<button type="submit" class="btn-primary">' + I18n.t('save') + '</button>' +
        '</div>',
      onSubmit: async (form) => {
        const fd = new FormData();
        fd.append('name', form.querySelector('#t-name').value);
        const desc = form.querySelector('#t-desc').value;
        if (desc) fd.append('description', desc);
        fd.append('is_default', form.querySelector('#t-default').checked ? 'true' : 'false');
        const file = form.querySelector('#t-file').files[0];
        if (file) fd.append('html_file', file);
        if (isEdit) await Api.upload('PUT', '/templates/' + tpl.id, fd);
        else await Api.upload('POST', '/templates', fd);
        cachedTemplates = null;
        Views.templates(document.getElementById('view'));
        return true;
      },
    });
  }

  async function templates(container) {
    const resp = await Api.get('/templates');
    const tpls = resp.templates;
    cachedTemplates = tpls;

    const rows = tpls.map((t) =>
      '<tr>' +
        '<td>' + Utils.escapeHtml(t.name) + (t.is_default ? ' <span class="category-chip" style="background:#2f6fed">' + I18n.t('default_badge') + '</span>' : '') + '</td>' +
        '<td>' + Utils.escapeHtml(t.description || '') + '</td>' +
        '<td style="white-space:nowrap">' +
          '<button class="edit-tpl btn-secondary" data-id="' + t.id + '">' + I18n.t('edit_template') + '</button> ' +
          '<button class="del-tpl btn-danger" data-id="' + t.id + '">' + I18n.t('delete_template') + '</button>' +
        '</td>' +
      '</tr>'
    ).join('');

    container.innerHTML =
      '<div class="toolbar"><h2>' + I18n.t('templates_title') + '</h2>' +
        '<div class="spacer"></div>' +
        '<button id="add-tpl" class="btn-primary">' + I18n.t('upload_template') + '</button>' +
      '</div>' +
      '<div class="card">' +
        (tpls.length === 0
          ? '<p class="muted">' + I18n.t('no_templates') + '</p>'
          : '<table class="table"><thead><tr><th>' + I18n.t('template_name') + '</th><th>' + I18n.t('template_description') + '</th><th></th></tr></thead><tbody>' + rows + '</tbody></table>') +
      '</div>';

    container.querySelector('#add-tpl').addEventListener('click', () => openTemplateModal(null));
    container.querySelectorAll('.edit-tpl').forEach((b) => {
      b.addEventListener('click', () => openTemplateModal(getById(tpls, b.dataset.id)));
    });
    container.querySelectorAll('.del-tpl').forEach((b) => {
      b.addEventListener('click', () => UI.run(async () => {
        if (!UI.confirmDialog(I18n.t('confirm_delete'))) return;
        await Api.del('/templates/' + b.dataset.id);
        cachedTemplates = null;
        Views.templates(container);
      }));
    });
  }

  async function exportView(container) {
    if (!cachedTemplates) {
      const tplResp = await Api.get('/templates');
      cachedTemplates = tplResp.templates;
    }
    const tpls = cachedTemplates;
    const tplOptions = '<option value="">' + I18n.t('default_template') + '</option>' +
      tpls.map((t) => '<option value="' + Utils.escapeHtml(t.id) + '">' + Utils.escapeHtml(t.name) + '</option>').join('');

    container.innerHTML =
      '<div class="toolbar"><h2>' + I18n.t('export_title') + '</h2></div>' +
      '<div class="card">' +
        '<label for="exp-month">' + I18n.t('month') + '</label>' +
        '<input type="month" id="exp-month" value="' + currentMonth + '">' +
        '<label for="exp-tpl">' + I18n.t('template') + '</label>' +
        '<select id="exp-tpl">' + tplOptions + '</select>' +
        '<label for="exp-archived" style="display:flex;align-items:center;gap:0.5em;margin-top:0.75em">' +
          '<input type="checkbox" id="exp-archived" style="width:auto">' +
          '<span>' + I18n.t('include_archived') + '</span>' +
        '</label>' +
        '<button id="do-export" class="btn-primary" style="margin-top:1em">' + I18n.t('export_pdf') + '</button>' +
      '</div>' +
      '<div id="export-result"></div>';

    container.querySelector('#do-export').addEventListener('click', () => UI.run(async () => {
      const month = container.querySelector('#exp-month').value;
      const template_id = container.querySelector('#exp-tpl').value || null;
      const include_archived = container.querySelector('#exp-archived').checked;
      const btn = container.querySelector('#do-export');
      if (!month) { UI.toast(I18n.t('select_month'), true); return; }
      UI.setBusy(btn, true);
      try {
        const res = await Api.post('/pdf/export', { month, template_id, include_archived });
        const result = container.querySelector('#export-result');
        result.innerHTML =
          '<div class="card message success">' + I18n.t('export_success') +
          ' <button id="dl-pdf" class="btn-primary">' + I18n.t('download') + '</button></div>';
        result.querySelector('#dl-pdf').addEventListener('click', () => UI.run(async () => {
          const blob = await Api.download('/pdf/' + res.pdf_id);
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = 'berichtsheft-' + month + '.pdf';
          document.body.appendChild(a);
          a.click();
          a.remove();
          URL.revokeObjectURL(url);
        }));
      } finally {
        UI.setBusy(btn, false);
      }
    }));
  }

  function openUserTasksModal(userId, username) {
    let modalForm = null;
    const m = UI.openModal({
      title: username,
      html:
        '<div class="toolbar">' +
          '<input type="month" id="ut-month" value="' + currentMonth + '" style="width:auto">' +
          '<button id="ut-load" class="btn-secondary" type="submit">OK</button>' +
        '</div>' +
        '<div id="ut-body"><p class="muted">' + I18n.t('loading') + '</p></div>',
      onSubmit: async (form) => {
        await loadTasks(form);
        return false;
      },
    });
    modalForm = m.form;
    UI.run(() => loadTasks(modalForm));

    async function loadTasks(form) {
      const month = form.querySelector('#ut-month').value;
      const resp = await Api.get('/admin/user/' + userId + '/tasks?month=' + encodeURIComponent(month));
      const tasks = resp.tasks;
      form.querySelector('#ut-body').innerHTML = tasks.length === 0
        ? '<p class="muted">' + I18n.t('no_tasks') + '</p>'
        : '<table class="table"><tbody>' + tasks.map((t) =>
            '<tr><td>' + Utils.escapeHtml(t.date) + '</td><td>' + Utils.escapeHtml(t.category || '') + '</td><td>' + Utils.escapeHtml(t.description) + '</td></tr>'
          ).join('') + '</tbody></table>';
    }
  }

  let lastInviteToken = null;

  async function admin(container) {
    container.innerHTML =
      '<div class="toolbar">' +
        '<h2>' + I18n.t('admin_title') + '</h2>' +
        '<div class="spacer"></div>' +
        '<button id="tab-users" class="btn-secondary">' + I18n.t('users') + '</button> ' +
        '<button id="tab-audit" class="btn-secondary">' + I18n.t('audit_log') + '</button> ' +
        '<button id="tab-invites" class="btn-secondary">' + I18n.t('invites') + '</button>' +
      '</div>' +
      '<div id="admin-content"></div>';

    const content = container.querySelector('#admin-content');
    const selfId = Storage.user().user_id;

    function setTab(active) {
      ['users', 'audit', 'invites'].forEach((t) => {
        const b = container.querySelector('#tab-' + t);
        if (b) b.classList.toggle('active', t === active);
      });
    }

    async function renderUsers() {
      setTab('users');
      const resp = await Api.get('/admin/users');
      const users = resp.users;
      const rows = users.map((u) => {
        const status = u.archived_at
          ? '<span class="category-chip" style="background:#cf3f3f">' + I18n.t('archived') + '</span>'
          : '<span class="category-chip" style="background:#4ade80">' + I18n.t('active') + '</span>';
        const isSelf = u.id === selfId;
        return '<tr>' +
          '<td>' + Utils.escapeHtml(u.username) + (u.is_admin ? ' <span class="category-chip" style="background:#2f6fed">' + I18n.t('role_admin') + '</span>' : '') + '</td>' +
          '<td>' + Utils.escapeHtml(u.email || '') + '</td>' +
          '<td>' + u.task_count + '</td>' +
          '<td>' + status + '</td>' +
          '<td style="white-space:nowrap">' +
            '<button class="view-user btn-secondary" data-id="' + u.id + '" data-name="' + Utils.escapeHtml(u.username) + '">' + I18n.t('view_tasks') + '</button> ' +
            (isSelf ? '' : (u.archived_at
              ? '<button class="unarchive-user btn-secondary" data-id="' + u.id + '">' + I18n.t('unarchive') + '</button>'
              : '<button class="archive-user btn-danger" data-id="' + u.id + '">' + I18n.t('archive') + '</button>')) +
          '</td></tr>';
      }).join('');

      content.innerHTML =
        '<div class="card">' +
          (users.length === 0 ? '<p class="muted">' + I18n.t('no_users') + '</p>' :
          '<table class="table"><thead><tr>' +
            '<th>' + I18n.t('username') + '</th><th>' + I18n.t('email') + '</th><th>' + I18n.t('task_count') + '</th><th></th><th></th>' +
          '</tr></thead><tbody>' + rows + '</tbody></table>') +
        '</div>';

      content.querySelectorAll('.view-user').forEach((b) => {
        b.addEventListener('click', () => openUserTasksModal(b.dataset.id, b.dataset.name));
      });
      content.querySelectorAll('.archive-user').forEach((b) => {
        b.addEventListener('click', () => UI.run(async () => {
          if (!UI.confirmDialog(I18n.t('confirm_archive'))) return;
          await Api.post('/admin/user/' + b.dataset.id + '/archive', {});
          renderUsers();
        }));
      });
      content.querySelectorAll('.unarchive-user').forEach((b) => {
        b.addEventListener('click', () => UI.run(async () => {
          await Api.post('/admin/user/' + b.dataset.id + '/unarchive', {});
          renderUsers();
        }));
      });
    }

    async function renderAudit() {
      setTab('audit');
      const resp = await Api.get('/admin/audit-log?limit=100');
      const logs = resp.logs;
      const rows = logs.map((l) => {
        let details = '';
        if (l.details && typeof l.details === 'object') details = Utils.escapeHtml(JSON.stringify(l.details));
        return '<tr>' +
          '<td>' + Utils.escapeHtml((l.timestamp || '').toString().slice(0, 19).replace('T', ' ')) + '</td>' +
          '<td>' + Utils.escapeHtml(l.action) + '</td>' +
          '<td>' + Utils.escapeHtml(l.username || '') + '</td>' +
          '<td>' + Utils.escapeHtml(l.target_username || '') + '</td>' +
          '<td>' + details + '</td>' +
        '</tr>';
      }).join('');
      content.innerHTML =
        '<div class="card"><table class="table"><thead><tr>' +
          '<th>' + I18n.t('timestamp') + '</th><th>' + I18n.t('action') + '</th><th>' + I18n.t('username') + '</th><th>' + I18n.t('target') + '</th><th></th>' +
        '</tr></thead><tbody>' + rows + '</tbody></table></div>';
    }

    async function renderInvites() {
      setTab('invites');
      const resp = await Api.get('/admin/invites');
      const invites = resp.invites;
      const rows = invites.map((inv) => {
        const status = inv.used_at
          ? '<span class="category-chip" style="background:#4ade80">' + I18n.t('used') + '</span>'
          : '<span class="category-chip" style="background:#fbbf24">' + I18n.t('unused') + '</span>';
        return '<tr>' +
          '<td>' + Utils.escapeHtml((inv.created_at || '').toString().slice(0, 10)) + '</td>' +
          '<td>' + Utils.escapeHtml(inv.created_by_username || '') + '</td>' +
          '<td>' + Utils.escapeHtml((inv.expires_at || '').toString().slice(0, 10)) + '</td>' +
          '<td>' + status + '</td>' +
        '</tr>';
      }).join('');

      const msg = lastInviteToken
        ? '<div class="message success">' + I18n.t('invite_created') + ' <code>' + Utils.escapeHtml(lastInviteToken) + '</code>' +
          ' <button id="copy-invite" class="btn-secondary">' + I18n.t('copy') + '</button></div>'
        : '';

      content.innerHTML =
        '<div class="toolbar"><button id="create-invite" class="btn-primary">' + I18n.t('create_invite') + '</button></div>' +
        msg +
        '<div class="card"><table class="table"><thead><tr>' +
          '<th>' + I18n.t('created_at') + '</th><th>' + I18n.t('created_by') + '</th><th>' + I18n.t('expires') + '</th><th>' + I18n.t('status') + '</th>' +
        '</tr></thead><tbody>' + rows + '</tbody></table></div>';

      content.querySelector('#create-invite').addEventListener('click', () => UI.run(async () => {
        const res = await Api.post('/admin/invites', {});
        lastInviteToken = res.invite_token;
        renderInvites();
      }));
      const copyBtn = content.querySelector('#copy-invite');
      if (copyBtn) copyBtn.addEventListener('click', () => UI.run(() => navigator.clipboard.writeText(lastInviteToken)));
    }

    container.querySelector('#tab-users').addEventListener('click', () => UI.run(renderUsers));
    container.querySelector('#tab-audit').addEventListener('click', () => UI.run(renderAudit));
    container.querySelector('#tab-invites').addEventListener('click', () => UI.run(renderInvites));
    UI.run(renderUsers);
  }

  return {
    dashboard,
    categories,
    templates,
    export: exportView,
    admin,
  };
})();
