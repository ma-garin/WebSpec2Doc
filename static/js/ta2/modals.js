/* WebSpec2Doc テスト自動化 (System 02) — モーダル群（FE-B）
 * #ov-new   新しいテスト（地図の穴 / 名前から生成）
 * #ov-trace 実行の証跡（ステップの時系列・成果物リンク）
 * #ov-help  使い方
 * 表示内容はすべて API 応答から作る。 */
(function () {
  'use strict';

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var esc = function (v) {
    return String(v == null ? '' : v).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  };
  var ENTRY_HASH = window.location.hash;
  var helpShown = false;

  function TA() { return window.TA2; }
  function state() { return (window.TA2 && window.TA2.state) || {}; }
  function api() { return (TA() && TA().api) || {}; }
  function domain() { return state().domain || ''; }
  function tests() { return Array.isArray(state().tests) ? state().tests : []; }
  function toast(m, c) { if (TA() && TA().toast) TA().toast(m, c || ''); }
  function errText(e) { return (e && e.message) || 'サーバに接続できません'; }
  /* モーダルを開いたらフォーカスをモーダルの中へ移す。
     移さないと Tab が背後の画面を巡り、Enter が背後のボタンを押してしまう */
  var lastFocus = null;
  var FOCUSABLE = 'input,select,textarea,button:not([data-close]),a[href],[tabindex]:not([tabindex="-1"])';
  function focusInto(o) {
    var md = o.querySelector('.md');
    if (!md) return;
    var el = md.querySelector(FOCUSABLE) || md.querySelector('button');
    if (el) { try { el.focus(); } catch (e) { /* 隠れている要素は諦める */ } }
  }
  function open(id) {
    var o = $(id);
    if (!o) return;
    if (!o.classList.contains('on')) lastFocus = document.activeElement;
    o.classList.add('on');
    setTimeout(function () { focusInto(o); }, 0);
  }
  function close(id) {
    var o = $(id);
    if (o) o.classList.remove('on');
    restoreFocus();
  }
  function restoreFocus() {
    if (!lastFocus) return;
    var el = lastFocus;
    lastFocus = null;
    if (el && el.isConnected && typeof el.focus === 'function') { try { el.focus(); } catch (e) { /* noop */ } }
  }
  function closeAll() {
    var any = $$('.ov.on');
    any.forEach(function (o) { o.classList.remove('on'); });
    if (any.length) restoreFocus();
  }

  function mapScreens() {
    var m = state().map;
    if (Array.isArray(m)) return m;
    if (m && Array.isArray(m.screens)) return m.screens;
    return [];
  }
  function allScreens() {
    var ms = mapScreens();
    if (ms.length) return ms;
    return Array.isArray(state().screens) ? state().screens : [];
  }
  function screenOf(id) {
    var list = allScreens();
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
    return null;
  }
  function currentTest() {
    var id = state().sel;
    var list = tests();
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
    return null;
  }
  function ensureMap(force) {
    if (TA().panels && TA().panels.ensureMap) return TA().panels.ensureMap(force);
    if (!api().map || !domain()) return Promise.resolve();
    return api().map(domain()).then(function (r) {
      if (TA().state) TA().state.map = (r && r.screens) ? r.screens : [];
    }, function () { });
  }
  function refreshTests() {
    if (TA().panels && TA().panels.refreshTests) return TA().panels.refreshTests();
    if (!api().tests || !domain()) return Promise.resolve();
    return api().tests(domain()).then(function (r) {
      var s = TA().state;
      if (s && r) {
        if (r.tests) s.tests = r.tests;
        if (r.elements) s.elements = r.elements;
        if (r.screens) s.screens = r.screens;
      }
    }, function () { });
  }

  /* ==================== 新しいテスト ==================== */
  function fillGaps(scrId) {
    var box = $('#new-gaps');
    if (!box) return;
    var s = screenOf(scrId);
    var gaps = (s && Array.isArray(s.gaps)) ? s.gaps : [];
    if (!gaps.length) {
      box.innerHTML = '<div style="color:var(--tx3);font-size:12px;padding:6px 0">' +
        (s ? 'この画面に、まだテストされていない箇所は見つかりませんでした' : '画面の情報がありません') +
        '</div>';
      return;
    }
    box.innerHTML = gaps.map(function (g, i) {
      return '<label class="gap"><input type="checkbox" value="' + esc(g.id) + '"' + (i < 2 ? ' checked' : '') + '>' +
        '<div><b>' + esc(g.title) + '</b><span>' + esc(g.detail || '') + '</span></div></label>';
    }).join('');
  }
  function fillNew(scrId) {
    var sel = $('#new-screen');
    if (!sel) return;
    var list = allScreens();
    if (!list.length) {
      sel.innerHTML = '';
      var box = $('#new-gaps');
      if (box) box.innerHTML = '<div style="color:var(--tx3);font-size:12px;padding:6px 0">クロール済みの画面がありません。先にサイトをクロールしてください</div>';
      return;
    }
    sel.innerHTML = list.map(function (s) {
      return '<option value="' + esc(s.id) + '">' + esc(s.id) + ' ' + esc(s.name || '') + '</option>';
    }).join('');
    if (scrId && screenOf(scrId)) sel.value = scrId;
    sel.onchange = function () { fillGaps(sel.value); };
    fillGaps(sel.value);
  }
  function openNew(scrId) {
    var ov = $('#ov-new');
    if (!ov) return;
    var name = $('#new-name'); if (name) name.value = '';
    var box = $('#new-gaps');
    if (box) box.innerHTML = '<div style="color:var(--tx3);font-size:12px;padding:6px 0">読み込み中です…</div>';
    open('#ov-new');
    var want = scrId || (currentTest() || {}).screen || '';
    ensureMap(false).then(function () { fillNew(want); });
  }
  function submitNew(btn) {
    var sel = $('#new-screen');
    if (!sel || !sel.value) { toast('画面を選んでください', 'ng'); return; }
    var ids = $$('#new-gaps input[type="checkbox"]').filter(function (c) { return c.checked; })
      .map(function (c) { return c.value; });
    var nameEl = $('#new-name');
    var name = nameEl ? String(nameEl.value || '').trim() : '';
    if (!ids.length && !name) { toast('候補を選ぶか、名前を入力してください', 'ng'); return; }
    if (!api().create) { toast('生成 API を利用できません', 'ng'); return; }

    var body = { domain: domain(), screen: sel.value };
    if (ids.length) body.gap_ids = ids;
    if (name) body.name = name;
    var label = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = '生成中…'; btn.title = 'テストを生成しています'; }

    api().create(domain(), body).then(function (r) {
      var created = (r && r.created) || [];
      if (btn) { btn.disabled = false; btn.textContent = label; btn.title = ''; }
      close('#ov-new');
      return refreshTests().then(function () { return ensureMap(true); }).then(function () {
        if (created.length && TA().select) TA().select(created[0].id);
        else if (TA().render) TA().render();
        toast(created.length + ' 件のテストを生成しました。ステップ表で編集できます', 'ok');
      });
    }, function (e) {
      if (btn) { btn.disabled = false; btn.textContent = label; btn.title = ''; }
      toast('生成できません: ' + errText(e), 'ng');
    });
  }

  /* ==================== 証跡（Trace） ==================== */
  function artifactUrl(id, kind) {
    return '/api/ta2/artifact?domain=' + encodeURIComponent(domain()) +
      '&id=' + encodeURIComponent(id) + '&kind=' + encodeURIComponent(kind);
  }
  function fmtDur(ms) {
    if (ms == null || isNaN(ms)) return '—';
    return (Number(ms) / 1000).toFixed(1) + 's';
  }
  function traceRow(t, s, i, failedAt, reachedAll) {
    var failed = failedAt != null && i === failedAt;
    var reached = reachedAll || (failedAt != null && i < failedAt);
    var mark = failed ? '<span class="fl">✕</span>' : reached ? '<span class="ok">✓</span>' : '<span class="s">·</span>';
    var shot = failed && t.last && t.last.run_id
      ? '<a href="' + esc(artifactUrl(t.id, 'screenshot')) + '" target="_blank" rel="noopener">スクショ</a>'
      : '<span class="s">—</span>';
    var err = failed && t.last && t.last.error
      ? '<br><span class="fl">' + esc(String(t.last.error).split('\n')[0]) + '</span>' : '';
    return '<div class="tr ' + (failed ? 'ng' : '') + '">' +
      '<span class="s">' + (s.kind === 'pre' ? '前提' : i) + '</span>' + mark +
      '<span>' + esc(s.action) + ' ' + esc(s.arg || '') +
      ' <span class="s">' + esc(s.loc || '') + '</span>' + err + '</span>' +
      '<div>' + (failed ? '<span class="s">—</span>' : '<span class="s">—</span>') + '</div>' +
      '<div>' + shot + '</div></div>';
  }
  function openTrace(test) {
    var t = test || currentTest();
    var body = $('#trace-body');
    if (!body) return;
    if (!t) { toast('先に一覧からテストを選んでください', 'ng'); return; }
    var last = t.last || {};
    var title = $('#trace-title');
    if (title) {
      title.textContent = t.id + ' · ' + t.name +
        (last.at ? ' · ' + last.at : '') + (last.dur_ms != null ? ' · ' + fmtDur(last.dur_ms) : '');
    }
    var steps = Array.isArray(t.steps) ? t.steps : [];
    var failedAt = (t.status === 'fail' && last.step != null) ? last.step : null;
    var reachedAll = (t.status === 'pass' || t.status === 'flaky');
    var head = '<div class="tr" style="color:var(--tx3);font-family:var(--sans);font-size:11px">' +
      '<span>ステップ</span><span></span><span>内容</span><span>Before</span><span>After</span></div>';
    var rows = steps.map(function (s, i) { return traceRow(t, s, i, failedAt, reachedAll); }).join('');

    var links = last.run_id
      ? '<h6>成果物</h6><div style="font-family:var(--sans);font-size:12.5px;display:flex;gap:12px">' +
      '<a href="' + esc(artifactUrl(t.id, 'trace')) + '" target="_blank" rel="noopener">trace.zip</a>' +
      '<a href="' + esc(artifactUrl(t.id, 'screenshot')) + '" target="_blank" rel="noopener">スクリーンショット</a>' +
      '<a href="' + esc(artifactUrl(t.id, 'report')) + '" target="_blank" rel="noopener">レポート</a></div>'
      : '<h6>成果物</h6><div style="font-family:var(--sans);font-size:12.5px;color:var(--tx3)">この実行の証跡はありません（まだ実行していません）</div>';

    var log = last.error
      ? '<h6>エラー</h6><pre>' + esc(last.error) + '</pre>'
      : '<h6>エラー</h6><pre>' + (last.at ? 'エラーはありません' : '未実行') + '</pre>';

    body.innerHTML = head + (rows || '<div class="tr"><span class="s">—</span><span></span><span>ステップがありません</span><div></div><div></div></div>') + links + log;
    open('#ov-trace');
  }
  function downloadTrace() {
    var t = currentTest();
    if (!t || !t.last || !t.last.run_id) { toast('この実行の証跡はありません', 'ng'); return; }
    window.open(artifactUrl(t.id, 'trace'), '_blank');
  }

  /* ==================== 使い方 ==================== */
  var HELP_HTML = '<ul>' +
    '<li>左の一覧からテストを選ぶ。検索・状態チップで絞り込む（<kbd>⌘K</kbd> で検索、<kbd>↑</kbd><kbd>↓</kbd> で移動）</li>' +
    '<li>ステップを押すと、右の画面で対象の要素を指す。下のフィルムからも移動できる</li>' +
    '<li>失敗したテストは、ステップ表の先頭に「なぜ止まったか」が出る。赤いステップの「適用」で修正案を取り込み、「▶ このテストを実行」（<kbd>R</kbd>）で確かめる</li>' +
    '<li>ステップのロケータ・値は文字を押すとその場で直せる（<kbd>Enter</kbd> 保存 / <kbd>Esc</kbd> 取り消し）</li>' +
    '<li>「＋ ステップを追加」→ 右の画面上の要素をクリック → 操作を選ぶと、その場で保存される</li>' +
    '<li>「＋ 新しいテスト」で、サイトの地図が見つけた「まだテストされていない箇所」からテストを生成する</li>' +
    '<li>左レール ▶ で全件実行と結果一覧。◈ でサイトの変更（影響するテストのセレクタを一括修正）。⌂ で画面ごとのカバレッジ</li>' +
    '<li>タイトルは直接編集できる。「⧉ 複製」で複製、「削除」で削除（確認あり）。状態はサーバに保存され、URL（#/tests/&lt;id&gt;）で共有できる</li>' +
    '</ul>';
  function openHelp() {
    var ov = $('#ov-help');
    if (!ov) return;
    var h = ov.querySelector('.mh h3');
    if (h) h.textContent = '使い方';
    var b = ov.querySelector('.mb');
    if (b) b.innerHTML = HELP_HTML;
    open('#ov-help');
  }

  /* ==================== 配線 ==================== */
  function bind() {
    document.addEventListener('click', function (e) {
      var t = e.target;
      var ov = t.classList && t.classList.contains('ov') ? t : null;
      if (ov) { ov.classList.remove('on'); restoreFocus(); return; }
      var closer = t.closest && t.closest('[data-close]');
      if (closer) {
        var host = closer.closest('.ov');
        if (host) { host.classList.remove('on'); restoreFocus(); }
        return;
      }
      var btn = t.closest && t.closest('button');
      if (!btn) return;
      if (btn.id === 'new-btn') { openNew(); return; }
      if (btn.id === 'new-ok') { submitNew(btn); return; }
      if (btn.id === 'trace-btn') { openTrace(); return; }
      if (btn.id === 'trace-dl') { downloadTrace(); return; }
      if (btn.id === 'help-btn') { openHelp(); return; }
      var gen = btn.getAttribute && btn.getAttribute('data-gen');
      if (gen) { openNew(gen); return; }
    });
    document.addEventListener('click', function (e) {
      var it = e.target.closest && e.target.closest('.it[data-gen]');
      if (it) openNew(it.getAttribute('data-gen'));
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeAll();
    });
  }

  function maybeAutoHelp() {
    if (helpShown) return;
    helpShown = true;
    if (!ENTRY_HASH) openHelp();          // 初回（ハッシュ無しの素の入り口）だけ出す。localStorage は使わない
  }

  function init() {
    if (!window.TA2) return;
    bind();
    if (typeof TA2.on === 'function') TA2.on('boot', maybeAutoHelp);
    TA2.modals = {
      openNew: openNew, openTrace: openTrace, openHelp: openHelp,
      close: function (id) { close(id); }
    };
  }

  if (window.TA2) init();
  else document.addEventListener('DOMContentLoaded', init);
})();
