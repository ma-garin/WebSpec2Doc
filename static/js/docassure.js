/* System06 ドキュメント品質保証（DAX 骨格）。問いの順: 大丈夫か → 何が問題か → 何を直すか → 根拠。
   段階表示 L1 判断 / L2 問題 / L3 根拠（details.dax-adv）/ L4 技術詳細（details.dax-adv）。文書由来の文字列は esc() を通す。 */
(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var esc = function (v) { return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  var S = { data: {}, tab: 'overview', chip: '', q: '', cols: {}, selF: null, fsev: '', busy: false, loaded: false, error: '', blocked: null, drawerFocus: null, menuFocus: null, rw: {}, draft: {}, ferr: {}, iid: null, full: null, fstate: 'open', fsevF: '', fkind: '', editDec: {}, decLog: null, disc: {} };
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
  var DEC_NAME = { accepted: '採用', rejected: '却下', waived: '免除', resolved: '解決済み', conflict_decided: '決定' };
  var FSTATE = [['open', '未解決'], ['done', '判断済み'], ['all', 'すべて']];
  var NAV = [['overview', '概要'], ['req', '要件'], ['issues', '指摘'], ['conf', '矛盾'], ['trace', 'トレーサビリティ'], ['diff', '変更'], ['review', 'レビュー']];
  var PANEL_TABS = { trace: 'trace', diff: 'diff', review: 'review' };
  var REQ_CHIPS = [['attention', '要対応'], ['nt', 'テスト不可'], ['cf', '矛盾あり'], ['notest', 'テストなし'], ['changed', '変更あり']];
  var OPT_COLS = [['kind', '種別'], ['doc', '文書'], ['infer', '推測を含む']];

  function fstat(x) {
    if (x.waiver_expired) return ['期限切れ。再度確認が必要', 'decision'];
    if (x.status === 'WAIVED') return ['免除', 'done'];
    if (x.status === 'ACCEPTED') return ['採用', 'done'];
    if (x.status === 'REJECTED') return ['却下', 'done'];
    if (DONE.indexOf(x.status) >= 0) return ['解決済み', 'done'];
    return ['判断待ち', 'decision'];
  }
  /* 表示部品: 重要度＝色付きドット／種類＝ニュートラルなタグ／状態＝ステータスピル（色だけに依存しない: 文字を必ず添える） */
  function sevDot(sev) { var k = SEV[sev] ? sev : 'none'; return '<span class="dax-sd dax-sd--' + k + '"><i aria-hidden="true"></i>' + (SEV[sev] || '未評価') + '</span>'; }
  function kindTag(it) { return '<span class="dax-kt">' + esc(it.kindLabel || it.label) + '</span>'; }
  function statPill(st) { return '<span class="dax-sp dax-sp--' + st[1] + '">' + esc(st[0]) + '</span>'; }
  function isOpenF(x) { return DONE.indexOf(x.status) < 0 || x.waiver_expired; }
  /* 製品の部品（標準の details / select / ラジオは使わない）
     開閉＝シェブロン付きの見出し行ボタン（aria-expanded）／ポップアップ＝ボタン＋メニュー（Esc で閉じる・矢印で移動） */
  var CHEV = '<svg class="dax-chev" viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 4l4 4-4 4"/></svg>';
  var CARET = '<svg class="dax-caret" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6l4 4 4-4"/></svg>';
  function disc(id, label, inner, meta) {
    var o = !!S.disc[id];
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
    return GATE.keys.filter(function (k) { return sc[k] && sc[k].value != null && Number(sc[k].value) < GATE.min; }).map(function (k) { return { key: k, name: QNAME[k], v: Math.round(Number(sc[k].value)) }; });
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
    var names = ['requirements', 'issues', 'conflicts', 'scores', 'trace', 'diff'];
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
      if (S.tab === 'issues' && !drawerOpen()) { var ae = document.activeElement, aid = ae && ae.id; render(); if (aid) { var n = document.getElementById(aid); if (n) n.focus(); } }
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
      out.push({ kind: 't', key: 't:' + k, id: k, sev: SEV[tc.severity] ? tc.severity : 'medium', label: 'テスト不可', kindLabel: 'テスト不可', short: why, req: rid2, open: true, raw: tc });
    });
    // 並び: 未決 → 判断済み（免除は最後）。同じ群の中は 重要度 → 種類（規則・矛盾・テスト不可）
    var grp = function (it) { return it.open ? 0 : (it.kind === 'f' && it.raw.status === 'WAIVED' ? 2 : 1); };
    var sv = function (it) { return SEV_ORDER[it.sev] != null ? SEV_ORDER[it.sev] : 9; };
    var kd = { f: 0, c: 1, t: 2 };
    out.sort(function (a, b) { return (grp(a) - grp(b)) || (sv(a) - sv(b)) || (kd[a.kind] - kd[b.kind]); });
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
  function topicOf(t) {
    var s = String(t || '').replace(/^\s*\d+[.．]\s*/, '').replace(/[。．.]\s*$/, '');
    var m = s.match(/^(.{1,14}?)(は|を|で|が|に)/); return m ? m[1] : s.slice(0, 12);
  }
  function actionTitle(it) {
    if (it.kind === 'c') return '「' + (it.short || '記述') + '」の食い違いを解消する';
    var tp = topicOf(it.reqText);
    if (it.kind === 't') { var miss = (it.raw.missing || [])[0]; return (tp ? tp + 'の' : '') + (miss || '合否の基準') + 'を決める'; }
    var q = String(it.raw.reason || '').match(/「([^」]{1,20})」/);
    if (/AMB|曖昧/i.test((it.raw.rule_id || '') + it.short) && q) return '『' + q[1] + '』の基準を決める';
    if (/ITEMS|必須/i.test((it.raw.rule_id || '') + it.short)) return (tp ? tp + 'の' : '') + '必須項目を確認する';
    return (tp ? tp + '：' : '') + it.short + 'を確認する';
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
    var miss = gateMiss(), ai = mode() === 'DETERMINISTIC_ONLY';
    var head = n ? '次工程へ進む前に ' + n + ' 件の確認が必要です' : (st[1] === 'ready' ? '次工程へ進めます' : '確認待ちの指摘はありません');
    // 判定の根拠: 確認待ちの件数と、品質スコアの基準未達を 1 行で結ぶ（API の理由がスコアに触れなくても画面側で補う）
    var basis = (n ? '確認が必要な指摘 ' + n + ' 件。' : '確認が必要な指摘はありません。')
      + (miss.length ? '品質スコアのうち ' + miss.map(function (m) { return m.name + ' ' + m.v + ' 点'; }).join('・') + ' は「次工程の基準に未達」です。' : '');
    var why = (rd && (rd.reasons || [])[0]) ? human(rd.reasons[0]) : (st[1] === 'ready' ? '必要な評価がそろい、未解決の指摘はありません。' : 'まだ判定に足る評価がありません。');
    var h = '<section class="dax-ready dax-ready--' + st[1] + '" aria-label="準備状態"><div class="dax-ready__main">'
      + '<span class="dax-pill dax-pill--' + st[1] + '">' + (st[1] === 'ready' ? ICON_OK : ICON_WARN) + ' ' + esc(st[0]) + '</span>'
      + '<h2 class="dax-ready__title">' + esc(head) + '</h2>'
      + '<p class="dax-ready__basis" title="' + esc(GATE.note) + '"><span class="dax-ready__k">判定の根拠</span>' + esc(basis) + '</p>'
      + '<p class="dax-ready__why"><span class="dax-ready__k">判定の理由</span>' + esc(why) + '</p>'
      + (ai ? '<p class="dax-ready__note">' + ICON_WARN + ' AI レビューは実行していません。規則による解析のみで判定しています。</p>' : '')
      + '</div><div class="dax-ready__act">' + (n ? '<button type="button" class="dax-btn dax-btn--primary" data-tab-go="issues" data-fstate="open">確認待ちを見る</button>' : '<button type="button" class="dax-btn dax-btn--primary" data-act="run"' + (S.busy ? ' disabled' : '') + '>' + (S.busy ? '解析中…' : '再解析') + '</button>') + '</div></section>';
    // KPI 帯（3 指標）。悪い向きの数は警告色・棒なし。棒は「進んだ量」（判断済み）だけ
    var kpi = function (label, val, sub, attrs, tone, bar) {
      return '<button type="button" class="dax-kpi' + (tone ? ' dax-kpi--' + tone : '') + '"' + attrs + '><span class="dax-kpi__label">' + label + '</span><span class="dax-kpi__value">' + val + '</span>'
        + (bar == null ? '' : '<span class="dax-bar dax-bar--progress" aria-hidden="true"><span style="width:' + bar + '%"></span></span>') + '<span class="dax-kpi__sub">' + sub + '</span></button>';
    };
    var evald = GATE.keys.filter(function (k) { return sc[k] && sc[k].value != null; }).length;
    h += '<section class="dax-kpis" aria-label="判断に使う数">'
      + kpi('基準未達の観点', evald ? miss.length + '<small> / ' + GATE.keys.length + '</small>' : '—', evald ? (miss.length ? miss.map(function (m) { return m.name; }).join('・') : '網羅性・テスト可能性・トレーサビリティは基準以上') : '評価不能（次の解析で評価）', ' data-jump="dx-qual"', miss.length ? 'warn' : '')
      + kpi('テスト不可の要件', tot ? nt + '<small> / ' + tot + '</small>' : '—', tot ? (nt ? '合否の基準が書かれていない' : 'テスト不可の要件なし') : '要件なし', ' data-tab-go="issues" data-fstate="open"', nt ? 'warn' : '')
      + kpi('判断済みの指摘', all.length ? dec + '<small> / ' + all.length + '</small>' : '—', all.length ? '採用・却下・免除を記録' : '対象なし', ' data-tab-go="issues" data-fstate="done"', '', all.length ? Math.round(dec / all.length * 100) : null)
      + '<button type="button" class="dax-link dax-kpis__more" data-jump="dx-qual">品質スコアと被覆の詳細を見る</button></section>';
    var LIM = 3, rows = open.slice(0, LIM);
    h += '<section class="dax-sec dax-sec--must" aria-labelledby="dx-must"><div class="dax-sec__head"><h2 class="dax-sec__title" id="dx-must">確認待ち' + (n ? ' <span class="dax-sec__n">' + n + ' 件</span>' : '') + '</h2></div>'
      + '<p class="dax-sec__lead">次工程の前に判断が必要なもの（重要度が中でも含めます）。重要度の高い順に ' + rows.length + ' 件を表示しています。</p>'
      + (n ? '<table class="dax-todo"><colgroup><col><col style="width:104px"><col style="width:112px"><col style="width:88px"><col style="width:32px"></colgroup><thead><tr><th scope="col">確認すること</th><th scope="col">要件</th><th scope="col">種類</th><th scope="col">重要度</th><th scope="col"><span class="dax-sr">開く</span></th></tr></thead><tbody>' + rows.map(function (it) {
        return '<tr tabindex="0" data-pgo="f" data-pid="' + esc(it.key) + '" aria-label="' + esc(actionTitle(it)) + '"><td><span class="dax-todo__title">' + esc(actionTitle(it)) + '</span><span class="dax-todo__why">' + esc(whyOf(it) || it.short) + '</span></td><td class="dax-todo__id">' + esc(it.req || '—') + '</td><td>' + kindTag(it) + '</td><td>' + sevDot(it.sev) + '</td><td class="dax-todo__go" aria-hidden="true">' + CHEV + '</td></tr>';
      }).join('') + '</tbody></table><div class="dax-sec__more"><button type="button" class="dax-link" data-tab-go="issues" data-fstate="open">すべて見る</button></div>'
      : '<p class="dax-sec__empty">検出なし（検出できた範囲）。検出が無いことは、問題が無いことの証明ではありません。</p>') + '</section>';
    var qrows = QUAL.map(function (q) {
      var s = sc[q[0]], na = !s || s.value == null, w = na ? null : Math.max(0, Math.min(100, Math.round(s.value)));
      var gate = GATE.keys.indexOf(q[0]) >= 0, low = w != null && w < GATE.min;
      var sub = !s ? '未評価。解析すると評価されます' : na ? (ai ? 'AI レビューか要件の補足で評価できます' : '要件を補って再解析すると評価できます') : '評価できた範囲 ' + pct(s.coverage) + '%';
      var val = !s ? '<span class="dax-badge">未評価</span>' : na ? '<span class="dax-badge dax-badge--na">評価不能</span>' : '<span class="dax-q__num">' + w + '<small> 点</small></span>';
      return '<button type="button" class="dax-q' + (low ? ' dax-q--low' : '') + (na ? ' dax-q--na' : '') + '" data-score="' + q[0] + '" title="' + esc(sub) + '"><span class="dax-q__name">' + q[1] + (low && gate ? '<span class="dax-tag dax-tag--warn">基準未達</span>' : '') + '</span>'
        + (na ? '<span class="dax-q__next">' + esc(sub) + '</span>' : '<span class="dax-bar" aria-hidden="true"><span style="width:' + w + '%"></span><i style="left:' + GATE.min + '%"></i></span>')
        + '<span class="dax-q__value">' + val + '</span></button>';
    }).join('');
    var can = rm.filter(function (m) { return m.tv === 'CAN_TEST' || m.tv === 'PARTIALLY_TESTABLE'; }).length;
    var linked = body('trace') && body('trace').graph ? rm.filter(function (m) { return !m.notest; }).length : null;
    h += '<div class="dax-cols"><section class="dax-sec" aria-labelledby="dx-qual" id="dx-qual" tabindex="-1"><div class="dax-sec__head"><h2 class="dax-sec__title">品質スコア</h2>' + infoTip('100 点満点・評価できた範囲だけで算出します。評価できなかった観点を 0 点や 100 点にはしません。縦線は次工程の基準（暫定 ' + GATE.min + ' 点）。行を選ぶと理由を表示します。') + '</div><div class="dax-qs">' + qrows + '</div></section>'
      + '<section class="dax-sec" aria-labelledby="dx-cov"><div class="dax-sec__head"><h2 class="dax-sec__title" id="dx-cov">被覆</h2>' + infoTip('要件の数で数えます（分母は全要件）。「テスト可能性」スコアとは別の指標です。テストへのつながりが無いことは、欠陥とは限りません。') + '</div><div class="dax-cov">'
      + frow2('テスト可能と判定された要件', can, tot) + (linked == null ? '<div class="dax-cov__row"><span class="dax-cov__label">テストへのつながりがある要件</span><span class="dax-badge">未評価</span></div>' : frow2('テストへのつながりがある要件', linked, tot))
      + frow2('判断を記録した指摘', dec, all.length) + '</div></section></div>';
    var ch = changedIds(), chN = Object.keys(ch).length;
    var moreBody = (chN ? '<p>変更のあった要件 ' + chN + ' 件：' + Object.keys(ch).slice(0, 8).map(function (k) { return '<span class="dax-tag">' + esc(k) + '</span>'; }).join(' ') + '</p><button type="button" class="dax-btn dax-btn--sm" data-tab-go="diff">変更を見る</button>' : '<p class="dax-meta">前の版との差分は記録されていません。</p>')
      + (rd && (rd.reasons || []).length ? '<ul>' + rd.reasons.map(function (x) { return '<li>' + esc(human(x)) + '</li>'; }).join('') + '</ul>' : '');
    h += '<div class="dax-more">' + disc('ov-more', '最近の変更と判定の理由', moreBody, (notRun('diff') || !body('diff') ? '変更なし' : '変更 ' + chN + ' 件') + (rd && (rd.reasons || []).length ? '・理由 ' + rd.reasons.length + ' 件' : '')) + '</div>';
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
    var colsel = pop('cols', '列' + CARET, 'dax-btn dax-btn--sm', '', OPT_COLS.map(function (c) { return '<button type="button" role="menuitemcheckbox" class="dax-pop__item" aria-checked="' + !!S.cols[c[0]] + '" data-colt="' + c[0] + '"><span class="dax-check" aria-hidden="true"></span>' + c[1] + '</button>'; }).join(''));
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
      + disc('rq-' + u.requirement_id, '根拠の詳細', ((tc.reasons || []).length ? '<ul>' + tc.reasons.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : '<p class="dax-meta">テスト可能性の判定理由はありません。</p>') + (u.snippet && u.snippet !== u.raw_text ? '<p>' + esc(u.snippet) + '</p>' : ''))
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
    var fs = S.fstate || 'open';
    var inState = function (it, s) { return s === 'all' || (s === 'open' ? it.open : !it.open); };
    var bySel = function (it) { return (!S.fsevF || (S.fsevF === 'none' ? !SEV[it.sev] : it.sev === S.fsevF)) && (!S.fkind || (it.kindLabel || it.label) === S.fkind); };
    var list = all.filter(function (it) { return inState(it, fs) && bySel(it); });
    if (!list.some(function (it) { return it.key === S.selF; })) S.selF = list.length ? list[0].key : null;
    var kinds = []; all.forEach(function (it) { var k = it.kindLabel || it.label; if (kinds.indexOf(k) < 0) kinds.push(k); });
    var sevs = Object.keys(SEV).filter(function (k) { return all.some(function (it) { return it.sev === k; }); });
    if (all.some(function (it) { return !SEV[it.sev]; })) sevs.push('none');
    var tabs = '<div class="dax-toolbar dax-ftool"><div class="dax-segc" role="tablist" aria-label="状態で切り替え">' + FSTATE.map(function (s) {
      var c = all.filter(function (it) { return inState(it, s[0]); }).length;
      return '<button type="button" role="tab" class="dax-segc__opt" aria-selected="' + (fs === s[0]) + '" tabindex="' + (fs === s[0] ? '0' : '-1') + '" data-fstate-tab="' + s[0] + '">' + s[1] + ' <span class="dax-segc__n">' + c + '</span></button>'; }).join('') + '</div>'
      + '<div class="dax-fsel">' + dd('sev', '重要度', [['', 'すべて']].concat(sevs.map(function (k) { return [k, SEV[k] || '未評価']; })), S.fsevF || '')
      + dd('kind', '種類', [['', 'すべて']].concat(kinds.map(function (k) { return [k, k]; })), S.fkind || '') + '</div></div>';
    var items = '<div class="dax-md__list" role="listbox" aria-label="指摘の一覧">' + (list.length ? list.map(function (it) {
      return '<button type="button" role="option" class="dax-item" aria-selected="' + (it.key === S.selF) + '" data-fid="' + esc(it.key) + '"><span class="dax-item__title">' + esc(actionTitle(it)) + '</span>'
        + '<span class="dax-item__meta">' + sevDot(it.sev) + kindTag(it) + '<span class="dax-item__req">' + esc(it.req || '要件なし') + '</span>' + statPill(itemStat(it)) + '</span></button>';
    }).join('') : '<p class="dax-meta dax-md__none">' + (fs === 'open' ? '未解決の指摘はありません。' : 'この条件に当てはまる指摘はありません。') + '</p>') + '</div>';
    var sel = list.filter(function (it) { return it.key === S.selF; })[0];
    return tabs + '<div class="dax-md">' + items + '<div class="dax-md__detail" aria-live="polite">' + (sel ? itemDetail(sel) : '<div class="dax-md__body"><p class="dax-meta">この条件に当てはまる指摘はありません。絞り込みを「すべて」に戻してください。</p></div>') + '</div></div>';
  }
  function sevTag(it) { return sevDot(it.sev); }
  function itemStat(it) { if (it.kind === 'f') return fstat(it.raw); if (it.kind === 'c') return it.open ? ['判断待ち', 'decision'] : ['決定済み', 'done']; return ['未対応', 'open']; }
  function props(it, extra) {
    var p = function (l, v) { return '<div class="dax-props__row"><dt>' + l + '</dt><dd>' + v + '</dd></div>'; };
    return '<dl class="dax-props">' + p('重要度', sevDot(it.sev)) + p('種類', kindTag(it)) + p('状態', statPill(itemStat(it))) + p('要件', esc(it.req || '要件なし')) + (extra || '') + '</dl>';
  }
  function itemDetail(it) {
    if (it.kind === 'f') return findingDetail(it.raw, it);
    var sec = function (t, inner) { return '<section class="dax-detail__section"><h3 class="dax-h3">' + t + '</h3>' + inner + '</section>'; };
    var head = '<header class="dax-dh"><h2 class="dax-dh__title">' + esc(actionTitle(it)) + '</h2>' + props(it, '<div class="dax-props__row"><dt>検出元</dt><dd>規則</dd></div>') + '</header>';
    return '<div class="dax-md__body">' + itemDetailBody(it, sec, head) + '</div>';
  }
  function itemDetailBody(it, sec, head) {
    var reqLine = it.req ? '<p class="dax-meta">要件 ' + esc(it.req) + (it.reqText ? '：' + esc(it.reqText) : '') + '</p>' : '';
    if (it.kind === 't') {
      var tc = it.raw, li = function (a) { return (a || []).length ? '<ul>' + a.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : ''; };
      return head + sec('何が問題か', '<p>この要件は合否の基準が書かれておらず、テストできません。</p>' + reqLine + ((tc.missing || []).length ? '<p>不足している情報</p>' + li(tc.missing) : ''))
        + sec('なぜ重要か', '<p>' + whyOf(it) + '</p>') + sec('推奨する対応', '<p>不足している情報（閾値・条件・失敗時の挙動など）を要件に書き足してください。</p>')
        + disc('tc-' + it.key, '根拠の詳細', li(tc.reasons) || '<p class="dax-meta">判定理由は記録されていません。</p>');
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
    var why = whyOf(it || { kind: 'f', raw: x }), p = problemOf(x);
    it = it || { kind: 'f', sev: x.severity, kindLabel: x.title || '指摘', req: x.requirement_id, raw: x, open: isOpenF(x) };
    var exp = x.status === 'WAIVED' && x.waiver_expiry ? '<div class="dax-props__row"><dt>免除の期限</dt><dd>' + esc(String(x.waiver_expiry).slice(0, 10)) + '</dd></div>' : '';
    var where = esc(p.doc) + (p.sec ? ' ' + esc(p.sec) : '') + (p.line ? '（行 ' + esc(p.line) + '）' : '');
    var h = '<div class="dax-md__body"><header class="dax-dh"><div class="dax-dh__row"><h2 class="dax-dh__title">' + esc(actionTitle(it)) + '</h2>'
      + (id ? '<button type="button" class="dax-link dax-jump" data-jump="dx-dec-' + id + '">判断へ' + CARET + '</button>' : '') + '</div>'
      + props(it, '<div class="dax-props__row"><dt>検出元</dt><dd>' + esc(SRC[x.source] || '不明') + '</dd></div>' + exp) + '</header>'
      + sec('何が問題か', '<p class="dax-prob__label">' + esc(p.label) + '</p>'
        + (p.quote ? '<figure class="dax-quote"><figcaption>' + (p.quoteIsTarget ? '原文の引用' : '関連する原文') + (where ? ' ・ ' + where : '') + '</figcaption><blockquote>' + esc(p.quote) + '</blockquote></figure>' : '<p class="dax-meta">引用はありません。</p>')
        + '<p class="dax-prob__expl"><span class="dax-prob__k">説明</span>' + esc(p.expl) + '</p>')
      + (why ? sec('なぜ重要か', '<p>' + esc(why) + '</p>') : '')
      + sec('推奨する対応', '<p>' + esc(x.how_to_fix || '推奨する対応は記録されていません。原文を確認して判断してください。') + '</p>')
      + disc('ev-' + id, '根拠の詳細', '<dl class="dax-props dax-props--one"><div class="dax-props__row"><dt>規則 ID</dt><dd>' + esc(x.rule_id || '—') + '</dd></div><div class="dax-props__row"><dt>出所</dt><dd>' + esc(SRC[x.source] || x.source || '—') + '</dd></div>'
        + '<div class="dax-props__row"><dt>関連度</dt><dd>' + conf(x.confidence) + '（' + (Number(x.confidence) || 0).toFixed(2) + '）</dd></div><div class="dax-props__row"><dt>検出時の文</dt><dd>' + esc(x.reason || '—') + '</dd></div></dl>');
    if (!id) return h + '</div>';
    var decided = !isOpenF(x) && ['WAIVED', 'ACCEPTED', 'REJECTED'].indexOf(x.status) >= 0;
    return h + (decided && !S.editDec[x.finding_id] ? decidedHtml(x, id) : decFormHtml(x, id, d, decided)) + '</div>';
  }
  /* 判断済み: 読むだけの表示＋［判断を変更］。最新の判断（報告書の「人の判断」節の最後の記録）を出す */
  function decidedHtml(x, id) {
    var lg = (S.decLog || {})[x.finding_id] || null, st = fstat(x);
    var row = function (l, v) { return '<div class="dax-props__row"><dt>' + l + '</dt><dd>' + v + '</dd></div>'; };
    return '<section class="dax-dec dax-dec--ro" id="dx-dec-' + id + '" tabindex="-1" aria-labelledby="dx-dech-' + id + '"><div class="dax-dec__head"><h3 class="dax-h3" id="dx-dech-' + id + '">判断</h3>'
      + '<button type="button" class="dax-btn dax-btn--sm" data-fedit="' + id + '">判断を変更</button></div>'
      + '<p class="dax-dec__sum">' + statPill(st) + (x.status === 'WAIVED' && x.waiver_expiry ? '<span class="dax-dec__exp">期限 ' + esc(String(x.waiver_expiry).slice(0, 10)) + '</span>' : '') + '</p>'
      + '<dl class="dax-props dax-props--one">' + row('理由', esc(lg && lg.reason ? lg.reason : (S.decLog ? '記録されていません' : '読み込み中…')))
      + row('判断者', esc(x.decided_by || (lg && lg.by) || '記録されていません')) + row('日時', esc(lg && lg.at ? lg.at : '—（報告書に日時が含まれていません）')) + '</dl></section>';
  }
  var DEC_DESC = { accepted: '指摘を受け入れ、文書を直します。', rejected: '問題ではないと判断します。', waived: '期限までは対応しないことを認めます。期限を過ぎると再び確認が必要になります。' };
  function decWhy(d) {
    if (!d.choice) return '採用・却下・期限つき免除のどれかを選ぶと記録できます。';
    if (!(d.reason || '').trim()) return '判断の理由を入力すると記録できます。';
    if (d.choice === 'waived' && !d.expiry) return '免除の期限を入力すると記録できます。';
    return '';
  }
  function decFormHtml(x, id, d, decided) {
    var c = d.choice || '', why = decWhy(d);
    var choice = function (v, label, cls) { return '<button type="button" class="dax-choice ' + cls + '" aria-pressed="' + (c === v) + '" data-fchoice="' + id + '" data-v="' + v + '">' + label + '</button>'; };
    return '<section class="dax-dec" id="dx-dec-' + id + '" tabindex="-1" aria-labelledby="dx-dech-' + id + '"><div class="dax-dec__head"><h3 class="dax-h3" id="dx-dech-' + id + '">' + (decided ? '判断を変更' : '判断') + '</h3>'
      + (decided ? '<span class="dax-dec__cur">現在：' + statPill(fstat(x)) + '</span>' : '<span class="dax-dec__hint">記録は履歴に残ります</span>') + '</div>'
      + '<div class="dax-dec__choices" role="group" aria-label="判断の種類">' + choice('accepted', '採用', 'dax-choice--main') + choice('rejected', '却下', '')
      + pop('wv-' + id, (c === 'waived' ? '期限つき免除' : 'その他') + CARET, 'dax-choice dax-choice--more', ' aria-pressed="' + (c === 'waived') + '" aria-label="その他の判断"',
        '<button type="button" role="menuitem" class="dax-pop__item" data-fchoice="' + id + '" data-v="waived"><span>期限つき免除</span><small>期限までは対応しないことを認める</small></button>') + '</div>'
      + '<p class="dax-dec__desc" data-fdesc="' + id + '">' + esc(DEC_DESC[c] || '主な判断は「採用」です。問題でなければ「却下」、期限まで対応しない場合は「その他」から免除を選びます。') + '</p>'
      + '<div class="dax-field" data-expiry-wrap="' + id + '"' + (c === 'waived' ? '' : ' hidden') + '><label class="dax-field__label" for="dx-ex-' + id + '">免除の期限</label><input class="dax-input dax-input--date" id="dx-ex-' + id + '" type="date" data-expiry="' + id + '" value="' + esc(d.expiry || '') + '"></div>'
      + '<div class="dax-field"><label class="dax-field__label" for="dx-rs-' + id + '">判断の理由</label><textarea class="dax-input" id="dx-rs-' + id + '" rows="3" data-reason="' + id + '" aria-describedby="dx-rsh-' + id + '"' + (S.ferr[x.finding_id] ? ' aria-invalid="true"' : '') + ' placeholder="例：仕様書 3.2 節で確認済みのため採用">' + esc(d.reason || '') + '</textarea><p class="dax-field__help" id="dx-rsh-' + id + '">あとで読む人が判断を追えるように、根拠を 1〜2 文で書きます。</p></div>'
      + (S.ferr[x.finding_id] ? '<p class="dax-field__err" role="alert">' + esc(S.ferr[x.finding_id]) + '</p>' : '')
      + '<div class="dax-dec__foot"><p class="dax-dec__why" id="dx-dw-' + id + '" data-fwhy="' + id + '" role="status">' + esc(why) + '</p>' + (decided ? '<button type="button" class="dax-btn" data-fcancel="' + id + '">取り消す</button>' : '')
      + '<button type="button" class="dax-btn dax-btn--primary" data-fsubmit="' + id + '" aria-describedby="dx-dw-' + id + '"' + (why ? ' aria-disabled="true"' : '') + '>判断を記録</button></div></section>';
  }
  function updDec(id) {
    var d = S.draft[id] || {}, why = decWhy(d), w = document.querySelector('[data-fwhy="' + id + '"]'), b = document.querySelector('[data-fsubmit="' + id + '"]');
    if (w) w.textContent = why;
    if (b) { if (why) b.setAttribute('aria-disabled', 'true'); else b.removeAttribute('aria-disabled'); }
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
    S.draft[id] = { reason: ta ? ta.value : o.reason, expiry: ex ? ex.value : o.expiry, pick: pk ? pk.value : o.pick, choice: o.choice }; return S.draft[id];
  }
  function record(id, d, expiry, reason, msg) {
    post('decisions', { decision: d, target: id, reason: reason, expiry: expiry }).then(function (r) {
      S.ferr[id] = r.ok ? '' : ((r.body && r.body.error) || '記録できませんでした。') + ' 権限を確認してから、もう一度お試しください。';
      if (r.ok) { delete S.draft[id]; delete S.editDec[id]; toast(msg); return load(); }
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
  function counts() {
    var req = body('requirements') ? reqModel().filter(function (m) { return m.st[1] === 'attention'; }).length : null;
    var open = buildModel().filter(function (it) { return it.open; });
    return { issues: open.length, conf: open.filter(function (it) { return it.kind === 'c'; }).length, req: req };
  }
  function tabName() { return (NAV.filter(function (n) { return n[0] === S.tab; })[0] || NAV[0])[1]; }
  function headerHtml() {
    var rq = body('requirements') || {}, sc = body('scores') || {};
    var vs = ((window.DV && DV.state && DV.state.review && DV.state.review.versions) || []).map(function (v) { return v && typeof v === 'object' ? (v.version != null ? v.version : v.no) : v; }).filter(function (v) { return v != null && v !== ''; });
    var ver = vs.length ? vs.reduce(function (a, b) { return Number(b) > Number(a) ? b : a; }) : null;
    var at = rq.saved_at || sc.saved_at || (body('issues') || {}).saved_at || (S.full && S.full.saved_at) || null;
    var hasData = !notRun('scores');
    return '<header class="dax-header">'
      + '<div class="dax-header__row"><div><h1 class="dax-h1">' + esc(tabName()) + '</h1><p class="dax-header__meta">レビュー: ' + esc(rname() || '') + (ver != null ? ' ・ 版 ' + esc(ver) : '') + (at ? ' ・ 最終解析 ' + esc(String(at).replace('T', ' ').slice(0, 16)) : '') + '</p></div>'
      + '<div class="dax-header__actions">' + (S.tab === 'overview' && S.loaded && !openCount() && hasData ? '' : '<button type="button" class="dax-btn" data-act="run"' + (S.busy ? ' disabled' : '') + '>' + (S.busy ? '解析中…' : '再解析') + '</button>')
      + pop('menu', '<span aria-hidden="true">⋯</span>', 'dax-btn dax-btn--ghost dax-btn--icon', ' aria-label="その他の操作" title="その他の操作"',
        '<button type="button" role="menuitem" class="dax-pop__item" data-tab-go="diff">前の版と比較</button>'
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
    else if (pn) main = (S.tab === 'trace' ? '<p class="dax-oldview"><a href="#trace" class="dax-link">旧ビュー（比較用）</a></p>' : '') + pn.html(ctx());
    else main = views[S.tab]();
    window.DAX_IID = rid();
    if (S.loaded) { try { window.dispatchEvent(new CustomEvent('dax:counts', { detail: counts() })); } catch (e) { /* 古いブラウザでは件数を出さないだけ */ } }
    var keepB = $('#da-root .dax-md__body'), keepL = $('#da-root .dax-md__list'), keepM = $('#dx-main'), sb = keepB ? keepB.scrollTop : 0, sl = keepL ? keepL.scrollTop : 0, sm = keepM ? keepM.scrollTop : 0, sameSel = S._lastSel === S.selF && S._lastTab === S.tab;
    root.innerHTML = '<div class="dax">' + headerHtml() + navHtml() + '<main class="dax-main" id="dx-main" aria-label="' + esc(tabName()) + '"><div class="dax-page dax-page--' + esc(S.tab) + '">' + main + '</div></main></div>';
    var mb = $('#dx-main .dax-page');
    if (sameSel) { var nb = $('#da-root .dax-md__body'), nl = $('#da-root .dax-md__list'), nm = $('#dx-main'); if (nb) nb.scrollTop = sb; if (nl) nl.scrollTop = sl; if (nm) nm.scrollTop = sm; }
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
    if ((el = t.closest('[data-dd]'))) { if (el.dataset.dd === 'sev') S.fsevF = el.dataset.val; else S.fkind = el.dataset.val; S.selF = null; closePops(false); render(); var db = $('[data-pop="dd-' + el.dataset.dd + '"]'); if (db) db.focus(); return; }
    if ((el = t.closest('[data-colt]'))) { var ck2 = el.dataset.colt; S.cols = Object.assign({}, S.cols); S.cols[ck2] = !S.cols[ck2]; render(); var cb = $('[data-pop="cols"]'); if (cb) { togglePop(cb); var ci = $('[data-colt="' + ck2 + '"]'); if (ci) ci.focus(); } return; }
    if ((el = t.closest('[data-fchoice]'))) { var fc = el.dataset.fchoice; draftOf(fc); S.draft[fc].choice = el.dataset.v; S.ferr[fc] = ''; closePops(false); render(); var fb = document.querySelector('[data-fchoice="' + fc + '"][data-v="' + el.dataset.v + '"]:not([role="menuitem"])') || document.querySelector('[data-pop="wv-' + fc + '"]'); if (el.dataset.v === 'waived') fb = document.getElementById('dx-ex-' + fc) || fb; if (fb) fb.focus({ preventScroll: true }); return; }
    if ((el = t.closest('[data-tab]'))) return setTab(el.dataset.tab);
    if ((el = t.closest('[data-tab-go]'))) { if (el.dataset.tabGo === 'issues') { S.fstate = el.dataset.fstate || 'open'; S.selF = null; S.fsevF = ''; S.fkind = ''; } return setTab(el.dataset.tabGo); }
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
    if ((el = t.closest('[data-chip]'))) { S.chip = S.chip === el.dataset.chip ? '' : el.dataset.chip; render(); var c = $('[data-chip="' + el.dataset.chip + '"]'); if (c) c.focus(); return; }
    if ((el = t.closest('[data-fsev]'))) { S.fsev = el.dataset.fsev; render(); var f = $('[data-fsev="' + el.dataset.fsev + '"]'); if (f) f.focus(); return; }
    if ((el = t.closest('.dax-item[data-fid]'))) { S.selF = el.dataset.fid; render(); var it = $('.dax-item[aria-selected="true"]'); if (it) it.focus(); return; }
    if ((el = t.closest('[data-fsubmit]'))) { var fid = el.dataset.fsubmit; draftOf(fid); var wm = decWhy(S.draft[fid] || {}); if (wm) { S.ferr[fid] = wm; render(); var rb = document.querySelector('[data-fsubmit="' + fid + '"]'); if (rb) rb.focus({ preventScroll: true }); return; } return decideFinding(fid, S.draft[fid].choice); }
    if ((el = t.closest('[data-decide]'))) return decideConflict(el.dataset.decide, el.dataset.d);
    if ((el = t.closest('tr[data-req]'))) return reqDrawer(el.dataset.req, el);
  });
  document.addEventListener('input', function (e) {
    var t = e.target; if (!t || !t.closest || !t.closest('#da-root')) return;
    if (t.id === 'dx-q') { S.q = t.value; var rows = reqRows(), tb = $('#dx-rows'), c = $('#dx-cnt'); if (tb) tb.innerHTML = reqRowsHtml(rows); if (c) { var am = reqModel(); c.textContent = am.length + ' 件中 要対応 ' + am.filter(function (m) { return m.st[1] === 'attention'; }).length + ' 件' + (rows.length !== am.length ? '（表示 ' + rows.length + ' 件）' : ''); } return; }
    var id = t.dataset && (t.dataset.reason || t.dataset.expiry || t.dataset.pick); if (id) { draftOf(id); updDec(id); }
  });
  document.addEventListener('change', function (e) {
    var t = e.target; if (!t || !t.closest || !t.closest('#da-root')) return;
    if (t.dataset && t.dataset.ffilter) { if (t.dataset.ffilter === 'sev') S.fsevF = t.value; else S.fkind = t.value; S.selF = null; render(); var fx = $('[data-ffilter="' + t.dataset.ffilter + '"]'); if (fx) fx.focus(); return; }
    if (t.dataset && t.dataset.col) { S.cols = Object.assign({}, S.cols); S.cols[t.dataset.col] = t.checked; render(); var x = $('[data-col="' + t.dataset.col + '"]'); if (x) { x.closest('details').open = true; x.focus(); } return; }
    if (t.dataset && t.dataset.fpick) { var fk = t.dataset.fpick; draftOf(fk); var w = document.querySelector('[data-expiry-wrap="' + fk + '"]'); if (w) w.hidden = t.value !== 'waived'; var sb = document.querySelector('[data-fsubmit="' + fk + '"]'); if (sb) { sb.disabled = false; sb.removeAttribute('aria-disabled'); } var ds = document.querySelector('[data-fdesc="' + fk + '"]'); if (ds) ds.textContent = { accepted: '指摘を受け入れ、文書を直す', rejected: '問題ではないと判断する', waived: '期限までは対応しないことを認める' }[t.value] || ''; return; }
    var id = t.dataset && (t.dataset.reason || t.dataset.expiry || t.dataset.pick); if (id) { draftOf(id); updDec(id); }
  });
  document.addEventListener('keydown', function (e) {
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
      if (its[j]) { S.selF = its[j].dataset.fid; render(); var n = $('.dax-item[aria-selected="true"]'); if (n) n.focus(); }
    }
  });
  function enter() {
    var ht = tabFromHash(); if (ht) S.tab = ht;
    syncHash();
    if (rid() !== S.iid) { S.data = {}; S.loaded = false; S.full = null; S.draft = {}; S.ferr = {}; S.rw = {}; S.selF = null; S.editDec = {}; S.decLog = null; S.fstate = 'open'; S.error = ''; S.blocked = null; }
    if (S.busy) return render();
    load();
  }
  function tabFromHash() { var hp = location.hash.slice(1).split('/'); if (hp[0] !== 'assure' || !hp[2]) return hp[0] === 'assure' ? 'overview' : null; var t = hp[2] === 'changes' ? 'diff' : hp[2]; return NAV.some(function (n) { return n[0] === t; }) ? t : 'overview'; }
  window.addEventListener('hashchange', function () { var t = tabFromHash(); if (t && t !== S.tab && rid()) { S.tab = t; closeDrawer(); render(); } });
  if (window.DV && window.DV.on) window.DV.on('assure', enter);
  window.DocAssure = { open: function () { if (window.DV) window.DV.show('assure'); }, close: closeDrawer, reload: load };
})();
