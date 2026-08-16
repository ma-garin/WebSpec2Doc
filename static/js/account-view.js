/* 個人設定ビュー（#view-account）。
 *
 * 旧アカウント専用ページ（templates/auth/account.html）を画面内ビューへ移したもの。
 * 中身はビューを開いた時に API から取る。ホームを開くたびにメンバー一覧や
 * APIトークンまで読むのを避けるため、サーバー側では埋め込まない。
 *
 * core.js の switchView('account') から loadAccountView() が呼ばれる。
 */

/* 同一オリジンの JSON API を呼ぶ。旧ページの postJSON と同じ契約。 */
async function accountPostJSON(url, method, body) {
  const res = await fetch(url, {
    method: method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = {};
  try { data = await res.json(); } catch (e) { /* 非JSONレスポンス */ }
  if (!res.ok) throw new Error(data.error || ('エラーが発生しました (' + res.status + ')'));
  return data;
}

function accountSetStatus(id, message, ok) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = message;
  el.className = 'account-status ' + (ok ? 'ok' : 'err');
}

(function () {
  'use strict';

  const view = document.getElementById('view-account');
  if (!view) return;

  const esc = (s) => String(s == null ? '' : s)
    .replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const roleBadge = (role) => role === 'admin'
    ? '<span class="badge-role is-admin">管理者</span>'
    : '<span class="badge-role">一般</span>';

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

  /* ── メンバー一覧（管理者のみ） ── */

  function renderMembers(users, meId) {
    const rows = document.getElementById('member-rows');
    if (!rows) return;
    if (!users.length) {
      rows.innerHTML = '<tr><td colspan="6" class="account-empty">メンバーがいません。</td></tr>';
      return;
    }
    rows.innerHTML = users.map((member) => {
      // 自分自身は無効化できない（自分を締め出す操作を UI に出さない）
      const action = member.id === meId ? '' :
        `<button type="button" class="btn-outline-sm toggle-active-btn" data-active="${member.is_active ? 1 : 0}">`
        + `${member.is_active ? '無効化' : '有効化'}</button>`;
      const state = member.is_active
        ? '<span class="badge-role">有効</span>'
        : '<span class="badge-role is-inactive">無効</span>';
      return `<tr data-user-id="${esc(member.id)}">
        <td>${esc(member.name)}</td>
        <td>${esc(member.email)}</td>
        <td>${roleBadge(member.role)}</td>
        <td>${state}</td>
        <td>${esc(member.last_login_at || '—')}</td>
        <td>${action}</td>
      </tr>`;
    }).join('');
  }

  /* ── APIトークン（管理者のみ） ── */

  function renderTokens(tokens) {
    const rows = document.getElementById('token-rows');
    if (!rows) return;
    if (!tokens.length) {
      rows.innerHTML = '<tr><td colspan="5" class="account-empty">まだ発行されていません。</td></tr>';
      return;
    }
    rows.innerHTML = tokens.map((token) => {
      const state = token.revoked_at
        ? '<span class="badge-role is-inactive">失効</span>'
        : '<span class="badge-role">有効</span>';
      const action = token.revoked_at ? ''
        : '<button type="button" class="btn-outline-sm revoke-token-btn">失効させる</button>';
      return `<tr data-token-id="${esc(token.id)}">
        <td>${esc(token.name)}</td>
        <td>${esc(token.created_at)}</td>
        <td>${esc(token.last_used_at || '—')}</td>
        <td>${state}</td>
        <td>${action}</td>
      </tr>`;
    }).join('');
  }

  /* ── 読み込み ── */

  let currentUserId = '';

  async function load() {
    let me;
    try {
      me = await accountPostJSON('/api/auth/me', 'GET');
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

    // 片方が落ちてももう片方は出す（管理画面が丸ごと白くならないように）
    try {
      renderMembers((await accountPostJSON('/api/auth/users', 'GET')).users || [], currentUserId);
    } catch (err) {
      accountSetStatus('invite-status', err.message, false);
    }
    try {
      renderTokens((await accountPostJSON('/api/auth/api-tokens', 'GET')).tokens || []);
    } catch (err) {
      accountSetStatus('token-status', err.message, false);
    }
  }

  // core.js の switchView から呼ぶ
  window.loadAccountView = load;

  /* ── 操作 ── */

  document.getElementById('password-form')?.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    try {
      await accountPostJSON('/api/auth/password', 'POST', {
        current: document.getElementById('pw-current').value,
        new: document.getElementById('pw-new').value,
      });
      accountSetStatus('password-status', '変更しました。再ログインしてください… ✓', true);
      setTimeout(() => { window.location.href = '/auth/login'; }, 1200);
    } catch (err) {
      accountSetStatus('password-status', err.message, false);
    }
  });

  document.getElementById('invite-form')?.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    try {
      await accountPostJSON('/api/auth/users', 'POST', {
        name: document.getElementById('inv-name').value,
        email: document.getElementById('inv-email').value,
        password: document.getElementById('inv-password').value,
        role: document.getElementById('inv-role').value,
      });
      accountSetStatus('invite-status', '追加しました ✓', true);
      ['inv-name', 'inv-email', 'inv-password'].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.value = '';
      });
      load();
    } catch (err) {
      accountSetStatus('invite-status', err.message, false);
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
      await accountPostJSON('/api/auth/users/' + row.dataset.userId, 'PATCH', { is_active: !active });
      load();
    } catch (err) {
      accountSetStatus('invite-status', err.message, false);
    }
  });

  document.getElementById('token-form')?.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    try {
      const data = await accountPostJSON('/api/auth/api-tokens', 'POST', {
        name: document.getElementById('token-name').value,
      });
      const box = document.getElementById('token-once');
      if (box) {
        box.hidden = false;
        box.textContent = 'このトークンは今だけ表示されます。安全な場所に保存してください: ' + data.token.token;
      }
      accountSetStatus('token-status', '発行しました ✓', true);
      document.getElementById('token-name').value = '';
      load();
    } catch (err) {
      accountSetStatus('token-status', err.message, false);
    }
  });

  document.getElementById('token-rows')?.addEventListener('click', async (ev) => {
    const btn = ev.target.closest('.revoke-token-btn');
    if (!btn) return;
    if (!window.confirm('このAPIトークンを失効させますか？この操作は取り消せません。')) return;
    const row = btn.closest('tr');
    try {
      await accountPostJSON('/api/auth/api-tokens/' + row.dataset.tokenId, 'DELETE');
      load();
    } catch (err) {
      accountSetStatus('token-status', err.message, false);
    }
  });
})();
