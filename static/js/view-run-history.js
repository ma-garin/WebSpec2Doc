// ---- 実行履歴ビュー（種別を問わない一般化・R2-27） ----
const RH_TYPE_LABELS = { crawl: '解析', autorun: 'AutoRun', comparison: '現新比較', ux_review: 'UXレビュー' };
const RH_TERMINAL_STATUSES = new Set(['complete', 'failed', 'cancelled']);
let _rhRuns = [];

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
  return `画面 ${s.screen_count || 0} / フォーム ${s.test_condition_count || 0} / 成果物 ${s.document_count || 0}`;
}

async function loadRunHistory() {
  const tbody = document.getElementById('rh-tbody');
  const empty = document.getElementById('rh-empty');
  if (!tbody) return;
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

function _rhRenderTable() {
  const tbody = document.getElementById('rh-tbody');
  const empty = document.getElementById('rh-empty');
  if (!tbody) return;
  const filter = document.getElementById('rh-type-filter')?.value || 'all';
  const runs = filter === 'all' ? _rhRuns : _rhRuns.filter(r => r.type === filter);
  if (!runs.length) {
    tbody.innerHTML = '';
    if (empty) { empty.style.display = ''; empty.textContent = '実行履歴がありません。'; }
    return;
  }
  if (empty) empty.style.display = 'none';
  tbody.innerHTML = runs.map(run => {
    const typeLabel = run.type_label || RH_TYPE_LABELS[run.type] || run.type;
    const linkCell = run.link
      ? `<button class="qa-output-btn qa-preview-btn" data-path="${escHtml(run.link)}" data-label="${escHtml(typeLabel)} - ${escHtml(run.domain)}">開く</button>`
      : '<span class="muted-copy">—</span>';
    return `<tr>
      <td><span class="rh-type-badge rh-type-${escHtml(run.type)}">${escHtml(typeLabel)}</span></td>
      <td>${escHtml(run.domain)}</td>
      <td>${escHtml(run.timestamp || '')}</td>
      <td><span class="rh-status-badge ${_rhStatusClass(run.status)}">${escHtml(_rhStatusLabel(run.status))}</span></td>
      <td>${escHtml(_rhSummaryText(run))}</td>
      <td>${linkCell}</td>
    </tr>`;
  }).join('');
}

document.getElementById('rh-type-filter')?.addEventListener('change', _rhRenderTable);
document.getElementById('rh-reload-btn')?.addEventListener('click', loadRunHistory);
