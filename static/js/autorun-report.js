// AutoRun 実行結果レポート専用ページ（仕様15〜17）。
//
// 8セクション: ダッシュボード / QA仕様書 / 計画 / 分析 / 設計 / ケース / スクリプト / 実行結果
// 成果物が無いセクションは「未生成」と正直に示す。
(function () {
  'use strict';

  var domain = document.body.getAttribute('data-domain') || '';
  var current = '';

  function $(id) { return document.getElementById(id); }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function setContent(nodes) {
    var box = $('arep-content');
    if (!box) return;
    box.replaceChildren.apply(box, nodes);
    var main = $('arep-main');
    if (main) main.scrollTop = 0;
  }

  function notGenerated(source) {
    var wrap = el('div', 'arep-empty');
    wrap.appendChild(el('p', 'arep-empty-title', 'この成果物はまだ生成されていません。'));
    wrap.appendChild(el('p', 'arep-empty-note',
      '「未生成」であり、「内容が無い」「問題が無い」という意味ではありません。'
      + (source ? '（期待する生成物: ' + source + '）' : '')));
    return [wrap];
  }

  // ---------------------------------------------------------------- 各種描画

  function renderDashboard(data) {
    var nodes = [];
    var grid = el('div', 'arep-tiles');

    function tile(label, value, sub) {
      var t = el('div', 'arep-tile');
      t.appendChild(el('div', 'arep-tile-label', label));
      t.appendChild(el('div', 'arep-tile-value', value == null ? '—' : String(value)));
      if (sub) t.appendChild(el('div', 'arep-tile-sub', sub));
      return t;
    }

    grid.appendChild(tile('画面', data.screen_count));
    grid.appendChild(tile('フォーム', data.form_count));
    grid.appendChild(tile('入力項目', data.input_count));
    grid.appendChild(tile('承認済み段階', data.stages_approved + ' / ' + data.stages_total));

    var passed = data.test_passed, failed = data.test_failed, total = data.test_total;
    grid.appendChild(tile('テスト実行', total == null ? '未実行' : total + ' 件'));
    grid.appendChild(tile('成功', passed == null ? '—' : passed));
    grid.appendChild(tile('失敗', failed == null ? '—' : failed,
      failed ? '内容は「実行結果」を参照' : ''));
    nodes.push(grid);

    var scope = el('div', 'arep-scope');
    scope.appendChild(el('strong', null, '報告の範囲について: '));
    scope.appendChild(document.createTextNode(data.claim_scope || ''));
    nodes.push(scope);
    return nodes;
  }

  // Markdown をそのまま読める形で出す（HTML 変換はせず、テキストとして安全に表示）
  function renderMarkdown(text, source) {
    if (!text) return notGenerated(source);
    var nodes = [];
    if (source) nodes.push(el('div', 'arep-source', '出典: ' + source));
    nodes.push(el('pre', 'arep-doc', text));
    return nodes;
  }

  function renderCode(text, source) {
    if (!text) return notGenerated(source);
    var nodes = [];
    if (source) nodes.push(el('div', 'arep-source', '出典: ' + source));
    nodes.push(el('pre', 'arep-code', text));
    return nodes;
  }

  function renderTable(payload) {
    var rows = payload.rows || [];
    if (!rows.length) return notGenerated(payload.source);

    var nodes = [];
    nodes.push(el('div', 'arep-source', '出典: ' + (payload.source || '') + ' / ' + rows.length + ' 件'));

    var wrap = el('div', 'arep-table-wrap');
    var table = el('table', 'arep-table');

    var thead = el('thead');
    var hrow = el('tr');
    (payload.columns || []).forEach(function (c) {
      hrow.appendChild(el('th', null, c.label));
    });
    thead.appendChild(hrow);
    table.appendChild(thead);

    var tbody = el('tbody');
    rows.forEach(function (row) {
      var tr = el('tr');
      (payload.columns || []).forEach(function (c) {
        // 対象サイト由来の文字列を含むため textContent で入れる
        tr.appendChild(el('td', 'arep-td-' + c.key, row[c.key] == null ? '' : String(row[c.key])));
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    nodes.push(wrap);
    return nodes;
  }

  function renderResults(data, source) {
    if (!data) return notGenerated(source);
    var nodes = [];
    nodes.push(el('div', 'arep-source', '出典: ' + (source || '')));

    var summary = data.summary || {};
    var grid = el('div', 'arep-tiles');
    ['total', 'passed', 'failed', 'skipped'].forEach(function (k) {
      if (summary[k] == null) return;
      var t = el('div', 'arep-tile');
      t.appendChild(el('div', 'arep-tile-label', k));
      t.appendChild(el('div', 'arep-tile-value', String(summary[k])));
      grid.appendChild(t);
    });
    if (grid.childNodes.length) nodes.push(grid);

    var tests = data.tests || data.results || [];
    if (Array.isArray(tests) && tests.length) {
      var list = el('div', 'arep-results');
      tests.slice(0, 300).forEach(function (t) {
        var row = el('div', 'arep-result-row');
        var status = String(t.status || t.outcome || '');
        var badge = el('span', 'arep-result-badge is-' + (status === 'passed' ? 'pass' : status === 'failed' ? 'fail' : 'other'), status || '—');
        row.appendChild(badge);
        row.appendChild(el('span', 'arep-result-title', String(t.title || t.name || '')));
        if (t.error || t.message) {
          row.appendChild(el('span', 'arep-result-error', String(t.error || t.message)));
        }
        list.appendChild(row);
      });
      nodes.push(list);
    } else {
      nodes.push(el('p', 'arep-empty-note', 'テスト実行の明細がありません（未実行、または結果が空です）。'));
    }
    return nodes;
  }

  // ---------------------------------------------------------------- 読み込み

  async function load(section) {
    current = section;
    document.querySelectorAll('.arep-nav-item').forEach(function (b) {
      b.classList.toggle('is-active', b.getAttribute('data-section') === section);
    });
    setContent([el('p', 'arep-loading', '読み込んでいます…')]);

    try {
      var res = await fetch('/api/autorun/report/' + encodeURIComponent(domain)
        + '?section=' + encodeURIComponent(section));
      var data = await res.json();
      if (!res.ok) throw new Error(data.error || '読み込みに失敗しました');

      if (data.kind === 'dashboard') setContent(renderDashboard(data.data || {}));
      else if (data.kind === 'markdown') setContent(renderMarkdown(data.text, data.source));
      else if (data.kind === 'code') setContent(renderCode(data.text, data.source));
      else if (data.kind === 'table') setContent(renderTable(data));
      else if (data.kind === 'results') setContent(renderResults(data.data, data.source));
      else setContent(notGenerated());

      try {
        history.replaceState(null, '', '#' + section);
      } catch (e) { /* 履歴が使えない環境では無視 */ }
    } catch (e) {
      setContent([el('div', 'arep-error', e && e.message ? e.message : '読み込みに失敗しました')]);
    }
  }

  function boot() {
    document.querySelectorAll('.arep-nav-item').forEach(function (btn) {
      btn.addEventListener('click', function () {
        load(btn.getAttribute('data-section'));
      });
    });

    var themeBtn = $('arep-theme');
    if (themeBtn) {
      themeBtn.addEventListener('click', function () {
        var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        try { localStorage.setItem('webspec2doc.theme', next); } catch (e) {}
      });
    }

    var initial = (location.hash || '').replace('#', '') || 'dashboard';
    var known = Array.prototype.map.call(
      document.querySelectorAll('.arep-nav-item'),
      function (b) { return b.getAttribute('data-section'); }
    );
    load(known.indexOf(initial) >= 0 ? initial : 'dashboard');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
