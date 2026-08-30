/* ============================================================================
 * TA2 / list.js — 左の一覧（描画・絞り込み・検索・キーボード操作）  FE-A 所有
 * ========================================================================== */
(function () {
  'use strict';
  var T = window.TA2, S = T.state, $ = T.$, $$ = T.$$, esc = T.esc;

  function counts() {
    var c = { all: S.tests.length, fail: 0, flaky: 0, fixed: 0, pass: 0, 'new': 0, running: 0 };
    S.tests.forEach(function (t) { c[t.status] = (c[t.status] || 0) + 1; });
    return c;
  }

  /** 画面の並び。screens に無い画面のテストも落とさない */
  function screenOrder() {
    var order = S.screens.map(function (s) { return s.id; });
    S.tests.forEach(function (t) { if (order.indexOf(t.screen) < 0) order.push(t.screen); });
    return order;
  }

  /** レールのバッジは「未対応（open）の変更」だけを数える。
      S.drift は配列が正だが、パネル側が payload 全体を入れても壊れないようにする */
  function openDriftCount() {
    var d = S.drift;
    var items = Array.isArray(d) ? d : (d && Array.isArray(d.items) ? d.items : []);
    return items.filter(function (x) { return (x.state || 'open') === 'open'; }).length;
  }

  function siteName() {
    var hit = null;
    S.sites.forEach(function (s) { if (s.domain === S.domain) hit = s; });
    return (hit && hit.name) || S.domain || '—';
  }

  function renderBadge(id, n) {
    var el = $(id);
    if (!el) return;
    el.textContent = n;
    el.style.display = n ? '' : 'none';
  }

  function renderSiteSelector() {
    var sel = $('#site-sel');
    if (!sel) return;
    if (S.sites.length < 2) { sel.style.display = 'none'; return; }
    sel.style.display = '';
    sel.innerHTML = S.sites.map(function (s) {
      return '<option value="' + esc(s.domain) + '"' + (s.domain === S.domain ? ' selected' : '') + '>'
        + esc(s.name || s.domain) + '</option>';
    }).join('');
  }

  function render() {
    var c = counts();
    var name = $('#site-name'); if (name) name.textContent = siteName();
    var cnt = $('#cnt-all'); if (cnt) cnt.textContent = c.all + ' tests';
    var sub = $('#list-sub');
    if (sub) {
      sub.textContent = c.pass + ' 成功 · ' + c.fail + ' 失敗 · ' + c.flaky + ' 不安定 · '
        + (c.fixed + c['new']) + ' 未実行';
    }
    renderBadge('#bd-fail', c.fail);
    renderBadge('#bd-drift', openDriftCount());
    renderSiteSelector();

    $$('#fchips .fchip').forEach(function (ch) { ch.classList.toggle('on', ch.dataset.f === S.filter); });

    var q = S.q.trim().toLowerCase();
    var html = '';
    screenOrder().forEach(function (scr) {
      var meta = T.screenOf(scr);
      var ts = S.tests.filter(function (t) {
        if (t.screen !== scr) return false;
        if (S.filter !== 'all' && t.status !== S.filter) return false;
        if (q && (t.name + ' ' + t.id + ' ' + (t.case_id || '') + ' ' + (meta.name || '')).toLowerCase().indexOf(q) < 0) return false;
        return true;
      });
      if (!ts.length && (S.filter !== 'all' || q)) return;
      html += '<div class="grp">' + esc(scr) + ' ' + esc(meta.name || '') + '<span>' + ts.length + '</span></div>';
      if (!ts.length) {
        html += '<div class="it empty" data-gen="' + esc(scr) + '"><i class="i-new"></i><b>未作成 · 地図から生成</b></div>';
        return;
      }
      ts.forEach(function (t) {
        html += '<div class="it ' + (t.id === S.sel ? 'on' : '') + '" data-id="' + esc(t.id) + '">'
          + '<i class="i-' + esc(t.status) + '"></i><b>' + esc(t.name) + '</b>'
          + '<code>' + esc(String(t.id).replace(/^PW-/, '')) + '</code></div>';
      });
    });
    var items = $('#items');
    if (items) {
      items.innerHTML = html || '<div class="it empty"><b>' + (S.ready ? '該当なし' : '読み込み中…') + '</b></div>';
      var on = $('#items .it.on');
      if (on) on.scrollIntoView({ block: 'nearest' });
    }
  }

  var draw = T.repaint(render);
  T.on('render', draw);
  T.on('tests', draw);
  T.on('drift', draw);
  T.on('select', draw);

  /* ------------------------------------------------------------ bindings */
  var items = $('#items');
  if (items) {
    items.addEventListener('click', function (e) {
      var it = e.target.closest('.it');
      if (!it) return;
      if (it.dataset.gen) { T.emit('new', { screen: it.dataset.gen }); return; }
      if (it.dataset.id) T.select(it.dataset.id);
    });
  }

  $$('#fchips .fchip').forEach(function (ch) {
    ch.addEventListener('click', function () { S.filter = ch.dataset.f; draw(); });
  });

  var q = $('#q');
  if (q) q.addEventListener('input', function (e) { S.q = e.target.value; draw(); });

  var siteSel = $('#site-sel');
  if (siteSel) {
    siteSel.addEventListener('change', function () {
      // ドメインを変えるとテスト・要素辞書・地図がすべて入れ替わる。素直に読み直す
      location.href = '/test-automation?domain=' + T.enc(siteSel.value);
    });
  }

  var newBtn = $('#new-btn');
  if (newBtn) {
    newBtn.addEventListener('click', function () {
      var cur = T.current();
      T.emit('new', { screen: cur ? cur.screen : (S.screens[0] || {}).id });
    });
  }

  /* 「全件実行」（#run-all-btn / #run-all-btn2）の配線は panels.js の
     document 委譲 1 箇所に集約した。ここで addEventListener すると
     同じクリックで POST /api/ta2/run が 2 回飛び、2 回目が 409 になる（10c）。*/

  /* ----------------------------------------------------------- keyboard */
  function typing() {
    var el = document.activeElement;
    if (!el) return false;
    return el.tagName === 'INPUT' || el.tagName === 'SELECT' || el.tagName === 'TEXTAREA' || el.isContentEditable;
  }

  document.addEventListener('keydown', function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      if (q) { q.focus(); q.select(); }
      return;
    }
    if (typing()) return;
    if (S.view !== 'test') return;
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    e.preventDefault();
    var ids = $$('#items .it[data-id]').map(function (x) { return x.dataset.id; });
    var i = ids.indexOf(S.sel);
    var next = ids[i + (e.key === 'ArrowDown' ? 1 : -1)];
    if (next) T.select(next);
  });
})();
