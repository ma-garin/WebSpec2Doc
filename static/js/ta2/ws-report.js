/* ============================================================================
 * TA2 / ws-report.js — 報告（C3）
 *
 * 報告そのものはサーバが 1 枚の HTML として返す（GET /api/ta2/report）。
 * この画面はそれを iframe に写し、保存リンクへ同じ URL（&download=1）を張るだけ。
 * 節のチェックは URL の sections= に落ちる。サーバが解釈するので飾りではない。
 * ========================================================================== */
(function () {
  'use strict';
  var T = window.TA2, S = T.state, $ = T.$;

  var SECTIONS = ['runs', 'failures', 'coverage', 'drift', 'roi'];

  function chosen() {
    var out = [];
    SECTIONS.forEach(function (name) {
      var box = document.querySelector('#report-sections input[value="' + name + '"]');
      if (!box || box.checked) out.push(name);
    });
    return out;
  }

  function url(download) {
    var q = '/api/ta2/report?domain=' + encodeURIComponent(S.domain || '')
      + '&sections=' + encodeURIComponent(chosen().join(','));
    return download ? q + '&download=1' : q;
  }

  function apply() {
    var frame = $('#report-preview');
    var dl = $('#report-dl');
    var meta = $('#report-meta');
    if (!S.domain) {
      if (meta) meta.textContent = '対象サイトが選ばれていません。ホームでサイトを選んでください。';
      if (dl) { dl.setAttribute('aria-disabled', 'true'); dl.title = '対象サイトが選ばれていません'; }
      return;
    }
    if (dl) {
      dl.href = url(true);
      dl.removeAttribute('aria-disabled');
      dl.removeAttribute('title');
      dl.setAttribute('download', S.domain + '-report.html');
    }
    if (frame) frame.src = url(false);
    if (meta) meta.textContent = '選んだ節だけを 1 枚の HTML にします。外部の読み込みはありません。';
  }

  function print() {
    var frame = $('#report-preview');
    if (!frame || !frame.contentWindow) {
      T.toast('プレビューが読み込まれていません', 'ng');
      return;
    }
    frame.contentWindow.focus();
    frame.contentWindow.print();
  }

  function bind() {
    var box = $('#report-sections');
    if (box) box.addEventListener('change', apply);
    var p = $('#report-print');
    if (p) p.addEventListener('click', print);
  }

  bind();
  T.on('view', function (v) { if (v === 'report') apply(); });
  T.on('boot', function () { if (S.view === 'report') apply(); });
})();
