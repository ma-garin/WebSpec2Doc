// ====================== AutoRun ======================
let _autoRunJobId = null;
let _autoRunPollTimer = null;
let _autoRunElapsedTimer = null;
let _autoRunStartedAt = null;  // ISO string from server
let _autoRunPreviewLoaded = false;
let _autoRunPreviewData = null;
let _autoRunApprovalModalShown = false;
let _autorunViewpointSets = [];
let _autorunViewpointRecommendation = null;
let _autorunViewpointTimer = null;
let _autoRunLogLines = [];
let _autoRunLogLevel = 'all';
let _autoRunLoginSuppressed = false; // ✕で閉じた後、次のポーリングで再ポップさせない
let _autoRunLivePreviewTimer = null;
let _autoRunLivePreviewDomain = '';

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

// コックピット見出しのフェーズ表示（固定の見込み時間は出さない: 実測の経過時間のみ表示）
const AUTORUN_PHASE_LABELS = {
  idle: '待機中',
  discovering: '画面分析中…',
  awaiting_input: 'ログイン情報の入力待ち',
  crawling: '仕様書生成中…',
  generating_qa: 'QA成果物生成中…',
  generating_scripts: 'スクリプト生成中…',
  awaiting_approval: '承認待ち — 実行範囲を選択してください',
  running_tests: 'テスト実行中…',
  complete: '完了',
  failed: '失敗',
  cancelled: '停止済み',
};

// テスト実行中の「n/188件目」進捗表示。承認188件を実行したのに進捗が
// 全く見えない、というドッグフーディング指摘への対応。progress ndjson から
// 読んだ実測件数のみを表示し、不明な場合は捏造せず既定ラベルのままにする。
function _autorunPhaseLabelWithProgress(status, data) {
  const base = AUTORUN_PHASE_LABELS[status] || '';
  if (status !== 'running_tests') return base;
  const progress = data.test_progress;
  if (!progress || !progress.total) return base;
  return `テスト実行中…（${progress.completed || 0}/${progress.total}件目）`;
}

// 全体進捗の重み（フェーズ完了ベース。実行中フェーズは半分進んだとみなす近似）
const AUTORUN_PHASE_ORDER = ['discovering', 'crawling', 'generating_qa', 'generating_scripts', 'awaiting_approval', 'running_tests'];
const AUTORUN_PHASE_WEIGHTS = { discovering: 10, crawling: 40, generating_qa: 20, generating_scripts: 10, awaiting_approval: 5, running_tests: 15 };

const AUTORUN_OUTPUT_LABELS = {
  report_json:             '仕様書 JSON',
  report_html:             '仕様書 HTML',
  test_plan:               'テスト計画',
  test_analysis:           'テスト分析',
  test_design:             'テスト設計',
  test_cases:              'テストケース',
  cross_review:            '横断レビュー',
  qa_process_report:       'QAレポート',
  model_graph:             'モデルグラフ',
  playwright_candidates_html: 'Playwright候補',
  spec_ts:                 'autorun.spec.ts',
  playwright_report_html:  'テスト実行レポート',
  playwright_native_html:  'テスト実行レポート（開発者向け）',
  playwright_report_json:  '実行結果 JSON',
  viewpoint_snapshot:      '観点スナップショット',
};

// SDLC（計画/分析/設計/実装/実行/レポート）思想での成果物カテゴライズ（R2-22対応）
const AUTORUN_OUTPUT_CATEGORY_ORDER = ['計画', '分析', '設計', '実装', '実行', 'レポート'];
const AUTORUN_OUTPUT_CATEGORIES = {
  test_plan:               '計画',
  viewpoint_snapshot:      '計画',
  report_json:             '分析',
  report_html:             '分析',
  test_analysis:           '分析',
  cross_review:            '分析',
  test_design:             '設計',
  test_cases:              '設計',
  model_graph:             '設計',
  playwright_candidates_html: '設計',
  spec_ts:                 '実装',
  playwright_report_html:  '実行',
  playwright_native_html:  '実行',
  playwright_report_json:  '実行',
  qa_process_report:       'レポート',
};

// ステッパーアイコン（テキスト記号を廃止し SVG で状態表現）
const AUTORUN_STEP_ICONS = {
  pending: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="8" cy="8" r="6.2"/></svg>',
  active:  '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" class="autorun-icon-spin"><path d="M8 1.8a6.2 6.2 0 1 1-6.2 6.2" stroke-linecap="round"/></svg>',
  done:    '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="6.2" fill="currentColor" stroke="none" opacity=".15"/><path d="M5 8.2l2.1 2.1L11 6"/></svg>',
  waiting: '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="8" cy="8" r="6.2"/><path d="M8 4.8V8l2.2 1.4"/></svg>',
  error:   '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="8" cy="8" r="6.2" stroke-width="1.6"/><path d="M5.8 5.8l4.4 4.4M10.2 5.8l-4.4 4.4"/></svg>',
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

function _autorunSetText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value || '';
}

// R1-09: 観点セットを目的別（推奨/その他）にグルーピング表示する。
// is_default はアプリ全体で「自動選択される推奨セット」を表す実データであり、
// 存在しないカテゴリを捏造せず、この実フラグに基づいて分類する。
function _autorunViewpointOptionsHtml(sets) {
  const optionHtml = (item) =>
    `<option value="${escHtml(item.id)}">${escHtml(item.name)} v${Number(item.published_version || 0)}</option>`;
  const defaults = sets.filter((item) => item.is_default);
  const others = sets.filter((item) => !item.is_default);
  if (defaults.length && others.length) {
    return `<optgroup label="推奨セット">${defaults.map(optionHtml).join('')}</optgroup>` +
      `<optgroup label="その他のセット">${others.map(optionHtml).join('')}</optgroup>`;
  }
  return sets.map(optionHtml).join('');
}

async function autorunLoadViewpointSelection() {
  const url = (document.getElementById('autorun-url')?.value || '').trim();
  const select = document.getElementById('autorun-viewpoint-set');
  const note = document.getElementById('autorun-viewpoint-recommendation');
  if (!select || !note) return;
  const current = select.value;
  note.textContent = '公開済み観点セットを確認しています…';
  note.classList.remove('is-error');
  try {
    const response = await fetch(`/api/viewpoint-selection?url=${encodeURIComponent(url)}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '観点セットを読み込めません');
    _autorunViewpointSets = data.sets || [];
    _autorunViewpointRecommendation = data.recommended || null;
    select.innerHTML = '<option value="">自動選択</option>' + _autorunViewpointOptionsHtml(_autorunViewpointSets);
    if (_autorunViewpointSets.some((item) => item.id === current)) select.value = current;
    _autorunRenderViewpointRecommendation();
    document.getElementById('autorun-start-btn').disabled = false;
  } catch (error) {
    note.textContent = `観点セットを固定できません: ${error.message}。観点管理で既定公開版を確認してください。`;
    note.classList.add('is-error');
    document.getElementById('autorun-start-btn').disabled = true;
  }
}

function _autorunRenderViewpointRecommendation() {
  const select = document.getElementById('autorun-viewpoint-set');
  const note = document.getElementById('autorun-viewpoint-recommendation');
  if (!select || !note) return;
  if (select.value) {
    const selected = _autorunViewpointSets.find((item) => item.id === select.value);
    note.textContent = selected
      ? `${selected.name} v${selected.published_version}を手動選択 / ${Number(selected.item_count || 0)}件`
      : '選択した公開版を開始時に固定します。';
    return;
  }
  const recommended = _autorunViewpointRecommendation;
  note.textContent = recommended
    ? `推奨: ${recommended.set_name} v${recommended.version} / ${recommended.viewpoint_count}件 / ${recommended.selection_reason}`
    : 'URLと適用ルールから公開版を自動選択します。';
}

function _autorunFailureTypeLabel(type) {
  const labels = {
    app_change: '仕様変更の可能性',
    test_rot: 'テストロケータの劣化',
    env_issue: '環境・認証の問題',
    unknown: '未分類',
  };
  return labels[type] || type || '未分類';
}

function _autorunOutputSummary(data) {
  const outputs = data.outputs || {};
  const labels = Object.keys(outputs)
    .filter(key => outputs[key])
    .map(key => AUTORUN_OUTPUT_LABELS[key] || key);
  return labels.length ? labels.slice(0, 4).join(' / ') : 'まだありません';
}

function _autorunRenderFailurePanel(data) {
  const panel = document.getElementById('autorun-failure-panel');
  const body = document.getElementById('autorun-failure-body');
  if (!panel || !body) return;

  const result = data.test_results || {};
  const hasFailedTests = (result.failed || 0) > 0 || !!result.error;
  const hasJobFailure = ['failed', 'cancelled'].includes(data.status || '');
  if (!hasFailedTests && !hasJobFailure) {
    panel.style.display = 'none';
    body.innerHTML = '';
    return;
  }

  panel.style.display = '';
  const outputs = _autorunOutputSummary(data);
  const classifications = data.failure_classifications || [];
  const summary = data.failure_summary || {};
  const summaryCards = Object.entries(summary)
    .filter(([, count]) => count)
    .map(([type, count]) => `
      <div class="stat-card">
        <span class="stat-card-label">${escHtml(_autorunFailureTypeLabel(type))}</span>
        <strong class="stat-card-value status-critical">${escHtml(String(count))}</strong>
      </div>
    `).join('');

  const fallbackReason = data.error || result.error || 'テスト実行結果に失敗が含まれています。';
  const items = classifications.length
    ? classifications.slice(0, 6).map(item => `
      <div class="autorun-failure-item">
        <strong>${escHtml(item.test_id || 'AutoRun')} / ${escHtml(_autorunFailureTypeLabel(item.failure_type))}</strong>
        <span>${escHtml(item.reason || '')}</span>
        <p>${escHtml(item.suggested_action || '')}</p>
      </div>
    `).join('')
    : `<div class="autorun-failure-item">
        <strong>${escHtml(data.status === 'cancelled' ? '停止済み' : 'AutoRunエラー')}</strong>
        <span>${escHtml(fallbackReason)}</span>
        <p>${escHtml(data.status === 'cancelled' ? '必要に応じて新しく実行してください。' : 'ログと部分成果を確認してから再実行してください。')}</p>
      </div>`;

  body.innerHTML = `
    <div class="autorun-failure-summary">
      ${summaryCards || '<div class="badge badge-muted">分類サマリーなし</div>'}
    </div>
    <div class="autorun-failure-item">
      <strong>部分成果</strong>
      <span>${escHtml(outputs)}</span>
      <p>生成済みの成果物は左ペインから確認できます。</p>
    </div>
    <div class="autorun-failure-list">${items}</div>
  `;
}

// ジョブへ接続（新規開始・リロード後の再接続で共通）
function _autorunAttachJob(jobId) {
  _autoRunJobId = jobId;
  _autoRunStartedAt = null;
  _autoRunPreviewLoaded = false;
  _autoRunPreviewData = null;
  _autoRunApprovalModalShown = false;
  _autoRunLoginSuppressed = false;
  _autorunInitPreviewModal();
  _autorunShowRunning();
  _autorunStartPolling();
  _autorunStartElapsed();
  _autorunPoll();
}

function _autorunShowRunning() {
  document.getElementById('autorun-steps').style.display = '';
  document.getElementById('autorun-start-btn').disabled = true;
  document.getElementById('ar-log-section').style.display = '';
  document.getElementById('autorun-idle-msg').style.display = 'none';
  document.getElementById('autorun-preview-panel').style.display = 'none';
  document.getElementById('autorun-complete-card').style.display = 'none';
  document.getElementById('autorun-failure-panel').style.display = 'none';
  document.getElementById('autorun-cancel-area').style.display = '';
}

// ---- AutoRun: リロード後の再接続・最近の実行 ----
async function autorunResume() {
  let jobs = [];
  try {
    const data = await fetch('/api/autorun/jobs').then(r => r.json());
    jobs = data.jobs || [];
  } catch (e) { return; }

  const activeStatuses = ['discovering', 'awaiting_input', 'crawling', 'generating_qa', 'generating_document_mbt', 'generating_scripts', 'awaiting_approval', 'running_tests'];
  const active = jobs.find(j => activeStatuses.includes(j.status));
  if (active && !_autoRunJobId) {
    _autorunAttachJob(active.job_id);
    autorunSetStartStatus('実行中のジョブに再接続しました。', false);
  }

  const finished = jobs.filter(j => ['complete', 'failed', 'cancelled'].includes(j.status)).slice(0, 5);
  const area = document.getElementById('autorun-recent-area');
  const list = document.getElementById('autorun-recent-list');
  if (!area || !list) return;
  if (!finished.length) { area.style.display = 'none'; return; }
  area.style.display = '';
  list.replaceChildren();
  const statusLabel = { complete: '完了', failed: '失敗', cancelled: '停止' };
  for (const j of finished) {
    const row = document.createElement('div');
    row.className = 'autorun-recent-item';
    const info = document.createElement('div');
    info.className = 'autorun-recent-info';
    const name = document.createElement('strong');
    name.textContent = j.domain || j.url || '';
    const meta = document.createElement('span');
    meta.className = `autorun-recent-status is-${j.status}`;
    meta.textContent = `${statusLabel[j.status] || j.status} / ${autorunFmtElapsed(j.elapsed_sec || 0)}`;
    info.append(name, meta);
    row.appendChild(info);
    if (j.domain && j.status === 'complete') {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn-outline-sm';
      btn.textContent = '結果を見る';
      btn.addEventListener('click', () => openResultsForDomain(j.domain, 'runs'));
      row.appendChild(btn);
    }
    list.appendChild(row);
  }
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

// ---- AutoRun: テスト実行中のライブプレビュー ----
function _autorunStartLivePreview(domain) {
  if (!domain) return;
  _autoRunLivePreviewDomain = domain;
  const frame = document.getElementById('autorun-preview-frame');
  if (frame) frame.style.display = '';
  if (_autoRunLivePreviewTimer) return; // 既にポーリング中
  const poll = () => {
    const image = document.getElementById('autorun-preview-image');
    const placeholder = document.getElementById('autorun-preview-placeholder');
    if (!image || !placeholder) return;
    const probe = new Image();
    probe.onload = () => {
      image.src = probe.src;
      image.classList.add('show');
      placeholder.classList.add('hidden');
    };
    probe.src = `/api/autorun/live-screenshot?domain=${encodeURIComponent(_autoRunLivePreviewDomain)}&t=${Date.now()}`;
  };
  poll();
  _autoRunLivePreviewTimer = setInterval(poll, 1500);
}
function _autorunStopLivePreview() {
  if (_autoRunLivePreviewTimer) { clearInterval(_autoRunLivePreviewTimer); _autoRunLivePreviewTimer = null; }
  const frame = document.getElementById('autorun-preview-frame');
  if (frame) frame.style.display = 'none';
  const image = document.getElementById('autorun-preview-image');
  const placeholder = document.getElementById('autorun-preview-placeholder');
  if (image) image.classList.remove('show');
  if (placeholder) placeholder.classList.remove('hidden');
}

// ---- AutoRun: 実行中の実況（title/status/error を新しい順に表示。R3-01） ----
function _autorunLiveTestRows(tp) {
  if (!tp || !Array.isArray(tp.tests) || !tp.tests.length) return '';
  const badge = s => s === 'passed' ? '<span class="status-low">✅ OK</span>'
    : s === 'failed' ? '<span class="status-critical">❌ NG</span>'
    : '<span class="status-muted">⏭ スキップ</span>';
  const rows = tp.tests.map(t =>
    `<tr><td>${badge(t.status)}</td><td>${escHtml(t.title)}</td>` +
    `<td class="num">${t.duration_ms != null ? Math.round(t.duration_ms / 1000) + '秒' : '—'}</td></tr>`
  ).join('');
  return `<div class="autorun-live-tests"><div class="autorun-live-tests-head">` +
    `実行結果（実況・最新${tp.tests.length}件） <b class="status-low">OK ${tp.passed || 0}</b> / ` +
    `<b class="status-critical">NG ${tp.failed || 0}</b></div>` +
    `<table class="ov-screens"><tbody>${rows}</tbody></table></div>`;
}

function _autorunRenderLiveTests(data) {
  const area = document.getElementById('autorun-live-tests-area');
  if (!area) return;
  if (data.status !== 'running_tests') {
    area.innerHTML = '';
    return;
  }
  area.innerHTML = _autorunLiveTestRows(data.test_progress);
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

// ---- AutoRun: 全体進捗（フェーズ完了ベースの近似。偽の残り時間は出さない） ----
function _autorunProgressPercent(status) {
  if (status === 'complete') return 100;
  const normalizedStatus = status === 'awaiting_input' ? 'discovering'
    : status === 'generating_document_mbt' ? 'generating_qa'
    : status;
  const idx = AUTORUN_PHASE_ORDER.indexOf(normalizedStatus);
  if (idx < 0) return 0;
  let pct = 0;
  for (let i = 0; i < idx; i++) pct += AUTORUN_PHASE_WEIGHTS[AUTORUN_PHASE_ORDER[i]];
  pct += AUTORUN_PHASE_WEIGHTS[AUTORUN_PHASE_ORDER[idx]] * 0.5;
  return Math.round(pct);
}

// ---- AutoRun: ステッパー ----
function _autorunStepMeta(data) {
  const sd = data.step_data || {};
  const meta = {};
  if (sd.crawl && sd.crawl.screens != null) {
    meta['ars-crawl'] = `${sd.crawl.screens}画面 / ${sd.crawl.forms || 0}フォーム`;
  }
  if (sd.qa && sd.qa.count) meta['ars-qa'] = `${sd.qa.count}件の成果物`;
  if (sd.document_mbt) {
    const rate = Math.round(Number(sd.document_mbt.coverage_rate || 0) * 100);
    meta['ars-qa'] = `要件${sd.document_mbt.requirements || 0}件 / パス${sd.document_mbt.paths || 0}件 / カバー${rate}%`;
  }
  if (sd.scripts && sd.scripts.all != null) meta['ars-scripts'] = `${sd.scripts.all}件のテストケース`;
  const policy = data.run_policy || {};
  if (policy.filter_mode) {
    const labels = { all: '全テスト', smoke: 'スモーク', transition: '遷移', form: 'フォーム' };
    meta['ars-approval'] = `${labels[policy.filter_mode] || policy.filter_mode}を承認済み`;
  }
  const r = data.test_results || {};
  const tp = data.test_progress;
  if (data.status === 'running_tests' && tp && (tp.passed || tp.failed)) {
    // 実行中の実況（R3-01）: 完了集計を待たず途中経過を出す
    meta['ars-running'] = `PASS ${tp.passed || 0} / FAIL ${tp.failed || 0}（実行中）`;
  } else if (r.total != null) {
    meta['ars-running'] = r.unavailable ? '実行不可' : `PASS ${r.passed || 0} / FAIL ${r.failed || 0}`;
  }
  return meta;
}

function _autorunUpdateStepper(data) {
  const status = data.status || 'idle';
  const activeStepId = AUTORUN_STEP_MAP[status];
  const stepOrder = ['ars-crawl','ars-qa','ars-scripts','ars-approval','ars-running','ars-done'];
  const activeIdx = stepOrder.indexOf(activeStepId);
  const isError = ['failed','cancelled'].includes(status);
  const isAwaiting = (status === 'awaiting_approval');
  const metas = _autorunStepMeta(data);
  stepOrder.forEach((sid, idx) => {
    const el = document.getElementById(sid);
    if (!el) return;
    // e2e がクラス文字列の完全一致を検証するため、状態クラスの付け方は変えない
    el.className = 'autorun-step-item';
    const icon = el.querySelector('.autorun-step-icon');
    let kind = 'pending';
    if (sid === activeStepId && isError) { el.classList.add('is-error'); kind = 'error'; }
    else if (sid === 'ars-approval' && isAwaiting) { el.classList.add('is-waiting'); kind = 'waiting'; }
    else if (sid === activeStepId && status !== 'complete') { el.classList.add('is-active'); kind = 'active'; }
    else if (idx < activeIdx || status === 'complete') { el.classList.add('is-done'); kind = 'done'; }
    if (icon) icon.innerHTML = AUTORUN_STEP_ICONS[kind];
    const metaEl = document.getElementById(sid + '-meta');
    if (metaEl) metaEl.textContent = metas[sid] || '';
  });

  _autorunSetText('autorun-phase-label', _autorunPhaseLabelWithProgress(status, data));
  const pct = _autorunProgressPercent(status);
  const fill = document.getElementById('autorun-progress-fill');
  const bar = document.getElementById('autorun-progressbar');
  if (fill) {
    fill.style.width = pct + '%';
    fill.classList.toggle('is-error', isError);
    fill.classList.toggle('is-done', status === 'complete');
  }
  if (bar) bar.setAttribute('aria-valuenow', String(pct));

  // ログイン入力を✕で閉じた場合の再開導線
  const note = document.getElementById('autorun-step-note');
  if (note) {
    if (status === 'awaiting_input' && _autoRunLoginSuppressed) {
      note.style.display = '';
      note.replaceChildren();
      const span = document.createElement('span');
      span.textContent = 'ログイン情報の入力を待っています。';
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn-outline-sm';
      btn.textContent = '入力を再開';
      btn.addEventListener('click', () => {
        _autoRunLoginSuppressed = false;
        if (window._autoRunLastData) _autorunRender(window._autoRunLastData);
      });
      note.append(span, btn);
    } else {
      note.style.display = 'none';
    }
  }
}

// ---- AutoRun: ログ（レベルフィルタ + 自動スクロール） ----
function _autorunLogLevelOf(line) {
  if (/\[ERROR\]|エラー/.test(line)) return 'error';
  if (/\[WARN\]|警告/.test(line)) return 'warn';
  return 'info';
}

// クロールCLIの生出力（`[cli] ...`）は開発者向け。既定では非表示にし、
// 「開発者向け詳細を表示」チェックで見られるようにする（生ログがそのまま
// 表示され読みにくい、というドッグフーディング指摘への対応）。
function _autorunIsRawCliLine(line) {
  return /\[cli\]/.test(line);
}

function _autorunRenderLog() {
  const logEl = document.getElementById('autorun-log');
  if (!logEl) return;
  const showRaw = document.getElementById('autorun-log-show-raw')?.checked;
  const lines = _autoRunLogLines.filter(line => {
    if (!showRaw && _autorunIsRawCliLine(line)) return false;
    const lv = _autorunLogLevelOf(line);
    if (_autoRunLogLevel === 'error') return lv === 'error';
    if (_autoRunLogLevel === 'warn') return lv !== 'info';
    return true;
  });
  logEl.innerHTML = lines.map(line => {
    const esc = escHtml(line);
    const lv = _autorunLogLevelOf(line);
    if (lv === 'error') return `<span class="log-error">${esc}</span>`;
    if (lv === 'warn') return `<span class="log-warn">${esc}</span>`;
    if (/\[OK\]|完了|成功|✓/.test(line)) return `<span class="log-ok">${esc}</span>`;
    return esc;
  }).join('\n');
  if (document.getElementById('autorun-log-autoscroll')?.checked) {
    logEl.scrollTop = logEl.scrollHeight;
  }
}

document.querySelectorAll('.autorun-log-filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    _autoRunLogLevel = btn.dataset.logLevel || 'all';
    document.querySelectorAll('.autorun-log-filter-btn').forEach(b =>
      b.classList.toggle('is-active', b === btn));
    _autorunRenderLog();
  });
});
document.getElementById('autorun-log-show-raw')?.addEventListener('change', () => _autorunRenderLog());
document.getElementById('autorun-log-copy')?.addEventListener('click', () => {
  navigator.clipboard.writeText(_autoRunLogLines.join('\n')).then(() => {
    const btn = document.getElementById('autorun-log-copy');
    if (!btn) return;
    const orig = btn.textContent;
    btn.textContent = 'コピーしました';
    setTimeout(() => { btn.textContent = orig; }, 1500);
  }).catch(() => {});
});

// ---- AutoRun: 完了カード（レポート「テスト実行」タブへの導線） ----
function _autorunRenderComplete(data) {
  const card = document.getElementById('autorun-complete-card');
  if (!card) return;
  if (data.status !== 'complete') { card.style.display = 'none'; return; }
  card.style.display = '';
  card.replaceChildren();

  const r = data.test_results || {};
  const unavailable = !!r.unavailable;
  const noTests = !unavailable && (r.total || 0) === 0;
  // evidence-only: 0件は「成功」ではない。実行対象が無かった旨を中立に伝える
  // （0/0/0が無言で「全テスト成功」と表示された致命的UX破綻の再発防止）。
  const ok = !unavailable && !noTests && (r.failed || 0) === 0;

  const head = document.createElement('div');
  head.className = 'autorun-complete-head';
  const icon = document.createElement('div');
  icon.className = 'autorun-complete-icon ' + (unavailable ? 'is-warn' : noTests ? 'is-warn' : ok ? 'is-ok' : 'is-fail');
  icon.textContent = unavailable ? '⚠' : noTests ? '⚠' : ok ? '✓' : '✕';
  const titleWrap = document.createElement('div');
  const title = document.createElement('div');
  title.className = 'autorun-complete-title';
  title.textContent = unavailable
    ? 'AutoRun 完了（テストは実行できませんでした）'
    : noTests ? 'AutoRun 完了 — 実行対象のテストがありませんでした'
    : ok ? 'AutoRun 完了 — 全テスト成功' : 'AutoRun 完了 — 失敗したテストがあります';
  const sub = document.createElement('p');
  sub.className = 'muted-copy';
  sub.textContent = unavailable
    ? (r.error || 'Playwright 実行環境が未セットアップです。レポートの「テスト実行」タブにセットアップ手順があります。')
    : `PASS ${r.passed || 0} ／ FAIL ${r.failed || 0} ／ SKIP ${r.skipped || 0} ／ 全${r.total || 0}件（所要 ${autorunFmtElapsed(data.elapsed_sec || 0)}）`;
  titleWrap.append(title, sub);
  head.append(icon, titleWrap);
  card.appendChild(head);

  const actions = document.createElement('div');
  actions.className = 'autorun-complete-actions';
  if (data.domain) {
    const cta = document.createElement('button');
    cta.type = 'button';
    cta.className = 'btn-primary';
    cta.textContent = 'レポートで結果を見る →';
    cta.addEventListener('click', () => openResultsForDomain(data.domain, 'runs'));
    actions.appendChild(cta);
  }
  const outputs = data.outputs || {};
  // 主導線: 自前の日本語実行レポート（R3-03/04/05）。Playwright ネイティブ
  // （英語・開発者向け）は playwright_native_html があれば副導線として併置する。
  if (outputs.playwright_report_html) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'btn-outline-sm qa-preview-btn';
    b.dataset.path = outputs.playwright_report_html;
    b.dataset.label = 'テスト実行レポート';
    b.textContent = '実行レポート';
    actions.appendChild(b);
  }
  if (outputs.playwright_native_html) {
    const nb = document.createElement('button');
    nb.type = 'button';
    nb.className = 'btn-outline-sm qa-preview-btn';
    nb.dataset.path = outputs.playwright_native_html;
    nb.dataset.label = 'テスト実行レポート（開発者向け）';
    nb.textContent = '詳細（開発者向け・英語）';
    actions.appendChild(nb);
  }
  if (outputs.qa_process_report) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'btn-outline-sm qa-preview-btn';
    b.dataset.path = outputs.qa_process_report;
    b.dataset.label = 'QAレポート';
    b.textContent = 'QAレポート';
    actions.appendChild(b);
  }
  card.appendChild(actions);
}

// ---- AutoRun: レンダリング（status/outputs から冪等に導出） ----
function _autorunRender(data) {
  if (!data) return;
  window._autoRunLastData = data;
  const status = data.status || 'idle';

  // started_at を保存（経過時間計算用）
  if (data.started_at && !_autoRunStartedAt) {
    _autoRunStartedAt = data.started_at;
  }

  // 経過時間（サーバー値で最終確定）
  const elapsedEl = document.getElementById('autorun-elapsed');
  if (elapsedEl && ['complete','failed','cancelled'].includes(status)) {
    elapsedEl.textContent = autorunFmtElapsed(data.elapsed_sec || 0);
  }

  _autorunUpdateStepper(data);

  // ---- ログ ----
  if (data.log) {
    _autoRunLogLines = data.log;
    _autorunRenderLog();
  }

  // ---- ログイン入力ポップアップ ----
  if (status === 'awaiting_input' && data.input_request?.type === 'login' && !_autoRunLoginSuppressed) {
    _autorunShowLoginModal(data.input_request);
  } else {
    _autorunHideLoginModal();
  }
  if (status !== 'awaiting_input') _autoRunLoginSuppressed = false;

  // ---- 承認モーダル自動表示 ----
  if (status === 'awaiting_approval' && !_autoRunApprovalModalShown) {
    _autoRunApprovalModalShown = true;
    _autorunPrepareAndShowApprovalModal();
  }
  if (status !== 'awaiting_approval') {
    _autorunHideApprovalModal();
  }

  _autorunRenderComplete(data);
  _autorunRenderFailurePanel(data);

  // ---- テスト実行中のライブプレビュー ----
  if (status === 'running_tests' && data.domain) {
    _autorunStartLivePreview(data.domain);
  } else {
    _autorunStopLivePreview();
  }

  // ---- テスト実行中の実況（OK/NGリスト。R3-01） ----
  _autorunRenderLiveTests(data);

  // ---- 停止ボタン ----
  const cancelArea = document.getElementById('autorun-cancel-area');
  const activeStatuses = ['discovering','awaiting_input','crawling','generating_qa','generating_document_mbt','generating_scripts','running_tests'];
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
    autorunResume(); // 最近の実行リストを更新
  }

  // ---- エラー表示 ----
  if (data.error) {
    autorunSetStartStatus(data.error, true);
  }

  // ---- 成果物リンク（左サイドバー・SDLCフェーズ別グルーピング） ----
  if (data.outputs && Object.keys(data.outputs).length) {
    const linksEl = document.getElementById('autorun-output-links');
    const area    = document.getElementById('autorun-outputs-area');
    if (linksEl && area) {
      area.style.display = '';
      const grouped = {};
      Object.entries(data.outputs).filter(([,p]) => p).forEach(([key, path]) => {
        const category = AUTORUN_OUTPUT_CATEGORIES[key] || 'その他';
        (grouped[category] = grouped[category] || []).push([key, path]);
      });
      const categories = AUTORUN_OUTPUT_CATEGORY_ORDER.filter(c => grouped[c])
        .concat(Object.keys(grouped).filter(c => !AUTORUN_OUTPUT_CATEGORY_ORDER.includes(c)));
      linksEl.innerHTML = categories.map(category => {
        const items = grouped[category].map(([key, path]) => {
          const label = AUTORUN_OUTPUT_LABELS[key] || key;
          return `<div class="qa-output-item">
            <span class="qa-output-item-label" title="${escHtml(label)}">${escHtml(label)}</span>
            <div class="qa-output-item-actions">
              <button class="btn-outline-sm qa-output-btn qa-preview-btn" data-path="${escHtml(path)}" data-label="${escHtml(label)}">プレビュー</button>
            </div></div>`;
        }).join('');
        return `<div class="qa-output-category"><div class="qa-output-category-title">${escHtml(category)}</div>${items}</div>`;
      }).join('');
    }
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
// R3-13: ヘルプオーバーレイを開いたままログイン要求が来ると、ヘルプが前面に
// 重なって入力欄がクリック不能になる（z-index競合）＋ Esc がヘルプ側だけに
// 奪われる（core.jsのグローバルkeydownはヘルプしか閉じない）という競合があった。
// core.js は編集せず、(1) 表示時にヘルプを明示的に閉じる、(2) ログインモーダル
// 表示中だけ有効なEscハンドラを登録する、(3) z-indexをヘルプより前面にする
// （static/css/components.css の #autorun-login-modal）ことで解消する。
function _autorunLoginEscHandler(e) {
  if (e.key !== 'Escape') return;
  e.stopPropagation();
  autorunDismissLoginModal();
}

function _autorunShowLoginModal(inputRequest) {
  const modal = document.getElementById('autorun-login-modal');
  if (!modal || !modal.classList.contains('hidden')) return; // 既に表示中
  const msgEl  = document.getElementById('autorun-login-msg');
  const urlEl  = document.getElementById('autorun-login-url');
  if (msgEl) msgEl.textContent = inputRequest.message || 'ログインが必要です。';
  if (urlEl) urlEl.value = inputRequest.login_url || '';
  if (typeof toggleShortcutHelp === 'function') toggleShortcutHelp(false);
  // 先に hidden を外してから focus する（非表示要素への focus は効かないため）
  modal.classList.remove('hidden');
  document.getElementById('autorun-login-username')?.focus();
  document.addEventListener('keydown', _autorunLoginEscHandler);
}

function _autorunHideLoginModal() {
  document.getElementById('autorun-login-modal')?.classList.add('hidden');
  document.removeEventListener('keydown', _autorunLoginEscHandler);
}

// ✕で閉じる: スキップせず入力待ちのまま（誤操作でスキップさせない）。再開はステッパー下の導線から。
function autorunDismissLoginModal() {
  _autoRunLoginSuppressed = true;
  _autorunHideLoginModal();
  if (window._autoRunLastData) _autorunRender(window._autoRunLastData);
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
function _autorunInitPreviewModal() {
  const panel = document.getElementById('autorun-preview-panel');
  if (panel && !panel._backdropBound) {
    panel.addEventListener('click', _autorunClosePreviewOnBackdrop);
    panel._backdropBound = true;
  }
}

function autorunReset() {
  _autoRunJobId               = null;
  _autoRunStartedAt           = null;
  _autoRunPreviewLoaded       = false;
  _autoRunPreviewData         = null;
  _autoRunApprovalModalShown  = false;
  _autoRunLoginSuppressed     = false;
  _autoRunLogLines            = [];
  window._autoRunLastData     = null;
  _autorunStopPolling();
  _autorunStopElapsed();
  _autorunStopLivePreview();
  _autorunHideApprovalModal();
  _autorunHideLoginModal();
  document.getElementById('autorun-steps').style.display          = 'none';
  document.getElementById('autorun-outputs-area').style.display   = 'none';
  document.getElementById('ar-log-section').style.display         = 'none';
  document.getElementById('autorun-complete-card').style.display  = 'none';
  document.getElementById('autorun-failure-panel').style.display  = 'none';
  document.getElementById('autorun-preview-panel').style.display  = 'none';
  document.getElementById('autorun-cancel-area').style.display    = 'none';
  document.getElementById('autorun-restart-area').style.display   = 'none';
  document.getElementById('autorun-idle-msg').style.display       = '';
  document.getElementById('autorun-start-btn').disabled = false;
  document.getElementById('autorun-start-btn').textContent = '開始';
  document.getElementById('autorun-url').value = '';
  _autorunResetDocumentMode();
  const viewpointSelect = document.getElementById('autorun-viewpoint-set');
  if (viewpointSelect) viewpointSelect.value = '';
  autorunLoadViewpointSelection();
  document.getElementById('autorun-elapsed').textContent = '0:00';
  const completeCard = document.getElementById('autorun-complete-card');
  if (completeCard) completeCard.replaceChildren();
  const failureBody = document.getElementById('autorun-failure-body');
  if (failureBody) failureBody.innerHTML = '';
  const logPre = document.getElementById('autorun-log');
  if (logPre) logPre.textContent = '';
  const liveTestsArea = document.getElementById('autorun-live-tests-area');
  if (liveTestsArea) liveTestsArea.innerHTML = '';
  autorunSetStartStatus('', false);
}

document.getElementById('autorun-viewpoint-set')?.addEventListener('change', _autorunRenderViewpointRecommendation);
document.getElementById('autorun-url')?.addEventListener('input', () => {
  clearTimeout(_autorunViewpointTimer);
  _autorunViewpointTimer = setTimeout(autorunLoadViewpointSelection, 350);
});
