/* ============================================================================
 * TA2 / ws-team.js — チーム（C4）
 *
 *   GET|POST   /api/auth/users            一覧・追加
 *   PATCH      /api/auth/users/<id>       権限・有効/停止
 *   GET|POST   /api/auth/api-tokens       トークン一覧・発行（値は発行直後の 1 回だけ）
 *   DELETE     /api/auth/api-tokens/<id>  失効
 *
 * これらは全て「ログイン済みかつ管理者」が要る。認証オフ（WEBSPEC2DOC_AUTH_MODE=off）や
 * 非管理者では 401/403 が返るので、フォームを閉じて理由を出す。押せるのに必ず失敗する
 * 状態を作らない。招待メールは送らない旨は常に出す（#team-note はテンプレート側で固定）。
 * ========================================================================== */
(function () {
  'use strict';
  var T = window.TA2, $ = T.$, esc = T.esc;
  var S = T.state;

  var loaded = false;
  var locked = false;

  var ROLE_LABEL = { admin: '管理者', member: 'メンバー', viewer: '閲覧のみ' };

  function el(id) { return $('#' + id); }

  function inputs() {
    var list = [];
    ['team-name', 'team-email', 'team-pass', 'team-role', 'token-name'].forEach(function (id) {
      var n = el(id);
      if (n) list.push(n);
    });
    ['#team-new', '#token-new'].forEach(function (sel) {
      var form = document.querySelector(sel);
      if (!form) return;
      var btns = form.querySelectorAll('button');
      for (var i = 0; i < btns.length; i++) list.push(btns[i]);
    });
    var rowCtl = document.querySelectorAll('#team-rows select, #team-rows button, #token-rows button');
    for (var j = 0; j < rowCtl.length; j++) list.push(rowCtl[j]);
    return list;
  }

  function lock(why) {
    locked = true;
    inputs().forEach(function (n) { n.disabled = true; n.title = why; });
    var meta = el('team-meta');
    if (meta) meta.textContent = why;
  }

  function why(e) {
    var msg = (e && e.message) || '';
    if (/403|admin|管理者|forbidden/i.test(msg)) {
      return '管理者のみユーザーとトークンを管理できます。';
    }
    return '認証がオフ（またはログインしていない）ため、ユーザー管理は使えません。'
      + '設定で認証を有効にし、管理者でログインしてください。';
  }

  function initial(name, email) {
    var s = String(name || email || '?').trim();
    return s ? s.charAt(0) : '?';
  }

  function shortDate(iso) {
    if (!iso) return '—';
    var s = String(iso).replace('T', ' ');
    return s.length >= 10 ? s.slice(0, 10) : s;
  }

  /* ---------------------------------------------------------------- メンバー */
  function renderUsers(users) {
    var body = el('team-rows');
    if (!body) return;
    if (!users.length) {
      body.innerHTML = '<tr><td colspan="4" style="color:var(--tx3)">'
        + '登録されている人がいません。</td></tr>';
      return;
    }
    body.innerHTML = users.map(function (u) {
      var role = String(u.role || 'member');
      var opts = ['admin', 'member'].map(function (r) {
        return '<option value="' + r + '"' + (r === role ? ' selected' : '') + '>'
          + esc(ROLE_LABEL[r] || r) + '</option>';
      }).join('');
      if (role !== 'admin' && role !== 'member') {
        opts = '<option value="' + esc(role) + '" selected>' + esc(ROLE_LABEL[role] || role)
          + '</option>' + opts;
      }
      var active = u.is_active !== false;
      return '<tr data-uid="' + esc(u.id) + '">'
        + '<td><span class="avatar">' + esc(initial(u.name, u.email)) + '</span></td>'
        + '<td>' + esc(u.name || '（名前なし）')
        + '<br><small style="color:var(--tx3)">' + esc(u.email || '') + '</small></td>'
        + '<td><select class="role-sel" aria-label="権限">' + opts + '</select></td>'
        + '<td><button type="button" class="btn sm act-toggle">'
        + (active ? '停止する' : '有効にする') + '</button>'
        + '<div><span class="pill ' + (active ? 'p-pass' : 'p-new') + '">'
        + (active ? '有効' : '停止中') + '</span></div></td></tr>';
    }).join('');
    bindRows();
  }

  /** PATCH / DELETE は T.api（GET/POST のみ）に口が無いので素の fetch を使う。 */
  function patchUser(uid, body, okMsg) {
    return fetch('/api/auth/users/' + encodeURIComponent(uid), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok || j.error) throw new Error(j.error || ('HTTP ' + r.status));
        T.toast(okMsg, 'ok');
        return load(true);
      });
    }, function () { throw new Error('サーバに接続できませんでした'); });
  }

  function bindRows() {
    var sels = document.querySelectorAll('#team-rows .role-sel');
    for (var i = 0; i < sels.length; i++) {
      sels[i].addEventListener('change', function (e) {
        var tr = e.target.closest('tr');
        patchUser(tr.dataset.uid, { role: e.target.value }, '権限を変えました')
          .catch(function (err) { T.toast('変えられませんでした: ' + err.message, 'ng'); });
      });
    }
    var btns = document.querySelectorAll('#team-rows .act-toggle');
    for (var j = 0; j < btns.length; j++) {
      btns[j].addEventListener('click', function (e) {
        var tr = e.target.closest('tr');
        var turnOn = e.target.textContent.indexOf('有効') >= 0;
        patchUser(tr.dataset.uid, { is_active: turnOn }, turnOn ? '有効にしました' : '停止しました')
          .catch(function (err) { T.toast('変えられませんでした: ' + err.message, 'ng'); });
      });
    }
    var del = document.querySelectorAll('#token-rows .tok-del');
    for (var k = 0; k < del.length; k++) {
      del[k].addEventListener('click', function (e) {
        var id = e.target.closest('tr').dataset.tid;
        if (!window.confirm('このトークンを失効させます。CI から呼べなくなります。')) return;
        fetch('/api/auth/api-tokens/' + encodeURIComponent(id), { method: 'DELETE' })
          .then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            T.toast('トークンを失効させました', 'ok');
            load(true);
          })
          .catch(function (err) { T.toast('失効できませんでした: ' + err.message, 'ng'); });
      });
    }
  }

  /* --------------------------------------------------------------- トークン */
  function renderTokens(tokens) {
    var body = el('token-rows');
    if (!body) return;
    var live = tokens.filter(function (t) { return !t.revoked_at; });
    if (!live.length) {
      body.innerHTML = '<tr><td colspan="3" style="color:var(--tx3)">'
        + '有効なトークンはありません。</td></tr>';
      return;
    }
    body.innerHTML = live.map(function (t) {
      return '<tr data-tid="' + esc(t.id) + '"><td>' + esc(t.name || '（名前なし）') + '</td>'
        + '<td>' + esc(shortDate(t.created_at)) + '</td>'
        + '<td><button type="button" class="btn sm tok-del">失効</button></td></tr>';
    }).join('');
    bindRows();
  }

  function showIssued(token) {
    var box = el('token-issued');
    if (!box) return;
    box.hidden = false;
    box.innerHTML = '<div style="font-size:11px;color:var(--ok-tx);font-weight:700;margin-bottom:5px">'
      + '発行しました（この 1 回だけ表示されます）</div>'
      + '<span class="tok" id="token-value">' + esc(token) + '</span>'
      + '<button type="button" class="btn sm" id="token-copy" style="margin-left:6px">コピー</button>';
    var copy = el('token-copy');
    if (copy) {
      copy.addEventListener('click', function () {
        var text = (el('token-value') || {}).textContent || '';
        var done = function () { T.toast('コピーしました', 'ok'); };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done, function () {
            T.toast('コピーできませんでした。文字を選んでコピーしてください', 'ng');
          });
          return;
        }
        T.toast('この環境では自動コピーできません。文字を選んでコピーしてください', 'ng');
      });
    }
  }

  /* ------------------------------------------------------------------ 読込み */
  /** ログイン済みか。認証オフ（未ログイン）ではレールのログアウト form が描かれない。
   *  叩けば必ず 401/400 になる API を先に呼ばないための判定（console を汚さない）。 */
  function loggedIn() {
    return !!document.querySelector('form[action="/auth/logout"]');
  }

  function load(force) {
    if (loaded && !force) return Promise.resolve();
    loaded = true;
    if (!loggedIn()) {
      lock('認証がオフ（またはログインしていない）ため、ユーザー管理は使えません。'
        + '設定で認証を有効にし、管理者でログインしてください。');
      renderUsers([]);
      renderTokens([]);
      inputs().forEach(function (n) { n.disabled = true; });
      return Promise.resolve();
    }
    return T.api.get('/api/auth/users').then(function (r) {
      locked = false;
      var meta = el('team-meta');
      if (meta) meta.textContent = '';
      renderUsers((r && r.users) || []);
      return T.api.get('/api/auth/api-tokens');
    }, function (e) {
      lock(why(e));
      renderUsers([]);
      renderTokens([]);
      throw e;
    }).then(function (r) {
      renderTokens((r && r.tokens) || []);
    }, function () { /* lock 済み。ここでの再通知はしない */ });
  }

  /* -------------------------------------------------------------------- 配線 */
  function bind() {
    var form = el('team-new');
    if (form) {
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        if (locked) return;
        var body = {
          name: (el('team-name') || {}).value || '',
          email: ((el('team-email') || {}).value || '').trim(),
          password: (el('team-pass') || {}).value || '',
          role: (el('team-role') || {}).value || 'member'
        };
        if (!body.email || !body.password) {
          T.toast('メールアドレスと初期パスワードを入れてください', 'ng');
          return;
        }
        T.api.post('/api/auth/users', body).then(function () {
          T.toast('追加しました。初期パスワードを本人に直接お伝えください', 'ok');
          ['team-name', 'team-email', 'team-pass'].forEach(function (id) {
            var n = el(id); if (n) n.value = '';
          });
          load(true);
        }, function (err) { T.toast('追加できませんでした: ' + err.message, 'ng'); });
      });
    }
    var tform = el('token-new');
    if (tform) {
      tform.addEventListener('submit', function (e) {
        e.preventDefault();
        if (locked) return;
        var name = ((el('token-name') || {}).value || '').trim();
        if (!name) { T.toast('トークンの名前を入れてください', 'ng'); return; }
        T.api.post('/api/auth/api-tokens', { name: name }).then(function (r) {
          var tok = (r && r.token) || {};
          if (el('token-name')) el('token-name').value = '';
          if (tok.token) showIssued(tok.token);
          load(true);
        }, function (err) { T.toast('発行できませんでした: ' + err.message, 'ng'); });
      });
    }
  }

  bind();
  T.on('view', function (v) { if (v === 'team') load(false); });
  T.on('boot', function () { if (S.view === 'team') load(false); });
})();
