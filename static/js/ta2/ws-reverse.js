/* ws-reverse.js — リバース解析表示
 * T.reverseRender(host, domain): GET /api/reverse-analysis?domain=... を取得して host に描く。
 * テキストは必ず esc() / textContent 経由。内部 JSON は画面に出さない（id のみ「詳細情報」内）。
 */
(function () {
  'use strict';
  var T = window.TA2;
  if (!T) return;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  var STATE_LABEL = { observed: '実測', static: '静的', inferred: '推論', ambiguous: '曖昧', unknown: '未確認', unavailable: '利用不可' };
  var ORIGIN_LABEL = { runtime: '実行時に観測', static: '静的のみ' };
  var OUTCOME_LABEL = { partial: '一部のみ', success: '完了', failed: '失敗', unknown: '未確認' };
  var SEV_LABEL = { error: 'エラー', warning: '警告', info: '情報' };
  var TABS = [
    { key: 'all', label: 'すべて' },
    { key: 'route', label: 'Route' },
    { key: 'api', label: 'API' },
    { key: 'module', label: 'Module' },
    { key: 'source', label: 'Source' },
    { key: 'diag', label: '診断' }
  ];
  var seq = 0;

  function badge(state) {
    var s = STATE_LABEL[state] ? state : 'unknown';
    return '<span class="rv-badge rv-st-' + s + '">' + esc(STATE_LABEL[s]) + '</span>';
  }
  function isNum(v) { return typeof v === 'number' && isFinite(v); }

  function reverseRender(host, domain) {
    if (!host) return;
    var token = ++seq;
    var data = null;
    var tab = 'all';
    var lastRow = null;

    host.setAttribute('aria-busy', 'true');
    host.innerHTML = '<div class="rv rv-card rv-loading" role="status">リバース解析の結果を読み込んでいます…</div>';

    function load() {
      var my = ++seq; token = my;
      host.setAttribute('aria-busy', 'true');
      host.innerHTML = '<div class="rv rv-card rv-loading" role="status">リバース解析の結果を読み込んでいます…</div>';
      fetch('/api/reverse-analysis?domain=' + encodeURIComponent(domain || ''), { headers: { 'Accept': 'application/json' } })
        .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(function (j) { if (my !== token) return; data = j || {}; host.removeAttribute('aria-busy'); draw(); })
        .catch(function () {
          if (my !== token) return;
          host.removeAttribute('aria-busy');
          data = { state: 'error', message: 'リバース解析の結果を取得できませんでした。', next_action: '通信状態を確認して、再読み込みしてください。' };
          draw();
        });
    }

    /* ---------- 状態カード ---------- */
    function noticeCard(title, d, withReload) {
      var h = '<div class="rv rv-card rv-notice" role="status"><h3 class="rv-notice-title">' + esc(title) + '</h3>';
      if (d.message) h += '<p class="rv-text">' + esc(d.message) + '</p>';
      if (d.next_action) h += '<p class="rv-next"><b>次の行動</b> ' + esc(d.next_action) + '</p>';
      if (withReload) h += '<button type="button" class="rv-btn rv-btn-pri" data-rv="reload">再読み込み</button>';
      return h + '</div>';
    }

    /* ---------- 上部 ---------- */
    function headHtml() {
      var p = data.provider;
      var h = '<div class="rv-head"><div class="rv-head-main"><h2 class="rv-title">リバース解析</h2>' +
        '<p class="rv-lead">実行時観測だけでは見えなかった構造を、静的解析で補完しました。</p></div>';
      if (p && p.name) h += '<div class="rv-prov">解析: ' + esc(p.name) + (p.version ? ' ' + esc(p.version) : '') + '</div>';
      h += '</div>';
      if (data.input_label) h += '<p class="rv-input">対象: ' + esc(data.input_label) + '</p>';
      return h;
    }

    function partialHtml() {
      if (!data.status || data.status === 'complete') return '';
      var h = '<div class="rv-partial" role="status"><b>一部のみ取得しました</b>';
      var msg = data.message || '';
      if (msg) h += '<span> ' + esc(msg) + '</span>';
      if (data.status !== 'partial') h += '<span> 解析の状態: ' + esc(data.status) + '</span>';
      if (data.next_action) h += '<span class="rv-partial-next"> 次の行動: ' + esc(data.next_action) + '</span>';
      return h + '</div>';
    }

    /* ---------- Before / After ---------- */
    function diffHtml(b, a) {
      if (!isNum(b) || !isNum(a)) return '<span class="rv-diff rv-diff-unk">未確認</span>';
      var d = a - b;
      if (d > 0) return '<span class="rv-diff rv-diff-up">+' + d + '</span>';
      if (d === 0) return '<span class="rv-diff rv-diff-zero">変化なし</span>';
      return '<span class="rv-diff rv-diff-down">' + d + '</span>';
    }
    function numHtml(v) { return isNum(v) ? String(v) : '<span class="rv-unk">未確認</span>'; }

    function summaryHtml() {
      var items = data.summary || [];
      var h = '<section class="rv-sec" aria-label="実行時のみとリバース解析の比較"><div class="rv-cols" aria-hidden="true">' +
        '<span>実行時のみ</span><span class="rv-cols-arrow">→</span><span>＋リバース解析</span></div><div class="rv-tiles">';
      items.forEach(function (it) {
        var up = isNum(it.before) && isNum(it.after) && it.after > it.before;
        h += '<div class="rv-tile' + (up ? ' rv-tile-up' : '') + '"><div class="rv-tile-label">' + esc(it.label) + '</div>' +
          '<div class="rv-tile-nums"><span class="rv-num-b" title="">' + numHtml(it.before) + '</span>' +
          '<span class="rv-arrow" aria-hidden="true">→</span><span class="rv-num-a">' + numHtml(it.after) + '</span></div>' +
          '<div class="rv-tile-foot">' + diffHtml(it.before, it.after) + '</div>' +
          (it.note ? '<div class="rv-tile-note">' + esc(it.note) + '</div>' : '') + '</div>';
      });
      var sec = isNum(data.added_seconds) ? data.added_seconds.toFixed(3) + ' 秒' : '<span class="rv-unk">未計測</span>';
      h += '<div class="rv-tile rv-tile-time"><div class="rv-tile-label">追加解析時間</div><div class="rv-tile-nums"><span class="rv-num-a">' + sec + '</span></div>' +
        (data.measured_once ? '<div class="rv-tile-note">単発測定</div>' : '') + '</div>';
      return h + '</div></section>';
    }

    /* ---------- タブ ---------- */
    function group(g) { return (data.evidence || []).filter(function (e) { return e.group === g; }); }
    function rowsFor(key) { return key === 'all' ? (data.evidence || []) : group(key); }
    function count(key) {
      if (key === 'diag') return group('diagnostic').length + (data.diagnostics || []).length;
      return rowsFor(key).length;
    }
    function tabsHtml() {
      var h = '<div class="rv-tabs" role="tablist" aria-label="根拠の種類">';
      TABS.forEach(function (t) {
        var on = t.key === tab;
        h += '<button type="button" role="tab" class="rv-tab' + (on ? ' on' : '') + '" id="rv-tab-' + t.key + '-' + token + '" data-tab="' + t.key +
          '" aria-selected="' + on + '" aria-controls="rv-panel-' + token + '" tabindex="' + (on ? '0' : '-1') + '">' +
          esc(t.label) + '<span class="rv-count">' + count(t.key) + '</span></button>';
      });
      return h + '</div>';
    }

    /* ---------- 一覧 ---------- */
    function originHtml(e) {
      if (e.group === 'api') {
        var m = e.method ? esc(e.method) : '不明';
        var o = ORIGIN_LABEL[e.origin] || '起点不明';
        return '<div class="rv-sub"><span class="rv-method' + (e.method ? '' : ' rv-unk') + '">' + m + '</span> <span class="rv-origin rv-or-' + esc(e.origin || 'x') + '">' + esc(o) + '</span></div>';
      }
      if (e.group === 'route') return '<div class="rv-sub">静的候補・到達は未確認</div>';
      return '';
    }
    function tableHtml(rows) {
      if (!rows.length) return '<p class="rv-empty">該当する根拠はありません</p>';
      var h = '<div class="rv-tablewrap"><table class="rv-table"><thead><tr><th scope="col">種別</th><th scope="col">値</th><th scope="col">状態</th><th scope="col">根拠の位置</th><th scope="col">出所</th></tr></thead><tbody>';
      rows.forEach(function (e) {
        var i = (data.evidence || []).indexOf(e);
        h += '<tr class="rv-row" tabindex="0" data-ev="' + i + '" aria-label="' + esc((e.kind_label || '') + ' ' + (e.value || '') + ' の詳細を開く') + '">' +
          '<td data-l="種別">' + esc(e.kind_label) + '</td>' +
          '<td data-l="値"><span class="rv-val">' + esc(e.value) + '</span>' + originHtml(e) + '</td>' +
          '<td data-l="状態">' + badge(e.state) + '</td>' +
          '<td data-l="根拠の位置">' + (e.location ? '<code class="rv-loc">' + esc(e.location) + '</code>' : '<span class="rv-unk">位置なし</span>') + '</td>' +
          '<td data-l="出所">' + esc(e.provider) + '</td></tr>';
      });
      return h + '</tbody></table></div>';
    }
    function depsHtml() {
      var deps = data.dependencies || [];
      var h = '<h3 class="rv-h3">依存関係</h3>';
      if (!deps.length) return h + '<p class="rv-empty">該当する依存関係はありません</p>';
      h += '<ul class="rv-deps">';
      deps.forEach(function (d) {
        h += '<li class="rv-dep"><div class="rv-dep-line"><span class="rv-val">' + esc(d.source) + '</span> <span aria-hidden="true">→</span><span class="rv-vh"> から </span> <span class="rv-val">' + esc(d.target) + '</span>' +
          (d.external ? ' <span class="rv-chip">外部パッケージ</span>' : '') + '</div>' +
          '<div class="rv-dep-meta">' + esc(d.relation_label) + ' ' + badge(d.state) + ' ' +
          (d.location ? '<code class="rv-loc">' + esc(d.location) + '</code>' : '<span class="rv-unk">位置なし</span>') + '</div>';
        if (d.limitations && d.limitations.length) {
          h += '<details class="rv-dep-lim"><summary>制限事項（' + d.limitations.length + '）</summary><ul class="rv-lim">' +
            d.limitations.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul></details>';
        }
        h += '</li>';
      });
      return h + '</ul>';
    }
    function diagHtml() {
      var h = '';
      var sm = data.source_map || [];
      h += '<h3 class="rv-h3">解析ケースの結果</h3>';
      if (!sm.length) h += '<p class="rv-empty">該当する根拠はありません</p>';
      else {
        h += '<div class="rv-tablewrap"><table class="rv-table rv-table-sm"><thead><tr><th scope="col">ケース</th><th scope="col">結果</th><th scope="col">意味</th></tr></thead><tbody>';
        sm.forEach(function (s) {
          h += '<tr><td data-l="ケース">' + esc(s.label || s.case) + '</td><td data-l="結果"><span class="rv-badge rv-oc-' + esc(s.outcome) + '">' + esc(OUTCOME_LABEL[s.outcome] || s.outcome) + '</span></td><td data-l="意味">' + esc(s.meaning) + '</td></tr>';
        });
        h += '</tbody></table></div>';
      }
      var dg = data.diagnostics || [];
      h += '<h3 class="rv-h3">診断メッセージ</h3>';
      if (!dg.length) h += '<p class="rv-empty">診断メッセージはありません</p>';
      else {
        h += '<ul class="rv-diags">';
        dg.forEach(function (d) {
          var sv = SEV_LABEL[d.severity] ? d.severity : 'info';
          h += '<li class="rv-diag rv-sv-' + sv + '"><span class="rv-badge rv-sev-' + sv + '">' + esc(SEV_LABEL[sv]) + '</span> <span>' + esc(d.message) + '</span>' +
            (d.next_action ? '<div class="rv-sub">次の行動: ' + esc(d.next_action) + '</div>' : '') + '</li>';
        });
        h += '</ul>';
      }
      var cl = data.coverage_limitations || [];
      h += '<h3 class="rv-h3">網羅できていない範囲</h3>';
      if (!cl.length) h += '<p class="rv-empty">記載された制限はありません</p>';
      else h += '<ul class="rv-lim rv-lim-box">' + cl.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>';
      return h;
    }
    function panelHtml() {
      var h = '<div class="rv-panel" role="tabpanel" id="rv-panel-' + token + '" aria-labelledby="rv-tab-' + tab + '-' + token + '">';
      if (tab === 'diag') {
        var dr = group('diagnostic');
        if (dr.length) h += '<h3 class="rv-h3">診断の根拠</h3>' + tableHtml(dr);
        h += diagHtml();
      } else {
        h += tableHtml(rowsFor(tab));
        if (tab === 'module') h += depsHtml();
      }
      return h + '</div>';
    }

    /* ---------- 全体 ---------- */
    function draw() {
      var st = data.state;
      if (st === 'empty') { host.innerHTML = noticeCard('リバース解析結果はまだありません', data, false); return; }
      if (st === 'provider_unavailable') { host.innerHTML = noticeCard('静的解析ツールを利用できません', data, true); return; }
      if (st === 'error') { host.innerHTML = noticeCard('リバース解析の結果を表示できません', data, true); return; }
      host.innerHTML = '<div class="rv">' + headHtml() + partialHtml() + summaryHtml() + '<div class="rv-card rv-main">' + tabsHtml() + '<div id="rv-body">' + panelHtml() + '</div></div></div>';
    }
    function redrawBody() {
      var body = host.querySelector('#rv-body');
      var tabs = host.querySelector('.rv-tabs');
      if (!body || !tabs) return;
      var tmp = document.createElement('div');
      tmp.innerHTML = tabsHtml();
      tabs.parentNode.replaceChild(tmp.firstChild, tabs);
      body.innerHTML = panelHtml();
    }

    /* ---------- Drawer ---------- */
    function closeDrawer() {
      var d = host.querySelector('.rv-drawer-wrap');
      if (d) d.parentNode.removeChild(d);
      if (lastRow && document.contains(lastRow)) lastRow.focus();
      lastRow = null;
    }
    function li(arr) {
      if (!arr || !arr.length) return '<p class="rv-text">記載された制限はありません</p>';
      return '<ul class="rv-lim">' + arr.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>';
    }
    function openDrawer(i, row) {
      var e = (data.evidence || [])[i];
      if (!e) return;
      closeDrawer();
      lastRow = row;
      var w = document.createElement('div');
      w.className = 'rv-drawer-wrap';
      var methodLine = e.group === 'api' ? '<dt>メソッド</dt><dd>' + (e.method ? esc(e.method) : '不明') + '</dd>' : '';
      w.innerHTML = '<div class="rv-backdrop" data-rv="close"></div>' +
        '<aside class="rv-drawer" role="dialog" aria-modal="true" aria-labelledby="rv-dr-t-' + token + '">' +
        '<div class="rv-dr-head"><h3 id="rv-dr-t-' + token + '" class="rv-dr-title">根拠の詳細</h3>' +
        '<button type="button" class="rv-btn" data-rv="close" aria-label="詳細を閉じる">閉じる</button></div>' +
        '<div class="rv-dr-body"><p class="rv-claim">' + esc(e.claim) + '</p><dl class="rv-dl">' +
        '<dt>種別</dt><dd>' + esc(e.kind_label) + '</dd>' +
        '<dt>値</dt><dd class="rv-val">' + esc(e.value) + '</dd>' + methodLine +
        '<dt>状態</dt><dd>' + badge(e.state) + '</dd>' +
        '<dt>出所</dt><dd>' + esc(e.provider) + '</dd>' +
        '<dt>起点</dt><dd>' + esc(ORIGIN_LABEL[e.origin] || '不明') + '</dd>' +
        '<dt>位置</dt><dd>' + (e.location ? '<code class="rv-loc">' + esc(e.location) + '</code>' : '位置なし') + '</dd>' +
        '<dt>対応の根拠</dt><dd>' + esc(e.relation) + '</dd>' +
        '<dt>制限事項</dt><dd>' + li(e.limitations) + '</dd>' +
        '<dt>解析バージョン</dt><dd>' + (e.rea_version ? esc(e.rea_version) : '不明') + '</dd></dl>' +
        '<details class="rv-details"><summary>詳細情報</summary><p class="rv-text">ID: <code>' + esc(e.id) + '</code></p></details></div></aside>';
      host.appendChild(w);
      var btn = w.querySelector('.rv-dr-head .rv-btn');
      if (btn) btn.focus();
    }

    /* ---------- イベント（host に 1 回だけ付け替える） ---------- */
    if (host._rvHandlers) {
      host.removeEventListener('click', host._rvHandlers.click);
      host.removeEventListener('keydown', host._rvHandlers.key);
    }
    function selectTab(key, focus) {
      tab = key;
      redrawBody();
      if (focus) { var b = host.querySelector('.rv-tab[data-tab="' + key + '"]'); if (b) b.focus(); }
    }
    function onClick(ev) {
      var t = ev.target;
      var act = t.closest ? t.closest('[data-rv]') : null;
      if (act) {
        var a = act.getAttribute('data-rv');
        if (a === 'reload') { load(); return; }
        if (a === 'close') { closeDrawer(); return; }
      }
      var tb = t.closest ? t.closest('.rv-tab') : null;
      if (tb && host.contains(tb)) { selectTab(tb.getAttribute('data-tab'), false); return; }
      var row = t.closest ? t.closest('.rv-row') : null;
      if (row && host.contains(row)) openDrawer(parseInt(row.getAttribute('data-ev'), 10), row);
    }
    function onKey(ev) {
      var k = ev.key, t = ev.target;
      var dr = host.querySelector('.rv-drawer');
      if (dr) {
        if (k === 'Escape') { ev.preventDefault(); ev.stopPropagation(); closeDrawer(); return; }
        if (k === 'Tab') {
          var f = dr.querySelectorAll('button, summary, a[href], [tabindex="0"]');
          if (!f.length) return;
          var first = f[0], last = f[f.length - 1];
          if (!dr.contains(document.activeElement)) { ev.preventDefault(); first.focus(); }
          else if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
          else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
        }
        return;
      }
      if (t.classList && t.classList.contains('rv-tab')) {
        var keys = TABS.map(function (x) { return x.key; });
        var idx = keys.indexOf(t.getAttribute('data-tab'));
        var n = -1;
        if (k === 'ArrowRight') n = (idx + 1) % keys.length;
        else if (k === 'ArrowLeft') n = (idx - 1 + keys.length) % keys.length;
        else if (k === 'Home') n = 0;
        else if (k === 'End') n = keys.length - 1;
        if (n >= 0) { ev.preventDefault(); selectTab(keys[n], true); }
        return;
      }
      if (t.classList && t.classList.contains('rv-row') && (k === 'Enter' || k === ' ')) {
        ev.preventDefault();
        openDrawer(parseInt(t.getAttribute('data-ev'), 10), t);
      }
    }
    host._rvHandlers = { click: onClick, key: onKey };
    host.addEventListener('click', onClick);
    host.addEventListener('keydown', onKey);

    load();
  }

  T.reverseRender = reverseRender;
})();
