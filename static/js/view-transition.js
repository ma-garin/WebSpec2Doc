// ---- 画面遷移図（UML 3タブ + テスト観点マップ）----
function _commonNavTargets(screens) {
  const n = screens.length;
  const count = {};
  screens.forEach(sc => {
    (sc.transitions && sc.transitions.to || []).forEach(to => { count[to] = (count[to] || 0) + 1; });
  });
  const threshold = Math.max(2, Math.floor(n * 0.5));
  return new Set(Object.entries(count).filter(([, c]) => c >= threshold).map(([k]) => k));
}

function _shortVisLabel(sc) {
  return (sc.title || sc.page_id).replace(/\s*[|｜]\s*.*/g, '').replace(/['"]/g, '').slice(0, 24) || sc.page_id;
}

function _loadMermaid(cb) {
  if (window.mermaid) {
    cb();
    return;
  }
  const existing = document.querySelector('script[data-lib="mermaid"]');
  if (existing) {
    existing.addEventListener('load', cb, { once: true });
    return;
  }
  const s = document.createElement('script');
  s.src = 'https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js';
  s.dataset.lib = 'mermaid';
  s.onload = cb;
  s.onerror = () => {
    const target = document.getElementById('uml-render-target');
    if (target) target.innerHTML = '<div class="hero-msg">Mermaidを読み込めませんでした。ネットワーク接続を確認してください。</div>';
  };
  document.head.appendChild(s);
}

function _umlAlias(value) {
  return `N${String(value || '').replace(/[^a-zA-Z0-9_]/g, '_')}`;
}

function _mermaidText(value) {
  return String(value || '').replace(/[<>{}"'`]/g, '').replace(/\s+/g, ' ').trim();
}

function _transitionRows(screens) {
  const common = _commonNavTargets(screens);
  const idToScreen = {};
  const urlToId = {};
  screens.forEach(sc => {
    idToScreen[sc.page_id] = sc;
    urlToId[sc.url] = sc.page_id;
  });

  const rows = [];
  const keys = new Set();
  const addRow = row => {
    if (!row.fromId || !row.toId || row.fromId === row.toId) return;
    if (!idToScreen[row.fromId] || !idToScreen[row.toId] || common.has(row.toId)) return;
    const key = `${row.fromId}:${row.toId}:${row.event}:${row.eventDetail}`;
    if (keys.has(key)) return;
    keys.add(key);
    rows.push({
      no: `T${String(rows.length + 1).padStart(2, '0')}`,
      fromId: row.fromId,
      fromTitle: idToScreen[row.fromId].title || row.fromId,
      event: row.event,
      eventDetail: row.eventDetail || '',
      toId: row.toId,
      toTitle: idToScreen[row.toId].title || row.toId,
      action: row.action || '',
      viewpoint: row.event === 'フォーム送信' ? '入力後に期待画面へ到達する' : 'リンク操作で期待画面へ到達する',
    });
  };

  screens.forEach(sc => {
    (sc.transitions && sc.transitions.to || []).forEach(to => {
      addRow({ fromId: sc.page_id, event: 'リンク', eventDetail: 'リンククリック', toId: to, action: '' });
    });
    (sc.forms || []).forEach(f => {
      const toId = f.action ? urlToId[f.action] : '';
      addRow({
        fromId: sc.page_id,
        event: 'フォーム送信',
        eventDetail: `${(f.method || 'GET').toUpperCase()} submit`,
        toId,
        action: f.action || '',
      });
    });
  });
  return rows;
}

function renderTransition() {
  const screens = reportJson && reportJson.screens || [];
  if (!screens.length) {
    resultHero.innerHTML = '<div class="hero-msg">遷移データがありません。クロールを実行してください。</div>';
    return;
  }

  resultHero.innerHTML =
    '<div class="uml-view">' +
    '<div class="uml-subtabs" id="uml-subtabs">' +
    '<button class="uml-subtab is-active" data-uml="sequence">シーケンス図<span>操作順</span></button>' +
    '<button class="uml-subtab" data-uml="communication">コミュニケーション図<span>全体関係</span></button>' +
    '<button class="uml-subtab" data-uml="activity">アクティビティ図<span>テスト手順</span></button>' +
    '<button class="uml-subtab" data-uml="viewpoints">テスト観点マップ<span>設計観点</span></button>' +
    '</div>' +
    '<div id="uml-diagram-area" class="uml-diagram-area"></div>' +
    '</div>';

  document.querySelectorAll('.uml-subtab').forEach(t => {
    t.addEventListener('click', () => {
      document.querySelectorAll('.uml-subtab').forEach(x => x.classList.toggle('is-active', x === t));
      _showUmlPanel(t.dataset.uml, screens);
    });
  });

  _showUmlPanel('sequence', screens);
}

function _showUmlPanel(type, screens) {
  const area = document.getElementById('uml-diagram-area');
  if (!area) return;
  const rows = _transitionRows(screens);
  if (type === 'viewpoints') {
    _showViewpointMap(area, rows);
    return;
  }
  const meta = _umlMeta(type);
  area.innerHTML =
    '<div class="uml-panel-head">' +
    `<div><strong>${escHtml(meta.title)}</strong><span>${escHtml(meta.desc)}</span></div>` +
    `<p>${rows.length}件の遷移。共通ナビゲーション（全ページの50%以上から発生する遷移）は除外しています。</p>` +
    '</div>' +
    '<div class="uml-layout">' +
    '<div class="uml-canvas" id="uml-render-target"><div class="hero-msg">図を描画しています…</div></div>' +
    `<div class="uml-table-wrap">${_umlTable(type, rows)}</div>` +
    '</div>';
  _loadMermaid(() => _renderUmlDiagram(type, screens, rows));
}

function _umlMeta(type) {
  if (type === 'communication') {
    return { title: 'コミュニケーション図', desc: '画面間の関係をエッジ番号で俯瞰します。' };
  }
  if (type === 'activity') {
    return { title: 'アクティビティ図', desc: 'QAテスト手順として操作と期待結果を追います。' };
  }
  return { title: 'シーケンス図', desc: '代表的な遷移を時系列で確認します。' };
}

function _showViewpointMap(area, rows) {
  const groups = _viewpointGroups(rows);
  const totalChecks = groups.reduce((sum, g) => sum + g.rows.length, 0);
  area.innerHTML =
    '<div class="uml-panel-head">' +
    '<div><strong>テスト観点マップ</strong><span>遷移をQA観点へ分類し、テスト設計の入口にします。</span></div>' +
    `<p>${rows.length}件の遷移から${totalChecks}件の観点候補を抽出しています。</p>` +
    '</div>' +
    '<div class="viewpoint-map">' +
    `<div class="viewpoint-summary">${groups.map(_viewpointCard).join('')}</div>` +
    `<div class="viewpoint-table-wrap">${_viewpointTable(groups)}</div>` +
    '</div>';
}

function _viewpointGroups(rows) {
  const defs = [
    {
      key: 'reachability',
      label: '到達性',
      desc: 'リンク操作で期待画面へ到達できるか',
      match: r => r.event === 'リンク',
      check: r => `${r.fromId}から${r.toId}へリンク操作で到達する`,
    },
    {
      key: 'form',
      label: '入力後遷移',
      desc: 'フォーム送信後に期待画面へ進むか',
      match: r => r.event === 'フォーム送信',
      check: r => `${r.fromId}の入力送信後に${r.toId}へ進む`,
    },
    {
      key: 'auth',
      label: '認証・会員導線',
      desc: 'ログイン、会員登録、認証前後の導線が妥当か',
      match: r => _rowText(r).match(/login|sign in|sign up|ログイン|会員|登録/i),
      check: r => `${r.fromId}から${r.toId}への認証関連導線を確認する`,
    },
    {
      key: 'critical',
      label: '業務クリティカル導線',
      desc: '予約、申込、完了など主要業務の導線が途切れないか',
      match: r => _rowText(r).match(/予約|reservation|reserve|plans|plan|宿泊|完了|confirm|complete/i),
      check: r => `${r.fromId}から${r.toId}への主要業務導線を確認する`,
    },
  ];
  return defs.map(def => {
    const matched = rows.filter(def.match);
    return {
      ...def,
      rows: matched.map(r => ({ ...r, check: def.check(r) })),
    };
  });
}

function _rowText(row) {
  return [row.fromId, row.fromTitle, row.event, row.eventDetail, row.toId, row.toTitle, row.action].join(' ');
}

function _viewpointCard(group) {
  return (
    '<div class="viewpoint-card">' +
    `<strong>${escHtml(group.label)}</strong>` +
    `<span class="viewpoint-count">${group.rows.length}</span>` +
    `<p>${escHtml(group.desc)}</p>` +
    '</div>'
  );
}

function _viewpointTable(groups) {
  const rows = groups.flatMap(group => group.rows.map(row => ({ group, row })));
  if (!rows.length) return '<div class="hero-msg">観点候補がありません。</div>';
  const tableRows = rows.map(({ group, row }) => `
    <tr>
      <td><span class="viewpoint-pill">${escHtml(group.label)}</span></td>
      <td class="c-screen">${escHtml(row.no)}</td>
      <td><strong>${escHtml(row.fromId)}</strong><span>${escHtml(row.fromTitle)}</span></td>
      <td><strong>${escHtml(row.toId)}</strong><span>${escHtml(row.toTitle)}</span></td>
      <td>${escHtml(row.check)}</td>
      <td>${escHtml(group.desc)}</td>
    </tr>
  `).join('');
  return (
    '<div class="uml-table-title">観点別テスト候補</div>' +
    '<table class="trans-table uml-linked-table viewpoint-table">' +
    '<thead><tr><th>観点</th><th>No</th><th>From</th><th>To</th><th>確認内容</th><th>狙い</th></tr></thead>' +
    `<tbody>${tableRows}</tbody>` +
    '</table>'
  );
}

async function _renderUmlDiagram(type, screens, rows) {
  const target = document.getElementById('uml-render-target');
  if (!target) return;
  const source = _umlSource(type, screens, rows);
  if (!rows.length) {
    target.innerHTML = '<div class="hero-msg">遷移情報がありません（共通ナビのみ検出）。</div>';
    return;
  }
  try {
    window.mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'strict' });
    const id = `uml-${type}-${Date.now()}`;
    const rendered = await window.mermaid.render(id, source);
    target.innerHTML = rendered.svg || rendered;
  } catch (e) {
    target.innerHTML = `<pre class="uml-source">${escHtml(source)}</pre>`;
  }
}

function _umlSource(type, screens, rows) {
  if (type === 'communication') return _communicationDiagram(screens, rows);
  if (type === 'activity') return _activityDiagram(rows);
  return _sequenceDiagram(screens, rows);
}

function _sequenceDiagram(screens, rows) {
  const diagramRows = rows.slice(0, 12);
  const used = new Set();
  diagramRows.forEach(r => { used.add(r.fromId); used.add(r.toId); });
  const participants = screens
    .filter(sc => used.has(sc.page_id))
    .map(sc => `  participant ${_umlAlias(sc.page_id)} as ${_mermaidText(sc.page_id)} ${_mermaidText(_shortVisLabel(sc))}`)
    .join('\n');
  const messages = diagramRows.map(r => {
    const arrow = r.event === 'フォーム送信' ? '->>' : '-->>';
    return `  ${_umlAlias(r.fromId)}${arrow}${_umlAlias(r.toId)}: ${r.no} ${_mermaidText(r.event)}`;
  }).join('\n');
  return `sequenceDiagram\n  autonumber\n${participants}\n${messages}`;
}

function _communicationDiagram(screens, rows) {
  const used = new Set();
  rows.forEach(r => { used.add(r.fromId); used.add(r.toId); });
  const nodes = screens
    .filter(sc => used.has(sc.page_id))
    .map(sc => `  ${_umlAlias(sc.page_id)}["${_mermaidText(sc.page_id)}<br/>${_mermaidText(_shortVisLabel(sc))}"]`)
    .join('\n');
  const edges = rows.map(r => {
    const arrow = r.event === 'フォーム送信' ? '-.->' : '-->';
    return `  ${_umlAlias(r.fromId)} ${arrow}|${r.no} ${_mermaidText(r.event)}| ${_umlAlias(r.toId)}`;
  }).join('\n');
  return `flowchart LR\n${nodes}\n${edges}`;
}

function _activityDiagram(rows) {
  const lines = ['flowchart TD', '  START([開始])'];
  rows.slice(0, 30).forEach((r, i) => {
    const prev = i === 0 ? 'START' : `CHECK${i - 1}`;
    lines.push(`  ${prev} --> S${i}["${_mermaidText(r.fromId)}を表示"]`);
    lines.push(`  S${i} --> A${i}["${r.no} ${_mermaidText(r.eventDetail || r.event)}"]`);
    lines.push(`  A${i} --> CHECK${i}{"${_mermaidText(r.toId)}へ到達?"}`);
    lines.push(`  CHECK${i} -->|OK| T${i}["${_mermaidText(r.toId)}を確認"]`);
    lines.push(`  CHECK${i} -->|NG| R${i}["遷移条件・リンク・入力値を確認"]`);
  });
  lines.push(`  CHECK${Math.min(rows.length, 30) - 1} --> END([終了])`);
  return lines.join('\n');
}

function _umlTable(type, rows) {
  if (!rows.length) return '<div class="hero-msg">表にできる遷移がありません。</div>';
  const title = type === 'activity' ? 'テスト手順表' : type === 'sequence' ? 'シナリオ表' : '遷移サマリー表';
  const tableRows = rows.map(r => `
    <tr>
      <td class="c-screen">${escHtml(r.no)}</td>
      <td><strong>${escHtml(r.fromId)}</strong><span>${escHtml(r.fromTitle)}</span></td>
      <td><span class="cond-pill ${r.event === 'フォーム送信' ? 'cc-format trans-event-form' : 'cc-other trans-event-link'}">${escHtml(r.event)}</span><span class="trans-link-detail">${escHtml(r.eventDetail)}</span></td>
      <td><strong>${escHtml(r.toId)}</strong><span>${escHtml(r.toTitle)}</span></td>
      <td>${escHtml(r.viewpoint)}</td>
    </tr>
  `).join('');
  return (
    `<div class="uml-table-title">${escHtml(title)}</div>` +
    '<table class="trans-table uml-linked-table">' +
    '<thead><tr><th>No</th><th>From</th><th>操作</th><th>To</th><th>QA観点</th></tr></thead>' +
    `<tbody>${tableRows}</tbody>` +
    '</table>'
  );
}

// ---- 画面遷移表（ISTQB 状態遷移テスト標準フォーマット）----
function renderTransitionTable() {
  if (!reportJson || !(reportJson.screens || []).length) {
    resultHero.innerHTML = '<div class="hero-msg">遷移データがありません。</div>';
    return;
  }
  const screens = reportJson.screens;
  const idToUrl = {};
  screens.forEach(s => { idToUrl[s.page_id] = s.url; });
  const rows = _transitionRows(screens);

  if (!rows.length) { resultHero.innerHTML = '<div class="hero-msg">遷移情報がありません（共通ナビのみ検出）。</div>'; return; }

  const tableRows = rows.map(r => {
    const destUrl = idToUrl[r.toId] || r.action || '';
    let linkPath = destUrl;
    try { linkPath = new URL(destUrl).pathname; } catch (e) {}
    return `<tr>
      <td class="c-screen">${escHtml(r.fromId)}</td>
      <td>${escHtml(r.fromTitle)}</td>
      <td>
        <span class="cond-pill ${r.event === 'フォーム送信' ? 'cc-format trans-event-form' : 'cc-other trans-event-link'}">${escHtml(r.event)}</span>
        <span class="trans-link-detail">${escHtml(r.event === 'フォーム送信' ? r.eventDetail : linkPath)}</span>
      </td>
      <td class="c-screen">${escHtml(r.toId)}</td>
      <td>${escHtml(r.toTitle)}</td>
      <td style="font-size:11px;font-family:monospace;color:var(--text-muted);word-break:break-all">${escHtml(destUrl)}</td>
    </tr>`;
  }).join('');

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
