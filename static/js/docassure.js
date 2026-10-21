/* System06 ドキュメント品質保証（DAX 骨格）。問いの順: 大丈夫か → 何が問題か → 何を直すか → 根拠。
   段階表示 L1 判断 / L2 問題 / L3 根拠（details.dax-adv）/ L4 技術詳細（details.dax-adv）。文書由来の文字列は esc() を通す。 */
(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var esc = function (v) { return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  var S = { data: {}, tab: 'overview', chip: '', q: '', cols: {}, selF: null, fsev: '', busy: false, loaded: false, error: '', blocked: null, drawerFocus: null, menuFocus: null, rw: {}, draft: {}, ferr: {}, iid: null, full: null };
  window.DAPanels = window.DAPanels || {};

  /* ---------- 語彙（内部 status は本文に出さず、ここで翻訳する） ---------- */
  var READY = { READY: ['準備完了', 'ready'], CONDITIONALLY_READY: ['条件付き', 'conditional'], REVIEWABLE: ['条件付き', 'conditional'], BLOCKED: ['ブロック', 'blocked'], DRAFT: ['ドラフト', 'draft'] };
  var SEV = { critical: '重大', high: '高', medium: '中', low: '低', info: '情報' };
  var SEV_ORDER = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
  var SRC = { deterministic: '規則', ai: 'AI', hybrid: '規則＋AI', human: '人' };
  var QUAL = [['Clarity', '明確さ'], ['Completeness', '網羅性'], ['Consistency', '一貫性'], ['Testability', 'テスト可能性'], ['Traceability', 'トレーサビリティ']];
  var TEST = { CAN_TEST: 'テストできる', PARTIALLY_TESTABLE: '一部のみ', NOT_TESTABLE: 'テスト不可', UNKNOWN: '判定不能' };
  var KIND = { functional: '機能', nfr: '非機能', business_rule: '業務ルール', security_rule: 'セキュリティ', constraint: '制約' };
  var PROV = { OBSERVED: '原文に記載', DERIVED: '原文から導出', INFERRED: '推測（事実ではない）' };
  var FIELDS = [['actor', '主体'], ['trigger', '契機'], ['condition', '条件'], ['action', '動作'], ['expected_result', '期待結果'], ['precondition', '前提'], ['object', '対象'], ['constraint', '制約']];
  var DONE = ['REJECTED', 'WAIVED', 'RESOLVED', 'DECIDED'];
  var NAV = [['overview', '概要'], ['req', '要件'], ['issues', '指摘'], ['conf', '矛盾'], ['trace', 'トレーサビリティ'], ['diff', '変更'], ['review', 'レビュー']];
  var PANEL_TABS = { trace: 'trace', diff: 'diff', review: 'review' };
  var REQ_CHIPS = [['attention', '要対応'], ['nt', 'テスト不可'], ['cf', '矛盾あり'], ['notest', 'テストなし'], ['changed', '変更あり']];
  var OPT_COLS = [['kind', '種別'], ['doc', '文書'], ['infer', '推測を含む']];

  function fstat(x) {
    if (x.waiver_expired) return ['期限切れ。再度確認が必要', 'decision'];
    if (x.status === 'WAIVED') return ['免除', 'waived'];
    if (DONE.indexOf(x.status) >= 0) return ['解決済み', 'resolved'];
    if (x.status === 'ACCEPTED') return ['未対応', 'open'];
    return ['判断待ち', 'decision'];
  }
  function isOpenF(x) { return DONE.indexOf(x.status) < 0 || x.waiver_expired; }

  /* ---------- API（相対パスのみ。ctx でパネルへ渡す） ---------- */
  function rid() { var r = window.DV && window.DV.state && window.DV.state.review; return r && r.id; }
  function rname() { var r = window.DV && window.DV.state && window.DV.state.review; return r && r.name; }
  function url(p) { return '/api/docassure/inspections/' + encodeURIComponent(rid()) + '/' + p; }
  function wrap(f) {
    return f.then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, status: r.status, body: b }; }); })
      .catch(function () { return { ok: false, status: 0, body: {} }; });
  }
  function get(p) { return wrap(fetch(url(p), { headers: { Accept: 'application/json' } })); }
  function post(p, b) { return wrap(fetch(url(p), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b == null ? {} : b) })); }
  function ctx() { return { iid: rid(), url: url, data: S.data, esc: esc, get: get, post: post }; }
  function toast(m) { if (window.DV && window.DV.toast) window.DV.toast(m); }
  function pct(x) { return Math.round((Number(x) || 0) * 100); }
  function conf(c) { var n = Number(c) || 0; return n >= 0.75 ? '高' : n >= 0.4 ? '中' : '低'; }

  function load() {
    if (!rid()) { S.loaded = false; render(); return Promise.resolve(); }
    S.iid = rid(); S.busy = true; S.error = ''; render();
    var names = ['requirements', 'issues', 'conflicts', 'scores', 'trace', 'diff'];
    return Promise.all(names.map(get)).then(function (rs) {
      S.data = { trace: null };
      rs.forEach(function (r, i) { S.data[names[i]] = r; });
      S.loadFail = rs.slice(0, 4).every(function (r) { return r.status === 0 || r.status >= 500; });
      S.busy = false; S.loaded = true; render();
    });
  }
  function analyze() {
    if (!rid() || S.busy) return;
    S.busy = true; S.error = ''; S.blocked = null; render();
    wrap(fetch(url('analyze'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })).then(function (r) {
      if (!r.ok) {
        S.busy = false;
        if (r.body && r.body.code === 'no_document') S.blocked = { why: '解析する文書が取り込まれていません。', next: 'レビュー一覧で文書を取り込んでから、再解析してください。' };
        else if (r.status === 403) S.blocked = { why: '解析する権限がありません。', next: '管理者に権限を確認してください。' };
        else S.error = '解析できませんでした。少し待ってから再試行してください。';
        return render();
      }
      toast('解析が終わりました。'); S.full = r.body; return load();
    });
  }
  function body(k) { var x = S.data[k], b = x && x.ok ? x.body : null; return k === 'trace' && b && b.trace ? b.trace : b; }
  function notRun(k) { var x = S.data[k]; return !x || x.status === 404 || x.status === 0; }
  function tests() { var rq = body('requirements') || {}; return rq.testability || (S.full && S.full.testability) || {}; }
  function findings() { return ((body('issues') || {}).findings || []).filter(function (x) { return x.result !== 'PASS'; }); }
  function conflicts() { return (body('conflicts') || {}).conflicts || []; }
  function scores() { return (body('scores') || {}).scores || {}; }
  function readiness() { var a = body('requirements'), b = body('scores'); return (a && a.readiness) || (b && b.readiness) || null; }
  function mode() { var a = body('requirements'), b = body('scores'); return (a && a.mode) || (b && b.mode); }

  /* ---------- 状態画面 ---------- */
  function stateBox(kind, title, msg, btn) {
    return '<section class="dax-state dax-state--' + kind + '" role="status"><p class="dax-state__title">' + esc(title) + '</p><p class="dax-state__body">' + msg + '</p>' + (btn || '') + '</section>';
  }
  var RUN_BTN = '<button type="button" class="dax-btn dax-btn--primary" data-act="run">解析を開始</button>';
  var RETRY_BTN = '<button type="button" class="dax-btn dax-btn--primary" data-act="reload">再試行</button>';
  function skeleton() { return '<div class="dax-page" aria-busy="true"><div class="dax-skel"></div><div class="dax-skel"></div><div class="dax-skel"></div></div>'; }
  function failBox() { return stateBox('error', '解析結果を取得できませんでした', 'サーバから結果を受け取れませんでした。少し待ってから再試行してください。', RETRY_BTN); }
  function emptyBox() { return stateBox('empty', 'まだ解析結果がありません', '解析すると、この文書が次工程へ進めるか、何を直すべきかを示します。', RUN_BTN); }

  /* ---------- モデル ---------- */
  function changedIds() {
    var d = body('diff'), ids = {};
    var walk = function (o, depth) {
      if (!o || depth > 4) return;
      if (Array.isArray(o)) return o.forEach(function (x) { walk(x, depth + 1); });
      if (typeof o === 'object') Object.keys(o).forEach(function (k) { if (k === 'requirement_id' && typeof o[k] === 'string') ids[o[k]] = 1; else walk(o[k], depth + 1); });
    };
    walk(d, 0); return ids;
  }
  /* 指摘集合の唯一の算出元: 規則の指摘（FAIL）＋矛盾＋テスト不可の要件。並びは 重大度 → 矛盾 → テスト不可。
     ナビのバッジ・概要の優先 3 件・指摘タブ・要件一覧の指摘列・要件ドロワーの問題欄はすべてここから出す。 */
  var WHY = [[/AMB|曖昧/i, '人によって解釈が割れ、実装とテストがずれます。'], [/TBD|未決/i, '決まるまで設計とテストを確定できません。'], [/REF|参照/i, '根拠をたどれません。'],
    [/^ID|ITEMS|ID-|識別/i, '追跡できません。'], [/NUM|RANGE|数値|範囲/i, '境界のテストが作れません。']];
  function whyOf(it) {
    if (it.kind === 'c') return 'どちらで作るか決まりません。';
    if (it.kind === 't') return '合否を判定できません。';
    var k = (it.raw.rule_id || '') + ' ' + (it.raw.title || '');
    for (var i = 0; i < WHY.length; i++) if (WHY[i][0].test(k)) return WHY[i][1];
    return '';
  }
  function reqIndex() { var m = {}; ((body('requirements') || {}).requirements || []).forEach(function (u) { m[u.requirement_id] = u; m[u.document_id + ':' + u.requirement_id] = u; }); return m; }
  function buildModel() {
    var ri = reqIndex(), t = tests(), out = [];
    findings().filter(function (x) { return x.result === 'FAIL' || !x.result; }).forEach(function (x) {
      out.push({ kind: 'f', key: 'f:' + x.finding_id, id: x.finding_id, sev: x.severity, label: SEV[x.severity] || '', short: x.title || '指摘', req: x.requirement_id, open: isOpenF(x), raw: x });
    });
    conflicts().forEach(function (c) {
      var r = ((c.evidence || [])[0] || {}).requirement_id;
      out.push({ kind: 'c', key: 'c:' + c.conflict_id, id: c.conflict_id, sev: null, label: '矛盾', short: c.topic || '記述の食い違い', req: r, open: c.status === 'UNRESOLVED', raw: c });
    });
    Object.keys(t).forEach(function (k) {
      var tc = t[k]; if (!tc || tc.verdict !== 'NOT_TESTABLE') return;
      var u = ri[k]; var rid2 = u ? u.requirement_id : k.split(':').pop();
      var miss = (tc.missing || [])[0], why = miss ? miss + 'がない' : ((tc.reasons || [])[0] || '合否の基準がない');
      out.push({ kind: 't', key: 't:' + k, id: k, sev: null, label: 'テスト不可', short: why, req: rid2, open: true, raw: tc });
    });
    var rank = function (it) { return it.kind === 'f' ? SEV_ORDER[it.sev] != null ? SEV_ORDER[it.sev] : 5 : it.kind === 'c' ? 10 : 20; };
    out.sort(function (a, b) { return (b.open - a.open) || (rank(a) - rank(b)); });
    out.forEach(function (it) { var u = ri[it.req]; it.reqText = u ? (u.raw_text || u.snippet || '') : ''; });
    return out;
  }
  function itemsFor(reqId) { return buildModel().filter(function (it) { return it.req === reqId; }); }
  function reqModel() {
    var rq = body('requirements') || {}, t = tests(), tr = body('trace'), orph = {}, ch = changedIds(), all = buildModel();
    if (tr && tr.graph) (tr.graph.orphans || []).forEach(function (o) { orph[o.node_id] = (orph[o.node_id] || []).concat(o.kind || ''); });
    return (rq.requirements || []).map(function (u) {
      var key = u.document_id + ':' + u.requirement_id;
      var mine = all.filter(function (it) { return it.req === u.requirement_id; }), open = mine.filter(function (it) { return it.open; });
      var worst = open.filter(function (it) { return it.kind === 'f'; }).reduce(function (a, it) { return a == null || SEV_ORDER[it.sev] < SEV_ORDER[a] ? it.sev : a; }, null);
      var tv = (t[key] || t[u.requirement_id] || {}).verdict || null;
      var notest = (orph[key] || orph[u.requirement_id] || []).some(function (k) { return /test/i.test(k); });
      var inf = Object.keys(u.fields || {}).some(function (k) { return u.fields[k] && u.fields[k].provenance === 'INFERRED'; });
      var cf = open.some(function (it) { return it.kind === 'c'; });
      var st = open.length ? ['要対応', 'attention'] : (tv === 'CAN_TEST' ? ['問題なし', 'ok'] : ['判定材料なし', 'unknown']);
      return { u: u, key: key, open: open.length, all: mine.length, worst: worst, tv: tv, cf: cf, notest: notest, inf: inf, changed: !!ch[u.requirement_id], st: st };
    });
  }
  function itemLine(it) { var s = String(it.reqText || '').slice(0, 24); return (it.req ? it.req + ' ' : '') + s + (it.reqText && it.reqText.length > 24 ? '…' : '') + ' — ' + it.label + '：' + it.short; }
  function priorities() { return buildModel().filter(function (it) { return it.open; }).map(function (it) { return { text: itemLine(it), go: 'f', id: it.key }; }); }
  function rawScore(sc) { return sc && sc.value != null ? Number(sc.value) : null; }
  function scoreText(sc) {
    if (!sc) return '未評価';
    if (sc.value == null) return '評価不能（評価できた範囲 ' + pct(sc.coverage) + '%）';
    return Math.round(sc.value) + '%';
  }
  function overviewHtml() {
    var rd = readiness();
    if (!rd && notRun('scores') && notRun('requirements')) return emptyBox();
    var st = rd ? (READY[rd.state] || ['ドラフト', 'draft']) : ['ドラフト', 'draft'];
    var pr = priorities(), n = pr.length, f = findings(), sc = scores();
    var lead = n ? n + ' 件の確認が必要です' : '確認が必要な項目は検出されていません（検出できた範囲）';
    var h = '<section class="dax-hero" aria-label="準備状態"><span class="dax-pill dax-pill--' + st[1] + '">準備状態</span>'
      + '<p class="dax-hero__state">' + esc(st[0]) + '</p><p class="dax-hero__lead">' + esc(lead) + '</p>'
      + '<button type="button" class="dax-btn dax-btn--primary" data-tab-go="issues">問題を確認</button></section>';
    var verdict = st[1] === 'ready' ? 'この文書は次工程へ進めます' : st[1] === 'conditional' ? 'この文書は条件付きで次工程へ進めます' : st[1] === 'blocked' ? 'この文書はこのままでは次工程へ進めません' : 'この文書はまだ判定に足る評価がありません';
    h += '<section class="dax-summary" aria-label="要約"><p>' + esc(verdict) + (n ? '。' + n + ' 件の確認が必要です。優先して確認:' : '。') + '</p>'
      + (n ? '<ol class="dax-actions">' + pr.slice(0, 3).map(function (a) { return '<li class="dax-action"><button type="button" class="dax-btn dax-btn--ghost" data-pgo="' + a.go + '" data-pid="' + esc(a.id) + '">' + esc(a.text) + '</button></li>'; }).join('') + '</ol>' : '')
      + (rd && (rd.reasons || []).length ? '<details class="dax-adv"><summary>判定の理由</summary><ul>' + rd.reasons.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul></details>' : '') + '</section>';
    var openF = f.filter(isOpenF), cnt = function (s) { return openF.filter(function (x) { return x.severity === s; }).length; };
    var unres = conflicts().filter(function (c) { return c.status === 'UNRESOLVED'; }).length;
    var metric = function (label, v, go, raw) { var flag = v === 0 ? ' data-zero' : (raw != null && raw < 70 ? ' data-warn' : ''); return '<button type="button" class="dax-metric"' + flag + ' data-tab-go="' + go + '"><span class="dax-metric__label">' + label + '</span><span class="dax-metric__value">' + esc(v) + '</span></button>'; };
    var bm = buildModel().filter(function (it) { return it.open; }), bc = function (fn) { return bm.filter(fn).length; };
    var parts = [['重大', bc(function (it) { return it.sev === 'critical'; })], ['高', bc(function (it) { return it.sev === 'high'; })], ['中', bc(function (it) { return it.sev === 'medium'; })], ['テスト不可', bc(function (it) { return it.kind === 't'; })], ['矛盾', bc(function (it) { return it.kind === 'c'; })]];
    h += '<div class="dax-metrics" role="group" aria-label="主な指標">' + metric('確認が必要', bm.length, 'issues')
      + parts.filter(function (p) { return p[1] > 0; }).map(function (p) { return metric(p[0], p[1], p[0] === '矛盾' ? 'conf' : 'issues'); }).join('')
      + ''
      + '</div>'
      + '<p class="dax-meta">点数は評価できた範囲だけで出します。評価できなかった範囲を 0 点や 100 点にはしません。</p>';
    if (mode() === 'DETERMINISTIC_ONLY') h += '<p class="dax-meta">AI レビューは実行していません（規則による解析のみ）。AI の観点は評価に含まれていません。</p>';
    h += '<details class="dax-collapse" open><summary class="dax-h2">品質</summary><div class="dax-quality">' + QUAL.map(function (q) {
      var s = sc[q[0]], w = s && s.value != null ? Math.max(0, Math.min(100, Math.round(s.value))) : null;
      var lv = w == null ? '' : ' data-level="' + (w < 50 ? 'low' : w < 75 ? 'mid' : 'ok') + '"';
      return '<button type="button" class="dax-qrow"' + lv + ' data-score="' + q[0] + '"><span class="dax-qrow__name">' + q[1] + '</span><span class="dax-qrow__value">' + esc(scoreText(s)) + '</span>'
        + (w == null ? '' : '<span class="dax-bar" aria-hidden="true"><span class="dax-bar__fill" style="width:' + w + '%"></span></span>') + '</button>';
    }).join('') + '</div></details>';
    var ch = changedIds(), chN = Object.keys(ch).length;
    h += '<details class="dax-collapse"><summary class="dax-h2">最近の変更 — ' + (notRun('diff') || !body('diff') ? '比較なし' : chN + ' 件') + '</summary>' + (notRun('diff') || !body('diff') ? '<p class="dax-meta">前の版との比較はまだありません。</p>'
      : '<div class="dax-change"><p class="dax-change__title">変更のあった要件 ' + chN + ' 件</p><p class="dax-change__impact">' + Object.keys(ch).slice(0, 8).map(function (k) { return '<span class="dax-tag">' + esc(k) + '</span>'; }).join(' ') + '</p><button type="button" class="dax-btn dax-btn--ghost dax-btn--sm" data-tab-go="diff">変更を見る</button></div>') + '</details>';
    var rm = reqModel(), tot = rm.length, can = rm.filter(function (m) { return m.tv === 'CAN_TEST' || m.tv === 'PARTIALLY_TESTABLE'; }).length;
    var tr = body('trace'), linked = tr && tr.graph ? rm.filter(function (m) { return !m.notest; }).length : null;
    var frow = function (label, v) { var w = tot && v != null ? Math.round(v / tot * 100) : null; return '<div class="dax-funnel__row"><span>' + label + '</span><span>' + (v == null ? '未評価' : v + ' / ' + tot) + '</span>' + (w == null ? '' : '<span class="dax-bar" aria-hidden="true"><span class="dax-bar__fill" style="width:' + w + '%"></span></span>') + '</div>'; };
    h += '<details class="dax-collapse"><summary class="dax-h2">被覆 — テスト可能と判定された要件 ' + can + ' / ' + tot + ' 件・テストへのつながりがある要件 ' + (linked == null ? '未評価' : linked + ' / ' + tot + ' 件') + '</summary><div class="dax-funnel">' + frow('要件', tot) + frow('テスト可能と判定された要件', body('requirements') ? can : null) + frow('テストへのつながりがある要件', linked) + '</div></details>';
    var allIt = buildModel(), dec = allIt.filter(function (it) { return !it.open || (it.kind === 'f' && it.raw.status === 'ACCEPTED'); }).length;
    h += '<details class="dax-collapse" open><summary class="dax-h2">レビューの進み — 判断済み ' + dec + ' / ' + allIt.length + '</summary><div class="dax-funnel">' + frow2('判断済みの指摘', dec, allIt.length) + frow2('決定済みの矛盾', conflicts().length - unres, conflicts().length) + '</div></details>';
    return h;
  }
  function frow2(label, v, t) { var w = t ? Math.round(v / t * 100) : null; return '<div class="dax-funnel__row"><span>' + label + '</span><span>' + (t ? v + ' / ' + t : '対象なし') + '</span>' + (w == null ? '' : '<span class="dax-bar" aria-hidden="true"><span class="dax-bar__fill" style="width:' + w + '%"></span></span>') + '</div>'; }
  function scoreDrawer(key, trigger) {
    var sc = scores()[key], label = (QUAL.filter(function (q) { return q[0] === key; })[0] || [0, key])[1];
    var list = function (a) { return a && a.length ? '<ul>' + a.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : '<p class="dax-meta">なし</p>'; };
    var h = !sc ? '<p>未評価です。解析すると評価されます。</p>' : (sc.value == null ? '<p>評価不能です。点数は付けていません（評価できた範囲 ' + pct(sc.coverage) + '%）。</p>' : '<p>' + Math.round(sc.value) + '%（評価できた範囲 ' + pct(sc.coverage) + '%）</p>')
      + (sc ? '<h3 class="dax-h3">主な理由</h3>' + list(sc.explanation) + '<details class="dax-adv"><summary>根拠の詳細</summary><h3 class="dax-h3">評価に含めたもの</h3>' + list(sc.included) + '<h3 class="dax-h3">評価できなかったもの</h3>' + list(sc.not_evaluated) + '</details>' : '');
    showDrawer(label, h, trigger);
  }

  /* ---------- 要件 ---------- */
  function reqRows() {
    var q = S.q.trim().toLowerCase();
    return reqModel().filter(function (m) {
      if (S.chip === 'attention' && m.st[1] !== 'attention') return false;
      if (S.chip === 'nt' && m.tv !== 'NOT_TESTABLE') return false;
      if (S.chip === 'cf' && !m.cf) return false;
      if (S.chip === 'notest' && !m.notest) return false;
      if (S.chip === 'changed' && !m.changed) return false;
      return !q || (m.u.requirement_id + ' ' + (m.u.raw_text || '')).toLowerCase().indexOf(q) >= 0;
    }).sort(function (a, b) { var R = { attention: 0, unknown: 1, ok: 2 }; return R[a.st[1]] - R[b.st[1]]; });
  }
  function reqRowsHtml(rows) {
    if (!rows.length) return '<tr><td colspan="9">この条件に当てはまる要件はありません。絞り込みを解除してください。</td></tr>';
    return rows.map(function (m) {
      return '<tr tabindex="0" data-req="' + esc(m.key) + '"><td>' + esc(m.u.requirement_id) + '</td><td>' + esc(m.u.raw_text || m.u.snippet || '') + '</td>'
        + '<td><span class="dax-req--' + m.st[1] + '">' + m.st[0] + '</span></td>'
        + '<td>' + (m.worst ? '<span class="dax-sev--' + esc(m.worst) + '">' + esc(SEV[m.worst] || '') + '</span>' : '<span class="dax-meta">検出なし</span>') + '</td>'
        + '<td>' + esc(m.tv ? TEST[m.tv] || '判定不能' : '未判定') + '</td><td>' + (m.open ? m.open + ' 件' : '—') + '</td>'
        + (S.cols.kind ? '<td>' + esc(KIND[m.u.kind] || m.u.kind || '—') + '</td>' : '') + (S.cols.doc ? '<td>' + esc(m.u.document_id) + '</td>' : '') + (S.cols.infer ? '<td>' + (m.inf ? '推測を含む' : '—') + '</td>' : '') + '</tr>';
    }).join('');
  }
  function reqHtml() {
    if (!body('requirements')) return notRun('requirements') ? emptyBox() : failBox();
    var all = reqModel();
    if (!all.length) return stateBox('empty', '要件が見つかりません', '文書に要件の記述があるか確認し、取り込み直してから再解析してください。', RUN_BTN);
    var rows = reqRows();
    var chips = '<div class="dax-chips" role="group" aria-label="絞り込み">' + REQ_CHIPS.map(function (c) {
      return '<button type="button" class="dax-chip" aria-pressed="' + (S.chip === c[0]) + '" data-chip="' + c[0] + '">' + c[1] + '</button>'; }).join('') + '</div>';
    var colsel = '<details class="dax-colsel"><summary>列</summary>' + OPT_COLS.map(function (c) { return '<label><input type="checkbox" data-col="' + c[0] + '"' + (S.cols[c[0]] ? ' checked' : '') + '> ' + c[1] + '</label>'; }).join('') + '</details>';
    var head = '<tr><th scope="col">ID</th><th scope="col">要件</th><th scope="col">状態</th><th scope="col">品質</th><th scope="col">テスト可能性</th><th scope="col">指摘</th>'
      + OPT_COLS.filter(function (c) { return S.cols[c[0]]; }).map(function (c) { return '<th scope="col">' + c[1] + '</th>'; }).join('') + '</tr>';
    return '<div class="dax-toolbar"><input type="search" class="dax-search" id="dx-q" placeholder="ID・本文で検索" aria-label="要件を検索" value="' + esc(S.q) + '">' + chips + colsel + '<span class="dax-meta" role="status" id="dx-cnt">' + all.length + ' 件中 要対応 ' + all.filter(function (m) { return m.st[1] === 'attention'; }).length + ' 件' + (rows.length !== all.length ? '（表示 ' + rows.length + ' 件）' : '') + '</span></div>'
      + '<div class="dax-table-wrap"><table class="dax-table"><thead>' + head + '</thead><tbody id="dx-rows">' + reqRowsHtml(rows) + '</tbody></table></div>';
  }
  function fieldVal(f) { if (f && typeof f === 'object') return f.value != null ? f.value : (f.text != null ? f.text : ''); return f == null ? '' : f; }
  function reqDrawer(key, trigger) {
    var m = reqModel().filter(function (x) { return x.key === key; })[0]; if (!m) return;
    var u = m.u, tc = tests()[key] || tests()[u.requirement_id] || {}, loc = u.location || {}, line = u.line_start || loc.line_start;
    var mine = itemsFor(u.requirement_id);
    var sec = function (t, inner) { return '<section class="dax-detail__section"><h3 class="dax-h3">' + t + '</h3>' + inner + '</section>'; };
    var h = sec('状態', '<p><span class="dax-req--' + m.st[1] + '">' + m.st[0] + '</span> ・ 指摘 ' + (mine.length ? mine.length + ' 件' : '検出なし（検出できた範囲）') + ' ・ テスト可能性 ' + esc(m.tv ? TEST[m.tv] || '判定不能' : '未判定') + '</p>')
      + sec('原文', '<blockquote>' + esc(u.raw_text || u.snippet || '') + '</blockquote><p class="dax-meta">' + esc(u.document_id) + (line ? ' ・ ' + esc(line) + ' 行目' : '') + '</p>')
      + sec('構造化された解釈', '<dl>' + FIELDS.map(function (p) {
        var fv = (u.fields || {})[p[0]]; if (fv == null || fv === '') return '';
        var pv = fv && fv.provenance;
        return '<dt>' + p[1] + '</dt><dd>' + esc(fieldVal(fv)) + ' <span class="dax-meta">' + (pv ? esc(PROV[pv] || '出所不明') : '出所不明') + '</span></dd>';
      }).join('') + '</dl>')
      + sec('問題', mine.length ? '<ul>' + mine.map(function (it) { var st = itemStat(it); return '<li><button type="button" class="dax-btn dax-btn--ghost dax-btn--sm" data-pgo="f" data-pid="' + esc(it.key) + '">' + sevTag(it) + ' ' + esc(it.short) + '</button> <span class="dax-status--' + st[1] + '">' + st[0] + '</span>'
        + (it.kind === 't' ? ((it.raw.reasons || []).length ? '<ul>' + it.raw.reasons.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : '') + ((it.raw.missing || []).length ? '<p class="dax-meta">不足：' + it.raw.missing.map(esc).join('、') + '</p>' : '') : '') + '</li>'; }).join('') + '</ul>' : '<p class="dax-meta">検出なし（検出できた範囲）</p>')
      + sec('トレーサビリティ', body('trace') ? (m.notest ? '<p>テストへのつながりが見つかっていません。欠陥とは限りません。</p>' : '<p>つながりの欠落は検出されていません（検出できた範囲）。</p>') : '<p class="dax-meta">未評価</p>')
      + sec('テスト', '<p>' + esc(m.tv ? TEST[m.tv] || '判定不能' : '未判定') + '</p>' + ((tc.missing || []).length ? '<p>不足している情報</p><ul>' + tc.missing.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : '') + '<div id="dx-rw">' + rwHtml(S.rw[u.requirement_id]) + '</div>')
      + '<details class="dax-adv"><summary>根拠の詳細</summary>' + ((tc.reasons || []).length ? '<ul>' + tc.reasons.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : '<p class="dax-meta">テスト可能性の判定理由はありません。</p>') + (u.snippet && u.snippet !== u.raw_text ? '<p>' + esc(u.snippet) + '</p>' : '') + '</details>'
      + sec('履歴', m.changed ? '<p>前の版から変更があります。<button type="button" class="dax-btn dax-btn--ghost dax-btn--sm" data-tab-go="diff">変更を見る</button></p>' : '<p class="dax-meta">前の版との差分は記録されていません。</p>');
    var firstOpen = mine.filter(function (it) { return it.open; })[0];
    h += '<div data-foot>' + (firstOpen ? '<button type="button" class="dax-btn dax-btn--primary" data-pgo="f" data-pid="' + esc(firstOpen.key) + '">この指摘を判断する</button>' : '<button type="button" class="dax-btn dax-btn--ghost" data-drawer-close>閉じる</button>') + '</div>';
    showDrawer(u.requirement_id + '　' + String(u.raw_text || '').slice(0, 40), h, trigger);
    var reqId = u.requirement_id;
    if (S.rw[reqId] === undefined) get('rewrite/' + encodeURIComponent(reqId)).then(function (r) {
      S.rw[reqId] = r.ok ? (r.body || null) : null;
      var box = document.getElementById('dx-rw'); if (box && drawerOpen()) box.innerHTML = rwHtml(S.rw[reqId]);
    });
  }
  function rwHtml(r) {
    if (r === undefined) return '<p class="dax-meta" role="status">書き換え案を読み込み中…</p>';
    if (!r) return '';
    var txt = function (v) { return typeof v === 'string' ? v : JSON.stringify(v); };
    var GW = { given: '前提（Given）', when: '操作（When）', then: '結果（Then）' }, pr = r.proposal && typeof r.proposal === 'object' ? r.proposal : null;
    var out = '<p>提案（未承認）：採用するかは人が決めます。原文からの推測で、事実ではありません。</p>';
    if (typeof r === 'string') return out + '<p>' + esc(r) + '</p>';
    if (pr) return out + '<dl>' + Object.keys(GW).filter(function (k) { return pr[k]; }).map(function (k) { return '<dt>' + GW[k] + '</dt><dd>' + esc(txt(pr[k])) + '</dd>'; }).join('') + '</dl>';
    return out + '<p>' + esc(txt(r.proposed_text || r.text || r)) + '</p>';
  }

  /* ---------- 指摘（マスター詳細） ---------- */
  function issuesHtml() {
    if (!body('issues') && !body('requirements')) return notRun('issues') ? emptyBox() : failBox();
    var all = buildModel();
    if (!all.length) return stateBox('empty', '検出なし（検出できた範囲）', '規則で検出できた範囲に指摘・矛盾・テスト不可の要件はありません。検出が無いことは、問題が無いことの証明ではありません。');
    var KF = [['', 'すべて']].concat(Object.keys(SEV).map(function (k) { return ['s:' + k, SEV[k]]; }), [['c', '矛盾'], ['t', 'テスト不可']]);
    var match = function (it, f) { return !f || (f === 'c' || f === 't' ? it.kind === f : it.kind === 'f' && 's:' + it.sev === f); };
    var list = all.filter(function (it) { return match(it, S.fsev); });
    if (!list.some(function (it) { return it.key === S.selF; })) S.selF = list.length ? list[0].key : null;
    var chips = '<div class="dax-toolbar"><div class="dax-chips" role="group" aria-label="種類で絞り込み">' + KF.map(function (k) {
      var n = all.filter(function (it) { return match(it, k[0]); }).length;
      return n ? '<button type="button" class="dax-chip" aria-pressed="' + (S.fsev === k[0]) + '" data-fsev="' + k[0] + '">' + k[1] + ' ' + n + '</button>' : ''; }).join('') + '</div></div>';
    var items = '<div class="dax-md__list" role="listbox" aria-label="指摘の一覧">' + list.map(function (it) {
      var st = itemStat(it);
      return '<button type="button" role="option" class="dax-item" aria-selected="' + (it.key === S.selF) + '" data-fid="' + esc(it.key) + '">' + sevTag(it) + ' <b>' + esc(it.short) + '</b>'
        + '<span class="dax-meta">' + esc(it.req || '要件なし') + ' ・ <span class="dax-status--' + st[1] + '">' + esc(st[0]) + '</span></span></button>';
    }).join('') + '</div>';
    var sel = list.filter(function (it) { return it.key === S.selF; })[0];
    return chips + '<div class="dax-md">' + items + '<div class="dax-md__detail" aria-live="polite">' + (sel ? itemDetail(sel) : '<p class="dax-meta">この条件に当てはまる指摘はありません。</p>') + '</div></div>';
  }
  function sevTag(it) { return it.kind === 'f' ? '<span class="dax-sev--' + esc(it.sev) + '">' + esc(it.label) + '</span>' : '<span class="dax-sev--high">' + esc(it.label) + '</span>'; }
  function itemStat(it) { if (it.kind === 'f') return fstat(it.raw); if (it.kind === 'c') return it.open ? ['判断待ち', 'decision'] : ['解決済み', 'resolved']; return ['未対応', 'open']; }
  function itemDetail(it) {
    if (it.kind === 'f') return findingDetail(it.raw, it);
    var sec = function (t, inner) { return '<section class="dax-detail__section"><h3 class="dax-h3">' + t + '</h3>' + inner + '</section>'; };
    var st = itemStat(it), head = '<header><p class="dax-meta">' + sevTag(it) + ' ・ <span class="dax-status--' + st[1] + '">' + esc(st[0]) + '</span> ・ 検出元 規則</p><h2 class="dax-h2">' + esc(it.short) + '</h2></header>';
    var reqLine = it.req ? '<p class="dax-meta">要件 ' + esc(it.req) + (it.reqText ? '：' + esc(it.reqText) : '') + '</p>' : '';
    if (it.kind === 't') {
      var tc = it.raw, li = function (a) { return (a || []).length ? '<ul>' + a.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : ''; };
      return head + sec('何が問題か', '<p>この要件は合否の基準が書かれておらず、テストできません。</p>' + reqLine + ((tc.missing || []).length ? '<p>不足している情報</p>' + li(tc.missing) : ''))
        + sec('なぜ重要か', '<p>' + whyOf(it) + '</p>') + sec('推奨する対応', '<p>不足している情報（閾値・条件・失敗時の挙動など）を要件に書き足してください。</p>')
        + '<details class="dax-adv"><summary>根拠の詳細</summary>' + (li(tc.reasons) || '<p class="dax-meta">判定理由は記録されていません。</p>') + '</details>';
    }
    var c = it.raw, ev = c.evidence || [], q = function (e, l) { return '<div class="dax-compare__side"><p class="dax-meta">' + l + '</p>' + (e ? '<blockquote>' + esc(e.quote) + '</blockquote><p class="dax-meta">' + esc(e.document_id) + ' ・ ' + esc(e.requirement_id) + '</p>' : '<p class="dax-meta">対応する記述がありません。</p>') + '</div>'; };
    return head + sec('何が問題か', '<div class="dax-compare">' + q(ev[0], '記述 A') + '<div class="dax-compare__topic">' + esc(c.question || '') + '</div>' + q(ev[1], '記述 B') + '</div><p class="dax-unknown">どちらが正しいかは未確定です。</p>')
      + sec('なぜ重要か', '<p>' + whyOf(it) + '</p>') + sec('推奨する対応', '<p>「矛盾」タブでどちらを正とするかを決め、理由を記録してください。</p><button type="button" class="dax-btn dax-btn--sm" data-tab-go="conf">矛盾タブで決める</button>');
  }
  function findingDetail(x, it) {
    var id = esc(x.finding_id || ''), loc = x.location || {}, st = fstat(x), d = S.draft[x.finding_id] || {};
    var sec = function (t, inner) { return '<section class="dax-detail__section"><h3 class="dax-h3">' + t + '</h3>' + inner + '</section>'; };
    var why = whyOf(it || { kind: 'f', raw: x });
    var h = '<header><p class="dax-meta"><span class="dax-sev--' + esc(x.severity) + '">' + esc(SEV[x.severity] || '') + '</span> ・ <span class="dax-status--' + st[1] + '">' + esc(st[0]) + '</span>'
      + (x.status === 'WAIVED' && x.waiver_expiry ? '（期限 ' + esc(String(x.waiver_expiry).slice(0, 10)) + '）' : '') + ' ・ 検出元 ' + esc(SRC[x.source] || '不明') + '</p><h2 class="dax-h2">' + esc(x.title || '指摘') + '</h2></header>'
      + sec('何が問題か', '<p>' + esc(x.reason || loc.snippet || '説明はありません。') + '</p>' + (x.requirement_id ? '<p class="dax-meta">要件 ' + esc(x.requirement_id) + '</p>' : ''))
      + (why ? sec('なぜ重要か', '<p>' + esc(why) + '</p>') : '')
      + sec('推奨する対応', '<p>' + esc(x.how_to_fix || '推奨する対応は記録されていません。原文を確認して判断してください。') + '</p>')
      + (id ? sec('判断', '<fieldset><legend>判断</legend>' + [['accepted', '採用'], ['rejected', '却下'], ['waived', '期限つきで免除']].map(function (o) {
          return '<label><input type="radio" name="dx-fd-' + id + '" value="' + o[0] + '" data-fpick="' + id + '"' + (d.choice === o[0] ? ' checked' : '') + '> ' + o[1] + '</label>'; }).join('') + '</fieldset>'
        + '<div data-field><label for="dx-rs-' + id + '">判断の理由</label><textarea id="dx-rs-' + id + '" rows="2" data-reason="' + id + '" placeholder="例：仕様書 3.2 節で確認済みのため採用">' + esc(d.reason || '') + '</textarea></div>'
        + '<div data-field data-expiry-wrap="' + id + '"' + (d.choice === 'waived' ? '' : ' hidden') + '><label for="dx-ex-' + id + '">免除の期限</label><input id="dx-ex-' + id + '" type="date" data-expiry="' + id + '" value="' + esc(d.expiry || '') + '"></div>'
        + (S.ferr[x.finding_id] ? '<p role="alert">' + esc(S.ferr[x.finding_id]) + '</p>' : '')
        + '<button type="button" class="dax-btn dax-btn--primary" data-fsubmit="' + id + '">判断を記録</button>') : '')
      + '<details class="dax-adv"><summary>根拠の詳細</summary>' + (loc.snippet ? '<blockquote>' + esc(loc.snippet) + '</blockquote>' : '<p class="dax-meta">引用はありません。</p>')
      + '<p class="dax-meta">' + esc(loc.document_id || x.document_id || '') + ' ' + esc(loc.section || '') + (loc.line_start ? ' ・ ' + esc(loc.line_start) + ' 行目' : '') + '</p></details>'
      + '<details class="dax-adv"><summary>技術詳細</summary><dl><dt>規則 ID</dt><dd>' + esc(x.rule_id || '—') + '</dd><dt>出所</dt><dd>' + esc(SRC[x.source] || x.source || '—') + '</dd><dt>関連度</dt><dd>' + conf(x.confidence) + '（' + (Number(x.confidence) || 0).toFixed(2) + '）</dd></dl></details>';
    return h;
  }

  /* ---------- 矛盾（第 1 段は簡易表示） ---------- */
  function conflictsHtml() {
    if (!body('conflicts')) return notRun('conflicts') ? emptyBox() : failBox();
    var list = conflicts();
    if (!list.length) return stateBox('empty', '検出なし（検出できた範囲）', '矛盾は見つかっていません。見つからないことは、矛盾が無いことの証明ではありません。');
    return list.map(function (c) {
      var ev = c.evidence || [], id = esc(c.conflict_id), d = S.draft[c.conflict_id] || {};
      var side = function (e, l) { return '<div class="dax-compare__side"><p class="dax-meta">' + l + '</p>' + (e ? '<blockquote>' + esc(e.quote) + '</blockquote><p class="dax-meta">' + esc(e.document_id) + ' ・ ' + esc(e.requirement_id) + '</p>' : '<p class="dax-meta">対応する記述がありません。</p>') + '</div>'; };
      return '<section class="dax-section"><h2 class="dax-h2">' + esc(c.topic) + '</h2><p class="dax-unknown">どちらが正しいかは未確定です。人が確かめて決めてください。</p>'
        + '<div class="dax-compare">' + side(ev[0], '記述 A') + '<div class="dax-compare__topic">' + esc(c.question || '') + '</div>' + side(ev[1], '記述 B') + '</div>'
        + '<fieldset><legend>どちらを正としますか</legend>' + [['A', '記述 A を正とする'], ['B', '記述 B を正とする'], ['N', 'どちらも違う（文書を直す）']].map(function (o) {
          return '<label><input type="radio" name="dx-pick-' + id + '" value="' + o[0] + '" data-pick="' + id + '"' + (d.pick === o[0] ? ' checked' : '') + '> ' + o[1] + '</label>'; }).join('') + '</fieldset>'
        + '<label>決定の理由<textarea rows="2" data-reason="' + id + '">' + esc(d.reason || '') + '</textarea></label>' + (S.ferr[c.conflict_id] ? '<p role="alert">' + esc(S.ferr[c.conflict_id]) + '</p>' : '')
        + '<div><button type="button" class="dax-btn dax-btn--sm" data-decide="' + id + '" data-d="conflict_decided">決定を記録</button> <button type="button" class="dax-btn dax-btn--ghost dax-btn--sm" data-decide="' + id + '" data-d="rejected">矛盾ではない</button></div></section>';
    }).join('');
  }

  /* ---------- 判断の記録（理由必須・免除は期限必須。ネイティブダイアログは使わない） ---------- */
  function draftOf(id) {
    var ta = document.querySelector('textarea[data-reason="' + id + '"]'), ex = document.querySelector('input[data-expiry="' + id + '"]'), pk = document.querySelector('input[data-pick="' + id + '"]:checked'), o = S.draft[id] || {};
    var fp = document.querySelector('input[data-fpick="' + id + '"]:checked'); S.draft[id] = { reason: ta ? ta.value : o.reason, expiry: ex ? ex.value : o.expiry, pick: pk ? pk.value : o.pick, choice: fp ? fp.value : o.choice }; return S.draft[id];
  }
  function record(id, d, expiry, reason, msg) {
    post('decisions', { decision: d, target: id, reason: reason, expiry: expiry }).then(function (r) {
      S.ferr[id] = r.ok ? '' : ((r.body && r.body.error) || '記録できませんでした。') + ' 権限を確認してから、もう一度お試しください。';
      if (r.ok) { delete S.draft[id]; toast(msg); return load(); }
      render();
    });
  }
  function decideFinding(id, d) {
    var dr = draftOf(id);
    if (!dr.reason || !dr.reason.trim()) { S.ferr[id] = '理由が空です。理由を入力してからもう一度押してください。'; return render(); }
    if (d === 'waived' && !dr.expiry) { S.ferr[id] = '免除するには期限が必要です。期限の日付を入力してからもう一度押してください。'; return render(); }
    record(id, d, d === 'waived' ? dr.expiry : null, dr.reason.trim(), '判断を記録しました（' + ({ accepted: '採用', rejected: '却下', waived: '期限つきで免除' }[d]) + '）。');
  }
  function decideConflict(id, d) {
    var dr = draftOf(id), PICK = { A: '記述 A を正とする', B: '記述 B を正とする', N: 'どちらも違う' };
    if (d === 'conflict_decided' && !dr.pick) { S.ferr[id] = 'どちらを正とするかを選んでから、もう一度押してください。'; return render(); }
    if (!dr.reason || !dr.reason.trim()) { S.ferr[id] = '理由が空です。理由を入力してからもう一度押してください。'; return render(); }
    record(id, d, null, (d === 'conflict_decided' ? '【' + PICK[dr.pick] + '】' : '') + dr.reason.trim(), d === 'rejected' ? '「矛盾ではない」と記録しました。' : '決定を記録しました。');
  }

  /* ---------- ドロワー ---------- */
  function drawerEl() {
    var d = document.getElementById('dx-drawer');
    if (!d) { d = document.createElement('aside'); d.id = 'dx-drawer'; d.className = 'dax-drawer'; d.setAttribute('role', 'dialog'); d.setAttribute('aria-modal', 'true'); d.hidden = true; document.body.appendChild(d); }
    return d;
  }
  function drawerOpen() { var d = document.getElementById('dx-drawer'); return !!(d && !d.hidden); }
  function closeDrawer() {
    var d = document.getElementById('dx-drawer'); if (!d || d.hidden) return;
    d.hidden = true; if (S.drawerFocus && document.contains(S.drawerFocus)) S.drawerFocus.focus(); S.drawerFocus = null;
  }
  function showDrawer(title, html, trigger) {
    var d = drawerEl(); if (d.hidden) S.drawerFocus = trigger;
    d.setAttribute('aria-label', title);
    d.innerHTML = '<header class="dax-drawer__head"><h2 class="dax-h2">' + esc(title) + '</h2><button type="button" class="dax-btn dax-btn--ghost dax-btn--sm" data-drawer-close aria-label="閉じる">閉じる</button></header><div class="dax-drawer__body">' + html + '</div>';
    d.hidden = false; var c = d.querySelector('[data-drawer-close]'); if (c) c.focus();
  }

  /* ---------- 枠 ---------- */
  function navCount(k) {
    var n = null;
    if (k === 'req' && body('requirements')) n = reqModel().filter(function (m) { return m.st[1] === 'attention'; }).length;
    if (k === 'issues') n = buildModel().filter(function (it) { return it.open; }).length;
    if (k === 'conf' && body('conflicts')) n = conflicts().filter(function (c) { return c.status === 'UNRESOLVED'; }).length;
    var lab = k === 'req' ? '要対応 ' + n + ' 件' : '未対応 ' + n + ' 件';
    return n ? ' <span class="dax-count" aria-label="' + lab + '" title="' + lab + '">' + n + '</span>' : '';
  }
  function headerHtml() {
    var rq = body('requirements') || {}, sc = body('scores') || {}, rd = readiness(), st = rd ? READY[rd.state] || ['ドラフト', 'draft'] : null;
    var vs = ((window.DV && DV.state && DV.state.review && DV.state.review.versions) || []).map(function (v) { return v && typeof v === 'object' ? (v.version != null ? v.version : v.no) : v; }).filter(function (v) { return v != null && v !== ''; });
    var ver = vs.length ? vs.reduce(function (a, b) { return Number(b) > Number(a) ? b : a; }) : null;
    var at = rq.saved_at || sc.saved_at || (body('issues') || {}).saved_at || (S.full && S.full.saved_at) || null;
    var hasData = !notRun('scores');
    return '<header class="dax-header"><div><h1 class="dax-h1 dax-header__title">ドキュメント品質保証</h1><p class="dax-header__meta dax-meta">' + esc(rname() || '') + (ver != null ? ' ・ 版 ' + esc(ver) : '') + (at ? ' ・ 最終解析 ' + esc(String(at).replace('T', ' ').slice(0, 16)) : '')
      + ''
      + '<div class="dax-header__actions"><button type="button" class="dax-btn dax-btn--ghost" data-act="run"' + (S.busy ? ' disabled' : '') + '>' + (S.busy ? '解析中…' : '再解析') + '</button>'
      + '<button type="button" class="dax-btn dax-btn--ghost" data-tab-go="diff">比較</button>'
      + '<details class="dax-menu"' + (hasData ? '' : ' hidden') + '><summary class="dax-btn dax-btn--ghost">エクスポート</summary><div role="menu"><a role="menuitem" href="' + url('report.md') + '" download>レポート（Markdown）</a><a role="menuitem" href="' + url('report.csv') + '" download>指摘一覧（CSV）</a></div></details>'
      + '<button type="button" class="dax-btn dax-btn--ghost" data-act="settings">設定</button></div></header>';
  }
  function navHtml() {
    return '<nav class="dax-nav" role="tablist" aria-label="品質保証の表示">' + NAV.map(function (t) {
      var on = S.tab === t[0];
      return '<button type="button" role="tab" class="dax-nav__item" id="dx-t-' + t[0] + '" aria-selected="' + on + '"' + (on ? ' aria-current="page"' : '') + ' tabindex="' + (on ? 0 : -1) + '" data-tab="' + t[0] + '">' + t[1] + navCount(t[0]) + '</button>'; }).join('') + '</nav>';
  }
  function render() {
    var root = $('#da-root'); if (!root) return;
    if (!rid()) { root.innerHTML = '<div class="dax"><main class="dax-main">' + stateBox('empty', '文書を選んでいません', 'レビュー一覧から対象の文書を開いてください。', '<a class="dax-btn dax-btn--primary" href="#reviews" data-go="reviews">レビュー一覧へ</a>') + '</main></div>'; return; }
    var views = { overview: overviewHtml, req: reqHtml, issues: issuesHtml, conf: conflictsHtml };
    var pn = PANEL_TABS[S.tab] ? window.DAPanels[PANEL_TABS[S.tab]] : null;
    if (!views[S.tab] && !pn) S.tab = 'overview';
    var main;
    if (S.blocked) main = stateBox('blocked', '解析できません', '理由：' + esc(S.blocked.why) + '<br>次にすること：' + esc(S.blocked.next), RETRY_BTN);
    else if (S.error) main = stateBox('error', '解析結果を取得できませんでした', esc(S.error), RETRY_BTN);
    else if (!S.loaded) main = skeleton();
    else if (S.loadFail) main = failBox();
    else if (pn) main = pn.html(ctx());
    else main = views[S.tab]();
    root.innerHTML = '<div class="dax">' + headerHtml() + navHtml() + '<main class="dax-main" id="dx-main" aria-labelledby="dx-t-' + S.tab + '"><div class="dax-page">' + main + '</div></main></div>';
    var mb = $('#dx-main .dax-page');
    if (pn && pn.bind && mb && S.loaded && !S.error && !S.blocked) pn.bind(mb, ctx());
  }
  function syncHash() { if (rid()) history.replaceState(null, '', '#assure/' + encodeURIComponent(rid()) + (S.tab !== 'overview' ? '/' + S.tab : '')); }
  function setTab(t, focus) { S.tab = t; syncHash(); closeDrawer(); render(); if (focus !== false) { var n = document.getElementById('dx-t-' + t); if (n) n.focus(); } }
  function closeMenu(ret) { var m = document.querySelector('#da-root details.dax-menu[open]'); if (!m) return false; m.open = false; if (ret) { var su = m.querySelector('summary'); if (su) su.focus(); } return true; }

  document.addEventListener('click', function (e) {
    var t = e.target; if (!t || !t.closest) return;
    var el;
    if (t.closest('[data-drawer-close]')) return closeDrawer();
    if (!t.closest('#da-root')) { if (!t.closest('#dx-drawer')) return; }
    if (t.closest('.dax-menu summary')) return;
    closeMenu(false);
    if ((el = t.closest('[data-tab]'))) return setTab(el.dataset.tab);
    if ((el = t.closest('[data-tab-go]'))) return setTab(el.dataset.tabGo);
    if ((el = t.closest('[data-act]'))) {
      var a2 = el.dataset.act;
      if (a2 === 'run') return analyze();
      if (a2 === 'reload') { S.error = ''; S.blocked = null; return load(); }
      if (a2 === 'settings') return toast('設定は次の段で提供します。');
      return;
    }
    if ((el = t.closest('[data-go="reviews"]'))) { if (window.DV && window.DV.show) { e.preventDefault(); window.DV.show('reviews'); } return; }
    if ((el = t.closest('[data-pgo]'))) {
      var g = el.dataset.pgo, id = el.dataset.pid;
      if (g === 'f') { S.selF = id; S.fsev = ''; return setTab('issues'); }
      if (g === 'conf') return setTab('conf');
      if (g === 'req') { setTab('req', false); return reqDrawer(id, el); }
    }
    if ((el = t.closest('[data-score]'))) return scoreDrawer(el.dataset.score, el);
    if ((el = t.closest('[data-chip]'))) { S.chip = S.chip === el.dataset.chip ? '' : el.dataset.chip; render(); var c = $('[data-chip="' + el.dataset.chip + '"]'); if (c) c.focus(); return; }
    if ((el = t.closest('[data-fsev]'))) { S.fsev = el.dataset.fsev; render(); var f = $('[data-fsev="' + el.dataset.fsev + '"]'); if (f) f.focus(); return; }
    if ((el = t.closest('.dax-item[data-fid]'))) { S.selF = el.dataset.fid; render(); var it = $('.dax-item[aria-selected="true"]'); if (it) it.focus(); return; }
    if ((el = t.closest('[data-fsubmit]'))) { var fid = el.dataset.fsubmit, ch = (S.draft[fid] || {}).choice; if (!ch) { S.ferr[fid] = '採用・却下・期限つきで免除のどれかを選んでから、もう一度押してください。'; return render(); } return decideFinding(fid, ch); }
    if ((el = t.closest('[data-decide]'))) return decideConflict(el.dataset.decide, el.dataset.d);
    if ((el = t.closest('tr[data-req]'))) return reqDrawer(el.dataset.req, el);
  });
  document.addEventListener('input', function (e) {
    var t = e.target; if (!t || !t.closest || !t.closest('#da-root')) return;
    if (t.id === 'dx-q') { S.q = t.value; var rows = reqRows(), tb = $('#dx-rows'), c = $('#dx-cnt'); if (tb) tb.innerHTML = reqRowsHtml(rows); if (c) { var am = reqModel(); c.textContent = am.length + ' 件中 要対応 ' + am.filter(function (m) { return m.st[1] === 'attention'; }).length + ' 件' + (rows.length !== am.length ? '（表示 ' + rows.length + ' 件）' : ''); } return; }
    var id = t.dataset && (t.dataset.reason || t.dataset.expiry || t.dataset.pick); if (id) draftOf(id);
  });
  document.addEventListener('change', function (e) {
    var t = e.target; if (!t || !t.closest || !t.closest('#da-root')) return;
    if (t.dataset && t.dataset.col) { S.cols = Object.assign({}, S.cols); S.cols[t.dataset.col] = t.checked; render(); var x = $('[data-col="' + t.dataset.col + '"]'); if (x) { x.closest('details').open = true; x.focus(); } return; }
    if (t.dataset && t.dataset.fpick) { draftOf(t.dataset.fpick); var w = document.querySelector('[data-expiry-wrap="' + t.dataset.fpick + '"]'); if (w) w.hidden = t.value !== 'waived'; return; }
    var id = t.dataset && (t.dataset.reason || t.dataset.expiry || t.dataset.pick); if (id) draftOf(id);
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { if (drawerOpen()) { e.preventDefault(); return closeDrawer(); } if (closeMenu(true)) { e.preventDefault(); } return; }
    var t = e.target; if (!t || !t.matches) return;
    if (e.key === 'Enter' && t.matches('tr[data-req]')) { e.preventDefault(); return reqDrawer(t.dataset.req, t); }
    if ((e.key === 'ArrowRight' || e.key === 'ArrowLeft' || e.key === 'Home' || e.key === 'End') && t.matches('.dax-nav__item')) {
      e.preventDefault();
      var keys = NAV.map(function (n) { return n[0]; }), i = keys.indexOf(S.tab);
      i = e.key === 'Home' ? 0 : e.key === 'End' ? keys.length - 1 : (i + (e.key === 'ArrowRight' ? 1 : keys.length - 1)) % keys.length;
      return setTab(keys[i]);
    }
    if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && t.matches('.dax-item')) {
      e.preventDefault(); var its = Array.prototype.slice.call(document.querySelectorAll('.dax-item')), j = its.indexOf(t) + (e.key === 'ArrowDown' ? 1 : -1);
      if (its[j]) { S.selF = its[j].dataset.fid; render(); var n = $('.dax-item[aria-selected="true"]'); if (n) n.focus(); }
    }
  });
  function enter() {
    var hp = location.hash.slice(1).split('/');
    if (hp[0] === 'assure' && hp[2] && NAV.some(function (n) { return n[0] === hp[2]; })) S.tab = hp[2];
    syncHash();
    if (rid() !== S.iid) { S.data = {}; S.loaded = false; S.full = null; S.draft = {}; S.ferr = {}; S.rw = {}; S.selF = null; S.error = ''; S.blocked = null; }
    if (S.busy) return render();
    load();
  }
  if (window.DV && window.DV.on) window.DV.on('assure', enter);
  window.DocAssure = { open: function () { if (window.DV) window.DV.show('assure'); }, close: closeDrawer, reload: load };
})();
