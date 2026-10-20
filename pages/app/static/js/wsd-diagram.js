// 自前の図描画器（外部ライブラリなし）。モデル → SVG 文字列。
//   WsdDiagram.render(model) : model = {kind, direction, nodes, edges, groups}
//     kind      : 'flowchart'（階層レイアウト）| 'sequence'（参加者＋時系列メッセージ）
//     direction : 'TD'（既定）| 'LR'（flowchart のみ）
//     nodes     : [{id, label, shape: box|round|diamond|cyl|para, cls}]  label 内の \n は改行
//     edges     : [{from, to, label, style: solid|dashed|thick}]
//     groups    : [{id, label, members: [nodeId]}]（flowchart のみ）
// Python 版（src/generator/svg_diagram.py）と同じモデル形式。ラベルは必ず HTML エスケープする。
(function (root) {
  'use strict';

  var FONT = "'Hiragino Sans','Noto Sans JP','Yu Gothic',Meiryo,sans-serif";
  var SIZE = 12;
  var LINE_H = 16;
  var MAIN_GAP = 56;
  var CROSS_GAP = 36;
  var MARGIN = 20;
  var seq = 0;

  var STYLE = [
    '.wd-node{fill:#fff;stroke:#475569;stroke-width:1.4}',
    '.wd-text{fill:#0f172a;font-size:' + SIZE + 'px;font-family:' + FONT + '}',
    '.wd-edge{fill:none;stroke:#475569;stroke-width:1.4}',
    '.wd-edge.thick{stroke-width:2.6}',
    '.wd-edge.dashed{stroke-dasharray:6 4}',
    '.wd-label{fill:#334155;font-size:11px;font-family:' + FONT + '}',
    '.wd-label-bg{fill:#fff;opacity:.9}',
    '.wd-group{fill:#f8fafc;stroke:#94a3b8;stroke-dasharray:5 4}',
    '.wd-group-text{fill:#475569;font-size:11px;font-weight:700;font-family:' + FONT + '}',
    '.wd-life{stroke:#94a3b8;stroke-dasharray:4 4}',
    '.wd-node.user{fill:#fef3c7;stroke:#d97706}',
    '.wd-node.fe{fill:#dbeafe;stroke:#2563eb}',
    '.wd-node.api{fill:#dcfce7;stroke:#16a34a}',
    '.wd-node.be{fill:#ede9fe;stroke:#7c3aed}',
    '.wd-node.db{fill:#fee2e2;stroke:#dc2626}',
    '.wd-node.start{fill:#e2e8f0}',
  ].join('');

  function esc(v) {
    return String(v == null ? '' : v)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function textWidth(s) {
    var w = 0;
    for (var i = 0; i < s.length; i++) w += s.charCodeAt(i) > 0x2e7f ? SIZE + 1 : SIZE * 0.6;
    return w;
  }

  function lines(label) {
    var parts = String(label == null ? '' : label).split('\n');
    return parts.length ? parts : [''];
  }

  function r1(n) { return Math.round(n * 10) / 10; }

  function clsOf(cls) {
    return String(cls || '').replace(/[^a-zA-Z0-9_-]/g, '');
  }

  function measure(node) {
    var ls = lines(node.label);
    var tw = 0;
    ls.forEach(function (l) { tw = Math.max(tw, textWidth(l)); });
    var w = Math.max(72, tw + 28);
    var h = Math.max(36, ls.length * LINE_H + 16);
    if (node.shape === 'diamond') { w = w * 1.5; h = h * 1.7; }
    if (node.shape === 'para') w += 24;
    if (node.shape === 'cyl') h += 12;
    return { w: r1(w), h: r1(h), lines: ls };
  }

  function shapeSvg(n) {
    var x = n.x - n.w / 2, y = n.y - n.h / 2, c = 'wd-node ' + clsOf(n.cls);
    var s = n.shape;
    if (s === 'diamond') {
      return '<polygon class="' + c + '" points="' + [n.x, y, x + n.w, n.y, n.x, y + n.h, x, n.y].map(r1).join(' ') + '"/>';
    }
    if (s === 'para') {
      var k = 12;
      return '<polygon class="' + c + '" points="' + [x + k, y, x + n.w, y, x + n.w - k, y + n.h, x, y + n.h].map(r1).join(' ') + '"/>';
    }
    if (s === 'cyl') {
      var e = 7;
      return '<path class="' + c + '" d="M' + r1(x) + ' ' + r1(y + e) + 'a' + r1(n.w / 2) + ' ' + e + ' 0 0 1 ' + r1(n.w) + ' 0v' + r1(n.h - 2 * e) +
        'a' + r1(n.w / 2) + ' ' + e + ' 0 0 1 ' + r1(-n.w) + ' 0z"/>' +
        '<path class="wd-edge" d="M' + r1(x) + ' ' + r1(y + e) + 'a' + r1(n.w / 2) + ' ' + e + ' 0 0 0 ' + r1(n.w) + ' 0"/>';
    }
    var rx = s === 'round' ? n.h / 2 : 6;
    return '<rect class="' + c + '" x="' + r1(x) + '" y="' + r1(y) + '" width="' + r1(n.w) + '" height="' + r1(n.h) + '" rx="' + r1(rx) + '"/>';
  }

  function textSvg(n) {
    var top = n.y - (n.lines.length * LINE_H) / 2 + LINE_H * 0.75;
    return '<text class="wd-text" text-anchor="middle">' + n.lines.map(function (l, i) {
      return '<tspan x="' + r1(n.x) + '" y="' + r1(top + i * LINE_H) + '">' + esc(l) + '</tspan>';
    }).join('') + '</text>';
  }

  // ---- flowchart の階層レイアウト ----
  function layerize(ids, edges) {
    var out = {}, state = {}, back = {};
    ids.forEach(function (id) { out[id] = []; state[id] = 0; });
    edges.forEach(function (e, i) { if (e.from !== e.to) out[e.from].push([e.to, i]); });
    var hasIn = {};
    edges.forEach(function (e) { if (e.from !== e.to) hasIn[e.to] = true; });
    var order = [];
    function visit(start) {
      var stack = [[start, 0]];
      state[start] = 1;
      while (stack.length) {
        var top = stack[stack.length - 1];
        var adj = out[top[0]];
        if (top[1] < adj.length) {
          var pair = adj[top[1]++];
          if (state[pair[0]] === 1) back[pair[1]] = true;
          else if (state[pair[0]] === 0) { state[pair[0]] = 1; stack.push([pair[0], 0]); }
        } else {
          state[top[0]] = 2;
          order.push(top[0]);
          stack.pop();
        }
      }
    }
    ids.filter(function (id) { return !hasIn[id]; }).forEach(function (id) { if (!state[id]) visit(id); });
    ids.forEach(function (id) { if (!state[id]) visit(id); });
    order.reverse();
    var layer = {};
    ids.forEach(function (id) { layer[id] = 0; });
    order.forEach(function (id) {
      out[id].forEach(function (pair) {
        if (!back[pair[1]]) layer[pair[0]] = Math.max(layer[pair[0]], layer[id] + 1);
      });
    });
    return { layer: layer, back: back };
  }

  function orderLayers(ids, edges, layer, back) {
    var count = 0;
    ids.forEach(function (id) { count = Math.max(count, layer[id] + 1); });
    var rows = [];
    for (var i = 0; i < count; i++) rows.push([]);
    ids.forEach(function (id) { rows[layer[id]].push(id); });
    var preds = {}, succs = {};
    ids.forEach(function (id) { preds[id] = []; succs[id] = []; });
    edges.forEach(function (e, i) {
      if (e.from === e.to || back[i]) return;
      succs[e.from].push(e.to);
      preds[e.to].push(e.from);
    });
    function pos() {
      var p = {};
      rows.forEach(function (row) { row.forEach(function (id, k) { p[id] = k; }); });
      return p;
    }
    function sweep(rowIdx, nbr) {
      var p = pos();
      var keyed = rows[rowIdx].map(function (id, k) {
        var ns = nbr[id];
        var bary = ns.length ? ns.reduce(function (s, n) { return s + p[n]; }, 0) / ns.length : k;
        return { id: id, key: bary, k: k };
      });
      keyed.sort(function (a, b) { return a.key - b.key || a.k - b.k; });
      rows[rowIdx] = keyed.map(function (o) { return o.id; });
    }
    for (var pass = 0; pass < 2; pass++) {
      for (var d = 1; d < rows.length; d++) sweep(d, preds);
      for (var u = rows.length - 2; u >= 0; u--) sweep(u, succs);
    }
    return rows;
  }

  function clip(n, dx, dy) {
    var hw = n.w / 2, hh = n.h / 2;
    var ax = Math.abs(dx) / hw, ay = Math.abs(dy) / hh;
    var t = n.shape === 'diamond' ? 1 / ((ax + ay) || 1) : 1 / (Math.max(ax, ay) || 1);
    return { x: n.x + dx * t, y: n.y + dy * t };
  }

  function edgePath(a, b, bend) {
    var dx = b.x - a.x, dy = b.y - a.y;
    var p0 = clip(a, dx, dy), p1 = clip(b, -dx, -dy);
    var len = Math.sqrt(dx * dx + dy * dy) || 1;
    var cx = (p0.x + p1.x) / 2 + (-dy / len) * bend;
    var cy = (p0.y + p1.y) / 2 + (dx / len) * bend;
    return {
      d: 'M' + r1(p0.x) + ' ' + r1(p0.y) + (bend ? 'Q' + r1(cx) + ' ' + r1(cy) + ' ' : 'L') + r1(p1.x) + ' ' + r1(p1.y),
      mx: 0.25 * p0.x + 0.5 * cx + 0.25 * p1.x,
      my: 0.25 * p0.y + 0.5 * cy + 0.25 * p1.y,
    };
  }

  function labelSvg(text, x, y) {
    if (!text) return '';
    var w = textWidth(String(text)) + 8;
    return '<rect class="wd-label-bg" x="' + r1(x - w / 2) + '" y="' + r1(y - 9) + '" width="' + r1(w) + '" height="16" rx="3"/>' +
      '<text class="wd-label" x="' + r1(x) + '" y="' + r1(y + 3) + '" text-anchor="middle">' + esc(text) + '</text>';
  }

  function wrap(body, w, h, markerId, label) {
    return '<svg xmlns="http://www.w3.org/2000/svg" class="wsd-diagram" role="img" aria-label="' + esc(label || '図') + '"' +
      ' viewBox="0 0 ' + r1(w) + ' ' + r1(h) + '" width="' + r1(w) + '" height="' + r1(h) + '" style="max-width:none">' +
      '<style>' + STYLE + '</style>' +
      '<defs><marker id="' + markerId + '" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">' +
      '<path d="M0 0L10 5L0 10z" fill="#475569"/></marker></defs>' + body + '</svg>';
  }

  function placeholder(msg) {
    return wrap('<text class="wd-text" x="' + MARGIN + '" y="34">' + esc(msg) + '</text>', 240, 56, 'wd-m-empty', msg);
  }

  function renderFlow(model) {
    var dir = model.direction === 'LR' ? 'LR' : 'TD';
    var byId = {}, ids = [];
    (model.nodes || []).forEach(function (n) {
      if (!n || n.id == null || byId[n.id]) return;
      var m = measure(n);
      byId[n.id] = { id: n.id, shape: n.shape || 'box', cls: n.cls, w: m.w, h: m.h, lines: m.lines, x: 0, y: 0 };
      ids.push(n.id);
    });
    if (!ids.length) return placeholder('表示する項目がありません');
    var edges = (model.edges || []).filter(function (e) { return e && byId[e.from] && byId[e.to]; });
    var lay = layerize(ids, edges);
    var rows = orderLayers(ids, edges, lay.layer, lay.back);
    var td = dir === 'TD';
    var mainAt = 0, maxCross = 0, extents = [];
    rows.forEach(function (row) {
      var mainSize = 0, crossSize = 0;
      row.forEach(function (id) {
        var n = byId[id];
        mainSize = Math.max(mainSize, td ? n.h : n.w);
        crossSize += (td ? n.w : n.h) + CROSS_GAP;
      });
      crossSize -= CROSS_GAP;
      extents.push({ main: mainAt + mainSize / 2, cross: crossSize });
      mainAt += mainSize + MAIN_GAP;
      maxCross = Math.max(maxCross, crossSize);
    });
    rows.forEach(function (row, ri) {
      var c = (maxCross - extents[ri].cross) / 2;
      row.forEach(function (id) {
        var n = byId[id], size = td ? n.w : n.h;
        var cross = c + size / 2;
        c += size + CROSS_GAP;
        n.x = MARGIN + (td ? cross : extents[ri].main);
        n.y = MARGIN + (td ? extents[ri].main : cross);
      });
    });
    var markerId = 'wd-m-' + (++seq);
    var groupsSvg = '', nodesSvg = '', edgesSvg = '', labelsSvg = '';
    var maxX = 0, maxY = 0;
    ids.forEach(function (id) {
      var n = byId[id];
      maxX = Math.max(maxX, n.x + n.w / 2);
      maxY = Math.max(maxY, n.y + n.h / 2);
      nodesSvg += shapeSvg(n) + textSvg(n);
    });
    (model.groups || []).forEach(function (g) {
      var ms = (g.members || []).filter(function (m) { return byId[m]; }).map(function (m) { return byId[m]; });
      if (!ms.length) return;
      var x0 = Math.min.apply(null, ms.map(function (n) { return n.x - n.w / 2; })) - 14;
      var y0 = Math.min.apply(null, ms.map(function (n) { return n.y - n.h / 2; })) - 26;
      var x1 = Math.max.apply(null, ms.map(function (n) { return n.x + n.w / 2; })) + 14;
      var y1 = Math.max.apply(null, ms.map(function (n) { return n.y + n.h / 2; })) + 14;
      maxX = Math.max(maxX, x1); maxY = Math.max(maxY, y1);
      groupsSvg += '<rect class="wd-group" x="' + r1(x0) + '" y="' + r1(y0) + '" width="' + r1(x1 - x0) + '" height="' + r1(y1 - y0) + '" rx="8"/>' +
        '<text class="wd-group-text" x="' + r1(x0 + 10) + '" y="' + r1(y0 + 15) + '">' + esc(g.label || g.id) + '</text>';
    });
    var pairCount = {}, pairSeen = {};
    edges.forEach(function (e) {
      var k = e.from < e.to ? e.from + '\u0000' + e.to : e.to + '\u0000' + e.from;
      pairCount[k] = (pairCount[k] || 0) + 1;
    });
    edges.forEach(function (e, i) {
      var a = byId[e.from], b = byId[e.to], cls = 'wd-edge ' + (e.style === 'dashed' ? 'dashed' : e.style === 'thick' ? 'thick' : '');
      if (a === b) {
        var lx = a.x + a.w / 2, ly = a.y - a.h / 4;
        edgesSvg += '<path class="' + cls + '" d="M' + r1(lx) + ' ' + r1(ly) + 'c34 -6 34 ' + r1(a.h / 2 + 6) + ' 0 ' + r1(a.h / 2) + '" marker-end="url(#' + markerId + ')"/>';
        labelsSvg += labelSvg(e.label, lx + 40, a.y);
        maxX = Math.max(maxX, lx + 60);
        return;
      }
      var k = e.from < e.to ? e.from + '\u0000' + e.to : e.to + '\u0000' + e.from;
      var idx = pairSeen[k] = (pairSeen[k] || 0) + 1;
      var bend = (idx - 1 - (pairCount[k] - 1) / 2) * 34;
      if (lay.back[i]) bend += 36;
      var p = edgePath(a, b, bend);
      edgesSvg += '<path class="' + cls + '" d="' + p.d + '" marker-end="url(#' + markerId + ')"/>';
      labelsSvg += labelSvg(e.label, p.mx, p.my);
      maxX = Math.max(maxX, p.mx + 40); maxY = Math.max(maxY, p.my + 12);
    });
    return wrap(groupsSvg + edgesSvg + nodesSvg + labelsSvg, maxX + MARGIN, maxY + MARGIN, markerId, '図');
  }

  // ---- シーケンス図 ----
  function renderSequence(model) {
    var parts = [], idx = {};
    (model.nodes || []).forEach(function (n) {
      if (!n || n.id == null || idx[n.id] !== undefined) return;
      var m = measure({ label: n.label, shape: 'box' });
      idx[n.id] = parts.length;
      parts.push({ id: n.id, w: m.w, h: m.h, lines: m.lines, x: 0, y: MARGIN + m.h / 2, shape: 'box', cls: n.cls });
    });
    if (!parts.length) return placeholder('表示する項目がありません');
    var msgs = (model.edges || []).filter(function (e) { return e && idx[e.from] !== undefined && idx[e.to] !== undefined; });
    var headH = 0, x = MARGIN;
    parts.forEach(function (p) { headH = Math.max(headH, p.h); });
    // 隣接参加者の間隔は、その間を渡るメッセージのラベル幅も確保する
    var gap = parts.map(function () { return 36; });
    msgs.forEach(function (m) {
      var a = Math.min(idx[m.from], idx[m.to]), b = Math.max(idx[m.from], idx[m.to]);
      if (a === b) return;
      var need = (textWidth(m.label || '') + 24) / (b - a);
      for (var k = a; k < b; k++) gap[k] = Math.max(gap[k], need);
    });
    parts.forEach(function (p, i) {
      p.x = x + p.w / 2;
      p.y = MARGIN + headH / 2;
      p.h = headH;
      x += p.w + (i < parts.length - 1 ? Math.max(gap[i], 36) : 0);
    });
    // 中心間距離がラベルに足りるよう補正
    for (var i = 1; i < parts.length; i++) {
      var need = parts[i - 1].x + (parts[i - 1].w + parts[i].w) / 2 + 20;
      if (parts[i].x < need) {
        var shift = need - parts[i].x;
        for (var j = i; j < parts.length; j++) parts[j].x += shift;
      }
    }
    var markerId = 'wd-m-' + (++seq);
    var top = MARGIN + headH;
    var bottom = top + 40 + msgs.length * 44;
    var body = '', heads = '', labels = '';
    parts.forEach(function (p) {
      body += '<line class="wd-life" x1="' + r1(p.x) + '" y1="' + r1(top) + '" x2="' + r1(p.x) + '" y2="' + r1(bottom) + '"/>';
      heads += shapeSvg(p) + textSvg(p);
    });
    msgs.forEach(function (m, i) {
      var y = top + 40 + i * 44;
      var a = parts[idx[m.from]], b = parts[idx[m.to]];
      var cls = 'wd-edge ' + (m.style === 'dashed' ? 'dashed' : m.style === 'thick' ? 'thick' : '');
      if (a === b) {
        body += '<path class="' + cls + '" d="M' + r1(a.x) + ' ' + r1(y - 8) + 'h28v16h-28" marker-end="url(#' + markerId + ')"/>';
        labels += labelSvg(m.label, a.x + 28 + textWidth(m.label || '') / 2 + 8, y);
        return;
      }
      body += '<path class="' + cls + '" d="M' + r1(a.x) + ' ' + r1(y) + 'L' + r1(b.x) + ' ' + r1(y) + '" marker-end="url(#' + markerId + ')"/>';
      labels += labelSvg(m.label, (a.x + b.x) / 2, y - 10);
    });
    var last = parts[parts.length - 1];
    var width = last.x + last.w / 2 + MARGIN;
    msgs.forEach(function (m) {
      if (idx[m.from] === idx[m.to]) width = Math.max(width, parts[idx[m.from]].x + 40 + textWidth(m.label || '') + MARGIN);
    });
    return wrap(body + heads + labels, width, bottom + MARGIN, markerId, 'シーケンス図');
  }

  function render(model) {
    if (!model || typeof model !== 'object') return placeholder('表示する項目がありません');
    return model.kind === 'sequence' ? renderSequence(model) : renderFlow(model);
  }

  var api = { render: render, escape: esc };
  root.WsdDiagram = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
