/* System 09 影響度分析 — コード依存（リバース解析・静的）。System 01 の module 依存を別の Evidence 層として表示する。
   既存の文書項目の影響分析は変えない。状態は提供元の値をそのまま出し、静的依存を実行時の依存とは言わない。 */
(function () {
  'use strict';
  var IM = window.IM, ui = IM.ui, esc = ui.esc, $ = ui.$;
  var URL_ = '/api/impact/rea-layer';
  var STATE = { inferred: '推論', ambiguous: '曖昧' };
  var NOTICE = '静的依存（実行時の依存ではない）';

  function get(q) {
    var p = Object.keys(q).filter(function (k) { return q[k]; }).map(function (k) { return encodeURIComponent(k) + '=' + encodeURIComponent(q[k]); }).join('&');
    return fetch(URL_ + (p ? '?' + p : ''), { credentials: 'same-origin', headers: { Accept: 'application/json' } }).then(function (r) {
      return r.json().then(function (d) { if (!r.ok) throw new Error((d && d.error) || 'コード依存を読み込めませんでした。もう一度開き直してください。'); return d; });
    });
  }
  function badge(s) {
    var k = STATE[s] ? s : 'unknown';
    return '<span class="im-rea-b s-' + k + '">' + (STATE[s] || '未確認') + '</span>';
  }
  function dl(title, m, reason) {
    return '<div class="im-rea-card"><h4>' + esc(title) + '</h4><dl><dt>依存 edge</dt><dd>' + m.dependency_edges + '</dd><dt>影響候補 module</dt><dd>' + m.candidates +
      '</dd><dt>関連 route</dt><dd>' + m.routes + '</dd>' +
      '<dt>実測で到達した関連 route</dt><dd>' + (m.observed_routes || 0) + '</dd><dt>うち認証済み</dt><dd>' + (m.observed_routes_authenticated || 0) + '</dd><dt>関連 API（静的）</dt><dd>' + m.apis + '</dd><dt>関連テスト</dt><dd>' + m.tests + '</dd></dl>' +
      (reason ? '<p class="im-rea-note">' + esc(String(reason).replace('このサイトに対する', '選んだサイトに対する')) + '</p>' : '') + '</div>';
  }
  function reach(i) {
    if (!i.reach_label) return '';
    // 実際に開いた結果（到達・未到達・認証）だけ「実測」と書く。曖昧・失敗・未探索は開いていない／確かめられていない
    var measured = ['unreached', 'auth_required'].indexOf(i.reach_status) >= 0;  // observed は名前に「実測」を含む
    return ' <span class="im-rea-b im-rea-reach r-' + esc(i.reach_status || 'not_probed') + '">到達: ' + esc(i.reach_label) + (measured ? '（実測）' : '') + '</span>';
  }
  function items(list, label) {
    if (!list || !list.length) return '';
    return '<ul class="im-rea-rel" aria-label="' + esc(label) + '">' + list.map(function (i) {
      return '<li>' + esc(label) + ' <code>' + esc((i.method ? i.method + ' ' : '') + i.value) + '</code> ' + badge(i.state) + reach(i) + ' <small>' + esc(i.location || '') + '（静的）</small></li>';
    }).join('') + '</ul>';
  }
  function tests(list) {
    if (!list || !list.length) return '<small class="im-rea-note">関連テスト: 0 件</small>';
    return '<ul class="im-rea-rel" aria-label="関連テスト">' + list.map(function (t) {
      return '<li>テスト観点 ' + esc(t.text) + ' <small>（' + (t.source === 'runtime' ? '実測由来' : '静的候補由来') + '・System 02）</small></li>';
    }).join('') + '</ul>';
  }
  function flow(d) {
    if (!d.module) return '<div class="im-state" role="status">変更元 module を選ぶと、影響候補と関連 route / API / テストを表示します。</div>';
    var imp = d.impacted || [];
    var own = d.own || {};
    var h = '<p class="im-rea-note"><strong>' + esc(NOTICE) + '</strong>。上流の確かな実行経路は示しません。</p>';
    h += '<ul class="im-rea-flow"><li><strong>変更元</strong> <code>' + esc(d.module) + '</code>' + items(own.routes, 'route') + items(own.apis, 'API') + tests(own.tests) + '</li></ul>';
    if (!imp.length) return h + '<div class="im-state" role="status">この module の影響候補はありません。</div>' + ext(d);
    h += '<h4 class="im-rea-note">影響候補 module</h4><ul class="im-rea-flow">' + imp.map(function (c) {
      var v = c.via || {};
      var dir = c.direction === 'reverse' ? 'を import している' : 'が import している';
      return '<li><code>' + esc(c.module) + '</code> <small>変更元' + dir + '（' + c.depth + ' 段）</small> ' + badge(v.state) +
        '<br><small>' + esc(v.source) + ' → ' + esc(v.target) + '／' + esc(v.relation_label || '依存') + '／位置 ' + esc(v.location || '不明') + '／' + esc(NOTICE) + '</small>' +
        items(c.routes, 'route') + items(c.apis, 'API') + tests(c.tests) + '</li>';
    }).join('') + '</ul>';
    return h + ext(d);
  }
  function ext(d) {
    var e = d.external || [];
    if (!e.length) return '';
    return '<h4 class="im-rea-note">外部パッケージ（影響候補に含めない）</h4><ul class="im-rea-flow">' + e.map(function (x) {
      return '<li><code>' + esc(x.raw_target || x.target) + '</code> <small>' + esc(x.source) + ' から</small> ' + badge(x.state) + '</li>';
    }).join('') + '</ul>';
  }

  /* ---------- 変更 → module → route → test → 承認 の段 ---------- */
  var W = window.WS2D;
  var STAGES = [
    { k: 'change', t: '変更', u: '件' }, { k: 'modules', t: 'code / module', u: '件' },
    { k: 'routes', t: 'route', u: '件' }, { k: 'tests', t: 'test', u: '件' }, { k: 'approval', t: '承認', u: '' }
  ];
  var REACH = { observed_auth: ['observed_auth', '認証済み実測'], observed: ['observed', '未認証実測'], unverified: ['unverified', '未確認'] };
  function ev(code) { var r = REACH[code] || REACH.unverified; return W && W.evidence ? W.evidence.html(r[0], r[1]) : esc(r[1]); }
  function openDrawer(o, btn) { if (W && W.drawer) { o.returnFocus = btn; W.drawer.open(o); } }
  function routeDrawer(r, btn) {
    var c = REACH[r.reach_class] || REACH.unverified;
    openDrawer({
      title: 'route ' + (r.method ? r.method + ' ' : '') + r.value, state: c[0],
      stateReason: r.reach_class === 'unverified' ? '到達は確かめられていません（' + (r.reach_label || '未探索') + '）。' : '実際に開いた結果です。',
      claim: 'この route は、変更元 module から静的な依存でたどれる位置にあります。',
      facts: [{ label: '到達の実測', value: r.reach_class === 'observed_auth' ? '実測で到達（認証済み）' : r.reach_class === 'observed' ? '実測で到達（未認証）' : (r.reach_label || '未探索') },
        { label: '関連 module', value: r.module || '' }],
      inferences: ['module との関係は静的依存からの推論です（状態: ' + (STATE[r.state] || '未確認') + '）。'],
      limitations: [NOTICE, '到達できたことは、機能が正常に動くことを意味しません。', '認証済み実測は保存済みの認証状態で開いた結果です。'],
      sources: [{ label: '位置', value: r.location || '不明' }, { label: 'provider', value: 'System 01 リバース解析（静的）／到達: System 03 到達確認（実測）' }]
    }, btn);
  }
  function testDrawer(t, btn) {
    openDrawer({
      title: 'テスト観点', state: 'static', stateReason: t.source === 'runtime' ? '実測由来の観点です。' : '静的候補由来です。実行・合格を示しません。',
      claim: t.text || '', facts: [], inferences: ['この観点は変更元に関連する根拠から導いた候補です。'],
      limitations: ['生成された観点は実行済みを意味しません。', NOTICE],
      sources: [{ label: '根拠 id', value: t.evidence_id || '' }, { label: 'provider', value: 'System 02 テスト観点（リバース解析由来）' }]
    }, btn);
  }
  function moduleDrawer(m, via, btn) {
    var v = via || {};
    openDrawer({
      title: 'module ' + m, state: v.state === 'ambiguous' ? 'ambiguous' : 'inferred', stateReason: v.state ? '依存の状態: ' + (STATE[v.state] || '未確認') : '変更元です。',
      claim: via ? m + ' は変更元と import 関係でつながっています。' : m + ' が変更元です。',
      facts: [], inferences: via ? [(v.source || '') + ' → ' + (v.target || '') + '／' + (v.relation_label || '依存')] : [],
      limitations: [NOTICE, '影響候補であり、実際に影響するとは限りません。'],
      sources: [{ label: '位置', value: v.location || '不明' }, { label: 'provider', value: 'System 01 リバース解析（静的）' }]
    }, btn);
  }
  function rowBtn(cls, label, extra) { return '<li><button type="button" class="im-rea-row" data-rid="' + cls + '">' + label + '</button>' + (extra || '') + '</li>'; }
  function stagesHtml(f, d, active) {
    var s = f.stages, wait = s.blockers;
    return '<ol class="im-rea-lane" aria-label="変更から承認までの段">' + STAGES.map(function (g, n) {
      var v = g.k === 'approval' ? (wait ? wait + ' 件の阻害' : '阻害なし') : s[g.k] + ' ' + g.u;
      var on = active === g.k;
      return '<li class="im-rea-stage' + (on ? ' on' : '') + (g.k === 'approval' && wait ? ' warn' : '') + '">' +
        '<button type="button" data-stage="' + g.k + '" aria-pressed="' + on + '" aria-label="' + esc(g.t + ' ' + v + 'で一覧を絞り込む') + '">' +
        '<small>' + (n + 1) + '. ' + esc(g.t) + '</small><strong>' + esc(v) + '</strong></button></li>';
    }).join('') + '</ol>';
  }
  function stageList(k, f, d) {
    var own = d.own || {}, imp = d.impacted || [], h = '', list;
    if (k === 'change' || k === 'modules') {
      list = (k === 'modules' ? [{ module: d.module, own: 1 }].concat(imp) : [{ module: d.module, own: 1 }]);
      h = list.map(function (c, i) { return rowBtn('m' + i, '<code>' + esc(c.module) + '</code> <small>' + (c.own ? '変更元' : (c.direction === 'reverse' ? 'を import している' : 'が import している') + '（' + c.depth + ' 段）') + '</small> ' + (c.via ? badge(c.via.state) : '')); }).join('');
      return { html: '<ul class="im-rea-flow">' + h + '</ul>', bind: function (box) { $$$(box).forEach(function (b) { b.addEventListener('click', function () { var c = list[+b.getAttribute('data-rid').slice(1)]; moduleDrawer(c.module, c.via, b); }); }); } };
    }
    if (k === 'routes') {
      list = f.route_rows;
      if (!list.length) return { html: '<div class="im-state" role="status">関連 route は 0 件です。</div>' };
      h = list.map(function (r, i) { return rowBtn('r' + i, '<code>' + esc((r.method ? r.method + ' ' : '') + r.value) + '</code> ' + ev(r.reach_class) + ' <small>' + esc(r.module || '') + '（静的）</small>'); }).join('');
      return { html: '<ul class="im-rea-flow">' + h + '</ul>', bind: function (box) { $$$(box).forEach(function (b) { b.addEventListener('click', function () { routeDrawer(list[+b.getAttribute('data-rid').slice(1)], b); }); }); } };
    }
    if (k === 'tests') {
      list = f.test_rows;
      if (!list.length) return { html: '<div class="im-state" role="status">関連テストは 0 件です。承認の阻害理由になります。</div>' };
      h = list.map(function (t, i) { return rowBtn('t' + i, 'テスト観点 ' + esc(t.text) + ' <small>（' + (t.source === 'runtime' ? '実測由来' : '静的候補由来') + '）</small>'); }).join('');
      return { html: '<ul class="im-rea-flow">' + h + '</ul>', bind: function (box) { $$$(box).forEach(function (b) { b.addEventListener('click', function () { testDrawer(list[+b.getAttribute('data-rid').slice(1)], b); }); }); } };
    }
    var st = W && W.status ? W.status.html('unverified', '承認状態は取得できません') : '承認状態は取得できません';
    var bl = f.blockers.length ? '<ul class="im-rea-flow im-rea-block">' + f.blockers.map(function (b) { return '<li><strong>阻害</strong> ' + esc(b.label) + (b.count ? '：' + b.count + ' 件' : '') + '</li>'; }).join('') + '</ul>'
      : '<p class="im-rea-note">この結果から見える阻害理由はありません（承認できるという意味ではありません）。</p>';
    return { html: '<div class="im-rea-appr"><div><h4 class="im-rea-note">承認</h4><p>' + st + '</p><p class="im-rea-note">承認は変更要求の承認画面で人が行います。この画面は承認しません。' + esc(f.link.reason) + '</p></div><div><h4 class="im-rea-note">阻害理由</h4>' + bl + '</div></div>' };
  }
  function $$$(box) { return Array.prototype.slice.call(box.querySelectorAll('.im-rea-row')); }
  function layerBands() {
    return '<div class="im-rea-bands" role="group" aria-label="2 つの層">' +
      '<div class="im-rea-band doc"><strong>文書の影響</strong><small>文書の項目のつながり。「つながり」「変更要求」で見ます。</small></div>' +
      '<div class="im-rea-band code"><strong>コード依存（サイト単位・静的）</strong><small>この画面。リバース解析の import 関係で、文書の影響とは別の層です。</small></div></div>';
  }
  function drawFlow(root, site, d) {
    var host = $('#im-rea-flow', root);
    if (!d.module || !d.flow) { host.innerHTML = flow(d); return; }
    var f = d.flow, active = null;
    function paint() {
      var x = active ? stageList(active, f, d) : null;
      host.innerHTML = stagesHtml(f, d, active) +
        (x ? '<div class="im-rea-fh"><span>絞り込み: ' + esc(STAGES.filter(function (g) { return g.k === active; })[0].t) + '</span><button type="button" class="btn-outline-sm" data-clear="1">絞り込みを解除</button></div><div id="im-rea-list">' + x.html + '</div>' : flow(d));
      Array.prototype.forEach.call(host.querySelectorAll('[data-stage]'), function (b) {
        b.addEventListener('click', function () { var k = b.getAttribute('data-stage'); active = active === k ? null : k; paint(); var again = host.querySelector('[data-stage="' + k + '"]'); if (again) again.focus(); });
      });
      var c = host.querySelector('[data-clear]'); if (c) c.addEventListener('click', function () { active = null; paint(); });
      if (x && x.bind) x.bind(host);
    }
    paint();
  }
  function view(root, site, d) {
    var m = d.metrics;
    var h = '<div class="im-rea-ba" role="group" aria-label="Before と After">' +
      dl('Before（リバース解析なし）', m.before, m.before.reason) + dl('After（Before ＋ コード依存）', m.after, '') +
      '<div class="im-rea-card"><h4>差分</h4><dl><dt>新規影響候補</dt><dd>' + (m.after.candidates - m.before.candidates) + '</dd><dt>追加の依存 edge</dt><dd>' + (m.after.dependency_edges - m.before.dependency_edges) +
      '</dd></dl><p class="im-rea-note">関連テスト: ' + esc((d.tests || {}).note || '') + '</p></div></div>';
    var opts = (d.sources || []).map(function (s) {
      return '<option value="' + esc(s.module) + '"' + (s.module === d.module ? ' selected' : '') + '>' + esc(s.module) + '（import ' + s.imports + '／被 import ' + s.imported_by + '）</option>';
    }).join('');
    h += '<div class="im-rea-bar"><label>変更元 module<select id="im-rea-mod"><option value="">選んでください</option>' + opts + '</select></label></div>';
    h += '<div id="im-rea-flow"></div>';
    $('#im-rea-body', root).innerHTML = h;
    drawFlow(root, site, d);
    $('#im-rea-mod', root).addEventListener('change', function (e) { load(root, site, e.target.value); });
  }
  function load(box, site, mod) {
    ui.loading($('#im-rea-body', box));
    get({ domain: site, module: mod }).then(function (d) {
      var body = $('#im-rea-body', box);
      if (d.state === 'unconfirmed') {
        body.innerHTML = '<div class="im-state" role="status"><strong>未確認（結果なし）</strong><p>' + esc(d.message || '') + '</p><p>System 01 でリバース解析を実行すると依存関係が加わります。</p></div>';
        return;
      }
      view(box, site, d);
    }, function (e) { ui.failed($('#im-rea-body', box), e, function () { load(box, site, mod); }); });
  }
  function render(el, ctx) {
    var sys = (ctx && ctx.system) || {}, sname = sys.name || sys.title || '';
    var link = 'コード依存はサイト単位（System01 のリバース解析結果）です。この対象システム' + (sname ? '（' + sname + '）' : '') + 'との対応は設定されていません。同じものとは限りません。';
    el.innerHTML = '<div class="dashboard-section-head"><div><h2 class="dash-section-title">コード依存（サイト単位・静的）<span id="im-rea-cur" class="im-rea-cur"></span></h2>' +
      '<p class="dashboard-section-copy">System 01 のリバース解析で見つけた module の import 関係です。' + esc(NOTICE) + '。既存の影響分析とは別の層です。</p></div></div>' +
      layerBands() + '<div id="im-rea-reason"></div><p class="im-rea-link" role="note">' + esc(link) + '</p>' +
      '<div class="im-rea-bar"><label>対象サイト<select id="im-rea-site"><option value="">読み込み中…</option></select></label></div><div id="im-rea-body"></div>';
    if (W && W.reason) W.reason($('#im-rea-reason', el), 'サイト（コード依存）と対象システムの関連付けは未設定です。同じものとは限りません。', 'warning');
    get({}).then(function (d) {
      var sites = d.sites || [], sel = $('#im-rea-site', el);
      if (!sites.length) {
        sel.innerHTML = '<option value="">リバース解析済みのサイトがありません</option>';
        $('#im-rea-body', el).innerHTML = '<div class="im-state" role="status"><strong>未確認（結果なし）</strong><p>System 01 でリバース解析を実行すると依存関係が加わります。</p></div>';
        return;
      }
      sel.innerHTML = sites.map(function (s) { return '<option value="' + esc(s) + '">' + esc(s) + '</option>'; }).join('');
      var cur = $('#im-rea-cur', el);
      function mark() { cur.textContent = ' ／ 選択中: ' + sel.value; }
      sel.addEventListener('change', function () { mark(); load(el, sel.value, ''); });
      mark();
      load(el, sel.value, '');
    }, function (e) { ui.failed($('#im-rea-body', el), e, function () { render(el, ctx); }); });
  }
  IM.rea = { render: render };
})();
