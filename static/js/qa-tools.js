// ---- QA拡張ビュー（品質観点）----
const QA_TOOL_CONFIG = {
  'qa-quality': {
    select: 'qa-quality-domain-select',
    status: 'qa-quality-status',
    content: 'qa-quality-content',
    outputs: 'qa-quality-output-links',
    render: renderQaQualityTool,
  },
};
const QA_TOOL_LABELS = {
  quality_viewpoints: '品質観点JSON',
  quality_viewpoints_html: '品質観点HTML',
};
let qaToolSitesLoaded = false;

function qaList(items) {
  const values = Array.isArray(items) ? items : [];
  if (values.length === 0) return '<li>なし</li>';
  return values.map(item => `<li>${escHtml(item)}</li>`).join('');
}

async function loadQaToolSites(viewName, force) {
  const cfg = QA_TOOL_CONFIG[viewName];
  if (!cfg) return;
  if (qaToolSitesLoaded && !force) {
    const selectEl = document.getElementById(cfg.select);
    if (selectEl?.value) await loadQaToolData(viewName, selectEl.value);
    return;
  }
  setQaToolStatus(viewName, '解析済みサイトを読み込んでいます。');
  try {
    const res = await fetch('/api/history');
    const data = await res.json();
    const items = data.items || [];
    for (const toolName of Object.keys(QA_TOOL_CONFIG)) {
      const select = document.getElementById(QA_TOOL_CONFIG[toolName].select);
      if (!select) continue;
      const previous = select.value;
      select.innerHTML = '<option value="">解析済みサイトを選択</option>' +
        items.map(it => `<option value="${escHtml(it.domain)}">${escHtml(it.domain)}</option>`).join('');
      if (previous && items.some(it => it.domain === previous)) select.value = previous;
      if (!previous && items.length > 0) select.value = items[0].domain;
    }
    qaToolSitesLoaded = true;
    if (items.length > 0) {
      const selectEl = document.getElementById(cfg.select);
      if (selectEl?.value) await loadQaToolData(viewName, selectEl.value);
      return;
    }
    setQaToolStatus(viewName, '解析済みサイトがありません。「+ サイトを追加」から最初のサイトを登録してください。');
    for (const toolCfg of Object.values(QA_TOOL_CONFIG)) {
      const contentEl = document.getElementById(toolCfg.content);
      const outputsEl = document.getElementById(toolCfg.outputs);
      if (contentEl) {
        contentEl.innerHTML = `<div class="empty" style="text-align:center;padding:40px 20px">
          <p style="font-size:15px;font-weight:700;margin-bottom:8px">まだ解析済みサイトがありません</p>
          <p style="font-size:13px;color:var(--text-muted);margin-bottom:20px">
            生成ウィザードでサイトを解析すると、ここにデータが表示されます。
          </p>
          <button type="button" class="btn-primary qa-empty-goto-wizard"
            style="height:40px;padding:0 24px;font-size:14px">
            生成ウィザードへ →
          </button>
        </div>`;
      }
      if (outputsEl) outputsEl.innerHTML = '';
    }
    document.querySelectorAll('.qa-empty-goto-wizard').forEach(btn => {
      btn.addEventListener('click', () => {
        const addSiteButton = document.getElementById('add-site-btn');
        if (addSiteButton) addSiteButton.click();
      });
    });
  } catch (e) {
    setQaToolStatus(viewName, 'サイト一覧の読み込みに失敗しました。', true);
  }
}

async function loadQaToolData(viewName, domain) {
  const cfg = QA_TOOL_CONFIG[viewName];
  if (!cfg) return;
  if (!domain) {
    const emptyMsgs = {
      'qa-quality': ['品質観点レポート', '境界値・アクセシビリティ・セキュリティ等6観点でテスト観点を整理します'],
    };
    const [title, desc] = emptyMsgs[viewName] || ['データなし', 'サイトを選択してください'];
    document.getElementById(cfg.content).innerHTML = `<div class="qa-empty-state"><div class="qa-empty-icon">📋</div><div class="qa-empty-title">${escHtml(title)}</div><div class="qa-empty-desc">${escHtml(desc)}</div></div>`;
    document.getElementById(cfg.outputs).innerHTML = '';
    setQaToolStatus(viewName, '');
    return;
  }
  setQaToolStatus(viewName, 'QA拡張データを読み込んでいます。');
  try {
    const res = await fetch('/api/qa-process/advanced?domain=' + encodeURIComponent(domain));
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'QA拡張データを取得できませんでした');
    cfg.render(data);
    renderQaToolOutputLinks(cfg.outputs, data.outputs || {}, viewName);
    setQaToolStatus(viewName, '読み込みました。');
  } catch (e) {
    document.getElementById(cfg.content).innerHTML = `<div class="empty">${escHtml(e.message)}</div>`;
    setQaToolStatus(viewName, e.message, true);
  }
}

async function generateQaAdvanced(viewName) {
  const cfg = QA_TOOL_CONFIG[viewName];
  if (!cfg) return;
  const domain = document.getElementById(cfg.select).value;
  if (!domain) { setQaToolStatus(viewName, '対象サイトを選択してください。', true); return; }
  setQaToolStatus(viewName, '成果物を生成しています。外部LLM/APIは呼び出しません。');
  try {
    const res = await fetch('/api/qa-process/generate-advanced', {
      method: 'POST',
      body: new URLSearchParams({ domain }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '生成に失敗しました');
    cfg.render(data.advanced || {});
    renderQaToolOutputLinks(cfg.outputs, data.outputs || {}, viewName);
    setQaToolStatus(viewName, '成果物を生成しました。外部LLM/APIは呼び出していません。');
    // C: 生成後はコンテンツエリア先頭へスクロール
    const contentEl = document.getElementById(cfg.content);
    if (contentEl) setTimeout(() => contentEl.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80);
  } catch (e) {
    setQaToolStatus(viewName, e.message, true);
  }
}

function setQaToolStatus(viewName, message, isError) {
  const cfg = QA_TOOL_CONFIG[viewName];
  if (!cfg) return;
  const el = document.getElementById(cfg.status);
  if (!el) return;
  el.textContent = message || '';
  el.classList.toggle('input-field-message-error', !!isError);
}

function renderQaToolOutputLinks(containerId, outputs, viewName) {
  // B: サイドバー用コンパクト成果物リスト（プレビューボタン、別ウィンドウ廃止）
  const keys = ['quality_viewpoints', 'quality_viewpoints_html'];
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = keys.map(key => {
    const path = outputs[key];
    const label = QA_TOOL_LABELS[key] || key;
    if (!path) {
      return `<div class="qa-output-item is-missing">` +
        `<span class="qa-output-item-name" title="${escHtml(label)}">${escHtml(label)}</span>` +
        `<span style="font-size:11px;color:var(--text-muted)">未生成</span>` +
        `</div>`;
    }
    return `<div class="qa-output-item">` +
      `<span class="qa-output-item-name" title="${escHtml(label)}">${escHtml(label)}</span>` +
      `<div class="qa-output-item-actions">` +
      `<button class="qa-output-btn qa-preview-btn" data-path="${escHtml(path)}" data-label="${escHtml(label)}">プレビュー</button>` +
      `<a class="qa-output-btn" href="/download?path=${encodeURIComponent(path)}" download>DL</a>` +
      `</div></div>`;
  }).join('');
}

function sourceBadge(source) {
  if (source === 'openai') {
    return '<span style="display:inline-block;padding:1px 7px;border-radius:10px;font-size:11px;font-weight:700;background:var(--info-bg,#e8f4fd);color:var(--primary-dark,#1a56db);white-space:nowrap">✨ AI補完</span>';
  }
  return '<span style="display:inline-block;padding:1px 7px;border-radius:10px;font-size:11px;font-weight:700;background:var(--surface,#f4f5f7);color:var(--text-muted,#666);white-space:nowrap">⚙️ 決定的</span>';
}

function renderQaModelTool(data) {
  const graph = data.transition_graph || {};
  const metrics = data.coverage_metrics || {};
  const nodes = graph.nodes || [];
  const edges = graph.edges || [];
  const rates = metrics.rates || {};
  const rateCards = Object.entries(rates).map(([key, value]) =>
    `<div class="qa-metric-card"><strong>${escHtml(metricLabel(key))}</strong><span>${escHtml(value)}%</span><div class="qa-meter"><i style="width:${Math.max(0, Math.min(100, Number(value) || 0))}%"></i></div></div>`
  ).join('');
  const nodeRows = nodes.map(node => `<tr><td class="qa-trace">${escHtml(node.id)}</td><td>${escHtml(node.title)}</td><td>${escHtml(node.url)}</td><td class="num">${node.forms}</td><td class="num">${node.fields}</td><td class="num">${node.required}</td><td class="num">${node.risk_score}</td></tr>`).join('');
  const edgeRows = edges.map(edge => `<tr><td class="qa-trace">${escHtml(edge.trace_id)}</td><td>${escHtml(edge.from)}</td><td>${escHtml(edge.to)}</td><td>${escHtml(edge.label)}</td></tr>`).join('');
  const gates = (metrics.review_gates || []).map(g => `<div class="qa-mini-card"><strong>${escHtml(g.gate)}</strong><span>${escHtml(g.status)}${g.count !== undefined ? ' / ' + escHtml(g.count) + '件' : ''}</span></div>`).join('');
  document.getElementById('qa-model-content').innerHTML =
    `<div class="qa-metric-grid">${rateCards}</div>` +
    `<div class="qa-readable-section"><h3>レビューゲート</h3><div class="qa-card-grid">${gates || '<div class="empty">ゲートがありません。</div>'}</div></div>` +
    `<div class="qa-readable-section"><h3>画面ノード</h3><table class="data"><thead><tr><th>画面ID</th><th>画面</th><th>URL</th><th class="num">フォーム</th><th class="num">入力</th><th class="num">必須</th><th class="num">リスク</th></tr></thead><tbody>${nodeRows || '<tr><td colspan="7">画面がありません</td></tr>'}</tbody></table></div>` +
    `<div class="qa-readable-section"><h3>遷移エッジ</h3><table class="data"><thead><tr><th>Trace</th><th>From</th><th>To</th><th>種別</th></tr></thead><tbody>${edgeRows || '<tr><td colspan="4">遷移がありません</td></tr>'}</tbody></table></div>`;
  if (typeof wrapTraceTerms === 'function') wrapTraceTerms(document.getElementById('qa-model-content'));
}

function renderQaAutomationTool(data) {
  const pw = data.playwright_candidates || {};
  const rows = (pw.candidates || []).map(item =>
    `<tr><td class="qa-trace">${escHtml(item.id)}</td><td>${escHtml(item.title)} ${sourceBadge(item.source || 'rules')}</td><td class="qa-trace">${escHtml(item.trace_id)}</td><td>${escHtml(item.automation_status)}</td><td>${escHtml(item.expected)}</td><td>${escHtml(item.locator_strategy)}</td></tr>`
  ).join('');
  const policies = (pw.locator_policy || []).map(p => `<span class="fmt-badge">${escHtml(p)}</span>`).join('');
  document.getElementById('qa-auto-content').innerHTML =
    `<div class="qa-readable-section"><h3>ロケータ方針</h3><div class="fmt-badges">${policies}</div><p class="input-hint">${escHtml(pw.execution_policy || '')}</p></div>` +
    `<div class="qa-readable-section"><h3>候補一覧</h3><table class="data"><thead><tr><th>ID</th><th>タイトル</th><th>Trace${infoTip('この候補が根拠とする画面・遷移のID。画面遷移タブの同じIDと対応します。')}</th><th>状態${infoTip('自動テストとして実行可能か（auto）／人手確認が必要か（manual）を示します。')}</th><th>期待結果</th><th>ロケータ方針${infoTip('要素をどう特定してテストを組み立てるかの方針（例: data-testid優先）。')}</th></tr></thead><tbody>${rows || '<tr><td colspan="6">候補がありません</td></tr>'}</tbody></table></div>`;
  if (typeof wrapTraceTerms === 'function') wrapTraceTerms(document.getElementById('qa-auto-content'));
}

function renderQaQualityTool(data) {
  const quality = data.quality_viewpoints || {};
  const grouped = {};
  for (const item of quality.items || []) {
    const key = item.category || 'その他';
    grouped[key] = grouped[key] || [];
    grouped[key].push(item);
  }
  const sections = Object.entries(grouped).map(([category, items]) => {
    const rows = items.map(item => `<tr><td class="qa-trace">${escHtml(item.id)}</td><td>${escHtml(item.viewpoint)} ${sourceBadge(item.source || 'rules')}</td><td>${escHtml(item.trigger)}</td><td>${escHtml(item.recommendation)}</td><td>${escHtml(item.automation)}</td><td class="qa-trace">${escHtml(item.trace_id)}</td></tr>`).join('');
    return `<div class="qa-readable-section"><h3>${escHtml(category)}</h3><table class="data"><thead><tr><th>ID</th><th>観点</th><th>発火条件${infoTip('この観点をテストで確認すべきタイミング・状況（例: 必須項目が未入力のとき）。')}</th><th>推奨確認${infoTip('確認すべき挙動・表示内容の推奨事項。')}</th><th>自動化${infoTip('自動テスト化しやすいか（自動）／人手での確認が必要か（手動）の目安。')}</th><th>Trace${infoTip('この観点が根拠とする画面・要件のID。')}</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }).join('');
  const risks = (quality.screen_risks || []).map(risk => `<tr><td class="qa-trace">${escHtml(risk.screen_id)}</td><td>${escHtml(risk.title)}</td><td class="num">${escHtml(risk.risk_score)}</td><td>${escHtml((risk.reasons || []).join(' / '))}</td></tr>`).join('');
  document.getElementById('qa-quality-content').innerHTML =
    `<div class="qa-readable-section"><h3>画面リスク</h3><table class="data"><thead><tr><th>画面ID</th><th>画面</th><th class="num">リスク</th><th>理由</th></tr></thead><tbody>${risks || '<tr><td colspan="4">画面がありません</td></tr>'}</tbody></table></div>` +
    (sections || '<div class="empty">品質観点がありません。</div>') +
    `<div class="qa-readable-section"><h3>質問待ち</h3><ul class="qa-check-list qa-question-list">${qaList(quality.questions)}</ul></div>`;
  if (typeof wrapTraceTerms === 'function') wrapTraceTerms(document.getElementById('qa-quality-content'));
}

function metricLabel(key) {
  return ({
    screen_trace_rate: '画面Trace率',
    field_trace_rate: '入力Trace率',
    transition_trace_rate: '遷移Trace率',
    operation_trace_rate: '操作Trace率',
    required_field_rate: '必須項目率',
  })[key] || key;
}

document.querySelectorAll('.qa-tool-domain').forEach(select => {
  select.addEventListener('change', () => {
    const viewName = Object.keys(QA_TOOL_CONFIG).find(name => QA_TOOL_CONFIG[name].select === select.id);
    loadQaToolData(viewName, select.value);
  });
});
document.querySelectorAll('.qa-tool-reload').forEach(btn => {
  btn.addEventListener('click', () => {
    qaToolSitesLoaded = false;
    const view = document.querySelector('.view.is-active');
    const viewName = view ? view.id.replace('view-', '') : 'qa-quality';
    loadQaToolSites(viewName, true);
  });
});
document.getElementById('qa-quality-generate').addEventListener('click', () => generateQaAdvanced('qa-quality'));
