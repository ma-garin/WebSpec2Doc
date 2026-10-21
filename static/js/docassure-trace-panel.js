/* Document Assurance: トレーサビリティ（被覆ファネル → 候補の集計 → 要件一覧＋近傍グラフ）。外部ライブラリなし・自前 SVG のみ。
   真実規律: 観測≠推測（INFERRED は必ず「推測」）／つながりが見つからない≠存在しない／テスト案≠実行済み／未評価≠合格。 */
(function () {
  'use strict';
  window.DAPanels = window.DAPanels || {};

  var STAGES = [
    ['requirement', '要件', '抽出できた要件'],
    ['design', '設計', '画面・API への言及がある'],
    ['test_designed', 'テスト設計', 'テスト案がある'],
    ['execution', '実行', '実行結果がある'],
    ['passed', '合格', '合格の結果がある'],
    ['verified', '検証', '証跡で確かめられた']
  ];
  var NA_TIP = '評価していません。テストの実行結果（System02）がまだ無いため、0 件や合格とは扱いません。';
  var PROV_LABEL = { EXPLICIT: '原文に明記', OBSERVED: '原文に記載', DERIVED: '原文から導出', INFERRED: '推測' };
  var TYPE_LABEL = { Requirement: '要件', BusinessRule: '業務ルール', Document: '文書', Section: '節', Screen: '画面', API: 'API', Test: 'テスト', Evidence: '証跡' };
  var KIND_LABEL = { contains: '記載箇所', mentions: '画面・API を参照', references: '参照', relates: '関連', verifies: 'テストで確認', exercises: 'テストで実行', evidences: '証跡あり' };
  var COLS = [['文書', ['Document', 'Section']], ['要件', ['Requirement', 'BusinessRule']], ['画面・API', ['Screen', 'API']], ['テスト', ['Test']], ['証跡', ['Evidence']]];
  var GAPS = [['any', '要対応'], ['', 'すべて'], ['design', '設計無'], ['test', 'テスト無'], ['evidence', '証跡無']];
  var GAP_TIP = '欠陥とは限りません。候補です。つながりが見つからなかっただけで、無いと証明したものではありません。';
  var GUIDE = '要件を選ぶと、その要件につながる文書・画面・API・テスト・証跡を表示します。';
  var ST = {};   // レビューごとの表示状態（再描画をまたいで保つ）

  function colOf(t) { for (var i = 0; i < COLS.length; i++) if (COLS[i][1].indexOf(t) >= 0) return i; return 4; }
  function level(c) { var n = Number(c); return !isFinite(n) ? '不明' : n >= 0.75 ? '高' : n >= 0.5 ? '中' : '低'; }
  function provName(p) { return PROV_LABEL[p] || '不明'; }
  function cw(ch) { return /[\u0000-ÿ]/.test(ch) ? 7 : 12; }
  /* 幅 px に収まる 2 行へ折り返し、溢れたら末尾を … にする（全文は title） */
  function wrap2(s, px) {
    var lines = ['', ''], w = 0, li = 0, i, ch;
    for (i = 0; i < s.length; i++) {
      ch = s.charAt(i);
      if (w + cw(ch) > px) { if (li === 1) { lines[1] = lines[1].replace(/.$/, '') + '…'; return lines; } li = 1; w = 0; }
      lines[li] += ch; w += cw(ch);
    }
    return lines;
  }
  function reqId(n) { var m = String(n.id || '').split(':'); return m.length > 1 ? m.slice(1).join(':') : n.id; }
  function reqTitle(n) { var id = reqId(n), l = String(n.label || ''); return l.indexOf(id) === 0 ? l.slice(id.length).replace(/^\s+/, '') : l; }

  function model(tr, allReqs) {
    var g = tr.graph || {}, nodes = g.nodes || [], edges = g.edges || [], byId = {}, adj = {};
    nodes.forEach(function (n) { byId[n.id] = n; adj[n.id] = []; });
    edges.forEach(function (e, i) { if (adj[e.src]) adj[e.src].push(i); if (adj[e.dst]) adj[e.dst].push(i); });
    var cov = tr.coverage || {}, st = cov.status || {};
    var hasEvidence = nodes.some(function (n) { return n.type === 'Evidence'; });
    var execNA = !hasEvidence && (cov.execution == null || st.execution === 'NOT_EVALUATED');
    var orph = {};
    (g.orphans || []).forEach(function (o) { (orph[o.node_id] = orph[o.node_id] || {})[o.kind] = o; });
    var reqs = nodes.filter(function (n) { return n.type === 'Requirement'; }).map(function (n) {
      var o = orph[n.id] || {}, ev = reach(n.id, adj, edges, byId, 3, 'Evidence');
      return { n: n, id: reqId(n), title: reqTitle(n), noDesign: !!o.requirement_without_design, noTest: !!o.requirement_without_test,
        noEv: execNA ? null : !ev, orph: o };
    });
    var ids = {}; reqs.forEach(function (r) { ids[r.n.id] = true; });
    var excl = (allReqs || []).filter(function (q) { return q.requirement_id && !ids[(q.document_id || '') + ':' + q.requirement_id]; }).map(function (q) { var t = String(q.raw_text || ''); return { id: q.requirement_id, doc: q.document_id || '', title: t.indexOf(q.requirement_id) === 0 ? t.slice(q.requirement_id.length).replace(/^\s+/, '') : t }; });
    return { nodes: nodes, edges: edges, byId: byId, adj: adj, cov: cov, reqs: reqs, execNA: execNA, excl: excl };
  }
  function reach(id, adj, edges, byId, depth, type) {
    var seen = {}, fr = [id], d; seen[id] = true;
    for (d = 0; d < depth; d++) {
      var nx = [];
      fr.forEach(function (x) { (adj[x] || []).forEach(function (i) { var e = edges[i], o = e.src === x ? e.dst : e.src; if (!seen[o] && e.kind !== 'contains') { seen[o] = true; nx.push(o); } }); });
      if (nx.some(function (o) { return byId[o] && byId[o].type === type; })) return true;
      fr = nx;
    }
    return false;
  }
  /* 2 段目では「節・文書が含む他の要件」へは広げない（同じ章の兄弟は追跡ではなく、線の束になるため） */
  function hood(m, id, depth) {
    var seen = {}, fr = [id], es = {}, d; seen[id] = 0;
    for (d = 1; d <= depth; d++) {
      var nx = [];
      fr.forEach(function (x) { (m.adj[x] || []).forEach(function (i) { var e = m.edges[i], o = e.src === x ? e.dst : e.src; if (!m.byId[o]) return; if (d >= 2 && e.kind === 'contains' && e.src === x) return; es[i] = true; if (!(o in seen)) { seen[o] = d; nx.push(o); } }); });
      fr = nx;
    }
    Object.keys(m.edges).forEach(function (i) { var e = m.edges[i]; if (e.src in seen && e.dst in seen) es[i] = true; });
    return { nodes: seen, edges: Object.keys(es).map(Number) };
  }

  var LATE = { execution: 1, passed: 1, verified: 1 };
  /* 要件ごとの 6 段の経路: true=つながりあり／false=見つからない／null=未接続（評価していない） */
  function path(r, execNA) { var ex = execNA ? null : !r.noEv; return [true, !r.noDesign, !r.noTest, ex, null, null]; }
  function brk(p) { for (var i = 0; i < p.length; i++) if (p[i] === false) return i; return -1; }
  function dots(r, execNA, short) {
    var p = path(r, execNA), b = brk(p), n = 0; while (n < 6 && p[n] === true) n++;
    var pill = b >= 0 ? '<span class="dat-pill" title="' + STAGES[b][1] + 'で途切れ（候補）">' + STAGES[b][1] + (short ? '' : 'で途切れ') + '</span>' : '<span class="dat-pill dat-pill--n" title="途切れた段は見つかっていません。以降は未接続（評価していません）">途切れなし</span>';
    return pill + '<span class="dat-reach" title="6 段のうちつながりを確認できた段の数">到達 ' + n + '/6</span>';
  }
  function covHtml(m, esc, infoTip, allN) {
    var late = [], T = m.reqs.length, reached = [0, 0, 0, 0, 0, 0], lost = [0, 0, 0, 0, 0, 0], ex = m.excl.length;
    m.reqs.forEach(function (r) { var p = path(r, m.execNA); for (var i = 0; i < 6; i++) { if (p[i] === true) reached[i]++; else { if (p[i] === false) lost[i]++; break; } } });
    var head = '追跡対象 ' + T + ' 件' + (ex ? '（重複 ID ' + ex + ' 件は対象外・抽出は ' + (allN || T + ex) + ' 件）' : '');
    var cells = STAGES.map(function (s, i) {
      var c = m.cov[s[0]], isNa = c == null || c.ratio == null || (m.execNA && LATE[s[0]]);
      var l = '<span class="dat-kpi__l" title="' + esc(s[2]) + '">' + (i + 1) + '. ' + esc(s[1]) + '</span>';
      if (isNa) { late.push((i + 1) + '. ' + s[1]); return ''; }
      var p = T ? Math.round(reached[i] / T * 100) : 0;
      return '<div class="dat-kpi' + (lost[i] ? ' dat-kpi--cut' : '') + '" data-stage="' + s[0] + '">' + l + '<span class="dat-kpi__v">' + reached[i] + '<small>/' + T + '</small></span>'
        + '<span class="dax-bar dax-bar--progress dat-bar" aria-hidden="true"><span style="width:' + p + '%"></span></span>'
        + (i === 0 ? '<span class="dat-lost dat-lost--z">起点</span>' : lost[i] ? '<button type="button" class="dax-link dat-lost" data-trgap="brk' + i + '" title="この段で新たにつながりが見つからなくなった ' + lost[i] + ' 件（候補）を一覧に表示">未達 ' + lost[i] + ' 件 ›</button>' : '<span class="dat-lost dat-lost--z">未達 0 件</span>') + '</div>';
    }).join('');
    var notTest = T - reached[2];
    var lp = lost.filter(function (x) { return x; }), lsum = lp.reduce(function (x, y) { return x + y; }, 0);
    var foot0 = lp.length ? '未達 ' + lp.join('＋') + (lp.length > 1 ? '＝' + lsum : '') + ' 件＝一覧の途切れ段の件数。' : '';
    var foot = foot0 + (notTest ? (notTest === T ? T + ' 件すべてが' : T + ' 件中 ' + notTest + ' 件が') + 'テスト設計まで届いていません。' : '');
    return '<section class="dat-kpis" aria-labelledby="dat-cov-h"><h2 class="dat-kpis__h" id="dat-cov-h"><span class="dat-kpis__t">' + esc(head) + '</span><span class="dat-kpis__tip">' + infoTip('到達＝その段までつながった要件の数（分母は追跡対象）。未達 n＝その段で新たにつながりが見つからなくなった数（候補）。' + NA_TIP) + '</span></h2><div class="dat-kpis__row">' + cells + (late.length ? '<div class="dat-late2" title="' + esc(NA_TIP) + '"><span class="dat-kpi__l">' + esc(late.join(' → ')) + '</span><span class="dat-kpi__v">未接続</span><a class="dax-btn dax-btn--sm" href="/systems">実行結果を取り込む</a></div>' : '') + '</div>' + (foot ? '<p class="dat-kpis__foot">' + esc(foot) + '</p>' : '') + '</section>';
  }
  var GAP_SEL = [['design', '設計無'], ['test', 'テスト無'], ['evidence', '証跡無']];
  function gapHtml(m, s, infoTip) {
    var miss = function (r) { return r.noDesign || r.noTest || r.noEv; };
    var n = { excl: m.excl.length, '': m.reqs.length,
      design: m.reqs.filter(function (r) { return r.noDesign; }).length, test: m.reqs.filter(function (r) { return r.noTest; }).length,
      evidence: m.execNA ? null : m.reqs.filter(function (r) { return r.noEv; }).length };
    var tab = function (k, l) {
      var sel = s.gap === k, dis = !n[k];
      return '<button type="button" role="tab" class="dax-segc__opt" aria-selected="' + sel + '" tabindex="' + (sel ? 0 : -1) + '" data-trgap="' + k + '"' + (dis ? ' disabled title="該当 0 件のため選べません（0 件は問題なしを意味しません）"' : '') + '>' + l + '<span class="dat-badge">' + n[k] + '</span></button>';
    };
    var chip = /^brk/.test(s.gap) ? '<button type="button" class="dat-chip" data-trgap="" title="絞り込みを解除">' + STAGES[Number(s.gap.slice(3))][1] + 'で切れ ×</button>' : '';
    return '<div class="dat-gap"><div class="dat-gap__row"><div class="dax-segc" role="tablist" aria-label="要件の絞り込み" title="' + GAP_TIP + '">' + tab('', '追跡対象') + tab('excl', '対象外') + '</div>'
      + chip + '</div></div>';
  }
  function filtered(m, s) { /* brkN = N 段で最初に切れた要件 */
    var q = (s.q || '').toLowerCase();
    return m.reqs.filter(function (r) {
      if (s.gap === 'any' && !(r.noDesign || r.noTest || r.noEv)) return false;
      if (s.gap === 'design' && !r.noDesign) return false;
      if (s.gap === 'test' && !r.noTest) return false;
      if (s.gap === 'evidence' && !r.noEv) return false;
      if (s.gap === 'excl') return false;
      if (/^brk/.test(s.gap) && brk(path(r, m.execNA)) !== Number(s.gap.slice(3))) return false;
      return !q || (r.id + ' ' + r.title).toLowerCase().indexOf(q) >= 0;
    });
  }
  function listHtml(m, s, esc) {
    var list = filtered(m, s);
    var ex = s.gap === 'excl' ? m.excl.filter(function (x) { var q = (s.q || '').toLowerCase(); return !q || (x.id + ' ' + x.title).toLowerCase().indexOf(q) >= 0; }) : [];
    if (!list.length && !ex.length) return '<p class="dax-meta dax-md__none">この条件に当てはまる要件はありません。絞り込みを「すべて」に戻すか、検索語を変えてください。</p>';
    return list.map(function (r) {
      var sel = r.n.id === s.sel;
      return '<button type="button" role="option" class="dat-row" aria-selected="' + sel + '" data-trq="' + esc(r.n.id) + '" title="' + esc(r.n.label || r.id) + '"><span class="dat-row__id">' + esc(r.id) + '</span><span class="dat-row__t">' + esc(r.title) + '</span>' + dots(r, m.execNA, true) + '</button>';
    }).join('') + ex.map(function (x) {
      return '<div class="dat-row dat-excl" role="option" aria-disabled="true" title="追跡の対象外です。同じ要件 ID が文書「' + esc(x.doc) + '」にもあり、つながりを調べていません（問題なしを意味しません）"><span class="dax-item__title"><span class="dax-item__req">' + esc(x.id) + '</span> ' + esc(x.title) + '</span><span class="dax-item__meta"><span class="dat-brk">対象外・文書 ' + esc(x.doc) + ' の同じ ID</span></span></div>';
    }).join('');
  }
  var STG_T = { 1: ['Screen', 'API'], 2: ['Test'], 3: ['Evidence'] };
  function stageTable(m, r, esc) {
    var h = hood(m, r.n.id, 2), p = path(r, m.execNA);
    var rows = STAGES.map(function (st, i) {
      if (i === 0) return '';
      var v = p[i], cell;
      if (v === null) cell = '<span class="dat-na">未接続（評価していません）</span>';
      else {
        var ts = STG_T[i] || [], ns = Object.keys(h.nodes).filter(function (id) { return ts.indexOf(m.byId[id].type) >= 0; });
        cell = ns.length ? ns.map(function (id) { var n = m.byId[id]; return '<span class="dat-tag">' + esc(TYPE_LABEL[n.type] || n.type) + ' ' + esc(n.label || id) + '</span>'; }).join(' ') : '<span class="dat-gapcell">見つかりません（候補）</span>';
      }
      return '<tr class="' + (v === false ? 'is-gap' : '') + '"><th scope="row">' + (i + 1) + '. ' + esc(st[1]) + '</th><td>' + cell + '</td></tr>';
    }).join('');
    return '<section class="dat-stg"><h3 class="dat-next__h">段ごとのつながり</h3><table class="dax-table dat-stgt"><tbody>' + rows + '</tbody></table></section>';
  }
  function nextGap(r, execNA) {
    var p = path(r, execNA), out = [], na = [];
    var first = brk(p), ACT = function (i) { if (i === first) return ''; var c = 'dax-btn dax-btn--sm'; return i === 1 ? '<button type="button" class="' + c + '" data-tab-go="req">設計を紐付け</button>' : i === 2 ? '<button type="button" class="' + c + '" data-tab-go="review">テスト案を生成</button>' : ''; };
    p.forEach(function (v, i) { if (i === 0) return; if (v === false) out.push('<li class="dat-next__row"><span><b>' + (i + 1) + '. ' + STAGES[i][1] + '</b>：' + STAGES[i][2].replace('がある', '') + 'が見つかりません（候補）</span>' + ACT(i) + '</li>'); else if (v === null) na.push((i + 1) + '. ' + STAGES[i][1]); });
    return '<section class="dat-next"><h3 class="dat-next__h">次の段の不足</h3>' + (out.length ? '<ul>' + out.join('') + '</ul>' : '<p class="dax-meta">切れた段は見つかっていません。</p>')
      + (na.length ? '<p class="dax-meta dat-next__na">' + na.join('・') + '：未接続（評価していません。合格とは扱いません）</p>' : '') + '</section>';
  }
  /* 近傍グラフ: 列＝ノード型（文書→要件→画面/API→テスト→証跡）。列内は縦に積むので重ならない */
  function graphSvg(m, h, center, focusId, width, esc) {
    var cols = [[], [], [], [], []];
    Object.keys(h.nodes).forEach(function (id) { cols[colOf(m.byId[id].type)].push(id); });
    cols.forEach(function (c) { c.sort(function (a, b) { return h.nodes[a] - h.nodes[b] || (a < b ? -1 : 1); }); });
    var used = [], i; for (i = 0; i < 5; i++) if (cols[i].length || i === 1) used.push(i);
    var colW = Math.max(130, Math.floor(width / used.length)), W = colW * used.length, bw = colW - 36, BH = 56, STEP = 72, TOP = 34;
    var rows = Math.max.apply(null, used.map(function (c) { return cols[c].length; })), H = TOP + rows * STEP + 8, pos = {};
    used.forEach(function (c, ci) {
      var off = 0;
      cols[c].forEach(function (id, ri) { pos[id] = { x: ci * colW + 18, y: TOP + off + ri * STEP, c: ci }; });
    });
    var out = '<svg class="dat-svg" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" role="group" aria-label="選んだ要件の近傍グラフ">';
    used.forEach(function (c, ci) { out += '<text class="dat-colh" x="' + (ci * colW + 18) + '" y="16">' + esc(COLS[c][0]) + '</text>'; });
    h.edges.forEach(function (ei) {
      var e = m.edges[ei], a = pos[e.src], b = pos[e.dst]; if (!a || !b) return;
      if (a.x > b.x) { var t = a; a = b; b = t; }
      var y1 = a.y + BH / 2, y2 = b.y + BH / 2, d;
      if (a.c === b.c) { var x = a.x; d = 'M' + x + ' ' + y1 + ' C' + (x - 15) + ' ' + y1 + ' ' + (x - 15) + ' ' + y2 + ' ' + x + ' ' + y2; }
      else { var x1 = a.x + bw, x2 = b.x, mx = (x1 + x2) / 2; d = 'M' + x1 + ' ' + y1 + ' C' + mx + ' ' + y1 + ' ' + mx + ' ' + y2 + ' ' + x2 + ' ' + y2; }
      var cls = 'dat-edge' + (e.provenance === 'INFERRED' ? ' dat-infer' : e.provenance === 'DERIVED' ? ' dat-derived' : '') + (e.src === focusId || e.dst === focusId ? ' dat-hot' : '');
      out += '<path class="' + cls + '" d="' + d + '"><title>' + esc(KIND_LABEL[e.kind] || e.kind) + '・出所: ' + esc(provName(e.provenance)) + '</title></path>';
    });
    Object.keys(pos).forEach(function (id) {
      var n = m.byId[id], p = pos[id], tl = TYPE_LABEL[n.type] || n.type, lab = n.type === 'Requirement' ? reqId(n) + ' ' + reqTitle(n) : String(n.label || n.id);
      var ln = wrap2(lab, bw - 16), full = tl + '：' + (n.label || n.id);
      out += '<g class="dat-node' + (id === center ? ' dat-center' : '') + (id === focusId ? ' dat-sel' : '') + '" tabindex="0" role="button" data-trn="' + esc(id) + '" aria-pressed="' + (id === focusId) + '" aria-label="' + esc(full) + '">'
        + '<title>' + esc(full) + '</title><rect class="dat-box" x="' + p.x + '" y="' + p.y + '" width="' + bw + '" height="' + BH + '" rx="' + (n.type === 'Requirement' ? 2 : 8) + '"/>'
        + '<text class="dat-type" x="' + (p.x + 8) + '" y="' + (p.y + 15) + '">' + esc(tl) + (id === center ? '（選択中）' : '') + '</text>'
        + '<text x="' + (p.x + 8) + '" y="' + (p.y + 32) + '">' + esc(ln[0]) + '</text><text x="' + (p.x + 8) + '" y="' + (p.y + 48) + '">' + esc(ln[1]) + '</text></g>';
    });
    return out + '</svg>';
  }
  function legendHtml() {
    var ln = function (cls, t) { return '<li><svg width="30" height="8" aria-hidden="true"><line x1="0" y1="4" x2="30" y2="4" class="dat-edge' + cls + '"/></svg>' + t + '</li>'; };
    return '<ul class="dat-legend" aria-label="線の凡例">' + ln('', '実線: 明示・観測') + ln(' dat-derived', '破線: 導出') + ln(' dat-infer', '点線: 推測（根拠が弱い）') + '<li title="2 段目では同じ節の他の要件は表示しません。四角: 要件／角丸: 文書・画面・API・テスト・証跡">四角＝要件</li></ul>';
  }
  function nodeDetail(m, h, id, esc) {
    var n = m.byId[id]; if (!n) return '';
    var rel = h.edges.map(function (i) { return m.edges[i]; }).filter(function (e) { return e.src === id || e.dst === id; });
    var row = function (l, v) { return '<div class="dax-props__row"><dt>' + l + '</dt><dd>' + v + '</dd></div>'; };
    var items = rel.map(function (e) {
      var o = m.byId[e.src === id ? e.dst : e.src] || {};
      return '<li>' + esc(KIND_LABEL[e.kind] || e.kind) + ' → ' + esc(TYPE_LABEL[o.type] || o.type || '') + '「' + esc(o.label || o.id || '') + '」<br><span class="dax-meta">出所: ' + esc(provName(e.provenance))
        + ' ・ 根拠: ' + esc(e.basis || '記録なし') + ' ・ 関連度: ' + esc(level(e.confidence)) + '</span></li>';
    }).join('');
    return '<section class="dax-sec" aria-live="polite"><div class="dax-sec__head"><h3 class="dax-sec__title">' + esc(n.label || n.id) + '</h3></div><dl class="dax-props dax-props--one">'
      + row('種類', esc(TYPE_LABEL[n.type] || n.type)) + row('ID', esc(n.id)) + (n.document_id ? row('文書', esc(n.document_id)) : '') + '</dl>'
      + (items ? '<ul class="dat-rel">' + items + '</ul>' : '<p class="dax-meta">この範囲ではつながりが見つかりません（無いと証明したものではありません）。</p>') + '</section>';
  }
  function tableHtml(m, h, center, esc) {
    var es = h.edges.map(function (i) { return m.edges[i]; });
    if (!es.length) return '<p class="dax-meta">この要件のつながりは見つかりません。欠陥とは限りません。</p>';
    var stOf = function (e) { return e.provenance === 'INFERRED' || e.provenance === 'DERIVED' ? '要確認' : '確認済み'; };
    var cnt = {}; es.forEach(function (e) { cnt[e.provenance] = (cnt[e.provenance] || 0) + 1; });
    var major = Object.keys(cnt).sort(function (a, b) { return cnt[b] - cnt[a]; })[0];
    var anyEx = es.some(function (e) { return e.provenance !== major || stOf(e) !== '確認済み'; });
    var rows = es.map(function (e) {
      var a = m.byId[e.src] || {}, b = m.byId[e.dst] || {};
      var tgt = function (n, id) { return n.type === 'Requirement' ? '<button type="button" class="dax-link" data-trq="' + esc(n.id) + '">' + esc(reqId(n)) + '</button>' : esc(TYPE_LABEL[n.type] || '') + '「' + esc(n.label || id) + '」'; };
      var badge = (e.provenance !== major ? '<span class="dat-ex">' + esc(provName(e.provenance)) + '</span>' : '') + (stOf(e) !== '確認済み' ? '<span class="dat-ex">要確認</span>' : '');
      return '<tr><td>' + tgt(a, e.src) + ' → ' + tgt(b, e.dst) + '<div class="dat-sub">' + esc(KIND_LABEL[e.kind] || e.kind) + '</div></td>' + (anyEx ? '<td title="確からしさ ' + esc(level(e.confidence)) + '">' + (badge || '—') + '</td>' : '') + '</tr>';
    }).join('');
    return '<div class="dax-table-wrap"><table class="dax-table dat-table"><thead><tr><th>つながり</th>' + (anyEx ? '<th>状態</th>' : '') + '</tr></thead><tbody>' + rows + '</tbody></table></div>'
      + '<p class="dat-note">' + (anyEx ? '状態は例外だけを表示しています。' : '全 ' + es.length + ' 件') + '出所は「' + esc(provName(major)) + '」' + (anyEx ? 'が既定です。' : '・確認済みです。') + '</p>';
  }
  function segc(name, opts, cur, label) {
    return '<div class="dax-segc" role="tablist" aria-label="' + label + '">' + opts.map(function (o) {
      var sel = String(cur) === String(o[0]);
      return '<button type="button" role="tab" class="dax-segc__opt" aria-selected="' + sel + '" tabindex="' + (sel ? 0 : -1) + '" data-' + name + '="' + o[0] + '">' + o[1] + '</button>';
    }).join('') + '</div>';
  }

  window.DAPanels.trace = {
    label: 'つながり',
    html: function (ctx) {
      var esc = ctx.esc, t = ctx.data && ctx.data.trace;
      if (!t || t.status === 404) return '<section class="dax-state dax-state--empty" role="status"><p class="dax-state__title">まだ分析していません</p><p class="dax-state__body">「解析を開始」を押すと、要件と設計・テストのつながりが表示されます。</p></section>';
      if (!t.ok) return '<section class="dax-state dax-state--error" role="alert"><p class="dax-state__title">つながりを読み込めませんでした（状態 ' + esc(String(t.status)) + '）</p><p class="dax-state__body">「再試行」か、ページの再読み込みをしてください。</p></section>';
      return '<div class="dat-root" data-role="tr"></div>';
    },
    bind: function (root, ctx) {
      var esc = ctx.esc, t = ctx.data && ctx.data.trace, box = root.querySelector('[data-role="tr"]');
      if (!t || !t.ok || !box) return;
      var tip = function (x) { return '<button type="button" class="dax-info" aria-label="' + esc(x) + '" data-tip="' + esc(x) + '">i</button>'; };
      var rq0 = ctx.data && ctx.data.requirements && ctx.data.requirements.body, m = model((t.body && t.body.trace) || {}, rq0 && rq0.requirements), key = ctx.iid || '_';
      var s = ST[key] = ST[key] || { gap: '', q: '', sel: null, hop: 1, view: 'table', focus: null };
      if (s.sel == null || !m.byId[s.sel]) { var first = m.reqs[0]; s.sel = first ? first.n.id : null; s.focus = s.sel; }
      var rqb = ctx.data && ctx.data.requirements && ctx.data.requirements.body; box.innerHTML = covHtml(m, esc, tip, rqb && rqb.requirements ? rqb.requirements.length : null)
        + '<div class="dax-md dat-md"><div class="dax-md__left"><div data-role="gap">' + gapHtml(m, s, tip) + '</div><div class="dat-search"><input type="search" class="dax-search" data-role="q" placeholder="ID・本文で検索" aria-label="要件を検索" value="' + esc(s.q) + '"></div>'
        + '<div class="dax-md__list" role="listbox" aria-label="要件の一覧" data-role="list"></div></div><div class="dax-md__detail" data-role="detail"></div></div>';
      var listEl = box.querySelector('[data-role="list"]'), detEl = box.querySelector('[data-role="detail"]'), gapEl = box.querySelector('[data-role="gap"]');
      function paintList() { listEl.innerHTML = listHtml(m, s, esc); }
      function paintDetail() {
        if (!s.sel || !m.byId[s.sel]) { detEl.innerHTML = '<div class="dax-md__body"><p class="dax-meta">' + GUIDE + '</p></div>'; return; }
        var n = m.byId[s.sel], h = hood(m, s.sel, s.hop), r = m.reqs.filter(function (x) { return x.n.id === s.sel; })[0] || {};
        if (!s.focus || !(s.focus in h.nodes)) s.focus = s.sel;
        var tt = reqTitle(n); detEl.innerHTML = '<div class="dax-md__head"><h2 class="dax-sec__title dat-rh" title="' + esc(reqId(n) + ' ' + tt) + '">' + esc(reqId(n)) + ' ' + esc(tt) + '</h2><div class="dax-md__hmeta">'
          + dots(r, m.execNA) + '</div>' + (r.noDesign ? '<button type="button" class="dax-btn dax-btn--primary dat-hcta" data-tab-go="req">設計を紐付け</button>' : r.noTest ? '<button type="button" class="dax-btn dax-btn--primary dat-hcta" data-tab-go="review" title="生成しただけでは実行済みに数えません">テスト案を生成</button>' : '') + '</div>'
          + '<div class="dax-md__body" data-role="body"></div>';
        var tools = '<div class="dat-tools"><h3 class="dat-tools__h">つながりの明細 ' + h.edges.length + ' 件</h3>' + segc('trview', [['table', '表'], ['graph', 'グラフ']], s.view, '表示の切り替え')
          + '<label class="dat-hop"><input type="checkbox" data-role="hop"' + (s.hop === 2 ? ' checked' : '') + '> 間接も含める</label></div>';
        var bodyEl = detEl.querySelector('[data-role="body"]');
        if (s.view === 'table') { bodyEl.innerHTML = stageTable(m, r, esc) + tools + tableHtml(m, h, s.sel, esc); return; }
        var w = Math.max(300, bodyEl.clientWidth - 56);
        bodyEl.innerHTML = stageTable(m, r, esc) + tools + legendHtml() + '<div class="dat-graph" data-role="graph">' + graphSvg(m, h, s.sel, s.focus, w, esc) + '</div>' + nodeDetail(m, h, s.focus, esc);
      }
      function select(id, refocus) {
        s.sel = id; s.focus = id; paintList(); paintDetail();
        if (refocus) { var b = listEl.querySelector('[data-trq="' + (window.CSS && CSS.escape ? CSS.escape(id) : id) + '"]'); if (b) b.focus(); }
      }
      function refocusAttr(attr, v) { var b = box.querySelector('[' + attr + '="' + v + '"]'); if (b) b.focus(); }
      box.addEventListener('click', function (ev) {
        var el = ev.target.closest ? ev.target : null; if (!el) return;
        var q;
        if ((q = el.closest('[data-trgap]'))) { if (q.disabled) return; s.gap = q.getAttribute('data-trgap'); gapEl.innerHTML = gapHtml(m, s, tip); var f = filtered(m, s); if (f.length && !f.some(function (r) { return r.n.id === s.sel; })) { s.sel = f[0].n.id; s.focus = s.sel; } paintList(); paintDetail(); refocusAttr('data-trgap', s.gap); return; }
        if ((q = el.closest('[data-trq]'))) return select(q.getAttribute('data-trq'), true);
        if ((q = el.closest('[data-trview]'))) { s.view = q.getAttribute('data-trview'); paintDetail(); refocusAttr('data-trview', s.view); return; }
        if ((q = el.closest('[data-trhop]'))) { s.hop = Number(q.getAttribute('data-trhop')); paintDetail(); refocusAttr('data-trhop', s.hop); return; }
        if ((q = el.closest('[data-trn]'))) { s.focus = q.getAttribute('data-trn'); paintDetail(); var g = detEl.querySelector('[data-trn="' + (window.CSS && CSS.escape ? CSS.escape(s.focus) : s.focus) + '"]'); if (g) g.focus(); }
      });
      box.addEventListener('keydown', function (ev) {
        var tg = ev.target;
        if ((ev.key === 'ArrowDown' || ev.key === 'ArrowUp') && tg.matches && tg.matches('[data-trq]')) {
          ev.preventDefault(); ev.stopPropagation();
          var its = [].slice.call(listEl.querySelectorAll('[data-trq]')), j = its.indexOf(tg) + (ev.key === 'ArrowDown' ? 1 : -1);
          if (its[j]) its[j].focus();
          return;
        }
        if ((ev.key === 'Enter' || ev.key === ' ') && tg.matches && tg.matches('[data-trn]')) { ev.preventDefault(); tg.dispatchEvent(new MouseEvent('click', { bubbles: true })); return; }
        if (ev.key === 'Escape' && s.focus !== s.sel) { s.focus = s.sel; paintDetail(); }
      });
      box.addEventListener('change', function (ev) {
        if (ev.target.getAttribute('data-role') === 'hop') { s.hop = ev.target.checked ? 2 : 1; paintDetail(); var hb = detEl.querySelector('[data-role="hop"]'); if (hb) hb.focus(); return; }
        if (ev.target.getAttribute('data-role') !== 'gapsel') return;
        s.gap = ev.target.value || 'any'; gapEl.innerHTML = gapHtml(m, s, tip); var f = filtered(m, s);
        if (f.length && !f.some(function (r) { return r.n.id === s.sel; })) { s.sel = f[0].n.id; s.focus = s.sel; } paintList(); paintDetail();
        var sl = gapEl.querySelector('[data-role="gapsel"]'); if (sl) sl.focus();
      });
      box.addEventListener('input', function (ev) { if (ev.target.getAttribute('data-role') === 'q') { s.q = ev.target.value; paintList(); } });
      paintList(); paintDetail();
    }
  };
})();
