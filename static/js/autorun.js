// ====================== AutoRun ======================
let _autoRunJobId = null;
let _autoRunPollTimer = null;
let _autoRunElapsedTimer = null;
let _autoRunStartedAt = null;  // ISO string from server
let _autoRunPreviewLoaded = false;
let _autoRunPreviewData = null;
let _arCards = {};  // 生成済みカード管理: {crawl, qa, scripts, tests}

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
  document.getElementById('ar-log-section').style.display = '';
  document.getElementById('autorun-idle-msg').style.display = 'none';
  document.getElementById('autorun-preview-panel').style.display = 'none';
  document.getElementById('autorun-cancel-area').style.display = '';
}

// ---- AutoRun: ログ折りたたみ ----
function arToggleLog() {
  const pre = document.getElementById('autorun-log');
  const btn = document.getElementById('ar-log-toggle');
  if (!pre || !btn) return;
  const open = pre.style.display === 'none';
  pre.style.display = open ? '' : 'none';
  btn.textContent = open ? '▲ 折りたたむ' : '▶ 展開';
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

  // ---- タイムラインカード更新 ----
  _autorunUpdateTimeline(data);

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
              <button class="btn-outline-sm qa-preview-btn" data-path="${escHtml(path)}" data-label="${escHtml(label)}" style="font-size:11px;height:26px;padding:0 8px">プレビュー</button>
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
    const btns = [{ label: 'QAレポートを見る', cls: 'btn-primary', path: outputs.qa_process_report, dataLabel: 'QAプロセスレポート' }];
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
    const card = _arAppendCard('scripts',
      status === 'awaiting_approval' ? '⏳' : '✅',
      status === 'awaiting_approval' ? 'テストスクリプト 承認待ち' : 'テストスクリプト生成完了',
      elapsed, metaParts.join(' / '), btns);
    if (status === 'awaiting_approval' && card) {
      const hint = document.createElement('p');
      hint.style.cssText = 'font-size:11px;color:var(--text-muted);margin-top:6px';
      hint.textContent = '← 左側で実行方針を選択してテスト実行を承認してください';
      card.appendChild(hint);
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
      outputs.qa_process_report ? { label: 'QAレポート', cls: 'btn-outline-sm', path: outputs.qa_process_report, dataLabel: 'QAプロセスレポート' } : null,
    ].filter(Boolean);
    const card = _arAppendCard('tests', ok ? '✅' : '❌', ok ? 'テスト実行完了' : 'テスト実行失敗', elapsed, meta, btns);
    if (!ok && r.error && !r.unavailable && card) {
      const errDiv = document.createElement('div');
      errDiv.style.cssText = 'margin-top:6px;font-size:11px;color:var(--critical);word-break:break-all';
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
      b.style.cssText = 'font-size:12px;height:30px;padding:0 12px';
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

// ---- AutoRun: テストケースプレビュー（スクリプトカードから呼び出し） ----
function arShowPreview() {
  const panel = document.getElementById('autorun-preview-panel');
  if (!panel) return;
  const visible = panel.style.display !== 'none';
  panel.style.display = visible ? 'none' : '';
  if (!visible && !_autoRunPreviewLoaded) {
    _autoRunPreviewLoaded = true;
    _autorunLoadPreview();
  }
}

// ---- AutoRun: テストプレビュー ----
async function _autorunLoadPreview() {
  if (!_autoRunJobId) return;
  const loadingEl = document.getElementById('autorun-preview-loading');
  if (loadingEl) loadingEl.textContent = '読み込み中…';
  try {
    const data = await fetch('/api/autorun/preview?job_id=' + encodeURIComponent(_autoRunJobId)).then(r => r.json());
    _autoRunPreviewData = data;
    _autorunRenderPreview(data);
    _autorunUpdateFilterCounts(data.summary?.filter_counts || {});
    if (loadingEl) loadingEl.textContent = '';
  } catch (e) {
    if (loadingEl) loadingEl.textContent = '(読み込みエラー)';
  }
}

function _autorunRenderPreview(data) {
  const summaryEl = document.getElementById('autorun-preview-summary');
  const tableWrap = document.getElementById('autorun-preview-table-wrap');
  const specEl    = document.getElementById('autorun-preview-spec');

  const summary    = data.summary || {};
  const candidates = data.candidates || [];
  const byStatus   = summary.by_status || {};
  const byTitle    = summary.by_title || {};

  // サマリーバー
  if (summaryEl) {
    const autoCount  = byStatus.auto || 0;
    const skipCount  = (byStatus['manual-review'] || 0) + (byStatus.review || 0);
    const titleBadges = Object.entries(byTitle)
      .map(([t, c]) => `<span class="fmt-badge">${escHtml(t)}: ${c}</span>`)
      .join('');
    summaryEl.innerHTML = `
      <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px;font-size:12px">
        <span><strong>${summary.total || 0}</strong> 件</span>
        <span style="color:#16a34a">自動: ${autoCount}</span>
        <span style="color:#9ca3af">スキップ: ${skipCount}</span>
      </div>
      <div class="fmt-badges" style="margin-bottom:10px">${titleBadges}</div>`;
  }

  // テストケーステーブル
  if (tableWrap) {
    if (candidates.length) {
      const rows = candidates.map(c => {
        const sClr = c.automation_status === 'auto' ? '#16a34a' : '#9ca3af';
        return `<tr>
          <td style="white-space:nowrap;font-size:11px">${escHtml(c.id || '')}</td>
          <td style="font-size:12px">${escHtml(c.title || '')}</td>
          <td style="font-size:11px;font-weight:600;color:${sClr}">${escHtml(c.automation_status || '')}</td>
          <td style="font-size:11px;white-space:nowrap">${escHtml(c.trace_id || '')}</td>
          <td style="font-size:11px;max-width:200px;word-break:break-word;color:var(--text-muted)">${escHtml((c.expected || '').substring(0, 60))}</td>
        </tr>`;
      }).join('');
      tableWrap.innerHTML = `<table class="data" style="font-size:12px;width:100%">
        <thead><tr><th>ID</th><th>タイトル</th><th>自動化</th><th>Trace</th><th>期待結果</th></tr></thead>
        <tbody>${rows}</tbody></table>`;
    } else {
      tableWrap.innerHTML = '<div class="empty" style="padding:16px">テストケースなし</div>';
    }
  }

  // スクリプト
  if (specEl) specEl.textContent = data.spec_content || '(スクリプトなし)';
}

function _autorunUpdateFilterCounts(counts) {
  const map = { all: '#afc-all', smoke: '#afc-smoke', transition: '#afc-transition', form: '#afc-form' };
  Object.entries(map).forEach(([key, sel]) => {
    const el = document.querySelector(sel);
    if (el && counts[key] !== undefined) el.textContent = `(${counts[key]}件)`;
  });
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

  const filterMode = document.querySelector('input[name="autorun-filter"]:checked')?.value || 'all';
  const timeoutSec = parseInt(document.getElementById('autorun-timeout')?.value || '60', 10);

  try {
    const res = await fetch('/api/autorun/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: _autoRunJobId, filter_mode: filterMode, timeout_sec: timeoutSec }),
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
  _autoRunJobId          = null;
  _autoRunStartedAt      = null;
  _autoRunPreviewLoaded  = false;
  _autoRunPreviewData    = null;
  _arCards               = {};
  _autorunStopPolling();
  _autorunStopElapsed();
  _autorunHideLoginModal();
  document.getElementById('autorun-steps').style.display          = 'none';
  document.getElementById('autorun-outputs-area').style.display   = 'none';
  document.getElementById('ar-log-section').style.display         = 'none';
  document.getElementById('autorun-preview-panel').style.display  = 'none';
  document.getElementById('autorun-cancel-area').style.display    = 'none';
  document.getElementById('autorun-restart-area').style.display   = 'none';
  document.getElementById('autorun-idle-msg').style.display       = '';
  document.getElementById('autorun-start-btn').disabled = false;
  document.getElementById('autorun-start-btn').textContent = '開始';
  document.getElementById('autorun-url').value = '';
  document.getElementById('autorun-elapsed').textContent = '0:00';
  const timeline = document.getElementById('ar-timeline');
  if (timeline) timeline.innerHTML = '';
  const logPre = document.getElementById('autorun-log');
  if (logPre) { logPre.textContent = ''; logPre.style.display = 'none'; }
  const logToggle = document.getElementById('ar-log-toggle');
  if (logToggle) logToggle.textContent = '▶ 展開';
  const allRadio = document.querySelector('input[name="autorun-filter"][value="all"]');
  if (allRadio) allRadio.checked = true;
  autorunSetStartStatus('', false);
}

