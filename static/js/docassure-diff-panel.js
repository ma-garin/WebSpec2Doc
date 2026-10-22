/* Document Assurance パネル: 意味差分。docassure.js からは window.DAPanels.diff 経由で呼ばれる。 */
(function () {
  'use strict';
  window.DAPanels = window.DAPanels || {};
  var CHANGE = {
    CREATED: ['＋', '新規'], MODIFIED: ['△', '変更'], REMOVED: ['－', '削除'],
    MOVED: ['↔', '位置のみ'], SPLIT: ['⑂', '分割'], MERGED: ['⑃', '統合']
  };
  var TYPE = { threshold_change: 'しきい値の変更' };
  var RISK = { high: '高', medium: '中', low: '低' };

  function side(esc, title, ref) {
    if (!ref) { return '<div class="dap-side"><h5>' + title + '</h5><p class="dap-muted">該当なし</p></div>'; }
    return '<div class="dap-side"><h5>' + title + '</h5><p class="dap-meta">' + esc(ref.document_id || '') + ' ' + esc(ref.section || '') +
      '</p><pre class="dap-text" tabindex="0">' + esc(ref.text || '') + '</pre></div>';
  }

  function meaning(esc, d) {
    if (d.change === 'MOVED') {
      return '<p class="dap-note">位置が変わっただけ。要件の変更ではありません。</p>';
    }
    var out = '';
    if (d.change_type) {
      out += '<p><strong>' + esc(TYPE[d.change_type] || d.change_type) + '</strong>' + (d.topic ? '（' + esc(d.topic) + '）' : '') + '</p>';
    }
    if (d.before_value != null || d.after_value != null) {
      out += '<p class="dap-change">' + esc(d.before_value) + ' → ' + esc(d.after_value) + '</p>';
    }
    if (d.risk) { out += '<p>リスク: ' + esc(RISK[d.risk] || d.risk) + '</p>'; }
    if (d.impacted_requirements && d.impacted_requirements.length) {
      out += '<p>影響しうる要件: ' + d.impacted_requirements.map(esc).join('、') + '</p>';
    }
    if (d.change === 'SPLIT') { out += '<p>分割先: ' + (d.after_ids || []).map(esc).join('、') + '</p>'; }
    if (d.change === 'MERGED') { out += '<p>統合元: ' + (d.before_ids || []).map(esc).join('、') + '</p>'; }
    if (!out) { out = '<p class="dap-muted">意味の変化は自動では特定できません。原文の差分を確認してください。</p>'; }
    return out;
  }

  function item(ctx, d) {
    var esc = ctx.esc, c = CHANGE[d.change] || ['?', d.change];
    return '<article class="dap-item" data-change="' + esc(d.change) + '">' +
      '<h4><span class="dap-badge dap-' + esc(String(d.change).toLowerCase()) + '">' + c[0] + ' ' + esc(c[1]) + '</span> ' + esc(d.requirement_id) + '</h4>' +
      '<section aria-label="意味の変化"><h5>意味の変化</h5>' + meaning(esc, d) + '</section>' +
      '<section aria-label="原文の差分"><h5>原文の差分（生の差分）</h5><div class="dap-cols">' +
      side(esc, '前の版', d.before) + side(esc, '今の版', d.after) + '</div></section></article>';
  }

  window.DAPanels.diff = {
    label: '意味差分',
    html: function (ctx) {
      return '<section class="dap" aria-labelledby="dap-diff-h"><h3 id="dap-diff-h">意味差分</h3>' +
        '<p class="dap-muted">前の版と今の版を比べ、位置だけの変更と要件の変更を分けて表示します。</p>' +
        '<div class="dap-body" data-dap-diff aria-live="polite"><p class="dap-muted">読み込み中…</p></div></section>';
    },
    bind: function (root, ctx) {
      var box = root.querySelector('[data-dap-diff]');
      if (!box) { return; }
      ctx.get('diff').then(function (r) {
        if (r.status === 404 && r.body && r.body.code === 'no_previous') {
          box.innerHTML = '<p class="dap-empty">前の版がありません。文書を更新して再分析すると表示されます。</p>';
          return;
        }
        if (!r.ok) {
          box.innerHTML = '<p class="dap-error" role="alert">' + ctx.esc((r.body && r.body.error) || '差分を取得できませんでした。時間をおいて再度お試しください。') + '</p>';
          return;
        }
        var list = (r.body && r.body.diff) || [];
        if (!list.length) { box.innerHTML = '<p class="dap-empty">前の版との違いはありません。</p>'; return; }
        var moved = list.filter(function (d) { return d.change === 'MOVED'; }).length;
        box.innerHTML = '<p class="dap-summary">変更 ' + (list.length - moved) + ' 件／位置のみ ' + moved + ' 件</p>' + list.map(function (d) { return item(ctx, d); }).join('');
      }).catch(function () {
        box.innerHTML = '<p class="dap-error" role="alert">通信に失敗しました。接続を確認して再度お試しください。</p>';
      });
    }
  };
})();
