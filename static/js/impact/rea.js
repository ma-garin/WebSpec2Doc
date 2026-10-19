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
      '</dd><dt>関連 route</dt><dd>' + m.routes + '</dd><dt>関連 API（静的）</dt><dd>' + m.apis + '</dd><dt>関連テスト</dt><dd>' + m.tests + '</dd></dl>' +
      (reason ? '<p class="im-rea-note">' + esc(reason) + '</p>' : '') + '</div>';
  }
  function items(list, label) {
    if (!list || !list.length) return '';
    return '<ul class="im-rea-rel" aria-label="' + esc(label) + '">' + list.map(function (i) {
      return '<li>' + esc(label) + ' <code>' + esc((i.method ? i.method + ' ' : '') + i.value) + '</code> ' + badge(i.state) + ' <small>' + esc(i.location || '') + '（静的）</small></li>';
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
    h += '<div id="im-rea-flow">' + flow(d) + '</div>';
    $('#im-rea-body', root).innerHTML = h;
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
    el.innerHTML = '<div class="dashboard-section-head"><div><h2 class="dash-section-title">コード依存（リバース解析・静的）</h2>' +
      '<p class="dashboard-section-copy">System 01 のリバース解析で見つけた module の import 関係です。' + esc(NOTICE) + '。既存の影響分析とは別の層です。</p></div></div>' +
      '<div class="im-rea-bar"><label>対象サイト<select id="im-rea-site"><option value="">読み込み中…</option></select></label></div><div id="im-rea-body"></div>';
    get({}).then(function (d) {
      var sites = d.sites || [], sel = $('#im-rea-site', el);
      if (!sites.length) {
        sel.innerHTML = '<option value="">リバース解析済みのサイトがありません</option>';
        $('#im-rea-body', el).innerHTML = '<div class="im-state" role="status"><strong>未確認（結果なし）</strong><p>System 01 でリバース解析を実行すると依存関係が加わります。</p></div>';
        return;
      }
      sel.innerHTML = sites.map(function (s) { return '<option value="' + esc(s) + '">' + esc(s) + '</option>'; }).join('');
      sel.addEventListener('change', function () { load(el, sel.value, ''); });
      load(el, sel.value, '');
    }, function (e) { ui.failed($('#im-rea-body', el), e, function () { render(el, ctx); }); });
  }
  IM.rea = { render: render };
})();
