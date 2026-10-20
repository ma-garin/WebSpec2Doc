/* ws-rea-viewpoints.js — テスト候補の由来と実行（System 02「実行と結果」）
 * T.reaViewpointsRender(host, domain): GET /api/sites/<domain>/rea-test-viewpoints を C. Hybrid 部品（window.WS2D）で描く。
 * 区別する 8 語: 元候補 / 解析で追加 / 静的 / 未認証実測 / 認証済み実測 / 未確認 / 実行対象 / 実行済み。
 * 実行対象（System 03 が到達を実測した route）≠ 実行済み（実行記録が観点に結び付いたものだけ。取れなければ「未計測」）。
 * 状態は文字＋形で示す（色だけにしない）。テキストは WS2D.esc / textContent 経由。
 */
(function () {
  'use strict';
  var T = window.TA2;
  if (!T) return;
  var seq = 0;
  var CAT_LABEL = { fact: '事実', inference: '推論', unverified: '未確認' };
  // 根拠の区分（表示順 = 事実 → 推論 → 未確認）。ev は WS2D.evidence の code
  var EV = [
    { key: 'base', label: '元候補（既存の候補・実測とは限らない）', ev: 'unverified', cat: 'unverified' },
    { key: 'observed', label: '未認証実測', ev: 'observed', cat: 'fact' },
    { key: 'observed_auth', label: '認証済み実測', ev: 'observed_auth', cat: 'fact' },
    { key: 'static', label: '静的', ev: 'static', cat: 'inference' },
    { key: 'inferred', label: '推論', ev: 'inferred', cat: 'inference' },
    { key: 'ambiguous', label: '曖昧', ev: 'ambiguous', cat: 'inference' },
    { key: 'unverified', label: '未確認', ev: 'unverified', cat: 'unverified' },
    { key: 'unavailable', label: '利用不可', ev: 'unavailable', cat: 'unverified' }
  ];
  var EV_BY = {};
  EV.forEach(function (e) { EV_BY[e.key] = e; });

  /** 観点 1 件の根拠区分（純関数・tests/js で検証）。由来（元候補 / 解析で追加）と根拠の強さを分けて返す */
  function evKey(v) {
    if (!v.is_new) return 'base';
    var o = v.origin;
    if (o === 'observed' || o === 'observed_auth' || o === 'static') return o;
    if (o === 'rea_added') return v.ev_code === 'ambiguous' ? 'ambiguous' : 'inferred';
    return v.ev_code === 'unavailable' ? 'unavailable' : 'unverified';
  }
  function isTarget(v) { return !!(v.execution && v.execution.target); }
  function isExecuted(v) { return !!(v.execution && v.execution.count > 0); }

  var FILTERS = {
    all: { label: 'すべて', test: function () { return true; } },
    base: { label: '元候補', test: function (v) { return !v.is_new; } },
    'new': { label: '解析で追加', test: function (v) { return !!v.is_new; } },
    target: { label: '実行対象', test: isTarget },
    executed: { label: '実行済み', test: isExecuted }
  };
  EV.forEach(function (e) {
    FILTERS['ev:' + e.key] = { label: '根拠「' + e.label + '」', test: function (v) { return evKey(v) === e.key; } };
  });

  function W() { return window.WS2D; }
  function esc(s) { return W() ? W().esc(s) : String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }

  function fallbackNotice(host, d) {
    var msg = (d.message || 'リバース解析の根拠がありません。') + '（元候補 ' + ((d.metrics || {}).before || 0) + ' 件のみ。解析で追加 0 件・実行対象 0 件は「無い」ではなく未確認です）';
    var next = d.next_action || 'System01 でリバース解析を実行すると観点が増えます';
    if (W()) { W().state(host, { kind: 'unverified', title: 'テスト候補の由来: リバース解析の根拠なし', message: msg, next: next }); return; }
    host.textContent = msg + ' 次の操作: ' + next;
  }

  function targetText(v) {
    if (isTarget(v)) return '実行対象';
    if (v.kind === 'route') return '対象外（到達を実測していない）';
    return '対象外';
  }
  function executedHTML(v) {
    var ex = v.execution || {};
    if (ex.measured === false) return W().status.html('unverified', '未計測');
    if (!(ex.count > 0)) return W().status.html('not_started', '未実行');
    return W().status.html(ex.last_result === 'pass' ? 'done' : (ex.last_result === 'fail' ? 'failed' : 'partial'), ex.label);
  }

  function openDrawer(v, ret) {
    var ex = v.execution || {};
    var k = EV_BY[evKey(v)];
    var facts = [{ label: '由来', value: v.is_new ? '解析で追加（リバース解析で増えた観点）' : '元候補（既存のテスト候補）' }];
    if (v.kind === 'route') {
      facts.push({ label: '到達の実測（System 03）', value: (v.reach_label || '未探索') });
      if (v.reach_observed_at) facts.push({ label: '実測日時', value: v.reach_observed_at });
    }
    if (v.source === 'runtime') facts.push({ label: '実測', value: '実行時に観測された API' });
    facts.push({ label: '実行対象', value: targetText(v) });
    facts.push({ label: '実行済み', value: ex.measured === false ? '未計測（実行記録を取得できません）' : (ex.label || '未実行') });
    var inf = [];
    if (k.cat !== 'fact') {
      inf.push('根拠: ' + k.label + '（' + (v.evidence_state_label || v.source_label || '不明') + '）');
      if (!v.runnable) inf.push('到達・動作は実測で確認していません。');
    }
    var sources = [{ label: '位置', value: v.location || '未確認' }, { label: '出所', value: 'リバース解析（System 01）' }];
    if (v.evidence_id) sources.push({ label: '根拠 ID', value: String(v.evidence_id) });
    W().drawer.open({
      title: v.text, state: k.ev, stateReason: k.label,
      claim: v.claim || '（根拠の説明なし）', facts: facts, inferences: inf,
      limitations: (v.limitations && v.limitations.length) ? v.limitations : ['限界の記載なし（未確認）'],
      sources: sources, returnFocus: ret
    });
  }

  function rowEl(v) {
    var tr = document.createElement('tr');
    tr.setAttribute('tabindex', '0');
    var k = EV_BY[evKey(v)];
    tr.setAttribute('aria-label', v.text + '。由来 ' + (v.is_new ? '解析で追加' : '元候補') + '、根拠 ' + k.label + '、' + targetText(v) + '。根拠を開く');
    tr.innerHTML = '<td data-label="観点"><span class="rt-text">' + esc(v.text) + '</span></td>'
      + '<td data-label="由来"><span class="rt-origin">' + (v.is_new ? '解析で追加' : '元候補') + '</span></td>'
      + '<td data-label="根拠">' + W().evidence.html(k.ev, k.label) + '</td>'
      + '<td data-label="実行対象"><span class="' + (isTarget(v) ? 'rt-run-target' : 'rt-run-none') + '">' + esc(targetText(v)) + '</span></td>'
      + '<td data-label="実行済み">' + executedHTML(v) + '</td>';
    function open() { openDrawer(v, tr); }
    tr.addEventListener('click', open);
    tr.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
    return tr;
  }

  function flowStep(no, key, label, value, sub, cls) {
    return '<li class="rt-step' + (cls ? ' ' + cls : '') + '"><button type="button" class="rt-step__btn" data-f="' + key + '"'
      + ' aria-label="' + esc(label + ' ' + (value == null ? '未計測' : value + ' 件') + '。一覧を絞り込む') + '">'
      + '<span class="rt-step__no" aria-hidden="true">' + no + '</span>'
      + '<span class="rt-step__label">' + esc(label) + '</span>'
      + '<span class="rt-step__value">' + esc(value == null ? '未計測' : String(value)) + '</span>'
      + '<span class="rt-step__sub">' + esc(sub) + '</span></button></li>';
  }

  function draw(host, d) {
    if (!W()) { fallbackNotice(host, d); return; }
    if (d.state !== 'ok') { fallbackNotice(host, d); return; }
    var m = d.metrics || {};
    var rows = d.viewpoints || [];
    var cov = (d.covered_by_runtime || []).length;
    var filter = 'all';
    var cnt = {};
    EV.forEach(function (e) { cnt[e.key] = 0; });
    rows.forEach(function (v) { cnt[evKey(v)]++; });

    host.innerHTML = '<div class="rt-wrap">'
      + '<div class="rv-head-main"><h3 class="rv-title">テスト候補の由来と実行</h3>'
      + '<p class="rv-lead">元候補にリバース解析の観点を足した一覧です。<b>実行対象</b>は System 03 が到達を実測した route、<b>実行済み</b>は実行記録が観点に結び付いたものだけで、別の数です（探索済み ' + esc(m.probed || 0) + ' 件）。</p></div>'
      + '<ol class="rt-flow" aria-label="テスト候補の流れ（数を押すと一覧を絞り込みます）">'
      + flowStep(1, 'base', '元候補', m.before, m.before_basis || '既存のテスト候補')
      + flowStep(2, 'new', '解析で追加', m['new'], '根拠 ID 付き ' + (m.with_evidence == null ? '未計測' : m.with_evidence) + ' 件', 'is-inference')
      + flowStep(3, 'all', '合計', m.after, '元 ' + m.before + ' ＋ 追加 ' + m['new'])
      + flowStep(4, 'target', '実行対象', m.runnable, '到達を実測した route', 'is-fact')
      + flowStep(5, 'executed', '実行済み', m.executed, m.executed == null ? '実行記録を取得できません' : '実行記録が結び付いた観点', 'is-fact')
      + '</ol>'
      + '<div class="rt-ev c-split" role="group" aria-label="根拠の内訳（事実・推論・未確認）">'
      + ['fact', 'inference', 'unverified'].map(function (c) {
        var items = EV.filter(function (e) { return e.cat === c && (cnt[e.key] || e.key !== 'unavailable') && !(e.key === 'base' && !cnt.base); });
        var total = items.reduce(function (a, e) { return a + cnt[e.key]; }, 0);
        return '<div class="c-split__cell c-split__cell--' + c + '"><span class="c-split__label">' + CAT_LABEL[c] + ' <b>' + total + '</b></span>'
          + '<span class="rt-ev__chips">' + items.map(function (e) {
            return '<button type="button" class="rt-chip" data-f="ev:' + e.key + '" aria-label="' + esc(e.label + ' ' + cnt[e.key] + ' 件。一覧を絞り込む') + '">'
              + W().evidence.html(e.ev, e.label) + '<span class="rt-chip__n">' + cnt[e.key] + '</span></button>';
          }).join('') + '</span></div>';
      }).join('') + '</div>'
      + '<div class="rt-filterbar" role="status" aria-live="polite"></div>'
      + (cov ? '<p class="rt-cov">実測で確認済みの API と同じ path の静的 API ' + cov + ' 件は、静的出典として扱い新規観点に数えていません。</p>' : '')
      + '<details class="rt-details"><summary>観点の一覧（<span class="rt-count">' + rows.length + '</span> 件）</summary><div class="rt-tablehost"></div></details></div>';
    var fBar = host.querySelector('.rt-filterbar'), tHost = host.querySelector('.rt-tablehost');
    var det = host.querySelector('.rt-details');

    function pick(key, from) {
      filter = key; update(); det.open = true;
      if (from && key !== 'all' && det.scrollIntoView) det.scrollIntoView({ block: 'nearest' });
    }
    Array.prototype.forEach.call(host.querySelectorAll('[data-f]'), function (b) {
      b.addEventListener('click', function () { pick(b.getAttribute('data-f'), b); });
    });

    function update() {
      var f = FILTERS[filter] || FILTERS.all;
      var list = rows.filter(f.test);
      Array.prototype.forEach.call(host.querySelectorAll('[data-f]'), function (b) {
        b.setAttribute('aria-pressed', b.getAttribute('data-f') === filter ? 'true' : 'false');
      });
      host.querySelector('.rt-count').textContent = filter === 'all' ? String(rows.length) : list.length + ' / ' + rows.length;
      fBar.innerHTML = '';
      if (filter !== 'all') {
        var b = document.createElement('button');
        b.type = 'button'; b.className = 'c-btn c-btn--ghost'; b.textContent = '絞り込みを解除';
        b.addEventListener('click', function () { pick('all'); });
        fBar.appendChild(document.createTextNode('絞り込み: ' + f.label + '（' + list.length + ' 件） '));
        fBar.appendChild(b);
      }
      tHost.innerHTML = '';
      if (!list.length) {
        W().state(tHost, { kind: 'empty', message: filter === 'executed' ? '観点に結び付いた実行記録はありません（未実行）。実行対象であっても、実行するまで実行済みには数えません。' : '該当する観点はありません。' });
        return;
      }
      var wrap = document.createElement('div'); wrap.className = 'c-table-wrap';
      var tb = document.createElement('table'); tb.className = 'c-table rt-table';
      tb.innerHTML = '<thead><tr><th scope="col">観点（' + list.length + ' 件）</th><th scope="col">由来</th><th scope="col">根拠</th><th scope="col">実行対象</th><th scope="col">実行済み</th></tr></thead>';
      var body = document.createElement('tbody');
      list.forEach(function (v) { body.appendChild(rowEl(v)); });
      tb.appendChild(body); wrap.appendChild(tb); tHost.appendChild(wrap);
    }
    update();
  }

  function render(host, domain) {
    if (!host) return;
    var my = ++seq;
    host.setAttribute('aria-busy', 'true');
    if (W()) W().state(host, { kind: 'loading', message: '観点を読み込んでいます…' });
    else host.textContent = '観点を読み込んでいます…';
    fetch('/api/sites/' + encodeURIComponent(domain || '') + '/rea-test-viewpoints', { headers: { 'Accept': 'application/json' } })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (j) { if (my !== seq) return; host.removeAttribute('aria-busy'); draw(host, j || {}); })
      .catch(function () {
        if (my !== seq) return;
        host.removeAttribute('aria-busy');
        if (W()) W().state(host, { kind: 'error', message: '観点を取得できませんでした。', next: '通信状態を確認して、再読み込みしてください。', retained: false });
        else host.textContent = '観点を取得できませんでした。通信状態を確認して、再読み込みしてください。';
      });
  }

  T.reaViewpointsRender = render;
  // テスト自動化（System 02）の「実行と結果」を開いたときに描く
  if (T.on) {
    T.on('view', function (v) {
      if (v !== 'run') return;
      var host = document.getElementById('run-reaview');
      if (host && T.state && T.state.domain) render(host, T.state.domain);
    });
  }
})();
