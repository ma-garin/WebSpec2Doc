/* 個人設定ビュー（#view-account）。
 *
 * 旧アカウント専用ページ（templates/auth/account.html）を画面内ビューへ移したもの。
 * 中身はビューを開いた時に API から取る。ホームを開くたびにメンバー一覧や
 * APIトークンまで読むのを避けるため、サーバー側では埋め込まない。
 *
 * fetch と状態表示は core.js の apiJSON / setViewStatus を使う。
 */
(function () {
  'use strict';

  const view = document.getElementById('view-account');
  if (!view) return;

  // core.js の escHtml をそのまま使う。null/undefined を空にする点だけがここの都合。
  const esc = (s) => escHtml(s == null ? '' : s);

  const status = (id, message, kind) => setViewStatus(document.getElementById(id), message, kind);

  const roleBadge = (role) => role === 'admin'
    ? '<span class="badge-role is-admin">管理者</span>'
    : '<span class="badge-role">一般</span>';

  /** 表の中身を描く。空なら理由を1行出す（黙って空の表を見せない）。 */
  function renderRows(tbodyId, items, colspan, emptyText, rowHtml) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;
    tbody.innerHTML = items.length
      ? items.map(rowHtml).join('')
      : `<tr><td colspan="${colspan}" class="account-empty">${esc(emptyText)}</td></tr>`;
  }

  /* ── プロフィール ── */

  let currentUserId = '';

  function renderProfile(me) {
    const box = document.getElementById('account-profile');
    if (!box) return;
    const user = me.user || {};
    const tenant = me.tenant || {};
    const memberships = me.memberships || [];

    const chips = memberships.length
      ? memberships.map((m) => `<span class="account-chip ${m.role === 'admin' ? 'is-admin' : ''}">`
          + `${esc(m.name)} / ${m.role === 'admin' ? '管理者' : '一般'}</span>`).join('')
      : '—';
    const adminLink = user.role === 'admin'
      ? '<a href="/admin/console">テナント・ユーザー管理</a>'
      : '';

    box.innerHTML = `
      <dt>表示名</dt><dd>${esc(user.name)}</dd>
      <dt>ログインID</dt><dd>${esc(user.email)}</dd>
      <dt>ロール</dt>
      <dd>${roleBadge(user.role)} <span class="account-note">（このテナントでのロール）</span></dd>
      <dt>選択中のテナント</dt>
      <dd>${tenant.name ? esc(tenant.name) + '（' + esc(tenant.slug) + '）' : '未選択'}</dd>
      <dt>所属テナント</dt>
      <dd>${chips}<span class="account-links"><a href="/auth/tenant">切り替え</a>${adminLink}</span></dd>
      <dt>最終ログイン</dt><dd>${esc(user.last_login_at || '—')}</dd>
    `;
  }

  /* ── メンバー一覧・APIトークン（管理者のみ） ── */

  async function loadMembers() {
    try {
      const users = (await apiJSON('/api/auth/users')).users || [];
      renderRows('member-rows', users, 6, 'メンバーがいません。', (member) => {
        // 自分自身は無効化できない（自分を締め出す操作を UI に出さない）
        const action = member.id === currentUserId ? '' :
          `<button type="button" class="btn-outline-sm toggle-active-btn" data-active="${member.is_active ? 1 : 0}">`
          + `${member.is_active ? '無効化' : '有効化'}</button>`;
        return `<tr data-user-id="${esc(member.id)}">
          <td>${esc(member.name)}</td>
          <td>${esc(member.email)}</td>
          <td>${roleBadge(member.role)}</td>
          <td>${member.is_active
            ? '<span class="badge-role">有効</span>'
            : '<span class="badge-role is-inactive">無効</span>'}</td>
          <td>${esc(member.last_login_at || '—')}</td>
          <td>${action}</td>
        </tr>`;
      });
    } catch (err) {
      status('invite-status', err.message, 'error');
    }
  }

  async function loadTokens() {
    try {
      const tokens = (await apiJSON('/api/auth/api-tokens')).tokens || [];
      renderRows('token-rows', tokens, 5, 'まだ発行されていません。', (token) => {
        const action = token.revoked_at ? ''
          : '<button type="button" class="btn-outline-sm revoke-token-btn">失効させる</button>';
        return `<tr data-token-id="${esc(token.id)}">
          <td>${esc(token.name)}</td>
          <td>${esc(token.created_at)}</td>
          <td>${esc(token.last_used_at || '—')}</td>
          <td>${token.revoked_at
            ? '<span class="badge-role is-inactive">失効</span>'
            : '<span class="badge-role">有効</span>'}</td>
          <td>${action}</td>
        </tr>`;
      });
    } catch (err) {
      status('token-status', err.message, 'error');
    }
  }

  /* ── 読み込み ── */

  async function load() {
    let me;
    try {
      me = await apiJSON('/api/auth/me');
    } catch (err) {
      // 読めなかったことを黙って空表示にしない
      const box = document.getElementById('account-profile');
      if (box) box.innerHTML = `<dt>読み込み失敗</dt><dd>${esc(err.message)}</dd>`;
      return;
    }
    currentUserId = (me.user && me.user.id) || '';
    renderProfile(me);

    const isAdmin = !!(me.user && me.user.role === 'admin');
    const membersCard = document.getElementById('account-members-card');
    const tokensCard = document.getElementById('account-tokens-card');
    if (membersCard) membersCard.hidden = !isAdmin;
    if (tokensCard) tokensCard.hidden = !isAdmin;
    if (!isAdmin) return;

    // 互いに独立しているので待ち時間を積み上げない。片方が落ちても他方は出す。
    await Promise.all([loadMembers(), loadTokens()]);
  }

  onViewEnter('account', load);

  /* ── 操作 ── */

  document.getElementById('password-form')?.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    try {
      await apiJSON('/api/auth/password', 'POST', {
        current: document.getElementById('pw-current').value,
        new: document.getElementById('pw-new').value,
      });
      status('password-status', '変更しました。再ログインしてください… ✓', 'success');
      setTimeout(() => { window.location.href = '/auth/login'; }, 1200);
    } catch (err) {
      status('password-status', err.message, 'error');
    }
  });

  document.getElementById('invite-form')?.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    try {
      await apiJSON('/api/auth/users', 'POST', {
        name: document.getElementById('inv-name').value,
        email: document.getElementById('inv-email').value,
        password: document.getElementById('inv-password').value,
        role: document.getElementById('inv-role').value,
      });
      status('invite-status', '追加しました ✓', 'success');
      ['inv-name', 'inv-email', 'inv-password'].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.value = '';
      });
      loadMembers();  // 変わったのはメンバー表だけ
    } catch (err) {
      status('invite-status', err.message, 'error');
    }
  });

  // 行は描き直されるので、個々のボタンではなく表に委譲する
  document.getElementById('member-rows')?.addEventListener('click', async (ev) => {
    const btn = ev.target.closest('.toggle-active-btn');
    if (!btn) return;
    const row = btn.closest('tr');
    const active = btn.dataset.active === '1';
    if (active && !window.confirm('このメンバーを無効化しますか？既存のセッションも失効します。')) return;
    try {
      await apiJSON('/api/auth/users/' + row.dataset.userId, 'PATCH', { is_active: !active });
      loadMembers();
    } catch (err) {
      status('invite-status', err.message, 'error');
    }
  });

  document.getElementById('token-form')?.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    try {
      const data = await apiJSON('/api/auth/api-tokens', 'POST', {
        name: document.getElementById('token-name').value,
      });
      const box = document.getElementById('token-once');
      if (box) {
        box.hidden = false;
        box.textContent = 'このトークンは今だけ表示されます。安全な場所に保存してください: ' + data.token.token;
      }
      status('token-status', '発行しました ✓', 'success');
      document.getElementById('token-name').value = '';
      loadTokens();
    } catch (err) {
      status('token-status', err.message, 'error');
    }
  });

  document.getElementById('token-rows')?.addEventListener('click', async (ev) => {
    const btn = ev.target.closest('.revoke-token-btn');
    if (!btn) return;
    if (!window.confirm('このAPIトークンを失効させますか？この操作は取り消せません。')) return;
    const row = btn.closest('tr');
    try {
      await apiJSON('/api/auth/api-tokens/' + row.dataset.tokenId, 'DELETE');
      loadTokens();
    } catch (err) {
      status('token-status', err.message, 'error');
    }
  });
})();
