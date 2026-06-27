// ====================== AutoRun ======================
let _autoRunJobId = null;
let _autoRunPollTimer = null;
let _autoRunElapsedTimer = null;
let _autoRunStartedAt = null;  // ISO string from server
let _autoRunPreviewLoaded = false;
let _autoRunPreviewData = null;
let _arCards = {};  // 生成済みカード管理: {crawl, qa, scripts, tests}
let _autoRunApprovalModalShown = false;
let _autorunViewpointSets = [];
let _autorunViewpointRecommendation = null;
let _autorunViewpointTimer = null;

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

const AUTORUN_STATUS_META = {
  idle: {
    current: '待機中',
    reason: 'URL解析を開始できます',
    estimate: '10画面で約2〜3分',
    next: '対象URLを入力して開始',
  },
  discovering: {
    current: '画面分析中',
    reason: 'ログイン壁や解析対象URLを確認しています',
    estimate: '数十秒',
    next: '解析結果を待機',
  },
  awaiting_input: {
    current: '入力待ち',
    reason: 'ログインが必要な画面を検出しました',
    estimate: 'ユーザー入力後に再開',
    next: 'ログイン情報を入力またはスキップ',
  },
  crawling: {
    current: '仕様書生成中',
    reason: '対象画面をクロールして画面構造を取得しています',
    estimate: '画面数に応じて変動',
    next: 'QA成果物生成へ進む',
  },
  generating_qa: {
    current: 'QA成果物生成中',
    reason: '仕様書からテスト計画・設計・ケースを作っています',
    estimate: '1分前後',
    next: 'スクリプト生成へ進む',
  },
  generating_scripts: {
    current: 'スクリプト生成中',
    reason: 'Playwright候補を実行可能なspecへ変換しています',
    estimate: '数十秒',
    next: '実行範囲の承認',
  },
  awaiting_approval: {
    current: '承認待ち',
    reason: 'スクリプト生成が完了しました',
    estimate: '承認後にテスト開始',
    next: 'モーダルで実行対象を選択',
  },
  running_tests: {
    current: 'テスト実行中',
    reason: '承認済みのPlaywrightテストを実行しています',
    estimate: 'テスト件数とタイムアウト設定に応じて変動',
    next: '実行結果を確認',
  },
  complete: {
    current: '完了',
    reason: '成果物と実行結果を生成しました',
    estimate: '完了',
    next: '結果と成果物を確認',
  },
  failed: {
    current: '失敗',
    reason: '処理中に復旧が必要なエラーが発生しました',
    estimate: '復旧後に再実行',
    next: '失敗の見立てを確認',
  },
  cancelled: {
    current: '停止済み',
    reason: 'ユーザー操作でAutoRunを停止しました',
    estimate: '停止済み',
    next: '必要なら新しく実行',
  },
};

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
  playwright_report_json:  '実行結果 JSON',
  viewpoint_snapshot:      '観点スナップショット',
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

function _autorunOutputSummary(data) {
  const outputs = data.outputs || {};
  const labels = Object.keys(outputs)
    .filter(key => outputs[key])
    .map(key => AUTORUN_OUTPUT_LABELS[key] || key);
  const result = data.test_results || {};
  if (result.total != null) {
    labels.push(`テスト結果 PASS:${result.passed || 0} FAIL:${result.failed || 0}`);
  }
  return labels.length ? labels.slice(0, 4).join(' / ') : 'まだありません';
}

function _autorunUpdateStatusPanel(data) {
  const panel = document.getElementById('autorun-status-panel');
  if (!panel) return;
  panel.style.display = '';
  const status = data.status || 'idle';
  const meta = AUTORUN_STATUS_META[status] || AUTORUN_STATUS_META.idle;
  _autorunSetText('autorun-current-step', data.step_label || meta.current);
  _autorunSetText('autorun-current-reason', data.error || meta.reason);
  _autorunSetText('autorun-estimate', meta.estimate);
  _autorunSetText('autorun-next-action', meta.next);
  _autorunSetText('autorun-partial-output', _autorunOutputSummary(data));
  const viewpoint = data.viewpoint || {};
  _autorunSetText(
    'autorun-applied-viewpoint',
    viewpoint.set_name
      ? `${viewpoint.set_name} v${viewpoint.version} / ${viewpoint.count}件 / ${viewpoint.selection_reason}`
      : '開始時に公開版を固定します',
  );
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
    select.innerHTML = '<option value="">自動選択</option>' + _autorunViewpointSets.map((item) =>
      `<option value="${escHtml(item.id)}">${escHtml(item.name)} v${Number(item.published_version || 0)}</option>`
    ).join('');
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

// ---- AutoRun: 開始 ----
async function autorunStart() {
  const url = (document.getElementById('autorun-url')?.value || '').trim();
  if (!url) { autorunSetStartStatus('URLを入力してください。', true); return; }

  const depth    = document.getElementById('autorun-depth')?.value || '2';
  const maxPages = document.getElementById('autorun-max-pages')?.value || '30';
  const viewpointSetId = document.getElementById('autorun-viewpoint-set')?.value || '';

  const btn = document.getElementById('autorun-start-btn');
  if (btn) { btn.disabled = true; btn.textContent = '開始中…'; }
  autorunSetStartStatus('', false);

  try {
    const res = await fetch('/api/autorun/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url,
        depth: parseInt(depth),
        max_pages: parseInt(maxPages),
        viewpoint_set_id: viewpointSetId,
      }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || '開始に失敗しました');
    _autoRunJobId  = data.job_id;
    _autoRunStartedAt = null;
    _autorunInitPreviewModal();
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
  document.getElementById('ar-log-section').style.display = '';
  document.getElementById('autorun-status-panel').style.display = '';
  document.getElementById('autorun-idle-msg').style.display = 'none';
  document.getElementById('autorun-preview-panel').style.display = 'none';
  document.getElementById('autorun-result-panel').style.display = 'none';
  document.getElementById('autorun-failure-panel').style.display = 'none';
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
  _autorunUpdateStatusPanel(data);

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
  const isAwaiting = (status === 'awaiting_approval');
  stepOrder.forEach((sid, idx) => {
    const el = document.getElementById(sid);
    if (!el) return;
    el.className = 'autorun-step-item';
    const icon = el.querySelector('.autorun-step-icon');
    if (sid === activeStepId && isError) {
      el.classList.add('is-error'); icon.textContent = '✕';
    } else if (sid === 'ars-approval' && isAwaiting) {
      el.classList.add('is-waiting'); icon.textContent = '⏳';
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
    logEl.innerHTML = data.log.map(line => {
      const esc = escHtml(line);
      if (/\[ERROR\]|エラー/.test(line)) return `<span class="log-error">${esc}</span>`;
      if (/\[WARN\]|警告/.test(line)) return `<span class="log-warn">${esc}</span>`;
      if (/\[OK\]|完了|成功|✓/.test(line)) return `<span class="log-ok">${esc}</span>`;
      return esc;
    }).join('\n');
    logEl.scrollTop = logEl.scrollHeight;
  }

  // ---- ログイン入力ポップアップ ----
  if (status === 'awaiting_input' && data.input_request?.type === 'login') {
    _autorunShowLoginModal(data.input_request);
  } else {
    _autorunHideLoginModal();
  }

  // ---- 承認モーダル自動表示 ----
  if (status === 'awaiting_approval' && !_autoRunApprovalModalShown) {
    _autoRunApprovalModalShown = true;
    _autorunPrepareAndShowApprovalModal();
  }
  if (status !== 'awaiting_approval') {
    _autorunHideApprovalModal();
  }

  // ---- タイムラインカード更新 ----
  _autorunUpdateTimeline(data);
  _autorunRenderResults(data.test_results || {}, data.outputs || {});
  _autorunRenderFailurePanel(data);

  // ---- 承認ボタン（サイドバー） ----
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

  // ---- 成果物リンク（左サイドバー） ----
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
              <button class="btn-outline-sm qa-output-btn qa-preview-btn" data-path="${escHtml(path)}" data-label="${escHtml(label)}">プレビュー</button>
            </div></div>`;
        }).join('');
    }
  }
}

// ---- AutoRun: タイムラインカード管理 ----
function _autorunUpdateTimeline(data) {
  const outputs = data.outputs || {};
  const sd = data.step_data || {};
  const elapsed = autorunFmtElapsed(data.elapsed_sec || 0);
  const status = data.status || 'idle';

  // 仕様書生成完了カード
  if (outputs.report_json && !_arCards.crawl) {
    _arCards.crawl = true;
    const crawl = sd.crawl || {};
    const meta = crawl.screens != null
      ? `${crawl.screens}画面 / ${crawl.forms || 0}フォーム を検出`
      : `${crawl.domain || ''} クロール完了`;
    const btns = [
      outputs.report_html ? { label: 'HTMLレポート', cls: 'btn-primary', path: outputs.report_html, dataLabel: '仕様書 HTML' } : null,
      outputs.report_json ? { label: 'JSON', cls: 'btn-outline-sm', path: outputs.report_json, dataLabel: '仕様書 JSON' } : null,
    ].filter(Boolean);
    _arAppendCard('crawl', '✅', '仕様書生成完了', elapsed, meta, btns);
  }

  // QA成果物完了カード
  if (outputs.qa_process_report && !_arCards.qa) {
    _arCards.qa = true;
    const qa = sd.qa || {};
    const meta = `テスト計画・分析・設計・ケース・横断レビュー${qa.count ? '（' + qa.count + '件）' : ''}`;
    const btns = [{ label: 'QAレポートを見る', cls: 'btn-primary', path: outputs.qa_process_report, dataLabel: 'QAレポート' }];
    _arAppendCard('qa', '✅', 'QA成果物生成完了', elapsed, meta, btns);
  }

  // テストスクリプトカード
  if ((outputs.spec_ts || status === 'awaiting_approval') && !_arCards.scripts) {
    _arCards.scripts = true;
    const sc = sd.scripts || {};
    const metaParts = [sc.all != null ? `${sc.all}件のテストケース` : 'テストケース生成完了'];
    if (sc.smoke != null) metaParts.push(`スモーク:${sc.smoke}`);
    if (sc.form != null) metaParts.push(`フォーム:${sc.form}`);
    const btns = [{ label: 'テストケース確認', cls: 'btn-outline-sm', onclick: arShowPreview }];
    if (status === 'awaiting_approval') {
      btns.push({ label: '実行設定・承認', cls: 'btn-primary', onclick: _autorunPrepareAndShowApprovalModal });
    }
    const card = _arAppendCard('scripts',
      status === 'awaiting_approval' ? '⏳' : '✅',
      status === 'awaiting_approval' ? 'スクリプト生成完了 — 承認待ち' : 'テストスクリプト生成完了',
      elapsed, metaParts.join(' / '), btns);
    if (status === 'awaiting_approval' && card) {
      card.classList.add('is-approval');
    }
  }

  // テスト結果カード
  if (data.test_results && data.test_results.total != null && !_arCards.tests) {
    _arCards.tests = true;
    const r = data.test_results;
    const ok = r.ok;
    const meta = r.unavailable
      ? (r.error || '@playwright/test 未セットアップ')
      : `PASS: ${r.passed}　FAIL: ${r.failed}　SKIP: ${r.skipped}　TOTAL: ${r.total}`;
    const btns = [
      outputs.playwright_report_html ? { label: '実行レポートを見る', cls: 'btn-primary', path: outputs.playwright_report_html, dataLabel: 'テスト実行レポート' } : null,
      outputs.qa_process_report ? { label: 'QAレポート', cls: 'btn-outline-sm', path: outputs.qa_process_report, dataLabel: 'QAレポート' } : null,
    ].filter(Boolean);
    const card = _arAppendCard('tests', ok ? '✅' : '❌', ok ? 'テスト実行完了' : 'テスト実行失敗', elapsed, meta, btns);
    if (!ok && r.error && !r.unavailable && card) {
      const errDiv = document.createElement('div');
      errDiv.className = 'ar-card-error';
      errDiv.textContent = r.error;
      card.appendChild(errDiv);
    }
  }
}

// ---- カード生成（DOM API のみ・innerHTML 不使用） ----
function _arAppendCard(id, icon, title, timeStr, meta, buttons) {
  const timeline = document.getElementById('ar-timeline');
  if (!timeline) return null;

  const card = document.createElement('div');
  card.className = 'ar-card';
  card.id = `ar-card-${id}`;

  const head = document.createElement('div');
  head.className = 'ar-card-head';
  const titleEl = document.createElement('div');
  titleEl.className = 'ar-card-title';
  titleEl.textContent = `${icon} ${title}`;
  const timeEl = document.createElement('span');
  timeEl.className = 'ar-card-time';
  timeEl.textContent = timeStr;
  head.appendChild(titleEl);
  head.appendChild(timeEl);
  card.appendChild(head);

  const metaEl = document.createElement('div');
  metaEl.className = 'ar-card-meta';
  metaEl.textContent = meta;
  card.appendChild(metaEl);

  if (buttons && buttons.length) {
    const actionsEl = document.createElement('div');
    actionsEl.className = 'ar-card-actions';
    for (const btn of buttons) {
      const b = document.createElement('button');
      b.className = (btn.cls || 'btn-outline-sm');
      b.classList.add('ar-card-button');
      b.textContent = btn.label;
      if (btn.path) {
        b.dataset.path = btn.path;
        b.dataset.label = btn.dataLabel || btn.label;
        b.classList.add('qa-preview-btn');
      }
      if (btn.onclick) b.addEventListener('click', btn.onclick);
      actionsEl.appendChild(b);
    }
    card.appendChild(actionsEl);
  }

  timeline.appendChild(card);
  return card;
}

// ---- AutoRun: テストケースプレビューモーダル ----
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
  _arCards                    = {};
  _autoRunApprovalModalShown  = false;
  _autorunStopPolling();
  _autorunStopElapsed();
  _autorunHideApprovalModal();
  _autorunHideLoginModal();
  document.getElementById('autorun-steps').style.display          = 'none';
  document.getElementById('autorun-outputs-area').style.display   = 'none';
  document.getElementById('ar-log-section').style.display         = 'none';
  document.getElementById('autorun-status-panel').style.display   = 'none';
  document.getElementById('autorun-result-panel').style.display   = 'none';
  document.getElementById('autorun-failure-panel').style.display  = 'none';
  document.getElementById('autorun-preview-panel').style.display  = 'none';
  document.getElementById('autorun-cancel-area').style.display    = 'none';
  document.getElementById('autorun-restart-area').style.display   = 'none';
  document.getElementById('autorun-idle-msg').style.display       = '';
  document.getElementById('autorun-start-btn').disabled = false;
  document.getElementById('autorun-start-btn').textContent = '開始';
  document.getElementById('autorun-url').value = '';
  const viewpointSelect = document.getElementById('autorun-viewpoint-set');
  if (viewpointSelect) viewpointSelect.value = '';
  autorunLoadViewpointSelection();
  document.getElementById('autorun-elapsed').textContent = '0:00';
  const timeline = document.getElementById('ar-timeline');
  if (timeline) timeline.innerHTML = '';
  const resultCards = document.getElementById('autorun-result-cards');
  if (resultCards) resultCards.innerHTML = '';
  const failureBody = document.getElementById('autorun-failure-body');
  if (failureBody) failureBody.innerHTML = '';
  const logPre = document.getElementById('autorun-log');
  if (logPre) logPre.textContent = '';
  const allRadio = document.querySelector('input[name="autorun-filter"][value="all"]');
  if (allRadio) allRadio.checked = true;
  autorunSetStartStatus('', false);
}

document.getElementById('autorun-viewpoint-set')?.addEventListener('change', _autorunRenderViewpointRecommendation);
document.getElementById('autorun-url')?.addEventListener('input', () => {
  clearTimeout(_autorunViewpointTimer);
  _autorunViewpointTimer = setTimeout(autorunLoadViewpointSelection, 350);
});
