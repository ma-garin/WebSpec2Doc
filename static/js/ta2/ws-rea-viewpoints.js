/* ws-rea-viewpoints.js — リバース解析で増えたテスト観点（System 02「実行と結果」）
 * T.reaViewpointsRender(host, domain): GET /api/sites/<domain>/rea-test-viewpoints を C. Hybrid 部品（window.WS2D）で描く。
 * 実行対象（実測で到達）≠ 実行済み。実行済みは実行記録が観点に結び付く場合だけ数え、取れなければ「未計測」。
 * 状態は文字＋形で示す（色だけにしない）。テキストは WS2D.esc / textContent 経由。
 */
(function () {
  'use strict';
  var T = window.TA2;
  if (!T) return;
  var seq = 0;
  var FILTERS = {
    all: { label: 'すべて', test: function () { return true; } },
    'new': { label: 'REA 追加', test: function (v) { return !!v.is_new; } },
    evidence: { label: 'Evidence 付き', test: function (v) { return !!v.is_new && !!v.evidence_id; } },
    target: { label: '実行対象', test: function (v) { return !!(v.execution && v.execution.target); } },
    executed: { label: '実行済み', test: function (v) { return !!(v.execution && v.execution.count > 0); } }
  };
  var CAT_LABEL = { fact: '事実', inference: '推論', unverified: '未確認' };

  function W() { return window.WS2D; }
  function esc(s) { return W() ? W().esc(s) : String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }

  function fallbackNotice(host, d) {
    host.innerHTML = '<div class="rt-wrap"><p><b>リバース解析で増えたテスト観点: 0 件（未確認）</b></p><p>' + esc(d.message || 'リバース解析の根拠がありません。')
      + '</p><p>次の操作: ' + esc(d.next_action || 'System01 でリバース解析を実行すると観点が増えます') + '</p></div>';
  }

  function openDrawer(v, ret) {
    var ex = v.execution || {};
    var facts = [];
    if (v.kind === 'route') {
      facts.push({ label: '到達の実測', value: (v.reach_label || '未探索') + (v.runnable ? (v.reach_authenticated ? '（認証済み）' : '（未認証）') : '') });
      if (v.reach_observed_at) facts.push({ label: '実測日時', value: v.reach_observed_at });
    }
    if (v.source === 'runtime') facts.push({ label: '実測', value: '実行時に観測された API' });
    facts.push({ label: '実行', value: ex.measured === false ? '未計測' : (ex.target ? '実行対象' : '実行対象外') + ' / ' + (ex.label || '未実行') });
    var inf = [];
    if (v.source === 'static' || v.evidence_state === 'static' || v.evidence_state === 'inferred' || v.evidence_state === 'ambiguous') {
      inf.push('根拠: ' + (v.evidence_state_label || '不明') + '（' + (v.source_label || '') + '）');
      if (!v.runnable) inf.push('到達・動作は実測で確認していません。');
    }
    var sources = [{ label: '位置', value: v.location || '未確認' }, { label: 'provider', value: 'リバース解析（System 01）' }];
    if (v.evidence_id) sources.push({ label: '根拠 ID', value: String(v.evidence_id) });
    W().drawer.open({
      title: v.text, state: v.ev_code, stateReason: v.origin_label,
      claim: v.claim || '（根拠の説明なし）', facts: facts, inferences: inf,
      limitations: (v.limitations && v.limitations.length) ? v.limitations : ['限界の記載なし（未確認）'],
      sources: sources, returnFocus: ret
    });
  }

  function rowEl(v) {
    var tr = document.createElement('tr');
    tr.setAttribute('tabindex', '0');
    var ex = v.execution || {};
    var run = ex.measured === false ? '<span class="rt-run-na">未計測</span>'
      : (ex.target ? '<span class="rt-run-target">実行対象</span> ' : '') + '<span class="' + (ex.count > 0 ? 'rt-run-done' : 'rt-run-none') + '">' + esc(ex.label || '未実行') + '</span>';
    tr.innerHTML = '<td data-label="観点"><span class="rt-text">' + esc(v.text) + '</span></td>'
      + '<td data-label="由来と根拠">' + W().evidence.html(v.ev_code, v.origin_label) + '</td>'
      + '<td data-label="実行">' + run + '</td>';
    function open() { openDrawer(v, tr); }
    tr.addEventListener('click', open);
    tr.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
    return tr;
  }

  function draw(host, d) {
    if (!W()) { fallbackNotice(host, d); return; }
    if (d.state !== 'ok') { fallbackNotice(host, d); return; }
    var m = d.metrics || {};
    var rows = d.viewpoints || [];
    var cov = (d.covered_by_runtime || []).length;
    var filter = 'all';
    host.innerHTML = '<div class="rt-wrap">'
      + '<div class="rv-head-main"><h3 class="rv-title">リバース解析で増えたテスト観点</h3>'
      + '<p class="rv-lead">静的解析の候補です。「実行対象」は System 03 が到達を実測した route で、実行済みとは別です（探索済み ' + esc(m.probed || 0) + ' 件）。Before はリバース解析なし（' + esc(m.before_basis || '') + '）。</p></div>'
      + '<div class="rt-kpis"></div><div class="rt-split"></div>'
      + '<div class="rt-filterbar" role="status" aria-live="polite"></div>'
      + (cov ? '<p class="rt-cov">実測で確認済みの API と同じ path の静的 API ' + cov + ' 件は、静的出典として扱い新規観点に数えていません。</p>' : '')
      + '<div class="rt-tablehost"></div></div>';
    var kHost = host.querySelector('.rt-kpis'), sHost = host.querySelector('.rt-split');
    var fBar = host.querySelector('.rt-filterbar'), tHost = host.querySelector('.rt-tablehost');

    function pick(key) { return function () { filter = key; update(); }; }
    W().kpis(kHost, [
      { label: 'テスト候補（元→合計）', value: m.after, sub: '元 ' + m.before + ' → 合計 ' + m.after, onClick: pick('all') },
      { label: 'REA 追加', value: m['new'], sub: '静的解析で増えた観点', category: 'inference', onClick: pick('new') },
      { label: 'Evidence 付き', value: m.with_evidence, sub: '根拠 ID のある追加観点', category: 'fact', onClick: pick('evidence') },
      { label: '実行対象', value: m.runnable == null ? null : m.runnable, sub: '実測で到達した route', category: 'fact', onClick: pick('target') },
      { label: '実行済み', value: m.executed == null ? null : m.executed, sub: m.executed == null ? '実行記録を取得できません' : '実行記録が結び付く観点', category: 'fact', onClick: pick('executed') }
    ]);

    var cnt = { fact: 0, inference: 0, unverified: 0 };
    rows.forEach(function (v) { cnt[v.ev_category || 'unverified']++; });
    sHost.className = 'rt-split c-split';
    sHost.innerHTML = ['fact', 'inference', 'unverified'].map(function (k) {
      return '<div class="c-split__cell c-split__cell--' + k + '"><span class="c-split__label">' + CAT_LABEL[k] + '</span><span class="c-split__value">' + cnt[k] + '</span></div>';
    }).join('');

    function update() {
      var f = FILTERS[filter];
      var list = rows.filter(f.test);
      fBar.innerHTML = '';
      if (filter !== 'all') {
        var b = document.createElement('button');
        b.type = 'button'; b.className = 'c-btn c-btn--ghost'; b.textContent = '絞り込みを解除';
        b.addEventListener('click', pick('all'));
        fBar.appendChild(document.createTextNode('絞り込み: ' + f.label + '（' + list.length + ' 件） '));
        fBar.appendChild(b);
      }
      tHost.innerHTML = '';
      if (!list.length) {
        W().state(tHost, { kind: 'empty', message: filter === 'executed' ? '観点に結び付いた実行記録はありません（未実行）。' : '該当する観点はありません。' });
        return;
      }
      var wrap = document.createElement('div'); wrap.className = 'c-table-wrap';
      var tb = document.createElement('table'); tb.className = 'c-table';
      tb.innerHTML = '<thead><tr><th scope="col">観点（件数 ' + list.length + '）</th><th scope="col">由来と根拠</th><th scope="col">実行</th></tr></thead>';
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
