/* Document Assurance: Trace グラフパネル。外部ライブラリなし・自前 SVG のみ。 */
(function () {
  'use strict';
  window.DAPanels = window.DAPanels || {};

  var STAGES = [
    ['requirement', '要件'],
    ['design', '設計（画面・API への言及）'],
    ['test_designed', 'テスト設計済み（テスト案あり）'],
    ['execution', 'テスト実行済み'],
    ['passed', 'テスト合格'],
    ['verified', '検証済み']
  ];
  var PROVS = ['EXPLICIT', 'OBSERVED', 'DERIVED', 'INFERRED'];
  var PROV_LABEL = { EXPLICIT: '明示', OBSERVED: '観測', DERIVED: '導出', INFERRED: '推測' };
  var TYPE_LABEL = { Requirement: '要件', BusinessRule: '業務ルール', Document: '文書', Section: '節', Screen: '画面', API: 'API', Test: 'テスト', Evidence: '証跡' };
  var COLS = ['Document', 'Section', 'Requirement', 'Screen', 'API', 'Test', 'Evidence'];
  var KIND_LABEL = {
    requirement_without_design: '設計への言及が見つからない要件',
    requirement_without_test: 'テストが見つからない要件',
    api_without_requirement: '要件が見つからない API',
    test_without_requirement: '要件が見つからないテスト'
  };
  var W = 1000, ROW = 34, PAD = 30;

  function colOf(t) { return t === 'BusinessRule' ? 'Requirement' : t; }
  function short(s) { s = String(s == null ? '' : s); return s.length > 14 ? s.slice(0, 14) + '…' : s; }
  function level(c) {
    var n = Number(c);
    if (!isFinite(n)) return '関連度: 不明';
    return n >= 0.75 ? '関連度: 高' : n >= 0.5 ? '関連度: 中' : '関連度: 低';
  }

  function shapePath(type, x, y) {
    var w = 120, h = 24;
    if (type === 'Requirement' || type === 'BusinessRule') return '<rect x="' + (x - w / 2) + '" y="' + (y - h / 2) + '" width="' + w + '" height="' + h + '"/>';
    if (type === 'Screen') return '<polygon points="' + x + ',' + (y - 15) + ' ' + (x + 62) + ',' + y + ' ' + x + ',' + (y + 15) + ' ' + (x - 62) + ',' + y + '"/>';
    if (type === 'API') return '<polygon points="' + (x - 48) + ',' + (y - 13) + ' ' + (x + 48) + ',' + (y - 13) + ' ' + (x + 62) + ',' + y + ' ' + (x + 48) + ',' + (y + 13) + ' ' + (x - 48) + ',' + (y + 13) + ' ' + (x - 62) + ',' + y + '"/>';
    if (type === 'Test') return '<ellipse cx="' + x + '" cy="' + y + '" rx="60" ry="13"/>';
    return '<rect x="' + (x - w / 2) + '" y="' + (y - h / 2) + '" width="' + w + '" height="' + h + '" rx="10"/>';
  }

  function layout(nodes) {
    var cols = {}, pos = {}, i, n, c;
    for (i = 0; i < nodes.length; i++) {
      n = nodes[i]; c = colOf(n.type);
      if (COLS.indexOf(c) < 0) c = 'Evidence';
      (cols[c] = cols[c] || []).push(i);
    }
    var used = COLS.filter(function (k) { return cols[k]; });
    var step = W / (used.length || 1), maxRows = 1;
    used.forEach(function (k, ci) {
      cols[k].forEach(function (idx, ri) { pos[idx] = { x: step * ci + step / 2, y: PAD + ri * ROW }; });
      maxRows = Math.max(maxRows, cols[k].length);
    });
    return { pos: pos, height: PAD * 2 + maxRows * ROW };
  }

  function neighbors(edges, id, depth) {
    var seen = {}, frontier = [id], d;
    seen[id] = true;
    for (d = 0; d < depth; d++) {
      var next = [];
      edges.forEach(function (e) {
        if (seen[e.src] && !seen[e.dst] && frontier.indexOf(e.src) >= 0) { seen[e.dst] = true; next.push(e.dst); }
        if (seen[e.dst] && !seen[e.src] && frontier.indexOf(e.dst) >= 0) { seen[e.src] = true; next.push(e.src); }
      });
      frontier = next;
    }
    return seen;
  }

  function coverageHtml(cov, esc) {
    var rows = STAGES.map(function (s) {
      var m = cov[s[0]], body;
      if (m == null || m.ratio == null && cov.status && cov.status[s[0]] === 'NOT_EVALUATED') {
        body = '<span class="dat-na">評価していません</span>';
      } else if (m.ratio == null) {
        body = '<span class="dat-na">対象 0 件</span>';
      } else {
        var pct = Math.round(m.ratio * 100);
        body = '<span class="dat-cov-v"><span class="dat-bar" aria-hidden="true"><i style="width:' + pct + '%"></i></span><span>' +
          esc(String(m.count)) + ' / ' + esc(String(m.total)) + '（' + esc(String(pct)) + '%）</span></span>';
      }
      return '<div class="dat-cov-row"><span class="dat-cov-name">' + esc(s[1]) + '</span>' + body + '</div>';
    }).join('');
    return '<section class="dat-sec" aria-label="カバレッジ"><h3>カバレッジ（段ごとに別々に評価）</h3>' + rows +
      '<p class="dat-note">' + esc(cov.note || 'テスト案があることは実行済みを意味しません。') + '</p></section>';
  }

  function orphansHtml(orphans, nodes, esc) {
    var byId = {};
    nodes.forEach(function (n) { byId[n.id] = n; });
    var items = (orphans || []).map(function (o) {
      var n = byId[o.node_id] || {};
      return '<li><b>' + esc(KIND_LABEL[o.kind] || o.kind || '') + '</b> ' + esc(n.label || o.node_id) +
        '<br><span class="dat-sub">' + esc(o.reason || '') + '</span></li>';
    }).join('');
    return '<section class="dat-sec" aria-label="孤立候補"><h3>孤立候補（' + esc(String((orphans || []).length)) + ' 件）</h3>' +
      '<p class="dat-note">欠陥とは限りません。候補です。リンクが見つからなかっただけで、無いと証明したものではありません。</p>' +
      (items ? '<ul class="dat-orph">' + items + '</ul>' : '<p class="dat-na">候補はありません</p>') + '</section>';
  }

  window.DAPanels.trace = {
    label: 'つながり',
    html: function (ctx) {
      var esc = ctx.esc, t = ctx.data && ctx.data.trace;
      if (!t || t.status === 404) {
        return '<div class="dat-root"><p class="dat-na">まだ分析していません。「分析を実行」を押すと、要件と設計・テストのつながりが表示されます。</p></div>';
      }
      if (!t.ok) {
        return '<div class="dat-root"><p class="dat-err" role="alert">つながりを読み込めませんでした（状態 ' + esc(String(t.status)) + '）。「もう一度読み込む」か、ページの再読み込みをしてください。</p></div>';
      }
      var tr = (t.body && t.body.trace) || {}, g = tr.graph || { nodes: [], edges: [], orphans: [] };
      var checks = PROVS.map(function (p) {
        return '<label class="dat-chk"><input type="checkbox" data-prov="' + esc(p) + '" checked> ' + esc(PROV_LABEL[p]) + '</label>';
      }).join('');
      var legend = '<ul class="dat-legend" aria-label="凡例">' +
        '<li><svg width="22" height="14" aria-hidden="true"><rect x="2" y="2" width="18" height="10" class="dat-shape"/></svg>要件・業務ルール（四角）</li>' +
        '<li><svg width="22" height="14" aria-hidden="true"><rect x="2" y="2" width="18" height="10" rx="5" class="dat-shape"/></svg>文書・節（角丸）</li>' +
        '<li><svg width="22" height="14" aria-hidden="true"><polygon points="11,0 21,7 11,14 1,7" class="dat-shape"/></svg>画面（ひし形）</li>' +
        '<li><svg width="22" height="14" aria-hidden="true"><polygon points="5,1 17,1 21,7 17,13 5,13 1,7" class="dat-shape"/></svg>API（六角形）</li>' +
        '<li><svg width="22" height="14" aria-hidden="true"><ellipse cx="11" cy="7" rx="9" ry="6" class="dat-shape"/></svg>テスト（丸）</li>' +
        '<li><svg width="30" height="8" aria-hidden="true"><line x1="0" y1="4" x2="30" y2="4" class="dat-edge"/></svg>実線: 明示・観測・導出</li>' +
        '<li><svg width="30" height="8" aria-hidden="true"><line x1="0" y1="4" x2="30" y2="4" class="dat-edge dat-infer"/></svg>点線: 推測（根拠が弱い）</li></ul>';
      return '<div class="dat-root">' + coverageHtml(tr.coverage || {}, esc) +
        '<section class="dat-sec" aria-label="Trace グラフ"><h3>つながりの図（要件中心）</h3>' +
        '<div class="dat-filter" role="group" aria-label="出所フィルタ">' + checks + '</div>' + legend +
        '<div class="dat-main"><div class="dat-graph" data-role="graph"></div>' +
        '<aside class="dat-detail" data-role="detail" aria-live="polite"><p class="dat-na">図の要素を選ぶと、つながる要素と詳細を表示します。Esc で選択を解除します。</p></aside></div></section>' +
        orphansHtml(g.orphans, g.nodes || [], esc) + '</div>';
    },
    bind: function (root, ctx) {
      var esc = ctx.esc, t = ctx.data && ctx.data.trace;
      if (!t || !t.ok) return;
      var g = (t.body && t.body.trace && t.body.trace.graph) || { nodes: [], edges: [] };
      var nodes = g.nodes || [], edges = g.edges || [];
      var graphEl = root.querySelector('[data-role="graph"]'), detail = root.querySelector('[data-role="detail"]');
      if (!graphEl || !detail) return;
      var idx = {}, selected = null, lay = layout(nodes);
      nodes.forEach(function (n, i) { idx[n.id] = i; });

      function active() {
        var on = {};
        [].forEach.call(root.querySelectorAll('input[data-prov]'), function (c) { if (c.checked) on[c.getAttribute('data-prov')] = true; });
        return edges.filter(function (e) { return on[e.provenance]; });
      }

      function showDetail(vis) {
        if (selected == null) {
          detail.innerHTML = '<p class="dat-na">図の要素を選ぶと、つながる要素と詳細を表示します。Esc で選択を解除します。</p>';
          return;
        }
        var n = nodes[selected], rel = vis.filter(function (e) { return e.src === n.id || e.dst === n.id; });
        var items = rel.map(function (e) {
          var other = nodes[idx[e.src === n.id ? e.dst : e.src]] || {};
          return '<li>' + esc(PROV_LABEL[e.provenance] || e.provenance) + '（' + esc(e.provenance) + '）・' + esc(e.kind) +
            ' → ' + esc(other.label || '') + '<br><span class="dat-sub">' + esc(level(e.confidence)) +
            '（confidence ' + esc(String(e.confidence)) + '）／根拠: ' + esc(e.basis || '') + '</span></li>';
        }).join('');
        detail.innerHTML = '<h4>' + esc(n.label || n.id) + '</h4><p class="dat-sub">' + esc(TYPE_LABEL[n.type] || n.type) +
          ' ／ ' + esc(n.id) + (n.document_id ? ' ／ 文書: ' + esc(n.document_id) : '') + '</p>' +
          (items ? '<ul class="dat-rel">' + items + '</ul>' : '<p class="dat-na">この出所の条件では関係が見つかりません。</p>');
      }

      function draw() {
        var vis = active(), near = selected == null ? null : neighbors(vis, nodes[selected].id, 2);
        var h = Math.max(lay.height, 120), out = '<svg class="dat-svg" viewBox="0 0 ' + W + ' ' + h +
          '" preserveAspectRatio="xMidYMin meet" role="group" aria-label="Trace グラフ">';
        vis.forEach(function (e) {
          var a = lay.pos[idx[e.src]], b = lay.pos[idx[e.dst]];
          if (!a || !b) return;
          var dim = near && !(near[e.src] && near[e.dst]);
          out += '<line x1="' + a.x + '" y1="' + a.y + '" x2="' + b.x + '" y2="' + b.y + '" class="dat-edge' +
            (e.provenance === 'INFERRED' ? ' dat-infer' : '') + (dim ? ' dat-dim' : '') + '"/>';
        });
        nodes.forEach(function (n, i) {
          var p = lay.pos[i], dim = near && !near[n.id], sel = i === selected;
          var full = (n.label || n.id) + '（' + (TYPE_LABEL[n.type] || n.type) + '）';
          out += '<g class="dat-node' + (dim ? ' dat-dim' : '') + (sel ? ' dat-sel' : '') + '" tabindex="0" role="button" data-i="' + i +
            '" aria-pressed="' + (sel ? 'true' : 'false') + '" aria-label="' + esc(full) + '"><title>' + esc(full) + '</title>' +
            '<g class="dat-shape">' + shapePath(n.type, p.x, p.y) + '</g><text x="' + p.x + '" y="' + (p.y + 4) +
            '" text-anchor="middle">' + esc(short(n.label || n.id)) + '</text></g>';
        });
        graphEl.innerHTML = out + '</svg>';
        showDetail(vis);
      }

      function pick(el) {
        var g2 = el && el.closest ? el.closest('[data-i]') : null;
        if (!g2) return;
        var i = Number(g2.getAttribute('data-i'));
        selected = selected === i ? null : i;
        draw();
        var again = graphEl.querySelector('[data-i="' + i + '"]');
        if (again) again.focus();
      }

      graphEl.addEventListener('click', function (ev) { pick(ev.target); });
      graphEl.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); pick(ev.target); }
      });
      root.addEventListener('keydown', function (ev) {
        if (ev.key === 'Escape' && selected != null) { selected = null; draw(); }
      });
      [].forEach.call(root.querySelectorAll('input[data-prov]'), function (c) { c.addEventListener('change', draw); });
      draw();
    }
  };
})();
