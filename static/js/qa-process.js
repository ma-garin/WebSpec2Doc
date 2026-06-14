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
    const cases = (c.cases || []).map(item => `<tr><td class="qa-trace">${escHtml(item.case_id || '')}</td><td>${escHtml(item.title || '')} ${sourceBadge(item.source || (qaAiStatus.used ? 'openai' : 'rules'))}</td><td>${escHtml((item.steps || []).join(' / '))}</td><td>${escHtml(item.expected || '')}</td><td>${escHtml(item.execution_type || '')}</td><td>${escHtml(item.status || '')}</td><td class="qa-trace">${escHtml(item.trace_id || '')}</td></tr>`).join('');
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
  return `<tr><td class="qa-trace">TC-${String(no).padStart(4, '0')}</td><td>${escHtml(type)} ${sourceBadge('rules')}</td><td>${escHtml(step)}</td><td>${escHtml(expected)}</td><td class="qa-trace">${escHtml(trace)}</td></tr>`;
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
