// ---- 画面遷移図（vis.js ネットワーク）----
function _commonNavTargets(screens) {
  const n = screens.length;
  const count = {};
  screens.forEach(sc => {
    (sc.transitions && sc.transitions.to || []).forEach(to => { count[to] = (count[to] || 0) + 1; });
  });
  const threshold = Math.max(2, Math.floor(n * 0.5));
  return new Set(Object.entries(count).filter(([, c]) => c >= threshold).map(([k]) => k));
}

function _loadVisNetwork(cb) {
  if (window.vis) { cb(); return; }
  const css = document.createElement('link');
  css.rel = 'stylesheet';
  css.href = 'https://unpkg.com/vis-network@9/dist/dist/vis-network.min.css';
  document.head.appendChild(css);
  const s = document.createElement('script');
  s.src = 'https://unpkg.com/vis-network@9/dist/vis-network.min.js';
  s.onload = cb;
  document.head.appendChild(s);
}

function _shortVisLabel(sc) {
  return (sc.title || sc.page_id).replace(/\s*[|｜]\s*.*/g, '').replace(/['"]/g, '').slice(0, 24) || sc.page_id;
}

function renderTransition() {
  const screens = reportJson && reportJson.screens || [];
  if (!screens.length) {
    resultHero.innerHTML = '<div class="hero-msg">遷移データがありません。クロールを実行してください。</div>';
    return;
  }

  resultHero.innerHTML =
    '<div style="display:flex;flex-direction:column;height:100%;min-height:0">' +
    '<div id="vis-toolbar" style="padding:8px 12px;font-size:12px;color:var(--text-muted);border-bottom:1px solid var(--border);display:flex;gap:16px;align-items:center;flex-shrink:0;flex-wrap:wrap">' +
    '<span>※ 共通ナビゲーション（全ページの50%以上）は除外</span>' +
    '<span>📋 フォームあり画面</span>' +
    '<span>- - → フォーム送信</span>' +
    '<span style="color:var(--text-subtle)">ノードをクリック → 画面別仕様を表示</span>' +
    '</div>' +
    '<div id="vis-network-container" style="flex:1;min-height:0"></div>' +
    '</div>';

  _loadVisNetwork(() => {
    const container = document.getElementById('vis-network-container');
    if (!container) return;

    const common = _commonNavTargets(screens);
    const urlToId = {};
    const knownIds = new Set();
    screens.forEach(sc => {
      urlToId[sc.url] = sc.page_id;
      knownIds.add(sc.page_id);
    });

    const nodes = screens.map(sc => {
      const hasForm = (sc.forms || []).some(f => f.fields && f.fields.length);
      return {
        id: sc.page_id,
        label: `${sc.page_id}\n${_shortVisLabel(sc)}`,
        shape: 'box',
        font: { size: 12 },
        color: hasForm
          ? { background: '#DBEAFE', border: '#3B82F6' }
          : { background: '#F3F4F6', border: '#9CA3AF' },
      };
    });

    const edges = [];
    const edgeKeys = new Set();
    const addEdge = edge => {
      const key = `${edge.from}:${edge.to}:${edge.label || 'link'}`;
      if (!edgeKeys.has(key)) {
        edgeKeys.add(key);
        edges.push(edge);
      }
    };

    screens.forEach(sc => {
      (sc.transitions && sc.transitions.to || []).forEach(to => {
        if (common.has(to) || !knownIds.has(to)) return;
        addEdge({ from: sc.page_id, to, color: '#94A3B8' });
      });
      (sc.forms || []).forEach(f => {
        const toId = f.action ? urlToId[f.action] : null;
        if (!toId || toId === sc.page_id || common.has(toId) || !knownIds.has(toId)) return;
        addEdge({ from: sc.page_id, to: toId, label: 'フォーム送信', dashes: true, color: '#F59E0B' });
      });
    });

    const data = {
      nodes: new vis.DataSet(nodes),
      edges: new vis.DataSet(edges),
    };
    const options = {
      physics: {
        enabled: true,
        hierarchicalRepulsion: { nodeDistance: 160 },
        solver: 'hierarchicalRepulsion'
      },
      layout: {
        hierarchical: {
          enabled: true,
          direction: 'LR',
          sortMethod: 'directed',
          levelSeparation: 200,
          nodeSpacing: 120,
        }
      },
      interaction: {
        zoomView: true,
        dragView: true,
        hover: true,
      },
      edges: {
        arrows: { to: { enabled: true, scaleFactor: 0.8 } },
        smooth: { type: 'cubicBezier', forceDirection: 'horizontal' }
      }
    };

    const network = new vis.Network(container, data, options);
    network.on('click', (params) => {
      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0];
        selectResultTab('report');
        setTimeout(() => {
          const item = document.querySelector(`.rpt-list-item[data-id="${nodeId}"], .rpt-list-item[data-pid="${nodeId}"]`);
          if (item) item.click();
        }, 100);
      }
    });
  });
}

// ---- 画面遷移表（ISTQB 状態遷移テスト標準フォーマット）----
function renderTransitionTable() {
  if (!reportJson || !(reportJson.screens || []).length) {
    resultHero.innerHTML = '<div class="hero-msg">遷移データがありません。</div>';
    return;
  }
  const screens = reportJson.screens;
  const common = _commonNavTargets(screens);
  const idToTitle = {};
  screens.forEach(sc => { idToTitle[sc.page_id] = sc.title || sc.page_id; });

  const urlToId = {};
  screens.forEach(s => { urlToId[s.url] = s.page_id; });
  const idToUrl = {};
  screens.forEach(s => { idToUrl[s.page_id] = s.url; });

  const rows = [];
  screens.forEach(sc => {
    (sc.transitions && sc.transitions.to || []).forEach(to => {
      if (common.has(to)) return;
      const destUrl = idToUrl[to] || '';
      let linkPath = destUrl;
      try { linkPath = new URL(destUrl).pathname; } catch (e) {}
      rows.push({ fromId: sc.page_id, fromTitle: sc.title || sc.page_id, event: 'リンク', eventDetail: linkPath, toId: to, toTitle: idToTitle[to] || to, action: destUrl });
    });
    (sc.forms || []).forEach(f => {
      if (!f.action) return;
      const toId = urlToId[f.action] || f.action;
      const toTitle = idToTitle[toId] || '（未取得）';
      rows.push({ fromId: sc.page_id, fromTitle: sc.title || sc.page_id, event: 'フォーム送信', eventDetail: `${(f.method || 'GET').toUpperCase()}`, toId, toTitle, action: f.action });
    });
  });

  if (!rows.length) { resultHero.innerHTML = '<div class="hero-msg">遷移情報がありません（共通ナビのみ検出）。</div>'; return; }

  const tableRows = rows.map(r =>
    `<tr>
      <td class="c-screen">${escHtml(r.fromId)}</td>
      <td>${escHtml(r.fromTitle)}</td>
      <td>
        <span class="cond-pill ${r.event === 'フォーム送信' ? 'cc-format trans-event-form' : 'cc-other trans-event-link'}">${escHtml(r.event)}</span>
        <span class="trans-link-detail">${escHtml(r.eventDetail)}</span>
      </td>
      <td class="c-screen">${escHtml(r.toId)}</td>
      <td>${escHtml(r.toTitle)}</td>
      <td style="font-size:11px;font-family:monospace;color:var(--text-muted);word-break:break-all">${escHtml(r.action)}</td>
    </tr>`
  ).join('');

  resultHero.innerHTML =
    '<div class="hero-pad">' +
    '<div class="hero-section-title">画面遷移表 — ISTQB 状態遷移テスト</div>' +
    `<p style="color:var(--text-muted);font-size:12px;margin:0 0 12px">${rows.length}件の遷移。共通ナビ（${Math.floor(screens.length * 0.5)}件以上から発生）は除外しています。</p>` +
    '<div style="overflow-x:auto">' +
    '<table class="trans-table">' +
    '<thead><tr><th>現在の画面</th><th>タイトル</th><th>イベント</th><th>遷移先</th><th>遷移先タイトル</th><th>アクション</th></tr></thead>' +
    `<tbody>${tableRows}</tbody>` +
    '</table></div></div>';
}
