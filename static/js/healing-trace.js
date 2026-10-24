'use strict';

/* オートヒーリング 実行ビュー: 工程バーと「欠陥ごとの 根拠 → 修正差分 → 再検証 → 判断」。
   中身はサーバ（/api/healing/runs/<id>/trace）が決める。この画面は描くだけで、
   「修正済み」を自分で判定しない。判断（採用／不採用／要確認）は人の記録だけを出す。
   状態は #hl-trace の data-state（normal / empty / loading / error）で切り替える。
   検証用に URL の ?hl_state=<状態> で表示状態を固定できる。 */
(function () {
  var lastKey = '';
  var selected = '';
  var data = null;
  var lastRunId = '';

  function q(id) { return document.getElementById(id); }
  function node(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text !== undefined && text !== null) { e.textContent = String(text); }
    return e;
  }
  function forcedState() {
    var m = /[?&]hl_state=([a-z-]+)/.exec(window.location.search);
    return m ? m[1] : '';
  }
  function setState(s, msg) {
    var root = q('hl-trace');
    if (!root) { return; }
    var f = forcedState();
    root.setAttribute('data-state', f || s);
    if (msg) { q('hl-trace-error-text').textContent = msg; }
  }

  function renderSteps(steps) {
    var ol = q('hl-steps');
    ol.textContent = '';
    steps.forEach(function (s, i) {
      var li = node('li', 'hl-step is-' + s.state);
      li.setAttribute('data-step', s.key);
      if (s.state === 'current') { li.setAttribute('aria-current', 'step'); }
      li.appendChild(node('span', 'hl-step__no', i + 1));
      var t = node('span', 'hl-step__text');
      t.appendChild(node('b', 'hl-step__label', s.label));
      t.appendChild(node('span', 'hl-step__detail', s.detail));
      li.appendChild(t);
      ol.appendChild(li);
    });
  }

  var REV_KIND = { passed: 'ok', failing: 'ng', unverified: 'warn' };
  var DEC_KIND = { '採用': 'ok', '不採用': 'ng', '要確認': 'warn' };

  function renderList(defects) {
    var ul = q('hl-trace-list');
    ul.textContent = '';
    defects.forEach(function (d) {
      var li = node('li', 'hl-trace-item' + (d.defect_id === selected ? ' is-selected' : ''));
      var b = node('button', 'hl-trace-item__btn');
      b.type = 'button';
      b.setAttribute('aria-pressed', d.defect_id === selected ? 'true' : 'false');
      b.appendChild(node('span', 'hl-sev hl-sev--' + d.severity, d.severity));
      b.appendChild(node('span', 'hl-trace-item__title', d.title));
      var tags = node('span', 'hl-trace-item__tags');
      tags.appendChild(node('span', 'hl-chip hl-chip--' + REV_KIND[d.reverify.result], d.reverify.label));
      tags.appendChild(node('span', 'hl-chip hl-chip--' + DEC_KIND[d.decision.value], d.decision.value));
      b.appendChild(tags);
      b.addEventListener('click', function () { selected = d.defect_id; renderList(defects); renderDetail(d); });
      li.appendChild(b);
      ul.appendChild(li);
    });
  }

  function block(title, kind) {
    var s = node('section', 'hl-tb' + (kind ? ' hl-tb--' + kind : ''));
    s.appendChild(node('h3', 'hl-tb__title', title));
    return s;
  }
  function pre(text, cls) { var p = node('pre', cls || 'hl-tb__pre', text); p.tabIndex = 0; return p; }

  function renderDiff(diff) {
    var p = node('pre', 'hl-tb__pre hl-tb__diff');
    p.tabIndex = 0;
    diff.split('\n').forEach(function (line) {
      var c = line.charAt(0);
      var cls = (c === '+' && line.indexOf('+++') !== 0) ? 'is-add' : (c === '-' && line.indexOf('---') !== 0) ? 'is-del' : '';
      p.appendChild(node('span', cls, line + '\n'));
    });
    return p;
  }

  function renderDetail(d) {
    var box = q('hl-trace-detail');
    box.textContent = '';
    if (!d) { box.appendChild(node('p', 'hl-tb__muted', '左の一覧から欠陥を選ぶと、根拠・修正差分・再検証・判断を表示します。')); return; }
    box.appendChild(node('h3', 'hl-trace-detail__title', d.title + '（周回 ' + d.iteration + '）'));
    var ev = block('1. 根拠（失敗したケースとログ）');
    ev.appendChild(node('p', 'hl-tb__kv', 'ケース: ' + (d.evidence.test_id || '特定できませんでした')));
    if (d.evidence.message) { ev.appendChild(node('p', 'hl-tb__kv', '内容: ' + d.evidence.message)); }
    ev.appendChild(d.evidence.log ? pre(d.evidence.log) : node('p', 'hl-tb__muted', 'ログは記録されていません。'));
    box.appendChild(ev);
    var fx = block('2. 修正差分', d.fix.has_diff ? '' : 'warn');
    fx.appendChild(node('p', 'hl-tb__kv', d.fix.summary || ''));
    if (d.fix.files && d.fix.files.length) { fx.appendChild(node('p', 'hl-tb__kv', '変更したファイル: ' + d.fix.files.join('、'))); }
    if (d.fix.error) { fx.appendChild(node('p', 'hl-tb__kv hl-tb__err', '失敗の理由: ' + d.fix.error)); }
    fx.appendChild(d.fix.has_diff ? renderDiff(d.fix.diff) : node('p', 'hl-tb__muted', 'コードの変更はありません。この欠陥を直した根拠にはなりません。'));
    box.appendChild(fx);
    var rv = block('3. 再検証の結果', REV_KIND[d.reverify.result]);
    rv.appendChild(node('p', 'hl-tb__verdict', d.reverify.label));
    rv.appendChild(node('p', 'hl-tb__kv', d.reverify.detail));
    box.appendChild(rv);
    var dc = block('4. 判断', DEC_KIND[d.decision.value]);
    dc.appendChild(node('p', 'hl-tb__verdict', d.decision.value));
    dc.appendChild(node('p', 'hl-tb__kv', d.decision.by_human
      ? '判断した人: ' + d.decision.actor + '　日時: ' + d.decision.at + (d.decision.note ? '　理由: ' + d.decision.note : '')
      : '人の判断がまだありません。再検証の結果を見て、上の「承認」か「却下」で決めてください。'));
    box.appendChild(dc);
  }

  function renderGate(g) {
    [['overall', 'hl-gate-overall'], ['change', 'hl-gate-change']].forEach(function (pair) {
      var row = q(pair[1]);
      var v = g[pair[0]];
      row.querySelector('.hl-gate__verdict').textContent = v.verdict;
      row.setAttribute('data-verdict', v.verdict);
      var ul = row.querySelector('.hl-gate__items');
      ul.textContent = '';
      (v.items.length ? v.items : ['名指しする項目はありません']).forEach(function (t) { ul.appendChild(node('li', '', t)); });
    });
  }

  function renderAudit(audit) {
    var ul = q('hl-trace-audit');
    ul.textContent = '';
    if (!audit.length) { ul.appendChild(node('li', 'hl-tb__muted', '判断の記録はまだありません。')); return; }
    audit.forEach(function (a) {
      ul.appendChild(node('li', '', a.at + '　' + a.actor + '　' + a.action + (a.note ? '（' + a.note + '）' : '')));
    });
  }

  function draw(t) {
    data = t;
    renderSteps(t.steps);
    renderGate(t.gate);
    renderAudit(t.audit);
    if (!t.defects.length) { setState('empty'); renderDetail(null); return; }
    if (!t.defects.some(function (d) { return d.defect_id === selected; })) { selected = t.defects[0].defect_id; }
    renderList(t.defects);
    renderDetail(t.defects.filter(function (d) { return d.defect_id === selected; })[0]);
    setState('normal');
  }

  function load(runId) {
    if (!data) { setState('loading'); }
    fetch('/api/healing/runs/' + encodeURIComponent(runId) + '/trace', { headers: { Accept: 'application/json' } })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (body) {
          if (!res.ok) { throw new Error(body.error || '取得に失敗しました（' + res.status + '）'); }
          return body.trace;
        });
      })
      .then(draw)
      .catch(function (e) {
        lastKey = '';
        setState('error', '工程と証跡を読み込めませんでした: ' + e.message + '　「再読み込み」を押してください。');
      });
  }

  function render(run) {
    if (!run || !run.run_id || !q('hl-trace')) { return; }
    var its = run.iterations || [];
    var key = [run.run_id, run.status, its.length, (run.decisions || []).length,
      its.length ? (its[its.length - 1].verify_after ? 1 : 0) : 0].join('|');
    if (key === lastKey) { return; }
    if (lastKey.split('|')[0] !== run.run_id) { data = null; selected = ''; }
    lastKey = key;
    lastRunId = run.run_id;
    load(run.run_id);
  }

  document.addEventListener('click', function (e) {
    if (e.target && e.target.id === 'hl-trace-retry' && lastRunId) { load(lastRunId); }
  });
  window.HealingTrace = { render: render };
})();
