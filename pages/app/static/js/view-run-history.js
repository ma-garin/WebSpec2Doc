// ---- 実行履歴ビュー（種別を問わない一般化・R2-27） ----
const RH_TYPE_LABELS = { crawl: '解析', autorun: 'AutoRun', comparison: '現新比較', ux_review: 'UXレビュー', schedule: 'スケジュール' };
const RH_TERMINAL_STATUSES = new Set(['complete', 'failed', 'cancelled']);
const RH_TYPE_KEY = 'wsd_rh_type';
const RH_VALID_TYPES = ['crawl', 'autorun', 'comparison', 'ux_review', 'schedule', 'all'];
const RH_PAGE_SIZE = 20;
let _rhRuns = [];
let _rhPage = 1;

// 履歴の種別タブ（R3-16: 従来の全種別混在selectをタブ分離。既定は「解析」）
function _rhCurrentType() {
  let stored = '';
  try { stored = localStorage.getItem(RH_TYPE_KEY) || ''; } catch (_) { stored = ''; }
  return RH_VALID_TYPES.includes(stored) ? stored : 'crawl';
}
function _rhSyncTypeTabsUI(type) {
  document.querySelectorAll('.rh-type-tab').forEach(btn => {
    const active = btn.dataset.type === type;
    btn.classList.toggle('is-active', active);
    btn.setAttribute('aria-selected', active ? 'true' : 'false');
  });
}
function _rhSetType(type) {
  try { localStorage.setItem(RH_TYPE_KEY, type); } catch (_) { /* 保存失敗時はUIのみ切替（機能は継続） */ }
  _rhPage = 1; // 種別切替でページを先頭に戻す
  _rhSyncTypeTabsUI(type);
  _rhRenderTable();
}

// ISO形式（例: 2026-07-05T16:08:11+00:00）のまま出すと読みにくいため、
// ローカル時刻の読みやすい形式に整形する（監査で発覚・修正）。
// 解析に失敗した場合は元の文字列をそのまま返す（未加工の値を握りつぶさない）。
function _rhFormatTimestamp(raw) {
  if (!raw) return '';
  const d = new Date(raw);
  if (isNaN(d.getTime())) return raw;
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} `
    + `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function _rhStatusClass(status) {
  if (status === 'complete') return 'rh-status-complete';
  if (status === 'failed') return 'rh-status-failed';
  if (status === 'cancelled') return 'rh-status-cancelled';
  return 'rh-status-running';
}

function _rhStatusLabel(status) {
  if (status === 'complete') return '完了';
  if (status === 'failed') return '失敗';
  if (status === 'cancelled') return '中断';
  return RH_TERMINAL_STATUSES.has(status) ? status : '実行中';
}

function _rhSummaryText(run) {
  const s = run.summary || {};
  if (run.type === 'autorun') {
    return `PASS ${s.passed || 0} / FAIL ${s.failed || 0} / TOTAL ${s.total || 0}（${s.duration_sec || 0}秒）`;
  }
  if (run.type === 'comparison' || run.type === 'ux_review') {
    return `画面 ${s.compare_screen_count || 0} / 指摘 ${s.finding_count || 0}件`;
  }
  if (run.type === 'schedule') {
    const error = s.error ? ` / ${s.error}` : '';
    return `試行 ${s.attempts || 0}回 / ${s.duration_sec || 0}秒${error}`;
  }
  return `画面 ${s.screen_count || 0} / フォーム ${s.test_condition_count || 0} / 成果物 ${s.document_count || 0}`;
}

async function loadRunHistory() {
  const tbody = document.getElementById('rh-tbody');
  const empty = document.getElementById('rh-empty');
  if (!tbody) return;
  _rhSyncTypeTabsUI(_rhCurrentType());
  tbody.innerHTML = '<tr><td colspan="6">読み込んでいます…</td></tr>';
  try {
    const res = await fetch('/api/history/runs');
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '実行履歴を取得できませんでした');
    _rhRuns = data.runs || [];
    _rhRenderTable();
  } catch (e) {
    tbody.innerHTML = '';
    if (empty) { empty.style.display = ''; empty.textContent = String(e.message); }
  }
}

// 段階承認の状況。「未承認のまま実行された」ことを隠さない。
function _rhApprovalCell(run) {
  const a = run.stage_approval;
  if (!a) return '<span class="muted-copy">—</span>';
  const label = `${a.approved} / ${a.total}`;
  if (a.all_approved) {
    const note = a.skipped && a.skipped.length
      ? `（${a.skipped.join('・')}をスキップ）` : '';
    return `<span class="rh-approval is-ok">${escHtml(label)} 承認済み</span>`
      + (note ? `<span class="rh-approval-note">${escHtml(note)}</span>` : '');
  }
  return `<span class="rh-approval is-partial">${escHtml(label)}</span>`
    + '<span class="rh-approval-note">未承認の段階があります</span>';
}

function _rhRenderTable() {
  const tbody = document.getElementById('rh-tbody');
  const empty = document.getElementById('rh-empty');
  const pager = document.getElementById('rh-pager');
  if (!tbody) return;
  const filter = _rhCurrentType();
  const runs = filter === 'all' ? _rhRuns : _rhRuns.filter(r => r.type === filter);
  if (pager) pager.innerHTML = '';
  if (!runs.length) {
    tbody.innerHTML = '';
    if (empty) { empty.style.display = ''; empty.textContent = '実行履歴がありません。'; }
    return;
  }
  if (empty) empty.style.display = 'none';
  const info = TableUtils.paginate(runs, _rhPage, RH_PAGE_SIZE);
  _rhPage = info.page; // クランプ後の値へ同期
  if (pager) pager.innerHTML = TableUtils.pagerHtml(info);
  tbody.innerHTML = info.items.map(run => {
    const typeLabel = run.type_label || RH_TYPE_LABELS[run.type] || run.type;
    const linkCell = run.report_url
      ? `<a class="qa-output-btn" href="${escHtml(run.report_url)}">結果を見る →</a>`
      : (run.link
        ? `<button class="qa-output-btn qa-preview-btn" data-path="${escHtml(run.link)}" data-label="${escHtml(typeLabel)} - ${escHtml(run.domain)}">開く</button>`
        : '<span class="muted-copy">—</span>');
    return `<tr>
      <td><span class="rh-type-badge rh-type-${escHtml(run.type)}">${escHtml(typeLabel)}</span></td>
      <td>${escHtml(run.domain)}</td>
      <td title="${escHtml(run.timestamp || '')}">${escHtml(_rhFormatTimestamp(run.timestamp))}</td>
      <td><span class="rh-status-badge ${_rhStatusClass(run.status)}">${escHtml(_rhStatusLabel(run.status))}</span></td>
      <td>${_rhApprovalCell(run)}</td>
      <td>${escHtml(_rhSummaryText(run))}</td>
      <td>${linkCell}</td>
    </tr>`;
  }).join('');
}

document.querySelectorAll('.rh-type-tab').forEach(btn => {
  btn.addEventListener('click', () => _rhSetType(btn.dataset.type));
});
document.getElementById('rh-reload-btn')?.addEventListener('click', loadRunHistory);
// ページャ（イベント委譲）: クリックされたページへ移動して再描画する
document.getElementById('rh-pager')?.addEventListener('click', (e) => {
  const page = TableUtils.pageFromClick(e);
  if (page === null || page === _rhPage) return;
  _rhPage = page;
  _rhRenderTable();
});
