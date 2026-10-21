/* Document Assurance ビュー（System06 /docverify に追加）。既存 DV には触れず、DV.state.review を読むだけ。 */
(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var esc = function (v) { return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  var S = { data: {}, tab: 'home', filter: '', busy: false, error: '', lastFocus: null, ifilter: {}, drawerFocus: null, rw: {} };
  window.DAPanels = window.DAPanels || {};
  var PANEL_TABS = ['diff', 'review'];
  var STATE = { READY: ['✔', '準備完了'], CONDITIONALLY_READY: ['▲', '条件付きで準備完了'], BLOCKED: ['✖', '進められない'], REVIEWABLE: ['●', 'レビュー可能'], DRAFT: ['○', '下書き（評価不足）'] };
  var SEV = { critical: ['⛔', '致命的'], high: ['▲', '高'], medium: ['●', '中'], low: ['○', '低'], info: ['i', '情報'] };
  var SRC = { deterministic: '規則', ai: 'AI', hybrid: '規則＋AI', human: '人' };
  var SCORES = [['Overall', '総合'], ['Clarity', '明確さ'], ['Completeness', '網羅性'], ['Consistency', '一貫性'], ['Testability', 'テスト可能性'], ['Traceability', '追跡可能性']];
  var TEST = { CAN_TEST: ['✔', 'テストできる'], PARTIALLY_TESTABLE: ['▲', '一部のみ'], NOT_TESTABLE: ['✖', 'テスト不可'], UNKNOWN: ['?', '判定不能'] };
  var KIND = { functional: '機能', nfr: '非機能', business_rule: '業務ルール', security_rule: 'セキュリティ', constraint: '制約' };
  var STATUS = { CANDIDATE: '候補', CONFIRMED: '確定', REJECTED: '却下', UNKNOWN: '未確認', UNRESOLVED: '未解決', ACCEPTED: '採用済み', RESOLVED: '解決済み', DECIDED: '判断済み', WAIVED: '免除（waiver）中' };
  var PROV = { OBSERVED: '原文に記載', DERIVED: '原文から導出', INFERRED: '推測（事実ではない）' };
  var FIELDS = [['actor', '主体'], ['trigger', '契機'], ['condition', '条件'], ['action', '動作'], ['expected_result', '期待結果'], ['precondition', '前提'], ['object', '対象'], ['constraint', '制約']];

  function rid() { var r = window.DV && window.DV.state && window.DV.state.review; return r && r.id; }
  function url(p) { return '/api/docassure/inspections/' + encodeURIComponent(rid()) + '/' + p; }
  function conf(c) { var n = Number(c) || 0; return (n >= 0.75 ? '高' : n >= 0.4 ? '中' : '低'); }
  function confFull(c) { return '関連度: ' + conf(c) + '（詳細 ' + (Number(c) || 0).toFixed(2) + '）'; }

  function wrap(f) {
    return f.then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, status: r.status, body: b }; });
    }).catch(function () { return { ok: false, status: 0, body: {} }; });
  }
  function get(p) { return wrap(fetch(url(p), { headers: { Accept: 'application/json' } })); }
  function post(p, b) { return wrap(fetch(url(p), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b == null ? {} : b) })); }
  function ctx() { return { iid: rid(), url: url, data: S.data, esc: esc, get: get, post: post }; }

  function load() {
    if (!rid()) { render(); return Promise.resolve(); }
    S.busy = true; S.error = ''; render();
    var names = ['requirements', 'issues', 'conflicts', 'scores', 'trace'];
    return Promise.all(names.map(get)).then(function (rs) {
      S.data = { trace: null };
      rs.forEach(function (r, i) { S.data[names[i]] = r; });
      S.busy = false; render();
    });
  }

  function analyze() {
    if (!rid() || S.busy) return;
    S.busy = true; S.error = ''; render();
    fetch(url('analyze'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (b) {
        if (!r.ok) { S.error = (b.error || '分析できませんでした。') + ' 文書を取り込んでから、もう一度「分析を実行」を押してください。'; S.busy = false; render(); return; }
        S.full = b; return load();
      });
    }).catch(function () { S.error = 'サーバに接続できませんでした。少し待ってから「分析を実行」を押し直してください。'; S.busy = false; render(); });
  }

  function body(k) { var x = S.data[k], b = x && x.ok ? x.body : null; return k === 'trace' && b && b.trace ? b.trace : b; }
  function notRun(k) { var x = S.data[k]; return !x || x.status === 404 || x.status === 0; }

  function scoreCard(key, label, s) {
    if (!s) return '<button type="button" class="da-score da-ne" data-score="' + key + '"><span class="da-sl">' + label + '</span><span class="da-sv">未実行</span><span class="da-sc">分析を実行すると表示されます</span></button>';
    var covPct = Math.round((Number(s.coverage) || 0) * 100);
    if (s.value == null) {
      return '<button type="button" class="da-score da-ne" data-score="' + key + '" aria-label="' + label + ' 評価不能。根拠を見る"><span class="da-sl">' + label + '</span><span class="da-sv">― 評価不能</span><span class="da-sc">評価できた範囲 ' + covPct + '%</span></button>';
    }
    return '<button type="button" class="da-score" data-score="' + key + '" aria-label="' + label + ' ' + Math.round(s.value) + '点。根拠を見る"><span class="da-sl">' + label + '</span><span class="da-sv">' + Math.round(s.value) + '<small>/100</small></span><span class="da-sc">評価できた範囲 ' + covPct + '%</span></button>';
  }

  function homeHtml() {
    var req = body('requirements'), iss = body('issues'), cf = body('conflicts'), sc = body('scores');
    var rd = (req && req.readiness) || (sc && sc.readiness) || null;
    var mode = (req && req.mode) || (sc && sc.mode);
    var h = '';
    if (!rd) {
      h += '<section class="da-card"><h3 class="da-h">準備状態</h3><p class="da-mut">まだ分析していません。「分析を実行」を押すと、文書が次の工程へ進める状態かを判定します。</p></section>';
    } else {
      var st = STATE[rd.state] || ['?', rd.state];
      h += '<section class="da-card da-state da-st-' + esc(rd.state) + '"><h3 class="da-h">準備状態</h3><p class="da-big"><span aria-hidden="true">' + st[0] + '</span> ' + esc(st[1]) + '</p>'
        + '<p class="da-why"><b>なぜこの状態か</b></p><ul class="da-list">' + (rd.reasons || []).map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul></section>';
    }
    if (mode === 'DETERMINISTIC_ONLY') h += '<p class="da-note">ⓘ AI レビューは未実行です（決定論の分析のみ）。AI の観点は含まれていません。</p>';
    var scores = (sc && sc.scores) || {};
    h += '<section class="da-card"><h3 class="da-h">品質スコア</h3><p class="da-mut">スコアを押すと根拠を見られます。評価できなかった範囲は点数にせず「評価不能」と表示します。</p><div class="da-scores">'
      + SCORES.map(function (p) { return scoreCard(p[0], p[1], sc ? scores[p[0]] : null); }).join('') + '</div></section>';
    var f = (iss && iss.findings) || [], fail = f.filter(function (x) { return x.result === 'FAIL' || !x.result; });
    var cnt = function (sev) { return fail.filter(function (x) { return x.severity === sev; }).length; };
    var tr = body('trace'), orph = tr && tr.graph && tr.graph.orphans ? tr.graph.orphans.length : null;
    h += '<section class="da-card"><h3 class="da-h">件数</h3><dl class="da-counts">'
      + '<div><dt>⛔ 致命的な指摘</dt><dd>' + (iss ? cnt('critical') : '―') + '</dd></div>'
      + '<div><dt>▲ 高の指摘</dt><dd>' + (iss ? cnt('high') : '―') + '</dd></div>'
      + '<div><dt>矛盾</dt><dd>' + (cf ? (cf.conflicts || []).length : '―') + '</dd></div>'
      + '<div><dt>確認が必要な質問</dt><dd>' + (cf ? (cf.conflicts || []).filter(function (c) { return c.status === 'UNRESOLVED'; }).length : '―') + '</dd></div>'
      + '<div><dt>つながりの無い要件</dt><dd>' + (orph == null ? '未実行' : orph) + '</dd></div></dl></section>';
    return h;
  }

  function reqHtml() {
    var rq = body('requirements');
    if (!rq) return empty('要件', notRun('requirements'));
    var list = rq.requirements || [], f = (body('issues') || {}).findings || [];
    var tests = rq.testability || (S.full && S.full.testability) || {};
    var cfIds = {}; ((body('conflicts') || {}).conflicts || []).forEach(function (c) { (c.evidence || []).forEach(function (e) { cfIds[e.requirement_id] = 1; }); });
    var inferred = function (u) { return Object.keys(u.fields || {}).some(function (k) { return u.fields[k] && u.fields[k].provenance === 'INFERRED'; }); };
    var rows = list.filter(function (u) {
      var t = (tests[u.document_id + ':' + u.requirement_id] || {}).verdict;
      if (S.filter === 'nt') return t === 'NOT_TESTABLE';
      if (S.filter === 'cf') return !!cfIds[u.requirement_id];
      if (S.filter === 'ai') return inferred(u);
      return true;
    });
    var chips = [['', 'すべて'], ['nt', 'テスト不可'], ['cf', '矛盾あり'], ['ai', 'AI 推論を含む']].map(function (c) {
      return '<button type="button" class="da-chip" aria-pressed="' + (S.filter === c[0]) + '" data-filter="' + c[0] + '">' + c[1] + '</button>'; }).join('');
    if (!list.length) return empty('要件', false);
    return '<div class="da-chips" role="group" aria-label="絞り込み">' + chips + '</div>'
      + (S.full ? '' : '<p class="da-mut"></p>')
      + '<div class="da-tscroll"><table class="da-table"><thead><tr><th>ID</th><th>要件</th><th>種別</th><th>テスト可能性</th><th>指摘数</th></tr></thead><tbody>'
      + (rows.length ? rows.map(function (u) {
        var t = (tests[u.document_id + ':' + u.requirement_id] || {}).verdict, tt = t ? (TEST[t] || ['?', t]) : ['―', '未判定'];
        var n = f.filter(function (x) { return x.requirement_id === u.requirement_id && x.result !== 'PASS'; }).length;
        return '<tr class="da-reqrow" tabindex="0" role="button" aria-label="要件 ' + esc(u.requirement_id) + ' の詳細を開く" data-req="' + esc(u.document_id + ':' + u.requirement_id) + '"><td>' + esc(u.requirement_id) + '</td><td>' + esc(u.raw_text) + '</td><td>' + esc(KIND[u.kind] || u.kind) + '</td><td><span aria-hidden="true">' + tt[0] + '</span> ' + tt[1] + '</td><td>' + n + '</td></tr>';
      }).join('') : '<tr><td colspan="5" class="da-mut">この条件に当てはまる要件はありません。「すべて」に戻してください。</td></tr>')
      + '</tbody></table></div>';
  }

  function ifOpts(list, key, labelFn) {
    var seen = {}; list.forEach(function (x) { var v = key(x); if (v) seen[v] = 1; });
    return Object.keys(seen).sort().map(function (v) { return '<option value="' + esc(v) + '"' + (S.ifilter[labelFn] === v ? ' selected' : '') + '>' + esc(v) + '</option>'; }).join('');
  }
  function fDoc(x) { return (x.location && x.location.document_id) || x.document_id || ''; }
  function fKind(x) { return x.category || x.kind || x.type || ''; }
  function issuesHtml() {
    var b = body('issues');
    if (!b) return empty('指摘', notRun('issues'));
    var all = (b.findings || []).filter(function (x) { return x.result !== 'PASS'; });
    if (!all.length) return '<p class="da-mut">指摘はありません。ただし、評価できなかった範囲があるときは品質スコアの「評価不能」を確認してください。</p>';
    var F = S.ifilter;
    var f = all.filter(function (x) {
      return (!F.sev || x.severity === F.sev) && (!F.kind || fKind(x) === F.kind) && (!F.doc || fDoc(x) === F.doc)
        && (!F.req || x.requirement_id === F.req) && (!F.status || (x.waiver_expired ? 'EXPIRED' : x.status) === F.status) && (!F.src || x.source === F.src);
    });
    var sel = function (k, label, opts) { return '<label class="da-fl">' + label + ' <select data-if="' + k + '"><option value="">すべて</option>' + opts + '</select></label>'; };
    var sevO = Object.keys(SEV).map(function (k) { return '<option value="' + k + '"' + (F.sev === k ? ' selected' : '') + '>' + SEV[k][1] + '</option>'; }).join('');
    var stO = Object.keys(STATUS).concat(['EXPIRED']).map(function (k) { return '<option value="' + k + '"' + (F.status === k ? ' selected' : '') + '>' + (k === 'EXPIRED' ? '免除の期限切れ' : STATUS[k]) + '</option>'; }).join('');
    var srcO = Object.keys(SRC).map(function (k) { return '<option value="' + k + '"' + (F.src === k ? ' selected' : '') + '>' + SRC[k] + '</option>'; }).join('');
    var bar = '<div class="da-filters" role="group" aria-label="指摘の絞り込み">'
      + sel('sev', '重大度', sevO) + sel('kind', '種別', ifOpts(all, fKind, 'kind')) + sel('doc', '文書', ifOpts(all, fDoc, 'doc'))
      + sel('req', '要件', ifOpts(all, function (x) { return x.requirement_id; }, 'req')) + sel('status', '状態', stO) + sel('src', '検出元', srcO) + '</div>';
    return bar + '<p class="da-mut" role="status">' + f.length + ' / ' + all.length + ' 件を表示</p>'
      + (f.length ? '<div class="da-tscroll"><table class="da-table"><thead><tr><th>重大度</th><th>規則</th><th>要件</th><th>根拠</th><th>状態</th><th>判断</th></tr></thead><tbody>'
      + f.map(function (x) {
        var sv = SEV[x.severity] || ['?', x.severity], loc = x.location || {}, fid = esc(x.finding_id || '');
        var st = x.waiver_expired ? '<b>期限切れ。再度確認が必要</b>' : (STATUS[x.status] || esc(x.status))
          + (x.status === 'WAIVED' && x.waiver_expiry ? '<br><span class="da-mut">期限 ' + esc(String(x.waiver_expiry).slice(0, 10)) + '</span>' : '');
        var act = fid ? '<label class="da-reason">理由<textarea rows="2" data-reason="' + fid + '"></textarea></label>'
          + '<label class="da-reason">waiver の期限<input type="date" data-expiry="' + fid + '"></label>'
          + '<div class="da-actions"><button type="button" class="btn-outline-sm" data-fdecide="' + fid + '" data-d="accepted">採用</button><button type="button" class="btn-outline-sm" data-fdecide="' + fid + '" data-d="rejected">却下</button><button type="button" class="btn-outline-sm" data-fdecide="' + fid + '" data-d="waived">waiver</button></div>' : '<span class="da-mut">判断できません</span>';
        return '<tr><td><span aria-hidden="true">' + sv[0] + '</span> ' + sv[1] + '</td><td>' + esc(x.title || x.rule_id) + '<br><span class="da-badge da-b-' + esc(x.source) + '">' + (SRC[x.source] || esc(x.source)) + '</span> <span class="da-mut" title="' + esc(confFull(x.confidence)) + '">関連度: ' + conf(x.confidence) + '</span></td>'
          + '<td>' + esc(x.requirement_id || '―') + '</td><td>' + esc(loc.snippet || x.reason || '') + '<br><span class="da-mut">' + esc(fDoc(x)) + ' ' + esc(loc.section || '') + (loc.line_start ? ' ・ ' + esc(loc.line_start) + ' 行目' : '') + '</span></td><td>' + st + '</td><td>' + act + '</td></tr>';
      }).join('') + '</tbody></table></div>' : '<p class="da-mut">この条件に当てはまる指摘はありません。絞り込みを「すべて」に戻してください。</p>');
  }

  function conflictsHtml() {
    var b = body('conflicts');
    if (!b) return empty('矛盾', notRun('conflicts'));
    var list = b.conflicts || [];
    if (!list.length) return '<p class="da-mut">矛盾は見つかっていません。見つからないことは、矛盾が無いことの証明ではありません。</p>';
    return list.map(function (c) {
      var ev = c.evidence || [];
      var col = function (e, label) {
        if (!e) return '<div class="da-ev"><b>' + label + '</b><p class="da-mut">対応する記述がありません。</p></div>';
        return '<div class="da-ev"><b>' + label + '</b><p>' + esc(e.quote) + '</p><p class="da-mut">' + esc(e.document_id) + ' ・ ' + esc(e.requirement_id) + (e.location && e.location.line_start ? ' ・ ' + e.location.line_start + ' 行目' : '') + '</p></div>';
      };
      var id = esc(c.conflict_id);
      return '<article class="da-card da-cf"><h3 class="da-h">' + esc(c.topic) + ' <span class="da-badge">' + (STATUS[c.status] || esc(c.status)) + '</span></h3>'
        + '<p class="da-note">⚠ どちらが正しいかは未確定です。人が確かめて決めてください。</p>'
        + '<div class="da-pair">' + col(ev[0], '根拠 A') + col(ev[1], '根拠 B') + '</div>'
        + '<p class="da-mut">' + confFull(c.confidence) + '</p>'
        + '<label class="da-reason">判断の理由（どの記述を正とするか）<textarea rows="2" data-reason="' + id + '"></textarea></label>'
        + '<div class="da-actions"><button type="button" class="btn-outline-sm" data-decide="' + id + '" data-d="conflict_decided">判断を記録する</button><button type="button" class="btn-outline-sm" data-decide="' + id + '" data-d="rejected">矛盾ではない</button></div></article>';
    }).join('');
  }

  function traceHtml() {
    if (window.DAPanels.trace && window.DAPanels.trace.html) return window.DAPanels.trace.html(ctx());
    var t = body('trace');
    if (!t) return '<p class="da-mut">未実行です。つながりの分析がまだ提供されていないか、実行されていません。</p>';
    var g = t.graph || {}, cov = t.coverage;
    return '<section class="da-card"><h3 class="da-h">つながり</h3><p>要素 ' + (g.nodes || []).length + ' 件 ・ つながり ' + (g.edges || []).length + ' 件 ・ つながりの無い要件 ' + (g.orphans || []).length + ' 件</p>'
      + (cov == null ? '' : '<p class="da-mut">カバー率 ' + esc(typeof cov === 'number' ? Math.round(cov * 100) + '%' : JSON.stringify(cov)) + '</p>')
      + ((g.orphans || []).length ? '<ul class="da-list">' + g.orphans.map(function (o) { return '<li>' + esc(typeof o === 'string' ? o : (o.id || o.requirement_id || '')) + '</li>'; }).join('') + '</ul>' : '') + '</section>';
  }

  function empty(what, notRunFlag) {
    return '<p class="da-mut">' + (notRunFlag ? 'まだ分析していません。「分析を実行」を押すと' + what + 'が表示されます。' : what + 'は 0 件です。文書に要件の記述があるか確認してください。') + '</p>';
  }

  var BASE_TABS = [['home', 'ホーム'], ['req', '要件一覧'], ['issues', '指摘一覧'], ['conf', '矛盾'], ['trace', 'Trace']];
  function tabs() {
    var t = BASE_TABS.slice();
    PANEL_TABS.forEach(function (k) { var p = window.DAPanels[k]; if (p) t.push([k, p.label || k]); });
    return t;
  }

  function render() {
    var root = $('#da-root');
    if (!root || root.hidden) return;
    var has = !!rid();
    var inner = '<div class="da-head"><h2 class="da-title">ドキュメント品質保証</h2><div class="da-head-actions">'
      + (rid() && !notRun('scores') ? '<a class="btn-outline-sm" href="' + url('report.md') + '" download>レポート（Markdown）</a><a class="btn-outline-sm" href="' + url('report.csv') + '" download>指摘一覧（CSV）</a>' : '')
      + '<button type="button" class="btn-outline-sm" id="da-run"' + (S.busy || !has ? ' disabled' : '') + '>' + (S.busy ? '実行中…' : '分析を実行') + '</button>'
      + '<button type="button" class="btn-outline-sm" id="da-close">閉じる (Esc)</button></div></div>';
    if (!has) { root.innerHTML = inner + '<p class="da-mut">レビューを開いていません。一覧からレビューを選んでから開いてください。</p>'; return; }
    inner += '<div class="da-tabs" role="tablist" aria-label="品質保証の表示">' + tabs().map(function (t) {
      return '<button type="button" role="tab" class="da-tab" id="da-t-' + t[0] + '" aria-selected="' + (S.tab === t[0]) + '" tabindex="' + (S.tab === t[0] ? 0 : -1) + '" data-tab="' + t[0] + '">' + t[1] + '</button>'; }).join('') + '</div>';
    if (S.error) inner += '<div class="da-err" role="alert">' + esc(S.error) + '</div>';
    if (S.busy) inner += '<p class="da-mut" role="status">分析しています。しばらくお待ちください。</p>';
    var views = { home: homeHtml, req: reqHtml, issues: issuesHtml, conf: conflictsHtml, trace: traceHtml };
    var pn = window.DAPanels[S.tab], isPanel = PANEL_TABS.indexOf(S.tab) >= 0 && pn;
    if (!isPanel && !views[S.tab]) S.tab = 'home';
    inner += '<div class="da-body" role="tabpanel" aria-labelledby="da-t-' + S.tab + '">' + (isPanel ? pn.html(ctx()) : views[S.tab]()) + '</div>';
    var keep = root.querySelector('.da-body') ? root.querySelector('.da-body').scrollTop : 0;
    var focusId = document.activeElement && document.activeElement.id;
    root.innerHTML = inner;
    var nb = root.querySelector('.da-body'); if (nb) nb.scrollTop = keep;
    if (isPanel && pn.bind && nb) pn.bind(nb, ctx());
    else if (S.tab === 'trace' && window.DAPanels.trace && window.DAPanels.trace.bind && nb) window.DAPanels.trace.bind(nb, ctx());
    if (focusId) { var el = document.getElementById(focusId); if (el) el.focus(); }
  }

  function explain(key) {
    var sc = ((body('scores') || {}).scores || {})[key];
    if (!sc) return;
    var label = (SCORES.filter(function (p) { return p[0] === key; })[0] || [0, key])[1];
    var dlg = $('#da-dialog');
    var list = function (a) { return a && a.length ? '<ul class="da-list">' + a.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : '<p class="da-mut">なし</p>'; };
    dlg.innerHTML = '<h3 class="da-h">' + label + ' の根拠</h3>'
      + (sc.value == null ? '<p>評価不能です。点数は付けていません（評価できた範囲 ' + Math.round((sc.coverage || 0) * 100) + '%）。</p>' : '<p>' + Math.round(sc.value) + ' 点（評価できた範囲 ' + Math.round((sc.coverage || 0) * 100) + '%）</p>')
      + '<h4>評価に含めたもの</h4>' + list(sc.included) + '<h4>評価できなかったもの</h4>' + list(sc.not_evaluated) + '<h4>主な減点理由</h4>' + list(sc.explanation)
      + '<div class="da-actions"><button type="button" class="btn-outline-sm" data-dlg-close>閉じる</button></div>';
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute('open', '');
    var b = dlg.querySelector('[data-dlg-close]'); if (b) b.focus();
  }

  function decide(id, d) {
    var ta = document.querySelector('textarea[data-reason="' + id + '"]');
    var reason = ta ? ta.value : '';
    if (!reason || !reason.trim()) { S.error = '理由が空です。理由を入力してからもう一度押してください。'; render(); return; }
    fetch(url('decisions'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision: d, target: id, reason: reason.trim(), expiry: null }) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) {
        S.error = r.ok ? '' : (b.error || '記録できませんでした。') + ' 権限を確認してから、もう一度お試しください。';
        render();
      }); })
      .catch(function () { S.error = '記録できませんでした。接続を確認してから、もう一度お試しください。'; render(); });
  }

  function decideFinding(id, d) {
    var ta = document.querySelector('textarea[data-reason="' + id + '"]');
    var reason = ta ? ta.value : '';
    if (!reason || !reason.trim()) { S.error = '理由が空です。理由を入力してからもう一度押してください。'; render(); return; }
    var expiry = null;
    if (d === 'waived') {
      var ex = document.querySelector('input[data-expiry="' + id + '"]');
      expiry = ex && ex.value ? ex.value : '';
      if (!expiry) { S.error = 'waiver には期限が必要です。期限の日付を入力してからもう一度押してください。'; render(); return; }
    }
    post('decisions', { decision: d, target: id, reason: reason.trim(), expiry: expiry }).then(function (r) {
      S.error = r.ok ? '' : ((r.body && r.body.error) || '記録できませんでした。') + ' 権限を確認してから、もう一度お試しください。';
      return r.ok ? load() : render();
    });
  }

  function fieldVal(f) { if (f && typeof f === 'object') return f.value != null ? f.value : (f.text != null ? f.text : ''); return f == null ? '' : f; }
  function drawerEl() {
    var d = document.getElementById('da-drawer');
    if (!d) {
      d = document.createElement('aside'); d.id = 'da-drawer'; d.className = 'da-drawer'; d.setAttribute('role', 'dialog'); d.setAttribute('aria-label', '要件の詳細'); d.tabIndex = -1; d.hidden = true;
      d.style.cssText = 'position:fixed;top:0;right:0;bottom:0;width:min(480px,100vw);overflow:auto;background:var(--color-surface,#fff);border-left:1px solid var(--color-border,#ccc);padding:16px;z-index:1000;box-shadow:-4px 0 12px rgba(0,0,0,.15)';
      document.body.appendChild(d);
    }
    return d;
  }
  function drawerOpen() { var d = document.getElementById('da-drawer'); return !!(d && !d.hidden); }
  function closeDrawer() {
    var d = document.getElementById('da-drawer'); if (!d || d.hidden) return;
    d.hidden = true;
    if (S.drawerFocus && document.contains(S.drawerFocus) && S.drawerFocus.focus) S.drawerFocus.focus();
    S.drawerFocus = null;
  }
  function drawerBody(u, key) {
    var rq = body('requirements') || {}, tc = (rq.testability || (S.full && S.full.testability) || {})[key] || {};
    var f = ((body('issues') || {}).findings || []).filter(function (x) { return x.requirement_id === u.requirement_id && x.result !== 'PASS'; });
    var loc = u.location || {}, line = u.line_start || loc.line_start;
    var h = '<div class="da-actions"><button type="button" class="btn-outline-sm" data-drawer-close>閉じる (Esc)</button></div>'
      + '<h3 class="da-h">' + esc(u.requirement_id) + '</h3>'
      + '<h4>原文</h4><p>' + esc(u.raw_text || u.snippet || '') + '</p><p class="da-mut">' + esc(u.document_id) + (line ? ' ・ ' + esc(line) + ' 行目' : '') + (u.snippet && u.snippet !== u.raw_text ? '<br>' + esc(u.snippet) : '') + '</p>'
      + '<h4>構造化フィールド</h4><dl class="da-counts">' + FIELDS.map(function (p) {
        var fv = (u.fields || {})[p[0]]; if (fv == null || fv === '') return '';
        var pv = fv && fv.provenance;
        return '<div><dt>' + p[1] + '</dt><dd>' + esc(fieldVal(fv)) + ' <span class="da-badge da-prov-' + esc(pv || 'NONE') + '">' + (pv ? esc(PROV[pv] || pv) : '出所不明') + '</span></dd></div>';
      }).join('') + '</dl>';
    var tt = tc.verdict ? (TEST[tc.verdict] || ['?', tc.verdict]) : null;
    h += '<h4>テスト可能性</h4>' + (tt ? '<p><span aria-hidden="true">' + tt[0] + '</span> ' + esc(tt[1]) + '</p>' : '<p class="da-mut">未判定</p>')
      + ((tc.reasons || []).length ? '<ul class="da-list">' + tc.reasons.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : '')
      + ((tc.missing || []).length ? '<p><b>不足している情報</b></p><ul class="da-list">' + tc.missing.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : '')
      + (tc.rewrite_proposal ? '<p><b>提案（未承認）</b></p><p>' + esc(typeof tc.rewrite_proposal === 'string' ? tc.rewrite_proposal : JSON.stringify(tc.rewrite_proposal)) + '</p>' : '');
    h += '<h4>関連する指摘</h4>' + (f.length ? '<ul class="da-list">' + f.map(function (x) { return '<li>' + esc((SEV[x.severity] || ['', x.severity])[1]) + ' ' + esc(x.title || x.rule_id) + '<br><span class="da-mut">' + esc((x.location && x.location.snippet) || x.reason || '') + '</span></li>'; }).join('') + '</ul>' : '<p class="da-mut">なし</p>');
    h += '<h4>書き換え案</h4><div id="da-rw">' + rwHtml(S.rw[u.requirement_id]) + '</div>';
    return h;
  }
  function rwHtml(r) {
    if (r === undefined) return '<p class="da-mut" role="status">読み込み中…</p>';
    if (!r) return '<p class="da-mut">書き換え案はありません。</p>';
    return '<p class="da-note">提案（未承認）です。採用するかは人が決めます。</p><pre class="da-pre" style="white-space:pre-wrap">' + esc(typeof r === 'string' ? r : (r.proposed_text || r.proposal || r.text || JSON.stringify(r, null, 1))) + '</pre>';
  }
  function openDrawer(key, trigger) {
    var rq = body('requirements'); if (!rq) return;
    var u = (rq.requirements || []).filter(function (x) { return x.document_id + ':' + x.requirement_id === key; })[0]; if (!u) return;
    var d = drawerEl();
    if (d.hidden) S.drawerFocus = trigger;
    d.innerHTML = drawerBody(u, key); d.hidden = false; d.focus();
    var reqId = u.requirement_id;
    if (S.rw[reqId] === undefined) {
      get('rewrite/' + encodeURIComponent(reqId)).then(function (r) {
        S.rw[reqId] = r.ok ? (r.body || null) : null;   // 404 等は無視して「なし」表示
        var box = document.getElementById('da-rw'); if (box && !d.hidden) box.innerHTML = rwHtml(S.rw[reqId]);
      });
    }
  }

  function open() {
    var root = $('#da-root'); if (!root) return;
    S.lastFocus = document.activeElement;
    root.hidden = false; document.body.classList.add('da-open');
    render(); load();
    var h = root.querySelector('#da-close'); if (h) h.focus();
  }
  function close() {
    var root = $('#da-root'); if (!root || root.hidden) return;
    closeDrawer();
    root.hidden = true; document.body.classList.remove('da-open');
    if (S.lastFocus && S.lastFocus.focus) S.lastFocus.focus();
  }

  document.addEventListener('click', function (e) {
    var t = e.target.closest ? e.target : null; if (!t) return;
    var el;
    if ((el = t.closest('#da-open'))) return open();
    if (t.closest('#da-close')) return close();
    if (t.closest('#da-run')) return analyze();
    if ((el = t.closest('[data-tab]'))) { S.tab = el.dataset.tab; render(); var n = document.getElementById('da-t-' + S.tab); if (n) n.focus(); return; }
    if ((el = t.closest('[data-filter]'))) { S.filter = el.dataset.filter; return render(); }
    if ((el = t.closest('[data-score]'))) return explain(el.dataset.score);
    if (t.closest('[data-drawer-close]')) return closeDrawer();
    if ((el = t.closest('[data-fdecide]'))) return decideFinding(el.dataset.fdecide, el.dataset.d);
    if ((el = t.closest('tr[data-req]'))) return openDrawer(el.dataset.req, el);
    if ((el = t.closest('[data-decide]'))) return decide(el.dataset.decide, el.dataset.d);
    if (t.closest('[data-dlg-close]')) { var d = $('#da-dialog'); if (d.close) d.close(); else d.removeAttribute('open'); }
  });
  document.addEventListener('change', function (e) {
    var el = e.target && e.target.closest ? e.target.closest('[data-if]') : null;
    if (!el) return;
    S.ifilter = Object.assign({}, S.ifilter); S.ifilter[el.dataset.if] = el.value;
    var id = el.id || ('da-if-' + el.dataset.if); el.id = id; render();
  });
  document.addEventListener('keydown', function (e) {
    var root = $('#da-root');
    if (e.key === 'Escape' && drawerOpen()) { e.preventDefault(); closeDrawer(); return; }
    if (e.key === 'Enter' && e.target && e.target.matches && e.target.matches('tr[data-req]')) { e.preventDefault(); openDrawer(e.target.dataset.req, e.target); return; }
    if (e.key === 'Escape' && root && !root.hidden) {
      var d = $('#da-dialog'); if (d && d.open) return; // dialog 自身の Esc に任せる
      e.preventDefault(); close(); return;
    }
    if ((e.key === 'ArrowRight' || e.key === 'ArrowLeft') && e.target.matches && e.target.matches('.da-tab')) {
      var TB = tabs(), i = TB.map(function (t) { return t[0]; }).indexOf(S.tab);
      i = (i + (e.key === 'ArrowRight' ? 1 : TB.length - 1)) % TB.length;
      S.tab = TB[i][0]; render(); var n = document.getElementById('da-t-' + S.tab); if (n) n.focus();
    }
  });
  window.DocAssure = { open: open, close: close, reload: load };
})();
