/* Document Assurance ビュー（System06 /docverify の「ドキュメント品質保証」）。DV.state.review を読むだけで、既存 DV には触れない。
 * 文書由来の文字列は必ず esc() を通す。確認・入力は画面内のフォームで行い、組み込みダイアログは使わない。 */
(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var esc = function (v) { return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  var S = { data: {}, tab: 'home', filter: '', q: '', sort: 'id', busy: false, loaded: false, loadFail: false, error: '', ifilter: {}, drawerFocus: null, rw: {}, draft: {}, ferr: {}, openF: {}, stage: -1, iid: null };
  window.DAPanels = window.DAPanels || {};
  var PANEL_TABS = ['diff', 'review', 'links'];
  var STATE = { READY: ['準備完了', 'ok'], CONDITIONALLY_READY: ['条件付きで準備完了', 'warn'], BLOCKED: ['進められない', 'bad'], REVIEWABLE: ['レビュー可能', 'info'], DRAFT: ['下書き（評価不足）', 'mute'] };
  var SEV = { critical: ['⛔', '致命的'], high: ['▲', '高'], medium: ['●', '中'], low: ['○', '低'], info: ['i', '情報'] };
  var SRC = { deterministic: '規則', ai: 'AI', hybrid: '規則＋AI', human: '人' };
  var SCORES = [['Overall', '総合'], ['Clarity', '明確さ'], ['Completeness', '網羅性'], ['Consistency', '一貫性'], ['Testability', 'テスト可能性'], ['Traceability', '追跡可能性']];
  var TEST = { CAN_TEST: ['✔', 'テストできる', 'ok'], PARTIALLY_TESTABLE: ['▲', '一部のみ', 'warn'], NOT_TESTABLE: ['✖', 'テスト不可', 'bad'], UNKNOWN: ['?', '判定不能', 'mute'] };
  var TEST_ORDER = { NOT_TESTABLE: 0, PARTIALLY_TESTABLE: 1, UNKNOWN: 2, CAN_TEST: 3 };
  var KIND = { functional: '機能', nfr: '非機能', business_rule: '業務ルール', security_rule: 'セキュリティ', constraint: '制約' };
  var STATUS = { CANDIDATE: '候補', CONFIRMED: '確定', REJECTED: '却下', UNKNOWN: '未確認', UNRESOLVED: '未解決', ACCEPTED: '採用済み', RESOLVED: '解決済み', DECIDED: '判断済み', WAIVED: '期限つきで免除中' };
  var PROV = { OBSERVED: '原文に記載', DERIVED: '原文から導出', INFERRED: '推測（事実ではない）' };
  var FIELDS = [['actor', '主体'], ['trigger', '契機'], ['condition', '条件'], ['action', '動作'], ['expected_result', '期待結果'], ['precondition', '前提'], ['object', '対象'], ['constraint', '制約']];
  var STAGES = ['構造化', '規則', '品質', '矛盾', '追跡', '判定'];
  var DONE_STATUS = ['ACCEPTED', 'REJECTED', 'WAIVED', 'RESOLVED', 'DECIDED'];

  var I = {
    ok: '<path d="M20 6 9 17l-5-5"/>', warn: '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17.5v.01"/>', bad: '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
    info: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>', mute: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
    play: '<path d="M7 4v16l13-8z"/>', dl: '<path d="M12 4v11M7 11l5 5 5-5M4 20h16"/>', x: '<path d="M6 6l12 12M18 6 6 18"/>', arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    flag: '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>', link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    swap: '<path d="M7 7h12l-3-3M17 17H5l3 3"/>', help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 17v.01"/>'
  };
  function ico(k, cls) { return '<svg class="da-i ' + (cls || '') + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (I[k] || '') + '</svg>'; }

  function rid() { var r = window.DV && window.DV.state && window.DV.state.review; return r && r.id; }
  function rname() { var r = window.DV && window.DV.state && window.DV.state.review; return r && r.name; }
  function url(p) { return '/api/docassure/inspections/' + encodeURIComponent(rid()) + '/' + p; }
  function conf(c) { var n = Number(c) || 0; return (n >= 0.75 ? '高' : n >= 0.4 ? '中' : '低'); }
  function confFull(c) { return '関連度: ' + conf(c) + '（詳細 ' + (Number(c) || 0).toFixed(2) + '）'; }
  var JP_WORDS = [[/CONDITIONALLY_READY/g, '条件付きで準備完了'], [/NOT_EVALUATED/g, '評価不能'], [/のため\s*READY\s*にしない/g, 'のため、まだ準備完了にできません'], [/READY/g, '準備完了'], [/BLOCKED/g, '進められない'], [/REVIEWABLE/g, 'レビュー可能'], [/DRAFT/g, '下書き'], [/Clarity/g, '明確さ'], [/Completeness/g, '網羅性'], [/Consistency/g, '一貫性'], [/Testability/g, 'テスト可能性'], [/Traceability/g, '追跡可能性'], [/Overall/g, '総合']];
  function jp(s) { var t = String(s == null ? '' : s); JP_WORDS.forEach(function (w) { t = t.replace(w[0], w[1]); }); return t; }
  function orphanReqs() { var tr = body('trace'); if (!tr || !tr.graph || !tr.graph.orphans) return null; var seen = {}; tr.graph.orphans.forEach(function (o) { seen[o.node_id] = 1; }); return Object.keys(seen).length; }
  function toast(m) { if (window.DV && window.DV.toast) window.DV.toast(m); }
  function pct(x) { return Math.round((Number(x) || 0) * 100); }

  function wrap(f) {
    return f.then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, status: r.status, body: b }; });
    }).catch(function () { return { ok: false, status: 0, body: {} }; });
  }
  function get(p) { return wrap(fetch(url(p), { headers: { Accept: 'application/json' } })); }
  function post(p, b) { return wrap(fetch(url(p), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b == null ? {} : b) })); }
  function ctx() { return { iid: rid(), url: url, data: S.data, esc: esc, get: get, post: post }; }

  function load() {
    if (!rid()) { S.loaded = false; render(); return Promise.resolve(); }
    S.iid = rid(); S.busy = true; S.error = ''; S.loadFail = false; render();
    var names = ['requirements', 'issues', 'conflicts', 'scores', 'trace', 'diff'];
    return Promise.all(names.map(get)).then(function (rs) {
      S.data = { trace: null };
      rs.forEach(function (r, i) { S.data[names[i]] = r; });
      S.loadFail = rs.slice(0, 5).every(function (r) { return r.status === 0 || r.status >= 500; });
      S.busy = false; S.loaded = true; render();
    });
  }

  var timer = null;
  function analyze() {
    if (!rid() || S.busy) return;
    S.busy = true; S.error = ''; S.errorDoc = false; S.stage = 0; render();
    timer = setInterval(function () { if (S.stage < STAGES.length - 1) S.stage++; var p = $('#da-prog'); if (p) p.innerHTML = progHtml(); }, 700);
    var stop = function () { clearInterval(timer); S.stage = -1; };
    fetch(url('analyze'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (b) {
        stop();
        if (!r.ok) { S.error = b.error || (r.status === 403 ? '分析する権限がありません。管理者に権限を確認してください。' : '分析できませんでした。少し待ってから「分析を実行」を押し直してください。'); S.errorDoc = b.code === 'no_document'; S.busy = false; render(); return; }
        toast('分析が終わりました。');
        S.full = b; return load();
      });
    }).catch(function () { stop(); S.error = 'サーバに接続できませんでした。少し待ってから「分析を実行」を押し直してください。'; S.busy = false; render(); });
  }

  function body(k) { var x = S.data[k], b = x && x.ok ? x.body : null; return k === 'trace' && b && b.trace ? b.trace : b; }
  function notRun(k) { var x = S.data[k]; return !x || x.status === 404 || x.status === 0; }
  function tests() { var rq = body('requirements') || {}; return rq.testability || (S.full && S.full.testability) || {}; }
  function liveFindings() { return ((body('issues') || {}).findings || []).filter(function (x) { return x.result !== 'PASS'; }); }

  function progHtml() {
    return '<ol class="da-prog" aria-label="分析の進み方">' + STAGES.map(function (s, i) {
      var st = i < S.stage ? 'done' : i === S.stage ? 'now' : 'wait';
      return '<li class="da-prog-' + st + '"' + (st === 'now' ? ' aria-current="step"' : '') + '><span class="da-prog-n">' + (st === 'done' ? '✔' : i + 1) + '</span>' + s + '</li>';
    }).join('') + '</ol>';
  }
  function skeleton() {
    return '<div class="da-skel" role="status" aria-label="読み込み中"><div class="da-sk da-sk-banner"></div><div class="da-sk-row"><div class="da-sk da-sk-ring"></div><div class="da-sk da-sk-blk"></div></div><div class="da-sk-row"><div class="da-sk da-sk-card"></div><div class="da-sk da-sk-card"></div><div class="da-sk da-sk-card"></div><div class="da-sk da-sk-card"></div></div></div>';
  }
  function blank(icon, title, msg, btn) {
    return '<div class="da-blank">' + ico(icon, 'da-i-lg') + '<p class="da-blank-t">' + title + '</p><p class="da-mut">' + msg + '</p>' + (btn || '') + '</div>';
  }
  var RUN_BTN = '<button type="button" class="c-btn c-btn--primary" data-act="run">' + ico('play') + '分析を実行</button>';

  /* ---------- ホーム ---------- */
  function gauge(s) {
    var R = 52, C = 2 * Math.PI * R, ne = !s || s.value == null;
    var v = ne ? 0 : Math.max(0, Math.min(100, Number(s.value)));
    var tone = ne ? 'mute' : v >= 80 ? 'ok' : v >= 50 ? 'warn' : 'bad';
    var arc = ne ? '' : '<circle class="da-ring-v da-tone-' + tone + '" cx="66" cy="66" r="' + R + '" fill="none" stroke-width="12" stroke-linecap="round" stroke-dasharray="' + (C * v / 100).toFixed(1) + ' ' + C.toFixed(1) + '" transform="rotate(-90 66 66)"/>';
    var cov = s ? pct(s.coverage) : 0;
    var label = ne ? (s ? '総合スコア 評価不能。評価できた範囲 ' + cov + '%' : '総合スコア 未実行') : '総合スコア ' + Math.round(v) + '点。評価できた範囲 ' + cov + '%';
    return '<button type="button" class="da-gauge" data-score="Overall" aria-label="' + label + '。根拠を見る"><svg viewBox="0 0 132 132" aria-hidden="true"><circle cx="66" cy="66" r="' + R + '" fill="none" stroke-width="12" class="da-ring-t"/>' + arc + '</svg>'
      + '<span class="da-gauge-c">' + (ne ? '<b class="da-gauge-n da-gauge-ne">' + (s ? '評価不能' : '未実行') + '</b>' : '<b class="da-gauge-n">' + Math.round(v) + '<small>/100</small></b>')
      + '<span class="da-gauge-s">' + (s ? '評価できた範囲 ' + cov + '%' : '分析すると表示') + '</span></span></button>';
  }
  function dimCard(key, label, s) {
    if (!s) return '<button type="button" class="da-dim da-ne" data-score="' + key + '"><span class="da-sl">' + label + '</span><span class="da-sv">未実行</span></button>';
    if (s.value == null) return '<button type="button" class="da-dim da-ne" data-score="' + key + '" aria-label="' + label + ' 評価不能。根拠を見る"><span class="da-sl">' + label + '</span><span class="da-sv">評価不能</span><span class="da-sc">評価できた範囲 ' + pct(s.coverage) + '%</span></button>';
    return '<button type="button" class="da-dim" data-score="' + key + '" aria-label="' + label + ' ' + Math.round(s.value) + '点。根拠を見る"><span class="da-sl">' + label + '</span><span class="da-sv">' + Math.round(s.value) + '<small>/100</small></span><span class="da-bar"><i style="width:' + Math.max(0, Math.min(100, s.value)) + '%"></i></span><span class="da-sc">評価できた範囲 ' + pct(s.coverage) + '%</span></button>';
  }
  function countCard(label, n, tone, go, goLabel) {
    var body = n === 'fail' ? '<b class="da-cn da-cn-ne">取得できません</b><span class="da-mut">「もう一度読み込む」で再取得してください</span>' : n == null ? '<b class="da-cn da-cn-ne">未実行</b><span class="da-mut">分析を実行すると表示されます</span>'
      : n === 0 ? '<b class="da-cn">0</b><span class="da-mut">検出なし（検出できた範囲）</span>'
        : '<b class="da-cn da-tx-' + tone + '">' + n + '</b><span class="da-mut">件</span>';
    return '<button type="button" class="da-cc' + (n && n !== 'fail' ? ' da-cc-' + tone : '') + '" data-tab="' + go + '"><span class="da-cc-l">' + label + '</span>' + body + '</button>';
  }
  function nextActions(rd) {
    var a = [], f = liveFindings(), cf = (body('conflicts') || {}).conflicts || [], t = tests();
    var open = function (x) { return DONE_STATUS.indexOf(x.status) < 0; };
    var un = cf.filter(function (c) { return c.status === 'UNRESOLVED'; });
    if (un.length) a.push(['矛盾「' + un[0].topic + '」ほか ' + un.length + ' 件の、正しい方を決める', 'conf', '']);
    var hi = f.filter(function (x) { return (x.severity === 'critical' || x.severity === 'high') && open(x); });
    if (hi.length) a.push(['致命的・高の指摘 ' + hi.length + ' 件を、採用・却下・期限つきで免除のどれにするか決める', 'issues', 'sev:' + hi[0].severity]);
    var nt = Object.keys(t).filter(function (k) { return t[k].verdict === 'NOT_TESTABLE'; });
    if (nt.length) a.push(['テスト不可の要件 ' + nt.length + ' 件を、書き換え案を見て直す', 'req', 'nt']);
    var orph = orphanReqs() || 0;
    if (orph) a.push(['設計・テストとのつながりが見つからない要件 ' + orph + ' 件を確かめる（候補）', 'trace', '']);
    if (!a.length && rd) a.push(['決めることはありません。評価できなかった範囲は、品質スコアの根拠で確認してください', 'home', '']);
    return a.slice(0, 3);
  }
  function recentHtml() {
    var d = S.data.diff;
    if (failed('diff')) return '<p class="da-tx-bad">変更点を読み込めませんでした。「意味差分」タブで再取得してください。</p>';
    if (!d || !d.ok) return '<p class="da-mut">比較できる前の版がありません。文書を更新して取り込むと、変更点が表示されます。</p>';
    var list = d.body.diff || [];
    if (!list.length) return '<p class="da-mut">前の版からの変更は検出されませんでした（検出できた範囲）。</p>';
    var CH = { MODIFIED: '変更', ADDED: '追加', REMOVED: '削除', SPLIT: '分割', MERGED: '統合', MOVED: '位置のみ変更', RENAMED: '名前の変更' };
    return '<ul class="da-recent">' + list.slice(0, 4).map(function (x) {
      var sv = x.risk === 'high' || x.risk === 'critical' ? 'high' : 'medium';
      return '<li><span class="da-sev da-sev-' + sv + '">' + (SEV[sv][0]) + ' 影響 ' + (sv === 'high' ? '大' : '中') + '</span> <b>' + esc(x.requirement_id) + '</b> ' + esc(CH[x.change] || x.change) + (x.before_value && x.after_value ? '：' + esc(x.before_value) + ' → ' + esc(x.after_value) : '') + '<br><span class="da-mut">' + esc(x.topic || '') + '</span></li>';
    }).join('') + '</ul>' + (list.length > 4 ? '<p class="da-mut">ほか ' + (list.length - 4) + ' 件。詳しくは「意味差分」タブで確認できます。</p>' : '');
  }
  function homeHtml() {
    var req = body('requirements'), iss = body('issues'), cf = body('conflicts'), sc = body('scores');
    var rd = (req && req.readiness) || (sc && sc.readiness) || null;
    var mode = (req && req.mode) || (sc && sc.mode);
    if (!rd && notRun('scores')) return blank('mute', 'まだ分析していません', '「分析を実行」を押すと、文書が次の工程へ進める状態かを判定し、直すべき点と決めることを示します。', RUN_BTN);
    var h = '';
    if (rd) {
      var st = STATE[rd.state] || [rd.state, 'mute'];
      h += '<section class="da-banner da-bn-' + st[1] + '" aria-label="準備状態"><span class="da-bn-ic">' + ico(st[1]) + '</span><div><p class="da-bn-t">準備状態：' + esc(st[0]) + '</p><p class="da-bn-w"><b>なぜこの状態か</b> ' + (rd.reasons || []).map(function (x) { return esc(jp(x)); }).join(' ／ ') + '</p></div></section>';
    }
    if (mode === 'DETERMINISTIC_ONLY') h += '<p class="da-note">ⓘ AI レビューは実行していません（規則による分析のみ）。AI の観点は評価に含まれていません。</p>';
    var f = liveFindings().filter(function (x) { return x.result === 'FAIL' || !x.result; });
    var hiN = f.filter(function (x) { return x.severity === 'critical' || x.severity === 'high'; }).length;
    var orph = orphanReqs();
    var cfl = (cf && cf.conflicts) || [];
    h += '<div class="da-cards">' + countCard('致命的・高の指摘', iss ? hiN : failed('issues') ? 'fail' : null, 'bad', 'issues')
      + countCard('矛盾', cf ? cfl.length : failed('conflicts') ? 'fail' : null, 'warn', 'conf')
      + countCard('確認が必要な質問', cf ? cfl.filter(function (c) { return c.status === 'UNRESOLVED'; }).length : failed('conflicts') ? 'fail' : null, 'warn', 'conf')
      + countCard('つながりが見つからない要件（候補）', orph == null && failed('trace') ? 'fail' : orph, 'info', 'trace') + '</div>';
    var na = nextActions(rd);
    h += '<div class="da-grid2"><section class="da-card"><h3 class="da-h">次にやること（決める）</h3>' + (na.length ? '<ol class="da-next">' + na.map(function (x) {
      return '<li><button type="button" class="da-next-b" data-tab="' + x[1] + '"' + (x[2] ? ' data-pre="' + esc(x[2]) + '"' : '') + '><span>' + esc(x[0]) + '</span>' + ico('arrow') + '</button></li>'; }).join('') + '</ol>' : '<p class="da-mut">分析を実行すると表示されます。</p>')
      + '</section><section class="da-card"><h3 class="da-h">直近の変更</h3>' + recentHtml() + '</section></div>';
    var scores = (sc && sc.scores) || {};
    h += '<div class="da-grid2"><section class="da-card da-ringcard"><h3 class="da-h">品質スコア</h3>' + gauge(sc ? scores.Overall || null : null)
      + '<p class="da-mut">押すと根拠（含めた指標・評価不能・主な減点）を見られます。評価できなかった範囲は点数にしません。</p></section>'
      + '<section class="da-card"><h3 class="da-h">指標ごとの状態</h3><div class="da-dims">' + SCORES.filter(function (p) { return p[0] !== 'Overall'; }).map(function (p) { return dimCard(p[0], p[1], sc ? scores[p[0]] : null); }).join('') + '</div></section></div>';
    return h;
  }

  /* ---------- 要件一覧 ---------- */
  function reqModel() {
    var rq = body('requirements') || {}, f = liveFindings(), t = tests(), tr = body('trace');
    var cfIds = {}; ((body('conflicts') || {}).conflicts || []).forEach(function (c) { (c.evidence || []).forEach(function (e) { cfIds[e.requirement_id] = 1; }); });
    var deg = {}, orph = {};
    if (tr && tr.graph) {
      (tr.graph.edges || []).forEach(function (e) { if (e.kind !== 'contains') { deg[e.src] = (deg[e.src] || 0) + 1; deg[e.dst] = (deg[e.dst] || 0) + 1; } });
      (tr.graph.orphans || []).forEach(function (o) { orph[o.node_id] = (orph[o.node_id] || []).concat(o.kind); });
    }
    return (rq.requirements || []).map(function (u) {
      var key = u.document_id + ':' + u.requirement_id, mine = f.filter(function (x) { return x.requirement_id === u.requirement_id; });
      var open = mine.filter(function (x) { return DONE_STATUS.indexOf(x.status) < 0; }).length;
      var inf = Object.keys(u.fields || {}).some(function (k) { return u.fields[k] && u.fields[k].provenance === 'INFERRED'; });
      var state = cfIds[u.requirement_id] ? ['矛盾あり', 'bad'] : open ? ['要確認', 'warn'] : mine.length ? ['判断済み', 'ok'] : ['検出なし', 'mute'];
      return { u: u, key: key, verdict: (t[key] || {}).verdict, n: mine.length, cf: !!cfIds[u.requirement_id], inf: inf, state: state, link: tr ? (orph[key] ? 0 : (deg[key] || 0)) : null, orphan: !!orph[key] };
    });
  }
  function reqRows() {
    var rows = reqModel().filter(function (m) {
      if (S.filter === 'nt' && m.verdict !== 'NOT_TESTABLE') return false;
      if (S.filter === 'cf' && !m.cf) return false;
      if (S.filter === 'ai' && !m.inf) return false;
      if (S.q) { var q = S.q.toLowerCase(); if ((m.u.requirement_id + ' ' + (m.u.raw_text || '')).toLowerCase().indexOf(q) < 0) return false; }
      return true;
    });
    rows.sort(function (a, b) {
      if (S.sort === 'issues') return b.n - a.n;
      if (S.sort === 'test') return (TEST_ORDER[a.verdict] == null ? 2 : TEST_ORDER[a.verdict]) - (TEST_ORDER[b.verdict] == null ? 2 : TEST_ORDER[b.verdict]);
      return String(a.u.requirement_id).localeCompare(String(b.u.requirement_id), 'ja', { numeric: true });
    });
    return rows;
  }
  function reqRowsHtml(rows) {
    if (!rows.length) return '<tr><td colspan="7" class="da-mut">この条件に当てはまる要件はありません。検索語を消すか、「すべて」に戻してください。</td></tr>';
    return rows.map(function (m) {
      var u = m.u, tt = m.verdict ? (TEST[m.verdict] || ['?', m.verdict, 'mute']) : ['―', '未判定', 'mute'];
      var lk = m.link == null ? '<span class="da-mut">未実行</span>' : m.link ? ico('link') + m.link + ' 件' : '<span class="da-tx-warn" title="見つからなかっただけで、無いとは限りません">未検出</span>';
      return '<tr class="da-reqrow" tabindex="0" role="button" aria-label="要件 ' + esc(u.requirement_id) + ' の詳細を開く" data-req="' + esc(m.key) + '"><td class="da-id">' + esc(u.requirement_id) + '<br><span class="da-mut">' + esc(u.document_id) + '</span></td><td class="da-tt">' + esc(u.raw_text) + '</td><td class="da-c-opt">' + esc(KIND[u.kind] || u.kind) + '</td>'
        + '<td><span class="da-pill da-pill-' + tt[2] + '"><span aria-hidden="true">' + tt[0] + '</span> ' + tt[1] + '</span></td><td class="da-c-opt">' + lk + '</td><td>' + (m.n ? '<b>' + m.n + '</b> 件' : '<span class="da-mut">0</span>') + '</td><td class="da-c-opt"><span class="da-pill da-pill-' + m.state[1] + '">' + m.state[0] + '</span></td></tr>';
    }).join('');
  }
  function reqHtml() {
    var rq = body('requirements');
    if (!rq) return empty('要件', 'requirements');
    if (!(rq.requirements || []).length) return empty('要件', null);
    var rows = reqRows();
    var chips = [['', 'すべて'], ['nt', 'テスト不可'], ['cf', '矛盾あり'], ['ai', 'AI 推論を含む']].map(function (c) {
      return '<button type="button" class="da-chip" aria-pressed="' + (S.filter === c[0]) + '" data-filter="' + c[0] + '">' + c[1] + '</button>'; }).join('');
    var so = [['id', 'ID 順'], ['issues', '指摘が多い順'], ['test', 'テスト可能性が低い順']].map(function (o) { return '<option value="' + o[0] + '"' + (S.sort === o[0] ? ' selected' : '') + '>' + o[1] + '</option>'; }).join('');
    return '<div class="da-tools"><label class="da-search"><span class="da-sr">要件を検索</span><input type="search" id="da-q" placeholder="ID・本文で検索" value="' + esc(S.q) + '" autocomplete="off"></label>'
      + '<div class="da-chips" role="group" aria-label="絞り込み">' + chips + '</div><label class="da-fl">並べ替え <select id="da-sort">' + so + '</select></label><span class="da-mut" id="da-cnt" role="status">' + rows.length + ' / ' + rq.requirements.length + ' 件</span></div>'
      + '<table class="da-table da-req"><thead><tr><th>ID</th><th>要件</th><th class="da-c-opt">種別</th><th>テスト可能性</th><th class="da-c-opt">つながり</th><th>指摘</th><th class="da-c-opt">状態</th></tr></thead><tbody id="da-rows">' + reqRowsHtml(rows) + '</tbody></table>';
  }

  /* ---------- 指摘一覧 ---------- */
  function ifOpts(list, key, k) {
    var seen = {}; list.forEach(function (x) { var v = key(x); if (v) seen[v] = 1; });
    return Object.keys(seen).sort().map(function (v) { return '<option value="' + esc(v) + '"' + (S.ifilter[k] === v ? ' selected' : '') + '>' + esc(v) + '</option>'; }).join('');
  }
  function fDoc(x) { return (x.location && x.location.document_id) || x.document_id || ''; }
  function fKind(x) { return x.category || x.kind || x.type || ''; }
  function reasonBox(id, extra) {
    var d = S.draft[id] || {};
    return '<label class="da-reason">判断の理由<textarea rows="2" data-reason="' + id + '" placeholder="例：仕様書 3.2 節で確認済みのため採用">' + esc(d.reason || '') + '</textarea></label>' + (extra || '')
      + (S.ferr[id] ? '<p class="da-ferr" role="alert">' + esc(S.ferr[id]) + '</p>' : '');
  }
  function findingCard(x) {
    var sv = SEV[x.severity] || ['?', x.severity], loc = x.location || {}, fid = esc(x.finding_id || '');
    var st = x.waiver_expired ? '<b>期限切れ。再度確認が必要</b>' : (STATUS[x.status] || esc(x.status)) + (x.status === 'WAIVED' && x.waiver_expiry ? '（期限 ' + esc(String(x.waiver_expiry).slice(0, 10)) + '）' : '');
    var form = fid ? '<details class="da-dec" data-fid="' + fid + '"' + (S.openF[x.finding_id] ? ' open' : '') + '><summary>' + (DONE_STATUS.indexOf(x.status) >= 0 ? '記録した判断を変える' : '判断を記録する') + '</summary>'
      + reasonBox(fid, '<label class="da-reason">免除の期限（「期限つきで免除」のときだけ）<input type="date" data-expiry="' + fid + '" value="' + esc((S.draft[fid] || {}).expiry || '') + '"></label>')
      + '<div class="da-actions"><button type="button" class="c-btn c-btn--secondary c-btn--sm" data-fdecide="' + fid + '" data-d="accepted">採用</button><button type="button" class="c-btn c-btn--secondary c-btn--sm" data-fdecide="' + fid + '" data-d="rejected">却下</button><button type="button" class="c-btn c-btn--secondary c-btn--sm" data-fdecide="' + fid + '" data-d="waived">期限つきで免除</button></div></details>' : '<span class="da-mut">判断できません</span>';
    var snip = loc.snippet || x.reason || '';
    return '<article class="da-fc da-fc-' + esc(x.severity) + '"><header class="da-fc-h"><span class="da-sev da-sev-' + esc(x.severity) + '"><span aria-hidden="true">' + sv[0] + '</span> ' + esc(sv[1]) + '</span><b class="da-fc-t">' + esc(x.title || x.rule_id) + '</b>'
      + '<span class="da-badge da-b-' + esc(x.source) + '" title="検出元">' + esc(SRC[x.source] || x.source) + '</span><span class="da-mut" title="' + esc(confFull(x.confidence)) + '">関連度: ' + conf(x.confidence) + '</span><span class="da-fc-st">' + st + '</span></header>'
      + (snip ? '<blockquote class="da-quote">' + esc(snip) + '</blockquote>' : '')
      + '<p class="da-mut">要件 ' + esc(x.requirement_id || '―') + ' ・ ' + esc(fDoc(x)) + ' ' + esc(loc.section || '') + (loc.line_start ? ' ・ ' + esc(loc.line_start) + ' 行目' : '') + '</p>'
      + (x.how_to_fix ? '<p class="da-fix"><b>直し方の例</b> ' + esc(x.how_to_fix) + '</p>' : '') + form + '</article>';
  }
  function issuesHtml() {
    var b = body('issues');
    if (!b) return empty('指摘', 'issues');
    var all = liveFindings();
    if (!all.length) return blank('ok', '検出なし（検出できた範囲）', '規則と AI で検出できた範囲に指摘はありません。評価できなかった範囲は、ホームの品質スコアの根拠で確認してください。');
    var F = S.ifilter;
    var f = all.filter(function (x) {
      return (!F.sev || x.severity === F.sev) && (!F.kind || fKind(x) === F.kind) && (!F.doc || fDoc(x) === F.doc)
        && (!F.req || x.requirement_id === F.req) && (!F.status || (x.waiver_expired ? 'EXPIRED' : x.status) === F.status) && (!F.src || x.source === F.src);
    });
    var sel = function (k, label, opts) { return '<label class="da-fl">' + label + ' <select data-if="' + k + '"><option value="">すべて</option>' + opts + '</select></label>'; };
    var stO = Object.keys(STATUS).concat(['EXPIRED']).map(function (k) { return '<option value="' + k + '"' + (F.status === k ? ' selected' : '') + '>' + (k === 'EXPIRED' ? '免除の期限切れ' : STATUS[k]) + '</option>'; }).join('');
    var srcO = Object.keys(SRC).map(function (k) { return '<option value="' + k + '"' + (F.src === k ? ' selected' : '') + '>' + SRC[k] + '</option>'; }).join('');
    var chips = '<div class="da-chips" role="group" aria-label="重大度で絞り込み"><button type="button" class="da-chip" aria-pressed="' + !F.sev + '" data-sev="">すべて ' + all.length + '</button>' + Object.keys(SEV).map(function (k) {
      var n = all.filter(function (x) { return x.severity === k; }).length;
      return n ? '<button type="button" class="da-chip" aria-pressed="' + (F.sev === k) + '" data-sev="' + k + '"><span aria-hidden="true">' + SEV[k][0] + '</span> ' + SEV[k][1] + ' ' + n + '</button>' : ''; }).join('') + '</div>';
    var bar = '<div class="da-filters" role="group" aria-label="指摘の絞り込み">' + sel('kind', '種別', ifOpts(all, fKind, 'kind')) + sel('doc', '文書', ifOpts(all, fDoc, 'doc'))
      + sel('req', '要件', ifOpts(all, function (x) { return x.requirement_id; }, 'req')) + sel('status', '状態', stO) + sel('src', '検出元', srcO) + '</div>';
    return chips + bar + '<p class="da-mut" role="status">' + f.length + ' / ' + all.length + ' 件を表示</p>'
      + (f.length ? '<div class="da-flist">' + f.map(findingCard).join('') + '</div>' : '<p class="da-mut">この条件に当てはまる指摘はありません。絞り込みを「すべて」に戻してください。</p>');
  }

  /* ---------- 矛盾 ---------- */
  function conflictsHtml() {
    var b = body('conflicts');
    if (!b) return empty('矛盾', 'conflicts');
    var list = b.conflicts || [];
    if (!list.length) return blank('ok', '検出なし（検出できた範囲）', '矛盾は見つかっていません。見つからないことは、矛盾が無いことの証明ではありません。');
    return list.map(function (c) {
      var ev = c.evidence || [];
      var col = function (e, label, side) {
        if (!e) return '<div class="da-ev"><b class="da-ev-l">' + label + '</b><p class="da-mut">対応する記述がありません。</p></div>';
        return '<div class="da-ev da-ev-' + side + '"><b class="da-ev-l">' + label + '</b><blockquote class="da-quote">' + esc(e.quote) + '</blockquote><p class="da-mut">' + esc(e.document_id) + ' ・ ' + esc(e.requirement_id) + (e.location && e.location.line_start ? ' ・ ' + esc(e.location.line_start) + ' 行目' : '') + '</p></div>';
      };
      var id = esc(c.conflict_id);
      return '<article class="da-card da-cf"><h3 class="da-h">' + esc(c.topic) + ' <span class="da-badge">' + (STATUS[c.status] || esc(c.status)) + '</span> <span class="da-mut" title="' + esc(confFull(c.confidence)) + '">関連度: ' + conf(c.confidence) + '</span></h3>'
        + '<p class="da-note">⚠ どちらが正しいかは未確定です。人が確かめて決めてください。</p>'
        + '<div class="da-pair">' + col(ev[0], '根拠 A', 'a') + '<span class="da-vs" aria-hidden="true">' + ico('swap') + '</span>' + col(ev[1], '根拠 B', 'b') + '</div>'
        + (c.question ? '<p class="da-fix"><b>確認したいこと</b> ' + esc(c.question) + '</p>' : '')
        + '<fieldset class="da-pick"><legend>どちらを正としますか</legend>' + [['A', '根拠 A を正とする'], ['B', '根拠 B を正とする'], ['N', 'どちらも違う（文書を直す）']].map(function (o) {
          var on = (S.draft[c.conflict_id] || {}).pick === o[0];
          return '<label class="da-pick-o"><input type="radio" name="da-pick-' + id + '" value="' + o[0] + '" data-pick="' + id + '"' + (on ? ' checked' : '') + '> ' + o[1] + '</label>'; }).join('') + '</fieldset>'
        + reasonBox(id).replace('判断の理由', '決定の理由')
        + '<div class="da-actions"><button type="button" class="c-btn c-btn--primary c-btn--sm" data-decide="' + id + '" data-d="conflict_decided">決定を記録する</button><button type="button" class="c-btn c-btn--secondary c-btn--sm" data-decide="' + id + '" data-d="rejected">矛盾ではない</button></div></article>';
    }).join('');
  }

  function traceHtml() {
    if (window.DAPanels.trace && window.DAPanels.trace.html) return window.DAPanels.trace.html(ctx());
    var t = body('trace');
    if (!t) return blank('mute', 'まだ分析していません', '「分析を実行」を押すと、要件と設計・テストのつながりが表示されます。', RUN_BTN);
    var g = t.graph || {}, cov = t.coverage;
    return '<section class="da-card"><h3 class="da-h">つながり</h3><p>要素 ' + (g.nodes || []).length + ' 件 ・ つながり ' + (g.edges || []).length + ' 件 ・ つながりの無い要件 ' + (g.orphans || []).length + ' 件</p>'
      + (cov == null ? '' : '<p class="da-mut">カバー率 ' + esc(typeof cov === 'number' ? Math.round(cov * 100) + '%' : JSON.stringify(cov)) + '</p>') + '</section>';
  }

  function failed(k) { var x = S.data[k]; return !!(x && !x.ok && x.status !== 404); }
  function failBlank(k) {
    var st = S.data[k] && S.data[k].status;
    return st === 403 ? blank('bad', '表示する権限がありません', 'この内容を見る権限がありません。管理者に権限を確認してください。')
      : blank('bad', '読み込めませんでした', 'サーバから受け取れませんでした（状態 ' + esc(st || '接続なし') + '）。「もう一度読み込む」を押してください。', '<button type="button" class="c-btn c-btn--secondary" data-act="reload">もう一度読み込む</button>');
  }
  function empty(what, k) {
    if (k && failed(k)) return failBlank(k);
    var notRunFlag = k ? notRun(k) : false;
    return notRunFlag ? blank('mute', 'まだ分析していません', '「分析を実行」を押すと' + what + 'が表示されます。', RUN_BTN)
      : blank('mute', what + 'は 0 件です', '文書に要件の記述があるか確認し、文書を取り込んでから分析をやり直してください。');
  }

  /* ---------- 枠 ---------- */
  var BASE_TABS = [['home', 'ホーム'], ['req', '要件一覧'], ['issues', '指摘一覧'], ['conf', '矛盾'], ['trace', 'つながり']];
  function tabs() {
    var t = BASE_TABS.slice();
    PANEL_TABS.forEach(function (k) { var p = window.DAPanels[k]; if (p) t.push([k, p.label || k]); });
    return t;
  }
  function tabCount(k) {
    if (!S.loaded) return '';
    var n = k === 'req' ? ((body('requirements') || {}).requirements || []).length : k === 'issues' ? liveFindings().length : k === 'conf' ? ((body('conflicts') || {}).conflicts || []).length : null;
    return n == null || !(body('requirements') || body('issues') || body('conflicts')) ? '' : ' <span class="da-tn">' + n + '</span>';
  }

  function render() {
    var root = $('#da-root');
    if (!root) return;
    var has = !!rid();
    if (!has) {
      root.innerHTML = blank('mute', 'レビューを選んでいません', 'ドキュメント品質保証は、レビューごとに表示します。レビュー一覧から対象を開いてください。', '<a class="c-btn c-btn--primary" href="#reviews" data-go="reviews">レビュー一覧へ</a>');
      return;
    }
    var scored = !notRun('scores') && S.loaded;
    var head = '<div class="da-sticky" id="da-sticky"><div class="da-top"><div class="da-who"><span class="da-mut">対象のレビュー</span><b class="da-name">' + esc(rname()) + '</b></div><div class="da-head-actions">'
      + (scored ? '<a class="c-btn c-btn--ghost c-btn--sm" href="' + url('report.md') + '" download>' + ico('dl') + 'レポート（Markdown）</a><a class="c-btn c-btn--ghost c-btn--sm" href="' + url('report.csv') + '" download>' + ico('dl') + '指摘一覧（CSV）</a>' : '')
      + '<button type="button" class="c-btn c-btn--primary" id="da-run" data-act="run"' + (S.busy ? ' disabled' : '') + '>' + ico('play') + (S.busy && S.stage >= 0 ? '分析中…' : '分析を実行') + '</button></div></div>'
      + '<div class="da-tabs" role="tablist" aria-label="品質保証の表示">' + tabs().map(function (t) {
        return '<button type="button" role="tab" class="da-tab" id="da-t-' + t[0] + '" aria-selected="' + (S.tab === t[0]) + '" tabindex="' + (S.tab === t[0] ? 0 : -1) + '" data-tab="' + t[0] + '">' + t[1] + tabCount(t[0]) + '</button>'; }).join('') + '</div></div>';
    var inner = head;
    if (S.error) inner += '<div class="da-err" role="alert">' + ico('bad') + '<span>' + esc(S.error) + '</span>' + (S.errorDoc ? '<a class="c-btn c-btn--secondary c-btn--sm" href="#reviews" data-go="reviews">レビュー一覧で文書を取り込む</a>' : '') + '</div>';
    if (S.busy && S.stage >= 0) inner += '<div class="da-card" id="da-prog" role="status">' + progHtml() + '</div>';
    var views = { home: homeHtml, req: reqHtml, issues: issuesHtml, conf: conflictsHtml, trace: traceHtml };
    var pn = window.DAPanels[S.tab], isPanel = PANEL_TABS.indexOf(S.tab) >= 0 && pn;
    if (!isPanel && !views[S.tab]) S.tab = 'home';
    var main;
    if (S.busy && !S.loaded) main = skeleton();
    else if (S.loadFail) main = blank('bad', '読み込めませんでした', 'サーバに接続できませんでした。接続を確認してから「もう一度読み込む」を押してください。', '<button type="button" class="c-btn c-btn--secondary" data-act="reload">もう一度読み込む</button>');
    else main = isPanel ? pn.html(ctx()) : views[S.tab]();
    inner += '<div class="da-body" role="tabpanel" aria-labelledby="da-t-' + S.tab + '">' + main + '</div>';
    var focusId = document.activeElement && document.activeElement.id;
    root.innerHTML = inner;
    var nb = root.querySelector('.da-body');
    var st = $('#da-sticky'); if (st) root.style.setProperty('--da-sticky-h', st.offsetHeight + 'px');
    if (!S.busy || S.loaded) {
      if (isPanel && pn.bind && nb) pn.bind(nb, ctx());
      else if (S.tab === 'trace' && window.DAPanels.trace && window.DAPanels.trace.bind && nb) window.DAPanels.trace.bind(nb, ctx());
    }
    if (focusId) { var el = document.getElementById(focusId); if (el) el.focus(); }
  }

  /* ---------- ドロワー（要件の詳細・スコアの根拠） ---------- */
  function drawerEl() {
    var d = document.getElementById('da-drawer');
    if (!d) {
      var bk = document.createElement('div'); bk.id = 'da-backdrop'; bk.className = 'da-backdrop'; bk.hidden = true; bk.setAttribute('data-drawer-close', ''); document.body.appendChild(bk);
      d = document.createElement('aside'); d.id = 'da-drawer'; d.className = 'da-drawer'; d.setAttribute('role', 'dialog'); d.setAttribute('aria-modal', 'true'); d.tabIndex = -1; d.hidden = true;
      document.body.appendChild(d);
    }
    return d;
  }
  function drawerOpen() { var d = document.getElementById('da-drawer'); return !!(d && !d.hidden); }
  function closeDrawer() {
    var d = document.getElementById('da-drawer'); if (!d || d.hidden) return;
    d.hidden = true; var bk = document.getElementById('da-backdrop'); if (bk) bk.hidden = true;
    if (S.drawerFocus && document.contains(S.drawerFocus) && S.drawerFocus.focus) S.drawerFocus.focus();
    S.drawerFocus = null;
  }
  function showDrawer(title, html, trigger) {
    var d = drawerEl();
    if (d.hidden) S.drawerFocus = trigger;
    d.setAttribute('aria-label', title);
    d.innerHTML = '<header class="da-dr-h"><h3 class="da-h">' + esc(title) + '</h3><button type="button" class="c-btn c-btn--ghost c-btn--sm" data-drawer-close aria-label="閉じる">' + ico('x') + '閉じる (Esc)</button></header><div class="da-dr-b">' + html + '</div>';
    d.hidden = false; document.getElementById('da-backdrop').hidden = false; d.focus();
  }
  function explain(key, trigger) {
    var sc = ((body('scores') || {}).scores || {})[key];
    if (!sc) return;
    var label = (SCORES.filter(function (p) { return p[0] === key; })[0] || [0, key])[1];
    var list = function (a) { return a && a.length ? '<ul class="da-list">' + a.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : '<p class="da-mut">なし</p>'; };
    var uniq = function (a) { var s = {}; return (a || []).filter(function (x) { return s[x] ? false : (s[x] = 1); }); };
    var head = sc.value == null ? '<p class="da-note">評価不能です。点数は付けていません（評価できた範囲 ' + pct(sc.coverage) + '%）。</p>' : '<p class="da-big">' + Math.round(sc.value) + ' 点 <span class="da-mut">評価できた範囲 ' + pct(sc.coverage) + '%</span></p>';
    showDrawer(label + ' の根拠', head + '<h4>評価に含めたもの</h4>' + list(uniq(sc.included)) + '<h4>評価できなかったもの</h4>' + list(uniq(sc.not_evaluated)) + '<h4>主な減点理由</h4>' + list(sc.explanation), trigger);
  }
  function fieldVal(f) { if (f && typeof f === 'object') return f.value != null ? f.value : (f.text != null ? f.text : ''); return f == null ? '' : f; }
  function drawerBody(u, key) {
    var tc = tests()[key] || {};
    var f = liveFindings().filter(function (x) { return x.requirement_id === u.requirement_id; });
    var loc = u.location || {}, line = u.line_start || loc.line_start;
    var h = '<h4>原文</h4><blockquote class="da-quote">' + esc(u.raw_text || u.snippet || '') + '</blockquote><p class="da-mut">' + esc(u.document_id) + (line ? ' ・ ' + esc(line) + ' 行目' : '') + (u.snippet && u.snippet !== u.raw_text ? '<br>' + esc(u.snippet) : '') + '</p>'
      + '<h4>構造化フィールド</h4><dl class="da-kv">' + FIELDS.map(function (p) {
        var fv = (u.fields || {})[p[0]]; if (fv == null || fv === '') return '';
        var pv = fv && fv.provenance;
        return '<div><dt>' + p[1] + '</dt><dd>' + esc(fieldVal(fv)) + ' <span class="da-badge da-prov-' + esc(pv || 'NONE') + '">' + (pv ? esc(PROV[pv] || pv) : '出所不明') + '</span></dd></div>';
      }).join('') + '</dl>';
    var tt = tc.verdict ? (TEST[tc.verdict] || ['?', tc.verdict, 'mute']) : null;
    h += '<h4>テスト可能性</h4>' + (tt ? '<p><span class="da-pill da-pill-' + tt[2] + '"><span aria-hidden="true">' + tt[0] + '</span> ' + esc(tt[1]) + '</span></p>' : '<p class="da-mut">未判定</p>')
      + ((tc.reasons || []).length ? '<ul class="da-list">' + tc.reasons.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : '')
      + ((tc.missing || []).length ? '<p><b>不足している情報</b></p><ul class="da-list">' + tc.missing.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : '')
      + (tc.rewrite_proposal ? '<p><b>提案（未承認）</b></p><p>' + esc(typeof tc.rewrite_proposal === 'string' ? tc.rewrite_proposal : JSON.stringify(tc.rewrite_proposal)) + '</p>' : '');
    h += '<h4>関連する指摘</h4>' + (f.length ? '<ul class="da-list">' + f.map(function (x) { return '<li>' + esc((SEV[x.severity] || ['', x.severity])[1]) + ' ' + esc(x.title || x.rule_id) + '<br><span class="da-mut">' + esc((x.location && x.location.snippet) || x.reason || '') + '</span></li>'; }).join('') + '</ul>' : '<p class="da-mut">検出なし（検出できた範囲）</p>');
    h += '<h4>書き換え案</h4><div id="da-rw">' + rwHtml(S.rw[u.requirement_id]) + '</div>';
    return h;
  }
  function rwHtml(r) {
    if (r === undefined) return '<p class="da-mut" role="status">読み込み中…</p>';
    if (!r) return '<p class="da-mut">書き換え案はありません。</p>';
    var txt = function (v) { return typeof v === 'string' ? v : JSON.stringify(v); };
    var out = '<p class="da-note">提案（未承認）です。採用するかは人が決めます。この案は原文からの推測で、事実ではありません。</p>';
    if (typeof r === 'string') return out + '<pre class="da-pre">' + esc(r) + '</pre>';
    var LV = { minimal: '最小の直し方', recommended: '推奨の直し方', strict: '厳密な直し方' }, GW = { given: '前提（Given）', when: '操作（When）', then: '結果（Then）' };
    var fl = r.fix_levels && typeof r.fix_levels === 'object' ? r.fix_levels : null, pr = r.proposal && typeof r.proposal === 'object' ? r.proposal : null;
    if (fl) out += '<dl class="da-kv">' + Object.keys(LV).filter(function (k) { return fl[k]; }).map(function (k) { return '<div><dt>' + LV[k] + '</dt><dd>' + esc(txt(fl[k])) + '</dd></div>'; }).join('') + '</dl>';
    if (pr) out += '<dl class="da-kv">' + Object.keys(GW).filter(function (k) { return pr[k]; }).map(function (k) { return '<div><dt>' + GW[k] + '</dt><dd>' + esc(txt(pr[k])) + '</dd></div>'; }).join('') + '</dl>';
    if (!fl && !pr) out += '<pre class="da-pre">' + esc(txt(r.proposed_text || r.proposal || r.text || r)) + '</pre>';
    return out;
  }
  function openDrawer(key, trigger) {
    var rq = body('requirements'); if (!rq) return;
    var u = (rq.requirements || []).filter(function (x) { return x.document_id + ':' + x.requirement_id === key; })[0]; if (!u) return;
    showDrawer('要件 ' + u.requirement_id, drawerBody(u, key), trigger);
    var reqId = u.requirement_id;
    if (S.rw[reqId] === undefined) {
      get('rewrite/' + encodeURIComponent(reqId)).then(function (r) {
        S.rw[reqId] = r.ok ? (r.body || null) : null;   // 404 等は無視して「なし」表示
        var box = document.getElementById('da-rw'); if (box && drawerOpen()) box.innerHTML = rwHtml(S.rw[reqId]);
      });
    }
  }

  /* ---------- 判断の記録 ---------- */
  function draftOf(id) { var ta = document.querySelector('textarea[data-reason="' + id + '"]'); var ex = document.querySelector('input[data-expiry="' + id + '"]'); var pk = document.querySelector('input[data-pick="' + id + '"]:checked'); var o = S.draft[id] || {}; S.draft[id] = { reason: ta ? ta.value : o.reason, expiry: ex ? ex.value : o.expiry, pick: pk ? pk.value : o.pick }; return S.draft[id]; }
  function decide(id, d) {
    var dr = draftOf(id), reason = dr.reason, PICK = { A: '根拠 A を正とする', B: '根拠 B を正とする', N: 'どちらも違う' };
    if (d === 'conflict_decided' && !dr.pick) { S.ferr[id] = 'どちらを正とするかを選んでから、もう一度押してください。'; render(); return; }
    if (!reason || !reason.trim()) { S.ferr[id] = '理由が空です。理由を入力してからもう一度押してください。'; render(); return; }
    if (d === 'conflict_decided') reason = '【' + PICK[dr.pick] + '】' + reason.trim();
    post('decisions', { decision: d, target: id, reason: reason.trim(), expiry: null }).then(function (r) {
      S.ferr[id] = r.ok ? '' : ((r.body && r.body.error) || '記録できませんでした。') + ' 権限を確認してから、もう一度お試しください。';
      if (r.ok) { delete S.draft[id]; toast(d === 'rejected' ? '「矛盾ではない」と記録しました。' : '決定を記録しました。'); return load(); }
      render();
    });
  }
  function decideFinding(id, d) {
    var dr = draftOf(id), reason = dr.reason;
    if (!reason || !reason.trim()) { S.ferr[id] = '理由が空です。理由を入力してからもう一度押してください。'; S.openF[id] = true; render(); return; }
    var expiry = null;
    if (d === 'waived') {
      expiry = dr.expiry || '';
      if (!expiry) { S.ferr[id] = '期限つきで免除するには期限が必要です。期限の日付を入力してからもう一度押してください。'; S.openF[id] = true; render(); return; }
    }
    post('decisions', { decision: d, target: id, reason: reason.trim(), expiry: expiry }).then(function (r) {
      S.ferr[id] = r.ok ? '' : ((r.body && r.body.error) || '記録できませんでした。') + ' 権限を確認してから、もう一度お試しください。';
      if (r.ok) { delete S.draft[id]; delete S.openF[id]; toast('判断を記録しました（' + ({ accepted: '採用', rejected: '却下', waived: '期限つきで免除' }[d] || d) + '）。'); return load(); }
      S.openF[id] = true; render();
    });
  }

  function setTab(t, pre) {
    S.tab = t;
    if (pre === 'nt' || pre === 'cf' || pre === 'ai') S.filter = pre;
    if (pre && pre.indexOf('sev:') === 0) S.ifilter = Object.assign({}, S.ifilter, { sev: pre.slice(4) });
    render(); var n = document.getElementById('da-t-' + S.tab); if (n) n.focus();
    var sc = document.querySelector('.dv-content'), st = document.getElementById('da-sticky'); if (sc && st && st.getBoundingClientRect().top <= sc.getBoundingClientRect().top + 1) sc.scrollTop = Math.max(0, $('#da-root').offsetTop - 8);
  }
  function enter() {
    if (rid() !== S.iid) { S.data = {}; S.loaded = false; S.full = null; S.draft = {}; S.ferr = {}; S.openF = {}; S.rw = {}; }
    if (S.busy) return render();
    load();
  }

  /* ---------- イベント ---------- */
  var isMine = function (t) { return t.closest && t.closest('#da-root, #da-drawer, #da-backdrop'); };
  document.addEventListener('click', function (e) {
    var t = e.target.closest ? e.target : null; if (!t) return;
    var el;
    if ((el = t.closest('#da-open'))) { if (window.DV && window.DV.show) window.DV.show('assure'); return; }
    if (t.closest('[data-drawer-close]')) return closeDrawer();
    if (!isMine(t)) return;
    if ((el = t.closest('[data-act]'))) { if (el.dataset.act === 'run') return analyze(); if (el.dataset.act === 'reload') return load(); }
    if ((el = t.closest('[data-tab]'))) return setTab(el.dataset.tab, el.dataset.pre);
    if ((el = t.closest('[data-filter]'))) { S.filter = el.dataset.filter; return render(); }
    if ((el = t.closest('[data-sev]'))) { S.ifilter = Object.assign({}, S.ifilter, { sev: el.dataset.sev }); return render(); }
    if ((el = t.closest('[data-score]'))) return explain(el.dataset.score, el);
    if ((el = t.closest('[data-fdecide]'))) return decideFinding(el.dataset.fdecide, el.dataset.d);
    if ((el = t.closest('tr[data-req]'))) return openDrawer(el.dataset.req, el);
    if ((el = t.closest('[data-decide]'))) return decide(el.dataset.decide, el.dataset.d);
  });
  document.addEventListener('change', function (e) {
    var el = e.target && e.target.closest ? e.target.closest('[data-if], #da-sort') : null;
    if (!el) return;
    if (el.id === 'da-sort') { S.sort = el.value; return render(); }
    S.ifilter = Object.assign({}, S.ifilter); S.ifilter[el.dataset.if] = el.value;
    el.id = el.id || ('da-if-' + el.dataset.if); render();
  });
  document.addEventListener('input', function (e) {
    var t = e.target;
    if (t && t.id === 'da-q') {
      S.q = t.value; var rows = reqRows(), tb = $('#da-rows'), c = $('#da-cnt');
      if (tb) tb.innerHTML = reqRowsHtml(rows);
      if (c) c.textContent = rows.length + ' / ' + ((body('requirements') || {}).requirements || []).length + ' 件';
    } else if (t && t.matches && (t.matches('textarea[data-reason]') || t.matches('input[data-expiry]') || t.matches('input[data-pick]'))) {
      draftOf(t.dataset.reason || t.dataset.expiry || t.dataset.pick);
    }
  });
  document.addEventListener('toggle', function (e) {
    var d = e.target; if (d && d.matches && d.matches('details[data-fid]')) S.openF[d.dataset.fid] = d.open;
  }, true);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && drawerOpen()) { e.preventDefault(); closeDrawer(); return; }
    if (e.key === 'Tab' && drawerOpen()) {
      var d = document.getElementById('da-drawer'), f = Array.prototype.filter.call(d.querySelectorAll('button,a[href],input,textarea,select,[tabindex="0"]'), function (x) { return !x.disabled && x.offsetParent !== null; });
      if (f.length) {
        var first = f[0], last = f[f.length - 1];
        if (e.shiftKey && (document.activeElement === first || document.activeElement === d)) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
      return;
    }
    if (e.key === 'Enter' && e.target && e.target.matches && e.target.matches('tr[data-req]')) { e.preventDefault(); openDrawer(e.target.dataset.req, e.target); return; }
    if ((e.key === 'ArrowRight' || e.key === 'ArrowLeft') && e.target.matches && e.target.matches('.da-tab')) {
      var TB = tabs(), i = TB.map(function (t) { return t[0]; }).indexOf(S.tab);
      i = (i + (e.key === 'ArrowRight' ? 1 : TB.length - 1)) % TB.length;
      setTab(TB[i][0]);
    }
  });
  window.addEventListener('resize', function () { var st = $('#da-sticky'), r = $('#da-root'); if (st && r) r.style.setProperty('--da-sticky-h', st.offsetHeight + 'px'); });
  if (window.DV && window.DV.on) window.DV.on('assure', enter);
  window.DocAssure = { open: function () { if (window.DV) window.DV.show('assure'); }, close: closeDrawer, reload: load };
})();
