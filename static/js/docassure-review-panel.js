/* Document Assurance パネル: AI レビュー（Review Board）。AI の結果は候補。確定は人が行う。 */
(function () {
  'use strict';
  window.DAPanels = window.DAPanels || {};
  var SRC = { deterministic: '規則', ai: 'AI', hybrid: '規則＋AI', human: '人' };
  var SEV = { critical: '致命的', high: '高', medium: '中', low: '低', info: '情報' };
  var DEST = { openai: '外部 AI（OpenAI）' };

  function evidence(esc, list) {
    if (!list || !list.length) { return '<p class="dap-muted">証拠なし</p>'; }
    return '<ul class="dap-evidence">' + list.map(function (e) {
      var pos = [e.document_id, e.section, e.requirement_id].filter(Boolean).map(esc).join(' / ');
      return '<li><span class="dap-meta">' + pos + '</span><blockquote>' + esc(e.quote || '') + '</blockquote></li>';
    }).join('') + '</ul>';
  }

  function finding(ctx, f, idx, decided) {
    var esc = ctx.esc, src = f.source || 'ai', id = esc(f.finding_id || f.requirement_id || ('F' + idx));
    var disputed = f.disputed || f.dispute_status === 'DISPUTED';
    var st = decided[f.finding_id || f.requirement_id || ('F' + idx)];
    return '<article class="dap-item" data-fid="' + id + '">' +
      '<h4><span class="dap-badge dap-src-' + esc(src) + '">' + esc(SRC[src] || src) + '</span> ' +
      '<span class="dap-badge">候補</span> ' + esc(f.finding) + '</h4>' +
      (disputed ? '<p class="dap-note">意見が割れています。どちらが正しいかは未確定です。</p>' : '') +
      '<p class="dap-meta">重要度: ' + esc(SEV[f.severity] || f.severity || '') + ' ／ 確からしさ: ' + esc(f.confidence == null ? '未算出' : (Number(f.confidence) >= 0.75 ? '高' : Number(f.confidence) >= 0.4 ? '中' : '低')) + '</p>' +
      (f.reason ? '<p>理由: ' + esc(f.reason) + '</p>' : '') +
      (f.question ? '<p>確認したい点: ' + esc(f.question) + '</p>' : '') +
      (f.recommended_action ? '<p>推奨: ' + esc(f.recommended_action) + '</p>' : '') +
      '<h5>証拠（原文位置・引用）</h5>' + evidence(esc, f.evidence) +
      (st ? '<p class="dap-ok" role="status">判断を記録しました: ' + esc(st) + '</p>' :
        '<label class="dap-label">判断の理由<textarea class="dap-reason" rows="2" maxlength="2000"></textarea></label>' +
        '<div class="dap-actions"><button type="button" class="c-btn c-btn--secondary c-btn--sm" data-decide="accepted" data-target="' + id + '">採用する</button> ' +
        '<button type="button" class="c-btn c-btn--secondary c-btn--sm" data-decide="rejected" data-target="' + id + '">却下する</button></div>') +
      '</article>';
  }

  function render(ctx, out, decided) {
    var esc = ctx.esc;
    if (out.mode === 'DEGRADED') {
      return '<p class="dap-note" role="status">AI レビューは実行していません（規則による分析のみ）。AI の観点は評価していません。左の「設定」で AI の送信先を選ぶと、候補を追加できます。</p>';
    }
    var fs = out.findings || [], un = out.unsupported || [], dis = out.dismissed || [];
    var by = {};
    fs.forEach(function (f, i) { var k = f.reviewer || '未分類'; (by[k] = by[k] || []).push([f, i]); });
    var h = '<p class="dap-summary">AI の指摘は候補です。確定は人が行います。' +
      (out.provider && out.provider.name ? '（' + esc(out.provider.name) + ' ' + esc(out.provider.model || '') + '）' : '') + '</p>';
    if (!fs.length) { h += '<p class="dap-empty">根拠付きの指摘はありませんでした。</p>'; }
    Object.keys(by).forEach(function (k) {
      h += '<section class="dap-group"><h4>観点: ' + esc(k) + '</h4>' + by[k].map(function (p) { return finding(ctx, p[0], p[1], decided); }).join('') + '</section>';
    });
    if (dis.length) {
      h += '<section class="dap-group"><h4>反証が見つかったため候補から外した指摘（' + dis.length + ' 件）</h4><ul>' +
        dis.map(function (f) { return '<li>' + esc(f.finding) + '</li>'; }).join('') + '</ul></section>';
    }
    if (un.length) {
      h += '<section class="dap-group dap-unsupported"><h4>根拠を確認できないため一覧から除外（' + un.length + ' 件）</h4><ul>' +
        un.map(function (f) { return '<li>' + esc(f.finding) + '<span class="dap-meta"> ' + esc((f.invalid_reasons || []).join('、')) + '</span></li>'; }).join('') + '</ul></section>';
    }
    return h;
  }

  window.DAPanels.review = {
    label: 'AI レビュー',
    html: function (ctx) {
      return '<section class="dap" aria-labelledby="dap-rv-h"><h3 id="dap-rv-h">AI レビュー</h3>' +
        '<p class="dap-muted">複数の観点で文書を読み、指摘の候補を出します。AI の指摘は候補で、規則による分析の結果は変わりません。設定で AI を有効にしていない場合は実行されません。</p>' +
        '<button type="button" class="c-btn c-btn--secondary" data-dap-run>AI レビューを実行</button>' +
        '<div class="dap-body" data-dap-review aria-live="polite"></div>' +
        '<dialog class="dap-dialog" data-dap-consent aria-labelledby="dap-cs-h"><form method="dialog">' +
        '<h4 id="dap-cs-h">文書の一部を外部へ送ります</h4><p data-dap-dest></p>' +
        '<p>送信してよい場合だけ同意してください。同意しない場合は何も送りません。</p>' +
        '<div class="dap-actions"><button type="button" class="c-btn c-btn--primary" data-dap-agree>同意して送信</button> ' +
        '<button type="button" class="c-btn c-btn--secondary" data-dap-cancel>やめる</button></div></form></dialog></section>';
    },
    bind: function (root, ctx) {
      var run = root.querySelector('[data-dap-run]'), box = root.querySelector('[data-dap-review]');
      var dlg = root.querySelector('[data-dap-consent]'), decided = {}, last = null;
      if (!run || !box || !dlg) { return; }
      var path = '/api/docassure/inspections/' + encodeURIComponent(ctx.iid);
      function show(msg, alert) { box.innerHTML = '<p class="' + (alert ? 'dap-error' : 'dap-muted') + '"' + (alert ? ' role="alert"' : '') + '>' + ctx.esc(msg) + '</p>'; }
      function exec(confirm) {
        run.disabled = true; show('AI レビューを実行しています…');
        ctx.post('review', { confirm_send: !!confirm }).then(function (r) {
          run.disabled = false;
          if (r.status === 409 && r.body && r.body.code === 'consent_required') {
            root.querySelector('[data-dap-dest]').textContent = '送信先: ' + (DEST[r.body.destination] || r.body.destination || '外部 AI') + '。文書の一部を外部へ送ります。';
            box.innerHTML = '';
            if (dlg.showModal) { dlg.showModal(); } else { dlg.setAttribute('open', ''); }
            var b = dlg.querySelector('[data-dap-agree]'); if (b) { b.focus(); }
            return;
          }
          if (!r.ok) { show((r.body && r.body.error) || 'AI レビューに失敗しました。時間をおいて再度お試しください。', true); return; }
          last = r.body; box.innerHTML = render(ctx, last, decided);
        }).catch(function () { run.disabled = false; show('通信に失敗しました。接続を確認して再度お試しください。', true); });
      }
      function close() { if (dlg.close) { dlg.close(); } else { dlg.removeAttribute('open'); } run.focus(); }
      run.addEventListener('click', function () { exec(false); });
      dlg.querySelector('[data-dap-agree]').addEventListener('click', function () { close(); exec(true); });
      dlg.querySelector('[data-dap-cancel]').addEventListener('click', function () { close(); show('送信をやめました。'); });
      dlg.addEventListener('keydown', function (e) { if (e.key === 'Escape') { e.preventDefault(); close(); show('送信をやめました。'); } });
      box.addEventListener('click', function (e) {
        var btn = e.target.closest && e.target.closest('[data-decide]');
        if (!btn) { return; }
        var art = btn.closest('article'), ta = art.querySelector('.dap-reason'), target = btn.getAttribute('data-target');
        if (ta && !ta.value.trim()) { var old = art.querySelector('.dap-error'); if (old) { old.remove(); } var m0 = document.createElement('p'); m0.className = 'dap-error'; m0.setAttribute('role', 'alert'); m0.textContent = '理由が空です。理由を入力してからもう一度押してください。'; art.appendChild(m0); ta.focus(); return; }
        btn.disabled = true;
        ctx.post('decisions', { decision: btn.getAttribute('data-decide'), target: target, reason: ta ? ta.value : '' }).then(function (r) {
          if (!r.ok) { btn.disabled = false; var m = document.createElement('p'); m.className = 'dap-error'; m.setAttribute('role', 'alert'); m.textContent = (r.body && r.body.error) || '記録できませんでした。再度お試しください。'; art.appendChild(m); return; }
          decided[target] = btn.getAttribute('data-decide') === 'accepted' ? '採用' : '却下';
          box.innerHTML = render(ctx, last, decided);
        });
      });
    }
  };
})();
