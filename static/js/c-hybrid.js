/* C. Hybrid 共通 API: window.WS2D（ES5・依存なし）。契約: docs/research/gui-commercial-v2/C_CONTRACT.md */
(function (root) {
  'use strict';
  var doc = root.document;


  // 共通シェルの折りたたみ。保存が使えなくても画面内の操作は続けられる。
  function initSidebar() {
    var shell = doc.querySelector('.app-shell');
    var button = doc.getElementById('sidebar-toggle-btn');
    if (!shell || !button || button.dataset.sidebarBound) { return; }
    button.dataset.sidebarBound = '1';
    var key = 'webspec2doc.sidebar-collapsed';
    function apply(collapsed) {
      shell.classList.toggle('sidebar-collapsed', collapsed);
      button.title = collapsed ? 'サイドバーを広げる' : 'サイドバーを折りたたむ';
      button.setAttribute('aria-label', button.title);
      button.setAttribute('aria-expanded', String(!collapsed));
    }
    try { apply(root.localStorage.getItem(key) === '1'); } catch (_) { apply(false); }
    button.addEventListener('click', function () {
      var collapsed = !shell.classList.contains('sidebar-collapsed');
      apply(collapsed);
      try { root.localStorage.setItem(key, collapsed ? '1' : '0'); } catch (_) { /* 表示操作は継続する */ }
    });
  }
  if (doc.readyState === 'loading') { doc.addEventListener('DOMContentLoaded', initSidebar); }
  else { initSidebar(); }

  function esc(s) {
    return String(s === null || s === undefined ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function el(tag, cls, text) {
    var e = doc.createElement(tag);
    if (cls) { e.className = cls; }
    if (text !== undefined && text !== null) { e.textContent = text; }
    return e;
  }
  function clear(host) { while (host && host.firstChild) { host.removeChild(host.firstChild); } }
  function has(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }

  /* ---- 語彙 ---- */
  var STATUS = {
    not_started: ['未開始', '○'], preparing: ['準備中', '◎'], running: ['実行中', '▶'],
    waiting_review: ['確認待ち', '?'], waiting_approval: ['承認待ち', '!'], partial: ['一部完了', '◐'],
    done: ['完了', '✓'], failed: ['失敗', '×'], cancelled: ['中止', '■'],
    unverified: ['未確認', '△'], unavailable: ['利用不可', '－']
  };
  var EVIDENCE = {
    observed: ['実測', '●', 'fact'], observed_auth: ['認証済み実測', '●🔑', 'fact'],
    record: ['記録', '▣', 'fact'], document: ['文書', '▭', 'inference'],  // 文書の記述は動作の観測ではない
    static: ['静的', '○', 'inference'], inferred: ['推論', '◐', 'inference'],
    ambiguous: ['曖昧', '◇', 'unverified'], unverified: ['未確認', '△', 'unverified'],
    unavailable: ['利用不可', '－', 'unverified']
  };

  function badge(table, base, code, label) {
    var d = has(table, code) ? table[code] : null;
    var text = label || (d ? d[0] : String(code));
    var icon = d ? d[1] : '△';
    var cls = base + ' ' + base + '--' + (d ? esc(code) : 'unknown');
    return '<span class="' + cls + '" data-code="' + esc(code) + '"><span class="' + base +
      '__icon" aria-hidden="true">' + esc(icon) + '</span><span class="' + base + '__text">' + esc(text) + '</span></span>';
  }
  var status = {
    html: function (code, label) { return badge(STATUS, 'c-status', code, label); },
    label: function (code) { return has(STATUS, code) ? STATUS[code][0] : '未確認'; }
  };
  var evidence = {
    html: function (code, label) { return badge(EVIDENCE, 'c-ev', code, label); },
    category: function (code) { return has(EVIDENCE, code) ? EVIDENCE[code][2] : 'unverified'; }
  };

  /* ---- KPI ---- */
  function kpis(host, items) {
    if (!host) { return; }
    clear(host);
    host.classList.add('c-kpis');
    (items || []).forEach(function (it) {
      var unmeasured = it.value === null || it.value === undefined;
      var tag = it.href ? 'a' : (typeof it.onClick === 'function' ? 'button' : 'div');
      var k = el(tag, 'c-kpi' + (it.category ? ' c-kpi--' + it.category : ''));
      if (it.tone) { k.setAttribute('data-tone', String(it.tone)); } /* ok|ng|warn|info */
      if (tag === 'a') { k.setAttribute('href', it.href); }
      if (tag === 'button') { k.setAttribute('type', 'button'); }
      if (typeof it.onClick === 'function') {
        k.addEventListener('click', function (ev) { it.onClick(ev, it); });
      }
      if (it.icon) {
        /* icon は呼び出し側の固定 SVG 文字列（利用者入力を渡さない）。01 の .stat-card-head と同じ並び */
        var head = el('span', 'c-kpi__head');
        var ic = el('span', 'c-kpi__icon');
        ic.setAttribute('aria-hidden', 'true');
        ic.innerHTML = String(it.icon);
        head.appendChild(ic);
        head.appendChild(el('span', 'c-kpi__label', it.label));
        k.appendChild(head);
      } else {
        k.appendChild(el('span', 'c-kpi__label', it.label));
      }
      k.appendChild(el('span', 'c-kpi__value' + (unmeasured ? ' is-unmeasured' : ''), unmeasured ? '未計測' : String(it.value)));
      if (it.sub) { k.appendChild(el('span', 'c-kpi__sub', it.sub)); }
      host.appendChild(k);
    });
  }

  /* ---- 状態表示 ---- */
  var STATE_TITLE = {
    loading: '読み込んでいます…', empty: 'まだデータがありません', error: '処理に失敗しました',
    partial: '一部のみ取得できました', permission: 'この操作の権限がありません',
    unavailable: '利用できません', unverified: '未確認です', stale: '情報が古い可能性があります'
  };
  function state(host, o) {
    if (!host) { return; }
    o = o || {};
    var kind = has(STATE_TITLE, o.kind) ? o.kind : 'error';
    clear(host);
    var box = el('div', 'c-state c-state--' + kind);
    box.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    if (kind === 'loading') {
      box.setAttribute('aria-busy', 'true');
      var sp = el('span', 'c-state__spinner'); sp.setAttribute('aria-hidden', 'true'); box.appendChild(sp);
    }
    box.appendChild(el('p', 'c-state__title', o.title || STATE_TITLE[kind]));
    if (o.message) { box.appendChild(el('p', 'c-state__msg', o.message)); }
    if (o.retained) { box.appendChild(el('p', 'c-state__retained', '既存の結果は保持しています')); }
    if (o.next) { box.appendChild(el('p', 'c-state__next', '次にすること: ' + o.next)); }
    if (typeof o.onAction === 'function') {
      var b = el('button', 'c-btn c-btn--secondary', o.actionLabel || (kind === 'error' ? '再試行' : '実行'));
      b.setAttribute('type', 'button');
      b.addEventListener('click', function (ev) { o.onAction(ev); });
      box.appendChild(b);
    }
    host.appendChild(box);
  }

  function reason(host, text, kind) {
    if (!host) { return; }
    clear(host);
    host.className = (host.className.replace(/\bc-reason(--\w+)?\b/g, '').replace(/\s+/g, ' ').trim() + ' c-reason' +
      (kind ? ' c-reason--' + kind : '')).trim();
    host.setAttribute('role', 'status');
    host.appendChild(el('span', 'c-reason__text', text));
  }

  /* ---- フォーカス管理 ---- */
  var FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
  function focusables(root_) {
    var list = root_.querySelectorAll(FOCUSABLE), out = [], i;
    for (i = 0; i < list.length; i++) { if (!list[i].hidden && list[i].offsetParent !== null) { out.push(list[i]); } }
    return out;
  }
  /* 重なったとき（ドロワーの上の確認など）は一番上だけが Esc・Tab を受ける */
  var trapStack = [];
  function trap(container, onEsc) {
    function handler(ev) {
      if (trapStack[trapStack.length - 1] !== handler) { return; }
      var key = ev.key || ev.keyCode;
      if (key === 'Escape' || key === 'Esc' || key === 27) { ev.preventDefault(); ev.stopPropagation(); onEsc(); return; }
      if (key !== 'Tab' && key !== 9) { return; }
      var f = focusables(container);
      if (!f.length) { ev.preventDefault(); container.focus(); return; }
      var first = f[0], last = f[f.length - 1], a = doc.activeElement;
      if (ev.shiftKey && (a === first || a === container)) { ev.preventDefault(); last.focus(); }
      else if (!ev.shiftKey && a === last) { ev.preventDefault(); first.focus(); }
      else if (!container.contains(a)) { ev.preventDefault(); first.focus(); }
    }
    doc.addEventListener('keydown', handler, true);
    trapStack.push(handler);
    return function () {
      doc.removeEventListener('keydown', handler, true);
      var i = trapStack.indexOf(handler);
      if (i >= 0) { trapStack.splice(i, 1); }
    };
  }
  var uid = 0;
  function nextId(p) { uid += 1; return p + uid; }

  /* ---- ドロワー ---- */
  var drawerCur = null;
  function section(num, title) {
    var s = el('section', 'c-drawer__sec');
    s.setAttribute('data-sec', String(num));
    s.appendChild(el('h3', null, num + '. ' + title));
    return s;
  }
  function none(s) { s.appendChild(el('p', 'c-drawer__none', 'なし')); }
  function kv(s, rows) {
    var dl = el('dl', 'c-drawer__kv');
    rows.forEach(function (r) {
      dl.appendChild(el('dt', null, r.label));
      dl.appendChild(el('dd', null, r.value === null || r.value === undefined ? '未確認' : String(r.value)));
    });
    s.appendChild(dl);
  }
  function ul(s, arr) {
    var l = el('ul', 'c-drawer__list');
    arr.forEach(function (t) { l.appendChild(el('li', null, typeof t === 'string' ? t : (t && t.label ? t.label + ': ' + t.value : String(t)))); });
    s.appendChild(l);
  }
  function drawerClose() {
    var d = drawerCur;
    if (!d) { return; }
    drawerCur = null;
    d.release();
    if (d.node.parentNode) { d.node.parentNode.removeChild(d.node); }
    if (d.backdrop && d.backdrop.parentNode) { d.backdrop.parentNode.removeChild(d.backdrop); }
    doc.body.classList.remove('c-drawer-open');
    var rf = d.returnFocus;
    if (rf && typeof rf.focus === 'function' && doc.body.contains(rf)) { rf.focus(); }
  }
  function drawerOpen(o) {
    o = o || {};
    var prevFocus = o.returnFocus || doc.activeElement;
    drawerClose();
    var titleId = nextId('c-drawer-t');
    var node = el('aside', 'c-drawer');
    node.setAttribute('role', 'dialog'); node.setAttribute('aria-modal', 'true');
    node.setAttribute('aria-labelledby', titleId); node.setAttribute('tabindex', '-1');
    var head = el('div', 'c-drawer__head');
    var hm = el('div');
    var h = el('h2', 'c-drawer__title', o.title || '根拠'); h.id = titleId;
    hm.appendChild(h);
    var st = el('div', 'c-drawer__state');
    if (o.state) {
      var holder = el('span'); holder.innerHTML = has(EVIDENCE, o.state) ? evidence.html(o.state) : status.html(o.state);
      st.appendChild(holder);
    }
    if (o.stateReason) {
      var why = el('span', 'c-drawer__why');
      why.appendChild(el('strong', null, 'なぜこの状態か: '));
      why.appendChild(doc.createTextNode(o.stateReason));
      st.appendChild(why);
    }
    if (st.childNodes.length) { hm.appendChild(st); }
    var close = el('button', 'c-btn c-btn--ghost c-btn--sm', '閉じる');
    close.setAttribute('type', 'button'); close.setAttribute('aria-label', 'ドロワーを閉じる');
    close.addEventListener('click', drawerClose);
    head.appendChild(hm); head.appendChild(close);
    node.appendChild(head);

    var body = el('div', 'c-drawer__body');
    var s1 = section(1, '主張');
    if (o.claim) { s1.appendChild(el('p', 'c-drawer__claim', o.claim)); } else { none(s1); }
    var s2 = section(2, '実測事実');
    if (o.facts && o.facts.length) { kv(s2, o.facts); } else { none(s2); }
    var s3 = section(3, '推論');
    if (o.inferences && o.inferences.length) { ul(s3, o.inferences); } else { none(s3); }
    var s4 = section(4, '制限');
    if (o.limitations && o.limitations.length) { ul(s4, o.limitations); } else { none(s4); }
    /* 出典 / 位置 / Provider・version を別節にする。呼び出し側が sources だけを渡した旧形式は、ラベルで振り分ける */
    var srcRows = (o.sources || []).slice(), locRows = (o.location || []).slice(), provRows = (o.provider || []).slice();
    if (!o.location && !o.provider) {
      srcRows = []; locRows = []; provRows = [];
      (o.sources || []).forEach(function (r) {
        var lb = String((r && r.label) || '');
        if (/位置|場所|行|location/i.test(lb)) { locRows.push(r); }
        else if (/provider|version|バージョン|解析器|出所|解析元/i.test(lb)) { provRows.push(r); }
        else { srcRows.push(r); }
      });
    }
    var s5 = section(5, '出典'); if (srcRows.length) { kv(s5, srcRows); } else { none(s5); }
    var s6 = section(6, '位置'); if (locRows.length) { kv(s6, locRows); } else { none(s6); }
    var s7 = section(7, 'Provider / version'); if (provRows.length) { kv(s7, provRows); } else { none(s7); }
    [s1, s2, s3, s4, s5, s6, s7].forEach(function (s) { body.appendChild(s); });
    if (o.extra) {
      var ex = el('section', 'c-drawer__sec c-drawer__extra');
      if (typeof o.extra === 'string') { ex.textContent = o.extra; } else { ex.appendChild(o.extra); }
      body.appendChild(ex);
    }
    node.appendChild(body);

    var backdrop = el('div', 'c-drawer-backdrop');
    backdrop.addEventListener('click', drawerClose);
    doc.body.appendChild(backdrop);
    doc.body.appendChild(node);
    doc.body.classList.add('c-drawer-open');
    drawerCur = { node: node, backdrop: backdrop, returnFocus: prevFocus, release: trap(node, drawerClose) };
    close.focus();
  }
  var drawer = { open: drawerOpen, close: drawerClose };

  /* ---- モーダル ---- */
  var modalCur = null;
  function modalClose(result) {
    var m = modalCur;
    if (!m) { return; }
    modalCur = null;
    m.release();
    if (m.backdrop.parentNode) { m.backdrop.parentNode.removeChild(m.backdrop); }
    var rf = m.returnFocus;
    if (rf && typeof rf.focus === 'function' && doc.body.contains(rf)) { rf.focus(); }
    if (typeof m.onClose === 'function') { m.onClose(result); }
  }
  function build(o, cls, onClose) {
    var prev = doc.activeElement;
    if (modalCur) { modalClose(); }
    var titleId = nextId('c-modal-t'), bodyId = nextId('c-modal-b');
    var backdrop = el('div', 'c-modal-backdrop');
    var box = el('div', cls);
    box.setAttribute('role', cls.indexOf('c-confirm') === 0 ? 'alertdialog' : 'dialog');
    box.setAttribute('aria-modal', 'true'); box.setAttribute('aria-labelledby', titleId);
    box.setAttribute('aria-describedby', bodyId); box.setAttribute('tabindex', '-1');
    var head = el('div', 'c-modal__head');
    var h = el('h2', 'c-modal__title', o.title || ''); h.id = titleId; head.appendChild(h);
    var body = el('div', 'c-modal__body'); body.id = bodyId;
    var foot = el('div', 'c-modal__foot');
    box.appendChild(head); box.appendChild(body); box.appendChild(foot);
    backdrop.appendChild(box);
    backdrop.addEventListener('mousedown', function (ev) { if (ev.target === backdrop) { modalClose(); } });
    doc.body.appendChild(backdrop);
    modalCur = { backdrop: backdrop, returnFocus: prev, onClose: onClose, release: trap(box, function () { modalClose(); }) };
    return { box: box, body: body, foot: foot };
  }
  function actionBtn(label, cls, fn) {
    var b = el('button', 'c-btn ' + cls, label);
    b.setAttribute('type', 'button');
    b.addEventListener('click', fn);
    return b;
  }
  var modal = {
    open: function (o) {
      o = o || {};
      var p = build(o, 'c-modal');
      if (o.body && o.body.nodeType === 1) { p.body.appendChild(o.body); } else { p.body.textContent = o.body || ''; }
      var first = null;
      (o.actions && o.actions.length ? o.actions : [{ label: '閉じる' }]).forEach(function (a) {
        var b = actionBtn(a.label, a.primary ? 'c-btn--primary' : 'c-btn--secondary', function () {
          if (typeof a.onClick === 'function') { a.onClick(); } else { modalClose(); }
        });
        p.foot.appendChild(b);
        if (!first || a.primary) { first = b; }
      });
      (first || p.box).focus();
    },
    close: function () { modalClose(); }
  };

  /* ---- 確認 ---- */
  function confirmDlg(o) {
    o = o || {};
    return new Promise(function (resolve) {
      var done = false;
      function fin(v) { if (!done) { done = true; resolve(v); } }
      var p = build(o, 'c-confirm' + (o.danger ? ' c-confirm--danger' : ''), function () { fin(false); });
      p.body.appendChild(el('p', null, o.message || ''));
      if (o.detail) { p.body.appendChild(el('div', 'c-confirm__detail', o.detail)); }
      var cancel = actionBtn('キャンセル', 'c-btn--secondary', function () { fin(false); modalClose(); });
      var ok = actionBtn(o.confirmLabel || 'OK', o.danger ? 'c-btn--danger' : 'c-btn--primary', function () { fin(true); modalClose(true); });
      p.foot.appendChild(cancel); p.foot.appendChild(ok);
      /* 破壊操作は誤確定を避けるためキャンセルを初期フォーカスにする */
      (o.danger ? cancel : ok).focus();
    });
  }

  /* ---- トースト ---- */
  var toastHost = null;
  var TOAST_KIND = { info: 'お知らせ：', success: '成功：', warning: '注意：', error: 'エラー：' };
  function toast(message, kind) {
    var k = { info: 1, success: 1, warning: 1, error: 1 }[kind] ? kind : 'info';
    if (!toastHost || !doc.body.contains(toastHost)) {
      toastHost = el('div', 'c-toast-host');
      toastHost.setAttribute('aria-live', 'polite'); toastHost.setAttribute('aria-atomic', 'false');
      doc.body.appendChild(toastHost);
    }
    /* 種類を色だけで伝えない: 先頭に種類の文字を出す */
    var t = el('div', 'c-toast c-toast--' + k);
    t.appendChild(el('span', 'c-toast__kind', TOAST_KIND[k]));
    t.appendChild(el('span', 'c-toast__msg', message));
    toastHost.appendChild(t);
    root.setTimeout(function () { if (t.parentNode) { t.parentNode.removeChild(t); } }, k === 'error' ? 8000 : 4500);
  }

  /* ---- パンくず: 「WebSpec2Doc / 画面 / 子」の 1 形式に統一する ----
     組み立て元は画面ごとに違う（topbar.html の初期値・core.js setHeader・各 System の JS）。
     新規・改修は crumb.set(['画面','子']) を使う。既存 JS が書いた内容は normalize が観察して整える。 */
  var CRUMB_ROOT = 'WebSpec2Doc';
  var crumbBusy = false;
  function crumbNode() { return doc.getElementById('topbar-breadcrumb'); }
  // サイドメニューが現在地(aria-current=page)を持つ画面では、パンくずに重ねない（1 画面 1 個）
  function sideHasCurrent() { return !!doc.querySelector('.app-nav [aria-current="page"]'); }
  function crumbSet(trail, links) {
    var bc = crumbNode();
    if (!bc) { return; }
    crumbBusy = true;
    clear(bc);
    [CRUMB_ROOT].concat(trail || []).forEach(function (t, i, all) {
      if (i) { bc.appendChild(el('span', 'sep', '/')); }
      var href = links && links[i - 1];
      var last = i === all.length - 1;
      var n;
      if (href && !last) { n = el('a', null, t); n.setAttribute('href', href); } else { n = el('span', null, t); }
      if (last && i && !sideHasCurrent()) { n.setAttribute('aria-current', 'page'); }
      bc.appendChild(n);
    });
    crumbBusy = false;
  }
  function crumbNormalize() {
    var bc = crumbNode();
    if (!bc || crumbBusy) { return; }
    crumbBusy = true;
    var seps = bc.querySelectorAll('.sep'), i;
    for (i = 0; i < seps.length; i++) { if (seps[i].textContent !== '/') { seps[i].textContent = '/'; } }
    var first = bc.firstElementChild;
    if (first && first.textContent.replace(/\s/g, '') !== CRUMB_ROOT) {
      var r = el('span', null, CRUMB_ROOT), sp = el('span', 'sep', '/');
      bc.insertBefore(sp, first); bc.insertBefore(r, sp);
    }
    var kids = bc.children, last = kids[kids.length - 1];
    if (last && kids.length > 1 && !last.hasAttribute('aria-current') && !sideHasCurrent()) { last.setAttribute('aria-current', 'page'); }
    crumbBusy = false;
  }
  function crumbWatch() {
    var bc = crumbNode();
    if (!bc) { return; }
    crumbNormalize();
    if (root.MutationObserver) { new root.MutationObserver(crumbNormalize).observe(bc, { childList: true, subtree: true, characterData: true }); }
  }
  if (doc.readyState === 'loading') { doc.addEventListener('DOMContentLoaded', crumbWatch); } else { crumbWatch(); }

  root.WS2D = {
    esc: esc, status: status, evidence: evidence, kpis: kpis, state: state, reason: reason,
    drawer: drawer, confirm: confirmDlg, toast: toast, modal: modal,
    crumb: { set: crumbSet, normalize: crumbNormalize }
  };
})(window);

/* C0（2026-10-24）: 右パネル（共通契約 §2.1）の開閉と保持。layouts/system.html が #app-rpanel を出した画面だけで動く。
   保持は System ごと（localStorage）。中身の描画は System 側の責任。 */
(function () {
  var panel = document.getElementById('app-rpanel');
  var btn = document.getElementById('app-rpanel-toggle');
  if (!panel || !btn || panel.getAttribute('data-bound') === '1') return;
  panel.setAttribute('data-bound', '1');
  var key = 'ws2d.rpanel.' + (panel.getAttribute('data-system') || 'default');
  function apply(collapsed) {
    panel.classList.toggle('is-collapsed', collapsed);
    btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    btn.textContent = collapsed ? '開く' : '閉じる';
    btn.title = collapsed ? '右パネルを開く' : '右パネルを閉じる';
  }
  var saved = null;
  try { saved = window.localStorage.getItem(key); } catch (e) { saved = null; }
  apply(saved === 'collapsed');
  btn.addEventListener('click', function () {
    var next = !panel.classList.contains('is-collapsed');
    apply(next);
    try { window.localStorage.setItem(key, next ? 'collapsed' : 'open'); } catch (e) { /* 保存できなくても開閉は効く */ }
  });
})();
