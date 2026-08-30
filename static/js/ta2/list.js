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
      // 数だけ出しても次の一手が分からない。失敗があるなら、そこへ入る導線をこの行に置く
      var txt = c.pass + ' 成功 · ' + c.fail + ' 失敗 · ' + c.flaky + ' 不安定 · '
        + (c.fixed + c['new']) + ' 未実行';
      var next = c.fail ? '<button class="sublink" id="go-fail">失敗 ' + c.fail + ' 件から直す</button>'
        : c.flaky ? '<button class="sublink" id="go-flaky">不安定 ' + c.flaky + ' 件を確認</button>'
          : (c.fixed + c['new']) ? '<button class="sublink" id="go-run">▶ 全件実行</button>' : '';
      sub.innerHTML = esc(txt) + (next ? '<br>' + next : '');
    }
    renderBadge('#bd-fail', c.fail);
    renderBadge('#bd-drift', openDriftCount());
    renderSiteSelector();

    if (items) {
    items.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ' && e.key !== 'Spacebar') return;
      var it = e.target.closest && e.target.closest('.it');
      if (!it) return;
      e.preventDefault();
      if (it.dataset.gen) { T.emit('new', { screen: it.dataset.gen }); return; }
      if (it.dataset.id) T.select(it.dataset.id);
    });
  }

  $$('#fchips .fchip').forEach(function (ch) {
      var on = ch.dataset.f === S.filter;
      ch.classList.toggle('on', on);
      ch.setAttribute('aria-pressed', on ? 'true' : 'false');
    });

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
        html += '<div class="it empty" data-gen="' + esc(scr) + '" role="button" tabindex="0">'
          + '<i class="i-new"></i><b>未作成 · 地図から生成</b></div>';
        return;
      }
      ts.forEach(function (t) {
        var on = t.id === S.sel;
        html += '<div class="it ' + (on ? 'on' : '') + '" data-id="' + esc(t.id) + '"'
          + ' role="option" aria-selected="' + (on ? 'true' : 'false') + '" tabindex="' + (on ? '0' : '-1') + '"'
          + ' title="' + esc(t.name) + ' · ' + esc(T.statusLabel[t.status] || t.status) + '">'
          + '<i class="i-' + esc(t.status) + '"></i><b>' + esc(t.name) + '</b>'
          + '<code>' + esc(String(t.id).replace(/^PW-/, '')) + '</code></div>';
      });
    });
    var items = $('#items');
    if (items) {
      items.innerHTML = html || emptyHTML();
      var on = $('#items .it.on');
      if (on) on.scrollIntoView({ block: 'nearest' });
    }
  }

  /** 0 件のときは「なぜ 0 件か」と「戻し方」を出す。「該当なし」だけだと手詰まりに見える */
  function emptyHTML() {
    if (!S.ready) return '<div class="it empty"><b>読み込み中…</b></div>';
    if (!S.tests.length) {
      return '<div class="it empty" style="display:block;padding:14px 16px;line-height:1.7">'
        + '<b>このサイトのテストはまだありません</b>'
        + '<div style="font-size:11.5px">下の「＋ 新しいテスト」か、⌂ サイトの地図から作れます</div></div>';
    }
    var why = [];
    if (S.filter !== 'all') why.push('状態「' + esc(chipLabel(S.filter)) + '」');
    if (S.q.trim()) why.push('検索「' + esc(S.q.trim()) + '」');
    return '<div class="it empty" style="display:block;padding:14px 16px;line-height:1.7">'
      + '<b>条件に合うテストがありません</b>'
      + '<div style="font-size:11.5px">' + (why.length ? why.join(' · ') + ' で ' : '')
      + S.tests.length + ' 件中 0 件</div>'
      + '<button class="clearf" id="clear-filters" style="margin:6px 0 0">絞り込みを解除</button></div>';
  }
  function chipLabel(f) {
    var el = $('#fchips .fchip[data-f="' + f + '"]');
    return el ? el.textContent.trim() : f;
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
      if (e.target.closest('#go-fail')) { S.filter = 'fail'; draw(); return; }
      if (e.target.closest('#go-flaky')) { S.filter = 'flaky'; draw(); return; }
      if (e.target.closest('#clear-filters')) {
        S.filter = 'all'; S.q = '';
        var qi = $('#q'); if (qi) qi.value = '';
        draw();
        return;
      }
      var it = e.target.closest('.it');
      if (!it) return;
      if (it.dataset.gen) { T.emit('new', { screen: it.dataset.gen }); return; }
      if (it.dataset.id) T.select(it.dataset.id);
    });
  }

  if (items) {
    items.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ' && e.key !== 'Spacebar') return;
      var it = e.target.closest && e.target.closest('.it');
      if (!it) return;
      e.preventDefault();
      if (it.dataset.gen) { T.emit('new', { screen: it.dataset.gen }); return; }
      if (it.dataset.id) T.select(it.dataset.id);
    });
  }

  $$('#fchips .fchip').forEach(function (ch) {
    ch.addEventListener('click', function () { S.filter = ch.dataset.f; draw(); });
    // role="button" にしたので Enter / Space でも押せるようにする
    ch.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ' && e.key !== 'Spacebar') return;
      e.preventDefault();
      S.filter = ch.dataset.f;
      draw();
    });
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
    if (!next) return;
    var inList = !!(document.activeElement && document.activeElement.closest
      && document.activeElement.closest('#items'));
    T.select(next);
    // 一覧を Tab で辿っている最中は、選択と一緒にフォーカスも移す（roving tabindex）
    if (inList) {
      requestAnimationFrame(function () {
        var el = $('#items .it[data-id="' + (window.CSS && CSS.escape ? CSS.escape(next) : next) + '"]');
        if (el) el.focus();
      });
    }
  });
})();
