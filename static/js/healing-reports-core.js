/* オートヒーリングの報告書（templates/healing_reports.html・healing_report.html）: 共通: 権限・小さなヘルパー・WS2D との接続・API 呼び出し・時刻と path の表示
   読み込み順: healing-reports-core.js → healing-reports-list.js → healing-reports-doc.js → healing-reports-bundle.js → healing-reports.js。
   ファイル間の共有は window.HealingReports（HL）だけ。他ファイルの関数は呼び出し時に HL から引く。 */
(function (HL) {
  'use strict';

  var IS_ADMIN = document.body.getAttribute('data-hl-admin') === 'true';

  /* ---------------- 小さなヘルパー ---------------- */

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text != null) { node.textContent = String(text); }
    return node;
  }

  function on(id, type, fn) {
    var node = document.getElementById(id);
    if (node) { node.addEventListener(type, fn); }
    return node;
  }

  function showError(message) {
    var box = document.getElementById('hl-error');
    if (!box) { return; }
    box.textContent = '';
    box.appendChild(el('div', null, message));
    box.hidden = false;
  }

  function clearError() {
    var box = document.getElementById('hl-error');
    if (box) { box.hidden = true; box.textContent = ''; }
  }

  /* ---------------- 共通部品 WS2D との接続 ---------------- */

  function hasWS() { return !!(window.WS2D && window.WS2D.status && window.WS2D.reason); }

  /* 内部の状態名は変えず、表示のときだけ標準語（WS2D.status）へ対応付ける。 */
  var WS_REPORT_STATUS = {
    awaiting: ['waiting_approval', null],
    approved: ['done', '承認済み'],
    returned: ['preparing', '差し戻し（再修正中）'],
    rejected: ['cancelled', '却下'],
    submitted: ['done', '提出済み'],
    draft: ['not_started', '下書き']
  };
  var WS_REPORT_REASON = {
    awaiting: '修正案と検証の結果が揃っています。下の証跡を読んでから、承認・差し戻し・却下を判断してください。',
    approved: '承認済みです。内容は変更できません。',
    returned: '差し戻されています。修正のやり直し結果が出るまで判断はできません。',
    rejected: '却下されました。この修正は送られていません。',
    submitted: '提出済みです。顧客に出した内容と証跡は固定されています。',
    draft: '下書きです。承認欄は空のままです。'
  };

  /* 外部のリポジトリや顧客向け記録に影響する判断の確認。WS2D.confirm が無いときは window.confirm。 */
  function askConfirm(opts) {
    if (window.WS2D && typeof window.WS2D.confirm === 'function') { return window.WS2D.confirm(opts); }
    return Promise.resolve(window.confirm(opts.title + '\n' + opts.message));
  }

  /* ページ先頭: 何の画面か・いまの状態・状態の理由。host が無い・WS2D が無いときは何もしない。 */
  function renderHead(o) {
    var head = document.getElementById('hl-page-head');
    if (!head || !hasWS()) { return; }
    var t = document.getElementById('hl-page-title');
    var d = document.getElementById('hl-page-desc');
    var st = document.getElementById('hl-ws-status');
    if (t && o.title) { t.textContent = o.title; }
    if (d && o.desc) { d.textContent = o.desc; }
    /* 状態と理由は topbar の #page-reason に 1 行で出す（本文にチップ・バナーを置かない）。
       共通レイアウトでない画面は従来どおり本文の #hl-ws-status / #hl-ws-reason。 */
    var top = document.getElementById('page-reason');
    if (top && o.reason) {
      if (st) { st.innerHTML = ''; st.hidden = true; }
      window.WS2D.reason(top, (o.statusLabel ? o.statusLabel + '。' : '') + o.reason, o.reasonKind || 'info');
      top.hidden = false;
    } else {
      if (st) { st.innerHTML = o.statusCode ? window.WS2D.status.html(o.statusCode, o.statusLabel || undefined) : ''; st.hidden = false; }
      var r = document.getElementById('hl-ws-reason');
      if (r && o.reason) { window.WS2D.reason(r, o.reason, o.reasonKind || 'info'); r.hidden = false; }
    }
    head.hidden = false;
  }

  /* 判断の文脈: 案件・対象・実行・PR・出力を 1 行に。どの実行の判断かを承認ボタンの前で見失わせない。 */
  function renderContext(items) {
    var box = document.getElementById('hl-doc-context');
    if (!box) { return; }
    box.textContent = '';
    items.forEach(function (it) {
      if (!it || !it.value) { return; }
      var span = el('span', 'c-context__item');
      span.appendChild(document.createTextNode(it.label + ': '));
      var b = el('b');
      if (it.href) {
        var a = el('a', null, it.value);
        a.href = it.href;
        if (it.external) { a.target = '_blank'; a.rel = 'noopener'; }
        b.appendChild(a);
      } else { b.textContent = it.value; }
      span.appendChild(b);
      box.appendChild(span);
    });
    box.hidden = !box.firstChild;
  }

  /* 空・失敗は共通の状態表示（WS2D.state）で出す。無いときは従来の文だけ。 */
  function showState(host, o, fallbackText) {
    if (!host) { return; }
    if (window.WS2D && typeof window.WS2D.state === 'function') {
      host.hidden = false;
      window.WS2D.state(host, o);
    } else {
      host.hidden = false;
      host.textContent = fallbackText;
    }
  }

  function api(path, options) {
    return fetch(path, options || {}).then(function (res) {
      if (res.status === 403) {
        throw new Error('この操作には管理者権限が必要です。');
      }
      return res.json().then(function (data) {
        if (!res.ok) { throw new Error((data && data.error) || '処理に失敗しました'); }
        return data;
      });
    });
  }

  /* 相対時刻。24 時間以内は「3 分前」、それ以降は日付。 */
  function relTime(iso) {
    if (!iso) { return '—'; }
    var t = new Date(iso);
    if (isNaN(t.getTime())) { return iso; }
    var diff = (Date.now() - t.getTime()) / 1000;
    if (diff < 60) { return 'たった今'; }
    if (diff < 3600) { return Math.floor(diff / 60) + ' 分前'; }
    if (diff < 86400) { return Math.floor(diff / 3600) + ' 時間前'; }
    return iso.slice(0, 10);
  }

  /* パスは末尾を残して省略する。先頭を切らないと、どのリポジトリか分からなくなる。 */
  function tailPath(text, max) {
    var s = String(text || '');
    if (s.length <= max) { return s; }
    return '…' + s.slice(s.length - max + 1);
  }

  /* ---- 他ファイルへ公開 ---- */
  HL.IS_ADMIN = IS_ADMIN;
  HL.WS_REPORT_REASON = WS_REPORT_REASON;
  HL.WS_REPORT_STATUS = WS_REPORT_STATUS;
  HL.api = api;
  HL.askConfirm = askConfirm;
  HL.clearError = clearError;
  HL.el = el;
  HL.hasWS = hasWS;
  HL.on = on;
  HL.relTime = relTime;
  HL.renderContext = renderContext;
  HL.renderHead = renderHead;
  HL.showError = showError;
  HL.showState = showState;
  HL.tailPath = tailPath;
})(window.HealingReports = window.HealingReports || {});
