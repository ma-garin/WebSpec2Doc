/* ws-rea-viewpoints.js — リバース解析で増えたテスト観点（System 02）
 * T.reaViewpointsRender(host, domain): GET /api/sites/<domain>/rea-test-viewpoints を描く。
 * 状態は文字で示す（色だけにしない）。テキストは esc() 経由。
 */
(function () {
  'use strict';
  var T = window.TA2;
  if (!T) return;
  var seq = 0;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function tile(label, before, after, up) {
    return '<div class="rv-tile' + (up ? ' rv-tile-up' : '') + '"><div class="rv-tile-label">' + esc(label) + '</div>'
      + '<div class="rv-tile-nums"><span class="rv-num-b">' + esc(before) + '</span>'
      + '<span class="rv-arrow" aria-hidden="true">→</span><span class="rv-num-a">' + esc(after) + '</span></div></div>';
  }

  function rowHtml(v) {
    var lim = (v.limitations || []).map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('');
    var reach = v.kind === 'route'
      ? '<span class="rv-badge rt-reach rt-reach-' + esc(v.reach_status || 'not_probed') + '">到達: ' + esc(v.reach_label || '未探索') + '</span>'
        + (v.runnable ? '<span class="rv-badge rt-reach-run">' + esc(v.runnable_label || '実行対象（実測で到達）') + '</span>' : '')
      : '';
    var tag = v.is_new ? '' : '<span class="rt-note">既存の実測（増分に数えない）</span>';
    return '<li class="rt-row"><details><summary>'
      + '<span class="rt-text">' + esc(v.text) + '</span>'
      + '<span class="rt-meta"><span class="rv-badge rt-src-' + esc(v.source) + '">' + esc(v.source_label) + '</span>'
      + '<span class="rv-badge">根拠: ' + esc(v.evidence_state_label) + '</span>' + reach
      + '<span class="rt-loc">' + (v.location ? esc(v.location) : '位置: 未確認') + '</span>' + tag + '</span>'
      + '</summary><div class="rt-detail"><p>' + esc(v.claim || '（根拠の説明なし）') + '</p>'
      + (lim ? '<p class="rt-h">限界</p><ul>' + lim + '</ul>' : '')
      + '</div></details></li>';
  }

  function draw(host, d) {
    if (d.state !== 'ok') {
      host.innerHTML = '<div class="rv-card rv-notice"><h3 class="rv-notice-title">リバース解析で増えたテスト観点: 0 件（未確認）</h3>'
        + '<p class="rv-text">' + esc(d.message || 'リバース解析の根拠がありません。') + '</p>'
        + '<p class="rv-next"><b>次の操作</b> ' + esc(d.next_action || 'System01 でリバース解析を実行すると観点が増えます') + '</p></div>';
      return;
    }
    var m = d.metrics || {};
    var rows = d.viewpoints || [];
    var cov = (d.covered_by_runtime || []).length;
    host.innerHTML = '<div class="rt-wrap">'
      + '<div class="rv-head-main"><h3 class="rv-title">リバース解析で増えたテスト観点</h3>'
      + '<p class="rv-lead">静的解析の候補です。到達・実行は未確認のものを含みます（System 03 で到達を実測した route のみ「実測で到達」。探索済み ' + esc(m.probed || 0) + ' 件）。Before はリバース解析なし（' + esc(m.before_basis || '') + '）。</p></div>'
      + '<div class="rv-tiles">'
      + tile('テスト候補数', m.before, m.after, m.new > 0)
      + tile('新規観点数', 0, m.new, m.new > 0)
      + tile('Evidence 付き候補数', 0, m.with_evidence, m.with_evidence > 0)
      + tile('実行対象（実測で到達）', 0, m.runnable || 0, (m.runnable || 0) > 0)
      + '</div>'
      + (cov ? '<p class="rt-cov">実測で確認済みの API と同じ path の静的 API ' + cov + ' 件は、静的出典として扱い新規観点に数えていません。</p>' : '')
      + (rows.length ? '<details class="rt-more"><summary>観点の一覧と根拠（' + rows.length + ' 件）</summary><ul class="rt-list">' + rows.map(rowHtml).join('') + '</ul></details>'
        : '<p class="rv-text">リバース解析の根拠から作れる観点はありませんでした。</p>')
      + '</div>';
  }

  function render(host, domain) {
    if (!host) return;
    var my = ++seq;
    host.setAttribute('aria-busy', 'true');
    host.innerHTML = '<div class="rv-card rv-loading" role="status">観点を読み込んでいます…</div>';
    fetch('/api/sites/' + encodeURIComponent(domain || '') + '/rea-test-viewpoints', { headers: { 'Accept': 'application/json' } })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (j) { if (my !== seq) return; host.removeAttribute('aria-busy'); draw(host, j || {}); })
      .catch(function () {
        if (my !== seq) return;
        host.removeAttribute('aria-busy');
        draw(host, { state: 'error', message: '観点を取得できませんでした。', next_action: '通信状態を確認して、再読み込みしてください。' });
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
