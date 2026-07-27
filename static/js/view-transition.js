// ---- 画面遷移図（UML 3タブ + テスト観点マップ）----
let umlZoom = 1;
let _currentUmlSource = '';
let _currentUmlType = 'sequence';

function _setupPan(canvas) {
  let dragging = false, startX = 0, startY = 0, startSL = 0, startST = 0;
  canvas.addEventListener('pointerdown', e => {
    if (e.button !== 0) return;
    dragging = true;
    startX = e.clientX; startY = e.clientY;
    startSL = canvas.scrollLeft; startST = canvas.scrollTop;
    canvas.classList.add('is-panning');
    canvas.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  canvas.addEventListener('pointermove', e => {
    if (!dragging) return;
    canvas.scrollLeft = startSL - (e.clientX - startX);
    canvas.scrollTop = startST - (e.clientY - startY);
  });
  canvas.addEventListener('pointerup', () => { dragging = false; canvas.classList.remove('is-panning'); });
  canvas.addEventListener('pointercancel', () => { dragging = false; canvas.classList.remove('is-panning'); });
  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    _setUmlZoom(umlZoom + (e.deltaY < 0 ? 0.1 : -0.1));
  }, { passive: false });
}

function _toggleUmlFullscreen() {
  const canvas = document.getElementById('uml-render-target');
  if (!canvas) return;
  const isFs = canvas.classList.toggle('is-fullscreen');
  document.querySelectorAll('[data-zoom="fullscreen"]').forEach(btn => {
    btn.title = isFs ? '全画面を解除 (Esc)' : '全画面 (Esc で解除)';
    btn.textContent = isFs ? '✕' : '⛶';
  });
  if (isFs) setTimeout(() => _fitUmlZoom(), 50);
}

function _exportUmlSvg() {
  const stage = document.getElementById('uml-zoom-stage');
  const svg = stage && stage.querySelector('svg');
  if (!svg) return;
  const blob = new Blob([new XMLSerializer().serializeToString(svg)], { type: 'image/svg+xml' });
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement('a'), { href: url, download: `${_currentUmlType}.svg` });
  a.click();
  URL.revokeObjectURL(url);
}

function _exportUmlPng() {
  const stage = document.getElementById('uml-zoom-stage');
  const svg = stage && stage.querySelector('svg');
  if (!svg) return;
  const svgStr = new XMLSerializer().serializeToString(svg);
  const svgBlob = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' });
  const url = URL.createObjectURL(svgBlob);
  const img = new Image();
  img.onload = () => {
    const w = svg.viewBox.baseVal.width || img.naturalWidth || 800;
    const h = svg.viewBox.baseVal.height || img.naturalHeight || 600;
    const canvas = document.createElement('canvas');
    canvas.width = w * 2;
    canvas.height = h * 2;
    const ctx = canvas.getContext('2d');
    ctx.scale(2, 2);
    // エクスポート PNG の下地は常に白（文書貼付・印刷用途。UI テーマに依存させない）
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, w, h);
    ctx.drawImage(img, 0, 0, w, h);
    URL.revokeObjectURL(url);
    const a = Object.assign(document.createElement('a'), { href: canvas.toDataURL('image/png'), download: `${_currentUmlType}.png` });
    a.click();
  };
  img.onerror = () => URL.revokeObjectURL(url);
  img.src = url;
}

function _exportUmlMmd() {
  if (!_currentUmlSource) return;
  const blob = new Blob([_currentUmlSource], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement('a'), { href: url, download: `${_currentUmlType}.mmd` });
  a.click();
  URL.revokeObjectURL(url);
}

document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  const canvas = document.getElementById('uml-render-target');
  if (canvas && canvas.classList.contains('is-fullscreen')) _toggleUmlFullscreen();
});

// 遷移「図」だけで使う間引き。図はヘッダリンクで密になると読めなくなるため、
// 全画面から張られている真の共通ナビだけを落とす。
// 割合（旧: 画面数の50%以上）を閾値にすると、画面数が少ないサイトでは
// 2画面から張られた通常のリンクまで共通ナビ扱いになり、図から遷移が消える。
// そのため「外向き遷移を持つ全画面（自分自身を除く）から張られているか」で判定し、
// 判定が成立しうる規模（3画面以上）でのみ適用する。
// なお遷移「表」では間引かない（状態遷移表は共通ナビを含めてこそ被覆が成立する）。
const _COMMON_NAV_MIN_SCREENS = 3;

function _commonNavTargets(screens) {
  if (screens.length < _COMMON_NAV_MIN_SCREENS) return new Set();
  const sources = {};
  const withExits = new Set();
  screens.forEach(sc => {
    const to = (sc.transitions && sc.transitions.to) || [];
    if (to.length) withExits.add(sc.page_id);
    to.forEach(t => { (sources[t] = sources[t] || new Set()).add(sc.page_id); });
  });
  const common = new Set();
  Object.entries(sources).forEach(([target, from]) => {
    const candidates = [...withExits].filter(id => id !== target);
    if (candidates.length >= 2 && candidates.every(id => from.has(id))) common.add(target);
  });
  return common;
}

function _shortVisLabel(sc) {
  return (sc.title || sc.page_id).replace(/\s*[|｜]\s*.*/g, '').replace(/['"]/g, '').slice(0, 24) || sc.page_id;
}

// セルフホスト版のみを使用し、外部ネットワークへコードを取得しない。
const _MERMAID_SOURCE = '/static/vendor/mermaid/mermaid.min.js';

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
  const tryLoad = () => {
    const s = document.createElement('script');
    s.src = _MERMAID_SOURCE;
    s.dataset.lib = 'mermaid';
    s.onload = cb;
    s.onerror = () => {
      s.remove();
      const target = document.getElementById('uml-render-target');
      if (target && typeof uiError === 'function') {
        uiError(target, {
          title: '遷移図ライブラリを読み込めませんでした',
          message: 'ローカル資産が見つかりません。遷移表タブをご利用ください。',
          onRetry: tryLoad,
        });
      }
    };
    document.head.appendChild(s);
  };
  tryLoad();
}

function _umlAlias(value) {
  return `N${String(value || '').replace(/[^a-zA-Z0-9_]/g, '_')}`;
}

function _mermaidText(value) {
  return String(value || '').replace(/[<>{}"'`]/g, '').replace(/\s+/g, ' ').trim();
}

// 間引き後にこの割合を下回るなら、間引き自体をやめて全遷移を出す。
// 全画面が相互リンクするサイトでは「共通ナビ」判定が全遷移に当たり、
// 図が空になってしまう。読みにくい図の方が、何も無い図よりましである。
const _COMMON_NAV_KEEP_RATIO = 0.3;

//: 直近の _transitionRows が実際に間引いたかどうか（見出し文の生成に使う）。
let _lastTransitionFiltered = false;

function _transitionRows(screens) {
  const all = _collectTransitionRows(screens, new Set());
  const common = _commonNavTargets(screens);
  if (!common.size) {
    _lastTransitionFiltered = false;
    return all;
  }
  const filtered = _collectTransitionRows(screens, common);
  if (filtered.length < Math.max(1, Math.floor(all.length * _COMMON_NAV_KEEP_RATIO))) {
    _lastTransitionFiltered = false;
    return all;
  }
  _lastTransitionFiltered = true;
  return filtered;
}

function _collectTransitionRows(screens, common) {
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
    const toTitle = idToScreen[row.toId].title || row.toId;
    const eventDetail = row.eventDetail || '';
    rows.push({
      no: `T${String(rows.length + 1).padStart(2, '0')}`,
      fromId: row.fromId,
      fromTitle: idToScreen[row.fromId].title || row.fromId,
      event: row.event,
      eventDetail,
      toId: row.toId,
      toTitle,
      action: row.action || '',
      // R2-11: 固定文言ではなく実データ（操作内容・遷移先画面名）で具体化する
      viewpoint: row.event === 'フォーム送信'
        ? `${eventDetail}を実行すると「${toTitle}」へ到達する`
        : `${eventDetail}を押すと「${toTitle}」へ遷移する`,
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
    '<button class="uml-subtab" data-uml="flowchart">フローチャート<span>処理の流れ</span></button>' +
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
  _currentUmlType = type;
  umlZoom = 1;
  area.innerHTML =
    '<div class="uml-panel-head">' +
    `<div><strong>${escHtml(meta.title)}</strong><span>${escHtml(meta.desc)}</span></div>` +
    '<div class="uml-panel-actions">' +
    `<p>${rows.length}件の遷移。${_lastTransitionFiltered
      ? '図を読めるようにするため、全画面から張られている共通ナビゲーションは除外しています（遷移表には含まれます）。'
      : '共通ナビゲーションを除外すると図がほぼ空になるため、除外していません。'}</p>` +
    _umlZoomControls() +
    '</div>' +
    '</div>' +
    '<div class="uml-layout">' +
    '<div class="uml-canvas" id="uml-render-target"><div class="hero-msg">図を描画しています…</div></div>' +
    `<div class="uml-table-wrap">${_umlTable(type, rows)}</div>` +
    '</div>';
  _loadMermaid(() => {
    _renderUmlDiagram(type, screens, rows).then(() => {
      setTimeout(_initUmlZoom, 100);
    });
  });
}

function _umlZoomControls() {
  return (
    '<div class="uml-zoom-controls" aria-label="図のズーム">' +
    '<button type="button" class="uml-zoom-btn" data-zoom="out" title="縮小 (ホイール↓)">−</button>' +
    '<button type="button" class="uml-zoom-btn uml-zoom-level" data-zoom="reset" title="100%に戻す">100%</button>' +
    '<button type="button" class="uml-zoom-btn" data-zoom="in" title="拡大 (ホイール↑)">＋</button>' +
    '<button type="button" class="uml-zoom-btn" data-zoom="fit" title="幅に合わせる">Fit</button>' +
    '<button type="button" class="uml-zoom-btn uml-zoom-sep" data-zoom="fullscreen" title="全画面 (Esc で解除)">⛶</button>' +
    '<span class="uml-zoom-divider"></span>' +
    '<button type="button" class="uml-zoom-btn uml-dl-btn" data-dl="svg" title="SVGをダウンロード">↓ SVG</button>' +
    '<button type="button" class="uml-zoom-btn uml-dl-btn" data-dl="png" title="PNGをダウンロード（2x高解像度）">↓ PNG</button>' +
    '<button type="button" class="uml-zoom-btn uml-dl-btn" data-dl="mmd" title="Mermaidソースをダウンロード（編集・再利用用）">↓ MMD</button>' +
    '</div>'
  );
}

function _umlMeta(type) {
  if (type === 'communication') {
    return { title: 'コミュニケーション図', desc: '画面間の関係をエッジ番号で俯瞰します。' };
  }
  if (type === 'activity') {
    return { title: 'アクティビティ図', desc: 'QAテスト手順として操作と期待結果を追います。' };
  }
  if (type === 'flowchart') {
    return { title: 'フローチャート', desc: '入口画面から各画面への処理の流れを上から下へ追います。' };
  }
  return { title: 'シーケンス図', desc: '代表的な遷移を時系列で確認します。' };
}

function _showViewpointMap(area, rows) {
  const groups = _viewpointGroups(rows);
  const totalChecks = groups.reduce((sum, g) => sum + g.rows.length, 0);
  // R1-05: 「見方がわかりにくい」への対応。各観点カテゴリの意味を凡例として明示する。
  const legend = groups.map(g =>
    `<span class="vp-legend-item"><strong>${escHtml(g.label)}</strong>: ${escHtml(g.desc)}</span>`
  ).join('');
  area.innerHTML =
    '<div class="uml-panel-head">' +
    '<div><strong>テスト観点マップ</strong><span>遷移をQA観点へ分類し、テスト設計の入口にします。</span></div>' +
    `<p>${rows.length}件の遷移から${totalChecks}件の観点候補を抽出しています。</p>` +
    '</div>' +
    `<div class="viewpoint-legend" aria-label="観点カテゴリの見方">${legend}</div>` +
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
  _currentUmlSource = source;
  if (!rows.length) {
    target.innerHTML = '<div class="hero-msg">遷移が観測されていません。</div>';
    return;
  }
  try {
    window.mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'strict' });
    const id = `uml-${type}-${Date.now()}`;
    const rendered = await window.mermaid.render(id, source);
    target.innerHTML = `<div class="uml-zoom-stage" id="uml-zoom-stage">${rendered.svg || rendered}</div>`;
    _prepareUmlZoom();
  } catch (e) {
    target.innerHTML = `<pre class="uml-source">${escHtml(source)}</pre>`;
  }
}

function _prepareUmlZoom() {
  const stage = document.getElementById('uml-zoom-stage');
  const svg = stage && stage.querySelector('svg');
  if (!stage || !svg) return;
  svg.style.maxWidth = 'none';
  const box = svg.getBoundingClientRect();
  stage.dataset.baseWidth = String(Math.max(1, Math.ceil(box.width)));
  stage.dataset.baseHeight = String(Math.max(1, Math.ceil(box.height)));
  _setUmlZoom(umlZoom);
  const canvas = document.getElementById('uml-render-target');
  if (canvas) _setupPan(canvas);
  document.querySelectorAll('.uml-zoom-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const mode = btn.dataset.zoom;
      if (mode === 'in') _setUmlZoom(umlZoom + 0.15);
      else if (mode === 'out') _setUmlZoom(umlZoom - 0.15);
      else if (mode === 'reset') { _setUmlZoom(1); if (canvas) { canvas.scrollLeft = 0; canvas.scrollTop = 0; } }
      else if (mode === 'fit') _fitUmlZoom();
      else if (mode === 'fullscreen') _toggleUmlFullscreen();
    });
  });
  document.querySelectorAll('.uml-dl-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const fmt = btn.dataset.dl;
      if (fmt === 'svg') _exportUmlSvg();
      else if (fmt === 'png') _exportUmlPng();
      else if (fmt === 'mmd') _exportUmlMmd();
    });
  });
}

function _setUmlZoom(value) {
  umlZoom = Math.min(5.0, Math.max(0.35, value));
  const stage = document.getElementById('uml-zoom-stage');
  const svg = stage && stage.querySelector('svg');
  if (stage && svg) {
    const baseWidth = Number(stage.dataset.baseWidth || 1);
    const baseHeight = Number(stage.dataset.baseHeight || 1);
    stage.style.width = `${Math.ceil(baseWidth * umlZoom)}px`;
    stage.style.height = `${Math.ceil(baseHeight * umlZoom)}px`;
    svg.style.transformOrigin = 'top left';
    svg.style.transform = `scale(${umlZoom})`;
  }
  const level = document.querySelector('.uml-zoom-level');
  if (level) level.textContent = `${Math.round(umlZoom * 100)}%`;
}

function _fitUmlZoom() {
  _applyUmlFit(false);
}

// 初期表示は等倍。Fit をそのまま使うと小さい図が 250% 超まで引き伸ばされ、
// 線と文字だけが太った読みにくい絵になる。画面より広い図のときだけ縮める。
function _initUmlZoom() {
  _applyUmlFit(true);
}

function _applyUmlFit(capToActualSize) {
  const target = document.getElementById('uml-render-target');
  const stage = document.getElementById('uml-zoom-stage');
  if (!target || !stage) return;
  const baseWidth = Number(stage.dataset.baseWidth || 1);
  const fit = (target.clientWidth - 32) / baseWidth;
  _setUmlZoom(capToActualSize ? Math.min(1, fit) : fit);
  target.scrollLeft = 0;
  target.scrollTop = 0;
}

function _umlSource(type, screens, rows) {
  if (type === 'communication') return _communicationDiagram(screens, rows);
  if (type === 'activity') return _activityDiagram(rows);
  if (type === 'flowchart') return _flowchartDiagram(rows);
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

// R2-12: 遷移をトップダウンの処理フロー（フローチャート）として描画する。
// コミュニケーション図(flowchart LR・関係俯瞰)とは向き・粒度が異なり、
// 入口画面(START)から各画面への「処理の流れ」を上から下へ追える形にする。
function _flowchartDiagram(rows) {
  if (!rows.length) return 'flowchart TD\n  START([開始])';
  const titleById = {};
  const targets = new Set();
  rows.forEach(r => {
    titleById[r.fromId] = r.fromTitle;
    titleById[r.toId] = r.toTitle;
    targets.add(r.toId);
  });
  const nodes = Object.keys(titleById)
    .map(id => `  ${_umlAlias(id)}["${_mermaidText(id)}<br/>${_mermaidText(titleById[id])}"]`)
    .join('\n');
  // 遷移先になっていない画面＝入口とみなし、START から接続する（無ければ先頭行のfrom）。
  const entries = Object.keys(titleById).filter(id => !targets.has(id));
  const starts = (entries.length ? entries : [rows[0].fromId])
    .map(id => `  START([開始]) --> ${_umlAlias(id)}`)
    .join('\n');
  // フォーム送信は太線(==>)、リンクは通常線(-->)で区別する。
  const edges = rows.map(r => {
    const arrow = r.event === 'フォーム送信' ? '==>' : '-->';
    return `  ${_umlAlias(r.fromId)} ${arrow}|${r.no} ${_mermaidText(r.eventDetail || r.event)}| ${_umlAlias(r.toId)}`;
  }).join('\n');
  return `flowchart TD\n  START([開始])\n${nodes}\n${starts}\n${edges}`;
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

// ---- 画面遷移表（ISTQB 状態遷移テスト）----
// 成果物は「有効遷移の一覧」だけでは足りない。状態 × イベントの全マトリクスと、
// そこに現れる無効遷移、0-switch / 1-switch 被覆までを一式で示す。
// 共通ナビゲーションは除外しない（除外すると「どの状態からでも同じイベントを
// 受け付ける」という表の核心が消え、被覆も欠ける）。印を付けるだけに留める。

function _stStatePill(state) {
  const marks = [];
  if (state.is_initial) marks.push('<span class="cond-pill cc-format">初期状態</span>');
  if (state.is_final) marks.push('<span class="cond-pill cc-other">終了状態</span>');
  return marks.join(' ');
}

function _stSummaryBlock(data) {
  const s = data.summary;
  const items = [
    ['状態', s.state_count],
    ['イベント', s.event_count],
    ['有効遷移', s.valid_transition_count],
    ['無効遷移', s.invalid_transition_count],
    ['0-switch', data.coverage.zero_switch.count],
    ['1-switch', data.coverage.one_switch.count],
  ];
  return (
    '<div class="st-summary">' +
    items.map(([label, value]) =>
      `<div class="st-summary-cell"><span class="st-summary-num">${value}</span><span class="st-summary-label">${escHtml(label)}</span></div>`
    ).join('') +
    '</div>'
  );
}

function _stMatrixBlock(data) {
  const head = data.events.map(e =>
    `<th title="${escHtml(e.label)}">${escHtml(e.event_id)}${e.is_common ? '<span class="st-common">共通</span>' : ''}</th>`
  ).join('');
  const body = data.matrix.map(row => {
    const cells = row.cells.map(c =>
      c.valid
        ? `<td class="st-cell st-valid">${escHtml(c.to)}</td>`
        : '<td class="st-cell st-invalid" title="無効遷移（この状態でこのイベントは定義されていない）">－</td>'
    ).join('');
    return `<tr><th class="st-rowhead">${escHtml(row.state_id)}<span>${escHtml(row.title)}</span></th>${cells}</tr>`;
  }).join('');
  return (
    '<div class="hero-section-title">状態遷移表（状態 × イベント）</div>' +
    '<p class="st-note">セルは遷移先の状態。<strong>－ は無効遷移</strong>で、その状態にそのイベントの導線が無いことを表す。</p>' +
    '<div style="overflow-x:auto"><table class="trans-table st-matrix">' +
    `<thead><tr><th>状態＼イベント</th>${head}</tr></thead>` +
    `<tbody>${body}</tbody></table></div>`
  );
}

function _stEventsBlock(data) {
  const rows = data.events.map(e => `
    <tr>
      <td class="c-screen">${escHtml(e.event_id)}</td>
      <td><span class="cond-pill ${e.kind === 'フォーム送信' ? 'cc-format trans-event-form' : 'cc-other trans-event-link'}">${escHtml(e.kind)}</span></td>
      <td>${escHtml(e.label)}</td>
      <td>${e.source_count}</td>
      <td>${e.is_common ? '共通ナビ' : '個別'}</td>
    </tr>`).join('');
  return (
    '<div class="hero-section-title">イベント一覧</div>' +
    '<table class="trans-table"><thead><tr><th>ID</th><th>種別</th><th>操作</th><th>受付状態数</th><th>区分</th></tr></thead>' +
    `<tbody>${rows}</tbody></table>`
  );
}

const _ST_KIND_LABEL = {
  screen: '画面',
  modal: 'モーダル',
  tabpanel: 'タブ',
  accordion: 'アコーディオン',
  dom_change: 'DOM変化',
};

function _stStatesBlock(data) {
  const rows = data.states.map(s => `
    <tr>
      <td class="c-screen">${escHtml(s.state_id)}</td>
      <td>${escHtml(s.title)}</td>
      <td>${escHtml(_ST_KIND_LABEL[s.kind] || s.kind)}${s.parent ? `<span class="trans-link-detail">親: ${escHtml(s.parent)}</span>` : ''}</td>
      <td>${_stStatePill(s)}</td>
      <td style="font-size:11px;font-family:monospace;color:var(--text-muted);word-break:break-all">${escHtml(s.url)}</td>
    </tr>`).join('');
  const child = data.summary.child_state_count;
  const note = child
    ? `<p class="st-note">同一 URL でも画面内アクションで出現する状態（モーダル等）は別状態として ${child} 件に分けています。</p>`
    : '<p class="st-note">画面内アクションによる状態（モーダル等）は観測されていません。</p>';
  return (
    '<div class="hero-section-title">状態一覧</div>' + note +
    '<table class="trans-table"><thead><tr><th>状態</th><th>タイトル</th><th>種別</th><th>区分</th><th>URL</th></tr></thead>' +
    `<tbody>${rows}</tbody></table>`
  );
}

function _stPathsBlock(data) {
  const zero = data.coverage.zero_switch.paths.map(p => `
    <tr><td class="c-screen">${escHtml(p.path_id)}</td><td>${escHtml(p.steps.join(' → '))}</td><td>${escHtml(p.event)}</td><td>${escHtml(p.expected)}</td></tr>`).join('');
  const one = data.coverage.one_switch.paths.map(p => `
    <tr><td class="c-screen">${escHtml(p.path_id)}</td><td>${escHtml(p.steps.join(' → '))}</td><td>${escHtml(p.events.join(' , '))}</td><td>${escHtml(p.expected)}</td></tr>`).join('');
  const droppedPaths = data.coverage.one_switch.dropped_paths || [];
  const droppedBlock = droppedPaths.length
    ? '<div class="hero-section-title">1-switch で除外した経路（' + droppedPaths.length + '件）</div>' +
      '<p class="st-note">上限を超えたため自動生成から外した経路。網羅済みと誤読しないよう全件を記載する（手動で補う対象）。</p>' +
      '<table class="trans-table"><thead><tr><th>経路</th><th>イベント</th><th>除外理由</th></tr></thead><tbody>' +
      droppedPaths.map(p => `<tr><td>${escHtml(p.steps.join(' → '))}</td><td>${escHtml((p.events || []).join(' , '))}</td><td>${escHtml(p.reason || '')}</td></tr>`).join('') +
      '</tbody></table>'
    : '';
  return (
    '<div class="hero-section-title">0-switch 被覆（各有効遷移を1回）</div>' +
    '<table class="trans-table"><thead><tr><th>ID</th><th>経路</th><th>イベント</th><th>期待結果</th></tr></thead>' +
    `<tbody>${zero}</tbody></table>` +
    '<div class="hero-section-title">1-switch 被覆（連続する2遷移の全組合せ）</div>' +
    '<table class="trans-table"><thead><tr><th>ID</th><th>経路</th><th>イベント</th><th>期待結果</th></tr></thead>' +
    `<tbody>${one}</tbody></table>` +
    droppedBlock
  );
}

function _stInvalidBlock(data) {
  const rows = data.coverage.invalid.cases.map(c => {
    const direct = c.direct_access_check || {};
    const directCell = direct.applicable
      ? `<strong>手順</strong><br>${(direct.steps || []).map(escHtml).join('<br>')}<span class="trans-link-detail">期待: ${escHtml(direct.expected || '')}</span>`
      : `<span style="color:var(--text-muted)">対象外 — ${escHtml(direct.reason || '')}</span>`;
    return `<tr>
      <td class="c-screen">${escHtml(c.case_id)}</td>
      <td class="c-screen">${escHtml(c.state)}</td>
      <td>${escHtml(c.event)}<span class="trans-link-detail">${escHtml(c.event_label || '')}</span></td>
      <td>${escHtml(c.reason)}</td>
      <td>${(c.ui_check.steps || []).map(escHtml).join('<br>')}<span class="trans-link-detail">期待: ${escHtml(c.ui_check.expected || '')}</span></td>
      <td>${directCell}</td>
    </tr>`;
  }).join('');
  return (
    '<div class="hero-section-title">無効遷移の検証（' + data.coverage.invalid.count + '件）</div>' +
    '<p class="st-note">「起きてはいけない遷移」の確認は状態遷移テストの主目的の一つで、有効遷移だけの一覧からは得られない。' +
    '<strong>導線が無いことの確認だけでは不十分</strong>で、URL を直接開けば到達できる場合があるため、認可の確認を別立てにしている。</p>' +
    '<div style="overflow-x:auto"><table class="trans-table"><thead><tr><th>ID</th><th>状態</th><th>イベント</th><th>無効である理由</th><th>UI上の確認</th><th>直接アクセスの確認（認可）</th></tr></thead>' +
    `<tbody>${rows}</tbody></table></div>`
  );
}

async function renderTransitionTable() {
  const domain = typeof currentResultDomain === 'string' ? currentResultDomain : '';
  if (!domain) {
    resultHero.innerHTML = '<div class="hero-msg">遷移データがありません。</div>';
    return;
  }
  resultHero.innerHTML = '<div class="hero-msg">状態遷移表を作成しています…</div>';

  let data;
  try {
    const res = await fetch('/api/state-table?domain=' + encodeURIComponent(domain));
    data = await res.json();
    if (!res.ok) throw new Error(data.error || '状態遷移表の取得に失敗しました');
  } catch (e) {
    resultHero.innerHTML = `<div class="hero-msg">状態遷移表を取得できませんでした（${escHtml(e.message)}）。</div>`;
    return;
  }
  if (!data.applicable) {
    resultHero.innerHTML = `<div class="hero-msg">${escHtml(data.reason || '状態が観測されていません。')}</div>`;
    return;
  }

  const s = data.summary;
  const notice = data.notice ? `<p class="st-note">注記: ${escHtml(data.notice)}</p>` : '';
  resultHero.innerHTML =
    '<div class="hero-pad">' +
    '<div class="hero-section-title">画面遷移表 — ISTQB 状態遷移テスト</div>' +
    `<p class="st-note">状態 ${s.state_count} × イベント ${s.event_count} = ${s.cell_total} セルのうち、` +
    `有効遷移 ${s.valid_transition_count} 件・無効遷移 ${s.invalid_transition_count} 件。` +
    `初期状態 ${escHtml((s.initial_states || []).join(', ') || 'なし')} ／ 終了状態 ${escHtml((s.final_states || []).join(', ') || 'なし')}。` +
    `共通ナビは ${s.common_events.length} 件を識別しているが、被覆が欠けるため除外していない。</p>` +
    _stSummaryBlock(data) +
    _stMatrixBlock(data) +
    _stStatesBlock(data) +
    _stEventsBlock(data) +
    _stInvalidBlock(data) +
    _stPathsBlock(data) +
    notice +
    '</div>';
}
