/* ドキュメント検証 R5: 精度ページ（SCR-06-10）。GET /api/docverify/accuracy を表で示す。 */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function v(x) { return x == null || x === '' ? '未測定' : x; }
  function table(head, rows) {
    return '<table class="dv-t"><thead><tr>' + head.map(function (h) { return '<th>' + esc(h) + '</th>'; }).join('') +
      '</tr></thead><tbody>' + rows.map(function (r) {
        return '<tr>' + r.map(function (c) { return '<td>' + c + '</td>'; }).join('') + '</tr>';
      }).join('') + '</tbody></table>';
  }

  function renderMeta(d) {
    var ds = d.dataset || {};
    var lines = [
      ['測定日', esc(v(d.measured_on))],
      ['データセット', d.dataset ? esc(ds.name) + '（' + esc(ds.language) + '・' + esc(ds.n) + ' 文・' + esc(ds.license) + '）' : '未測定'],
      ['注釈者数', esc(v(ds.annotators))],
      ["Cohen's kappa", esc(v(d.kappa))],
      ['規則の版', esc(v(d.rules_version))],
      ['前回の測定日', esc(v(d.previous_measured_on))],
      ['対象', esc(d.scope || '未測定')],
      ['既定で無効にする基準', '適合率 ' + esc(d.min_precision) + ' 未満']
    ];
    var msg = d.message ? '<p class="mut">' + esc(d.message) + '</p>' : '';
    $('dvAccMeta').innerHTML = msg + '<table class="dv-t"><tbody>' + lines.map(function (l) {
      return '<tr><th>' + esc(l[0]) + '</th><td>' + l[1] + '</td></tr>';
    }).join('') + '</tbody></table>';
  }

  function renderRules(d) {
    var rows = (d.rules || []).map(function (r) {
      var state = r.enabled_by_default ? '有効' : '<span class="chip c-maj">既定で無効</span>';
      return [esc(r.label), esc(r.precision), esc(r.recall), esc(v(r.n)), esc(r.n_gold == null ? '—' : r.n_gold),
        esc(r.n_predicted == null ? '—' : r.n_predicted), esc(r.previous.precision) + ' / ' + esc(r.previous.recall),
        esc(r.delta.precision) + ' / ' + esc(r.delta.recall), state, esc(r.reason)];
    });
    $('dvAccTable').innerHTML = rows.length ? table(['規則', '適合率', '再現率', 'n（文）', '正解の件数', '検出の件数',
      '前回（適合率 / 再現率）', '差（適合率 / 再現率）', '状態', '理由'], rows) : '<p class="mut">規則がありません。</p>';
  }

  function renderMethods(d) {
    var methods = d.methods || [];
    var head = ['規則'].concat(methods.map(function (m) { return m.label + '（適合率 / 再現率 / n）'; }));
    var rows = (d.rules || []).map(function (r) {
      return [esc(r.label)].concat(methods.map(function (m) {
        var c = (r.by_method || {})[m.key] || {};
        return esc(v(c.precision)) + ' / ' + esc(v(c.recall)) + ' / ' + esc(v(c.n));
      }));
    });
    $('dvAccMethods').innerHTML = '<h3 class="dvg-h3">測定方法ごとの値</h3>' + table(head, rows);
  }

  function renderLimits(d) {
    var items = d.limits || [];
    $('dvAccLimits').innerHTML = '<h3 class="dvg-h3">限界</h3>' + (items.length ?
      '<ul>' + items.map(function (s) { return '<li>' + esc(s) + '</li>'; }).join('') + '</ul>' : '<p class="mut">未測定</p>');
  }

  function fail(msg) {
    $('dvAccMeta').innerHTML = '<p class="mut" role="alert">' + esc(msg) + '</p>';
    ['dvAccTable', 'dvAccMethods', 'dvAccLimits'].forEach(function (id) { $(id).innerHTML = ''; });
  }

  function load() {
    if (!$('dvAccMeta')) return;
    $('dvAccMeta').innerHTML = '<p class="mut">読み込み中…</p>';
    fetch('/api/docverify/accuracy', { headers: { Accept: 'application/json' } }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (d) { return { ok: res.ok, d: d }; });
    }).then(function (x) {
      if (!x.ok) { fail(x.d.error || '精度を読めませんでした。時間をおいて再読み込みしてください。'); return; }
      renderMeta(x.d); renderRules(x.d); renderMethods(x.d); renderLimits(x.d);
    }).catch(function () { fail('精度を読めませんでした。通信を確かめてから再読み込みしてください。'); });
  }

  function onRoute() { if (location.hash === '#accuracy') load(); }
  document.addEventListener('DOMContentLoaded', function () {
    var btn = $('dvAccReload');
    if (btn) btn.addEventListener('click', load);
    onRoute();
  });
  window.addEventListener('hashchange', onRoute);
  window.DVAccuracy = { load: load };
})();
