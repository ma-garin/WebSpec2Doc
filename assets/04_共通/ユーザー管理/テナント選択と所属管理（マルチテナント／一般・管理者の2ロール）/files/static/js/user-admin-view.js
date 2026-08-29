/* ユーザー管理ビュー（#view-user-management）。管理者専用。
 *
 * 扱うのは利用者だけ。テナントそのものの管理は tenant-admin-view.js が担当する。
 *
 * 画面の形は一般的な管理画面に合わせている:
 *   一覧の上に「検索＋件数＋新規登録」、行の操作は「編集／削除」、
 *   新規登録と編集はダイアログ。
 *
 * API はテナント横断の /api/admin/tenancy/*。どの更新APIも更新後のスナップ
 * ショット（tenants/users）を返すので、変更のたびに一覧を取り直さない。
 *
 * 「自分の設定」は個人設定ビュー（account-view.js）の担当。
 *
 * fetch と状態表示は core.js の apiJSON / setViewStatus を使う。
 */
(function () {
  'use strict';

  const view = document.getElementById('view-user-management');
  if (!view) return;

  // core.js の escHtml をそのまま使う。null/undefined を空にする点だけがここの都合。
  const esc = (s) => escHtml(s == null ? '' : s);

  const status = (id, message, kind) => setViewStatus(document.getElementById(id), message, kind);

  const dialogs = createDialogController('uadm-');

  // 「自分の行だけ操作を出さない」ための判定。サーバーが埋めた値を使い、
  // ビューを開くたびに /api/auth/me を引き直さない。
  const currentUserId = view.dataset.currentUserId || '';

  // 直近のスナップショット。編集ダイアログが「いまの所属」を描くのに使う。
  let snapshot = { tenants: [], users: [] };
  // 絞り込み語（小文字化済み）。一覧の描画だけに効き、サーバーへは送らない。
  let query = '';

  /* ── 描画 ── */

  function render(data) {
    snapshot = { tenants: data.tenants || [], users: data.users || [] };
    renderUsers();
    renderTenantOptions();
  }

  function membershipChips(user) {
    const memberships = user.memberships || [];
    if (!memberships.length) return '<span class="uadm-muted">所属なし</span>';
    return memberships.map((m) =>
      `<span class="account-chip ${m.role === 'admin' ? 'is-admin' : ''}">`
      + `${esc(m.name)} / ${m.role === 'admin' ? '管理者' : '一般'}</span>`).join('');
  }

  /** 名前・ログインID・所属テナント名のどれかに含まれれば残す。 */
  function matchesQuery(user) {
    if (!query) return true;
    const haystack = [user.name, user.email]
      .concat((user.memberships || []).map((m) => m.name))
      .join(' ')
      .toLowerCase();
    return haystack.includes(query);
  }

  function renderUsers() {
    const visible = snapshot.users.filter(matchesQuery);

    const count = document.getElementById('uadm-user-count');
    if (count) {
      count.textContent = snapshot.users.length
        ? `${snapshot.users.length}件中 ${visible.length}件 表示中`
        : '';
    }

    const emptyText = query ? '絞り込みに一致するユーザーがいません。' : 'ユーザーがいません。';
    renderTableRows('uadm-user-rows', visible, 5, emptyText, (user) => {
      // 自分自身は消せない・所属も変えられない（自分を締め出す操作を UI に出さない）
      const actions = user.id === currentUserId
        ? '<span class="uadm-muted">自分</span>'
        : '<button type="button" class="btn-outline-sm uadm-act-btn uadm-edit-btn">編集</button>'
          + '<button type="button" class="btn-outline-sm uadm-act-btn uadm-danger'
          + ' uadm-delete-user-btn">削除</button>';
      return `<tr data-user-id="${esc(user.id)}" data-user-label="${esc(user.name)}">
        <td class="uadm-cell-clip" title="${esc(user.name)}">${esc(user.name)}</td>
        <td class="uadm-cell-clip" title="${esc(user.email)}">${esc(user.email)}</td>
        <td class="uadm-cell-wrap">${membershipChips(user)}</td>
        <td class="uadm-cell-seen">${esc(formatSeen(user.last_login_at))}</td>
        <td class="uadm-cell-act">${actions}</td>
      </tr>`;
    });
  }

  /** ISO 文字列は幅を食ううえ秒まで要らないので「YYYY-MM-DD HH:MM」に詰める。 */
  function formatSeen(value) {
    if (!value) return '—';
    const text = String(value);
    return text.length >= 16 ? `${text.slice(0, 10)} ${text.slice(11, 16)}` : text;
  }

  /** 新規登録ダイアログの「所属テナント」候補。 */
  function renderTenantOptions() {
    const select = document.getElementById('uadm-add-tenant');
    if (!select) return;
    const selected = select.value;
    select.innerHTML = snapshot.tenants.map((tenant) =>
      `<option value="${esc(tenant.id)}">${esc(tenant.name)}</option>`).join('');
    if (selected && snapshot.tenants.some((tenant) => tenant.id === selected)) {
      select.value = selected;
    }
  }

  document.getElementById('uadm-user-search')?.addEventListener('input', (ev) => {
    query = ev.target.value.trim().toLowerCase();
    renderUsers();
  });

  /* ── 読み込み ── */

  async function load() {
    // URL直打ちで一般利用者が来た場合。操作できない表を並べず理由を出す。
    if (view.dataset.isAdmin !== '1') {
      view.querySelectorAll('.uadm-admin-only').forEach((card) => { card.hidden = true; });
      const denied = document.getElementById('uadm-denied-card');
      if (denied) denied.hidden = false;
      return;
    }
    try {
      render(await apiJSON('/api/admin/tenancy'));
    } catch (err) {
      status('uadm-user-status', err.message, 'error');
    }
  }

  onViewEnter('user-management', load);

  /* ── 新規登録 ── */

  document.getElementById('uadm-add-btn')?.addEventListener('click', () => {
    ['uadm-add-name', 'uadm-add-email', 'uadm-add-password'].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
    status('uadm-add-status', '');
    dialogs.open('uadm-add-modal', 'uadm-add-name', '#uadm-add-btn');
  });

  document.getElementById('uadm-add-form')?.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    try {
      render(await apiJSON('/api/admin/tenancy/users', 'POST', {
        name: document.getElementById('uadm-add-name').value,
        email: document.getElementById('uadm-add-email').value,
        password: document.getElementById('uadm-add-password').value,
        tenant_id: document.getElementById('uadm-add-tenant').value,
        role: document.getElementById('uadm-add-role').value,
      }));
      dialogs.close();
      status('uadm-user-status', '登録しました ✓', 'success');
    } catch (err) {
      status('uadm-add-status', err.message, 'error');
    }
  });

  /* ── 編集（所属とロール／パスワードリセット） ── */

  let editUserId = '';
  let editUserLabel = '';

  function openUserEdit(userId, label) {
    editUserId = userId;
    editUserLabel = label;

    const title = document.getElementById('uadm-edit-title');
    if (title) title.textContent = `${label} を編集`;

    const user = snapshot.users.find((candidate) => candidate.id === userId);
    const current = new Map((user?.memberships || []).map((m) => [String(m.tenant_id), m.role]));
    const list = document.getElementById('uadm-membership-list');
    if (list) {
      list.innerHTML = snapshot.tenants.length
        ? snapshot.tenants.map((tenant, index) => {
          const role = current.get(String(tenant.id));
          const joined = role !== undefined;
          return `<div class="uadm-membership-row">
            <input type="checkbox" id="uadm-mb-${index}" data-tenant-id="${esc(tenant.id)}"
                   ${joined ? 'checked' : ''}>
            <label for="uadm-mb-${index}">${esc(tenant.name)}</label>
            <select class="uadm-role-select" aria-label="${esc(tenant.name)} でのロール"
                    ${joined ? '' : 'disabled'}>
              <option value="member"${role === 'admin' ? '' : ' selected'}>一般</option>
              <option value="admin"${role === 'admin' ? ' selected' : ''}>管理者</option>
            </select>
          </div>`;
        }).join('')
        : '<p class="uadm-muted">テナントがありません。先にテナント管理で登録してください。</p>';
    }

    const password = document.getElementById('uadm-edit-password');
    if (password) password.value = '';
    status('uadm-edit-status', '');
    dialogs.open('uadm-edit-modal', 'uadm-mb-0',
      `#uadm-user-rows tr[data-user-id="${userId}"] .uadm-edit-btn`);
  }

  // チェックを外したテナントのロールは選べないようにする（保存されない値を触らせない）
  document.getElementById('uadm-membership-list')?.addEventListener('change', (ev) => {
    const checkbox = ev.target.closest('input[type=checkbox][data-tenant-id]');
    if (!checkbox) return;
    const select = checkbox.closest('.uadm-membership-row')?.querySelector('.uadm-role-select');
    if (select) select.disabled = !checkbox.checked;
  });

  document.getElementById('uadm-membership-save')?.addEventListener('click', async () => {
    const rows = document.querySelectorAll('#uadm-membership-list .uadm-membership-row');
    const memberships = Array.from(rows)
      .filter((row) => row.querySelector('input[type=checkbox]').checked)
      .map((row) => ({
        tenant_id: row.querySelector('input[type=checkbox]').dataset.tenantId,
        role: row.querySelector('.uadm-role-select').value,
      }));
    try {
      render(await apiJSON(
        `/api/admin/tenancy/users/${editUserId}/memberships`, 'PUT', { memberships }));
      dialogs.close();
      status('uadm-user-status', `${editUserLabel} の所属を更新しました ✓`, 'success');
    } catch (err) {
      status('uadm-edit-status', err.message, 'error');
    }
  });

  document.getElementById('uadm-reset-submit')?.addEventListener('click', async () => {
    const password = document.getElementById('uadm-edit-password');
    try {
      const result = await apiJSON(`/api/admin/tenancy/users/${editUserId}/password`, 'POST', {
        password: password.value,
      });
      password.value = '';
      if (result.relogin) {
        // 自分自身を再設定した場合は自分のセッションも失効している
        status('uadm-edit-status', 'リセットしました。再ログインしてください… ✓', 'success');
        setTimeout(() => { window.location.href = '/auth/login'; }, 1200);
        return;
      }
      render(result);
      dialogs.close();
      status('uadm-user-status',
        `${editUserLabel} のパスワードをリセットしました。本人に伝えてください ✓`, 'success');
    } catch (err) {
      status('uadm-edit-status', err.message, 'error');
    }
  });

  /* ── 行の操作（編集・削除） ── */

  // 行は描き直されるので、個々のボタンではなく表に委譲する
  document.getElementById('uadm-user-rows')?.addEventListener('click', async (ev) => {
    const row = ev.target.closest('tr[data-user-id]');
    if (!row) return;

    if (ev.target.closest('.uadm-edit-btn')) {
      openUserEdit(row.dataset.userId, row.dataset.userLabel);
      return;
    }
    if (!ev.target.closest('.uadm-delete-user-btn')) return;

    const label = row.dataset.userLabel;
    if (!window.confirm(
      `${label} を削除しますか？所属とセッションも消え、この操作は取り消せません。`)) return;
    try {
      render(await apiJSON(`/api/admin/tenancy/users/${row.dataset.userId}`, 'DELETE'));
      status('uadm-user-status', `${label} を削除しました ✓`, 'success');
    } catch (err) {
      status('uadm-user-status', err.message, 'error');
    }
  });
})();
