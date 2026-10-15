/* System 09 影響度分析 — 変更要求の画面（変更内容・影響・関係図・マトリクス・テスト・承認・改修後レビュー）と分析ジョブ。
   状態遷移は DD-007、操作の可否は DD-003（my_role）。ジョブの進捗は表示中のジョブが終わるまで 1 秒ごとに取る。 */
(function () {
  'use strict';
  var IM = window.IM, api = IM.api, ui = IM.ui, esc = ui.esc, $ = ui.$, $$ = ui.$$;
  var TITLE = { changes: '変更内容', impacts: '影響', graph: '関係図', matrix: 'マトリクス', tests: 'テスト', approval: '承認', review: '改修後レビュー' };
  var STAGE = { queued: '開始を待っています', changes: '変更箇所を作っています', candidates: '影響の候補を集めています', llm: 'LLM で判定しています', risk: 'リスクを計算しています', save: '結果を保存しています' };
  var CHG = { add: '追加', modify: '変更', 'delete': '削除', text: '文章' };
  var EVI = { link: 'つながり', semantic: '意味検索', keyword: '語の一致', llm: 'LLM 判定' };
  var RES = { open: '要確認', required: '対応要', not_required: '対応不要' };
  var TERMINAL = ['done', 'failed', 'cancelled', 'interrupted'];
  var job = null, lastFail = null, pendingSelect = null;

  function table(cols, rows, label, cls) {
    return '<div class="bt-tblwrap im-tblwrap"><table class="bt-tbl ' + (cls || '') + '" aria-label="' + esc(label) + '"><thead><tr>' +
      cols.map(function (c) { return '<th scope="col">' + c + '</th>'; }).join('') + '</tr></thead><tbody>' + rows.join('') + '</tbody></table></div>';
  }
  function on(el, sel, fn) { $$(sel, el).forEach(function (b) { b.addEventListener('click', function (e) { fn(b, e); }); }); }
  function arr(v) { if (Array.isArray(v)) return v; try { var p = JSON.parse(v || '[]'); return Array.isArray(p) ? p : []; } catch (_) { return []; } }
  function eff(i) {
    var I = i.override_impact != null ? i.override_impact : i.impact_level, L = i.override_likelihood != null ? i.override_likelihood : i.likelihood;
    return { I: I, L: L, R: i.risk != null ? i.risk : I * L, P: i.priority };
  }
  function rerender() { IM.app.render(); }

  /* ---------- 分析ジョブ ---------- */
  function stopPoll() { if (job && job.timer) clearTimeout(job.timer); job = null; }
  function leave(sid, code) { if (job && (job.sid !== sid || job.code !== code)) stopPoll(); }
  function jobBox() { return document.getElementById('im-job'); }
  function drawJob(j, canStop) {
    var box = jobBox(); if (!box) return;
    var pct = Math.max(0, Math.min(100, Number(j.progress) || 0));
    box.innerHTML = '<div class="bt-card im-jobcard" role="status" aria-live="polite"><div class="im-row"><b>分析中: ' + esc(STAGE[j.stage] || STAGE[j.status] || j.stage || '処理しています') + '</b>' +
      '<span class="sp"></span>' + (canStop ? '<button type="button" class="btn-outline-sm" data-act="cancel">中止する</button>' : '') + '</div>' +
      '<div class="im-bar" role="progressbar" aria-label="分析の進み具合" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + pct + '"><span></span></div>' +
      '<p class="bt-hint">' + pct + '%' + (j.message ? ' ・ ' + esc(j.message) : '') + '</p></div>';
    $('.im-bar span', box).style.width = pct + '%'; /* CSP: style 属性は使わず CSSOM で幅を設定する */
    $$('.im-cracts button').forEach(function (b) { b.disabled = true; });
    on(box, '[data-act=cancel]', function (b) {
      b.disabled = true; b.textContent = '中止しています…';
      api.cancelJob(job && job.id).then(null, function (e) { b.disabled = false; b.textContent = '中止する'; ui.banner(e.message); });
    });
  }
  function finish(j, ctx) {
    var code = job && job.code; stopPoll();
    if (j.status === 'done') { ui.toast('分析が終わりました'); IM.app.go({ sid: ctx.sid, cr: code, tab: 'impacts' }); return; }
    if (j.status === 'cancelled') { ui.toast('分析を中止しました。変更要求は起票の状態に戻りました'); rerender(); return; }
    lastFail = { code: code, stage: STAGE[j.stage] || j.stage || '', message: j.message || '分析が止まりました。もう一度「分析する」を押してください。' };
    rerender();
  }
  function poll(ctx, canStop) {
    if (!job) return;
    var id = job.id;
    api.job(id).then(function (d) {
      if (!job || job.id !== id) return;
      var j = api.obj(d, 'job');
      if (TERMINAL.indexOf(j.status) >= 0) { finish(j, ctx); return; }
      drawJob(j, canStop);
      job.timer = setTimeout(function () { poll(ctx, canStop); }, 1000);
    }, function (e) {
      if (!job || job.id !== id) return;
      var box = jobBox(); stopPoll();
      if (box) { box.innerHTML = '<div class="im-state im-state-ng" role="alert"><b>進捗を取得できませんでした</b><p>' + esc(e.message) + '</p><button type="button" class="btn-outline-sm" data-act="repoll">もう一度確認する</button></div>';
        on(box, '[data-act=repoll]', function () { startPoll(ctx, id, canStop); }); }
    });
  }
  function startPoll(ctx, id, canStop) {
    stopPoll();
    job = { id: id, sid: ctx.sid, code: ctx.cr, timer: null };
    drawJob({ status: 'queued', progress: 0 }, canStop);
    poll(ctx, canStop);
  }
  function analyze(ctx, btn) {
    btn.disabled = true;
    var run = function (confirmSend) {
      return api.analyze(ctx.sid, ctx.cr, confirmSend).then(function (d) {
        var j = d.job; var id = j && typeof j === 'object' ? j.id : (j || d.job_id);
        lastFail = null; startPoll(ctx, id, true);
      });
    };
    api.estimate(ctx.sid, ctx.cr).then(function (est) {
      if (!est.policy || est.policy === 'none') return run(false);
      btn.disabled = false;
      ui.modal({ title: 'LLM への送信の確認', submit: '送信して分析する', danger: false,
        body: '<p class="im-confirm">分析のために次の量を LLM に送ります（送信方針: ' + esc(ui.POLICY[est.policy] || est.policy) + '）。</p>' +
          '<div class="kpis im-kpis2"><div class="kpi"><b>' + esc(est.count || 0) + '</b><span>送る項目数</span></div><div class="kpi"><b>' + esc(est.chars || 0) + '</b><span>文字数</span></div></div>' +
          '<p class="bt-hint">文書の本文は指示ではなくデータとして渡します。送信は監査ログに記録します。</p>',
        onSubmit: function () { return run(true); } });
    }).then(null, function (e) { btn.disabled = false; ui.banner(e.message); });
  }

  /* ---------- ヘッダ（状態と操作） ---------- */
  function actions(cr, ctx) {
    var w = ui.can(ctx.role, 'cr_write'), a = ui.can(ctx.role, 'approve'), s = cr.summary || {}, st = cr.status, b = [];
    var openN = Number(s.open || 0), analyzed = Number(s.total || 0) > 0 || !!cr.analyzed_at;
    var toReview = '<button type="button" class="btn-outline-sm" data-to="review"' + (openN > 0 || !analyzed ? ' disabled title="' + (analyzed ? '要確認が ' + openN + ' 件あります。影響をすべて解消してください' : '先に分析してください') + '"' : '') + '>レビューに回す</button>';
    if (w && (st === 'draft' || st === 'returned')) b.push('<button type="button" class="btn-primary" data-act="analyze">分析する</button>');
    if (w && st === 'analyzing' && !job) b.push('<button type="button" class="btn-outline-sm" data-act="analyze">再分析する</button>');
    if (w && (st === 'analyzing' || st === 'returned') && !job) b.push(toReview);
    if (w && (st === 'draft' || st === 'returned')) b.push('<button type="button" class="btn-outline-sm im-btn-danger" data-to="rejected">却下する</button>');
    if (a && st === 'review') b.push('<button type="button" class="btn-primary" data-dec="approved">承認する</button><button type="button" class="btn-outline-sm im-btn-danger" data-dec="returned">差し戻す</button>');
    if (w && st === 'approved') b.push('<button type="button" class="btn-primary" data-to="implemented">実装済みにする</button>');
    if (w && st === 'implemented') b.push('<button type="button" class="btn-primary" data-to="verified">検証済みにする</button>');
    b.push('<a class="btn-outline-sm" href="' + esc(api.reportUrl(ctx.sid, ctx.cr)) + '" download>Excel で書き出す</a>');
    return b.join('');
  }
  function header(cr, ctx) {
    var s = cr.summary || {}, e = cr.engine || {};
    var k = [['total', '影響'], ['p1', 'P1'], ['p2', 'P2'], ['p3', 'P3'], ['open', '要確認'], ['retest', '再テスト'], ['test_gap', 'テストの抜け']];
    var degraded = e.mode && e.mode !== 'llm' && e.mode !== 'embedding';
    return '<div class="im-crhead"><div class="im-crtitle"><code>' + esc(cr.code) + '</code><h2>' + esc(cr.title) + '</h2>' + ui.statusBadge(cr.status) + '</div>' +
      '<div class="im-cracts">' + actions(cr, ctx) + '</div></div>' +
      '<div class="kpis im-kpis7">' + k.map(function (x) { return '<div class="kpi' + ((x[0] === 'p1' || x[0] === 'test_gap' || x[0] === 'open') && Number(s[x[0]]) > 0 ? ' ng' : '') + '"><b>' + esc(s[x[0]] || 0) + '</b><span>' + x[1] + '</span></div>'; }).join('') + '</div>' +
      (degraded || e.reason ? '<div class="bt-sample im-engine" role="note"><b>' + (degraded ? '縮退して分析しました' : '分析の方式') + '</b>: ' + esc(e.reason || e.mode) + '</div>' : '') +
      '<div id="im-job"></div>';
  }
  function bindHeader(el, cr, ctx) {
    on(el, '[data-act=analyze]', function (b) { analyze(ctx, b); });
    on(el, '[data-to]', function (b) { transition(ctx, b.dataset.to, b); });
    on(el, '[data-dec]', function (b) { decide(ctx, b.dataset.dec); });
  }
  function transition(ctx, to, btn) {
    var needReason = to === 'rejected';
    var msg = { review: 'レビュー待ちにして承認者に回します。', rejected: 'この変更要求を却下します。', implemented: '実装済みにします。改修後レビューで実際に影響した項目を記録できます。', verified: '検証済みにします。' }[to];
    ui.modal({ title: ui.STATUS[to] + 'にする', submit: ui.STATUS[to] + 'にする', danger: to === 'rejected',
      body: '<p class="im-confirm">' + esc(msg) + '</p>' + (needReason ? '<label class="bt-field">理由（必須）<textarea name="reason" rows="3" class="im-ta" required></textarea></label>' : ''),
      onSubmit: function (f) {
        var reason = needReason ? ui.need(f.reason.value, '理由') : '';
        btn.disabled = true;
        return api.transition(ctx.sid, ctx.cr, to, reason).then(function () { ui.toast(ui.STATUS[to] + 'にしました'); rerender(); }, function (e) { btn.disabled = false; throw e; });
      } });
  }
  function decide(ctx, decision) {
    var ret = decision === 'returned';
    ui.modal({ title: ret ? '差し戻す' : '承認する', submit: ret ? '差し戻す' : '承認する', danger: ret,
      body: '<p class="im-confirm">' + (ret ? '分析担当に差し戻します。直してほしい点を書いてください。' : 'この変更要求の影響分析を承認します。') + '</p>' +
        '<label class="bt-field">理由' + (ret ? '（必須）' : '') + '<textarea name="reason" rows="3" class="im-ta"' + (ret ? ' required' : '') + '></textarea></label>',
      onSubmit: function (f) {
        var reason = ret ? ui.need(f.reason.value, '理由') : f.reason.value.trim();
        return api.approval(ctx.sid, ctx.cr, decision, reason).then(function () { ui.toast(ret ? '差し戻しました' : '承認しました'); rerender(); });
      } });
  }

  /* ---------- 変更内容 ---------- */
  function changeRows(changes) {
    return changes.map(function (c) {
      return '<tr><td><span class="pill p-new">' + esc(CHG[c.kind] || c.kind) + '</span>' + (c.wording_only ? '<small>文言のみ</small>' : '') + '</td><td><code>' + esc(c.code || '') + '</code><small>' + esc(c.location || '') + '</small></td>' +
        '<td>' + (c.before ? '<del>' + esc(c.before) + '</del>' : '') + '</td><td>' + (c.after ? '<ins>' + esc(c.after) + '</ins>' : '') + '</td></tr>';
    });
  }
  function tabChanges(el, cr) {
    var ch = cr.changes || [];
    el.innerHTML = '<div class="bt-card"><dl class="im-meta"><dt>理由</dt><dd>' + esc(cr.reason || '') + '</dd><dt>起票</dt><dd>' + esc(cr.created_by || '') + ' ・ ' + ui.fmtDate(cr.created_at) + '</dd>' +
      '<dt>変更内容</dt><dd>' + (cr.change_text ? esc(cr.change_text) : 'ベースラインの差分（' + esc(cr.base_baseline_name || cr.base_baseline || '') + ' → ' + esc(cr.target_baseline_name || cr.target_baseline || '') + '）') + '</dd><dt>波及の段数</dt><dd>' + esc(cr.depth || '') + ' 段</dd></dl></div>' +
      (ch.length ? table(['種別', '変更箇所', '変更前', '変更後'], changeRows(ch), '変更箇所', 'im-chg')
        : ui.empty({ title: 'まだ変更箇所がありません', desc: '「分析する」を押すと、変更内容から変更箇所を作って影響を探します。' }));
  }

  /* ---------- 影響（一覧＋詳細） ---------- */
  function detailHtml(i, cr, ctx) {
    var e = eff(i), chIds = arr(i.change_ids), chs = (cr.changes || []).filter(function (c) { return chIds.indexOf(c.id) >= 0 || chIds.indexOf(c.code) >= 0; });
    var ev = arr(i.evidence), tests = arr(i.tests), w = ui.can(ctx.role, 'resolve'), o = ui.can(ctx.role, 'override');
    var opt = function (n, cur) { var s = ''; for (var k = 1; k <= n; k++) s += '<option' + (k === Number(cur) ? ' selected' : '') + '>' + k + '</option>'; return s; };
    return '<div class="im-dhead">' + ui.priBadge(e.P) + '<b><code>' + esc(i.item_code) + '</code></b><span class="bt-mut">' + esc(i.document_name || '') + ' ' + esc(i.section || i.location || '') + '</span>' +
      '<span class="pill ' + (i.state === 'open' ? 'p-warn' : 'p-pass') + '">' + esc(RES[i.state] || i.state) + '</span><span class="pill p-new">' + (i.method === 'llm' ? 'LLM 判定' : '規則で判定') + '</span></div>' +
      '<div class="im-side2"><div><h4>変更箇所（変更前 → 変更後）</h4>' + (chs.length ? chs.map(function (c) {
        return '<div class="im-chgbox"><code>' + esc(c.code || '') + '</code> ' + esc(c.location || '') + '<p>' + (c.before ? '<del>' + esc(c.before) + '</del>' : '') + '</p><p>' + (c.after ? '<ins>' + esc(c.after) + '</ins>' : '') + '</p></div>'; }).join('') : '<p class="bt-hint">対応する変更箇所がありません。</p>') +
      '</div><div><h4>影響した項目の本文</h4><div class="im-chgbox"><p>' + esc(i.text || '') + '</p></div></div></div>' +
      '<h4>根拠</h4>' + (ev.length ? '<ul class="im-evi">' + ev.map(function (x) { return '<li><span class="pill p-new">' + esc(EVI[x.type] || x.type) + '</span> ' + esc(x.detail || '') + (x.score != null ? ' <small>' + esc(Number(x.score).toFixed(2)) + '</small>' : '') + '</li>'; }).join('') + '</ul>' : '<p class="bt-hint">根拠の記録がありません。</p>') +
      '<h4>リスク値</h4><p class="im-formula">影響度 I=' + esc(e.I) + '（' + esc(i.impact_reason || '') + '）× 発生可能性 L=' + esc(e.L) + '（' + esc(i.likelihood_reason || '') + '）＝ R=' + esc(e.R) + ' → ' + (e.P ? 'P' + esc(e.P) : '—') + '</p>' +
      (i.override_reason ? '<p class="bt-hint">修正済み: ' + esc(i.override_reason) + '（' + esc(i.override_by || '') + ' ・ ' + ui.fmtDate(i.override_at) + '）</p>' : '') +
      '<h4>確かめるテスト</h4>' + (tests.length ? '<p>' + tests.map(function (t) { return '<code>' + esc(t) + '</code>'; }).join(' ') + '</p>' : '<p class="im-ng"><b>テストの抜け</b>: つながったテストケースがありません。</p>') +
      (i.test_idea ? '<p class="bt-hint">観点: ' + esc(i.test_idea) + '</p>' : '') +
      (i.resolve_reason ? '<p class="bt-hint">解消: ' + esc(RES[i.state] || '') + ' ・ ' + esc(i.resolve_reason) + '（' + esc(i.resolved_by || '') + ' ・ ' + ui.fmtDate(i.resolved_at) + '）</p>' : '') +
      (w ? '<form class="im-subform" data-form="resolve"><h4>解消する</h4><fieldset class="im-radios"><legend class="visually-hidden">判断</legend><label><input type="radio" name="state" value="required"' + (i.state === 'required' ? ' checked' : '') + '> 対応要</label>' +
        '<label><input type="radio" name="state" value="not_required"' + (i.state === 'not_required' ? ' checked' : '') + '> 対応不要</label></fieldset><label class="bt-field">理由（必須）<textarea name="reason" rows="2" class="im-ta" required></textarea></label>' +
        '<div class="bt-actions"><span class="sp"></span><button type="submit" class="btn-primary">解消を記録</button></div></form>' : '') +
      (o ? '<form class="im-subform" data-form="override"><h4>影響度・発生可能性を直す</h4><div class="im-row"><label class="bt-field">影響度 I<select name="lv">' + opt(4, e.I) + '</select></label><label class="bt-field">発生可能性 L<select name="lk">' + opt(3, e.L) + '</select></label></div>' +
        '<label class="bt-field">理由（必須）<textarea name="reason" rows="2" class="im-ta" required></textarea></label><div class="bt-actions"><span class="sp"></span><button type="submit" class="btn-outline-sm">直して再計算</button></div></form>' : '');
  }
  function showDetail(panel, impact, cr, ctx) {
    panel.innerHTML = detailHtml(impact, cr, ctx);
    var submit = function (f, p, msg) {
      var btn = $('[type=submit]', f); btn.disabled = true;
      p.then(function () { ui.toast(msg); pendingSelect = impact.id; rerender(); }, function (e) { btn.disabled = false; ui.banner(e.message); });
    };
    var rf = $('[data-form=resolve]', panel), of = $('[data-form=override]', panel);
    if (rf) rf.addEventListener('submit', function (ev) {
      ev.preventDefault();
      if (!rf.state.value) { ui.banner('「対応要」か「対応不要」を選んでください。'); return; }
      if (!rf.reason.value.trim()) { ui.banner('解消の理由を入力してください。'); return; }
      submit(rf, api.resolve(impact.id, rf.state.value, rf.reason.value.trim()), '解消を記録しました');
    });
    if (of) of.addEventListener('submit', function (ev) {
      ev.preventDefault();
      if (!of.reason.value.trim()) { ui.banner('直す理由を入力してください。'); return; }
      submit(of, api.override(impact.id, Number(of.lv.value), Number(of.lk.value), of.reason.value.trim()), '値を直して再計算しました');
    });
  }
  function tabImpacts(el, cr, ctx) {
    var f = { priority: '', state: '' };
    var chips = function (key, opts) { return '<div class="fchips" role="group" aria-label="' + (key === 'priority' ? '優先度' : '状態') + 'で絞り込む">' + opts.map(function (o) {
      return '<button type="button" class="fchip' + (o[0] === '' ? ' on' : '') + '" aria-pressed="' + (o[0] === '') + '" data-f="' + key + '" data-v="' + o[0] + '">' + o[1] + '</button>'; }).join('') + '</div>'; };
    el.innerHTML = '<div class="im-filters">' + chips('priority', [['', 'すべて'], ['1', 'P1'], ['2', 'P2'], ['3', 'P3']]) + chips('state', [['', 'すべて'], ['open', '要確認'], ['required', '対応要'], ['not_required', '対応不要']]) + '</div>' +
      '<div class="im-split"><div id="im-ilist" class="im-ilist"></div><aside id="im-idetail" class="bt-card im-detail" aria-label="影響の詳細"><p class="bt-hint">左の一覧から影響を選ぶと、根拠とリスクの式を表示します。</p></aside></div>';
    var list = $('#im-ilist', el), panel = $('#im-idetail', el);
    var load = function () {
      ui.loading(list);
      api.impacts(ctx.sid, ctx.cr, f).then(function (d) {
        var rows = api.list(d, 'impacts');
        if (!rows.length) { list.innerHTML = ui.empty({ title: f.priority || f.state ? '条件に合う影響はありません' : 'まだ影響がありません', desc: '「分析する」を押すと影響を表示します。' }); return; }
        list.innerHTML = table(['優先度', '項目', 'I', '状態', 'テスト'], rows.map(function (i) {
          var e = eff(i), t = arr(i.tests);
          return '<tr class="im-irow" data-id="' + esc(i.id) + '" tabindex="0" aria-label="' + esc(i.item_code) + ' の詳細を開く"><td>' + ui.priBadge(e.P) + '</td><td><code>' + esc(i.item_code) + '</code><small>' + esc(String(i.text || '').slice(0, 40)) + '</small></td>' +
            '<td class="num">' + esc(e.I) + '</td><td>' + esc(RES[i.state] || i.state) + '</td><td>' + (t.length ? t.length + ' 件' : '<span class="im-ng">抜け</span>') + '</td></tr>'; }), '影響の一覧');
        var pick = function (tr) {
          $$('.im-irow', list).forEach(function (x) { x.classList.toggle('on', x === tr); });
          var row = rows.filter(function (r) { return String(r.id) === tr.dataset.id; })[0];
          showDetail(panel, row, cr, ctx);
          api.impact(row.id).then(function (d) { if (tr.classList.contains('on')) showDetail(panel, Object.assign({}, row, api.obj(d, 'impact')), cr, ctx); }, function () { /* 一覧の値で表示を続ける */ });
        };
        $$('.im-irow', list).forEach(function (tr) {
          tr.addEventListener('click', function () { pick(tr); });
          tr.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(tr); } });
        });
        var want = pendingSelect && $('.im-irow[data-id="' + CSS.escape(String(pendingSelect)) + '"]', list);
        pendingSelect = null;
        pick(want || $('.im-irow', list));
      }, function (e) { ui.failed(list, e, load); });
    };
    on(el, '[data-f]', function (b) {
      f[b.dataset.f] = b.dataset.v;
      $$('[data-f=' + b.dataset.f + ']', el).forEach(function (x) { x.classList.toggle('on', x === b); x.setAttribute('aria-pressed', String(x === b)); });
      load();
    });
    load();
  }

  /* ---------- 関係図・マトリクス・テスト ---------- */
  function tabGraph(el, cr, ctx) {
    el.innerHTML = '<div class="bt-card im-graph" id="im-graph"></div><aside class="bt-card im-detail" id="im-gdetail" aria-label="選んだ点の詳細"><p class="bt-hint">点を押すと詳細を表示します。</p></aside>';
    var box = $('#im-graph', el), panel = $('#im-gdetail', el);
    ui.loading(box);
    api.graph(ctx.sid, ctx.cr).then(function (d) {
      IM.graph.render(box, d, function (n) {
        if (n.kind === 'change') { panel.innerHTML = table(['種別', '変更箇所', '変更前', '変更後'], changeRows((cr.changes || []).filter(function (c) { return c.id === n.change_id || c.id === n.id || c.code === n.code; })), '変更箇所'); return; }
        ui.loading(panel);
        api.impact(n.impact_id || n.id).then(function (r) { showDetail(panel, api.obj(r, 'impact'), cr, ctx); }, function (e) { ui.failed(panel, e); });
      });
    }, function (e) { ui.failed(box, e, rerender); });
  }
  function withImpacts(el, fn) {
    ui.loading(el);
    var ctx = withImpacts.ctx;
    api.impacts(ctx.sid, ctx.cr, {}).then(function (d) { fn(api.list(d, 'impacts')); }, function (e) { ui.failed(el, e, rerender); });
  }
  function tabMatrix(el, cr) {
    withImpacts(el, function (rows) {
      var ch = cr.changes || [];
      if (!rows.length || !ch.length) { el.innerHTML = ui.empty({ title: 'マトリクスに出す影響がありません', desc: '分析すると、変更箇所 × 影響した項目の対応を表示します。' }); return; }
      el.innerHTML = table(['影響した項目'].concat(ch.map(function (c) { return '<code>' + esc(c.code || c.id) + '</code>'; })), rows.map(function (i) {
        var ids = arr(i.change_ids);
        return '<tr><th scope="row">' + ui.priBadge(eff(i).P) + ' <code>' + esc(i.item_code) + '</code></th>' + ch.map(function (c) { return '<td class="im-mx">' + (ids.indexOf(c.id) >= 0 || ids.indexOf(c.code) >= 0 ? '<span aria-label="影響あり">●</span>' : '') + '</td>'; }).join('') + '</tr>'; }), '変更箇所 × 影響した項目', 'im-matrix');
    });
  }
  function tabTests(el) {
    withImpacts(el, function (rows) {
      if (!rows.length) { el.innerHTML = ui.empty({ title: '確かめるテストはまだありません', desc: '分析すると、影響ごとに既存テストの選定か新しいテストの観点を表示します。' }); return; }
      var gap = rows.filter(function (i) { return !arr(i.tests).length; }).length;
      el.innerHTML = (gap ? '<div class="bt-banner im-gapnote" role="note">テストの抜けが ' + gap + ' 件あります。観点を見て新しいテストを作ってください。</div>' : '') +
        table(['優先度', '影響した項目', '確かめるテスト', 'テストの観点'], rows.map(function (i) {
          var t = arr(i.tests);
          return '<tr class="' + (t.length ? '' : 'im-gaprow') + '"><td>' + ui.priBadge(eff(i).P) + '</td><td><code>' + esc(i.item_code) + '</code><small>' + esc(String(i.text || '').slice(0, 50)) + '</small></td>' +
            '<td>' + (t.length ? t.map(function (x) { return '<code>' + esc(x) + '</code>'; }).join(' ') : '<b class="im-ng">テストの抜け</b>') + '</td><td>' + esc(i.test_idea || '') + '</td></tr>'; }), '影響 × 確かめるテスト');
    });
  }

  /* ---------- 承認・改修後レビュー ---------- */
  function tabApproval(el, cr, ctx) {
    var hist = cr.approvals || [];
    var canA = ui.can(ctx.role, 'approve') && cr.status === 'review';
    el.innerHTML = (canA ? '<div class="bt-card"><h3>判断</h3><p class="bt-hint">起票者・解消者本人は承認できません。</p><div class="bt-actions"><button type="button" class="btn-primary" data-dec="approved">承認する</button><button type="button" class="btn-outline-sm im-btn-danger" data-dec="returned">差し戻す</button></div></div>'
      : '<p class="bt-hint">' + (cr.status === 'review' ? '承認・差し戻しは承認者の役割が必要です。' : 'レビュー待ちになると承認・差し戻しができます。') + '</p>') +
      '<h3 class="im-h3">承認の履歴</h3>' + (hist.length ? table(['日時', '判断', '理由', '担当'], hist.map(function (h) {
        return '<tr><td>' + ui.fmtDate(h.at) + '</td><td>' + (h.decision === 'approved' ? '<span class="pill p-pass">承認</span>' : '<span class="pill p-fail">差し戻し</span>') + '</td><td>' + esc(h.reason || '') + '</td><td>' + esc(h.actor || '') + '</td></tr>'; }), '承認の履歴')
        : '<p class="bt-hint">まだ承認の記録はありません。</p>');
    on(el, '[data-dec]', function (b) { decide(ctx, b.dataset.dec); });
  }
  function tabReview(el, cr, ctx) {
    var ready = cr.status === 'implemented' || cr.status === 'verified', w = ui.can(ctx.role, 'actuals') && ready;
    el.innerHTML = (ready ? '' : '<p class="bt-hint">実装済みになると、実際に不具合や修正が出た項目を記録できます。</p>') +
      (w ? '<form class="bt-card im-row" id="im-actf"><label class="bt-field">項目 ID<input name="item_code" required maxlength="40" placeholder="例: SCR-0007"></label><label class="bt-field im-grow">内容<input name="note" maxlength="500"></label><button type="submit" class="btn-primary">記録する</button></form>' : '') +
      '<div id="im-rvsum"></div><div id="im-acts"></div>';
    if (w) $('#im-actf', el).addEventListener('submit', function (e) {
      e.preventDefault(); var f = e.target, code = f.item_code.value.trim();
      if (!code) { ui.banner('項目 ID を入力してください。'); return; }
      var b = $('[type=submit]', f); b.disabled = true;
      api.addActual(ctx.sid, ctx.cr, { item_code: code, note: f.note.value.trim() }).then(function () { ui.toast('記録しました'); rerender(); }, function (er) { b.disabled = false; ui.banner(er.message); });
    });
    var sum = $('#im-rvsum', el), box = $('#im-acts', el);
    if (!ready) return;
    ui.loading(sum);
    api.review(ctx.sid, ctx.cr).then(function (r) {
      var missed = r.missed || [];
      sum.innerHTML = '<div class="kpis im-kpis4"><div class="kpi"><b>' + esc(r.hit || 0) + '</b><span>予測と一致</span></div><div class="kpi' + (missed.length ? ' ng' : '') + '"><b>' + esc(missed.length) + '</b><span>見逃し</span></div>' +
        '<div class="kpi"><b>' + esc(r.false_alarm || 0) + '</b><span>空振り</span></div><div class="kpi"><b>' + (r.recall == null ? '未計測' : esc(Math.round(r.recall * 100)) + '%') + '</b><span>再現率</span></div></div>' +
        (missed.length ? '<p class="im-ng"><b>見逃し</b>: ' + missed.map(function (m) { return '<code>' + esc(m.item_code || m) + '</code>'; }).join(' ') + '</p>' : '');
    }, function (e) { ui.failed(sum, e); });
    api.actuals(ctx.sid, ctx.cr).then(function (d) {
      var rows = api.list(d, 'actuals');
      box.innerHTML = rows.length ? table(['項目', '内容', '記録'], rows.map(function (a) { return '<tr><td><code>' + esc(a.item_code) + '</code></td><td>' + esc(a.note || '') + '</td><td>' + esc(a.recorded_by || '') + ' ・ ' + ui.fmtDate(a.recorded_at) + '</td></tr>'; }), '実際に影響した項目') : '<p class="bt-hint">まだ記録がありません。</p>';
    }, function (e) { ui.failed(box, e); });
  }

  var TABS = { changes: tabChanges, impacts: tabImpacts, graph: tabGraph, matrix: tabMatrix, tests: tabTests, approval: tabApproval, review: tabReview };
  function render(root, ctx) {
    var tab = TABS[ctx.tab] ? ctx.tab : 'changes';
    ui.setTitle(ctx.system.name + ' / ' + ctx.cr, TITLE[tab]);
    ui.loading(root);
    api.cr(ctx.sid, ctx.cr).then(function (d) {
      var cr = Object.assign({ code: ctx.cr }, api.obj(d, 'cr'));
      root.innerHTML = '<div class="im-view">' + header(cr, ctx) + '<div id="im-crbody"></div></div>';
      bindHeader(root, cr, ctx);
      if (lastFail && lastFail.code === ctx.cr) {
        $('#im-job', root).innerHTML = '<div class="im-state im-state-ng" role="alert"><b>分析に失敗しました' + (lastFail.stage ? '（' + esc(lastFail.stage) + '）' : '') + '</b><p>' + esc(lastFail.message) + '</p></div>';
      }
      var running = cr.job && TERMINAL.indexOf(cr.job.status) < 0 ? cr.job : null;
      if (job && job.code === ctx.cr) drawJob({ status: 'running', progress: 0 }, ui.can(ctx.role, 'analyze'));
      else if (running && running.id) startPoll(ctx, running.id, ui.can(ctx.role, 'analyze'));
      withImpacts.ctx = ctx;
      TABS[tab]($('#im-crbody', root), cr, ctx);
    }, function (e) { ui.failed(root, e, rerender); });
  }
  IM.cr = { render: render, leave: leave };
})();
