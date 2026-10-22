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
      '<h4><span class="dar-no">候補 ' + (idx + 1) + '</span> <span class="dap-badge dap-src-' + esc(src) + '">' + esc(SRC[src] || src) + '</span> ' +
      (f.reviewers && f.reviewers.length ? '<span class="dar-tag" title="' + esc(f.reviewers.map(function (r) { return RJ[r] || r; }).join('・')) + '">' + esc(RJ[f.reviewers[0]] || f.reviewers[0]) + (f.reviewers.length > 1 ? ' ほか ' + (f.reviewers.length - 1) : '') + '</span> ' : '') +
      esc(f.finding) + '</h4>' +
      (disputed ? '<p class="dap-note">意見が割れています。どちらが正しいかは未確定です。</p>' : '') +
      '<div class="dar-chips"><span class="dar-chip dar-chip--cand">候補</span><span class="dar-chip">根拠 ' + ((f.evidence || []).length) + ' 箇所</span><span class="dar-chip"><i class="dar-dot dar-dot--' + esc(f.severity || 'info') + '" aria-hidden="true"></i>重大度 ' + esc(SEV[f.severity] || f.severity || '未設定') + '</span><span class="dar-chip">確からしさ ' + esc(f.confidence == null ? '未算出' : (Number(f.confidence) >= 0.75 ? '高' : Number(f.confidence) >= 0.4 ? '中' : '低')) + '</span></div>' +
      (f.reason ? '<p>理由: ' + esc(f.reason) + '</p>' : '') +
      (f.question ? '<p>確認したい点: ' + esc(f.question) + '</p>' : '') +
      (f.recommended_action ? '<p>推奨: ' + esc(f.recommended_action) + '</p>' : '') +
      '<h5>証拠（原文位置・引用）</h5>' + evidence(esc, f.evidence) +
      (st ? '<p class="dap-ok" role="status">判断を記録しました: ' + esc(st) + '</p>' :
        '<div class="dap-actions"><button type="button" class="dax-link" data-tab-go="issues">指摘画面で判断 →</button></div>') +
      '</article>';
  }

  var NOTE = '';
  var TRUTH = '<p class="dar-truth" role="note"><span class="dar-pill">候補です。承認済みではありません</span><span class="dax-meta">規則による解析と AI レビューの結果です。AI の候補は判定に反映されず、採用・却下は指摘画面で行います。</span></p>';
  var ROLE = '<p class="dax-meta">この画面の実行は AI レビューだけをやり直します。ヘッダの「再解析」は規則による解析をやり直します。</p>';
  function scope(ctx) {
    var d = ctx.data || {}, rq = d.requirements && d.requirements.ok ? (d.requirements.body || {}).requirements || [] : null, docs = {};
    (rq || []).forEach(function (u) { docs[u.document_id] = (docs[u.document_id] || 0) + 1; });
    return { n: rq ? rq.length : null, docs: docs, views: VIEWS.length };
  }
  var DOCN = { REQ: '要件定義書', DES: '基本設計書' };
  function tgt(sc) {
    if (sc.n == null) { return '要件 未提供'; }
    var ks = Object.keys(sc.docs);
    return '要件 ' + sc.n + ' 件' + (ks.length ? '（' + ks.map(function (k) { return (DOCN[k] || k) + ' ' + sc.docs[k]; }).join('・') + '）' : '');
  }
  function scopeHtml(ctx, sc) {
    var esc = ctx.esc, ks = Object.keys(sc.docs);
    return '<dl class="dar-kv"><dt>対象</dt><dd>' + esc(tgt(sc)) + '</dd>' +
      '<dt>観点</dt><dd>' + sc.views + ' 観点（右の一覧）</dd></dl>';
  }
  function provHtml(ctx, pv) {
    var esc = ctx.esc;
    if (!pv) { return '<p class="dax-meta">送信先を確認しています…</p>'; }
    if (pv.err) { return '<p class="dar-warn">送信先の設定を取得できませんでした。実行すると、設定どおりに処理されます。</p>'; }
    var none = pv.key === 'none';
    return '<dl class="dar-kv"><dt>AI の送信先</dt><dd>' + (none ? '未設定（AI は使いません）' : esc(pv.name || pv.key) + (pv.model ? '（' + esc(pv.model) + '）' : '')) + '</dd>' +
      (none ? '' : '<dt>送信</dt><dd>' + esc(pv.location || '') + '</dd>') + '</dl>' +
      '';
  }
  function card(kind, title, body) {
    return '<section class="dar-card dar-card--' + kind + '"><header class="dar-card__head"><span class="dar-st dar-st--' + kind + '">' + ST[kind] + '</span><h4 class="dar-card__title">' + title + '</h4></header>' + body + '</section>';
  }
  var ST = { idle: '未実施', run: '実行中', done: '完了', fail: '失敗', part: '一部のみ' };
  var VD = [['要件', '完全性・一貫性・曖昧さ'], ['テスト可能性', '受入基準・境界値'], ['構成', '責務分割・依存'], ['セキュリティ', '認証・認可・暗号・機密情報'], ['性能', '応答時間・容量・スループット'], ['信頼性', '障害時挙動・再試行・復旧'], ['UX', '操作・メッセージ・状態遷移'], ['アクセシビリティ', '支援技術・キーボード・色以外の手段'], ['運用', '保守・設定・デプロイ'], ['データ', '定義・保持・整合性・移行']];
  var RJ = { Requirements: '要件', 'QA-Testability': 'テスト可能性', Architecture: '構成', Security: 'セキュリティ', Performance: '性能', Reliability: '信頼性', UX: 'UX', Accessibility: 'アクセシビリティ', Operations: '運用', Data: 'データ' };
  var VIEWS = VD.map(function (x) { return x[0]; });
  function viewList(ctx) {
    function li(x) { return '<li><strong>' + ctx.esc(x[0]) + '</strong><span>' + ctx.esc(x[1]) + '</span></li>'; }
    return '<h5>AI が見る 10 観点</h5><ul class="dar-views">' + VD.slice(0, 3).map(li).join('') + '</ul><details class="dar-more"><summary class="dax-link">すべて見る（ほか 7 観点）</summary><ul class="dar-views">' + VD.slice(3).map(li).join('') + '</ul></details>';
  }
  var RUN = '<button type="button" class="dax-btn dax-btn--primary" data-dap-run>AI レビューを実行</button>';

  function idle(ctx, v) {
    var sc = scope(ctx);
    var none = v.prov && v.prov.key === 'none';
    return card('idle', 'AI レビューはまだ実行していません',
      (none ? '<p class="dar-warn" role="note">AI の送信先が設定されていないため、AI レビューは実行できません。規則による解析のみ実行できます。</p>' : '') +
      '<div class="dar-idle"><div class="dar-idle__main"><div class="dar-grid"><div><h5>何をレビューするか</h5>' + scopeHtml(ctx, sc) + '</div><div><h5>送信先</h5>' + provHtml(ctx, v.prov) + '</div></div>' +
      '<h5>実行の手順</h5><ol class="dar-flow" aria-label="実行の手順"><li><span class="dar-ico" aria-hidden="true">1</span>要件ごとに AI へ送る（外部なら事前に同意）</li><li><span class="dar-ico" aria-hidden="true">2</span>引用で根拠を確かめた指摘だけ候補に</li><li><span class="dar-ico" aria-hidden="true">3</span>採用・却下は指摘画面で人が決める</li></ol>' +
      (v.prov && v.prov.key === 'none'
        ? '<div class="dar-act"><details class="dar-ask"><summary class="dax-btn dax-btn--primary">送信先を管理者に依頼</summary><p>管理者に「AI の送信先（OpenAI など）を設定してほしい」と伝えてください。設定されると「AI レビューを実行」が使えるようになります。</p></details>' +
          '<button type="button" class="dax-btn" disabled aria-describedby="dar-why">AI レビューを実行</button><button type="button" class="dax-btn" data-dap-run>規則のみで実行</button></div>' +
          '<p class="dar-sub" id="dar-why" title="「規則のみで実行」は AI へ何も送らず、AI の観点は評価しません。">AI の送信先が未設定のため「AI レビューを実行」は使えません。前回の実行: 未提供</p>'
        : '<div class="dar-act">' + RUN + '<span class="dax-meta">前回の実行: 未提供</span></div>') + '</div><aside class="dar-idle__side">' + viewList(ctx) + '</aside></div>') + NOTE;
  }
  function running(ctx) {
    var sc = scope(ctx);
    return card('run', 'AI レビューを実行しています',
      '<div class="dar-prog" role="progressbar" aria-label="AI レビューの進捗" aria-valuetext="実行中（完了まで件数は分かりません）"><span></span></div>' +
      '<p class="dax-meta">対象: ' + ctx.esc(tgt(sc)) + ' × ' + sc.views + ' 観点。最大 120 秒で打ち切ります。途中の件数は表示できないため、完了までお待ちください。</p>' +
      '<div class="dar-act"><button type="button" class="dax-btn" data-dap-abort>中止</button><span class="dax-meta">中止すると結果を表示しません。送信済みの分は処理が続く場合があります。</span></div>') + NOTE;
  }
  function failed(ctx, v) {
    var esc = ctx.esc, c = v.code, act;
    if (c === 0) { act = ['接続を確認する', '接続できませんでした。ネットワークを確認してから再実行してください。']; }
    else if (c === 404) { act = ['先に規則による解析を行う', 'まだ分析されていません。ヘッダの「再解析」を実行してから再実行してください。']; }
    else if (c === 401 || c === 403) { act = ['権限を確認する', 'この操作の権限がありません。管理者に権限を依頼してください。']; }
    else { act = ['送信先を確認する／管理者へ連絡する', 'AI の送信先の設定（送信先・キー）を管理者に確認してもらい、解消しなければ管理者へ連絡してください。']; }
    return card('fail', 'AI レビューを完了できませんでした',
      '<dl class="dar-kv"><dt>失敗した時刻</dt><dd>' + esc(v.at || '—') + '</dd><dt>送信回数</dt><dd>未提供</dd><dt>原因</dt><dd' + (c ? ' title="コード ' + c + '"' : '') + '>' + esc(c >= 500 ? 'AI の送信先に接続できませんでした' : (v.err || '原因は未提供です')) + '</dd></dl>' +
      '<div class="dar-cols"><div class="dar-range dar-range--ng"><h5>次の行動: ' + esc(act[0]) + '</h5><p>' + esc(act[1]) + '</p><div class="dar-act">' + (c === 0 || c === 404 ? '<button type="button" class="dax-btn dax-btn--primary" data-dap-run>再実行</button>' : '<details class="dar-ask"><summary class="dax-btn dax-btn--primary">送信先を確認（管理者に依頼）</summary><p>管理者に、AI の送信先（モデル・キーを含む）が有効か確認を依頼してください。</p></details><button type="button" class="dax-btn" data-dap-run>再実行</button>') + '</div></div>' +
      '<div class="dar-range dar-range--ok"><h5>規則による結果だけで進める</h5><p>AI の候補は 1 件も保存していません。規則による解析の結果はそのまま有効です。</p><div class="dar-act"><button type="button" class="dax-btn" data-tab-go="issues">指摘画面で確認する</button></div></div></div>') +
      '<section class="dar-card dar-card--plain"><h5>失敗時の確認項目</h5><ul class="dar-check"><li>AI の送信先（モデルを含む）が管理者の設定どおりか</li><li>API キーが有効期限内で、利用上限に達していないか</li><li>この端末から接続できるか（他の画面は開けるか）</li><li>規則による解析が済んでいるか（未解析ならヘッダの「再解析」）</li><li>時間をおいて再実行しても同じ原因で失敗するか（続くなら管理者へ連絡）</li></ul></section>' + NOTE;
  }
  function partial(ctx, out) {
    var esc = ctx.esc, nr = out.not_reviewed || {}, sc = scope(ctx), ai = out.mode !== 'DEGRADED';
    var miss = ai ? (nr.count || 0) : sc.n;
    var why = !ai ? (out.failures ? 'AI への送信がすべて失敗しました（' + out.failures + ' 回）。' : 'AI の送信先が使えない、または設定されていません。') : (nr.reason ? '理由: ' + esc(nr.reason) : '上限（送信数・時間）に達しました。');
    return '<div class="dar-cols"><div class="dar-range dar-range--ok"><h5>評価できた範囲</h5><p class="dar-big">' + (ai ? (sc.n == null ? '—' : Math.max(0, sc.n - miss)) : 0) + '<span> 件（AI）</span></p><p>' + (ai ? '要件 ' + (sc.n == null ? '—' : Math.max(0, sc.n - miss)) + ' 件を AI が評価しました。' : 'AI による評価はありません。規則による解析（要件 ' + (sc.n == null ? '—' : sc.n) + ' 件）だけが有効です。') + '</p></div>' +
      '<div class="dar-range dar-range--ng"><h5>評価できなかった範囲</h5><p class="dar-big">' + (miss == null ? '—' : miss) + '<span> 件</span></p><p>未評価 ' + (miss == null ? '—' : miss) + ' 件（AI が評価していない要件）。' + why + '</p>' +
      ((nr.requirement_ids || []).length ? '<p class="dax-meta">' + esc(nr.requirement_ids.slice(0, 30).join('、')) + (nr.requirement_ids.length > 30 ? ' ほか' : '') + '</p>' : '') +
      '<p class="dax-meta">評価していない要件に指摘が無いことは、問題が無いことを意味しません。</p></div></div>';
  }
  function dedupe(fs) {
    var m = {}, o = [];
    fs.forEach(function (f) {
      var k = (f.finding || '') + '§' + (f.reason || '');
      if (m[k]) {
        if (f.reviewer && m[k].reviewers.indexOf(f.reviewer) < 0) { m[k].reviewers.push(f.reviewer); }
        (f.evidence || []).forEach(function (e) { if (!m[k].evidence.some(function (x) { return x.document_id === e.document_id && x.section === e.section && x.requirement_id === e.requirement_id && x.quote === e.quote; })) { m[k].evidence.push(e); } });
        return;
      }
      m[k] = Object.assign({}, f, { reviewers: f.reviewer ? [f.reviewer] : [], evidence: (f.evidence || []).slice() }); o.push(m[k]);
    });
    return o;
  }
  function done(ctx, out, decided) {
    var esc = ctx.esc, fs = dedupe(out.findings || []), degraded = out.mode === 'DEGRADED' || ((out.not_reviewed || {}).count > 0);
    var pv = out.provider && out.provider.name ? esc(out.provider.name) + (out.provider.model ? '（' + esc(out.provider.model) + '）' : '') : '';
    var head = '<div class="dar-sum"><p class="dar-strip"><span>候補 <b>' + fs.length + '</b> 件</span><span>根拠 <b>' + fs.reduce(function (n, f) { return n + (f.evidence || []).length; }, 0) + '</b> 箇所</span><span>未評価 <b>' + ((out.not_reviewed || {}).count || 0) + '</b> 件</span></p><p class="dax-meta">' + (pv ? 'AI の送信先: ' + pv + ' ／ ' : '') + '送信 ' + (out.sends || 0) + ' 回・再利用 ' + (out.cache_hits || 0) + ' 回・失敗 ' + (out.failures || 0) + ' 回</p></div>' +
      TRUTH +
      (fs.length ? '' : '<p class="dar-warn">根拠を確認できた候補は 0 件でした。0 件は「問題が無い」ことを意味しません。規則による指摘は指摘画面で確認してください。</p>') +
      '<div class="dar-act"><button type="button" class="dax-btn dax-btn--primary" data-tab-go="issues">指摘画面で確認する</button><button type="button" class="dax-btn" data-dap-run>AI レビューを再実行</button>' + (degraded && (out.not_reviewed || {}).count ? '<span class="dax-meta">未評価 ' + out.not_reviewed.count + ' 件も再度評価されます（範囲を指定した再実行はできません）。</span>' : '') + '</div>';
    if (out.mode === 'DEGRADED') { return card('part', 'AI レビューは一部のみ実行できました', '<p class="dar-truth"><span class="dar-pill dar-pill--rule">規則による解析のみ</span><span class="dax-meta">AI は使えませんでした。</span></p>' + partial(ctx, out) + '<div class="dar-act"><button type="button" class="dax-btn dax-btn--primary" data-dap-run>AI レビューを再実行</button><button type="button" class="dax-btn" data-tab-go="issues">指摘画面で確認する</button></div>') + NOTE; }
    return card(degraded ? 'part' : 'done', degraded ? 'AI レビューは一部のみ評価しました' : 'AI レビューが完了しました', head + (degraded ? partial(ctx, out) : '')) + list(ctx, out, decided) + NOTE;
  }
  function list(ctx, out, decided) {
    var esc = ctx.esc, fs = dedupe(out.findings || []), un = out.unsupported || [], dis = out.dismissed || [], h = '';
    if (fs.length) { h += '<section class="dap-group"><h4>候補（重複を除いて ' + fs.length + ' 件）</h4><div class="dar-fgrid">' + fs.map(function (f, i) { return finding(ctx, f, i, decided); }).join('') + '</div></section>'; }
    if (dis.length) {
      h += '<section class="dap-group"><h4>反証が見つかったため候補から外した指摘（' + dis.length + ' 件）</h4><ul>' +
        dis.map(function (f) { return '<li>' + esc(f.finding) + '</li>'; }).join('') + '</ul></section>';
    }
    if (un.length) {
      h += '<section class="dap-group dap-unsupported"><h4>根拠を確認できないため一覧から除外（' + un.length + ' 件）</h4><ul>' +
        un.map(function (f) { return '<li>' + esc(f.finding) + '<span class="dap-meta"> ' + esc((f.invalid_reasons || []).join('、')) + '</span></li>'; }).join('') + '</ul></section>';
    }
    return h ? '<div class="dar-list">' + h + '</div>' : '';
  }
  /* 状態 → HTML（純関数。v = { st: idle|run|done|fail, out, err, prov }） */
  function view(ctx, v, decided) {
    if (v.st === 'run') { return running(ctx); }
    if (v.st === 'fail') { return failed(ctx, v); }
    if (v.st === 'done' && v.out) { return done(ctx, v.out, decided || {}); }
    return idle(ctx, v);
  }

  window.DAPanels.review = {
    label: 'AI レビュー',
    view: view,
    html: function (ctx) {
      return '<section class="dap dar" aria-labelledby="dap-rv-h"><h3 id="dap-rv-h">AI レビュー</h3>' +
        '<p class="dar-role">この画面の実行は AI レビューだけをやり直します（ヘッダの「再解析」は規則による解析）。</p><div class="dap-body" data-dap-review aria-live="polite">' + view(ctx, { st: 'idle' }) + '</div>' +
        '<dialog class="dap-dialog" data-dap-consent aria-labelledby="dap-cs-h"><form method="dialog">' +
        '<h4 id="dap-cs-h">文書の一部を外部へ送ります</h4><p data-dap-dest></p>' +
        '<p>送信してよい場合だけ同意してください。同意しない場合は何も送りません。</p>' +
        '<div class="dap-actions"><button type="button" class="dax-btn dax-btn--primary" data-dap-agree>同意して送信</button> ' +
        '<button type="button" class="dax-btn" data-dap-cancel>やめる</button></div></form></dialog></section>';
    },
    bind: function (root, ctx) {
      var box = root.querySelector('[data-dap-review]'), dlg = root.querySelector('[data-dap-consent]');
      var decided = {}, v = { st: 'idle' }, seq = 0;
      if (!box || !dlg) { return; }
      function paint(focusSel) { box.innerHTML = view(ctx, v, decided); var f = focusSel && box.querySelector(focusSel); if (f) { f.focus(); } }
      fetch('/api/docverify/r2/llm-settings', { headers: { Accept: 'application/json' } }).then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
        .then(function (j) { v.prov = j.destination || { err: true }; }).catch(function () { v.prov = { err: true }; })
        .then(function () { if (v.st === 'idle') { paint(); } });
      function exec(confirm) {
        var my = ++seq; v.st = 'run'; paint('[data-dap-abort]');
        ctx.post('review', { confirm_send: !!confirm }).then(function (r) {
          if (my !== seq) { return; }
          if (r.status === 409 && r.body && r.body.code === 'consent_required') {
            v.st = 'idle'; paint();
            root.querySelector('[data-dap-dest]').textContent = '送信先: ' + (DEST[r.body.destination] || r.body.destination || '外部 AI') + '。文書の一部を外部へ送ります。';
            if (dlg.showModal) { dlg.showModal(); } else { dlg.setAttribute('open', ''); }
            var b = dlg.querySelector('[data-dap-agree]'); if (b) { b.focus(); }
            return;
          }
          if (!r.ok) { v.st = 'fail'; v.code = r.status; v.at = new Date().toLocaleString('ja-JP'); v.err = (r.body && r.body.error) || 'AI レビューを完了できませんでした。時間をおいて再実行してください。'; paint('[data-dap-run]'); return; }
          v.st = 'done'; v.out = r.body; paint();
        }).catch(function () { if (my !== seq) { return; } v.st = 'fail'; v.code = 0; v.at = new Date().toLocaleString('ja-JP'); v.err = '通信に失敗しました。'; paint('[data-dap-run]'); });
      }
      function close() { if (dlg.close) { dlg.close(); } else { dlg.removeAttribute('open'); } }
      dlg.querySelector('[data-dap-agree]').addEventListener('click', function () { close(); exec(true); });
      function cancel() { close(); v.st = 'idle'; paint('[data-dap-run]'); }
      dlg.querySelector('[data-dap-cancel]').addEventListener('click', cancel);
      dlg.addEventListener('keydown', function (e) { if (e.key === 'Escape') { e.preventDefault(); cancel(); } });
      box.addEventListener('click', function (e) {
        if (e.target.closest('[data-dap-run]')) { exec(false); return; }
        if (e.target.closest('[data-dap-abort]')) { seq++; v.st = v.out ? 'done' : 'idle'; paint('[data-dap-run]'); return; }
        var btn = e.target.closest && e.target.closest('[data-decide]');
        if (!btn) { return; }
        var art = btn.closest('article'), ta = art.querySelector('.dap-reason'), target = btn.getAttribute('data-target');
        if (ta && !ta.value.trim()) { var old = art.querySelector('.dap-error'); if (old) { old.remove(); } var m0 = document.createElement('p'); m0.className = 'dap-error'; m0.setAttribute('role', 'alert'); m0.textContent = '理由が空です。理由を入力してからもう一度押してください。'; art.appendChild(m0); ta.focus(); return; }
        btn.disabled = true;
        ctx.post('decisions', { decision: btn.getAttribute('data-decide'), target: target, reason: ta ? ta.value : '' }).then(function (r) {
          if (!r.ok) { btn.disabled = false; var m = document.createElement('p'); m.className = 'dap-error'; m.setAttribute('role', 'alert'); m.textContent = (r.body && r.body.error) || '記録できませんでした。再度お試しください。'; art.appendChild(m); return; }
          decided[target] = btn.getAttribute('data-decide') === 'accepted' ? '採用' : '却下';
          paint();
        });
      });
    }
  };
})();
