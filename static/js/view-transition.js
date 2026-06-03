// ---- 画面遷移図（UML 3種サブタブ）----
function _commonNavTargets(screens) {
  const n = screens.length;
  const count = {};
  screens.forEach(sc => {
    (sc.transitions && sc.transitions.to || []).forEach(to => { count[to] = (count[to] || 0) + 1; });
  });
  const threshold = Math.max(2, Math.floor(n * 0.5));
  return new Set(Object.entries(count).filter(([, c]) => c >= threshold).map(([k]) => k));
}

function renderTransition() {
  if (!reportJson || !(reportJson.screens || []).length) {
    resultHero.innerHTML = '<div class="hero-msg">遷移データがありません。クロールを実行してください。</div>';
    return;
  }
  resultHero.innerHTML =
    '<div style="display:flex;flex-direction:column;height:100%;min-height:0">' +
    '<div class="uml-subtabs" id="uml-subtabs">' +
    '<button class="uml-subtab is-active" data-uml="sequence">シーケンス図</button>' +
    '<button class="uml-subtab" data-uml="communication">コミュニケーション図</button>' +
    '<button class="uml-subtab" data-uml="activity">アクティビティ図</button>' +
    '</div>' +
    '<div id="uml-diagram-area" style="flex:1;overflow:auto;padding:16px;background:#fafafa;border:1px solid var(--border);border-top:none;"></div>' +
    '</div>';

  document.querySelectorAll('.uml-subtab').forEach(t => {
    t.addEventListener('click', () => {
      document.querySelectorAll('.uml-subtab').forEach(x => x.classList.toggle('is-active', x === t));
      _renderUmlDiagram(t.dataset.uml, reportJson.screens);
    });
  });
  _loadMermaid(() => _renderUmlDiagram('sequence', reportJson.screens));
}

function _loadMermaid(cb) {
  if (window.mermaid) { cb(); return; }
  const s = document.createElement('script');
  s.src = 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js';
  s.onload = () => {
    window.mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'loose', fontFamily: 'system-ui, sans-serif' });
    cb();
  };
  document.head.appendChild(s);
}

async function _renderUmlDiagram(type, screens) {
  const area = document.getElementById('uml-diagram-area');
  if (!area) return;
  const common = _commonNavTargets(screens);
  const urlToId = {};
  screens.forEach(s => { urlToId[s.url] = s.page_id; });

  let src = '';
  if (type === 'sequence') src = _buildSequenceDiagram(screens, common, urlToId);
  else if (type === 'communication') src = _buildCommunicationDiagram(screens, common, urlToId);
  else src = _buildActivityDiagram(screens, common, urlToId);

  area.innerHTML = '<p style="color:var(--text-muted);font-size:12px;margin:0 0 8px">※ 共通ナビゲーション（全ページの50%以上から発生する遷移）は除外しています。</p><div id="uml-render-target"></div>';
  try {
    const { svg } = await window.mermaid.render('uml-svg-' + type + '-' + Date.now(), src);
    document.getElementById('uml-render-target').innerHTML = svg;
  } catch (e) {
    area.innerHTML = `<pre style="font-size:11px;color:var(--critical)">${escHtml(String(e))}</pre><pre style="font-size:11px;background:#f3f4f6;padding:12px;border-radius:6px;overflow:auto">${escHtml(src)}</pre>`;
  }
}

function _shortLabel(sc) {
  return (sc.title || sc.page_id).replace(/\s*[|｜]\s*.*/g, '').replace(/['"]/g, '').slice(0, 24) || sc.page_id;
}

function _buildSequenceDiagram(screens, common, urlToId) {
  const lines = ['sequenceDiagram'];
  screens.forEach(sc => {
    lines.push(`  participant ${sc.page_id} as ${_shortLabel(sc)}`);
  });
  screens.forEach(sc => {
    (sc.transitions && sc.transitions.to || []).forEach(to => {
      if (!common.has(to)) lines.push(`  ${sc.page_id}->>${to}: リンク`);
    });
    (sc.forms || []).forEach(f => {
      const toId = f.action ? urlToId[f.action] : null;
      if (toId && toId !== sc.page_id && !common.has(toId)) {
        lines.push(`  ${sc.page_id}-->>${toId}: フォーム送信`);
      }
    });
  });
  return lines.join('\n');
}

function _buildCommunicationDiagram(screens, common, urlToId) {
  const lines = ['graph LR'];
  screens.forEach(sc => {
    const label = _shortLabel(sc).replace(/[()]/g, '');
    const shape = (sc.forms || []).some(f => f.fields && f.fields.length)
      ? `${sc.page_id}["📋 ${sc.page_id}\\n${label}"]`
      : `${sc.page_id}["📄 ${sc.page_id}\\n${label}"]`;
    lines.push(`  ${shape}`);
  });
  let seq = 1;
  screens.forEach(sc => {
    (sc.transitions && sc.transitions.to || []).forEach(to => {
      if (!common.has(to)) lines.push(`  ${sc.page_id} -->|"${seq++}. リンク"| ${to}`);
    });
    (sc.forms || []).forEach(f => {
      const toId = f.action ? urlToId[f.action] : null;
      if (toId && toId !== sc.page_id && !common.has(toId)) {
        lines.push(`  ${sc.page_id} -.->|"${seq++}. ${(f.method || 'POST').toUpperCase()}"| ${toId}`);
      }
    });
  });
  return lines.join('\n');
}

function _buildActivityDiagram(screens, common, urlToId) {
  const lines = ['flowchart TD'];
  lines.push('  START([▶ 開始])');
  const starts = screens.filter(sc => (sc.transitions && sc.transitions.from || []).length === 0);
  (starts.length ? starts : screens.slice(0, 1)).forEach(sc => {
    lines.push(`  START --> ${sc.page_id}`);
  });
  screens.forEach(sc => {
    const label = _shortLabel(sc).replace(/[()]/g, '');
    const hasForm = (sc.forms || []).some(f => f.fields && f.fields.length);
    const shape = hasForm ? `${sc.page_id}["📋 ${label}"]` : `${sc.page_id}["${label}"]`;
    lines.push(`  ${shape}`);
    (sc.transitions && sc.transitions.to || []).forEach(to => {
      if (!common.has(to)) lines.push(`  ${sc.page_id} --> ${to}`);
    });
    (sc.forms || []).forEach(f => {
      const toId = f.action ? urlToId[f.action] : null;
      if (toId && toId !== sc.page_id && !common.has(toId)) {
        lines.push(`  ${sc.page_id} -->|"${(f.method || 'POST').toUpperCase()}"| ${toId}`);
      }
    });
  });
  const ends = screens.filter(sc => (sc.transitions && sc.transitions.to || []).filter(t => !common.has(t)).length === 0);
  (ends.length ? ends : []).forEach(sc => lines.push(`  ${sc.page_id} --> END`));
  if (ends.length) lines.push('  END([⏹ 終了])');
  return lines.join('\n');
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

