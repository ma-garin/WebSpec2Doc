/* System06 ドキュメント品質保証（DAX 骨格）。問いの順: 大丈夫か → 何が問題か → 何を直すか → 根拠。
   段階表示 L1 判断 / L2 問題 / L3 根拠（details.dax-adv）/ L4 技術詳細（details.dax-adv）。文書由来の文字列は esc() を通す。 */
(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var esc = function (v) { return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  var S = { data: {}, tab: 'overview', chip: '', q: '', cols: {}, selF: null, fsev: '', busy: false, loaded: false, error: '', blocked: null, drawerFocus: null, menuFocus: null, rw: {}, draft: {}, ferr: {}, iid: null, full: null, fstate: 'open', fsevF: '', fkind: '', fq: '', fsort: '', editDec: {}, decLog: null, disc: {} };
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
  var DONE = ['REJECTED', 'WAIVED', 'RESOLVED', 'DECIDED', 'ACCEPTED'];
  var DEC_NAME = { accepted: '認めた', rejected: '却下', waived: '免除', resolved: '解決済み', conflict_decided: '決定' };
  var FSTATE = [['open', '未解決'], ['done', '判断済み'], ['all', 'すべて']];
  var NAV = [['overview', '概要'], ['req', '要件'], ['issues', '指摘'], ['conf', '矛盾'], ['trace', 'トレーサビリティ'], ['diff', '変更'], ['review', 'AI レビュー']];
  var PANEL_TABS = { trace: 'trace', diff: 'diff', review: 'review' };
  var REQ_CHIPS = [['attention', '要対応'], ['nt', 'テスト不可'], ['cf', '矛盾あり'], ['notest', 'テストなし'], ['changed', '変更あり']];
  var OPT_COLS = [['kind', '種別'], ['doc', '文書'], ['infer', '推測を含む']];

  function fstat(x) {
    if (x.waiver_expired) return ['期限切れ。再度確認が必要', 'decision'];
    if (x.status === 'WAIVED') return ['免除', 'done'];
    if (x.status === 'ACCEPTED') return [isTbd(x) ? '決定を記録済み' : '認めた', 'done'];
    if (x.status === 'REJECTED') return ['却下', 'done'];
    if (DONE.indexOf(x.status) >= 0) return ['解決済み', 'done'];
    return ['判断待ち', 'decision'];
  }
  /* 表示部品: 重要度＝色付きドット／種類＝ニュートラルなタグ／状態＝ステータスピル（色だけに依存しない: 文字を必ず添える） */
  /* 重要度は 3 段（高=danger・中=warning・低=中立）。API の 5 段をここで畳む */
  var SEV3 = { critical: ['高', 'high'], high: ['高', 'high'], medium: ['中', 'medium'], low: ['低', 'low'], info: ['低', 'low'] };
  function sev3(sev) { return SEV3[sev] || ['未評価', 'none']; }
  function sevDot(sev) { var s = sev3(sev); return '<span class="dax-sd dax-sd--' + s[1] + '"><i aria-hidden="true"></i>' + s[0] + '</span>'; }
  function kindTag(it) { return '<span class="dax-kt">' + esc(it.kindLabel || it.label) + '</span>'; }
  var PILL_TIP = { decision: '判断待ち（規則・矛盾・未決）：判断を記録すると閉じます。修正待ち（テスト不可）：文書を直して再解析すると閉じます。判断済み：記録済み', fix: '修正待ち（テスト不可）：文書を直して再解析すると閉じます。判断待ち（規則・矛盾・未決）は判断の記録で閉じます', done: '判断済み：判断を記録しました。判断待ち（規則・矛盾・未決）・修正待ち（テスト不可）は未解決です' };
  function statPill(st) { return '<span class="dax-sp dax-sp--' + st[1] + '" title="' + (PILL_TIP[st[1]] || '') + '">' + esc(st[0]) + '</span>'; }
  function isOpenF(x) { return DONE.indexOf(x.status) < 0 || x.waiver_expired; }
  /* 製品の部品（標準の details / select / ラジオは使わない）
     開閉＝シェブロン付きの見出し行ボタン（aria-expanded）／ポップアップ＝ボタン＋メニュー（Esc で閉じる・矢印で移動） */
  var CHEV = '<svg class="dax-chev" viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 4l4 4-4 4"/></svg>';
  var CARET = '<svg class="dax-caret" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6l4 4 4-4"/></svg>';
  function disc(id, label, inner, meta, defOpen) {
    var o = id in S.disc ? !!S.disc[id] : !!defOpen;
    return '<div class="dax-disc"><button type="button" class="dax-disc__btn" aria-expanded="' + o + '" aria-controls="dxd-' + id + '" data-disc="' + id + '">' + CHEV + '<span class="dax-disc__label">' + label + '</span>' + (meta ? '<span class="dax-disc__meta">' + meta + '</span>' : '') + '</button>'
      + '<div class="dax-disc__body" id="dxd-' + id + '"' + (o ? '' : ' hidden') + '>' + inner + '</div></div>';
  }
  function pop(id, btn, cls, attrs, inner, role) {
    role = role || 'menu';
    return '<div class="dax-pop"><button type="button" class="' + cls + '" aria-haspopup="' + role + '" aria-expanded="false" aria-controls="dxp-' + id + '" data-pop="' + id + '"' + (attrs || '') + '>' + btn + '</button>'
      + '<div class="dax-pop__panel" id="dxp-' + id + '" role="' + role + '" hidden>' + inner + '</div></div>';
  }
  /* 絞り込みのドロップダウン（listbox）。値は data-dd / data-val で受ける */
  function dd(name, label, opts, cur) {
    var curL = (opts.filter(function (o) { return o[0] === cur; })[0] || opts[0])[1];
    return pop('dd-' + name, '<span class="dax-dd__l">' + esc(label) + '</span><span class="dax-dd__v">' + esc(curL) + '</span>' + CARET, 'dax-dd' + (cur ? ' is-set' : ''), ' aria-label="' + esc(label) + 'で絞り込み（現在: ' + esc(curL) + '）"',
      opts.map(function (o) { return '<button type="button" role="option" class="dax-pop__item" aria-selected="' + (o[0] === cur) + '" data-dd="' + name + '" data-val="' + esc(o[0]) + '">' + esc(o[1]) + '</button>'; }).join(''), 'listbox');
  }
  function infoTip(text) { return '<button type="button" class="dax-info" aria-label="' + esc(text) + '" data-tip="' + esc(text) + '">i</button>'; }
  /* 次工程の基準（暫定・画面内の唯一の定義）。API の判定理由がスコアに触れない場合に、画面側で補う */
  var GATE = { min: 60, keys: ['Completeness', 'Testability', 'Traceability'], note: '次工程の基準（暫定）：網羅性・テスト可能性・トレーサビリティがそれぞれ 60 点以上。基準は暫定で、今後見直します。' };
  function gateMiss() {
    var sc = scores();
    return QUAL.map(function (q) { return q[0]; }).filter(function (k) { return sc[k] && sc[k].value != null && Number(sc[k].value) < GATE.min; }).map(function (k) { return { key: k, name: QNAME[k], v: Math.round(Number(sc[k].value)) }; }).sort(function (a, b) { return a.v - b.v; });
  }
  function naNames() { var sc = scores(); return QUAL.filter(function (q) { return sc[q[0]] && sc[q[0]].value == null; }).map(function (q) { return q[1]; }); }
  function isTbd(x) { return /TBD|未決/i.test((x.rule_id || '') + ' ' + (x.title || '')); }
  function naReason(s) { return (s && (s.reason || s.not_evaluable_reason)) || '評価できた要件がない'; }
  /* 判定の 3 値: 進行不可／条件付きで可／可。条件＝確認待ち（重要度順）最大 3 件＋基準未達の観点 */
  function verdict3(rd, open, miss) {
    var s = rd && rd.state;
    if (s === 'BLOCKED' || s === 'DRAFT') return ['進行不可', 'blocked', '次工程へ進めません。'];
    if (!open.length && !miss.length && s === 'READY') return ['可', 'ready', '次工程へ進めます。'];
    if (naCount()) return ['判定保留', 'conditional', '次工程へ進めません（保留）'];
    return ['条件付きで可', 'conditional', '条件付きで次工程へ進めます。'];
  }
  function naCount() { return naNames().length; }
  /* 判定の理由: 根拠チップと同じデータ（gateMiss / naCount / 確認待ち件数）から文を組む */
  /* 理由文は件数と評価不能だけ（点数は根拠チップに出すので文には書かない） */
  function verdictText(n, miss, na) {
    var nm = naNames(), t = (n ? '確認待ちの指摘が ' + n + ' 件あります。' : '') + (nm.length ? nm.join('・') + 'は評価不能です。' : '');
    return t || (miss.length ? '基準未達の観点を直すと、次工程へ進めます。' : 'すべての観点が基準 ' + GATE.min + ' 以上です。');
  }

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
    var names = ['requirements', 'issues', 'conflicts', 'scores', 'trace'];
    return Promise.all(names.map(get)).then(function (rs) {
      S.data = { trace: null };
      rs.forEach(function (r, i) { S.data[names[i]] = r; });
      S.loadFail = rs.slice(0, 4).every(function (r) { return r.status === 0 || r.status >= 500; });
      S.busy = false; S.loaded = true; render();
      loadDecLog();
    });
  }
  /* 判断の理由・判断者は報告書（report.md）の「人の判断」節から読む。各対象の最後の記録が最新の判断 */
  function loadDecLog() {
    var iid = rid();
    return fetch(url('report.md'), { headers: { Accept: 'text/markdown' } }).then(function (r) { return r.ok ? r.text() : ''; }).catch(function () { return ''; }).then(function (t) {
      if (iid !== rid()) return;
      var m = {}, on = false;
      String(t || '').split('\n').forEach(function (ln) {
        if (/^##\s/.test(ln)) on = /人の判断/.test(ln);
        var g = on && ln.match(/^-\s+(\w+)\s+(\S+)（([^）]*)）:\s*(.*?)(?:\s+期限\s+(\d{4}-\d{2}-\d{2}))?(?:\s+[（(](\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2})[^)）]*[)）])?\s*$/);
        if (g) m[g[2]] = { decision: g[1], by: g[3], reason: g[4], expiry: g[5] || null, at: g[6] ? g[6].replace('T', ' ') : null };
      });
      S.decLog = m;
      if ((S.tab === 'issues' || S.tab === 'conf') && !drawerOpen()) { var ae = document.activeElement, aid = ae && ae.id; render(); if (aid) { var n = document.getElementById(aid); if (n) n.focus(); } }
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
    var ri = reqIndex(), t = tests(), out = [], tsc = scores().Testability, tLow = !!(tsc && tsc.value != null && Number(tsc.value) < GATE.min);
    var seen = {};
    findings().filter(function (x) { return x.result === 'FAIL' || !x.result; }).forEach(function (x) {
      var lc = x.location || {}, dk = [x.rule_id, x.requirement_id, lc.document_id || x.document_id, lc.line_start, x.reason].join('|'); if (seen[dk]) return; seen[dk] = 1;
      out.push({ kind: 'f', key: 'f:' + x.finding_id, id: x.finding_id, sev: x.severity, label: SEV[x.severity] || '', kindLabel: x.title || '指摘', short: x.title || '指摘', req: x.requirement_id, open: isOpenF(x), raw: x });
    });
    conflicts().forEach(function (c) {
      var r = ((c.evidence || [])[0] || {}).requirement_id;
      out.push({ kind: 'c', key: 'c:' + c.conflict_id, id: c.conflict_id, sev: SEV[c.severity] ? c.severity : null, label: '矛盾', kindLabel: '矛盾', short: c.topic || '記述の食い違い', req: r, open: c.status === 'UNRESOLVED', raw: c });
    });
    Object.keys(t).forEach(function (k) {
      var tc = t[k]; if (!tc || tc.verdict !== 'NOT_TESTABLE') return;
      var u = ri[k]; var rid2 = u ? u.requirement_id : k.split(':').pop();
      var miss = (tc.missing || [])[0], why = miss ? miss + 'がない' : ((tc.reasons || [])[0] || '合否の基準がない');
      // テスト不可にも重要度を付ける（規則側の重大度が無ければ「中」）
      out.push({ kind: 't', key: 't:' + k, id: k, sev: SEV[tc.severity] ? tc.severity : (tLow ? 'high' : 'medium'), label: 'テスト不可', kindLabel: 'テスト不可', short: why, req: rid2, open: true, raw: tc });
    });
    // 並び: 未決 → 判断済み（免除は最後）。同じ群の中は 重要度 → 種類（規則・矛盾・テスト不可）
    var grp = function (it) { return it.open ? 0 : (it.kind === 'f' && it.raw.status === 'WAIVED' ? 2 : 1); };
    var sv = function (it) { return SEV_ORDER[it.sev] != null ? SEV_ORDER[it.sev] : 9; };
    var kd = { f: 0, c: 1, t: 2 };
    out.sort(function (a, b) { return (grp(a) - grp(b)) || (sv(a) - sv(b)) || (kd[a.kind] - kd[b.kind]); });
    out.forEach(function (it) { var dk = it.kind === 'f' ? ((it.raw.location || {}).document_id || it.raw.document_id) : it.kind === 't' ? String(it.id).split(':')[0] : ((it.raw.evidence || [])[0] || {}).document_id; var u = (dk && ri[dk + ':' + it.req]) || ri[it.req]; it.reqU = u || null; it.reqText = u ? (u.raw_text || u.snippet || '') : ''; });
    return out;
  }
  function itemsFor(reqId) { return buildModel().filter(function (it) { return it.req === reqId; }); }
  function reqModel() {
    var rq = body('requirements') || {}, t = tests(), tr = body('trace'), orph = {}, ch = changedIds(), all = buildModel();
    if (tr && tr.graph) (tr.graph.orphans || []).forEach(function (o) { orph[o.node_id] = (orph[o.node_id] || []).concat(o.kind || ''); });
    var dord = {};
    return (rq.requirements || []).map(function (u) {
      var key = u.document_id + ':' + u.requirement_id;
      var mine = all.filter(function (it) { return it.req === u.requirement_id; }), open = mine.filter(function (it) { return it.open; });
      var worst = open.filter(function (it) { return it.kind === 'f'; }).reduce(function (a, it) { return a == null || SEV_ORDER[it.sev] < SEV_ORDER[a] ? it.sev : a; }, null);
      var tv = (t[key] || t[u.requirement_id] || {}).verdict || null;
      var notest = (orph[key] || orph[u.requirement_id] || []).some(function (k) { return /test/i.test(k); });
      var inf = Object.keys(u.fields || {}).some(function (k) { return u.fields[k] && u.fields[k].provenance === 'INFERRED'; });
      var cf = open.some(function (it) { return it.kind === 'c'; });
      var st = open.length ? ['要対応', 'attention'] : (tv === 'CAN_TEST' ? ['問題なし', 'ok'] : ['判定材料なし', 'unknown']);
      if (!(u.document_id in dord)) dord[u.document_id] = Object.keys(dord).length;
      return { di: dord[u.document_id], u: u, key: key, open: open.length, all: mine.length, worst: worst, tv: tv, cf: cf, notest: notest, inf: inf, changed: !!ch[u.requirement_id], st: st };
    });
  }
  function itemLine(it) { return (it.req ? it.req + ' ' : '') + actionTitle(it); }
  function priorities() { return buildModel().filter(function (it) { return it.open; }).map(function (it) { return { text: itemLine(it), go: 'f', id: it.key }; }); }
  function rawScore(sc) { return sc && sc.value != null ? Number(sc.value) : null; }
  function scoreText(sc) {
    if (!sc) return '未評価';
    if (sc.value == null) return '評価不能（評価できた範囲 ' + pct(sc.coverage) + '%）';
    return Math.round(sc.value) + '%';
  }
  /* 題の生成: 固定文字数で切らない。要件の原文から対象名（最初の名詞句＝助詞の手前）を語の境界で取り、規則別の型に入れる。省略は CSS に任せる */
  function stripId(t) { return String(t || '').replace(/^\s*(?:[A-Z]{2,}-\d+|\d+[.．])\s*/, '').replace(/[。．.]\s*$/, ''); }
  function topicOf(t) { var s = stripId(t), m = s.match(/^(.+?)(?:は|を|が|で|に|へ)/); return m ? m[1] : ''; }
  var VERB = /([一-龥ァ-ヶー]+)(?:する|される|できる)/;
  function phraseOf(t, after) {
    var s = stripId(t), tp = topicOf(s), rest = after != null ? after : s.slice(tp.length + 1);
    var o = rest.match(/^(?:[^、。]*?[、]\s*)?([一-龥ァ-ヶー]+(?:の[一-龥ァ-ヶー]+)*)を([一-龥ァ-ヶー]+)(?:する|される|できる)/);
    if (o) return o[1] + 'の' + o[2];
    var v = rest.match(VERB); if (v && !/検討|決定|調整/.test(v[1]) && tp) return tp + 'の' + v[1];
    return tp;
  }
  /* 題の折り返しは語の境界だけ（Intl.Segmenter で語に分け <wbr> を挟む。CSS は keep-all） */
  var SEG = (typeof Intl !== 'undefined' && Intl.Segmenter) ? new Intl.Segmenter('ja', { granularity: 'word' }) : null;
  function ttl(t) { if (!SEG) return esc(t); var o = ''; for (var it = SEG.segment(String(t))[Symbol.iterator](), r = it.next(); !r.done; r = it.next()) o += esc(r.value.segment) + '<wbr>'; return o; }
  function ruleName(x) { return x.title || '指摘'; }
  function actionTitle(it) {
    if (it.kind === 'c') return '「' + (it.short || '記述') + '」の食い違いを解消する';
    var txt = it.reqText, tp = topicOf(txt);
    if (it.kind === 't') { var miss = (it.raw.missing || [])[0] || '合否の基準', ph = phraseOf(txt); return (ph ? '「' + ph + '」の' : '') + miss + 'を定義する'; }
    var x = it.raw, k = (x.rule_id || '') + ' ' + (x.title || ''), r = String(x.reason || ''), q = r.match(/「([^」]{1,30})」/);
    if (/AMB|曖昧/i.test(k) && q) { var at = stripId(txt).indexOf(q[1]), ph2 = phraseOf(txt, at >= 0 ? stripId(txt).slice(at + q[1].length) : null); return '「' + q[1] + '」の基準を決める' + (ph2 ? '（' + ph2 + '）' : ''); }
    if (/TBD|未決/i.test(k)) return (tp ? tp + 'を' : '未決事項を') + '決める';
    if (/ITEMS|必須/i.test(k)) { var cat = r.match(/^(.+?)の必須項目/); return (cat ? cat[1] + 'の' : '') + '必須項目' + (q ? '「' + q[1] + '」' : '') + 'を文書に追加する'; }
    if (/ID-004|孤立/i.test(k)) { var ph3 = phraseOf(txt); return (ph3 ? '「' + ph3 + '」の要件' : '要件 ' + (it.req || '')) + 'の参照先を確認する'; }
    if (/ID-002|欠番/i.test(k)) { var g = r.match(/欠番[:：]\s*(.+)$/); return '要件 ID の欠番' + (g ? '（' + g[1] + '）' : '') + 'を確認する'; }
    return (tp ? tp + 'の' : '') + ruleName(x) + 'を確認する';
  }
  var QNAME = { Clarity: '明確さ', Completeness: '網羅性', Consistency: '一貫性', Testability: 'テスト可能性', Traceability: 'トレーサビリティ', Measurability: '測定可能性', Atomicity: '単一性', Overall: '総合' };
  function human(t) {
    return String(t || '').replace(/\b(Clarity|Completeness|Consistency|Testability|Traceability|Measurability|Atomicity|Overall)\b/g, function (k) { return QNAME[k]; })
      .replace(/\bCONDITIONALLY_READY\b|\bREVIEWABLE\b/g, '条件付き').replace(/\bREADY\b/g, '準備完了').replace(/\bBLOCKED\b/g, 'ブロック').replace(/\bNOT_TESTABLE\b/g, 'テスト不可')
      .replace(/主要次元/g, '主要な観点').replace(/のため\s*準備完了\s*にしない/, 'のため、準備完了にしていません');
  }
  var ICON_OK = '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><circle cx="8" cy="8" r="6.5"/><path d="M5 8.2l2 2 4-4.2"/></svg>';
  var ICON_WARN = '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><circle cx="8" cy="8" r="6.5"/><path d="M8 4.5v4M8 11v.5"/></svg>';
  function openCount() { return buildModel().filter(function (it) { return it.open; }).length; }
  function overviewHtml() {
    var rd = readiness();
    if (!rd && notRun('scores') && notRun('requirements')) return emptyBox();
    var st = rd ? (READY[rd.state] || ['ドラフト', 'draft']) : ['ドラフト', 'draft'];
    var all = buildModel(), open = all.filter(function (it) { return it.open; }), n = open.length, sc = scores();
    var rm = reqModel(), tot = rm.length, nt = open.filter(function (it) { return it.kind === 't'; }).length, dec = all.length - n;
    var closable = all.filter(function (it) { return it.kind !== 't'; }).length, nf = open.filter(function (it) { return it.kind === 'f'; }).length, nc = open.filter(function (it) { return it.kind === 'c'; }).length;
    var miss = gateMiss(), na = naCount(), ai = mode() === 'DETERMINISTIC_ONLY';
    var v3 = verdict3(rd, open, miss), apiWhy = (rd && rd.reasons) || [];
    var NUM = '①②③④⑤⑥⑦⑧⑨', condAll = open.map(function (it) { return itemLine(it); }).concat(miss.map(function (m) { return m.name + 'を ' + GATE.min + ' 以上にする（現在 ' + m.v + '）'; })), conds = condAll.slice(0, 3);
    var condHtml = v3[1] === 'ready' ? '' : '<div class="dax-ready__why"><span class="dax-ready__k">条件</span><ol class="dax-conds">' + conds.map(function (c, i) { return '<li><span class="dax-conds__n" aria-hidden="true">' + NUM.charAt(i) + '</span>' + esc(c) + '</li>'; }).join('')
      + (condAll.length > 3 ? '<li class="dax-conds__more"><button type="button" class="dax-link" data-tab-go="issues" data-fstate="open">すべて見る</button></li>' : '') + '</ol></div>';
    var naRow = na ? '<p class="dax-ready__one">' + esc(naNames().join('・')) + 'を評価する受入基準が不足しています。</p>' : '';
    var h = '<section class="dax-ready dax-ready--' + v3[1] + '" aria-label="判定"><div class="dax-ready__main">'
      + '<div class="dax-ready__head"><span class="dax-ready__icon" aria-hidden="true">' + (v3[1] === 'ready' ? ICON_OK : ICON_WARN) + '</span>'
      + '<h2 class="dax-ready__title" title="' + esc('判定: ' + v3[0] + '。' + GATE.note) + '">' + esc(v3[2]) + '</h2>'
      + '</div>'
      + naRow
      + (apiWhy.length && !na ? '<div class="dax-ready__why"><span class="dax-ready__k">判定の理由</span><ul class="dax-ready__rs">' + apiWhy.slice(0, 1).map(function (x) { return '<li>' + esc(human(x)) + '</li>'; }).join('') + '</ul></div>' : '')
      + (ai ? '<p class="dax-ready__ai"><span class="dax-info dax-info--static" aria-hidden="true">i</span>AI レビューは実行していません。規則による解析のみで判定しています。</p>' : '')
      + '</div><div class="dax-ready__act">' + (n ? '' : '<button type="button" class="dax-btn dax-btn--primary" data-act="run"' + (S.busy ? ' disabled' : '') + '>' + (S.busy ? '解析中…' : '再解析') + '</button>') + '</div></section>';
    // KPI 帯（3 指標）。大きな数字は無彩色。分母と単位を必ず添える。棒は「進んだ量」（判断済み）だけ
    var kpi = function (label, val, sub, attrs, bar) {
      return '<button type="button" class="dax-kpi"' + attrs + '><span class="dax-kpi__label">' + label + '</span><span class="dax-kpi__value">' + val + '</span>'
        + (bar == null ? '' : '<span class="dax-bar dax-bar--progress" aria-hidden="true"><span style="width:' + bar + '%"></span></span>') + '<span class="dax-kpi__sub">' + sub + '</span></button>';
    };
    var nd = n - nt;
    var band = '<div class="dax-band"><p class="dax-band__h">判定の根拠（100 点満点。赤字の −n は合格線 ' + GATE.min + ' との差）</p><div class="dax-band__row">' + QUAL.map(function (q) { var s2 = sc[q[0]], v = s2 && s2.value != null ? Math.round(Number(s2.value)) : null, df = v == null ? 0 : v - GATE.min;
      return '<button type="button" class="dax-bc' + (v == null ? ' dax-bc--na' : df < 0 ? ' dax-bc--low' : '') + '" data-score="' + q[0] + '" title="' + esc(q[1] + '：' + (v == null ? '評価不能（' + naReason(s2) + '）' : v + ' / 100' + (df < 0 ? '（合格線まで ' + (-df) + '）' : '（合格）'))) + '"><span class="dax-bc__n">' + q[1] + '</span><span class="dax-bc__v">' + (v == null ? '評価不能' : v + (df < 0 ? '<span class="dax-bc__d">−' + (-df) + '</span>' : '')) + '</span></button>'; }).join('') + '</div>'
      + (function () { var tc = (body('trace') || {}).coverage || {}, f = function (k, l) { var c = tc[k]; return c && c.total != null && c.count != null ? l + ' ' + c.count + ' / ' + c.total : null; }, parts = [f('design', '設計'), f('test_designed', 'テスト設計')].filter(Boolean);
        return '<p class="dax-band__cov">' + (parts.length ? '被覆（追跡対象の要件）：' + esc(parts.join('・')) + ' ・ ' : '') + '<button type="button" class="dax-link" data-tab-go="trace">トレーサビリティで見る</button></p>'; })() + '</div>';
    var bi = h.indexOf('</section>'); h = h.slice(0, bi) + band + h.slice(bi);
    h += '<section class="dax-qcards" aria-label="観点スコア">' + QUAL.map(function (q) {
      var s = sc[q[0]], v = s && s.value != null ? Math.round(Number(s.value)) : null, low = v != null && v < GATE.min, df = v == null ? 0 : v - GATE.min;
      return '<button type="button" class="dax-qc' + (low ? ' dax-qc--low' : '') + (v == null ? ' dax-qc--na' : '') + '" data-score="' + q[0] + '"><span class="dax-qc__name">' + q[1] + '</span>'
        + '<span class="dax-qc__row"><span class="dax-qc__num">' + (v == null ? '—' : v + '<small>点</small>') + '</span>' + (v == null ? '<span class="dax-qc__diff">評価不能</span>' : '<span class="dax-qc__diff">基準比 ' + (df < 0 ? '−' : '+') + Math.abs(df) + '</span>') + '</span>'
        + '<span class="dax-qc__badge">' + (!s ? '<span class="dax-badge">未評価</span>' : v == null ? '<span class="dax-badge dax-badge--na">評価不能</span>' : low ? '<span class="dax-tag dax-tag--warn">基準未達</span>' : '<span class="dax-badge">基準以上</span>') + '</span></button>';
    }).join('') + '</section>';
    var gm = {}, groups = []; open.forEach(function (it) { var k = it.req || ('_' + it.key); if (!gm[k]) { gm[k] = []; groups.push(gm[k]); } gm[k].push(it); });
    var rows = open.slice(0, window.innerWidth >= 1200 ? 10 : 5).map(function (it) { var sib = it.req ? gm[it.req].filter(function (x) { return x !== it; }) : []; return Object.assign({}, it, { more: sib.length, moreT: sib.map(actionTitle).join('／') }); });
    h += '<section class="dax-sec dax-sec--must" aria-labelledby="dx-must"><div class="dax-sec__head"><h2 class="dax-sec__title" id="dx-must">確認待ち ' + n + ' 件</h2>' + (n ? '<button type="button" class="dax-btn dax-btn--primary dax-btn--sm" data-tab-go="issues" data-fstate="open" title="判断 ' + (n - nt) + ' 件・文書の修正 ' + nt + ' 件">指摘を判断する（' + n + '）</button>' : '') + '</div>'
      + '<p class="dax-sec__lead">重要度 高 ' + open.filter(function (x) { return sev3(x.sev)[1] === 'high'; }).length + '／中 ' + open.filter(function (x) { return sev3(x.sev)[1] === 'medium'; }).length + '／低 ' + open.filter(function (x) { return sev3(x.sev)[1] === 'low'; }).length + '・重要度順の上位 ' + rows.length + ' 件' + '</p>'
      + (n ? '<table class="dax-todo"><colgroup><col><col style="width:84px"><col style="width:100px"><col style="width:28px"></colgroup><thead><tr><th scope="col">確認すること</th><th scope="col">要件</th><th scope="col">種類</th><th scope="col"><span class="dax-sr">開く</span></th></tr></thead><tbody>' + rows.map(function (it) {
        return '<tr tabindex="0" data-pgo="f" data-pid="' + esc(it.key) + '" aria-label="' + esc(actionTitle(it)) + '"><td><span class="dax-todo__title" title="' + esc(actionTitle(it)) + '">' + ttl(actionTitle(it)) + '</span><span class="dax-todo__why"' + (it.more ? ' title="' + esc(it.moreT) + '"' : '') + '>' + esc(whyOf(it) || it.short) + (it.more ? ' ・ 同じ要件にほか ' + it.more + ' 件' : '') + '</span></td><td class="dax-todo__id">' + esc(it.req || '—') + '</td><td><span class="dax-kt dax-kt--' + (it.kind === 'c' ? 'c' : it.kind === 't' ? 't' : isTbd(it.raw) ? 'tbd' : 'r') + '" title="重要度 ' + sev3(it.sev)[0] + '">' + esc(it.kindLabel || it.label) + '</span></td><td class="dax-todo__go" aria-hidden="true">' + CHEV + '</td></tr>';
      }).join('') + '</tbody></table><div class="dax-sec__more dax-tfoot"><button type="button" class="dax-link" data-tab-go="issues" data-fstate="open">すべて見る（' + n + ' 件）</button><span class="dax-tfoot__r"><button type="button" class="dax-link" data-tab-go="diff">最近の変更</button><button type="button" class="dax-link" data-tab-go="trace">トレーサビリティ</button></span></div>'
      : '<p class="dax-sec__empty">検出なし（検出できた範囲）。検出が無いことは、問題が無いことの証明ではありません。</p>') + '</section>';
    var qrows = QUAL.map(function (q) {
      var s = sc[q[0]], na = !s || s.value == null, w = na ? null : Math.max(0, Math.min(100, Math.round(s.value)));
      var low = w != null && w < GATE.min, df = w == null ? 0 : w - GATE.min, tone = low ? (df <= -30 ? 'danger' : 'warn') : '';
      var sub = !s ? '未評価。解析すると評価されます' : na ? (s.reason || s.not_evaluable_reason || '評価できた要件がありません') : '評価できた範囲 ' + pct(s.coverage) + '%';
      return '<button type="button" class="dax-q' + (low ? ' dax-q--low dax-q--' + tone : '') + (na || !s ? ' dax-q--na' : '') + '" data-score="' + q[0] + '" title="' + esc(sub) + '"><span class="dax-q__name">' + q[1] + '</span>'
        + (na || !s ? '<span class="dax-q__reason">' + esc(sub) + '</span>' : '<span class="dax-bar" aria-hidden="true"><span style="width:' + w + '%"></span><i style="left:' + GATE.min + '%"></i></span>'
        + '<span class="dax-q__num">' + w + '</span>'
        + '<span class="dax-q__diff' + (low ? ' dax-q__diff--' + tone : '') + '">' + (df < 0 ? '−' : '+') + Math.abs(df) + '</span>')
        + '<span class="dax-q__badge">' + (!s ? '<span class="dax-badge">未評価</span>' : na ? '<span class="dax-badge dax-badge--na">評価不能</span>' : low ? '<span class="dax-tag dax-tag--warn">基準未達</span>' : '') + '</span></button>';
    }).join('');
    var can = rm.filter(function (m) { return m.tv === 'CAN_TEST' || m.tv === 'PARTIALLY_TESTABLE'; }).length;
    var linked = body('trace') && body('trace').graph ? rm.filter(function (m) { return !m.notest; }).length : null;
    void can; void linked;
    var ch = changedIds(), chN = Object.keys(ch).length;
    var moreBody = (chN ? '<p>変更のあった要件 ' + chN + ' 件：' + Object.keys(ch).slice(0, 8).map(function (k) { return '<span class="dax-tag">' + esc(k) + '</span>'; }).join(' ') + '</p>' : '<p class="dax-meta">前の版との差分は「変更」で確認できます。</p>') + '<button type="button" class="dax-btn dax-btn--sm" data-tab-go="diff">変更を見る</button>'
      + (rd && (rd.reasons || []).length ? '<ul>' + rd.reasons.map(function (x) { return '<li>' + esc(human(x)) + '</li>'; }).join('') + '</ul>' : '');
    void moreBody; void chN;
    return h;
  }
  function frow2(label, v, t) { var w = t ? Math.round(v / t * 100) : null; return '<div class="dax-cov__row"><span class="dax-cov__label">' + label + '</span>' + (w == null ? '<span class="dax-badge">対象なし</span>' : '<span class="dax-bar dax-bar--progress" aria-hidden="true"><span style="width:' + w + '%"></span></span><span class="dax-cov__value">' + v + '<small> / ' + t + '</small></span>') + '</div>'; }
  function scoreDrawer(key, trigger) {
    var sc = scores()[key], label = (QUAL.filter(function (q) { return q[0] === key; })[0] || [0, key])[1];
    var list = function (a) { return a && a.length ? '<ul>' + a.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : '<p class="dax-meta">なし</p>'; };
    var h = !sc ? '<p>未評価です。解析すると評価されます。</p>' : (sc.value == null ? '<p>評価不能です。点数は付けていません（評価できた範囲 ' + pct(sc.coverage) + '%）。</p>' : '<p>' + Math.round(sc.value) + '%（評価できた範囲 ' + pct(sc.coverage) + '%）</p>')
      + (sc ? '<h3 class="dax-h3">主な理由</h3>' + list(sc.explanation) + disc('sc-' + key, '根拠の詳細', '<h3 class="dax-h3">評価に含めたもの</h3>' + list(sc.included) + '<h3 class="dax-h3">評価できなかったもの</h3>' + list(sc.not_evaluated)) : '');
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
      return !q || (m.u.requirement_id + ' ' + (m.u.document_id || '') + ' ' + (m.u.raw_text || '')).toLowerCase().indexOf(q) >= 0;
    }).sort(function (a, b) { var sv = function (m) { return m.worst ? SEV_ORDER[m.worst] : 99; }, c = String(a.u.requirement_id).localeCompare(String(b.u.requirement_id), 'ja', { numeric: true }), d = S.reqDesc ? -1 : 1;
      if (S.reqSort === 'id') return d * c || (a.di - b.di);
      return d * ((sv(a) - sv(b)) || (b.open - a.open)) || c || (a.di - b.di); });
  }
  function reqDoc(d) { var M = { REQ: '要件定義書', DES: '基本設計書' }; return M[String(d || '').toUpperCase()] || String(d || '—'); }
  var REQ_CHIP_HELP = { attention: '要対応＝未対応の指摘または矛盾が 1 件以上ある要件（矛盾ありを含む）', nt: 'テスト不可＝合否基準を書けない記述と判定された要件。要対応とは別の観点（重なることがある）', cf: '矛盾ありは要対応の一部。文書間の矛盾に関わる要件で、矛盾 1 件は両方の文書の要件として 2 件に数える', notest: 'テストなし＝テストケースへのつながりが無い要件。テストを書けるかどうか（テスト不可）とは別', changed: '前回の解析から記述が変わった要件' };
  function reqCount(all, rows) { return '表示 ' + rows.length + '／' + all.length + ' 件'; }
  function reqBody(u) { var t = String(u.raw_text || u.snippet || ''), id = String(u.requirement_id || ''); return id && t.indexOf(id) === 0 ? t.slice(id.length).replace(/^[\s:：.、]+/, '') : t; }
  function reqChipHit(m, c) { return c === 'attention' ? m.st[1] === 'attention' : c === 'nt' ? m.tv === 'NOT_TESTABLE' : c === 'cf' ? m.cf : c === 'notest' ? m.notest : c === 'changed' ? m.changed : false; }
  function reqDocAbbr(d) { var M = { REQ: '要', DES: '基' }; return M[String(d || '').toUpperCase()] || String(d || '—').slice(0, 2); }
  function reqRowsHtml(rows) {
    if (!rows.length) return '<tr><td colspan="9">この条件に当てはまる要件はありません。絞り込みを「すべて」に戻してください。</td></tr>';
    var gm = {}, order = [];
    rows.forEach(function (m) { var id = m.u.requirement_id; if (!gm[id]) { gm[id] = []; order.push(id); } gm[id].push(m); });
    var byId = {}; reqModel().forEach(function (m) { (byId[m.u.requirement_id] = byId[m.u.requirement_id] || []).push(m); });
    var norm = function (m) { return reqBody(m.u).replace(/[\s。．.、，,]/g, ''); };
    var flat = []; order.forEach(function (id) { gm[id].slice().sort(function (a, b) { return a.di - b.di; }).forEach(function (m) { flat.push(m); }); });
    var seenId = {};
    return flat.map(function (m) {
      var second = !!seenId[m.u.requirement_id]; seenId[m.u.requirement_id] = 1;
      var id = m.u.requirement_id, txt = reqBody(m.u), dn = reqDoc(m.u.document_id), hi = m.worst === 'critical' || m.worst === 'high';
      var x = m.open ? ['要対応', 'attention'] : m.all ? ['確認済み', 'done'] : ['問題なし', 'ok'];
      var differs = (byId[id] || []).some(function (o) { return o !== m && norm(o) !== norm(m); });
      var tags = (m.cf ? '<span class="dax-reqtag dax-reqtag--cf">矛盾</span>' : '') + (m.changed ? '<span class="dax-reqtag">変更あり</span>' : '') + (m.inf ? '<span class="dax-reqtag">推測を含む</span>' : '');
      return '<tr tabindex="0" data-req="' + esc(m.key) + '"' + (hi ? ' class="dax-reqrow--hi"' : '') + (S.reqSel === m.key ? ' aria-current="true"' : '') + ' aria-label="' + esc(id + '（' + dn + '）' + x[0] + '。Enter で詳細') + '">'
        + '<td class="dax-reqidc"><span class="dax-reqid">' + esc(id) + '</span><span class="dax-reqdoc" title="' + esc(dn) + '">' + esc(reqDocAbbr(m.u.document_id)) + '</span></td>'
        + '<td class="dax-reqtxt" title="' + esc(dn + '：' + txt) + '">' + (differs && second ? '<span class="dax-reqdiff" title="同じ ID の他の文書と記述が異なります（どちらが正しいかは判定していません）">他文書と相違</span>' : '') + '<span class="dax-reqtxt__t">' + esc(txt) + '</span>' + tags + '</td>'
        + '<td><span class="dax-reqst dax-reqst--' + x[1] + '">' + x[0] + '</span></td>'
        + '<td class="dax-reqq">' + (m.worst ? '<span class="dax-reqsev dax-reqsev--' + esc(m.worst) + '">' + esc(SEV[m.worst] || '') + '</span>' : '<span class="dax-reqsev dax-reqsev--none">—</span>') + (m.open ? '<span class="dax-reqq__n">' + m.open + ' 件</span>' : '') + '</td>'
        + '<td>' + esc(m.tv ? TEST[m.tv] || '判定不能' : '未判定') + '</td>'
        + (S.cols.kind ? '<td>' + esc(KIND[m.u.kind] || m.u.kind || '—') + '</td>' : '') + (S.cols.doc ? '<td>' + esc(dn) + '</td>' : '') + (S.cols.infer ? '<td>' + (m.inf ? '推測を含む' : '—') + '</td>' : '') + '<td class="dax-reqgo" aria-hidden="true">›</td></tr>';
    }).join('');
  }
  function reqHtml() {
    if (!body('requirements')) return notRun('requirements') ? emptyBox() : failBox();
    var all = reqModel();
    if (!all.length) return stateBox('empty', '要件が見つかりません', '文書に要件の記述があるか確認し、取り込み直してから再解析してください。', RUN_BTN);
    var rows = reqRows();
    var chips = '<div class="dax-chips dax-reqseg" role="group" aria-label="絞り込み"><button type="button" class="dax-chip" aria-pressed="' + !S.chip + '" data-chip="">すべて <span class="dax-segc__n">' + all.length + '</span></button>' + REQ_CHIPS.map(function (c) {
      var n = all.filter(function (m) { return reqChipHit(m, c[0]); }).length;
      if (!n && S.chip !== c[0]) return '';
      return '<button type="button" class="dax-chip" aria-pressed="' + (S.chip === c[0]) + '" data-chip="' + c[0] + '" title="' + esc(REQ_CHIP_HELP[c[0]] || '') + '">' + c[1] + ' <span class="dax-segc__n">' + n + '</span></button>'; }).join('') + '</div>';
    var colsel = pop('cols', '列' + CARET, 'dax-btn dax-btn--sm', '', OPT_COLS.map(function (c) { return '<button type="button" role="menuitemcheckbox" class="dax-pop__item" aria-checked="' + !!S.cols[c[0]] + '" data-colt="' + c[0] + '"><span class="dax-check" aria-hidden="true"></span>' + c[1] + '</button>'; }).join(''));
    var head = '<tr><th scope="col" aria-sort="' + (S.reqSort === 'id' ? (S.reqDesc ? 'descending' : 'ascending') : 'none') + '"><button type="button" class="dax-reqsort" data-reqsort="id" title="ID 順で並べ替え">ID ' + (S.reqSort === 'id' ? (S.reqDesc ? '↓' : '↑') : '') + '</button></th><th scope="col">要件</th><th scope="col">状態</th><th scope="col" aria-sort="' + (S.reqSort === 'id' ? 'none' : S.reqDesc ? 'ascending' : 'descending') + '"><button type="button" class="dax-reqsort" data-reqsort="sev" title="重大度順（高い順→未対応件数）で並べ替え">未対応の指摘 ' + (S.reqSort === 'id' ? '' : S.reqDesc ? '↑' : '↓') + '</button></th><th scope="col">テスト可能性</th>'
      + OPT_COLS.filter(function (c) { return S.cols[c[0]]; }).map(function (c) { return '<th scope="col">' + c[1] + '</th>'; }).join('') + '<th scope="col" class="dax-reqgo"><span class="dax-sr">開く</span></th></tr>';
    return '<div class="dax-toolbar dax-reqbar"><input type="search" class="dax-search" id="dx-q" placeholder="ID・文書・本文で検索" aria-label="要件を検索" value="' + esc(S.q) + '">' + chips + colsel + '<span class="dax-meta dax-reqbar__cnt" role="status" id="dx-cnt">' + reqCount(all, rows) + '</span></div>' + (S.chip && REQ_CHIP_HELP[S.chip] ? '<p class="dax-meta dax-reqhelp">' + esc(REQ_CHIP_HELP[S.chip]) + '</p>' : '')
      + '<div class="dax-table-wrap"><table class="dax-table dax-reqtable"><thead>' + head + '</thead><tbody id="dx-rows">' + reqRowsHtml(rows) + '</tbody></table></div>';
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
      + disc('rq-' + u.requirement_id, '根拠の詳細', ((tc.reasons || []).length ? '<ul>' + tc.reasons.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : '<p class="dax-meta">テスト可能性の判定理由はありません。</p>') + (u.snippet && u.snippet !== u.raw_text ? '<p>' + esc(u.snippet) + '</p>' : ''))
      + sec('履歴', m.changed ? '<p>前の版から変更があります。<button type="button" class="dax-btn dax-btn--ghost dax-btn--sm" data-tab-go="diff">変更を見る</button></p>' : '<p class="dax-meta">前の版との差分は記録されていません。</p>');
    var firstOpen = mine.filter(function (it) { return it.open; })[0];
    h += '<div data-foot>' + (firstOpen ? '<button type="button" class="dax-btn dax-btn--primary" data-pgo="f" data-pid="' + esc(firstOpen.key) + '">この指摘を判断する</button>' : '<button type="button" class="dax-btn dax-btn--ghost" data-drawer-close>閉じる</button>') + '</div>';
    showDrawer(u.requirement_id + '（文書 ' + (u.document_id || '—') + '）　' + reqBody(u).slice(0, 40), h, trigger);
    var reqId = u.requirement_id; S.reqSel = key;
    Array.prototype.forEach.call(document.querySelectorAll('#dx-rows tr[data-req]'), function (r) { if (r.dataset.req === key) r.setAttribute('aria-current', 'true'); else r.removeAttribute('aria-current'); });
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
    var fs = S.fstate || 'open';
    var inState = function (it, s) { return s === 'all' || (s === 'open' ? it.open : !it.open); };
    var bySel = function (it) { return (!S.fsevF || sev3(it.sev)[1] === S.fsevF) && (!S.fkind || (it.kindLabel || it.label) === S.fkind); };
    var fq = (S.fq || '').trim().toLowerCase(), byQ = function (it) { return !fq || ((it.req || '') + ' ' + actionTitle(it)).toLowerCase().indexOf(fq) >= 0; };
    var list = all.filter(function (it) { return inState(it, fs) && bySel(it) && byQ(it); });
    if (S.fsort === 'req') { var rn = function (it) { return it.req ? String(it.req) : '\uffff'; }; list = list.slice().sort(function (a, b) { return rn(a) < rn(b) ? -1 : rn(a) > rn(b) ? 1 : 0; }); }
    if (!list.some(function (it) { return it.key === S.selF; })) { var r0 = list.filter(function (it) { return it.open && it.kind === 'f' && !isTbd(it.raw); })[0]; S.selF = r0 ? r0.key : (list.length ? list[0].key : null); }
    S.flist = list.map(function (it) { return it.key; }); S.fall = all;
    var kinds = []; all.forEach(function (it) { var k = it.kindLabel || it.label; if (kinds.indexOf(k) < 0) kinds.push(k); });
    var sevs = ['high', 'medium', 'low', 'none'].filter(function (k) { return all.some(function (it) { return sev3(it.sev)[1] === k; }); });
    var tabs = '<div class="dax-toolbar dax-ftool"><div class="dax-segc" role="tablist" aria-label="状態で切り替え">' + FSTATE.map(function (s) {
      var c = all.filter(function (it) { return inState(it, s[0]); }).length;
      return '<button type="button" role="tab" class="dax-segc__opt" aria-selected="' + (fs === s[0]) + '" tabindex="' + (fs === s[0] ? '0' : '-1') + '" data-fstate-tab="' + s[0] + '">' + s[1] + ' <span class="dax-segc__n">' + c + '</span></button>'; }).join('') + '</div>'
      + '<div class="dax-fsel"><input type="search" class="dax-search dax-fsearch" id="dx-fq" placeholder="検索" aria-label="指摘を検索" value="' + esc(S.fq || '') + '">' + dd('sort', '並び順', [['', '重要度順'], ['req', '要件順']], S.fsort || '') + dd('sev', '重要度', [['', 'すべて']].concat(sevs.map(function (k) { return [k, { high: '高', medium: '中', low: '低' }[k] || '未評価']; })), S.fsevF || '')
      + dd('kind', '種類', [['', 'すべて']].concat(kinds.map(function (k) { return [k, k]; })), S.fkind || '') + '</div></div>';
        var nDone = all.filter(function (it) { return !it.open; }).length;
        var items = '<div class="dax-md__list" role="listbox" aria-label="指摘の一覧"><div class="dax-fprog" role="presentation"><span>処理済み ' + nDone + '/' + all.length + '</span><i style="--p:' + (all.length ? Math.round(nDone * 100 / all.length) : 0) + '%"></i></div>' + (list.length ? list.map(function (it) {
      return '<button type="button" role="option" class="dax-item' + (it.open ? '' : ' dax-item--done') + '" tabindex="' + (it.key === S.selF ? '0' : '-1') + '" aria-selected="' + (it.key === S.selF) + '" data-fid="' + esc(it.key) + '"><span class="dax-item__title" title="' + esc(actionTitle(it)) + '">' + esc(actionTitle(it)) + '</span>'
        + '<span class="dax-item__meta">' + sevDot(it.sev) + '<span class="dax-item__sub">' + esc(it.kindLabel || it.label) + ' · ' + esc(it.req || '要件なし') + '</span>' + statPill(itemStat(it)) + '</span></button>';
    }).join('') : '<p class="dax-meta dax-md__none">' + (fs === 'open' ? '未解決の指摘はありません。' : 'この条件に当てはまる指摘はありません。') + '</p>') + '</div>';
    var sel = list.filter(function (it) { return it.key === S.selF; })[0];
    return tabs + '<div class="dax-md"><div class="dax-md__left">' + items + '</div><div class="dax-md__detail" aria-live="polite">' + (sel ? itemDetail(sel) : '<div class="dax-md__body"><p class="dax-meta">この条件に当てはまる指摘はありません。絞り込みを「すべて」に戻してください。</p></div>') + '</div></div>';
  }
  function sevTag(it) { return sevDot(it.sev); }
  /* 詳細ヘッダの「n/N ‹ ›」と、同じ要件の別の指摘 */
  function fnavHtml(it) {
    var L = S.flist || [], i = L.indexOf(it.key); if (i < 0) return '';
    var b = function (d, lab, sym, dis) { return '<button type="button" class="dax-fnav__b" data-fnav="' + d + '" aria-label="' + lab + '（' + (d > 0 ? 'J' : 'K') + '）"' + (dis ? ' disabled' : '') + '>' + sym + '</button>'; };
    return '<div class="dax-fnav" aria-label="指摘の移動"><span class="dax-fnav__n">' + (i + 1) + '/' + L.length + '</span>' + b(-1, '前の指摘', '‹', i === 0) + b(1, '次の指摘', '›', i === L.length - 1) + '</div>';
  }
  function fsibHtml(it) {
    if (!it.req) return '';
    var sib = (S.fall || []).filter(function (o) { return o.req === it.req && o.key !== it.key; }); if (!sib.length) return '';
    return '<button type="button" class="dax-link dax-fsib" data-pgo="f" data-pid="' + esc(sib[0].key) + '" title="' + esc(sib.map(actionTitle).join(' / ')) + '">同じ要件のほかの指摘 ' + sib.length + ' 件</button>';
  }
  /* 行の状態は 3 語だけ: 判断待ち（規則・矛盾）／要修正（文書）（テスト不可）／判断済み */
  function itemStat(it) { if (it.kind === 't') return ['要修正', 'fix']; return it.open ? ['要判断', 'decision'] : ['判断済み', 'done']; }
  function props(it, extra) {
    var p = function (l, v) { return '<div class="dax-props__row"><dt>' + l + '</dt><dd>' + v + '</dd></div>'; };
    return '<dl class="dax-props">' + p('重要度', sevDot(it.sev)) + p('種類', kindTag(it)) + p('状態', statPill(itemStat(it))) + p('要件', esc(it.req || '要件なし')) + (extra || '') + '</dl>';
  }
  function itemDetail(it) {
    if (it.kind === 'f') return findingDetail(it.raw, it);
    var sec = function (t, inner) { return '<section class="dax-detail__section"><h3 class="dax-h3">' + t + '</h3>' + inner + '</section>'; };
    var head = '<header class="dax-md__head"><div class="dax-md__hmeta">' + sevDot(it.sev) + '<span class="dax-item__sub">' + esc(it.kindLabel || it.label) + '</span>' + statPill(itemStat(it)) + (it.req ? '<button type="button" class="dax-reqlink" data-reqid="' + esc(it.req) + '">' + '<svg class="dax-reqlink__i" viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M9 3h4v4M13 3 7.5 8.5M11 9.5V13H3V5h3.5"/></svg>' + '要件 ' + esc(it.req) + '</button>' : '<span class="dax-meta">要件なし</span>') + fnavHtml(it) + '</div><h2 class="dax-dh__title">' + ttl(actionTitle(it)) + '</h2>' + fsibHtml(it) + '</header>';
    var foot = it.kind === 't'
      ? '<footer class="dax-dbar dax-dbar--ro" aria-label="対応"><div class="dax-dbar__row">' + (it.req ? '<button type="button" class="dax-btn dax-btn--primary" data-reqid="' + esc(it.req) + '">要件を開く</button>' : '')
        + '<p class="dax-dbar__ro">文書を直して再解析すると解消します</p></div></footer>'
      : '<footer class="dax-dbar dax-dbar--ro" aria-label="対応"><div class="dax-dbar__row"><button type="button" class="dax-btn dax-btn--primary" data-tab-go="conf">正とする記述を選ぶ</button></div></footer>';
    return head + '<div class="dax-md__body">' + itemDetailBody(it, sec, '') + '</div>' + foot;
  }
  function reqQuote(it, bare) {
    var u = it.reqU; if (!u) return it.req ? '<p class="dax-meta">要件 ' + esc(it.req) + '</p>' : '';
    var loc = u.location || {}, line = u.line_start || loc.line_start;
    return '<figure class="dax-quote"><figcaption>原文' + (bare ? '' : ' ・ ' + esc(u.document_id || '') + (line ? '（行 ' + esc(line) + '）' : '') + ' ・ ' + esc(u.requirement_id)) + '</figcaption><blockquote>' + quoteHtml(u.raw_text || u.snippet || '') + '</blockquote></figure>';
  }
  /* 根拠の詳細＝出典だけ（文書・行・要件・判定元） */
  function srcOf(it) {
    var u = it.reqU || {}, loc = u.location || {}, line = u.line_start || loc.line_start, row = function (l, v) { return '<div class="dax-props__row"><dt>' + l + '</dt><dd>' + v + '</dd></div>'; };
    return '<dl class="dax-props dax-props--one dax-meta6">' + row('文書', esc(u.document_id || '—')) + row('位置', line ? '行 ' + esc(line) : '—') + row('要件', esc(it.req || '—')) + row('判定元', '規則（テスト可能性の判定）') + '</dl>';
  }
  /* 規則ごとの具体的な「なぜ重要か」「推奨する対応」 */
  function ruleAdvice(x) {
    var k = (x.rule_id || '') + ' ' + (x.title || ''), r = String(x.reason || ''), q = r.match(/「([^」]{1,20})」/);
    if (/AMB|曖昧/i.test(k)) return { why: (q ? '「' + q[1] + '」' : 'この語') + 'は人によって解釈が割れ、実装とテストの合否がずれます。', fix: (q ? '「' + q[1] + '」' : '曖昧な語') + 'を、検証できる基準に置き換えます。例：「なるべく速く」を「2 秒以内」のように数値と単位にします。' };
    if (/ITEMS|必須/i.test(k)) { var items = []; r.replace(/「([^」]+)」/g, function (_, v) { items.push(v); });
      return { why: '必須の項目が欠けると、その機能の設計とテストを始められません。', fix: '次の不足項目の節を文書に追加します：' + (items.length ? items.map(function (v) { return '「' + v + '」'; }).join('') : '（項目名は原文を確認）') + '。' }; }
    return { why: whyOf({ kind: 'f', raw: x }), fix: x.how_to_fix || '推奨する対応は記録されていません。原文を確認して判断してください。' };
  }
  function evDl(rule, c) { var r = function (l, v) { return '<div class="dax-props__row"><dt>' + l + '</dt><dd>' + v + '</dd></div>'; }; return '<dl class="dax-props dax-props--one dax-meta6">' + r('規則 ID', esc(rule || '—')) + r('関連度', c == null ? '—' : '<span title="関連度 ' + (Number(c) || 0).toFixed(2) + '">' + conf(c) + '</span>') + '</dl>'; }
  /* 原文の引用: 先頭の記法記号（- # * > 1.）を除き、該当語を mark する */
  function quoteHtml(t, term) { var s = String(t || '').replace(/^\s*(?:[-*+>]|#{1,6}|\d+[.)])\s+/, ''), e = esc(s); if (term) { var et = esc(term); e = e.split(et).join('<mark class="dax-mark">' + et + '</mark>'); } return e; }
  /* 「何が問題か」の 1 文 */
  function problemSentence(x) {
    var k = (x.rule_id || '') + ' ' + (x.title || ''), r = String(x.reason || ''), q = r.match(/「([^」]{1,30})」/);
    if (/AMB|曖昧/i.test(k)) return (q ? '「' + q[1] + '」' : 'この語') + 'は基準が曖昧で、人によって解釈が割れます。';
    if (isTbd(x)) return (q ? '「' + q[1] + '」の印が残り、' : '') + '内容がまだ決まっていません。';
    if (/ITEMS|必須/i.test(k)) { var cat = r.match(/^(.+?)の必須項目/); return (cat ? cat[1] + 'の' : '') + '必須項目' + (q ? '「' + q[1] + '」' : '') + 'の記述が文書にありません。'; }
    if (/ID-004|孤立/i.test(k)) return 'この要件 ID はどの文書からも参照されていません。';
    if (/ID-002|欠番/i.test(k)) { var g = r.match(/欠番[:：]\s*(.+)$/); return '要件 ID に欠番' + (g ? '（' + g[1] + '）' : '') + 'があります。'; }
    return r.replace(/『/g, '「').replace(/』/g, '」') || '説明はありません。';
  }
  function itemDetailBody(it, sec, head) {
    var reqLine = it.req ? '<p class="dax-meta">要件 ' + esc(it.req) + (it.reqText ? '：' + esc(it.reqText) : '') + '</p>' : '';
    if (it.kind === 't') {
      var tc = it.raw, li = function (a) { return (a || []).length ? '<ul>' + a.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : ''; };
      var KEYM = ['成功条件', '失敗時の挙動', '閾値・単位'], ms = tc.missing || [], keyMiss = KEYM.filter(function (k) { return ms.indexOf(k) >= 0; });
      return head + sec('何が問題か', '<p>' + (ms.length ? '次の情報が書かれていないため、テストできません：' + ms.map(esc).join('・') + '。' : '合否の基準が書かれていないため、テストできません。') + '</p>' + reqQuote(it, true))
        + sec('なぜ重要か', '<p>合否を判定できず、テストケースの期待結果を書けません。</p>')
        + sec('推奨する対応', '<p>不足している情報を要件に書き足して、再解析してください。</p>'
          + (keyMiss.indexOf('閾値・単位') >= 0 ? '<p class="dax-meta">例：「速く」ではなく「2 秒以内」のように数値と単位で書きます。</p>' : ''))
        + disc('tc-' + it.key, '根拠の詳細', evDl('テスト可能性の判定', it.raw.confidence), '', true);
    }
    var c = it.raw, ev = c.evidence || [], q = function (e, l) { return '<div class="dax-compare__side"><p class="dax-meta">' + l + '</p>' + (e ? '<blockquote>' + esc(e.quote) + '</blockquote><p class="dax-meta">' + esc(e.document_id) + ' ・ ' + esc(e.requirement_id) + '</p>' : '<p class="dax-meta">対応する記述がありません。</p>') + '</div>'; };
    return head + sec('何が問題か', '<div class="dax-compare">' + q(ev[0], '記述 A') + '<div class="dax-compare__topic">' + esc(c.question || '') + '</div>' + q(ev[1], '記述 B') + '</div><p class="dax-unknown">どちらが正しいかは未確定です。</p>')
      + sec('なぜ重要か', '<p>' + whyOf(it) + '</p>') + sec('推奨する対応', '<p>「矛盾」タブでどちらを正とするかを決め、理由を記録してください。</p><button type="button" class="dax-btn dax-btn--sm" data-tab-go="conf">矛盾タブで決める</button>');
  }
  /* 「何が問題か」: 原文の引用（位置つき）と問題の説明に分ける。理由文「曖昧語「なるべく」: 本文」を分解する */
  function problemOf(x) {
    var r = String(x.reason || ''), loc = x.location || {}, m = r.match(/^(.+?「[^」]+」)\s*[:：]\s*(.*)$/);
    var label = m ? m[1] : (x.title || '指摘'), quote = loc.snippet || (m ? m[2] : '');
    var amb = /AMB|曖昧/i.test((x.rule_id || '') + (x.title || ''));
    var expl = amb ? '基準が曖昧で、実装とテストの解釈が割れます。' : (m ? (whyOf({ kind: 'f', raw: x }) || r) : (r || '説明はありません。'));
    return { label: label, quote: quote, line: loc.line_start, doc: loc.document_id || x.document_id || '', sec: loc.section || '', expl: expl, quoteIsTarget: !!m };
  }
  function findingDetail(x, it) {
    var id = esc(x.finding_id || ''), d = S.draft[x.finding_id] || {};
    var sec = function (t, inner) { return '<section class="dax-detail__section"><h3 class="dax-h3">' + t + '</h3>' + inner + '</section>'; };
    var adv = ruleAdvice(x), why = adv.why, p = problemOf(x);
    it = it || { kind: 'f', sev: x.severity, kindLabel: x.title || '指摘', req: x.requirement_id, raw: x, open: isOpenF(x) };
    var exp = x.status === 'WAIVED' && x.waiver_expiry ? '<div class="dax-props__row"><dt>免除の期限</dt><dd>' + esc(String(x.waiver_expiry).slice(0, 10)) + '</dd></div>' : '';
    var where = esc(p.doc) + (p.sec ? ' ' + esc(p.sec) : '') + (p.line ? '（行 ' + esc(p.line) + '）' : '');
    var reqLink = it.req ? '<button type="button" class="dax-reqlink" data-reqid="' + esc(it.req) + '">' + '<svg class="dax-reqlink__i" viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M9 3h4v4M13 3 7.5 8.5M11 9.5V13H3V5h3.5"/></svg>' + '要件 ' + esc(it.req) + '</button>' : '<span class="dax-meta">要件なし</span>';
    var head = '<header class="dax-md__head"><div class="dax-md__trow"><h2 class="dax-dh__title">' + ttl(actionTitle(it)) + '</h2>' + fnavHtml(it) + '</div><div class="dax-md__hmeta">' + sevDot(it.sev) + '<span class="dax-item__sub">' + esc(it.kindLabel || it.label) + '</span>' + statPill(itemStat(it)) + reqLink + (x.rule_id ? '<span class="dax-meta dax-hrule">規則 ' + esc(x.rule_id) + '</span>' : '') + fsibHtml(it) + '</div></header>';
    var nz = function (v) { return String(v || '').replace(/[\s、。「」・（）()]/g, ''); }, ps = nz(problemSentence(x)), ws = nz(why);
    var bg = function (t) { var o = {}; for (var i = 0; i < t.length - 1; i++) o[t.substr(i, 2)] = 1; return o; }, bp = bg(ps), bw = bg(ws), kp = Object.keys(bp), sh = kp.filter(function (k) { return bw[k]; }).length;
    if (ws && kp.length && sh / Math.min(kp.length, Object.keys(bw).length || 1) >= 0.5) why = '';
    var term = (String(x.reason || '').match(/「([^」]{1,30})」/) || [])[1];
    var h = head + '<div class="dax-md__body">'
      + sec('何が問題か', (p.quote ? '<figure class="dax-quote"><figcaption>' + (p.quoteIsTarget ? '原文' : '関連する原文') + (where ? ' ・ ' + where : '') + '</figcaption><blockquote>' + quoteHtml(p.quote, term) + '</blockquote></figure>' : '')
        + '<p class="dax-prob__expl">' + esc(problemSentence(x)) + '</p>')
      + (why ? sec('なぜ重要か', '<p>' + esc(why) + '</p>') : '')
      + sec('推奨する対応', '<p>' + esc(adv.fix) + '</p>')
      + (exp ? '<dl class="dax-props dax-props--one dax-meta6">' + exp + '</dl>' : '')
      + disc('ev-' + id, '根拠の詳細', '<dl class="dax-props dax-props--one dax-meta6"><div class="dax-props__row"><dt>確からしさ</dt><dd>' + (x.confidence == null ? '—' : '<span title="確からしさ ' + (Number(x.confidence) || 0).toFixed(2) + '">' + conf(x.confidence) + '</span>') + '</dd></div></dl>', '', false) + '</div>';
    if (!id) return h;
    var decided = !isOpenF(x) && ['WAIVED', 'ACCEPTED', 'REJECTED'].indexOf(x.status) >= 0;
    return h + (decided && !S.editDec[x.finding_id] ? decidedHtml(x, id) : decFormHtml(x, id, d, decided));
  }
  /* 判断済み: 読むだけの表示＋［判断を変更］。最新の判断（報告書の「人の判断」節の最後の記録）を出す */
  function decidedHtml(x, id) {
    var lg = (S.decLog || {})[x.finding_id] || null, st = fstat(x);
    var row = function (l, v) { return '<div class="dax-props__row"><dt>' + l + '</dt><dd>' + v + '</dd></div>'; };
    var who = esc(x.decided_by || (lg && lg.by) || '判断者不明') + (lg && lg.at ? ' ・ ' + esc(lg.at) : '');
    return '<footer class="dax-dbar dax-dbar--ro" id="dx-dec-' + id + '" aria-label="判断（記録済み）"><div class="dax-dbar__row">' + statPill(st)
      + (x.status === 'WAIVED' && x.waiver_expiry ? '<span class="dax-dec__exp">期限 ' + esc(String(x.waiver_expiry).slice(0, 10)) + '</span>' : '')
      + '<p class="dax-dbar__ro" title="' + esc(lg && lg.reason ? lg.reason : '') + '"><span class="dax-dbar__k">理由</span>' + esc(lg && lg.reason ? lg.reason : (S.decLog ? '記録されていません' : '読み込み中…')) + '</p>'
      + '<button type="button" class="dax-btn dax-btn--sm" data-fedit="' + id + '">判断を変更</button></div>'
      + '<p class="dax-dbar__who">' + who + '</p></footer>';
  }
  var DEC_DESC = {};
  function decWhy(d) {
    var r = !(d.reason || '').trim(), e = d.choice === 'waived' && !d.expiry;
    if (d.choice === 'waived' && d.expiry && !/^\d{4}-\d{2}-\d{2}$/.test(d.expiry)) return '期限は「2026-12-31」の形（年-月-日）で入力してください。';
    if (!d.choice) return '判断を選び、理由を入力すると記録できます。';
    if (r && e) return '期限の日付と理由を入力すると記録できます。';
    if (e) return '期限の日付を入力すると記録できます。';
    if (r) return '理由を入力すると記録できます。';
    return '';
  }
  function decFormHtml(x, id, d, decided) {
    var c = d.choice || '', why = decWhy(d), err = S.ferr[x.finding_id], tbd = isTbd(x);
    var choice = function (v, label, cls) { return '<button type="button" class="dax-choice dax-seg__opt dax-seg__opt--' + v + ' ' + cls + '" aria-pressed="' + (c === v) + '" data-fchoice="' + id + '" data-v="' + v + '">' + label + '<kbd class="dax-kbd" aria-hidden="true">' + (++kn) + '</kbd></button>'; }, kn = 0;
    return '<footer class="dax-dbar" id="dx-dec-' + id + '" aria-label="' + (decided ? '判断を変更' : '判断') + '"><div class="dax-dbar__row"><div class="dax-seg" role="group" aria-label="判断の種類">'
      + (tbd ? choice('accepted', '決定する', 'dax-choice--main') + choice('waived', '先送り', 'dax-choice--sub')
        : choice('accepted', '指摘を認める', 'dax-choice--main') + choice('rejected', '却下（問題なし）', 'dax-choice--sub') + choice('waived', '期限つきで免除', 'dax-choice--sub')) + '</div>' + (c === 'waived' ? '<span class="dax-seg__desc">期限つきで受け入れます</span>' : '')
      + (decided ? '<span class="dax-dec__cur">現在 ' + statPill(fstat(x)) + '</span>' : '') + '</div>'
      + '<div class="dax-dbar__row dax-dbar__row2">'
      + (c === 'waived' ? '<label class="dax-dbar__ex"><span>期限（必須）</span><input class="dax-input dax-input--date" id="dx-ex-' + id + '" type="text" inputmode="numeric" placeholder="例 2026-12-31" pattern="\\d{4}-\\d{2}-\\d{2}" title="年-月-日（例 2026-12-31）" data-expiry="' + id + '" value="' + esc(d.expiry || '') + '"></label>' : '')
      + '<p class="dax-dec__why" id="dx-dw-' + id + '" data-fwhy="' + id + '" role="status">' + esc(why || (DEC_DESC[c] || '')) + '</p>'
      + '<label class="dax-dbar__lab" for="dx-rs-' + id + '">' + (tbd && c === 'accepted' ? '決定した内容（必須）' : '理由（必須）') + '</label><textarea class="dax-input dax-dbar__reason" id="dx-rs-' + id + '" rows="2" data-reason="' + id + '"' + (err ? ' aria-invalid="true"' : '') + ' placeholder="' + (tbd && c === 'accepted' ? '決めた内容を書く' : 'なぜそう判断したかを書く') + '">' + esc(d.reason || '') + '</textarea>'
      + (decided ? '<button type="button" class="dax-btn" data-fcancel="' + id + '">取り消す</button>' : '')
      + '<button type="button" class="dax-btn dax-btn--primary" data-fsubmit="' + id + '" aria-describedby="dx-dw-' + id + '"' + (why ? ' aria-disabled="true" title="' + esc(why) + '"' : '') + '>' + (tbd ? '記録して次へ' : '判断を記録して次へ') + '</button></div>'
      + (err ? '<p class="dax-field__err" role="alert">' + esc(err) + '</p>' : '') + '</footer>';
  }
  function updDec(id) {
    var d = S.draft[id] || {}, why = decWhy(d), w = document.querySelector('[data-fwhy="' + id + '"]'), b = document.querySelector('[data-fsubmit="' + id + '"]');
    if (w) w.textContent = why || (DEC_DESC[d.choice] || '');
    if (b) { if (why) b.setAttribute('aria-disabled', 'true'); else b.removeAttribute('aria-disabled'); }
  }

  /* ---------- 矛盾 ---------- */
  var CSTATE = [['open', '判断待ち'], ['done', '判断済み'], ['all', 'すべて']], CPICK = [['A', '記述 A を正とする'], ['B', '記述 B を正とする'], ['N', 'どちらも違う（文書を直す）'], ['R', '矛盾ではない']];
  function conflictsHtml() {
    if (!body('conflicts')) return notRun('conflicts') ? emptyBox() : failBox();
    var list = conflicts(), nReq = ((body('requirements') || {}).requirements || []).length;
    var scope = '検査の範囲：要件 ' + nReq + ' 件の組み合わせ（同じ対象の数値・条件・主体）。見つからないことは、矛盾が無いことの証明ではありません。';
    if (!list.length) return '<section class="dax-state dax-state--empty dax-cempty" role="status"><p class="dax-state__title">検出なし（検出できた範囲）</p>'
      + '<p class="dax-state__body">検査したこと：要件どうしで、同じ対象について数値・条件・主体が食い違う記述を比較しました。<br>検査の範囲：要件 ' + nReq + ' 件。<br>見つからないことは、矛盾が無いことの証明ではありません。</p>'
      + '<div class="dax-cempty__act"><button type="button" class="dax-btn" data-tab-go="trace">トレーサビリティを見る</button><button type="button" class="dax-btn" data-tab-go="review">AI レビューで確かめる</button></div></section>';
    var open = function (c) { return c.status === 'UNRESOLVED'; }, nOpen = list.filter(open).length, cnt = { open: nOpen, done: list.length - nOpen, all: list.length };
    var st = S.cstate || (nOpen ? 'open' : 'all'), shown = list.filter(function (c) { return st === 'all' || (st === 'open') === open(c); });
    if (!list.some(function (c) { return c.conflict_id === S.selC; }) || (shown.length && !shown.some(function (c) { return c.conflict_id === S.selC; }))) S.selC = (shown[0] || list.filter(open)[0] || list[0]).conflict_id;
    var reqs = function (c) { var a = []; (c.evidence || []).forEach(function (e) { if (e.requirement_id && a.indexOf(e.requirement_id) < 0) a.push(e.requirement_id); }); return a; };
    var docs = function (c) { return (c.evidence || []).map(function (e) { var l = e.location || {}; return esc(e.document_id || '?') + (l.line_start ? ' ' + l.line_start + ' 行' : ''); }).join(' ↔ '); };
    var tabs = '<div class="dax-segc dax-cf__tabs" role="tablist" aria-label="判断の状態で絞り込む">' + CSTATE.map(function (x) {
      return '<button type="button" role="tab" class="dax-segc__opt" aria-selected="' + (st === x[0]) + '" tabindex="' + (st === x[0] ? 0 : -1) + '" data-cstate="' + x[0] + '">' + x[1] + '<span class="dax-segc__n">' + cnt[x[0]] + '</span></button>';
    }).join('') + '</div>';
    var items = '<div class="dax-md__list" role="listbox" aria-label="矛盾の一覧（' + CSTATE.filter(function (x) { return x[0] === st; })[0][1] + '）">' + (shown.length ? shown.map(function (c) {
      return '<button type="button" role="option" class="dax-item" aria-selected="' + (c.conflict_id === S.selC) + '" data-cid="' + esc(c.conflict_id) + '"><span class="dax-item__title" title="' + esc(c.topic || '') + '">' + esc(c.topic || '記述の食い違い') + '</span>'
        + '<span class="dax-item__meta">' + statPill(open(c) ? ['判断待ち', 'decision'] : ['判断済み', 'done']) + (SEV[c.severity] ? '<span class="dax-tag dax-cf__sev dax-cf__sev--' + esc(c.severity) + '">重大度 ' + SEV[c.severity] + '</span>' : '') + '<span class="dax-item__req">' + esc(reqs(c).join('・') || '要件なし') + '</span></span>'
        + '<span class="dax-cf__docs">' + docs(c) + '</span></button>';
    }).join('') : '<p class="dax-cf__none" role="status">' + (st === 'open' ? '判断待ちの矛盾はありません。判断済み ' + cnt.done + ' 件は「判断済み」で確認できます。' : '該当する矛盾はありません。') + '</p>') + '</div>';
    var left = '<div class="dax-md__left"><div class="dax-cf__lhead">' + tabs + '<p class="dax-cf__scope">' + esc(scope) + '</p></div>' + items
      + '<p class="dax-cf__end">一覧の終わり ・ 判断待ち 残り ' + nOpen + ' 件</p></div>';
    var c = list.filter(function (x) { return x.conflict_id === S.selC; })[0];
    return '<div class="dax-md dax-cf' + (list.length === 1 ? ' dax-cf--one' : '') + '">' + left + '<div class="dax-md__detail" aria-live="polite">' + conflictDetail(c, open(c)) + '</div></div>';
  }
  /* 相違点: 片方にだけ現れる数値を mark する */
  function quoteHtmlRaw(t) { return String(t || '').replace(/^\s*(?:[-*+>]|#{1,6}|\d+[.)])\s+/, ''); }
  function diffMark(q, other) {
    var raw = quoteHtmlRaw(q), e = esc(raw), toks = raw.match(/\d+(?:\.\d+)?\s*(?:分|秒|回|件|日|時間|%)?/g) || [];
    toks.forEach(function (t) { if (String(other || '').indexOf(t) < 0) e = e.split(esc(t)).join('<mark class="dax-mark">' + esc(t) + '</mark>'); });
    return e;
  }
  function dtoks(ev) {
    var re = /\d+(?:\.\d+)?\s*(?:分|秒|回|件|日|時間|%)?/g, A = String((ev[0] || {}).quote || ''), B = String((ev[1] || {}).quote || '');
    var a = (A.match(re) || []).filter(function (t) { return B.indexOf(t) < 0; }), b = (B.match(re) || []).filter(function (t) { return A.indexOf(t) < 0; });
    return a.length || b.length ? '記述 A「' + (a.join('・') || '—') + '」 ↔ 記述 B「' + (b.join('・') || '—') + '」' : '';
  }
  /* 前後の文脈: 同じ文書から抽出した要件のうち、直前・直後の行 */
  function cfCtx(e) {
    var loc = e.location || {}, a = loc.line_start || 0, b = loc.line_end || a, prev = null, next = null;
    ((body('requirements') || {}).requirements || []).forEach(function (r) {
      var l = r.location || {}; if (r.document_id !== e.document_id || !l.line_start) return;
      if ((l.line_end || l.line_start) < a && (!prev || l.line_start > prev.location.line_start)) prev = r;
      if (l.line_start > b && (!next || l.line_start < next.location.line_start)) next = r;
    });
    return { prev: prev, next: next };
  }
  function cfWhy(d) { var p = d.pick || '', r = (d.reason || '').trim(); return !/[ABNR]/.test(p) ? '判断を 1 つ選び、理由を入力してください' : !r ? (p === 'R' ? '「矛盾ではない」も理由が必要です。理由を入力してください' : '理由を入力してください') : ''; }
  function cfDocs(id) { var c = conflicts().filter(function (x) { return x.conflict_id === id; })[0] || {}; return (c.evidence || []).map(function (e) { var sec = String((e.location || {}).section || ''), m = sec.match(/(要件定義書|基本設計書|詳細設計書)/); return m ? m[1] : (e.document_id || ''); }); }
  function cfPrefix(id, d) {
    var P = { A: '記述 A を正とする', B: '記述 B を正とする', R: '矛盾ではない' };
    if (d.pick !== 'N') return P[d.pick] || '';
    var dn = cfDocs(id)[d.fixdoc === 'B' ? 1 : 0] || '', v = (d.fixval || '').trim();
    return d.fixdoc && v ? 'どちらも違う：' + dn + 'を「' + v + '」に直す' : 'どちらも違う';
  }
  function cfSum(id, d) {
    var c = conflicts().filter(function (x) { return x.conflict_id === id; })[0] || {}, ev = c.evidence || [], dn = cfDocs(id), k = d.pick === 'A' ? 0 : d.pick === 'B' ? 1 : -1;
    var v = function (i) { return (String((ev[i] || {}).quote || '').match(/\d+(?:\.\d+)?\s*(?:分|秒|回|件|日|時間|%)/) || [''])[0]; };
    if (k >= 0) return '記述 ' + d.pick + '（' + [v(k), dn[k]].filter(Boolean).join('・') + '）を正として記録します';
    var p = cfPrefix(id, d); return p ? '【' + p + '】として記録します' : '';
  }
  function cfUpd(id) {
    var why = cfWhy(S.draft[id] || {}) || cfSum(id, S.draft[id] || {}), w = document.querySelector('[data-cwhy="' + id + '"]'), b = document.querySelector('[data-csubmit="' + id + '"]');
    if (w) { w.textContent = why; w.classList.remove('dax-cf__why--err'); } if (b) { if (cfWhy(S.draft[id] || {})) b.setAttribute('aria-disabled', 'true'); else b.removeAttribute('aria-disabled'); }
  }
  document.addEventListener('input', function (e) {
    var t = e.target, ds = (t && t.dataset) || {}, id = ds.reason || ds.cfix; if (!id || S.tab !== 'conf') return;
    draftOf(id); if (ds.cfix) S.draft[id][ds.k] = t.value; cfUpd(id);
  });
  function conflictDetail(c, isOpen) {
    var ev = c.evidence || [], id = esc(c.conflict_id), d = S.draft[c.conflict_id] || {}, err = S.ferr[c.conflict_id], lg = (S.decLog || {})[c.conflict_id];
    var cl = function (r) { var x = r.location || {}; return '<p class="dax-cf__ctx" title="' + esc(x.snippet || '') + '"><span class="dax-cf__ln">' + x.line_start + ' 行</span>' + esc(x.snippet || '') + '</p>'; };
    var side = function (e, o, l) {
      if (!e) return '<div class="dax-compare__side"><p class="dax-cf__lbl">' + l + '</p><p class="dax-meta">対応する記述がありません。</p></div>';
      var loc = e.location || {}, cx = cfCtx(e);
      var sec = String(loc.section || ''), tier = /要件定義書/.test(sec) ? '上流：要件定義書' : /基本設計書/.test(sec) ? '下流：基本設計書' : /詳細設計書/.test(sec) ? '下流：詳細設計書' : '';
      return '<div class="dax-compare__side"><p class="dax-cf__lbl">' + l + (tier ? '<span class="dax-tag dax-cf__tier">' + tier + '</span>' : '') + '</p><p class="dax-cf__q">' + diffMark(e.quote, o && o.quote) + '</p>'
        + '<p class="dax-cf__src"><span class="dax-cf__nw">' + esc(e.requirement_id || '要件なし') + ' ・ ' + esc(e.document_id || '') + (loc.line_start ? ' ' + loc.line_start + ' 行目' : '') + '</span><br>' + esc(loc.section || e.document_id || '文書名なし') + '</p>'
        + '<details class="dax-cf__more"><summary>前後の行</summary>' + (cx.prev ? cl(cx.prev) : '<p class="dax-cf__ctx">（前に抽出した要件なし）</p>') + (cx.next ? cl(cx.next) : '<p class="dax-cf__ctx">（後に抽出した要件なし）</p>') + '</details></div>';
    };
    var sev = SEV[c.severity] ? '<span class="dax-tag dax-cf__sev dax-cf__sev--' + esc(c.severity) + '">重大度 ' + SEV[c.severity] + '</span>' : '';
    var head = '<header class="dax-md__head"><div class="dax-md__hmeta">' + (isOpen ? '<span class="dax-sp dax-sp--decision" title="' + esc(c.question || '') + '">判断待ち</span>' : statPill(['判断済み', 'done'])) + sev + '</div><h2 class="dax-dh__title">' + esc(c.topic || '記述の食い違い') + '</h2></header>';
    var hist = lg ? '<dl class="dax-cf__hist"><div><dt>最新の記録</dt><dd>' + esc(DEC_NAME[lg.decision] || lg.decision) + (lg.by ? ' ・ ' + esc(lg.by) : '') + (lg.at ? ' ・ ' + esc(lg.at) : '') + '</dd></div><div><dt>理由</dt><dd>' + esc(lg.reason || '記録されていません') + '</dd></div></dl>'
      : '<p class="dax-meta">' + (S.decLog ? 'まだ判断は記録されていません。' : '読み込み中…') + '</p>';
    var vals = ev.map(function (e) { return (String(e.quote || '').match(/\d+(?:\.\d+)?\s*(?:分|秒|回|件|日|時間|%)/) || [''])[0]; });
    var plain = vals[0] && vals[1] ? '同じ対象「' + (c.topic || '') + '」の値が、記述 A では ' + vals[0] + '、記述 B では ' + vals[1] + ' になっています。' : '同じ対象について、記述 A と記述 B の内容が食い違っています。';
    var pos = ev.map(function (e, k) { var l = e.location || {}; return '記述 ' + 'AB'.charAt(k) + ' ' + (vals[k] || '—') + '（' + esc(e.document_id || '') + (l.line_start ? ' ' + l.line_start + ' 行目' : '') + '）'; }).join('　／　');
    var basisSec = '<div class="dax-cf__basis"><p class="dax-cf__bk">検出根拠</p><p class="dax-cf__bline">規則：' + (c.kind === 'numeric' ? '同じ対象で数値が食い違う記述' : '同じ対象で内容が食い違う記述') + '（確度 ' + conf(c.confidence) + '）</p><p class="dax-cf__bline">抽出した値：' + pos + '</p>'
      + '<details class="dax-cf__more"><summary>詳細（規則の内部値）</summary><p class="dax-cf__ctx">確度 ' + (Number(c.confidence) || 0).toFixed(2) + '</p>' + (c.confidence_basis || []).map(function (b) { return '<p class="dax-cf__ctx">' + esc(b) + '</p>'; }).join('') + '</details></div>'
      + (isOpen ? '<p class="dax-cf__note"><span class="dax-tag">推定</span>どちらが正しいかは未確定です。決定事項を確かめて判断してください。</p>' : '');
    var histSec = '<section class="dax-detail__section"><h3 class="dax-h3">判断の履歴</h3>' + hist + '</section>';
    var cmp = '<section class="dax-detail__section"><h3 class="dax-h3">何が食い違っているか</h3><div class="dax-compare">' + side(ev[0], ev[1], '記述 A') + side(ev[1], ev[0], '記述 B') + '</div>' + basisSec + '</section>';
    basisSec = '';
    var editing = isOpen || S.editDec[c.conflict_id], pk = d.pick || '';
    if (!editing) return head + '<div class="dax-md__body">' + cmp + histSec + basisSec + '</div><footer class="dax-dbar dax-dbar--ro" aria-label="判断（記録済み）"><div class="dax-dbar__row">' + statPill(['判断済み', 'done'])
      + '<p class="dax-dbar__ro"><span class="dax-dbar__k">理由</span>' + esc(lg && lg.reason ? lg.reason : (S.decLog ? '記録されていません' : '読み込み中…')) + '</p><button type="button" class="dax-btn dax-btn--sm" data-fedit="' + id + '">判断を変更</button></div></footer>';
    var radios = '<div class="dax-cf__radios" role="radiogroup" aria-labelledby="dx-cq-' + id + '">' + CPICK.map(function (x, i) {
      var on = pk === x[0]; return '<button type="button" role="radio" class="dax-cf__radio" aria-checked="' + on + '" tabindex="' + (on || (!pk && i === 0) ? 0 : -1) + '" data-cchoice="' + id + '" data-v="' + x[0] + '"><span class="dax-cf__dot" aria-hidden="true"></span>' + x[1] + '</button>';
    }).join('') + '</div>';
    var why = cfWhy(d);
    var dn = cfDocs(c.conflict_id), fix = pk !== 'N' ? '' : '<div class="dax-cf__fix"><label>直す文書<select class="dax-input" data-cfix="' + id + '" data-k="fixdoc"><option value="">選んでください</option><option value="A"' + (d.fixdoc === 'A' ? ' selected' : '') + '>記述 A：' + esc(dn[0] || '') + '</option><option value="B"' + (d.fixdoc === 'B' ? ' selected' : '') + '>記述 B：' + esc(dn[1] || '') + '</option></select></label>'
      + '<label>正しい値<input class="dax-input" type="text" data-cfix="' + id + '" data-k="fixval" value="' + esc(d.fixval || '') + '" placeholder="例：25分"></label></div>';
    var card = '<section class="dax-detail__section dax-cf__card" aria-label="判断"><h3 class="dax-h3" id="dx-cq-' + id + '">どう判断するか</h3><p class="dax-cf__vs">' + ev.slice(0, 2).map(function (e, k) { return '<span><b>' + 'AB'.charAt(k) + '</b> ' + esc(vals[k] || '—') + '（' + esc(dn[k] || e.document_id || '') + '）</span>'; }).join('<span class="dax-cf__vsep" aria-hidden="true">｜</span>') + '</p>' + radios + fix
      + '<label class="dax-h3" for="dx-rs-' + id + '">理由（必須）</label><textarea class="dax-input dax-cf__reason" id="dx-rs-' + id + '" rows="3" data-reason="' + id + '" placeholder="例：承認済みの決定事項 D-12 で 30 分と決まっている"' + (err ? ' aria-invalid="true"' : '') + '>' + esc(d.reason || '') + '</textarea>'
      + '<p class="dax-meta">確定すると、選んだ判断（例：【記述 A を正とする】）が理由の先頭に付いて記録されます。</p>'
      + (S.editDec[c.conflict_id] ? '<div><button type="button" class="dax-btn dax-btn--sm" data-fcancel="' + id + '">変更を取り消す</button></div>' : '') + '</section>';
    return head + '<div class="dax-md__body">' + cmp + card + histSec + '</div>'
      + '<footer class="dax-dbar dax-cf__bar" aria-label="確定"><p class="dax-cf__why' + (err ? ' dax-cf__why--err' : '') + '" id="dx-cw-' + id + '" data-cwhy="' + id + '"' + (err ? ' role="alert"' : '') + '>' + esc(err || why || cfSum(c.conflict_id, d)) + '</p>'
      + '<button type="button" class="dax-btn dax-btn--primary dax-cf__ok" data-csubmit="' + id + '"' + (why ? ' aria-disabled="true"' : '') + ' aria-describedby="dx-cw-' + id + '">確定</button></footer>';
  }
  /* ---------- 判断の記録（理由必須・免除は期限必須。ネイティブダイアログは使わない） ---------- */
  function draftOf(id) {
    var ta = document.querySelector('textarea[data-reason="' + id + '"]'), ex = document.querySelector('input[data-expiry="' + id + '"]'), pk = document.querySelector('input[data-pick="' + id + '"]:checked'), o = S.draft[id] || {};
    S.draft[id] = { reason: ta ? ta.value : o.reason, expiry: ex ? ex.value : o.expiry, pick: pk ? pk.value : o.pick, choice: o.choice, fixdoc: o.fixdoc, fixval: o.fixval }; return S.draft[id];
  }
  function record(id, d, expiry, reason, msg) {
    post('decisions', { decision: d, target: id, reason: reason, expiry: expiry }).then(function (r) {
      S.ferr[id] = r.ok ? '' : ((r.body && r.body.error) || '記録できませんでした。') + ' 権限を確認してから、もう一度お試しください。';
      if (r.ok) { delete S.draft[id]; delete S.editDec[id]; toast(msg); if (S.nextSel && S.tab === 'issues') { S.selF = S.nextSel; S.fstate = 'open'; } if (S.nextSelC && S.tab === 'conf') S.selC = S.nextSelC; S.nextSel = null; S.nextSelC = null; return load(); }
      render();
    });
  }
  function decideFinding(id, d) {
    var dr = draftOf(id), ol = buildModel().filter(function (it) { return it.open; }), ix = -1;
    ol.forEach(function (it, i) { if (it.id === id) ix = i; });
    S.nextSel = ix >= 0 ? ((ol[ix + 1] || ol[ix - 1] || {}).key || null) : null;
    if (!dr.reason || !dr.reason.trim()) { S.ferr[id] = '理由が空です。理由を入力してからもう一度押してください。'; return render(); }
    if (d === 'waived' && !dr.expiry) { S.ferr[id] = '免除するには期限が必要です。期限の日付を入力してからもう一度押してください。'; return render(); }
    record(id, d, d === 'waived' ? dr.expiry : null, dr.reason.trim(), '記録しました。');
  }
  function decideConflict(id, d) {
    var ol = conflicts().filter(function (c) { return c.status === 'UNRESOLVED'; }), ix = -1; ol.forEach(function (c, i) { if (c.conflict_id === id) ix = i; });
    S.nextSelC = ix >= 0 ? ((ol[ix + 1] || ol[ix - 1] || {}).conflict_id || null) : null;
    var dr = draftOf(id), PICK = { A: '記述 A を正とする', B: '記述 B を正とする', N: 'どちらも違う' };
    if (d === 'conflict_decided' && !dr.pick) { S.ferr[id] = 'A か B を選んでください（「どちらも違う」「矛盾ではない」も選べます）。'; render(); var sg = document.querySelector('.dax-cf__radios [tabindex="0"]'); if (sg) sg.focus(); return; }
    if (!dr.reason || !dr.reason.trim()) { S.ferr[id] = '決定の理由が空です。理由を入力してから確定してください。'; render(); var rt = document.getElementById('dx-rs-' + id); if (rt) rt.focus(); return; }
    record(id, d, null, (d === 'conflict_decided' ? '【' + (cfPrefix(id, dr) || PICK[dr.pick]) + '】' : '') + dr.reason.trim(), d === 'rejected' ? '「矛盾ではない」と記録しました。' : '決定を記録しました。');
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
  function counts() {
    var req = body('requirements') ? reqModel().filter(function (m) { return m.st[1] === 'attention'; }).length : null;
    var open = buildModel().filter(function (it) { return it.open; });
    return { issues: open.length, conf: open.filter(function (it) { return it.kind === 'c'; }).length, req: req };
  }
  function tabName() { return (NAV.filter(function (n) { return n[0] === S.tab; })[0] || NAV[0])[1]; }
  function subMeta(ver, at) {
    if (S.tab === 'overview') return '';
    if (S.loaded && S.tab === 'issues') return '未解決 ' + openCount() + ' 件';
    if (S.loaded && S.tab === 'conf') return '未解決の矛盾 ' + conflicts().filter(function (c) { return c.status === 'UNRESOLVED'; }).length + ' 件';
    if (S.loaded && S.tab === 'req') return '要件 ' + (((body('requirements') || {}).requirements || []).length) + ' 件';
    var rv = (window.DV && DV.state && DV.state.review) || {}, by = rv.created_by || rv.owner || rv.author || '';
    var p = [ver != null ? '版 ' + ver : '', at ? '最終解析 ' + String(at).replace('T', ' ').slice(0, 16) : '', by ? '作成者 ' + by : ''].filter(Boolean);
    if (p.length) return p.join(' ・ ');
    var rq = (body('requirements') || {}).requirements || [], docs = {}; rq.forEach(function (u) { docs[u.document_id] = 1; });
    return rq.length ? '文書 ' + Object.keys(docs).length + ' 件 ・ 要件 ' + rq.length + ' 件' : '';
  }
  function headerHtml() {
    var rq = body('requirements') || {}, sc = body('scores') || {};
    var vs = ((window.DV && DV.state && DV.state.review && DV.state.review.versions) || []).map(function (v) { return v && typeof v === 'object' ? (v.version != null ? v.version : v.no) : v; }).filter(function (v) { return v != null && v !== ''; });
    var ver = vs.length ? vs.reduce(function (a, b) { return Number(b) > Number(a) ? b : a; }) : null;
    var at = rq.saved_at || sc.saved_at || (body('issues') || {}).saved_at || (S.full && S.full.saved_at) || null;
    var hasData = !notRun('scores');
    return '<header class="dax-header">'
      + '<div class="dax-header__row"><div><h1 class="dax-h1">' + esc(tabName()) + '</h1><p class="dax-header__meta">' + esc(subMeta(ver, at)) + '</p></div>'
      + '<div class="dax-header__actions">' + (S.tab === 'overview' ? '' : '<button type="button" class="dax-btn" data-act="run"' + (S.busy ? ' disabled' : '') + '>' + (S.busy ? '解析中…' : '再解析') + '</button>')
      + pop('menu', '<span aria-hidden="true">⋯</span>', 'dax-btn dax-btn--ghost dax-btn--icon', ' aria-label="その他の操作" title="その他の操作"',
        (S.tab === 'overview' ? '<button type="button" role="menuitem" class="dax-pop__item" data-act="run">再解析</button><button type="button" role="menuitem" class="dax-pop__item" data-tab-go="review">AI レビューを実行</button>' : '') + '<button type="button" role="menuitem" class="dax-pop__item" data-tab-go="diff">前の版と比較</button>' + (S.tab === 'trace' ? '<a role="menuitem" class="dax-pop__item" href="#trace">旧ビュー（比較用）</a>' : '')
        + (hasData ? '<a role="menuitem" class="dax-pop__item" href="' + url('report.md') + '" download>エクスポート（Markdown）</a><a role="menuitem" class="dax-pop__item" href="' + url('report.csv') + '" download>エクスポート（CSV）</a>' : '')
        + '<button type="button" role="menuitem" class="dax-pop__item" data-act="settings">設定</button>') + '</div></div></header>';
  }
  function navHtml() { return ''; }   // ナビはサイド（.dv-sb）へ移った。件数は dax:counts で渡す
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
    window.DAX_IID = rid();
    if (S.loaded) { try { var cn = counts(); window.dispatchEvent(new CustomEvent('dax:counts', { detail: cn })); Array.prototype.forEach.call(document.querySelectorAll('.dv-sb__count[data-count="conf"]'), function (b) { b.title = '確認待ち ' + cn.issues + ' 件のうち矛盾 ' + cn.conf + ' 件'; b.setAttribute('aria-label', b.title); }); } catch (e) { /* 古いブラウザでは件数を出さないだけ */ } }
    var keepB = $('#da-root .dax-md__body'), keepL = $('#da-root .dax-md__list'), keepM = $('#dx-main'), sb = keepB ? keepB.scrollTop : 0, sl = keepL ? keepL.scrollTop : 0, sm = keepM ? keepM.scrollTop : 0, sameSel = S._lastSel === S.selF && S._lastTab === S.tab;
    root.innerHTML = '<div class="dax">' + headerHtml() + navHtml() + '<main class="dax-main" id="dx-main" aria-label="' + esc(tabName()) + '"><div class="dax-page dax-page--' + esc(S.tab) + '">' + main + '</div></main></div>';
    var mb = $('#dx-main .dax-page');
    if (sameSel) { var nb = $('#da-root .dax-md__body'), nl = $('#da-root .dax-md__list'), nm = $('#dx-main'); if (nb) nb.scrollTop = sb; if (nl) nl.scrollTop = sl; if (nm) nm.scrollTop = sm; }
    if (!sameSel && S.tab === 'issues') { var si = $('#da-root .dax-item[aria-selected="true"]'); if (si) si.scrollIntoView({ block: 'nearest' }); }
    S._lastSel = S.selF; S._lastTab = S.tab; fadeSync();
    if (pn && pn.bind && mb && S.loaded && !S.error && !S.blocked) pn.bind(mb, ctx());
  }
  function syncHash() { if (rid()) history.replaceState(null, '', '#assure/' + encodeURIComponent(rid()) + (S.tab !== 'overview' ? '/' + (S.tab === 'diff' ? 'changes' : S.tab) : '')); }
  function setTab(t, focus) { S.tab = t; syncHash(); closeDrawer(); render(); if (focus !== false) { var n = document.querySelector('#da-root .dax-h1'); if (n) { n.setAttribute('tabindex', '-1'); n.focus(); } } }
  function closePops(ret) {
    var open = document.querySelectorAll('#da-root [data-pop][aria-expanded="true"]'), any = false;
    Array.prototype.forEach.call(open, function (b) { var p = document.getElementById(b.getAttribute('aria-controls')); if (p) p.hidden = true; b.setAttribute('aria-expanded', 'false'); any = true; if (ret) b.focus(); });
    return any;
  }
  function closeMenu(ret) { return closePops(ret); }
  function togglePop(b) {
    var wasOpen = b.getAttribute('aria-expanded') === 'true'; closePops(false); if (wasOpen) return;
    var p = document.getElementById(b.getAttribute('aria-controls')); if (!p) return;
    p.hidden = false; b.setAttribute('aria-expanded', 'true');
    var first = p.querySelector('[aria-selected="true"]') || p.querySelector('[role="menuitem"],[role="option"],[role="menuitemcheckbox"]'); if (first) first.focus();
  }
  /* 詳細の下端フェード: 末尾まで読んだら消す */
  function fadeSync(el) {
    el = el || $('#da-root .dax-md__body'); if (!el) return;
    var d = el.closest('.dax-md__detail'); if (d) d.toggleAttribute('data-end', el.scrollHeight - el.scrollTop - el.clientHeight < 8);
  }
  document.addEventListener('scroll', function (e) { var t = e.target; if (t && t.classList && t.classList.contains('dax-md__body')) fadeSync(t); }, true);

  document.addEventListener('click', function (e) {
    var t = e.target; if (!t || !t.closest) return;
    var el;
    if (t.closest('[data-drawer-close]')) return closeDrawer();
    if (!t.closest('#da-root')) { if (!t.closest('#dx-drawer')) return; }
    if ((el = t.closest('[data-pop]'))) return togglePop(el);
    if (!t.closest('.dax-pop__panel')) closePops(false);
    if ((el = t.closest('[data-disc]'))) { var dk = el.dataset.disc, ob = el.getAttribute('aria-expanded') !== 'true'; S.disc[dk] = ob; el.setAttribute('aria-expanded', String(ob)); var bx = document.getElementById(el.getAttribute('aria-controls')); if (bx) bx.hidden = !ob; fadeSync(); return; }
    if ((el = t.closest('[data-jump]'))) { var jt = document.getElementById(el.dataset.jump); if (jt) { jt.scrollIntoView({ block: 'start', behavior: 'smooth' }); var jf = jt.querySelector('[data-fchoice],[data-fedit]'); (jf || jt).focus({ preventScroll: true }); } return; }
    if ((el = t.closest('[data-dd]'))) { if (el.dataset.dd === 'sev') S.fsevF = el.dataset.val; else if (el.dataset.dd === 'sort') S.fsort = el.dataset.val; else S.fkind = el.dataset.val; S.selF = null; closePops(false); render(); var db = $('[data-pop="dd-' + el.dataset.dd + '"]'); if (db) db.focus(); return; }
    if ((el = t.closest('[data-colt]'))) { var ck2 = el.dataset.colt; S.cols = Object.assign({}, S.cols); S.cols[ck2] = !S.cols[ck2]; render(); var cb = $('[data-pop="cols"]'); if (cb) { togglePop(cb); var ci = $('[data-colt="' + ck2 + '"]'); if (ci) ci.focus(); } return; }
    if ((el = t.closest('[data-fchoice]'))) { var fc = el.dataset.fchoice; draftOf(fc); S.draft[fc].choice = el.dataset.v; S.ferr[fc] = ''; closePops(false); render(); var fb = document.querySelector('[data-fchoice="' + fc + '"][data-v="' + el.dataset.v + '"]:not([role="menuitem"])') || document.querySelector('[data-pop="wv-' + fc + '"]'); fb = document.getElementById(el.dataset.v === 'waived' ? 'dx-ex-' + fc : 'dx-rs-' + fc) || fb; if (fb) fb.focus({ preventScroll: true }); return; }
    if ((el = t.closest('[data-tab]'))) return setTab(el.dataset.tab);
    if ((el = t.closest('[data-tab-go]'))) { if (el.dataset.tabGo === 'issues') { S.fstate = el.dataset.fstate || 'open'; S.selF = null; S.fsevF = ''; S.fkind = ''; } return setTab(el.dataset.tabGo); }
    if ((el = t.closest('[data-fstate-go]'))) { S.fstate = el.dataset.fstateGo; S.selF = null; render(); return; }
    if ((el = t.closest('[data-reqid]'))) { var rq = reqModel().filter(function (m) { return m.u.requirement_id === el.dataset.reqid; })[0]; if (rq) reqDrawer(rq.key, el); return; }
    if ((el = t.closest('[data-fstate-tab]'))) { S.fstate = el.dataset.fstateTab; S.selF = null; render(); var st = $('[data-fstate-tab="' + S.fstate + '"]'); if (st) st.focus(); return; }
    if ((el = t.closest('[data-fedit]'))) { var ek = el.dataset.fedit; S.editDec[ek] = true; render(); var r0 = document.querySelector('[data-fchoice="' + ek + '"]'); if (r0) r0.focus(); return; }
    if ((el = t.closest('[data-fcancel]'))) { var ck = el.dataset.fcancel; delete S.editDec[ck]; delete S.draft[ck]; S.ferr[ck] = ''; render(); var eb = document.querySelector('[data-fedit="' + ck + '"]'); if (eb) eb.focus(); return; }
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
      if (g === 'f') { var pit = buildModel().filter(function (x) { return x.key === id; })[0]; S.fstate = pit && !pit.open ? 'all' : 'open'; S.fsevF = ''; S.fkind = ''; S.selF = id; return setTab('issues'); }
      if (g === 'conf') return setTab('conf');
      if (g === 'req') { setTab('req', false); return reqDrawer(id, el); }
    }
    if ((el = t.closest('[data-score]'))) return scoreDrawer(el.dataset.score, el);
    if ((el = t.closest('[data-reqsort]'))) { var so = el.dataset.reqsort; S.reqDesc = (S.reqSort || 'sev') === so ? !S.reqDesc : false; S.reqSort = so; render(); var sb = $('[data-reqsort="' + so + '"]'); if (sb) sb.focus(); return; }
    if ((el = t.closest('[data-chip]'))) { S.chip = S.chip === el.dataset.chip ? '' : el.dataset.chip; render(); var c = $('[data-chip="' + el.dataset.chip + '"]'); if (c) c.focus(); return; }
    if ((el = t.closest('[data-fsev]'))) { S.fsev = el.dataset.fsev; render(); var f = $('[data-fsev="' + el.dataset.fsev + '"]'); if (f) f.focus(); return; }
    if ((el = t.closest('.dax-item[data-cid]'))) { S.selC = el.dataset.cid; render(); var ci2 = $('.dax-item[aria-selected="true"]'); if (ci2) ci2.focus(); return; }
    if ((el = t.closest('[data-cstate]'))) { if (S.selC) draftOf(S.selC); S.cstate = el.dataset.cstate; render(); var cst = $('[data-cstate="' + S.cstate + '"]'); if (cst) cst.focus(); return; }
    if ((el = t.closest('[data-cchoice]'))) { var cc = el.dataset.cchoice, cv = el.dataset.v; draftOf(cc); S.draft[cc].pick = cv; S.ferr[cc] = ''; render(); var cb = $('[data-cchoice="' + cc + '"][data-v="' + cv + '"]'); if (cb) cb.focus({ preventScroll: true }); var ccd = $('.dax-cf__card'), cbd = ccd && ccd.closest('.dax-md__body'); if (cbd) { var cr = ccd.getBoundingClientRect(), br = cbd.getBoundingClientRect(); if (cr.bottom > br.bottom - 8) cbd.scrollTop += Math.max(0, Math.min(cr.bottom - br.bottom + 8, cr.top - br.top - 8)); } return; }
    if ((el = t.closest('[data-csubmit]'))) { var cs = el.dataset.csubmit, cd = draftOf(cs); return decideConflict(cs, cd.pick === 'R' ? 'rejected' : 'conflict_decided'); }
    if ((el = t.closest('.dax-item[data-fid]'))) { S.selF = el.dataset.fid; render(); var it = $('.dax-item[aria-selected="true"]'); if (it) it.focus(); return; }
    if ((el = t.closest('[data-fsubmit]'))) { var fid = el.dataset.fsubmit; draftOf(fid); var wm = decWhy(S.draft[fid] || {}); if (wm) { S.ferr[fid] = wm; render(); var rb = document.querySelector('[data-fsubmit="' + fid + '"]'); if (rb) rb.focus({ preventScroll: true }); return; } return decideFinding(fid, S.draft[fid].choice); }
    if ((el = t.closest('[data-decide]'))) return decideConflict(el.dataset.decide, el.dataset.d);
    if ((el = t.closest('tr[data-req]'))) return reqDrawer(el.dataset.req, el);
  });
  document.addEventListener('input', function (e) {
    var t = e.target; if (!t || !t.closest || !t.closest('#da-root')) return;
    if (t.id === 'dx-fq') { S.fq = t.value; S.selF = null; var pos = t.selectionStart; render(); var nf = $('#dx-fq'); if (nf) { nf.focus(); try { nf.setSelectionRange(pos, pos); } catch (e2) {} } return; }
    if (t.id === 'dx-q') { S.q = t.value; var rows = reqRows(), tb = $('#dx-rows'), c = $('#dx-cnt'); if (tb) tb.innerHTML = reqRowsHtml(rows); if (c) c.textContent = reqCount(reqModel(), rows); return; }
    var id = t.dataset && (t.dataset.reason || t.dataset.expiry || t.dataset.pick); if (id) { draftOf(id); updDec(id); }
  });
  document.addEventListener('change', function (e) {
    var t = e.target; if (!t || !t.closest || !t.closest('#da-root')) return;
    if (t.dataset && t.dataset.ffilter) { if (t.dataset.ffilter === 'sev') S.fsevF = t.value; else S.fkind = t.value; S.selF = null; render(); var fx = $('[data-ffilter="' + t.dataset.ffilter + '"]'); if (fx) fx.focus(); return; }
    if (t.dataset && t.dataset.col) { S.cols = Object.assign({}, S.cols); S.cols[t.dataset.col] = t.checked; render(); var x = $('[data-col="' + t.dataset.col + '"]'); if (x) { x.closest('details').open = true; x.focus(); } return; }
    if (t.dataset && t.dataset.fpick) { var fk = t.dataset.fpick; draftOf(fk); var w = document.querySelector('[data-expiry-wrap="' + fk + '"]'); if (w) w.hidden = t.value !== 'waived'; var sb = document.querySelector('[data-fsubmit="' + fk + '"]'); if (sb) { sb.disabled = false; sb.removeAttribute('aria-disabled'); } var ds = document.querySelector('[data-fdesc="' + fk + '"]'); if (ds) ds.textContent = { accepted: '指摘を受け入れ、文書を直す', rejected: '問題ではないと判断する', waived: '期限までは対応しないことを認める' }[t.value] || ''; return; }
    var id = t.dataset && (t.dataset.reason || t.dataset.expiry || t.dataset.pick); if (id) { draftOf(id); updDec(id); }
  });
  function fnavGo(d) {
    var L = S.flist || [], i = L.indexOf(S.selF), j = i + d; if (S.tab !== 'issues' || i < 0 || j < 0 || j >= L.length) return;
    S.selF = L[j]; render(); var n = document.querySelector('#da-root .dax-item[aria-selected="true"]'); if (n) n.focus({ preventScroll: true });
  }
  document.addEventListener('click', function (e) { var b = e.target.closest && e.target.closest('[data-fnav]'); if (b && !b.disabled) fnavGo(Number(b.dataset.fnav)); });
  document.addEventListener('keydown', function (e) {
    var inField = e.target.closest && e.target.closest('input,textarea,select,[contenteditable="true"]');
    if (S.tab === 'issues' && !drawerOpen() && e.key === 'Escape' && inField && e.target.closest('#da-root .dax-md')) { e.preventDefault(); e.target.blur(); var cur = $('#da-root .dax-md__list .dax-item[aria-selected="true"]'); if (cur) cur.focus(); return; }
    if (S.tab === 'issues' && (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Home' || e.key === 'End') && e.target.matches && e.target.matches('.dax-md__list .dax-item[data-fid]')) {
      e.preventDefault(); var rl = Array.prototype.slice.call(document.querySelectorAll('#da-root .dax-md__list .dax-item[data-fid]')), ri = rl.indexOf(e.target);
      ri = e.key === 'Home' ? 0 : e.key === 'End' ? rl.length - 1 : Math.max(0, Math.min(rl.length - 1, ri + (e.key === 'ArrowDown' ? 1 : -1)));
      rl.forEach(function (b, k) { b.tabIndex = k === ri ? 0 : -1; }); rl[ri].focus(); return;
    }
    if (S.tab === 'issues' && !inField && !drawerOpen() && !e.ctrlKey && !e.metaKey && !e.altKey) {
      if (/^[123]$/.test(e.key)) { var ob = document.querySelectorAll('#da-root .dax-seg [data-fchoice]')[Number(e.key) - 1]; if (ob) { e.preventDefault(); ob.click(); return; } }
      if (e.key === 'Enter' && !(e.target.closest && e.target.closest('button,a,[role="option"]'))) { var sb = document.querySelector('#da-root [data-fsubmit]'); if (sb && sb.getAttribute('aria-disabled') !== 'true') { e.preventDefault(); sb.click(); return; } }
    }
    if ((e.key === 'j' || e.key === 'k') && !e.ctrlKey && !e.metaKey && !e.altKey && S.tab === 'issues' && !drawerOpen() && !(e.target.closest && e.target.closest('input,textarea,select,[contenteditable="true"]'))) { e.preventDefault(); return fnavGo(e.key === 'j' ? 1 : -1); }
    if (e.key === 'Escape') { if (drawerOpen()) { e.preventDefault(); return closeDrawer(); } if (closeMenu(true)) { e.preventDefault(); } return; }
    var t = e.target; if (!t || !t.matches) return;
    if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && t.closest('.dax-pop__panel')) {
      e.preventDefault(); var pi = Array.prototype.slice.call(t.closest('.dax-pop__panel').querySelectorAll('.dax-pop__item')), pj = pi.indexOf(t) + (e.key === 'ArrowDown' ? 1 : -1);
      if (pi[(pj + pi.length) % pi.length]) pi[(pj + pi.length) % pi.length].focus(); return;
    }
    if (e.key === 'ArrowDown' && t.matches('[data-pop]') && t.getAttribute('aria-expanded') !== 'true') { e.preventDefault(); return togglePop(t); }
    if ((e.key === 'ArrowRight' || e.key === 'ArrowLeft') && t.matches('[data-fstate-tab]')) {
      e.preventDefault(); var ks = FSTATE.map(function (x) { return x[0]; }), ki = (ks.indexOf(t.dataset.fstateTab) + (e.key === 'ArrowRight' ? 1 : ks.length - 1)) % ks.length;
      S.fstate = ks[ki]; S.selF = null; render(); var nt2 = $('[data-fstate-tab="' + S.fstate + '"]'); if (nt2) nt2.focus(); return;
    }
    if ((e.key === 'ArrowRight' || e.key === 'ArrowLeft') && t.matches('[data-cstate]')) {
      e.preventDefault(); var cks = CSTATE.map(function (x) { return x[0]; }), cki = (cks.indexOf(t.dataset.cstate) + (e.key === 'ArrowRight' ? 1 : cks.length - 1)) % cks.length;
      return $('[data-cstate="' + cks[cki] + '"]').click();
    }
    if (/^Arrow(Right|Left|Up|Down)$/.test(e.key) && t.matches('.dax-cf__radios [data-cchoice]')) {
      e.preventDefault(); var cps = Array.prototype.slice.call(document.querySelectorAll('.dax-cf__radios [data-cchoice]')), cpi = (cps.indexOf(t) + (e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : cps.length - 1)) % cps.length;
      return cps[cpi].click();
    }
    if (e.key === 'Enter' && t.matches('tr[data-req]')) { e.preventDefault(); return reqDrawer(t.dataset.req, t); }
    if ((e.key === 'Enter' || e.key === ' ') && t.matches('tr[data-pgo]')) { e.preventDefault(); return t.click(); }
    if ((e.key === 'ArrowRight' || e.key === 'ArrowLeft' || e.key === 'Home' || e.key === 'End') && t.matches('.dax-nav__item')) {
      e.preventDefault();
      var keys = NAV.map(function (n) { return n[0]; }), i = keys.indexOf(S.tab);
      i = e.key === 'Home' ? 0 : e.key === 'End' ? keys.length - 1 : (i + (e.key === 'ArrowRight' ? 1 : keys.length - 1)) % keys.length;
      return setTab(keys[i]);
    }
    if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && t.matches('.dax-item')) {
      e.preventDefault(); var its = Array.prototype.slice.call(document.querySelectorAll('.dax-item')), j = its.indexOf(t) + (e.key === 'ArrowDown' ? 1 : -1);
      if (its[j]) { if (its[j].dataset.cid) S.selC = its[j].dataset.cid; else S.selF = its[j].dataset.fid; render(); var n = $('.dax-item[aria-selected="true"]'); if (n) n.focus(); }
    }
  });
  function enter() {
    var ht = tabFromHash(); if (ht) S.tab = ht;
    syncHash();
    if (rid() !== S.iid) { S.data = {}; S.loaded = false; S.full = null; S.draft = {}; S.ferr = {}; S.rw = {}; S.selF = null; S.editDec = {}; S.decLog = null; S.cstate = ''; S.fstate = 'open'; S.error = ''; S.blocked = null; }
    if (S.busy) return render();
    load();
  }
  function tabFromHash() { var hp = location.hash.slice(1).split('/'); if (hp[0] !== 'assure' || !hp[2]) return hp[0] === 'assure' ? 'overview' : null; var t = hp[2] === 'changes' ? 'diff' : hp[2]; return NAV.some(function (n) { return n[0] === t; }) ? t : 'overview'; }
  window.addEventListener('hashchange', function () { var t = tabFromHash(); if (t && t !== S.tab && rid()) { S.tab = t; closeDrawer(); render(); } });
  if (window.DV && window.DV.on) window.DV.on('assure', enter);
  /* サイドバーを畳んだ幅（1280px 未満）でも名称が分かるよう title を付ける */
  Array.prototype.forEach.call(document.querySelectorAll('.dv-sb .dv-sb__item'), function (it) { var l = it.querySelector('.dv-sb__label'); if (l && !it.title) it.title = l.textContent.trim(); });
  window.DocAssure = { open: function () { if (window.DV) window.DV.show('assure'); }, close: closeDrawer, reload: load };
})();
