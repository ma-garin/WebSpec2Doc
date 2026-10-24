/* System 09 影響度分析 — 判断（1 画面で 変更要求 → 影響範囲 → 再テスト対象 → 判定 を辿る）。
   並びはサーバーが付けたリスク点（到達可能性 × 変更の強さ × 未検証）の順。件数で並べない。 */
(function () {
  'use strict';
  var IM = window.IM, api = IM.api, ui = IM.ui, esc = ui.esc, $$ = ui.$$;
  var CLS = { '合格': 'ok', '不合格': 'ng', '判定不能': 'hold', '未判定': 'hold' };

  function gate(label, v) {
    return '<div class="im-gate ' + (CLS[v.verdict] || 'hold') + '" data-verdict="' + esc(v.verdict) + '"><span class="im-gate-k">' + label + '</span>' +
      '<b class="im-gate-v">' + esc(v.verdict) + '</b><p>' + esc(v.reason) + (v.next ? '<br><span class="im-gate-next">' + esc(v.next) + '</span>' : '') + '</p></div>';
  }
  function impactRows(rows) {
    return rows.map(function (i, n) {
      var r = i.risk_score || {};
      return '<tr data-state="' + esc(i.state) + '"><td class="num">' + (n + 1) + '</td><td><b class="num">' + esc(r.score) + '</b></td>' +
        '<td><code>' + esc(i.item_code) + '</code> ' + esc(i.document_name || '') + '<div class="bt-hint">' + esc(r.why) + '</div></td>' +
        '<td>' + (r.untested ? '<span class="im-st st-rejected">未検証</span>' : '<span class="im-st st-verified">テストあり</span>') + '</td>' +
        '<td>' + esc(i.state_label) + '</td></tr>';
    });
  }
  function retestRows(rows) {
    return rows.map(function (t) {
      return '<tr><td>' + (t.kind === 'new' ? '<span class="im-st st-rejected">新規に作る</span>' : '<span class="im-st st-review">再実行</span>') + '</td>' +
        '<td>' + (t.test ? '<code>' + esc(t.test) + '</code>' : esc(t.idea || '確かめるテストを作る')) + '</td><td>' + esc(t.because.join('、')) + '</td><td class="num">' + esc(t.score) + '</td></tr>';
    });
  }
  function table(cols, rows, label) {
    return '<div class="bt-tblwrap im-tblwrap"><table class="bt-tbl" aria-label="' + esc(label) + '"><thead><tr>' +
      cols.map(function (c) { return '<th scope="col">' + c + '</th>'; }).join('') + '</tr></thead><tbody>' + rows.join('') + '</tbody></table></div>';
  }
  function draw(el, d, ctx) {
    var src = d.source || {}, m = d.missing_links || [];
    var srcBox = '<div class="im-src im-src-' + esc(src.kind) + '" role="note"><b>' + esc(src.label) + '</b>' +
      (src.inspection ? '<span>検査 ' + esc(src.inspection) + ' の意味差分から自動で起票されました。</span>' : '<span>この変更要求は利用者が起票しました。</span>') + '</div>';
    var imp = d.impacts.length ? table(['順', 'リスク', '影響する項目と理由', '検証', '判断'], impactRows(d.impacts), '影響範囲（リスク順）')
      : ui.empty({ title: '影響の候補はまだありません', desc: '「分析する」を押すと、変更が届く項目をリスクの高い順に並べます。' });
    var rt = d.retest.length ? table(['種類', 'テスト', '理由になった項目', 'リスク'], retestRows(d.retest), '再テスト対象')
      : '<p class="bt-hint">再テスト対象はありません。影響を「対応要」にすると、つながるテストがここに並びます。</p>';
    var ml = m.length ? '<ul class="im-missing">' + m.map(function (x) {
      return '<li><code>' + esc(x.code) + '</code> ' + esc(x.text) + ' — <b>' + esc(x.lack.join('・')) + 'へのつながりがありません</b></li>'; }).join('') + '</ul>'
      : '<p class="bt-hint">欠落しているつながりはありません。</p>';
    el.innerHTML = '<div class="im-decision" data-state="normal">' + srcBox +
      '<section class="im-dsec"><h3>1. 影響範囲 <small>' + esc(d.order) + '</small></h3>' + imp + '</section>' +
      '<section class="im-dsec"><h3>2. 再テスト対象</h3>' + rt + '</section>' +
      '<section class="im-dsec"><h3>3. 欠落しているつながり</h3>' + ml + '</section>' +
      '<section class="im-gates" aria-label="判定">' + gate('全体', d.verdict.overall) + gate('今回の変更分', d.verdict.change) + '</section>' +
      (d.impacts.length ? '<p class="im-dnext"><button type="button" class="btn-outline-sm" data-go="impacts">影響を 1 件ずつ判断する</button></p>' : '') + '</div>';
    $$('[data-go]', el).forEach(function (b) { b.addEventListener('click', function () { IM.app.go({ sid: ctx.sid, cr: ctx.cr, tab: b.dataset.go }); }); });
  }
  function render(el, cr, ctx) {
    ui.loading(el);
    api.decision(ctx.sid, ctx.cr).then(function (d) { draw(el, d, ctx); },
      function (e) { ui.failed(el, e, function () { render(el, cr, ctx); }); });
  }
  IM.decision = { render: render };
})();
