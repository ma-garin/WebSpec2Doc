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

  /* ── プロフィール ── */

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
      ? '<a href="/user-management">ユーザー管理</a>'
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

  /* ── APIトークン（管理者のみ） ── */

  async function loadTokens() {
    try {
      const tokens = (await apiJSON('/api/auth/api-tokens')).tokens || [];
      renderTableRows('token-rows', tokens, 5, 'まだ発行されていません。', (token) => {
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
    renderProfile(me);

    // APIトークンはワークスペース単位の資格情報なので管理者のみに出す
    const isAdmin = !!(me.user && me.user.role === 'admin');
    const tokensCard = document.getElementById('account-tokens-card');
    if (tokensCard) tokensCard.hidden = !isAdmin;
    if (!isAdmin) return;

    await loadTokens();
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
