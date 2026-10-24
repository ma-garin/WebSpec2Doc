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

    // AutoRun自身が実行した自己検証（ミューテーションテスト）のスコア。
    // 生成テストが対象の破壊を実際に検出できるかを毎回確認する。
    var scScore = data.self_check_score, scSurvivors = data.self_check_survivor_count;
    grid.appendChild(tile(
      '自己検証スコア',
      scScore == null ? '未実施' : scScore + '%',
      scSurvivors ? scSurvivors + '件、弱いテストあり' : (scScore != null ? '対象の破壊を正しく検出' : '')
    ));
    // L4 非機能の合否判定（性能・アクセシビリティ・技術的健全性）
    var VERDICT_LABEL = {
      pass: '基準内', fail: '不合格', baseline_established: '基準線を確立', unknown: '未検証',
    };
    (data.nonfunctional_judgements || []).forEach(function (j) {
      var AREA = { performance: '性能', accessibility: 'アクセシビリティ', technical_health: '技術的健全性' };
      grid.appendChild(tile(
        AREA[j.area] || j.area,
        VERDICT_LABEL[j.verdict] || j.verdict,
        j.verdict === 'fail' ? '「実行結果」を参照' : ''
      ));
    });
    nodes.push(grid);

    // L0 解析の完全性。どの範囲についての結論かを、数値より先に示す。
    if (data.observation_scope) {
      var obs = el('div', 'arep-scope');
      obs.appendChild(el('strong', null, '解析できた範囲: '));
      obs.appendChild(document.createTextNode(data.observation_scope));
      nodes.push(obs);
    }
    (data.observation_gaps || []).forEach(function (gap) {
      var g = el('div', 'arep-scope');
      g.appendChild(el('strong', null, '未解析 — ' + gap.kind + '（' + gap.count + '）: '));
      g.appendChild(document.createTextNode(gap.reason));
      nodes.push(g);
    });

    // 非機能判定の主張範囲（ラボ計測である等の限界）
    (data.nonfunctional_judgements || []).forEach(function (j) {
      if (!j.claim_scope) return;
      var c = el('div', 'arep-scope');
      c.appendChild(el('strong', null, (j.area || '') + ' の範囲: '));
      c.appendChild(document.createTextNode(j.claim_scope));
      nodes.push(c);
    });

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

  /* ---------------- オートヒーリングへの受け渡し ----------------
   * 失敗したテストから保守報告書を起こす。ここが「壊れたら直る」の入口。
   * 接続先が未設定なら、その場で何をすればよいかを 1 行で示す。
   */

  var healingProjects = null;  // 一度だけ取る

  function fetchHealingProjects() {
    if (healingProjects) { return Promise.resolve(healingProjects); }
    return fetch('/api/healing/projects')
      .then(function (r) { return r.ok ? r.json() : { projects: [] }; })
      .then(function (d) { healingProjects = d.projects || []; return healingProjects; })
      .catch(function () { healingProjects = []; return healingProjects; });
  }

  function currentDomain() {
    var m = window.location.pathname.match(/\/autorun\/report\/([^/]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  function healingToast(message) {
    var box = document.getElementById('arep-healing-toast');
    if (!box) {
      box = el('div', 'arep-healing-toast');
      box.id = 'arep-healing-toast';
      document.body.appendChild(box);
    }
    box.textContent = message;
    box.hidden = false;
    setTimeout(function () { box.hidden = true; }, 4000);
  }

  function startHealing(tests, button, noteHost) {
    var domain = currentDomain();
    if (!domain) { return; }
    button.disabled = true;
    var original = button.textContent;
    button.textContent = '下書き中…';
    fetchHealingProjects().then(function (projects) {
      var project = projects.filter(function (p) { return p.domain === domain; })[0];
      if (!project) {
        button.disabled = false;
        button.textContent = original;
        var note = el('span', 'arep-healing-note',
          'このサイトのリポジトリが未接続です。「ヒーリング › 設定」で接続してください。');
        (noteHost || button.parentNode).appendChild(note);
        return;
      }
      var ids = tests.map(function (t) {
        var title = String(t.title || t.name || '');
        var m = title.match(/^TC-[A-Z0-9-]+/);
        return m ? m[0] : title;
      });
      return fetch('/api/healing/runs/from-autorun', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: project.project_id, domain: domain, test_ids: ids })
      }).then(function (r) {
        return r.json().then(function (d) {
          if (!r.ok) { throw new Error(d.error || '起動できませんでした'); }
          return d;
        });
      }).then(function (d) {
        button.textContent = '下書き中…';
        healingToast('報告書を下書きしています。数分後に「ヒーリング › 報告書」に出ます（' + d.defects + ' 件）');
      });
    }).catch(function (e) {
      button.disabled = false;
      button.textContent = original;
      healingToast('起動できませんでした: ' + e.message);
    });
  }

  function buildHealingButton(tests) {
    var btn = el('button', 'arep-healing-btn', 'この失敗の報告書を作る');
    btn.type = 'button';
    btn.addEventListener('click', function () { startHealing(tests, btn); });
    return btn;
  }

  function buildHealingHeader(failedTests) {
    var bar = el('div', 'arep-healing-bar');
    bar.appendChild(el('span', 'arep-healing-count', '失敗 ' + failedTests.length + ' 件'));
    var btn = el('button', 'arep-healing-btn is-primary',
      '失敗 ' + failedTests.length + ' 件の報告書を作る');
    btn.type = 'button';
    btn.addEventListener('click', function () { startHealing(failedTests, btn, bar); });
    bar.appendChild(btn);
    return bar;
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
      var failedTests = tests.filter(function (t) {
        var st = String(t.status || t.outcome || '');
        return st && st !== 'passed' && st !== 'skipped';
      });
      if (failedTests.length) {
        nodes.push(buildHealingHeader(failedTests));
      }
      var list = el('div', 'arep-results');
      tests.slice(0, 300).forEach(function (t) {
        var row = el('div', 'arep-result-row');
        var status = String(t.status || t.outcome || '');
        var isFail = status && status !== 'passed' && status !== 'skipped';
        var badge = el('span', 'arep-result-badge is-' + (status === 'passed' ? 'pass' : status === 'failed' ? 'fail' : 'other'), status || '—');
        row.appendChild(badge);
        row.appendChild(el('span', 'arep-result-title', String(t.title || t.name || '')));
        if (t.error || t.message) {
          row.appendChild(el('span', 'arep-result-error', String(t.error || t.message)));
        }
        if (isFail) {
          row.appendChild(buildHealingButton([t]));
        }
        list.appendChild(row);
      });
      nodes.push(list);
    } else {
      nodes.push(el('p', 'arep-empty-note', 'テスト実行の明細がありません（未実行、または結果が空です）。'));
    }
    return nodes;
  }


  // ---------------------------------------------------------------- 判定と証跡（常時表示部）

  function namedList(named) {
    var ul = el('ul', 'arep-vnamed');
    Object.keys(named || {}).forEach(function (label) {
      var items = named[label] || [];
      if (!items.length) return;
      var shown = items.slice(0, 5).join('、') + (items.length > 5 ? ' ほか' + (items.length - 5) + '件' : '');
      ul.appendChild(el('li', null, label + '（' + items.length + '件）: ' + shown));
    });
    return ul;
  }

  function renderChrome(v) {
    var bar = $('arep-stagebar');
    bar.textContent = '';
    (v.stages || []).forEach(function (s) {
      var li = el('li', 'arep-stage');
      li.setAttribute('data-status', s.status);
      li.title = s.step_no + '. ' + s.name + '\n出口条件: ' + s.exit_criteria + '\n' + s.owner
        + (s.approver ? '\n判断: ' + s.approver + ' ' + s.approved_at : '');
      li.appendChild(el('span', 'arep-stage-name', s.step_no + '. ' + s.name));
      li.appendChild(el('span', 'arep-stage-status', s.status_label));
      bar.appendChild(li);
    });
    var run = el('li', 'arep-stage');
    var kind = (v.outcome || {}).kind;
    run.setAttribute('data-status', kind === 'complete' ? 'approved' : (kind === 'not_run' ? 'pending' : 'generated'));
    run.appendChild(el('span', 'arep-stage-name', '9. 実行'));
    run.appendChild(el('span', 'arep-stage-status', (v.outcome || {}).title || ''));
    bar.appendChild(run);

    var oc = $('arep-outcome');
    oc.textContent = '';
    oc.appendChild(el('strong', null, (v.outcome || {}).title || ''));
    oc.appendChild(document.createTextNode(((v.outcome || {}).detail || '') + ' ' + ((v.outcome || {}).next_action || '')));
    $('arep-log').textContent = (v.log && v.log.length) ? v.log.join('\n')
      : '実行ログはまだありません。実行が終わるとここに残ります。';

    var band = $('arep-verdictband');
    band.textContent = '';
    (v.verdicts || []).forEach(function (r) {
      var row = el('div', 'arep-vrow');
      row.appendChild(el('span', 'arep-vscope', r.scope));
      var badge = el('span', 'arep-vbadge', r.verdict);
      badge.setAttribute('data-verdict', r.verdict);
      row.appendChild(badge);
      row.appendChild(el('span', null, r.basis));
      row.appendChild(namedList(r.named));
      band.appendChild(row);
    });
  }

  function renderVerdict(v) {
    var nodes = [];
    var head = el('section', 'arep-card');
    head.appendChild(el('h2', null, (v.outcome || {}).title || ''));
    head.appendChild(el('p', null, (v.outcome || {}).detail || ''));
    head.appendChild(el('p', null, '次の行動: ' + ((v.outcome || {}).next_action || '')));
    head.appendChild(el('p', 'arep-claim', v.claim_scope || ''));
    nodes.push(head);

    var sec = el('section', 'arep-card');
    sec.appendChild(el('h2', null, '段階承認の記録'));
    var wrap = el('div', 'arep-trail-wrap');
    var table = el('table', 'arep-trail');
    var thead = el('tr');
    ['段階', '出口条件', '状態', '判断（誰が・いつ・理由）'].forEach(function (h) { thead.appendChild(el('th', null, h)); });
    table.appendChild(thead);
    (v.stages || []).forEach(function (s) {
      var tr = el('tr');
      tr.appendChild(el('td', null, s.step_no + '. ' + s.name));
      tr.appendChild(el('td', null, s.exit_criteria));
      tr.appendChild(el('td', null, s.status_label));
      var who = el('td', s.approver === '本人確認なし' ? 'arep-noauth' : null,
        s.approver ? (s.approver + '／' + s.approved_at + '／' + (s.reason || '理由の記載なし'))
          + (s.authenticated ? '' : '（承認として数えません）') : '判断の記録なし');
      tr.appendChild(who);
      table.appendChild(tr);
    });
    wrap.appendChild(table);
    sec.appendChild(wrap);
    nodes.push(sec);
    return nodes;
  }

  function loadChrome() {
    return fetch('/api/autorun/report/' + encodeURIComponent(domain) + '?section=verdict')
      .then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error); return d; }); })
      .then(function (d) { renderChrome(d.data || {}); })
      .catch(function () {
        $('arep-log').textContent = '実行ログを読み込めませんでした。ページを再読み込みしてください。';
      });
  }

  function previewState(state) {
    document.querySelectorAll('.arep-state-btn').forEach(function (b) {
      b.classList.toggle('is-active', b.getAttribute('data-state-switch') === state);
    });
    if (state === 'normal') { load(current || 'verdict'); return; }
    var box = $('arep-content');
    box.setAttribute('data-state', state);
    if (state === 'loading') setContent([el('p', 'arep-loading', '読み込んでいます…')]);
    if (state === 'empty') setContent([el('div', 'arep-empty', 'この対象にはまだ実行結果がありません。AutoRun の画面から実行を開始してください。')]);
    if (state === 'error') setContent([el('div', 'arep-error', '結果を読み込めませんでした。時間をおいて再読み込みし、続く場合は管理者に連絡してください。')]);
    box.setAttribute('data-state', state);
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

      if (data.kind === 'verdict') { setContent(renderVerdict(data.data || {})); renderChrome(data.data || {}); }
      else if (data.kind === 'dashboard') setContent(renderDashboard(data.data || {}));
      else if (data.kind === 'markdown') setContent(renderMarkdown(data.text, data.source));
      else if (data.kind === 'code') setContent(renderCode(data.text, data.source));
      else if (data.kind === 'table') setContent(renderTable(data));
      else if (data.kind === 'results') setContent(renderResults(data.data, data.source));
      else setContent(notGenerated());

      $('arep-content').setAttribute('data-state', 'normal');
      try {
        history.replaceState(null, '', '#' + section);
      } catch (e) { /* 履歴が使えない環境では無視 */ }
    } catch (e) {
      $('arep-content').setAttribute('data-state', 'error');
      setContent([el('div', 'arep-error', (e && e.message ? e.message : '読み込みに失敗しました') + ' 再読み込みしてください。')]);
    }
  }

  function boot() {
    document.querySelectorAll('.arep-nav-item').forEach(function (btn) {
      btn.addEventListener('click', function () {
        load(btn.getAttribute('data-section'));
      });
    });

    document.querySelectorAll('.arep-state-btn').forEach(function (btn) {
      btn.addEventListener('click', function () { previewState(btn.getAttribute('data-state-switch')); });
    });
    var initial = (location.hash || '').replace('#', '') || 'verdict';
    if (initial !== 'verdict') loadChrome();
    var known = Array.prototype.map.call(
      document.querySelectorAll('.arep-nav-item'),
      function (b) { return b.getAttribute('data-section'); }
    );
    load(known.indexOf(initial) >= 0 ? initial : 'verdict');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
