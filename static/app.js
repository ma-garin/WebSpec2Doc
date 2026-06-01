
const SETTINGS_KEY = 'webspec2doc.settings';
const VIEW_HEADER = {
  dashboard: { trail: ['ダッシュボード'], title: '監視対象サイト' },
  generate: { trail: ['ダッシュボード', 'サイトを追加'], title: 'サイトを追加 / 再クロール' },
  'qa-process': { trail: ['ダッシュボード', 'QAプロセス'], title: 'QAプロセス' },
  'qa-models': { trail: ['ダッシュボード', 'モデル/カバレッジ'], title: 'モデル/カバレッジ' },
  'qa-automation': { trail: ['ダッシュボード', '自動テスト候補'], title: '自動テスト候補' },
  'qa-quality': { trail: ['ダッシュボード', '品質観点'], title: '品質観点' },
  'auto-run': { trail: ['ダッシュボード', 'AutoRun'], title: 'AutoRun — 全自動テスト実行' },
  'user-guide': { trail: ['ダッシュボード', 'ユーザーガイド'], title: 'ユーザーガイド' },
  settings: { trail: ['ダッシュボード', '設定'], title: '設定' },
};
const escHtml = (s) => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// ---- ヘッダー（パンくず＋タイトル）----
function setHeader(trail, title) {
  const bc = document.getElementById('topbar-breadcrumb');
  bc.innerHTML = trail.map((t, i) => i === 0
    ? `<a data-bc-root="1">${escHtml(t)}</a>`
    : `<span class="sep">›</span><span>${escHtml(t)}</span>`).join('');
  const root = bc.querySelector('[data-bc-root]');
  if (root && trail.length > 1) root.addEventListener('click', () => switchView('dashboard'));
  document.getElementById('topbar-title').textContent = title;
  document.getElementById('topbar-actions').innerHTML = '';
}

// ---- ナビ切替 ----
document.querySelectorAll('.app-nav-item').forEach(btn => btn.addEventListener('click', () => switchView(btn.dataset.view)));
function switchView(name) {
  document.querySelectorAll('.app-nav-item').forEach(b => b.classList.toggle('is-active', b.dataset.view === name));
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('is-active', v.id === 'view-' + name));
  const h = VIEW_HEADER[name];
  if (h) setHeader(h.trail, h.title);
  if (name === 'dashboard') loadHistory();
  if (name === 'qa-process') loadQaProcessSites();
  if (['qa-models', 'qa-automation', 'qa-quality'].includes(name)) loadQaToolSites(name);
  // A: 2ペインツール画面では全高モードに切り替え
  const appContentEl = document.getElementById('app-content');
  if (appContentEl) appContentEl.classList.toggle('is-qa-tool', ['qa-models', 'qa-automation', 'qa-quality', 'auto-run'].includes(name));
}
// ---- ウィザード ステップ管理 ----
function showWizardStep(n) {
  const p1 = document.getElementById('wizard-p1');
  const p2 = document.getElementById('wizard-p2');
  const bar = document.getElementById('wizard-progress-bar');
  if (p1) p1.style.display = (n === 1) ? '' : 'none';
  if (p2) p2.style.display = (n === 2) ? '' : 'none';
  if (bar) bar.style.display = '';
  [1, 2, 3, 4].forEach(i => {
    const node = document.getElementById('ws-' + i);
    if (!node) return;
    node.classList.toggle('is-active', i === n);
    node.classList.toggle('is-done', i < n);
  });
  [1, 2, 3].forEach(i => {
    const line = document.getElementById('wl-' + i);
    if (line) line.classList.toggle('is-done', i < n);
  });
}

// 「+ サイトを追加」: 新規ウィザードを開く（P1から）
function openAddSite() {
  switchView('generate');
  executionView.classList.add('hidden'); resultPanel.classList.add('hidden');
  appContent.classList.remove('is-executing'); genPanel.style.display = '';
  document.getElementById('url-input').value = '';
  document.getElementById('p1-summary').style.display = 'none';
  clearDiscovered(); updateTargetPreview(); showWizardStep(1);
}
document.getElementById('add-site-btn').addEventListener('click', openAddSite);
document.getElementById('add-site-btn-2').addEventListener('click', openAddSite);

// P1 → P2: 「次へ」ボタン
document.getElementById('p1-next-btn').addEventListener('click', () => {
  showWizardStep(2);
  // 画面リストと必要なら認証パネルを表示
  if (discovered.length) {
    document.getElementById('discovered-url-panel').style.display = '';
    updateTargetPreview();
  }
});

// P2 → P1: 「解析に戻る」ボタン
document.getElementById('p2-back-btn').addEventListener('click', () => {
  showWizardStep(1);
});

// ---- 設定（localStorage）----
function getSettings() { try { return JSON.parse(localStorage.getItem(SETTINGS_KEY)) || {}; } catch { return {}; } }
function applySettings() {
  const s = getSettings();
  // crawl-depth / max-pages は MAX 固定（hidden input）のため上書きしない
  if (s.auth) document.getElementById('auth-path').value = s.auth;
}
function loadSettingsForm() {
  const s = getSettings();
  document.getElementById('set-depth').value = s.depth || 2;
  document.getElementById('set-max').value = s.maxPages || 30;
  document.getElementById('set-auth').value = s.auth || '';
}
document.getElementById('save-settings').addEventListener('click', () => {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify({
    depth: document.getElementById('set-depth').value,
    maxPages: document.getElementById('set-max').value,
    auth: document.getElementById('set-auth').value.trim(),
  }));
  applySettings();
  const msg = document.getElementById('settings-msg'); msg.classList.add('show');
  setTimeout(() => msg.classList.remove('show'), 2000);
});

// ---- 履歴 ----
async function loadHistory() {
  const body = document.getElementById('history-body');
  body.innerHTML = '<div class="empty">読み込み中...</div>';
  try {
    const res = await fetch('/api/history');
    const data = await res.json();
    if (!data.items.length) { body.innerHTML = '<div class="empty">まだ監視対象がありません。「+ サイトを追加」から最初のサイトをクロールしてください。</div>'; return; }
    let html = '<table class="data"><thead><tr><th>サイト</th><th class="num">画面数</th><th class="num">入力項目</th><th>形式</th><th>最終クロール</th><th>操作</th></tr></thead><tbody>';
    for (const it of data.items) {
      const badges = (it.formats || []).map(f => `<span class="fmt-badge">${escHtml(f)}</span>`).join('');
      html += `<tr><td><strong>${escHtml(it.domain)}</strong></td><td class="num">${it.screens}</td><td class="num">${it.fields}</td>` +
        `<td><div class="fmt-badges">${badges || '—'}</div></td><td>${escHtml(it.updated)}</td>` +
        `<td><div class="history-actions">` +
        `<button type="button" class="btn-outline-sm hist-recrawl" data-domain="${escHtml(it.domain)}">再クロール</button>` +
        `<button type="button" class="btn-primary hist-open" data-domain="${escHtml(it.domain)}" style="height:36px;padding:0 14px;font-size:13px">開く</button>` +
        `</div></td></tr>`;
    }
    html += '</tbody></table>';
    body.innerHTML = html;
    body.querySelectorAll('.hist-open').forEach(b => b.addEventListener('click', () => openResultsForDomain(b.dataset.domain)));
    body.querySelectorAll('.hist-recrawl').forEach(b => b.addEventListener('click', () => recrawlSite(b.dataset.domain)));
  } catch (e) { body.innerHTML = '<div class="empty">サイト一覧の読み込みに失敗しました。</div>'; }
}
document.getElementById('reload-history').addEventListener('click', loadHistory);

// ---- QAプロセス ----
const QA_STEP_LABELS = {
  test_plan: 'テスト計画',
  test_analysis: 'テスト分析',
  test_design: 'テスト設計',
  test_cases: 'テストケース',
  cross_review: '横断レビュー',
  qa_process_report: 'QAプロセスレポート',
  screen_transition_graph: '画面遷移グラフJSON',
  model_graph: 'モデルグラフHTML',
  coverage_metrics: 'カバレッジメトリクス',
  playwright_candidates: 'Playwright候補JSON',
  playwright_candidates_html: 'Playwright候補HTML',
  quality_viewpoints: '品質観点JSON',
  quality_viewpoints_html: '品質観点HTML',
};
const QA_PAGES = [
  { title: '対象サイト選択' },
  { title: '入力仕様サマリー' },
  { title: 'テスト計画', step: 'test_plan' },
  { title: 'テスト分析', step: 'test_analysis' },
  { title: 'テスト設計', step: 'test_design' },
  { title: 'テストケース', step: 'test_cases' },
  { title: '横断レビュー / レポート', step: 'qa_process_report' },
];
let qaLoadedSites = false;
let qaActiveDomain = '';
let qaInputData = null;
let qaCurrentPage = 0;
let qaOutputs = {};
let qaAiArtifact = null;
let qaAiStatus = {};
let qaViewpoints = [];
const qaGeneratedSteps = new Set(); // D: 生成済みステップ追跡

async function loadQaProcessSites(force) {
  const select = document.getElementById('qa-domain-select');
  if (!select) return;
  if (qaLoadedSites && !force) return;
  const previous = select.value;
  setQaStatus('解析済みサイトを読み込んでいます。');
  try {
    const res = await fetch('/api/history');
    const data = await res.json();
    const items = data.items || [];
    select.innerHTML = '<option value="">解析済みサイトを選択</option>' +
      items.map(it => `<option value="${escHtml(it.domain)}">${escHtml(it.domain)}</option>`).join('');
    if (previous && items.some(it => it.domain === previous)) select.value = previous;
    qaLoadedSites = true;
    setQaStatus(items.length ? '対象サイトを選択してください。' : '解析済みサイトがありません。先にサイトを追加してください。');
    if (select.value) await loadQaProcessInput(select.value);
  } catch (e) {
    setQaStatus('サイト一覧の読み込みに失敗しました。', true);
  }
}

async function loadQaProcessInput(domain) {
  qaActiveDomain = domain;
  qaInputData = null;
  qaOutputs = {};
  qaAiArtifact = null;
  qaAiStatus = {};
  qaViewpoints = [];
  qaGeneratedSteps.clear(); // D: リセット
  renderQaOutputLinks({});
  renderQaReadablePages(null);
  if (!domain) {
    document.getElementById('qa-input-summary').innerHTML = '<div class="empty">対象サイトを選択してください。</div>';
    qaCurrentPage = 0;
    updateQaWizard();
    return;
  }
  try {
    setQaStatus('入力仕様を読み込んでいます。');
    const res = await fetch('/api/qa-process/input?domain=' + encodeURIComponent(domain));
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '入力仕様の取得に失敗しました');
    qaInputData = data;
    qaOutputs = data.outputs || {};
    qaAiArtifact = data.ai_artifact || null;
    qaAiStatus = data.ai || {};
    qaViewpoints = data.viewpoints || [];
    // D: 既存成果物からステップを事前反映
    Object.entries(qaOutputs).forEach(([key, path]) => { if (path) qaGeneratedSteps.add(key); });
    renderQaInputSummary(data);
    renderQaReadablePages(data);
    renderQaOutputLinks(qaOutputs);
    qaCurrentPage = 1;
    updateQaWizard();
    setQaStatus('入力仕様を読み込みました。');
  } catch (e) {
    qaActiveDomain = '';
    qaCurrentPage = 0;
    document.getElementById('qa-input-summary').innerHTML = `<div class="empty">QAプロセス入力を読み込めません。${escHtml(e.message)}</div>`;
    renderQaReadablePages(null);
    updateQaWizard();
    setQaStatus(e.message, true);
  }
}

function renderQaInputSummary(data) {
  const s = data.summary || {};
  const files = data.input_files || {};
  const viewpoints = data.viewpoints || [];
  const fileBadge = (label, path) => `<span class="fmt-badge">${escHtml(label)}: ${path ? 'あり' : 'なし'}</span>`;
  const vpBadge = viewpoints.slice(0, 8).map(vp => `<span class="fmt-badge">${escHtml(vp.name)} ${escHtml(vp.count || 0)}</span>`).join('');
  const screenRows = (data.screens || []).map(sc => (
    `<tr><td><strong>${escHtml(sc.page_id || '')}</strong></td><td>${escHtml(sc.title || '')}</td>` +
    `<td class="num">${sc.forms || 0}</td><td class="num">${sc.fields || 0}</td><td class="num">${sc.required || 0}</td>` +
    `<td class="num">${sc.buttons || 0}</td></tr>`
  )).join('');
  document.getElementById('qa-input-summary').innerHTML =
    `<div class="result-stats" style="margin-bottom:14px">` +
    `<div><span class="num">${s.screens || 0}</span><span>画面数</span></div>` +
    `<div><span class="num">${s.forms || 0}</span><span>フォーム数</span></div>` +
    `<div><span class="num">${s.fields || 0}</span><span>入力項目数</span></div>` +
    `<div><span class="num">${s.required || 0}</span><span>必須項目数</span></div>` +
    `<div><span class="num">${s.buttons || 0}</span><span>操作要素数</span></div>` +
    `</div>` +
    `<div class="fmt-badges" style="margin-bottom:12px">${fileBadge('report.json', files.report_json)}${fileBadge('spec.xlsx', files.spec_excel)}${fileBadge('report.html', files.report_html)}</div>` +
    `<div class="qa-readable-section" style="margin-bottom:12px"><h3>参考QA観点CSV</h3><div class="fmt-badges">${vpBadge || '<span class="fmt-badge">未設定</span>'}</div></div>` +
    `<table class="data"><thead><tr><th>画面ID</th><th>画面</th><th class="num">フォーム</th><th class="num">入力</th><th class="num">必須</th><th class="num">操作</th></tr></thead><tbody>` +
    (screenRows || '<tr><td colspan="6" style="color:var(--text-muted)">画面がありません</td></tr>') +
    `</tbody></table>`;
}

function renderQaOutputLinks(outputs) {
  // ウィザードステップ7の成果物リスト（B: プレビューボタン、D: 常時表示）
  const basicSteps = [
    ['test_plan', 'テスト計画'], ['test_analysis', 'テスト分析'], ['test_design', 'テスト設計'],
    ['test_cases', 'テストケース'], ['cross_review', '横断レビュー'], ['qa_process_report', 'QAプロセスレポート'],
  ];
  const advancedSteps = [
    ['screen_transition_graph', '遷移グラフJSON'], ['model_graph', 'モデルグラフHTML'],
    ['coverage_metrics', 'カバレッジJSON'], ['playwright_candidates', 'Playwright候補JSON'],
    ['playwright_candidates_html', 'Playwright候補HTML'], ['quality_viewpoints', '品質観点JSON'],
    ['quality_viewpoints_html', '品質観点HTML'],
  ];
  const makeRow = ([key, label]) => {
    const path = outputs[key];
    if (!path) return `<div class="qa-output-row"><div class="qa-output-row-name"><strong>${escHtml(label)}</strong><span>未生成</span></div></div>`;
    const shortPath = path.split('/').slice(-2).join('/');
    return `<div class="qa-output-row is-ready">` +
      `<div class="qa-output-row-name"><strong>${escHtml(label)}</strong><span>${escHtml(shortPath)}</span></div>` +
      `<div class="qa-output-row-actions">` +
      `<button class="btn-outline-sm qa-preview-btn" data-path="${escHtml(path)}" data-label="${escHtml(label)}" style="font-size:12px;height:28px;padding:0 10px">プレビュー</button>` +
      `<a class="btn-outline-sm" href="/download?path=${encodeURIComponent(path)}" download style="font-size:12px;height:28px;padding:0 10px">DL</a>` +
      `</div></div>`;
  };
  const el = document.getElementById('qa-output-links');
  if (!el) return;
  el.innerHTML = basicSteps.map(makeRow).join('') +
    (Object.values(outputs).some(Boolean) ? '<div class="hero-section-title" style="margin:14px 0 8px">高度QA成果物</div>' + advancedSteps.map(makeRow).join('') : '');
}

async function generateQaProcess(step) {
  const domain = document.getElementById('qa-domain-select').value;
  if (!domain) { setQaStatus('対象サイトを選択してください。', true); return; }
  const useAi = !!document.getElementById('qa-use-ai')?.checked;
  setQaStatus(`${QA_STEP_LABELS[step] || '全ステップ'}を生成しています。${useAi ? 'OpenAI APIで補完します。' : 'ローカルテンプレートで生成します。'}`);
  try {
    const res = await fetch('/api/qa-process/generate', {
      method: 'POST',
      body: new URLSearchParams({ domain, step, use_ai: useAi ? 'true' : 'false' }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '生成に失敗しました');
    qaOutputs = data.outputs || {};
    qaAiArtifact = data.ai_artifact || null;
    qaAiStatus = data.ai || {};
    // D: 全ステップを生成済みとしてマーク（APIは常に全成果物を生成する）
    ['test_plan', 'test_analysis', 'test_design', 'test_cases', 'cross_review', 'qa_process_report'].forEach(s => qaGeneratedSteps.add(s));
    renderQaOutputLinks(qaOutputs);
    renderQaReadablePages(qaInputData);
    if (qaAiStatus.used) {
      setQaStatus(`QAプロセス成果物を生成しました。OpenAI API補完を使用しました。${qaAiStatus.model ? 'Model: ' + qaAiStatus.model : ''}`);
    } else if (qaAiStatus.fallback) {
      setQaStatus(`QAプロセス成果物を生成しました。OpenAI補完は使えずローカル生成に切り替えました。${qaAiStatus.error || ''}`, true);
    } else {
      setQaStatus('QAプロセス成果物を生成しました。外部LLM APIは呼び出していません。');
    }
    // C: 全成果物生成後はレポートステップへ自動遷移
    if (step === 'qa_process_report') {
      qaCurrentPage = QA_PAGES.length - 1;
    }
    updateQaWizard();
    // C: ウィザードカードの先頭へスクロールして成果物リンクを見せる
    if (step === 'qa_process_report') {
      const wizardEl = document.querySelector('#view-qa-process .input-card');
      if (wizardEl) wizardEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  } catch (e) {
    setQaStatus(e.message, true);
  }
}

function setQaStatus(message, isError) {
  const el = document.getElementById('qa-status');
  if (!el) return;
  el.textContent = message || '';
  el.classList.toggle('input-field-message-error', !!isError);
}

// D/C: ページ番号→ステップキーのマッピング
const QA_PAGE_STEP_KEY = [null, null, 'test_plan', 'test_analysis', 'test_design', 'test_cases', 'qa_process_report'];

function updateQaWizard() {
  document.querySelectorAll('[data-qa-page-panel]').forEach(panel => {
    panel.classList.toggle('is-active', Number(panel.dataset.qaPagePanel) === qaCurrentPage);
  });
  document.querySelectorAll('.qa-step-dot').forEach(dot => {
    const page = Number(dot.dataset.qaPage);
    const stepKey = QA_PAGE_STEP_KEY[page];
    const isDone = page < qaCurrentPage || (stepKey && qaGeneratedSteps.has(stepKey));
    dot.classList.toggle('is-active', page === qaCurrentPage);
    dot.classList.toggle('is-done', !!isDone);
  });
  const prev = document.getElementById('qa-prev');
  const next = document.getElementById('qa-next');
  if (prev) prev.disabled = qaCurrentPage === 0;
  if (next) {
    next.textContent = qaCurrentPage === QA_PAGES.length - 1 ? '完了' : '次へ';
    next.disabled = qaCurrentPage === 0 && !qaActiveDomain;
  }
}

function renderQaReadablePages(data) {
  document.getElementById('qa-step-test-plan').innerHTML = data ? renderQaPlan(data) : qaEmptyStep();
  document.getElementById('qa-step-test-analysis').innerHTML = data ? renderQaAnalysis(data) : qaEmptyStep();
  document.getElementById('qa-step-test-design').innerHTML = data ? renderQaDesign(data) : qaEmptyStep();
  document.getElementById('qa-step-test-cases').innerHTML = data ? renderQaCases(data) : qaEmptyStep();
  document.getElementById('qa-step-report').innerHTML = data ? renderQaReview(data) : qaEmptyStep();
}

function qaEmptyStep() {
  return '<div class="empty">先に対象サイトを選択してください。</div>';
}

function qaScreens(data) {
  return data && Array.isArray(data.screens) ? data.screens : [];
}

function qaSummary(data) {
  return (data && data.summary) || {};
}

function qaAllFieldRows(data) {
  const rows = [];
  for (const sc of qaScreens(data)) {
    for (let formIdx = 0; formIdx < (sc.raw_forms || []).length; formIdx++) {
      const form = sc.raw_forms[formIdx];
      for (let fieldIdx = 0; fieldIdx < (form.fields || []).length; fieldIdx++) {
        rows.push({ screen: sc, form, field: form.fields[fieldIdx], formIdx: formIdx + 1, fieldIdx: fieldIdx + 1 });
      }
    }
  }
  return rows;
}

function traceId(screen, formIdx, fieldIdx) {
  return `${screen.page_id || 'P???'}-F${String(formIdx).padStart(2, '0')}-I${String(fieldIdx).padStart(2, '0')}`;
}

function qaArtifact() {
  return qaAiArtifact && typeof qaAiArtifact === 'object' ? qaAiArtifact : null;
}

function qaList(items, question) {
  const rows = Array.isArray(items) && items.length ? items : [question || '質問待ち'];
  return rows.map(item => `<li>${escHtml(item)}</li>`).join('');
}

function qaViewpointCards(limit) {
  const rows = (qaViewpoints || []).slice(0, limit || 8);
  if (!rows.length) return '<div class="empty">参考QA観点CSVがありません。</div>';
  return `<div class="qa-card-grid">${rows.map(vp => `<div class="qa-mini-card"><strong>${escHtml(vp.name)}</strong><span>${escHtml(vp.summary_type)} / ${escHtml(vp.count || 0)}件</span></div>`).join('')}</div>`;
}

function renderAiBadge() {
  if (!qaArtifact()) return '';
  return `<div class="qa-readable-section"><h3>生成方式</h3><div class="fmt-badges"><span class="fmt-badge">OpenAI API補完</span><span class="fmt-badge">構造化JSON</span><span class="fmt-badge">${escHtml(qaAiStatus.model || qaAiArtifact.model || '')}</span></div></div>`;
}

function renderQaPlan(data) {
  const artifact = qaArtifact();
  if (artifact && artifact.test_plan) {
    const p = artifact.test_plan;
    return renderAiBadge() +
      `<div class="qa-readable-section"><h3>スコープ</h3><ul class="qa-check-list">${qaList(p.scope)}</ul></div>` +
      `<div class="qa-readable-section"><h3>テストレベル</h3><ul class="qa-check-list">${qaList(p.levels)}</ul></div>` +
      `<div class="qa-readable-section"><h3>リスク</h3><ul class="qa-check-list">${qaList(p.risks)}</ul></div>` +
      `<div class="qa-readable-section"><h3>Entry / Exit Criteria</h3><div class="qa-card-grid"><div class="qa-mini-card"><strong>Entry</strong><span>${escHtml((p.entry_criteria || []).join(' / ') || '質問待ち')}</span></div><div class="qa-mini-card"><strong>Exit</strong><span>${escHtml((p.exit_criteria || []).join(' / ') || '質問待ち')}</span></div></div></div>` +
      `<div class="qa-readable-section"><h3>質問待ち</h3><ul class="qa-check-list qa-question-list">${qaList(p.questions)}</ul></div>` +
      `<div class="qa-readable-section"><h3>参考QA観点CSV</h3>${qaViewpointCards(8)}</div>`;
  }
  const s = qaSummary(data);
  return `<div class="result-stats">` +
    `<div><span class="num">${s.screens || 0}</span><span>画面</span></div>` +
    `<div><span class="num">${s.forms || 0}</span><span>フォーム</span></div>` +
    `<div><span class="num">${s.fields || 0}</span><span>入力項目</span></div>` +
    `<div><span class="num">${s.required || 0}</span><span>必須</span></div>` +
    `<div><span class="num">${s.buttons || 0}</span><span>操作要素</span></div>` +
    `</div>` +
    `<div class="qa-readable-section"><h3>テストレベル</h3><ul class="qa-check-list">` +
    `<li>画面仕様確認</li><li>入力バリデーション確認</li><li>画面遷移確認</li><li>操作要素の表示・到達性確認</li>` +
    `</ul></div>` +
    `<div class="qa-readable-section"><h3>質問待ち</h3><ul class="qa-check-list qa-question-list">` +
    `<li>サポート対象ブラウザとデバイス条件</li><li>認証・権限ロール別の期待結果</li><li>外部連携、メール送信、決済など副作用を伴う処理の扱い</li><li>リリース判定基準と優先度付け</li>` +
    `</ul></div>` +
    `<div class="qa-readable-section"><h3>参考QA観点CSV</h3>${qaViewpointCards(8)}</div>`;
}

function renderQaAnalysis(data) {
  const artifact = qaArtifact();
  if (artifact && artifact.test_analysis) {
    const a = artifact.test_analysis;
    const inventory = (a.source_inventory || []).map(item => `<tr><td class="qa-trace">${escHtml(item.screen_id || '')}</td><td>${escHtml(item.title || '')}</td><td>${escHtml((item.observations || []).join(' / '))}</td><td>${escHtml(item.risk || '')}</td><td class="qa-trace">${escHtml(item.trace_id || '')}</td></tr>`).join('');
    const risks = (a.risk_items || []).map(item => `<tr><td class="qa-trace">${escHtml(item.risk_id || '')}</td><td>${escHtml(item.description || '')}</td><td>${escHtml(item.impact || '')}</td><td class="qa-trace">${escHtml(item.trace_id || '')}</td></tr>`).join('');
    return renderAiBadge() +
      `<div class="qa-readable-section"><h3>Source Structure Inventory</h3><table class="data"><thead><tr><th>画面ID</th><th>画面</th><th>観察事項</th><th>リスク</th><th>Trace</th></tr></thead><tbody>${inventory || '<tr><td colspan="5">分析対象がありません</td></tr>'}</tbody></table></div>` +
      `<div class="qa-readable-section"><h3>Risk Items</h3><table class="data"><thead><tr><th>リスクID</th><th>内容</th><th>影響</th><th>Trace</th></tr></thead><tbody>${risks || '<tr><td colspan="4">リスクがありません</td></tr>'}</tbody></table></div>` +
      `<div class="qa-readable-section"><h3>質問待ち</h3><ul class="qa-check-list qa-question-list">${qaList(a.questions)}</ul></div>`;
  }
  const rows = qaScreens(data).map(sc => `<tr><td><strong>${escHtml(sc.page_id || '')}</strong></td><td>${escHtml(sc.title || '')}</td><td class="num">${sc.forms || 0}</td><td class="num">${sc.fields || 0}</td><td class="num">${sc.required || 0}</td><td class="num">${sc.buttons || 0}</td><td>${escHtml((sc.transitions_to || []).join(', ') || '質問待ち')}</td></tr>`).join('');
  return `<div class="qa-readable-section"><h3>画面別の分析</h3><table class="data"><thead><tr><th>画面ID</th><th>画面</th><th class="num">フォーム</th><th class="num">入力</th><th class="num">必須</th><th class="num">操作</th><th>遷移先</th></tr></thead><tbody>${rows || '<tr><td colspan="7">画面がありません</td></tr>'}</tbody></table></div>` +
    `<div class="qa-readable-section"><h3>重点確認ポイント</h3><div class="qa-card-grid">` +
    qaScreens(data).filter(sc => sc.fields || sc.buttons || sc.transitions_to.length).slice(0, 6).map(sc => `<div class="qa-mini-card"><strong>${escHtml(sc.page_id || '')} ${escHtml(sc.title || '')}</strong><span>入力 ${sc.fields || 0} / 必須 ${sc.required || 0} / 操作 ${sc.buttons || 0}</span></div>`).join('') +
    `</div></div>`;
}

function renderQaDesign(data) {
  const artifact = qaArtifact();
  if (artifact && artifact.test_design) {
    const d = artifact.test_design;
    const viewpoints = (d.viewpoints || []).map(item => `<tr><td class="qa-trace">${escHtml(item.viewpoint_id || '')}</td><td>${escHtml(item.target || '')}</td><td>${escHtml(item.technique || '')}</td><td>${escHtml(item.design_note || '')}</td><td class="qa-trace">${escHtml(item.trace_id || '')}</td></tr>`).join('');
    const coverage = (d.coverage_matrix || []).map(item => `<tr><td class="qa-trace">${escHtml(item.trace_id || '')}</td><td>${escHtml(item.covered_by || '')}</td><td>${escHtml(item.coverage_note || '')}</td></tr>`).join('');
    return renderAiBadge() +
      `<div class="qa-readable-section"><h3>設計観点</h3><table class="data"><thead><tr><th>観点ID</th><th>対象</th><th>技法</th><th>設計メモ</th><th>Trace</th></tr></thead><tbody>${viewpoints || '<tr><td colspan="5">設計対象がありません</td></tr>'}</tbody></table></div>` +
      `<div class="qa-readable-section"><h3>Coverage Matrix</h3><table class="data"><thead><tr><th>Trace</th><th>Covered By</th><th>Coverage Note</th></tr></thead><tbody>${coverage || '<tr><td colspan="3">カバレッジ情報がありません</td></tr>'}</tbody></table></div>` +
      `<div class="qa-readable-section"><h3>質問待ち</h3><ul class="qa-check-list qa-question-list">${qaList(d.questions)}</ul></div>`;
  }
  const rows = [];
  for (const sc of qaScreens(data)) {
    rows.push(`<tr><td class="qa-trace">TD-${escHtml(sc.page_id)}-NAV</td><td>${escHtml(sc.title || '')}</td><td>画面遷移</td><td>${escHtml((sc.transitions_to || []).join(', ') || '質問待ち')}</td><td class="qa-trace">${escHtml(sc.page_id || '')}</td></tr>`);
    for (const row of qaAllFieldRows({ screens: [sc] })) {
      const fieldName = row.field.name || row.field.element_id || row.field.placeholder || 'unnamed';
      const cond = (row.field.test_conditions || []).join(' / ') || '仕様から条件を補完する';
      rows.push(`<tr><td class="qa-trace">TD-${escHtml(traceId(row.screen, row.formIdx, row.fieldIdx))}</td><td>${escHtml(fieldName)}</td><td>入力項目</td><td>${escHtml(cond)}</td><td class="qa-trace">${escHtml(traceId(row.screen, row.formIdx, row.fieldIdx))}</td></tr>`);
    }
  }
  return `<div class="qa-readable-section"><h3>設計観点</h3><table class="data"><thead><tr><th>観点ID</th><th>対象</th><th>種別</th><th>設計方針</th><th>元仕様</th></tr></thead><tbody>${rows.join('') || '<tr><td colspan="5">設計対象がありません</td></tr>'}</tbody></table></div>`;
}

function renderQaCases(data) {
  const artifact = qaArtifact();
  if (artifact && artifact.test_cases) {
    const c = artifact.test_cases;
    const cases = (c.cases || []).map(item => `<tr><td class="qa-trace">${escHtml(item.case_id || '')}</td><td>${escHtml(item.title || '')}</td><td>${escHtml((item.steps || []).join(' / '))}</td><td>${escHtml(item.expected || '')}</td><td>${escHtml(item.execution_type || '')}</td><td>${escHtml(item.status || '')}</td><td class="qa-trace">${escHtml(item.trace_id || '')}</td></tr>`).join('');
    return renderAiBadge() +
      `<div class="qa-readable-section"><h3>Expected Case Yield</h3><p>${escHtml(c.expected_case_yield || '質問待ち')}</p></div>` +
      `<div class="qa-readable-section"><h3>Case Expansion Ledger</h3><ul class="qa-check-list">${qaList(c.case_expansion_ledger)}</ul></div>` +
      `<div class="qa-readable-section"><h3>テストケース一覧</h3><table class="data"><thead><tr><th>ケースID</th><th>タイトル</th><th>手順</th><th>期待結果</th><th>実行区分</th><th>状態</th><th>Trace</th></tr></thead><tbody>${cases || '<tr><td colspan="7">ケースがありません</td></tr>'}</tbody></table></div>` +
      `<div class="qa-readable-section"><h3>質問待ち</h3><ul class="qa-check-list qa-question-list">${qaList(c.questions)}</ul></div>`;
  }
  const rows = [];
  let caseNo = 1;
  for (const sc of qaScreens(data)) {
    rows.push(qaCaseRow(caseNo++, '画面表示', `${sc.url || ''} を開く`, `${sc.title || sc.page_id || ''} の画面仕様が表示される`, sc.page_id || ''));
    for (const to of sc.transitions_to || []) rows.push(qaCaseRow(caseNo++, '画面遷移', `${sc.page_id} から ${to} へ遷移する操作を実行`, '遷移先画面へ到達する', `${sc.page_id}->${to}`));
    for (const row of qaAllFieldRows({ screens: [sc] })) {
      const id = traceId(row.screen, row.formIdx, row.fieldIdx);
      const label = row.field.name || row.field.element_id || row.field.placeholder || 'unnamed';
      rows.push(qaCaseRow(caseNo++, '入力', `${label} に代表値を入力`, '入力値が受理される', id));
      if (row.field.required) rows.push(qaCaseRow(caseNo++, '必須', `${label} を未入力にする`, '必須エラーが表示され送信されない', id));
      for (const cond of row.field.test_conditions || []) rows.push(qaCaseRow(caseNo++, '条件', `${label} で ${cond}`, '仕様通りに受理またはエラー表示される', id));
    }
  }
  return `<div class="qa-readable-section"><h3>テストケース一覧</h3><table class="data"><thead><tr><th>ケースID</th><th>種別</th><th>手順</th><th>期待結果</th><th>Trace</th></tr></thead><tbody>${rows.join('') || '<tr><td colspan="5">ケースがありません</td></tr>'}</tbody></table></div>`;
}

function qaCaseRow(no, type, step, expected, trace) {
  return `<tr><td class="qa-trace">TC-${String(no).padStart(4, '0')}</td><td>${escHtml(type)}</td><td>${escHtml(step)}</td><td>${escHtml(expected)}</td><td class="qa-trace">${escHtml(trace)}</td></tr>`;
}

function renderQaReview(data) {
  const artifact = qaArtifact();
  if (artifact && artifact.cross_review) {
    const r = artifact.cross_review;
    const report = artifact.qa_process_report || {};
    return renderAiBadge() +
      `<div class="qa-readable-section"><h3>横断レビュー 指摘</h3><ul class="qa-check-list">${qaList(r.findings)}</ul></div>` +
      `<div class="qa-readable-section"><h3>ギャップ</h3><ul class="qa-check-list qa-question-list">${qaList(r.gaps)}</ul></div>` +
      `<div class="qa-readable-section"><h3>推奨対応</h3><ul class="qa-check-list">${qaList(r.recommendations)}</ul></div>` +
      `<div class="qa-readable-section"><h3>QAプロセスレポート</h3><p>${escHtml(report.summary || '質問待ち')}</p><ul class="qa-check-list">${qaList(report.next_actions)}</ul></div>` +
      `<div class="qa-readable-section"><h3>質問待ち</h3><ul class="qa-check-list qa-question-list">${qaList(r.questions)}</ul></div>`;
  }
  const s = qaSummary(data);
  const findings = [];
  if (!s.screens) findings.push('画面が抽出されていません。クロール条件または認証状態の確認が必要です。');
  if (s.fields && !s.required) findings.push('入力項目はありますが必須項目が検出されていません。HTML属性と業務必須の差分確認が必要です。');
  if (!s.transitions && s.screens > 1) findings.push('複数画面がありますが遷移情報がありません。リンク抽出条件の確認が必要です。');
  if (!findings.length) findings.push('自動抽出範囲では重大な欠落兆候はありません。期待結果と業務ルールは質問待ちです。');
  return `<div class="qa-readable-section"><h3>横断レビュー</h3><ul class="qa-check-list">${findings.map(f => `<li>${escHtml(f)}</li>`).join('')}</ul></div>` +
    `<div class="qa-readable-section"><h3>最終確認</h3><ul class="qa-check-list qa-question-list"><li>画面ごとの優先度と利用頻度</li><li>障害時の業務影響</li><li>非機能要件と監査観点</li></ul></div>`;
}

document.getElementById('qa-reload-sites').addEventListener('click', () => {
  qaLoadedSites = false;
  loadQaProcessSites(true);
});
document.getElementById('qa-domain-select').addEventListener('change', e => loadQaProcessInput(e.target.value));
document.getElementById('qa-generate-all').addEventListener('click', () => generateQaProcess('qa_process_report'));
document.querySelectorAll('.qa-generate-current').forEach(btn => {
  btn.addEventListener('click', () => generateQaProcess(btn.dataset.qaStep));
});
document.querySelectorAll('.qa-step-dot').forEach(btn => {
  btn.addEventListener('click', () => {
    const page = Number(btn.dataset.qaPage);
    if (page > 0 && !qaActiveDomain) { setQaStatus('先に対象サイトを選択してください。', true); return; }
    qaCurrentPage = page;
    updateQaWizard();
  });
});
document.getElementById('qa-prev').addEventListener('click', () => {
  qaCurrentPage = Math.max(0, qaCurrentPage - 1);
  updateQaWizard();
});
document.getElementById('qa-next').addEventListener('click', () => {
  if (qaCurrentPage === 0 && !qaActiveDomain) { setQaStatus('対象サイトを選択してください。', true); return; }
  qaCurrentPage = Math.min(QA_PAGES.length - 1, qaCurrentPage + 1);
  updateQaWizard();
});

// ---- QA拡張ビュー（モデル/自動テスト候補/品質観点）----
const QA_TOOL_CONFIG = {
  'qa-models': {
    select: 'qa-model-domain-select',
    status: 'qa-model-status',
    content: 'qa-model-content',
    outputs: 'qa-model-output-links',
    render: renderQaModelTool,
  },
  'qa-automation': {
    select: 'qa-auto-domain-select',
    status: 'qa-auto-status',
    content: 'qa-auto-content',
    outputs: 'qa-auto-output-links',
    render: renderQaAutomationTool,
  },
  'qa-quality': {
    select: 'qa-quality-domain-select',
    status: 'qa-quality-status',
    content: 'qa-quality-content',
    outputs: 'qa-quality-output-links',
    render: renderQaQualityTool,
  },
};
let qaToolSitesLoaded = false;

async function loadQaToolSites(viewName, force) {
  const cfg = QA_TOOL_CONFIG[viewName];
  if (!cfg) return;
  if (qaToolSitesLoaded && !force) return;
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
    }
    qaToolSitesLoaded = true;
    setQaToolStatus(viewName, items.length ? '対象サイトを選択してください。' : '解析済みサイトがありません。先にサイトを追加してください。');
  } catch (e) {
    setQaToolStatus(viewName, 'サイト一覧の読み込みに失敗しました。', true);
  }
}

async function loadQaToolData(viewName, domain) {
  const cfg = QA_TOOL_CONFIG[viewName];
  if (!cfg) return;
  if (!domain) {
    document.getElementById(cfg.content).innerHTML = '<div class="empty">対象サイトを選択してください。</div>';
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
  const keys = viewName === 'qa-models'
    ? ['screen_transition_graph', 'model_graph', 'coverage_metrics']
    : viewName === 'qa-automation'
      ? ['playwright_candidates', 'playwright_candidates_html']
      : ['quality_viewpoints', 'quality_viewpoints_html'];
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = keys.map(key => {
    const path = outputs[key];
    const label = QA_STEP_LABELS[key] || key;
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
}

function renderQaAutomationTool(data) {
  const pw = data.playwright_candidates || {};
  const rows = (pw.candidates || []).map(item =>
    `<tr><td class="qa-trace">${escHtml(item.id)}</td><td>${escHtml(item.title)}</td><td class="qa-trace">${escHtml(item.trace_id)}</td><td>${escHtml(item.automation_status)}</td><td>${escHtml(item.expected)}</td><td>${escHtml(item.locator_strategy)}</td></tr>`
  ).join('');
  const policies = (pw.locator_policy || []).map(p => `<span class="fmt-badge">${escHtml(p)}</span>`).join('');
  document.getElementById('qa-auto-content').innerHTML =
    `<div class="qa-readable-section"><h3>ロケータ方針</h3><div class="fmt-badges">${policies}</div><p class="input-hint">${escHtml(pw.execution_policy || '')}</p></div>` +
    `<div class="qa-readable-section"><h3>候補一覧</h3><table class="data"><thead><tr><th>ID</th><th>タイトル</th><th>Trace</th><th>状態</th><th>期待結果</th><th>ロケータ方針</th></tr></thead><tbody>${rows || '<tr><td colspan="6">候補がありません</td></tr>'}</tbody></table></div>`;
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
    const rows = items.map(item => `<tr><td class="qa-trace">${escHtml(item.id)}</td><td>${escHtml(item.viewpoint)}</td><td>${escHtml(item.trigger)}</td><td>${escHtml(item.recommendation)}</td><td>${escHtml(item.automation)}</td><td class="qa-trace">${escHtml(item.trace_id)}</td></tr>`).join('');
    return `<div class="qa-readable-section"><h3>${escHtml(category)}</h3><table class="data"><thead><tr><th>ID</th><th>観点</th><th>発火条件</th><th>推奨確認</th><th>自動化</th><th>Trace</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }).join('');
  const risks = (quality.screen_risks || []).map(risk => `<tr><td class="qa-trace">${escHtml(risk.screen_id)}</td><td>${escHtml(risk.title)}</td><td class="num">${escHtml(risk.risk_score)}</td><td>${escHtml((risk.reasons || []).join(' / '))}</td></tr>`).join('');
  document.getElementById('qa-quality-content').innerHTML =
    `<div class="qa-readable-section"><h3>画面リスク</h3><table class="data"><thead><tr><th>画面ID</th><th>画面</th><th class="num">リスク</th><th>理由</th></tr></thead><tbody>${risks || '<tr><td colspan="4">画面がありません</td></tr>'}</tbody></table></div>` +
    (sections || '<div class="empty">品質観点がありません。</div>') +
    `<div class="qa-readable-section"><h3>質問待ち</h3><ul class="qa-check-list qa-question-list">${qaList(quality.questions)}</ul></div>`;
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
    const viewName = view ? view.id.replace('view-', '') : 'qa-models';
    loadQaToolSites(viewName, true);
  });
});
document.getElementById('qa-model-generate').addEventListener('click', () => generateQaAdvanced('qa-models'));
document.getElementById('qa-auto-generate').addEventListener('click', () => generateQaAdvanced('qa-automation'));
document.getElementById('qa-quality-generate').addEventListener('click', () => generateQaAdvanced('qa-quality'));

// ====================== B: ファイルプレビューモーダル ======================
function openFilePreview(path, label) {
  const modal = document.getElementById('file-preview-modal');
  const body = document.getElementById('file-preview-body');
  const titleEl = document.getElementById('file-preview-title');
  const newtab = document.getElementById('file-preview-newtab');
  if (!modal || !body) return;
  titleEl.textContent = label || 'プレビュー';
  const previewUrl = '/preview?path=' + encodeURIComponent(path);
  newtab.href = previewUrl;
  // ローディング表示
  body.innerHTML = '<div class="file-preview-loading"><span class="spinner"></span><span>読み込み中…</span></div>';
  modal.classList.remove('hidden');
  const ext = path.split('.').pop().toLowerCase();
  if (ext === 'html' || ext === 'htm') {
    // HTMLはiframeでサンドボックス表示
    body.innerHTML = `<iframe src="${escHtml(previewUrl)}" title="${escHtml(label || 'プレビュー')}" sandbox="allow-scripts allow-same-origin"></iframe>`;
  } else {
    // JSON / MD / テキストはコードブロックで表示
    fetch(previewUrl)
      .then(r => { if (!r.ok) throw new Error('読み込み失敗'); return r.text(); })
      .then(text => {
        const pre = document.createElement('pre');
        pre.textContent = text; // textContent でXSSを完全回避
        body.innerHTML = '';
        body.appendChild(pre);
      })
      .catch(() => {
        const pre = document.createElement('pre');
        pre.textContent = 'ファイルの読み込みに失敗しました。';
        body.innerHTML = '';
        body.appendChild(pre);
      });
  }
}

function closeFilePreview() {
  const modal = document.getElementById('file-preview-modal');
  const body = document.getElementById('file-preview-body');
  if (!modal) return;
  modal.classList.add('hidden');
  if (body) body.innerHTML = '';
}

document.getElementById('file-preview-close').addEventListener('click', closeFilePreview);
document.getElementById('file-preview-overlay').addEventListener('click', closeFilePreview);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !document.getElementById('file-preview-modal')?.classList.contains('hidden')) {
    closeFilePreview();
  }
});

// B: プレビューボタンのイベント委譲（動的生成ボタン対応）
document.addEventListener('click', (e) => {
  const btn = e.target.closest('.qa-preview-btn');
  if (btn && btn.dataset.path) openFilePreview(btn.dataset.path, btn.dataset.label || 'プレビュー');
});

// ---- 再クロール（ドリフト検知）: 既知のサイトを同じ画面構成で取り直す ----

async function recrawlSite(domain) {
  let site = null, urls = [], auth = getSettings().auth || '';
  try { site = (await fetch('/api/site?domain=' + encodeURIComponent(domain)).then(r => r.json())).site; } catch (e) {}
  if (site) {
    urls = site.urls || [];
    auth = site.auth_path || auth;
  } else {
    try {
      const data = await fetch('/api/result?domain=' + encodeURIComponent(domain)).then(r => r.json());
      if (data.files && data.files.json) {
        const rj = await fetch('/preview?path=' + encodeURIComponent(data.files.json)).then(r => r.json());
        urls = (rj.screens || []).map(s => ({ url: s.url, title: s.title || s.url }));
      }
    } catch (e) {}
  }
  if (!urls.length) urls = [{ url: 'https://' + domain + '/', title: domain }];

  // P2へ遷移して前回設定を復元
  switchView('generate');
  executionView.classList.add('hidden'); resultPanel.classList.add('hidden');
  appContent.classList.remove('is-executing'); genPanel.style.display = '';

  document.getElementById('url-input').value = 'https://' + domain + '/';
  if (auth) document.getElementById('auth-path').value = auth;
  document.getElementById('compare').checked = true;
  document.getElementById('p1-summary').style.display = 'none';

  // 前回の画面リストを復元
  discovered = (Array.isArray(urls) ? urls : []).map(u =>
    typeof u === 'string'
      ? { url: u, title: u, login_required: false, login_reasons: [], login_url: '' }
      : { url: u.url, title: u.title || u.url, login_required: false, login_reasons: [], login_url: '' }
  );
  renderDiscovered();
  updateTargetPreview();
  showWizardStep(2);
}

async function openResultsForDomain(domain) {
  switchView('generate');
  genPanel.style.display = 'none';
  executionView.classList.add('hidden');
  appContent.classList.add('is-executing');
  resultPanel.classList.remove('hidden');
  resultHero.innerHTML = '<div class="hero-msg">読み込み中…</div>';
  await showResults(domain);
}


// ====================== ウィザード ======================
let wizardStep = 1;
let discovered = [];
const urlInput = document.getElementById('url-input');
const crawlDiscoverySection = document.getElementById('crawl-discovery-section');
const targetPreview = document.getElementById('target-preview');
const targetPreviewList = document.getElementById('target-preview-list');

function showStep(n) { wizardStep = n; }
urlInput.addEventListener('input', () => { clearDiscovered(); updateTargetPreview(); });


function setUrlMessage(msg, isError) {
  const el = document.getElementById('url-input-message');
  el.textContent = msg; el.classList.toggle('input-field-message-error', !!(msg && isError));
}

// ---- 画面リスト取得（discover）----
document.getElementById('discover-btn').addEventListener('click', () => discoverUrls());

// ---- 自動ログイン（ADR-0002: GUIフォーム入力方式）----
function loginDomain() {
  const u = urlInput.value.trim();
  try { return new URL(u).hostname; } catch (e) { return ''; }
}
function setLoginStatus(msg, isError) {
  const el = document.getElementById('login-status');
  if (!el) return;
  el.textContent = msg; el.classList.toggle('input-field-message-error', !!(msg && isError));
}
function setLoginLoading(show, msg) {
  const el = document.getElementById('login-loading');
  if (!el) return;
  el.style.display = show ? 'flex' : 'none';
  if (msg) { const m = document.getElementById('login-loading-msg'); if (m) m.textContent = msg; }
}

// ---- 各「要ログイン」ページに埋め込んだログインボタン（イベント委譲）----
document.getElementById('discovered-url-list').addEventListener('click', async (e) => {
  const btn = e.target.closest('.disc-item-login-btn');
  if (!btn) return;
  const panel = btn.closest('.disc-item-login-panel');
  if (!panel) return;
  const loginUrl = panel.dataset.loginUrl || document.getElementById('login-url').value.trim();
  const username = panel.querySelector('.disc-item-login-user').value.trim();
  const password = panel.querySelector('.disc-item-login-pass').value;
  const statusEl = panel.querySelector('.disc-item-login-status');
  const loadingEl = panel.querySelector('.disc-item-login-loading');
  const domain = loginDomain();
  if (!loginUrl) { statusEl.textContent = 'ログインURLが見つかりません。上級設定でURLを入力してください。'; statusEl.classList.add('input-field-message-error'); return; }
  btn.disabled = true; loadingEl.style.display = 'flex'; statusEl.textContent = '';
  try {
    const res = await fetch('/api/login/simple', { method: 'POST', body: new URLSearchParams({
      domain: domain || 'site', login_url: loginUrl, username, password,
    }) });
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.error || 'ログインに失敗しました');
    document.getElementById('auth-path').value = data.auth_path || ('output/' + domain + '/auth.json');
    // パスワードを即破棄（セキュリティ）
    panel.querySelector('.disc-item-login-pass').value = '';
    statusEl.textContent = 'ログイン成功。認証後ページを再解析しています…';
    statusEl.classList.remove('input-field-message-error');
    await discoverUrls(true);
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.classList.add('input-field-message-error');
  } finally {
    btn.disabled = false; loadingEl.style.display = 'none';
  }
});

// ---- 上級ログイン（アコーディオン内）: フォームを取得ボタン ----
document.getElementById('login-scrape-btn').addEventListener('click', async () => {
  const url = document.getElementById('login-url').value.trim();
  const domain = loginDomain();
  if (!url) { setLoginStatus('ログインURLを入力してください', true); return; }
  setLoginStatus('', false);
  setLoginLoading(true, 'フォームを取得しています…');
  document.getElementById('login-scrape-btn').disabled = true;
  document.getElementById('login-fields-area').innerHTML = '';
  try {
    const res = await fetch('/api/login/scrape', { method: 'POST', body: new URLSearchParams({ url, domain: domain || 'site' }) });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || 'フォーム取得に失敗しました');
    renderLoginFields(data.fields || [], data.current_url);
  } catch (e) {
    setLoginStatus(e.message, true);
  } finally {
    setLoginLoading(false);
    document.getElementById('login-scrape-btn').disabled = false;
  }
});

function renderLoginFields(fields, currentUrl) {
  const area = document.getElementById('login-fields-area');
  if (!fields.length) { setLoginStatus('フォームフィールドが見つかりませんでした。ログインURLを確認してください。', true); return; }
  area.innerHTML = fields.map(f => {
    const type = f.field_type === 'password' ? 'password' : (f.field_type === 'email' ? 'email' : 'text');
    const ac = f.field_type === 'password' ? 'current-password' : (f.field_type === 'email' || f.name.includes('mail') || f.name.includes('user') ? 'username' : 'off');
    return `<div class="field" style="margin-bottom:8px">
      <label>${escHtml(f.placeholder || f.name || f.field_type)}</label>
      <input type="${type}" class="url-input login-field-input" data-field-name="${escHtml(f.name || f.element_id)}" data-current-url="${escHtml(currentUrl)}" placeholder="${escHtml(f.placeholder)}" autocomplete="${ac}" />
    </div>`;
  }).join('') +
    '<button type="button" id="login-submit-btn" class="btn-primary" style="margin-top:8px;height:36px;padding:0 18px;font-size:13px">ログイン</button>';
  document.getElementById('login-submit-btn').addEventListener('click', submitLogin);
  setLoginStatus('', false);
}

async function submitLogin() {
  const domain = loginDomain();
  const inputs = document.querySelectorAll('.login-field-input');
  if (!inputs.length) { setLoginStatus('先にフォームを取得してください', true); return; }
  const currentUrl = inputs[0].dataset.currentUrl || document.getElementById('login-url').value.trim();
  const fieldValues = {};
  inputs.forEach(inp => { if (inp.dataset.fieldName) fieldValues[inp.dataset.fieldName] = inp.value; });

  setLoginLoading(true, 'ログインしています…');
  const btn = document.getElementById('login-submit-btn');
  if (btn) btn.disabled = true;
  setLoginStatus('', false);
  try {
    const res = await fetch('/api/login/submit', { method: 'POST', body: new URLSearchParams({
      domain: domain || 'site', current_url: currentUrl, fields_json: JSON.stringify(fieldValues),
    }) });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'ログインに失敗しました');
    if (data.success) {
      document.getElementById('auth-path').value = data.auth_path || ('output/' + domain + '/auth.json');
      setLoginStatus('ログイン成功。認証後ページを再解析しています…', false);
      setLoginLoading(true, '認証後ページを再解析しています…');
      await discoverUrls(true);
    } else if (data.needs_more_fields) {
      setLoginStatus('追加認証（MFA等）が必要です。表示されたフィールドを入力してください。', false);
      renderLoginFields(data.fields || [], data.current_url || currentUrl);
    } else {
      throw new Error(data.error || 'ログインに失敗しました');
    }
  } catch (e) {
    setLoginStatus(e.message, true);
  } finally {
    setLoginLoading(false);
    const b = document.getElementById('login-submit-btn');
    if (b) b.disabled = false;
  }
}
document.getElementById('select-all-btn').addEventListener('click', () => setAllDiscovered(true));
document.getElementById('clear-all-btn').addEventListener('click', () => setAllDiscovered(false));

// ---- 画面分析 経過時間タイマー ----
let _discoverTimerInterval = null;
function _startDiscoverTimer() {
  const el = document.getElementById('discover-elapsed');
  if (!el) return;
  el.textContent = '0:00';
  const t0 = Date.now();
  _discoverTimerInterval = setInterval(() => {
    const s = Math.floor((Date.now() - t0) / 1000);
    el.textContent = Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
  }, 1000);
}
function _stopDiscoverTimer() {
  clearInterval(_discoverTimerInterval);
  _discoverTimerInterval = null;
  // 最終経過時間をサマリー用に返す（消去しない）
  const el = document.getElementById('discover-elapsed');
  const elapsed = el ? el.textContent : '';
  if (el) el.textContent = '';
  return elapsed;
}

// skipLoginSection=true のとき（ログイン後の再解析）はログインセクションを再展開しない
async function discoverUrls(skipLoginSection) {
  const url = urlInput.value.trim();
  if (!url) { setUrlMessage('URLを入力してから画面分析を実行してください', true); return; }
  const loading = document.getElementById('discover-loading');
  const status = document.getElementById('discover-status');
  const btn = document.getElementById('discover-btn');
  loading.style.display = 'flex'; status.textContent = ''; status.classList.remove('discover-status-error');
  btn.disabled = true;
  _startDiscoverTimer();
  try {
    const auth = document.getElementById('auth-path').value.trim() || getSettings().auth || '';
    const body = new URLSearchParams({ url, depth: '5', max_pages: '300', auth });
    const res = await fetch('/api/discover', { method: 'POST', body });
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || '画面リスト取得に失敗しました');
    discovered = (data.pages || []).filter(p => p && p.url);
    renderDiscovered();
    // ログインURLを上級設定フィールドに反映（参考表示）
    if (!skipLoginSection && discovered.some(p => p.login_required)) {
      const loginPage = discovered.find(p => p.login_required && p.login_url);
      if (loginPage) {
        const advUrl = document.getElementById('login-url');
        if (advUrl && !advUrl.value) advUrl.value = loginPage.login_url;
      }
    }
    const loginCount = discovered.filter(p => p.login_required).length;
    if (discovered.length) {
      const summary = document.getElementById('p1-summary');
      const countEl = document.getElementById('p1-count-text');
      const hintEl = document.getElementById('p1-login-hint');
      if (summary) {
        countEl.textContent = `${discovered.length}件の画面を検出しました`;
        hintEl.textContent = loginCount ? `うち${loginCount}件がログインを必要とします` : '';
        summary.style.display = '';
      }
      status.textContent = '';
    } else {
      status.textContent = '画面が0件でした。URLを確認してください。';
    }
  } catch (e) {
    clearDiscovered(); status.textContent = e.message; status.classList.add('discover-status-error');
  } finally {
    const elapsed = _stopDiscoverTimer();
    loading.style.display = 'none'; btn.disabled = false; updateTargetPreview();
    // 完了後：経過時間をサマリーに表示
    if (elapsed) {
      const hintEl = document.getElementById('p1-login-hint');
      if (hintEl && hintEl.textContent) {
        hintEl.textContent += ` （解析時間: ${elapsed}）`;
      } else {
        const countEl = document.getElementById('p1-count-text');
        if (countEl) countEl.textContent += ` （解析時間: ${elapsed}）`;
      }
    }
  }
}
function renderDiscovered() {
  const panel = document.getElementById('discovered-url-panel');
  const list = document.getElementById('discovered-url-list');
  panel.style.display = discovered.length ? '' : 'none';

  const makeNormalItem = (it) => `
    <label class="discovered-url-item">
      <input type="checkbox" class="discovered-cb" value="${escHtml(it.url)}" checked />
      <span><strong>${escHtml(it.title || 'タイトル未取得')}</strong><code>${escHtml(it.url)}</code></span>
    </label>`;

  const makeLoginItem = (it) => {
    const loginUrl = it.login_url || '';
    const loginUrlDisplay = loginUrl ? (() => { try { return new URL(loginUrl).pathname; } catch (e) { return loginUrl; } })() : '（検出中）';
    return `
    <div class="disc-login-item-wrap">
      <label class="discovered-url-item">
        <input type="checkbox" class="discovered-cb" value="${escHtml(it.url)}" checked />
        <span>
          <strong>${escHtml(it.title || 'タイトル未取得')}</strong>
          <code>${escHtml(it.url)}</code>
          <span class="disc-login-badge">要ログイン</span>
        </span>
      </label>
      <div class="disc-item-login-panel" data-login-url="${escHtml(loginUrl)}">
        <div class="disc-item-login-header">🔒 この画面へのアクセスに認証が必要です <span class="disc-item-login-urlpath">ログインURL: ${escHtml(loginUrlDisplay)}</span></div>
        <div class="disc-item-login-body">
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <input type="text" class="disc-item-login-user url-input" placeholder="ID / メールアドレス" autocomplete="username" style="flex:1;min-width:140px;height:34px;margin:0" />
            <input type="password" class="disc-item-login-pass url-input" placeholder="パスワード" autocomplete="current-password" style="flex:1;min-width:140px;height:34px;margin:0" />
            <button type="button" class="btn-primary disc-item-login-btn" style="height:34px;padding:0 16px;font-size:13px;flex-shrink:0">ログイン</button>
          </div>
          <div class="disc-item-login-loading discover-loading" style="display:none;margin-top:6px"><span class="spinner"></span><span>ログインしています…</span></div>
          <div class="disc-item-login-status input-field-message" style="margin-top:4px"></div>
        </div>
      </div>
    </div>`;
  };

  const normalPages = discovered.filter(p => !p.login_required);
  const loginPages = discovered.filter(p => p.login_required);

  let html = normalPages.map(makeNormalItem).join('');
  if (loginPages.length) {
    html += `<div class="disc-login-group-separator"><span>🔒 認証が必要なページ（${loginPages.length}件）— 各画面の認証情報を入力してください</span></div>`;
    html += loginPages.map(makeLoginItem).join('');
  }
  list.innerHTML = html;
  list.querySelectorAll('.discovered-cb').forEach(cb => cb.addEventListener('change', updateTargetPreview));
}
function clearDiscovered() {
  discovered = [];
  document.getElementById('discovered-url-panel').style.display = 'none';
  document.getElementById('discovered-url-list').innerHTML = '';
  document.getElementById('discover-status').textContent = '';
}
function setAllDiscovered(v) { document.querySelectorAll('.discovered-cb').forEach(cb => { cb.checked = v; }); updateTargetPreview(); }
function selectedDiscovered() { return [...document.querySelectorAll('.discovered-cb:checked')].map(cb => cb.value); }

// ---- 対象URLの確定 ----
function buildTargetUrls() { return selectedDiscovered(); }
function updateTargetPreview() {
  const urls = buildTargetUrls();
  targetPreview.querySelector('strong').textContent = `チェック対象 ${urls.length}件`;
  if (!urls.length) {
    const msg = urlInput.value.trim() ? '画面リスト取得を実行してください' : 'URLを入力してください';
    targetPreviewList.innerHTML = `<li><span>未確定</span><code>${msg}</code></li>`;
    return;
  }
  targetPreviewList.innerHTML = urls.map((u, i) => `<li><span>${i === 0 ? 'メイン' : '対象 ' + (i + 1)}</span><code>${escHtml(u)}</code></li>`).join('');
}

// ====================== 実行 ======================
const genPanel = document.getElementById('gen-panel');
const executionView = document.getElementById('execution-view');
const appContent = document.getElementById('app-content');
const execTitle = document.getElementById('exec-title');
const execMessage = document.getElementById('exec-message');
const execElapsed = document.getElementById('exec-elapsed');
const execProgressBar = document.getElementById('exec-progress-bar');
const execTarget = document.getElementById('exec-target');
const execPhase = document.getElementById('exec-phase');
const execLog = document.getElementById('exec-log');
const execError = document.getElementById('exec-error');
const execActions = document.getElementById('exec-actions');
const execRunningActions = document.getElementById('exec-running-actions');
const previewImage = document.getElementById('exec-preview-image');
const previewPlaceholder = document.getElementById('exec-preview-placeholder');
const estep = [0,1,2,3].map(i => document.getElementById('estep-' + i));
let timer, startTime, previewTimer, activeDomain = '';
let runAbort = null, lastRun = null, activeRunId = '';

function domainOf(url) { try { return new URL(url).host; } catch { return ''; } }
function startTimer() { startTime = Date.now(); timer = setInterval(() => { const s = Math.floor((Date.now() - startTime) / 1000); execElapsed.textContent = String(Math.floor(s / 60)).padStart(2,'0') + ':' + String(s % 60).padStart(2,'0'); }, 500); }
function stopTimer() { clearInterval(timer); }
function setStep(idx) { estep.forEach((el, i) => { el.className = 'execution-step' + (i < idx ? ' is-complete' : i === idx ? ' is-active' : ''); }); execProgressBar.style.width = (8 + idx * 23) + '%'; }
function guessStep(line) {
  if (line.includes('解析') || line.includes('analyz')) return 2;
  if (line.includes('グラフ') || line.includes('graph') || line.includes('保存') || line.includes('出力') || line.includes('完了')) return 3;
  if (line.includes('クロール') || line.includes('crawl') || line.includes('ページ')) return 1;
  return -1;
}
function startPreviewPolling() {
  if (!activeDomain) return;
  const poll = () => {
    const img = new Image();
    img.onload = () => { previewImage.src = img.src; previewImage.classList.add('show'); previewPlaceholder.classList.add('hidden'); };
    img.src = `/api/live-screenshot?domain=${encodeURIComponent(activeDomain)}&t=${Date.now()}`;
  };
  poll(); previewTimer = setInterval(poll, 1500);
}
function stopPreviewPolling() { clearInterval(previewTimer); }

document.getElementById('form').addEventListener('submit', (e) => {
  e.preventDefault();
  const url = urlInput.value.trim();
  if (!url) { setUrlMessage('URL を入力してください', true); return; }
  const urls = buildTargetUrls();
  if (!urls.length) {
    setUrlMessage(discovered.length ? 'ドキュメント化する画面を1件以上選択してください' : '先に「画面分析」を実行してください', true);
    return;
  }
  const body = new URLSearchParams({
    urls: urls.join(','),
    depth: document.getElementById('crawl-depth').value,
    max_pages: document.getElementById('max-pages').value,
    format: 'html,pdf,md,excel,json',
    compare: document.getElementById('compare').checked ? 'true' : 'false',
    auth: document.getElementById('auth-path').value.trim() || getSettings().auth || '',
    crawl_mode: 'crawl',
  });
  const label = urls.length > 1 ? `${urls[0]} ほか ${urls.length - 1}件` : urls[0];
  runWith(body.toString(), domainOf(urls[0]), label, urls.length);
});

async function runWith(bodyStr, domain, label, urlCount) {
  lastRun = { bodyStr, domain, label, urlCount };
  activeDomain = domain;
  runAbort = new AbortController();
  genPanel.style.display = 'none';
  resultPanel.classList.add('hidden');
  executionView.classList.remove('hidden');
  appContent.classList.add('is-executing');
  showWizardStep(3);
  execError.classList.add('hidden'); execActions.classList.add('hidden');
  execRunningActions.classList.remove('hidden');
  const stopBtn = document.getElementById('exec-stop-btn');
  stopBtn.disabled = false; stopBtn.textContent = '停止';
  previewImage.classList.remove('show'); previewPlaceholder.classList.remove('hidden');
  execLog.textContent = '';
  execTarget.textContent = label;
  execTitle.textContent = 'クロール中…'; execMessage.textContent = `${urlCount}件の対象をクロールしてドキュメント化します。`;
  execPhase.textContent = '実行中'; setStep(0); startTimer(); startPreviewPolling();

  activeRunId = '';
  let reportPath = '', summary = null, ok = false, cur = 0, cancelled = false, sessionExpired = false;
  try {
    const res = await fetch('/run', { method: 'POST', body: bodyStr, headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, signal: runAbort.signal });
    const reader = res.body.getReader(); const dec = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read(); if (done) break;
      const chunk = dec.decode(value);
      const ri = chunk.match(/RUN_ID:(.*)/); if (ri) activeRunId = ri[1].trim();
      const rp = chunk.match(/REPORT_PATH:(.*)/); if (rp) { reportPath = rp[1].trim(); ok = true; }
      const sm = chunk.match(/SUMMARY:(.*)/); if (sm) { try { summary = JSON.parse(sm[1].trim()); ok = true; } catch {} }
      if (/(^|\\n)\\s*停止しました。/.test(chunk)) cancelled = true;
      if (/SESSION_EXPIRED/.test(chunk)) sessionExpired = true;
      const clean = chunk.replace(/(RUN_ID|REPORT_PATH|PDF_PATH|SUMMARY):.*\\n?/g, '');
      execLog.textContent += clean; execLog.scrollTop = execLog.scrollHeight;
      for (const line of clean.split('\\n')) { const st = guessStep(line); if (st >= 0 && st >= cur) { cur = st; setStep(st); } }
    }
  } catch (err) {
    if (err.name === 'AbortError') cancelled = true;
    else execLog.textContent += '\\n通信エラー: ' + err.message;
  }

  stopTimer(); stopPreviewPolling(); execRunningActions.classList.add('hidden');
  if (sessionExpired) {
    execActions.classList.remove('hidden');
    execTitle.textContent = 'セッションが失効しています'; execPhase.textContent = '要再ログイン';
    execMessage.textContent = '保存済みのログインセッションが失効していたため、ドリフト誤検知を防ぐためクロールを中断しました（前回の結果は保持されています）。入力に戻り「ログイン情報の設定」から再ログインしてください。';
  } else if (cancelled) {
    execActions.classList.remove('hidden');
    execTitle.textContent = '実行を停止しました'; execPhase.textContent = '停止';
    execMessage.textContent = '停止要求により処理を終了しました。必要に応じて入力に戻って再実行してください。';
  } else if (ok || reportPath) {
    setStep(4); execProgressBar.style.width = '100%';
    estep.forEach(el => el.className = 'execution-step is-complete');
    execTitle.textContent = '生成完了'; execPhase.textContent = '完了';
    execMessage.textContent = 'ドキュメントの生成が完了しました。';
    document.getElementById('btn-view-report').style.display = '';
    execActions.classList.remove('hidden');
    _showCompletionPopup(Math.floor((Date.now() - startTime) / 1000));
  } else {
    execActions.classList.remove('hidden');
    execTitle.textContent = 'エラー'; execPhase.textContent = 'エラー'; execError.classList.remove('hidden');
  }
}

document.getElementById('exec-stop-btn').addEventListener('click', async () => {
  const stopBtn = document.getElementById('exec-stop-btn');
  stopBtn.disabled = true; stopBtn.textContent = '停止中…';
  execMessage.textContent = '停止要求を送信しています…';
  // サーバ側のクロールプロセスを確実に終了させてから、クライアントの受信を中断する
  if (activeRunId) {
    try { await fetch('/api/cancel', { method: 'POST', body: new URLSearchParams({ run_id: activeRunId }) }); } catch (e) {}
  }
  if (runAbort) runAbort.abort();
});

document.getElementById('exec-new-btn').addEventListener('click', () => {
  switchView('generate');
  executionView.classList.add('hidden'); resultPanel.classList.add('hidden');
  appContent.classList.remove('is-executing'); genPanel.style.display = '';
  showWizardStep(2);
});
document.getElementById('r-new-btn').addEventListener('click', () => switchView('dashboard'));
document.getElementById('btn-view-report').addEventListener('click', () => showResults(activeDomain));
document.getElementById('r-recrawl-btn').addEventListener('click', () => {
  const domain = document.getElementById('r-domain').textContent.trim();
  if (domain && domain !== '-') recrawlSite(domain);
});

// ====================== 結果ページ（QAビュー軸） ======================
const resultPanel = document.getElementById('result-panel');
const resultHero = document.getElementById('result-hero');
const EXPORT_DEFS = [
  { key: 'html', label: 'HTMLレポート', desc: 'テスト分析インプット文書（画面別カード＋テスト条件）' },
  { key: 'pdf', label: 'PDF', desc: '配布・印刷用（HTMLレポートのPDF版）' },
  { key: 'screens_md', label: 'Markdown（画面一覧）', desc: 'screens.md' },
  { key: 'forms_md', label: 'Markdown（フォーム）', desc: 'forms.md' },
  { key: 'excel', label: 'Excel', desc: 'spec.xlsx（表計算で編集）' },
  { key: 'json', label: 'JSON（機械可読）', desc: '自動化・連携用の構造化データ' },
  { key: 'diff', label: '差分レポート', desc: '前回スナップショットとの差分' },
];
let resultData = null, reportJson = null, activeResultTab = 'overview';

async function showResults(domain) {
  let data;
  try {
    const res = await fetch('/api/result?domain=' + encodeURIComponent(domain));
    data = await res.json();
    if (!res.ok) throw new Error(data.error || '結果の取得に失敗しました');
  } catch (e) {
    // 実行ビューが隠れている（履歴から開いた）場合は結果領域にエラーを表示
    executionView.classList.add('hidden'); resultPanel.classList.remove('hidden');
    appContent.classList.add('is-executing');
    setHeader(['ダッシュボード', domain], domain);
    resultHero.innerHTML = `<div class="hero-msg"><p>結果の取得に失敗しました。</p><p style="font-size:13px;color:var(--text-muted)">${escHtml(e.message)}</p></div>`;
    return;
  }
  resultData = data;
  reportJson = null;
  if (data.files && data.files.json) {
    try { reportJson = await fetch('/preview?path=' + encodeURIComponent(data.files.json)).then(r => r.json()); } catch (e) {}
  }
  const s = data.summary || {};
  const required = reportJson ? countRequired(reportJson) : 0;
  const crawledAt = reportJson && reportJson.meta ? reportJson.meta.crawled_at : '';
  document.getElementById('r-crawled').textContent = crawledAt ? ('最終クロール: ' + crawledAt) : '';
  document.getElementById('r-domain').textContent = domain;
  document.getElementById('r-screens').textContent = s.screens || 0;
  document.getElementById('r-forms').textContent = s.forms || 0;
  document.getElementById('r-fields').textContent = s.fields || 0;
  document.getElementById('r-required').textContent = required;
  document.getElementById('r-buttons').textContent = s.buttons || 0;
  setHeader(['ダッシュボード', domain], domain);

  executionView.classList.add('hidden'); resultPanel.classList.remove('hidden');
  _buildExportDropdown(data);
  showWizardStep(4);
  selectResultTab('overview');
}

function _buildExportDropdown(data) {
  const menu = document.getElementById('export-dropdown-menu');
  if (!menu) return;
  const files = (data && data.files) || {};
  const domain = (document.getElementById('r-domain') || {}).textContent || '';
  const defs = [
    { key: 'html', label: 'HTMLレポート' },
    { key: 'pdf', label: 'PDF' },
    { key: 'json', label: 'JSON' },
    { key: 'excel', label: 'Excel' },
    { key: 'screens_md', label: 'Markdown（画面一覧）' },
    { key: 'forms_md', label: 'Markdown（フォーム）' },
    { key: 'transition_mmd', label: '遷移図（Mermaid）' },
    { key: 'diff', label: '差分レポート' },
  ];
  const zipRow = `<div class="export-dropdown-item is-zip"><span>すべてZIPでダウンロード</span><a href="/download-zip?domain=${encodeURIComponent(domain)}" class="btn-primary" style="height:28px;padding:0 10px;font-size:12px">DL</a></div>`;
  const fileRows = defs.map(d => {
    if (files[d.key]) {
      return `<div class="export-dropdown-item"><span>${escHtml(d.label)}</span><div style="display:flex;gap:4px"><a href="/preview?path=${encodeURIComponent(files[d.key])}" target="_blank" class="btn-outline-sm" style="height:28px;padding:0 8px;font-size:12px">開く</a><a href="/download?path=${encodeURIComponent(files[d.key])}" class="btn-outline-sm" style="height:28px;padding:0 8px;font-size:12px" download>DL</a></div></div>`;
    }
    return `<div class="export-dropdown-item is-missing"><span>${escHtml(d.label)}（未生成）</span></div>`;
  }).join('');
  menu.innerHTML = zipRow + fileRows;
}

// エクスポートドロップダウンの開閉
document.getElementById('export-dropdown-btn').addEventListener('click', (e) => {
  e.stopPropagation();
  document.getElementById('export-dropdown').classList.toggle('is-open');
});
document.addEventListener('click', () => {
  const dd = document.getElementById('export-dropdown');
  if (dd) dd.classList.remove('is-open');
});

document.querySelectorAll('.result-tab').forEach(t => {
  t.addEventListener('click', () => selectResultTab(t.dataset.tab));
  t.addEventListener('keydown', e => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const tabs = [...document.querySelectorAll('.result-tab')].filter(x => x.offsetParent !== null);
    const i = tabs.indexOf(t);
    const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
    if (next) { selectResultTab(next.dataset.tab); next.focus(); }
  });
});
function selectResultTab(tab) {
  activeResultTab = tab;
  document.querySelectorAll('.result-tab').forEach(t => {
    const on = t.dataset.tab === tab;
    t.classList.toggle('is-active', on);
    t.setAttribute('aria-selected', on ? 'true' : 'false');
    t.tabIndex = on ? 0 : -1;
  });
  if (tab === 'overview') renderOverview();
  else if (tab === 'matrix') renderMatrix();
  else if (tab === 'report') renderReport();
  else if (tab === 'design') renderDesign();
  else if (tab === 'technique-detail') renderTechniqueDetail();
  else if (tab === 'transition') renderTransition();
  else if (tab === 'transition-table') renderTransitionTable();
  else if (tab === 'history') renderTimeline();
}

// ---- 履歴・差分（クロール履歴タイムライン＋任意2点の仕様ドリフト比較）----
let timelineDomain = '';
async function renderTimeline() {
  const domain = document.getElementById('r-domain').textContent.trim();
  timelineDomain = domain;
  resultHero.innerHTML = '<div class="hero-msg">クロール履歴を読み込み中…</div>';
  let snaps = [];
  try {
    const data = await fetch('/api/snapshots?domain=' + encodeURIComponent(domain)).then(r => r.json());
    snaps = data.snapshots || [];
  } catch (e) {}
  if (snaps.length < 2) {
    resultHero.innerHTML = '<div class="hero-pad"><div class="hero-section-title">クロール履歴</div>' +
      '<p style="color:var(--text-muted);font-size:13px">履歴が' + snaps.length + '件です。<strong>再クロール</strong>すると、前回との仕様ドリフト（追加/削除された画面・変更されたフォーム）を時系列で比較できます。</p></div>';
    return;
  }
  // 既定: to=最新(0), from=ひとつ前(1)
  const rows = snaps.map((s, i) => `
    <tr>
      <td style="text-align:center"><input type="radio" name="snap-from" value="${escHtml(s.id)}" ${i === 1 ? 'checked' : ''}></td>
      <td style="text-align:center"><input type="radio" name="snap-to" value="${escHtml(s.id)}" ${i === 0 ? 'checked' : ''}></td>
      <td>${escHtml(s.label)}${i === 0 ? ' <span class="tl-latest">最新</span>' : ''}</td>
      <td class="num">${s.screens}</td><td class="num">${s.forms}</td><td class="num">${s.fields}</td>
    </tr>`).join('');
  resultHero.innerHTML = '<div class="hero-pad">' +
    '<div class="hero-section-title">クロール履歴（' + snaps.length + '件）</div>' +
    '<p style="color:var(--text-muted);font-size:13px;margin-bottom:10px">比較する2時点を選び、仕様ドリフトを確認します（比較元＝古い／比較先＝新しい）。</p>' +
    '<table class="ov-screens tl-table"><thead><tr><th>比較元</th><th>比較先</th><th>クロール日時</th><th>画面</th><th>フォーム</th><th>入力項目</th></tr></thead><tbody>' +
    rows + '</tbody></table>' +
    '<div style="margin:12px 0"><button type="button" class="btn-primary" id="tl-diff-btn">この2時点の差分を表示</button></div>' +
    '<div class="tl-diff-frame" id="tl-diff"></div></div>';
  document.getElementById('tl-diff-btn').addEventListener('click', showTimelineDiff);
  showTimelineDiff();
}
function showTimelineDiff() {
  const from = (document.querySelector('input[name=snap-from]:checked') || {}).value;
  const to = (document.querySelector('input[name=snap-to]:checked') || {}).value;
  const box = document.getElementById('tl-diff');
  if (!from || !to) { box.innerHTML = '<div class="hero-msg">2時点を選択してください。</div>'; return; }
  if (from === to) { box.innerHTML = '<div class="hero-msg">異なる2時点を選択してください。</div>'; return; }
  box.innerHTML = `<iframe src="/api/snapshot-diff?domain=${encodeURIComponent(timelineDomain)}&from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}" title="仕様ドリフト差分"></iframe>`;
}

// ====================== 完了ポップアップ ======================
function _showCompletionPopup(elapsedSec) {
  const overlay = document.getElementById('completion-overlay');
  const elapsedEl = document.getElementById('popup-elapsed');
  if (!overlay) return;
  const m = Math.floor(elapsedSec / 60);
  const s = elapsedSec % 60;
  elapsedEl.textContent = `${m}:${String(s).padStart(2, '0')}`;
  overlay.classList.remove('hidden');
}

document.getElementById('popup-close-btn').addEventListener('click', () => {
  document.getElementById('completion-overlay').classList.add('hidden');
});
document.getElementById('popup-view-report-btn').addEventListener('click', () => {
  document.getElementById('completion-overlay').classList.add('hidden');
  showResults(activeDomain);
});
document.getElementById('completion-overlay').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) document.getElementById('completion-overlay').classList.add('hidden');
});

// ====================== AutoRun ======================
let _autoRunJobId = null;
let _autoRunPollTimer = null;
let _autoRunElapsedTimer = null;
let _autoRunStartedAt = null;  // ISO string from server

const AUTORUN_STEP_MAP = {
  idle:              null,
  discovering:       'ars-crawl',
  awaiting_input:    'ars-crawl',
  crawling:          'ars-crawl',
  generating_qa:     'ars-qa',
  generating_scripts:'ars-scripts',
  awaiting_approval: 'ars-approval',
  running_tests:     'ars-running',
  complete:          'ars-done',
  failed:            null,
  cancelled:         null,
};

const AUTORUN_OUTPUT_LABELS = {
  report_json:             '仕様書 JSON',
  report_html:             '仕様書 HTML',
  test_plan:               'テスト計画',
  test_analysis:           'テスト分析',
  test_design:             'テスト設計',
  test_cases:              'テストケース',
  cross_review:            '横断レビュー',
  qa_process_report:       'QAプロセスレポート',
  model_graph:             'モデルグラフ',
  playwright_candidates_html: 'Playwright候補',
  spec_ts:                 'autorun.spec.ts',
  playwright_report_html:  'テスト実行レポート',
  playwright_report_json:  '実行結果 JSON',
};

// ---- AutoRun: ユーティリティ ----
function autorunSetStartStatus(msg, isError) {
  const el = document.getElementById('autorun-start-status');
  if (!el) return;
  el.textContent = msg;
  el.classList.toggle('input-field-message-error', !!isError);
}

function autorunFmtElapsed(sec) {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2,'0')}`;
}

// ---- AutoRun: 開始 ----
async function autorunStart() {
  const url = (document.getElementById('autorun-url')?.value || '').trim();
  if (!url) { autorunSetStartStatus('URLを入力してください。', true); return; }

  const depth    = document.getElementById('autorun-depth')?.value || '2';
  const maxPages = document.getElementById('autorun-max-pages')?.value || '30';

  const btn = document.getElementById('autorun-start-btn');
  if (btn) { btn.disabled = true; btn.textContent = '開始中…'; }
  autorunSetStartStatus('', false);

  try {
    const res = await fetch('/api/autorun/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, depth: parseInt(depth), max_pages: parseInt(maxPages) }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || '開始に失敗しました');
    _autoRunJobId  = data.job_id;
    _autoRunStartedAt = null;
    _autorunShowRunning();
    _autorunStartPolling();
    _autorunStartElapsed();
  } catch (e) {
    autorunSetStartStatus(String(e), true);
    if (btn) { btn.disabled = false; btn.textContent = '開始'; }
  }
}

function _autorunShowRunning() {
  document.getElementById('autorun-steps').style.display = '';
  document.getElementById('autorun-start-btn').disabled = true;
  document.getElementById('autorun-log-panel').style.display = '';
  document.getElementById('autorun-idle-msg').style.display = 'none';
  document.getElementById('autorun-result-panel').style.display = 'none';
  document.getElementById('autorun-cancel-area').style.display = '';
}

// ---- AutoRun: ポーリング ----
function _autorunStartPolling() {
  if (_autoRunPollTimer) clearInterval(_autoRunPollTimer);
  _autoRunPollTimer = setInterval(_autorunPoll, 2000);
}
function _autorunStopPolling() {
  if (_autoRunPollTimer) { clearInterval(_autoRunPollTimer); _autoRunPollTimer = null; }
}
async function _autorunPoll() {
  if (!_autoRunJobId) return;
  try {
    const data = await fetch('/api/autorun/status?job_id=' + encodeURIComponent(_autoRunJobId)).then(r => r.json());
    _autorunRender(data);
  } catch (e) {}
}

// ---- AutoRun: 経過時間タイマー ----
function _autorunStartElapsed() {
  if (_autoRunElapsedTimer) clearInterval(_autoRunElapsedTimer);
  const el = document.getElementById('autorun-elapsed');
  if (!el) return;
  _autoRunElapsedTimer = setInterval(() => {
    if (!_autoRunStartedAt) return;
    const diffMs = Date.now() - new Date(_autoRunStartedAt).getTime();
    el.textContent = autorunFmtElapsed(Math.floor(diffMs / 1000));
  }, 1000);
}
function _autorunStopElapsed() {
  if (_autoRunElapsedTimer) { clearInterval(_autoRunElapsedTimer); _autoRunElapsedTimer = null; }
}

// ---- AutoRun: レンダリング ----
function _autorunRender(data) {
  if (!data) return;
  const status = data.status || 'idle';

  // started_at を保存（経過時間計算用）
  if (data.started_at && !_autoRunStartedAt) {
    _autoRunStartedAt = data.started_at;
  }

  // 経過時間（サーバー値で最終確定）
  const elapsedEl = document.getElementById('autorun-elapsed');
  if (elapsedEl) {
    const sec = data.elapsed_sec || 0;
    if (['complete','failed','cancelled'].includes(status)) {
      elapsedEl.textContent = autorunFmtElapsed(sec);
    }
  }

  // ---- ステップ進捗 ----
  const activeStepId = AUTORUN_STEP_MAP[status];
  const stepOrder = ['ars-crawl','ars-qa','ars-scripts','ars-approval','ars-running','ars-done'];
  const activeIdx = stepOrder.indexOf(activeStepId);
  const isError = ['failed','cancelled'].includes(status);
  stepOrder.forEach((sid, idx) => {
    const el = document.getElementById(sid);
    if (!el) return;
    el.className = 'autorun-step-item';
    const icon = el.querySelector('.autorun-step-icon');
    if (sid === activeStepId && isError) {
      el.classList.add('is-error'); icon.textContent = '✕';
    } else if (sid === activeStepId) {
      el.classList.add('is-active'); icon.textContent = '↻';
    } else if (idx < activeIdx || status === 'complete') {
      el.classList.add('is-done'); icon.textContent = '✓';
    } else {
      icon.textContent = '○';
    }
  });

  // ---- ログ ----
  const logEl = document.getElementById('autorun-log');
  if (logEl && data.log) {
    logEl.textContent = data.log.join('\n');
    logEl.scrollTop = logEl.scrollHeight;
  }

  // ---- ログイン入力ポップアップ ----
  if (status === 'awaiting_input' && data.input_request?.type === 'login') {
    _autorunShowLoginModal(data.input_request);
  } else {
    _autorunHideLoginModal();
  }

  // ---- 承認ボタン ----
  const approveArea = document.getElementById('autorun-approve-area');
  if (approveArea) approveArea.style.display = (status === 'awaiting_approval') ? '' : 'none';

  // ---- 停止ボタン ----
  const cancelArea = document.getElementById('autorun-cancel-area');
  const activeStatuses = ['discovering','awaiting_input','crawling','generating_qa','generating_scripts','running_tests'];
  if (cancelArea) cancelArea.style.display = activeStatuses.includes(status) ? '' : 'none';

  // ---- 再実行ボタン ----
  const restartArea = document.getElementById('autorun-restart-area');
  if (restartArea) restartArea.style.display = ['complete','failed','cancelled'].includes(status) ? '' : 'none';

  // ---- 終了時の後処理 ----
  if (['complete','failed','cancelled'].includes(status)) {
    const btn = document.getElementById('autorun-start-btn');
    if (btn) { btn.disabled = false; btn.textContent = '開始'; }
    _autorunStopPolling();
    _autorunStopElapsed();
  }

  // ---- エラー表示 ----
  if (data.error) {
    autorunSetStartStatus(data.error, true);
  }

  // ---- 成果物リンク ----
  if (data.outputs && Object.keys(data.outputs).length) {
    const linksEl = document.getElementById('autorun-output-links');
    const area    = document.getElementById('autorun-outputs-area');
    if (linksEl && area) {
      area.style.display = '';
      linksEl.innerHTML = Object.entries(data.outputs)
        .filter(([,p]) => p)
        .map(([key, path]) => {
          const label = AUTORUN_OUTPUT_LABELS[key] || key;
          return `<div class="qa-output-item">
            <span class="qa-output-item-label">${escHtml(label)}</span>
            <div class="qa-output-item-actions">
              <button class="btn-outline-sm qa-preview-btn" data-path="${escHtml(path)}" data-label="${escHtml(label)}" style="font-size:11px;height:26px;padding:0 8px">プレビュー</button>
            </div></div>`;
        }).join('');
    }
  }

  // ---- テスト結果 ----
  if (data.test_results && typeof data.test_results.total === 'number') {
    _autorunRenderResults(data.test_results, data.outputs || {});
  }
}

// ---- AutoRun: テスト結果 ----
function _autorunRenderResults(results, outputs) {
  const panel      = document.getElementById('autorun-result-panel');
  const cards      = document.getElementById('autorun-result-cards');
  const tableWrap  = document.getElementById('autorun-result-table-wrap');
  const reportLinks= document.getElementById('autorun-report-links');
  if (!panel) return;
  panel.style.display = '';

  cards.innerHTML = [
    { label:'PASS',  val:results.passed,  color:'#16a34a' },
    { label:'FAIL',  val:results.failed,  color:'#dc2626' },
    { label:'SKIP',  val:results.skipped, color:'#9ca3af' },
    { label:'TOTAL', val:results.total,   color:'#111827' },
  ].map(c => `<div class="autorun-result-card"><div class="num" style="color:${c.color}">${c.val}</div><div class="lbl">${c.label}</div></div>`).join('');

  const tests = results.tests || [];
  if (tests.length) {
    const rows = tests.map(t => {
      const clr = t.status==='passed' ? '#16a34a' : t.status==='skipped' ? '#9ca3af' : '#dc2626';
      return `<tr>
        <td style="font-size:12px;word-break:break-all">${escHtml(t.title||'')}</td>
        <td style="font-size:12px;font-weight:600;color:${clr}">${escHtml(t.status||'')}</td>
        <td style="font-size:12px">${t.duration_ms||0}ms</td>
        <td style="font-size:11px;color:var(--critical)">${escHtml((t.error||'').substring(0,100))}</td>
      </tr>`;
    }).join('');
    tableWrap.innerHTML = `<table class="data" style="font-size:12px">
      <thead><tr><th>テスト</th><th>結果</th><th>時間</th><th>エラー</th></tr></thead>
      <tbody>${rows}</tbody></table>`;
  } else if (results.error) {
    tableWrap.innerHTML = `<div class="input-field-message input-field-message-error">${escHtml(results.error)}</div>`;
  }

  reportLinks.innerHTML = '';
  if (outputs.playwright_report_html) {
    reportLinks.innerHTML += `<button class="btn-primary qa-preview-btn" data-path="${escHtml(outputs.playwright_report_html)}" data-label="テスト実行レポート" style="height:36px;padding:0 18px;font-size:13px">実行レポートを見る</button> `;
  }
  if (outputs.qa_process_report) {
    reportLinks.innerHTML += `<button class="btn-outline-sm qa-preview-btn" data-path="${escHtml(outputs.qa_process_report)}" data-label="QAプロセスレポート" style="height:36px;padding:0 18px;font-size:13px">QAレポートを見る</button>`;
  }
}

// ---- AutoRun: 承認 ----
async function autorunApprove() {
  if (!_autoRunJobId) return;
  const btn = document.getElementById('autorun-approve-btn');
  if (btn) { btn.disabled = true; btn.textContent = '承認中…'; }
  try {
    const res = await fetch('/api/autorun/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: _autoRunJobId }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || '承認に失敗しました');
    _autorunStartPolling();
    _autorunStartElapsed();
  } catch (e) {
    autorunSetStartStatus(String(e), true);
    if (btn) { btn.disabled = false; btn.textContent = 'テスト実行を承認'; }
  }
}

// ---- AutoRun: 停止 ----
async function autorunCancel() {
  if (!_autoRunJobId) return;
  const btn = document.getElementById('autorun-cancel-btn');
  if (btn) { btn.disabled = true; btn.textContent = '停止中…'; }
  try {
    const res = await fetch('/api/autorun/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: _autoRunJobId }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || '停止に失敗しました');
    _autorunStopPolling();
    _autorunStopElapsed();
    autorunSetStartStatus('停止しました。', false);
    if (btn) { btn.disabled = false; btn.textContent = '停止'; }
    const restartArea = document.getElementById('autorun-restart-area');
    if (restartArea) restartArea.style.display = '';
    const cancelArea = document.getElementById('autorun-cancel-area');
    if (cancelArea) cancelArea.style.display = 'none';
    const startBtn = document.getElementById('autorun-start-btn');
    if (startBtn) { startBtn.disabled = false; startBtn.textContent = '開始'; }
  } catch (e) {
    autorunSetStartStatus(String(e), true);
    if (btn) { btn.disabled = false; btn.textContent = '停止'; }
  }
}

// ---- AutoRun: ログインポップアップ ----
function _autorunShowLoginModal(inputRequest) {
  const modal = document.getElementById('autorun-login-modal');
  if (!modal || !modal.classList.contains('hidden')) return; // 既に表示中
  const msgEl  = document.getElementById('autorun-login-msg');
  const urlEl  = document.getElementById('autorun-login-url');
  if (msgEl) msgEl.textContent = inputRequest.message || 'ログインが必要です。';
  if (urlEl) urlEl.value = inputRequest.login_url || '';
  document.getElementById('autorun-login-username')?.focus();
  modal.classList.remove('hidden');
}

function _autorunHideLoginModal() {
  document.getElementById('autorun-login-modal')?.classList.add('hidden');
}

async function _autorunSubmitLogin(skip) {
  if (!_autoRunJobId) return;
  const statusEl = document.getElementById('autorun-login-status');
  const submitBtn = document.getElementById('autorun-login-submit');
  const skipBtn   = document.getElementById('autorun-login-skip');
  if (statusEl) statusEl.textContent = '';
  if (submitBtn) submitBtn.disabled = true;
  if (skipBtn)   skipBtn.disabled   = true;

  const body = skip
    ? { job_id: _autoRunJobId, type: 'skip' }
    : {
        job_id:   _autoRunJobId,
        type:     'login',
        username: document.getElementById('autorun-login-username')?.value || '',
        password: document.getElementById('autorun-login-password')?.value || '',
      };

  try {
    const res  = await fetch('/api/autorun/submit-input', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || '送信に失敗しました');
    _autorunHideLoginModal();
    // パスワードを即破棄
    const passEl = document.getElementById('autorun-login-password');
    if (passEl) passEl.value = '';
    _autorunStartPolling();
  } catch (e) {
    if (statusEl) { statusEl.textContent = String(e); statusEl.classList.add('input-field-message-error'); }
  } finally {
    if (submitBtn) submitBtn.disabled = false;
    if (skipBtn)   skipBtn.disabled   = false;
  }
}

// ---- AutoRun: リセット ----
function autorunReset() {
  _autoRunJobId     = null;
  _autoRunStartedAt = null;
  _autorunStopPolling();
  _autorunStopElapsed();
  _autorunHideLoginModal();
  document.getElementById('autorun-steps').style.display         = 'none';
  document.getElementById('autorun-outputs-area').style.display  = 'none';
  document.getElementById('autorun-log-panel').style.display     = 'none';
  document.getElementById('autorun-result-panel').style.display  = 'none';
  document.getElementById('autorun-cancel-area').style.display   = 'none';
  document.getElementById('autorun-restart-area').style.display  = 'none';
  document.getElementById('autorun-idle-msg').style.display      = '';
  document.getElementById('autorun-start-btn').disabled = false;
  document.getElementById('autorun-start-btn').textContent = '開始';
  document.getElementById('autorun-url').value = '';
  document.getElementById('autorun-elapsed').textContent = '0:00';
  autorunSetStartStatus('', false);
}

// ---- イベントリスナー ----
document.getElementById('autorun-start-btn')?.addEventListener('click', autorunStart);
document.getElementById('autorun-approve-btn')?.addEventListener('click', autorunApprove);
document.getElementById('autorun-cancel-btn')?.addEventListener('click', autorunCancel);
document.getElementById('autorun-restart-btn')?.addEventListener('click', autorunReset);
document.getElementById('autorun-login-submit')?.addEventListener('click', () => _autorunSubmitLogin(false));
document.getElementById('autorun-login-skip')?.addEventListener('click',   () => _autorunSubmitLogin(true));
document.getElementById('autorun-login-close')?.addEventListener('click',  () => _autorunSubmitLogin(true));
document.getElementById('autorun-login-overlay')?.addEventListener('click',() => _autorunSubmitLogin(true));
document.getElementById('autorun-login-password')?.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') _autorunSubmitLogin(false);
});
