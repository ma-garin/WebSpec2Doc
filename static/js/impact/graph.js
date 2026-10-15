/* System 09 影響度分析 — 関係図（REQ-F-036・DD-008）。外部ライブラリなしで SVG を描く。
   列 0 = 変更箇所、列 1..3 = 段数。点の色 = 優先度、線種 = 根拠（実線つながり／点線意味検索／破線 LLM・語）。 */
(function () {
  'use strict';
  var NS = 'http://www.w3.org/2000/svg';
  var COL_W = 260, ROW_H = 46, PAD_X = 30, PAD_Y = 44, R = 9;
  var COLOR = { 1: '#B42318', 2: '#B54708', 3: '#475467', change: '#C2410C', none: '#98A2B3' };
  var DASH = { link: '', semantic: '2 4', keyword: '8 4', llm: '8 4' };
  var EDGE_LABEL = { link: 'つながり', semantic: '意味検索', keyword: '語の一致', llm: 'LLM 判定' };

  function el(name, attrs, text) {
    var n = document.createElementNS(NS, name);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    if (text !== undefined) n.textContent = text;
    return n;
  }
  function colOf(n) { return n.kind === 'change' ? 0 : Math.max(1, Math.min(3, Number(n.depth) || 1)); }
  function clip(s, n) { s = String(s || ''); return s.length > n ? s.slice(0, n) + '…' : s; }

  function layout(nodes) {
    var cols = [[], [], [], []];
    nodes.forEach(function (n) { cols[colOf(n)].push(n); });
    cols.forEach(function (c) { c.sort(function (a, b) { return (a.priority || 9) - (b.priority || 9) || String(a.code || a.label).localeCompare(String(b.code || b.label)); }); });
    var pos = {};
    cols.forEach(function (c, ci) { c.forEach(function (n, ri) { pos[n.id] = { x: PAD_X + ci * COL_W, y: PAD_Y + ri * ROW_H }; }); });
    var rows = Math.max.apply(null, cols.map(function (c) { return c.length; }).concat([1]));
    return { pos: pos, width: PAD_X * 2 + 3 * COL_W + 200, height: PAD_Y + rows * ROW_H + 10 };
  }

  function legend() {
    var div = document.createElement('div');
    div.className = 'im-legend';
    div.setAttribute('aria-label', '凡例');
    var items = [['change', '変更箇所'], [1, 'P1'], [2, 'P2'], [3, 'P3']].map(function (p) {
      return '<span><i class="im-dot c-' + p[0] + '" aria-hidden="true"></i>' + p[1] + '</span>';
    });
    var lines = ['link', 'semantic', 'llm'].map(function (t) {
      return '<span><svg width="32" height="8" aria-hidden="true"><line x1="0" y1="4" x2="32" y2="4" stroke="#475467" stroke-width="2"' +
        (DASH[t] ? ' stroke-dasharray="' + DASH[t] + '"' : '') + '/></svg>' + (t === 'llm' ? 'LLM 判定・語の一致' : EDGE_LABEL[t]) + '</span>';
    });
    div.innerHTML = items.concat(lines).join('');
    return div;
  }

  function drawEdges(svg, edges, pos) {
    edges.forEach(function (e) {
      var a = pos[e.source || e.from], b = pos[e.target || e.to];
      if (!a || !b) return;
      var t = e.type || e.kind || 'link';
      var mx = (a.x + b.x) / 2;
      var path = el('path', { d: 'M' + a.x + ',' + a.y + ' C' + mx + ',' + a.y + ' ' + mx + ',' + b.y + ' ' + b.x + ',' + b.y,
        fill: 'none', stroke: '#98A2B3', 'stroke-width': '1.6' });
      if (DASH[t]) path.setAttribute('stroke-dasharray', DASH[t]);
      path.appendChild(el('title', {}, EDGE_LABEL[t] || t));
      svg.appendChild(path);
    });
  }

  function drawNode(svg, n, p, onSelect) {
    var g = el('g', { transform: 'translate(' + p.x + ',' + p.y + ')', tabindex: '0', role: 'button', 'class': 'im-gnode' });
    var color = n.kind === 'change' ? COLOR.change : (COLOR[n.priority] || COLOR.none);
    var name = (n.code || n.label || '') + ' ' + clip(n.text, 40);
    g.setAttribute('aria-label', (n.kind === 'change' ? '変更箇所 ' : (n.priority ? 'P' + n.priority + ' ' : '')) + name);
    g.appendChild(n.kind === 'change' ? el('rect', { x: -R, y: -R, width: R * 2, height: R * 2, rx: 3, fill: color })
      : el('circle', { r: R, fill: color }));
    g.appendChild(el('text', { x: R + 6, y: -2, 'font-size': '12', 'font-weight': '600', fill: '#101828' }, clip(n.code || n.label, 22)));
    g.appendChild(el('text', { x: R + 6, y: 13, 'font-size': '11', fill: '#475467' }, clip(n.text, 18)));
    g.appendChild(el('title', {}, name));
    var pick = function () { if (onSelect) onSelect(n); };
    g.addEventListener('click', pick);
    g.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); } });
    svg.appendChild(g);
  }

  function render(container, data, onSelect) {
    var nodes = (data && data.nodes) || [], edges = (data && data.edges) || [];
    container.innerHTML = '';
    if (!nodes.length) {
      var p = document.createElement('p'); p.className = 'bt-hint'; p.textContent = '関係図に出す影響がありません。分析を実行すると表示します。';
      container.appendChild(p); return;
    }
    var L = layout(nodes);
    var svg = el('svg', { width: L.width, height: L.height, viewBox: '0 0 ' + L.width + ' ' + L.height, role: 'group', 'aria-label': '変更箇所から影響項目への波及の関係図' });
    ['変更箇所', '1 段目', '2 段目', '3 段目'].forEach(function (t, i) {
      svg.appendChild(el('text', { x: PAD_X + i * COL_W - R, y: 18, 'font-size': '12', 'font-weight': '700', fill: '#475467' }, t));
    });
    drawEdges(svg, edges, L.pos);
    nodes.forEach(function (n) { if (L.pos[n.id]) drawNode(svg, n, L.pos[n.id], onSelect); });
    var wrap = document.createElement('div'); wrap.className = 'im-graph-scroll'; wrap.appendChild(svg);
    container.appendChild(legend());
    container.appendChild(wrap);
  }

  window.IM = window.IM || {};
  window.IM.graph = { render: render };
})();
