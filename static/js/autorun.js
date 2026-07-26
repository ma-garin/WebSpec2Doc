// ====================== AutoRun ======================
let _autoRunJobId = null;
let _autoRunPollTimer = null;
let _autoRunElapsedTimer = null;
let _autoRunStartedAt = null;  // ISO string from server
let _autoRunStagesDomain = null;  // 段階承認パイプラインを読み込み済みのドメイン
let _autoRunStagesOpened = false; // 承認待ちでフェーズ画面を開いたか
let _autoRunPreviewLoaded = false;
let _autoRunPreviewData = null;
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
  awaiting_stages:   'ars-qa',
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
  awaiting_stages: '承認待ち — テスト目的〜ケースを確認してください',
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
const AUTORUN_PHASE_ORDER = ['discovering', 'crawling', 'generating_qa', 'awaiting_stages', 'generating_scripts', 'awaiting_approval', 'running_tests'];
const AUTORUN_PHASE_WEIGHTS = { discovering: 10, crawling: 40, generating_qa: 15, awaiting_stages: 5, generating_scripts: 10, awaiting_approval: 5, running_tests: 15 };

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

// 成果物のまとめ方は「いつ開くか」で分ける（3束）。
// 以前は SDLC の工程名（計画/分析/設計/実装/実行/レポート）で並べていたが、
// これは作った側の都合の並びで、「まず何を開けばよいか」に答えていなかった。
const AUTORUN_OUTPUT_CATEGORY_ORDER = ['結果を見る', '根拠を確かめる', '持ち出す'];
const AUTORUN_OUTPUT_CATEGORY_HINTS = {
  '結果を見る':     'まずここだけ見れば判断できる',
  '根拠を確かめる': '結果に納得できないとき',
  '持ち出す':       '報告・提出・再利用',
};
const AUTORUN_OUTPUT_CATEGORIES = {
  // 1. 結果を見る — 実行直後に開く、結論と判断材料
  playwright_report_html:  '結果を見る',
  qa_process_report:       '結果を見る',
  cross_review:            '結果を見る',
  // 2. 根拠を確かめる — 結論を追うときに開く
  report_html:             '根拠を確かめる',
  test_cases:              '根拠を確かめる',
  test_design:             '根拠を確かめる',
  test_analysis:           '根拠を確かめる',
  model_graph:             '根拠を確かめる',
  viewpoint_snapshot:      '根拠を確かめる',
  test_plan:               '根拠を確かめる',
  playwright_native_html:  '根拠を確かめる',
  // 3. 持ち出す — 提出・再利用のために取り出す
  report_json:             '持ち出す',
  playwright_candidates_html: '持ち出す',
  spec_ts:                 '持ち出す',
  playwright_report_json:  '持ち出す',
};

// 成果物カードに出す主要数値。「その成果物で何が分かったか」を1つだけ示す。
// 実測値が無いものは数を捏造せず、動作（開く）を出す。
function _autorunOutputMetric(key, data) {
  const step = (data && data.step_data) || {};
  const crawl = step.crawl || {};
  const qa = step.qa || {};
  const scripts = step.scripts || {};
  const result = (data && data.test_results) || {};

  switch (key) {
    case 'playwright_report_html':
    case 'playwright_report_json': {
      const failed = Number(result.failed || 0);
      const passed = Number(result.passed || 0);
      const total = failed + passed;
      if (!total) return { num: '開く', sub: '', alert: false };
      return {
        num: total + '件',
        sub: failed ? `失敗${failed} / 成功${passed}` : `全${total}件成功`,
        alert: failed > 0,
      };
    }
    case 'report_html':
    case 'report_json':
      return crawl.screens
        ? { num: crawl.screens + '画面', sub: crawl.forms ? `フォーム${crawl.forms}件` : '', alert: false }
        : { num: '開く', sub: '', alert: false };
    case 'test_cases':
      return scripts.count
        ? { num: scripts.count + '件', sub: '', alert: false }
        : { num: '開く', sub: '', alert: false };
    case 'viewpoint_snapshot':
      return qa.viewpoint_count
        ? { num: qa.viewpoint_count + '観点', sub: qa.viewpoint_set || '', alert: false }
        : { num: '開く', sub: '', alert: false };
    case 'qa_process_report':
      return qa.count
        ? { num: qa.count + '件', sub: '成果物', alert: false }
        : { num: '開く', sub: '', alert: false };
    case 'cross_review': {
      // 横断レビューは指摘件数が判断材料そのもの。0件でも「0件」と出す。
      const findings = Number((step.review || {}).findings ?? NaN);
      if (Number.isNaN(findings)) return { num: '開く', sub: '', alert: false };
      return { num: findings + '件', sub: '指摘', alert: findings > 0 };
    }
    case 'test_design':
    case 'test_analysis':
      return qa.viewpoint_count
        ? { num: qa.viewpoint_count + '観点', sub: '', alert: false }
        : { num: '開く', sub: '', alert: false };
    case 'model_graph':
      return crawl.screens
        ? { num: crawl.screens + '画面', sub: '遷移モデル', alert: false }
        : { num: '開く', sub: '', alert: false };
    case 'playwright_candidates_html':
    case 'spec_ts':
      return scripts.count
        ? { num: scripts.count + '件', sub: '自動化候補', alert: false }
        : { num: '開く', sub: '', alert: false };
    case 'test_plan':
      return crawl.screens
        ? { num: crawl.screens + '画面', sub: '対象範囲', alert: false }
        : { num: '開く', sub: '', alert: false };
    case 'playwright_native_html':
      return { num: '開く', sub: '開発者向け', alert: false };
    default:
      return { num: '開く', sub: '', alert: false };
  }
}

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
  // 明示的なエラー・通知は、入力のたびに走る活性判定に上書きさせない。
  if (isError && msg) el.dataset.sticky = '1';
  else delete el.dataset.sticky;
}

function autorunFmtElapsed(sec) {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2,'0')}`;
}

// 待機の残り時間を人に読める粒度で返す。秒単位のカウントダウンは急かすだけなので出さない。
function autorunFmtRemaining(sec) {
  const n = Number(sec || 0);
  if (n <= 0) return '';
  if (n >= 3600) {
    const h = Math.floor(n / 3600);
    const m = Math.round((n % 3600) / 60);
    return m ? `約${h}時間${m}分` : `約${h}時間`;
  }
  if (n >= 60) return `約${Math.round(n / 60)}分`;
  return '1分未満';
}

// 未確認事項パネル。空なら何も描かない（無いものを大げさに出さない）。
// 「実行した」と「確認できた」は別物。この区別が消えると成果物が過大に読まれる。
function _autorunUnverifiedPanel(data) {
  const frag = document.createDocumentFragment();
  const items = (data && data.unverified) || [];
  if (!items.length) return frag;
  const box = document.createElement('section');
  box.className = 'autorun-unverified';
  box.setAttribute('role', 'note');
  const head = document.createElement('div');
  head.className = 'autorun-unverified-head';
  head.textContent = `未確認のまま残った事項 ${items.length} 件`;
  box.appendChild(head);
  const lead = document.createElement('p');
  lead.className = 'muted-copy';
  lead.textContent = 'これらは「問題なし」ではなく「確認していない」という意味です。';
  box.appendChild(lead);
  const ul = document.createElement('ul');
  ul.className = 'autorun-unverified-list';
  items.forEach((text) => {
    const li = document.createElement('li');
    li.textContent = String(text);
    ul.appendChild(li);
  });
  box.appendChild(ul);
  frag.appendChild(box);
  return frag;
}

// 待機に期限があることを、期限そのものと「切れたら何が起きるか」まで含めて説明する。
// 期限を隠すと、時間切れは「黙って承認された」のと区別がつかなくなる。
function _autorunDeadlineNote(data) {
  const remain = autorunFmtRemaining((data || {}).awaiting_remaining_sec);
  if (!remain) {
    return '確認せずに実行することもできます。その場合は「人の確認を経ていない」と成果物に記録されます。';
  }
  return `確認の期限はあと${remain}です。過ぎた場合は未確認のまま後続へ進み、`
    + '「人の確認を経ていない」と成果物に記録されます。';
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

// 仕様4: 過去に解析したサイトをURL入力の候補として出す。
// AutoRun の受付には独自の datalist を持たせる（別画面の url-history-list は
// ドキュメント作成側のもので、AutoRun からは埋まらなかった）。
async function autorunLoadUrlSuggestions() {
  const list = document.getElementById('autorun-url-suggestions');
  if (!list) return;
  try {
    const data = await fetch('/api/history').then(r => r.json());
    const urls = (data.items || [])
      .map(item => String(item.site_url || '').trim())
      .filter(Boolean);
    list.replaceChildren(...urls.map(url => {
      const option = document.createElement('option');
      option.value = url;
      return option;
    }));
  } catch (e) {
    // 候補が出せなくても入力自体は妨げない
  }
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
    // 観点セットが読めたことは「開始できる」ことを意味しない。
    // URL 未入力などの理由が残っていれば無効のままにする（判定は1箇所に集約）。
    autorunSyncStartButton();
  } catch (error) {
    note.textContent = `観点セットを固定できません: ${error.message}。観点管理で既定公開版を確認してください。`;
    note.classList.add('is-error');
    document.getElementById('autorun-start-btn').disabled = true;
    autorunSetStartStatus('観点セットを読み込めないため開始できません。', true);
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

  const activeStatuses = ['discovering', 'awaiting_input', 'crawling', 'generating_qa', 'awaiting_stages', 'generating_document_mbt', 'generating_scripts', 'awaiting_approval', 'running_tests'];
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
  // スクリーンショットは「まだ無い」のが正常な状態。img へ直接 404 を踏ませると
  // 実行中ずっとコンソールにエラーが出続け、本物の異常が埋もれる。
  // 取得できたときだけ表示する。
  const poll = async () => {
    const image = document.getElementById('autorun-preview-image');
    const placeholder = document.getElementById('autorun-preview-placeholder');
    if (!image || !placeholder) return;
    const url = `/api/autorun/live-screenshot?domain=${encodeURIComponent(_autoRunLivePreviewDomain)}&t=${Date.now()}`;
    try {
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) return; // 未生成。次のポーリングを待つ
      const blob = await res.blob();
      const objectUrl = URL.createObjectURL(blob);
      const previous = image.dataset.objectUrl;
      image.src = objectUrl;
      image.dataset.objectUrl = objectUrl;
      if (previous) URL.revokeObjectURL(previous);
      image.classList.add('show');
      placeholder.classList.add('hidden');
    } catch (_e) {
      // 取得失敗は表示を変えない（前回の画面を残す）
    }
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
  if (image) {
    image.classList.remove('show');
    // blob URL は明示的に解放しないとタブが持ち続ける。
    if (image.dataset.objectUrl) {
      URL.revokeObjectURL(image.dataset.objectUrl);
      delete image.dataset.objectUrl;
    }
  }
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

  // 「成功」の隣に「確認していない範囲」を必ず置く。
  // 未確認を黙ると、全テスト成功が「全部問題なし」と読まれる。
  card.appendChild(_autorunUnverifiedPanel(data));

  const actions = document.createElement('div');
  actions.className = 'autorun-complete-actions';
  if (data.domain) {
    // 仕様16: AutoRun の結果は専用ページで開く（SPA のタブではない）
    const cta = document.createElement('a');
    cta.className = 'btn-primary';
    cta.textContent = '実行結果レポートを開く →';
    cta.href = `/autorun/report/${encodeURIComponent(data.domain)}`;
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
// ログイン壁で止まったときの説明。判定根拠と取得できた範囲を示す。
// ログに1行流すだけでは「なぜ止まったか」が分からない。
function _autorunRenderLoginStop(data) {
  const host = document.getElementById('autorun-login-stop');
  if (!host) return;
  const req = data.input_request || {};
  const step = data.step_data || {};
  const discovered = step.discover || {};
  host.style.display = '';
  host.replaceChildren();

  const title = document.createElement('div');
  title.className = 'autorun-stop-title';
  title.textContent = 'このサイトはログインが必要です';
  host.appendChild(title);

  const body = document.createElement('p');
  body.className = 'autorun-stop-body';
  body.textContent = req.message
    || '未ログインで到達できる範囲まで取得しました。この先へ進むには認証が必要です。';
  host.appendChild(body);

  const fact = document.createElement('div');
  fact.className = 'autorun-stop-fact';
  const reachable = Number(discovered.pages || 0) - Number(discovered.login_required || 0);
  fact.textContent =
    `判定根拠: ${req.login_url || '対象URL'} でログインフォームを検出しました`
    + ` ／ 取得できた範囲: ${Math.max(reachable, 0)}画面`
    + ` ／ 到達できなかった: ${Number(discovered.login_required || 0)}画面`;
  host.appendChild(fact);

  const hint = document.createElement('p');
  hint.className = 'autorun-stop-hint';
  hint.textContent =
    '「未ログインのまま進む」を選ぶと、成果物に「未ログイン範囲のみ」と明記されます。';
  host.appendChild(hint);
}

function _autorunHideLoginStop() {
  const host = document.getElementById('autorun-login-stop');
  if (host) { host.style.display = 'none'; host.replaceChildren(); }
}

// 未ログインのまま進む。選ばなかったことを記録として残す。
async function _autorunSkipLogin(jobId) {
  if (!jobId) return;
  try {
    await fetch('/api/autorun/submit-input', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId, type: 'skip' }),
    });
    _autorunHideLoginStop();
  } catch (e) {
    console.error('[autorun] スキップに失敗しました', e);
  }
}

// 主導線バー: いま何が起きていて、次に何を押すかを最上部に常設する。
// 段階承認中は autorun-stages.js が上書きするので、ここでは扱わない。
function _autorunRenderLeadBar(data, status) {
  const bar = window.autorunLeadBar;
  if (!bar) return;

  if (status === 'awaiting_stages') return;

  if (status !== 'awaiting_input') _autorunHideLoginStop();
  if (status === 'idle' || !status) { bar.hide(); return; }

  if (status === 'awaiting_input') {
    // 無言で「取得できた範囲」を進めない。止めて、判定根拠と選択肢を出す。
    // ログインモーダルを開いている間は、バー側の操作はオーバーレイに遮られて
    // 押せない（実測）。押せないボタンを出さないため、操作はモーダルへ一本化する。
    const modalOpen = _autorunLoginModalIsOpen();
    const remain = autorunFmtRemaining(data.awaiting_remaining_sec);
    bar.set({
      tone: 'stop',
      // 「停止中」は中止操作の結果と紛らわしい。ここは人の入力を待っている状態。
      title: '入力待ち — ログインが必要です',
      meta: remain
        ? `あなたの選択を待っています（あと${remain}で未ログインのまま続行）`
        : 'あなたの選択を待っています',
      actions: modalOpen ? [] : [
        {
          label: 'ログイン情報を設定して続ける',
          onClick: () => { _autoRunLoginSuppressed = false; _autorunShowLoginModal(data.input_request); },
        },
        {
          label: '未ログインのまま進む',
          kind: 'ghost',
          onClick: () => _autorunSkipLogin(data.job_id),
        },
      ],
    });
    _autorunRenderLoginStop(data);
    return;
  }

  if (['complete', 'failed', 'cancelled'].includes(status)) {
    const result = data.test_results || {};
    const failed = Number(result.failed || 0);
    const label = status === 'complete'
      ? (failed ? `完了 — 失敗 ${failed} 件` : '完了')
      : (status === 'cancelled' ? '停止しました' : '失敗しました');
    bar.set({
      tone: status === 'complete' && !failed ? 'done' : (status === 'complete' ? 'blocked' : 'stop'),
      title: label,
      meta: autorunFmtElapsed(data.elapsed_sec || 0),
      actions: [],
    });
    return;
  }

  // 処理中: 何をしているか＋進捗を出す。操作は中止のみ。
  bar.set({
    tone: 'busy',
    title: data.step_label || '実行中',
    meta: _autorunLeadBarProgress(data),
    actions: [{ label: '中止する', onClick: autorunCancel, kind: 'danger' }],
  });
}

// バーに出す進捗。実測できている数だけを出し、無ければ経過時間だけにする。
function _autorunLeadBarProgress(data) {
  const step = data.step_data || {};
  const parts = [];
  if (step.crawl && step.crawl.screens) parts.push(`${step.crawl.screens}画面`);
  if (step.qa && step.qa.count) parts.push(`成果物${step.qa.count}件`);
  parts.push(`経過 ${autorunFmtElapsed(data.elapsed_sec || 0)}`);
  return parts.join(' ・ ');
}

function _autorunRender(data) {
  if (!data) return;
  window._autoRunLastData = data;
  const status = data.status || 'idle';

  // 段階承認パイプライン（仕様7〜14）: ドメインが確定した時点で読み込む。
  // 承認待ちに入ったらフェーズ画面を開く（それ以外では画面を奪わない）。
  if (data.domain && window.autorunStages) {
    const atGate = status === 'awaiting_stages';
    if (_autoRunStagesDomain !== data.domain || (atGate && !_autoRunStagesOpened)) {
      _autoRunStagesDomain = data.domain;
      _autoRunStagesOpened = atGate;
      window.autorunStages.load(data.domain, { open: atGate });
      // 要確認チェックリスト: 人が見るべき項目だけを同じタイミングで読み込む
      if (window.autorunReview) window.autorunReview.load(data.domain);
    }
    if (!atGate) _autoRunStagesOpened = false;
  }

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
  _autorunRenderLeadBar(data, status);

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
      linksEl.innerHTML = categories.map((category, index) => {
        const items = grouped[category].map(([key, path]) => {
          const label = AUTORUN_OUTPUT_LABELS[key] || key;
          const summary = _autorunOutputMetric(key, data);
          // カード全体を押せるようにし、同じ「プレビュー」ボタンの繰り返しを廃止する
          return `<button type="button" class="qa-output-item qa-preview-btn"
              data-path="${escHtml(path)}" data-label="${escHtml(label)}">
            <span class="qa-output-item-text">
              <span class="qa-output-item-label">${escHtml(label)}</span>
              ${summary.sub ? `<span class="qa-output-item-sub">${escHtml(summary.sub)}</span>` : ''}
            </span>
            <span class="qa-output-item-num${summary.alert ? ' is-alert' : ''}">${escHtml(summary.num)}</span>
          </button>`;
        }).join('');
        const hint = AUTORUN_OUTPUT_CATEGORY_HINTS[category] || '';
        return `<div class="qa-output-category">
          <div class="qa-output-category-title">
            <span class="qa-output-bundle-no">${index + 1}</span>
            <span>${escHtml(category)}</span>
            ${hint ? `<span class="qa-output-bundle-when">${escHtml(hint)}</span>` : ''}
          </div>${items}</div>`;
      }).join('');
    }
  }
}

// ---- AutoRun: 停止 ----
async function autorunCancel() {
  if (!_autoRunJobId) return;
  // 中止はやり直しが効かない（再開手段が無く、最初からになる）。
  // 押した瞬間に破棄せず、失うものを示してから確認する。
  const ok = window.confirm(
    'この実行を中止します。\n\n'
    + '中止すると、ここまでの生成物は残りますが実行は再開できません。'
    + 'もう一度最初から実行し直す必要があります。\n\n中止しますか？'
  );
  if (!ok) return;
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

// モーダル表示中はオーバーレイが背面の操作を奪う。バー側に押せないボタンを
// 出さないための判定（見えているのに押せない状態を作らない）。
function _autorunLoginModalIsOpen() {
  const modal = document.getElementById('autorun-login-modal');
  return !!modal && !modal.classList.contains('hidden');
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
  _autoRunLoginSuppressed     = false;
  _autoRunLogLines            = [];
  window._autoRunLastData     = null;
  _autoRunStagesDomain        = null;
  _autoRunStagesOpened        = false;
  _autorunStopPolling();
  _autorunStopElapsed();
  _autorunStopLivePreview();
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
  document.getElementById('autorun-start-btn').textContent = '開始';
  document.getElementById('autorun-url').value = '';
  _autorunResetDocumentMode();
  const viewpointSelect = document.getElementById('autorun-viewpoint-set');
  if (viewpointSelect) viewpointSelect.value = '';
  autorunLoadViewpointSelection();
  // URL を空に戻した以上、開始ボタンは再び「押せない」が正しい状態。
  autorunSyncStartButton();
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
