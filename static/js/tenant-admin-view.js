/* テナント管理ビュー（#view-tenant-management）。管理者専用。
 *
 * 扱うのはテナント（ワークスペース）そのものだけ。誰がどこに所属するかは
 * ユーザー管理ビュー（user-admin-view.js）の担当。
 *
 * 一覧・ツールバー・ダイアログの作りはユーザー管理と揃えている
 * （同じ .uadm-* を使い、2画面で操作の学習をやり直させない）。
 *
 * fetch と状態表示は core.js の apiJSON / setViewStatus を使う。
 */
(function () {
  'use strict';

  const view = document.getElementById('view-tenant-management');
  if (!view) return;

  const esc = (s) => escHtml(s == null ? '' : s);
  const status = (id, message, kind) => setViewStatus(document.getElementById(id), message, kind);

  const dialogs = createDialogController('tadm-');

  let tenants = [];
  let query = '';

  /* ── 描画 ── */

  function render(data) {
    tenants = data.tenants || [];
    renderTenants();
  }

  function matchesQuery(tenant) {
    if (!query) return true;
    return `${tenant.name} ${tenant.slug}`.toLowerCase().includes(query);
  }

  function renderTenants() {
    const visible = tenants.filter(matchesQuery);

    const count = document.getElementById('tadm-count');
    if (count) {
      count.textContent = tenants.length ? `${tenants.length}件中 ${visible.length}件 表示中` : '';
    }

    const emptyText = query ? '絞り込みに一致するテナントがありません。' : 'テナントがありません。';
    renderTableRows('tadm-rows', visible, 5, emptyText, (tenant) => `
      <tr data-tenant-id="${esc(tenant.id)}" data-tenant-label="${esc(tenant.name)}"
          data-tenant-slug="${esc(tenant.slug)}">
        <td class="uadm-cell-clip" title="${esc(tenant.name)}">${esc(tenant.name)}</td>
        <td class="uadm-cell-clip"><code>${esc(tenant.slug)}</code></td>
        <td>${esc(tenant.member_count)}</td>
        <td class="uadm-cell-seen">${esc(String(tenant.created_at || '').slice(0, 10) || '—')}</td>
        <td class="uadm-cell-act">
          <button type="button" class="btn-outline-sm uadm-act-btn tadm-edit-btn">編集</button>
          <button type="button" class="btn-outline-sm uadm-act-btn uadm-danger tadm-delete-btn">削除</button>
        </td>
      </tr>`);
  }

  document.getElementById('tadm-search')?.addEventListener('input', (ev) => {
    query = ev.target.value.trim().toLowerCase();
    renderTenants();
  });

  /* ── 読み込み ── */

  async function load() {
    if (view.dataset.isAdmin !== '1') {
      view.querySelectorAll('.tadm-admin-only').forEach((card) => { card.hidden = true; });
      const denied = document.getElementById('tadm-denied-card');
      if (denied) denied.hidden = false;
      return;
    }
    try {
      render(await apiJSON('/api/admin/tenancy'));
    } catch (err) {
      status('tadm-status', err.message, 'error');
    }
  }

  onViewEnter('tenant-management', load);

  /* ── 新規登録 ── */

  document.getElementById('tadm-add-btn')?.addEventListener('click', () => {
    ['tadm-name', 'tadm-slug'].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
    status('tadm-add-status', '');
    dialogs.open('tadm-add-modal', 'tadm-name', '#tadm-add-btn');
  });

  document.getElementById('tadm-add-form')?.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    try {
      render(await apiJSON('/api/admin/tenancy/tenants', 'POST', {
        name: document.getElementById('tadm-name').value,
        slug: document.getElementById('tadm-slug').value,
      }));
      dialogs.close();
      status('tadm-status', '登録しました ✓', 'success');
    } catch (err) {
      status('tadm-add-status', err.message, 'error');
    }
  });

  /* ── 編集（改名） ── */

  let editTenantId = '';

  function openTenantEdit(tenantId, label, slug) {
    editTenantId = tenantId;
    const title = document.getElementById('tadm-edit-title');
    if (title) title.textContent = `${label} を編集`;
    const input = document.getElementById('tadm-rename');
    if (input) input.value = label;
    const slugLabel = document.getElementById('tadm-edit-slug');
    if (slugLabel) slugLabel.textContent = slug;
    status('tadm-edit-status', '');
    dialogs.open('tadm-edit-modal', 'tadm-rename',
      `#tadm-rows tr[data-tenant-id="${tenantId}"] .tadm-edit-btn`);
  }

  document.getElementById('tadm-edit-form')?.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    try {
      render(await apiJSON(`/api/admin/tenancy/tenants/${editTenantId}`, 'PATCH', {
        name: document.getElementById('tadm-rename').value,
      }));
      dialogs.close();
      status('tadm-status', '保存しました ✓', 'success');
    } catch (err) {
      status('tadm-edit-status', err.message, 'error');
    }
  });

  /* ── 行の操作（編集・削除） ── */

  document.getElementById('tadm-rows')?.addEventListener('click', async (ev) => {
    const row = ev.target.closest('tr[data-tenant-id]');
    if (!row) return;

    if (ev.target.closest('.tadm-edit-btn')) {
      openTenantEdit(row.dataset.tenantId, row.dataset.tenantLabel, row.dataset.tenantSlug);
      return;
    }
    if (!ev.target.closest('.tadm-delete-btn')) return;

    const label = row.dataset.tenantLabel;
    // 生成物が残ることは押す前に伝える（消えたつもりでディスクが空かない事故を防ぐ）
    if (!window.confirm(
      `テナント「${label}」を削除しますか？所属も消えます。`
      + `output/tenants/${row.dataset.tenantSlug} 配下の生成物は残ります。`
      + 'この操作は取り消せません。')) return;
    try {
      const result = await apiJSON(`/api/admin/tenancy/tenants/${row.dataset.tenantId}`, 'DELETE');
      render(result);
      status('tadm-status', `削除しました ✓ ${result.note || ''}`.trim(), 'success');
    } catch (err) {
      status('tadm-status', err.message, 'error');
    }
  });
})();
