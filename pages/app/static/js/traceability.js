// ====================== トレーサビリティマトリクス ======================

// キャッシュ: 最後に取得したマトリクスデータ
let _traceabilityMatrix = null;

const _COVERAGE_LABELS = {
  covered:   'カバー済み',
  partial:   '部分カバー',
  uncovered: '未カバー',
};

function renderTraceabilityRow(req) {
  const coverage = req.coverage || 'uncovered';
  const label = _COVERAGE_LABELS[coverage] || coverage;
  // 色は CSS クラス（.coverage-${coverage}）で付与する（ダーク対応・生 hex を持たない）。
  const badge = `<span class="coverage-badge coverage-${escHtml(coverage)}">${escHtml(label)}</span>`;

  const testIdsHtml = req.test_ids && req.test_ids.length
    ? `<span class="test-ids-cell">${req.test_ids.map(escHtml).join(', ')}</span>`
    : '<span class="tc-dash">—</span>';

  return `
    <tr>
      <td class="req-id-cell">${escHtml(req.req_id)}</td>
      <td>${escHtml(req.req_title)}</td>
      <td class="url-cell">${escHtml(req.page_url)}</td>
      <td>${testIdsHtml}</td>
      <td>${badge}</td>
    </tr>`;
}

function renderCoverageBar(matrix) {
  const bar = document.getElementById('traceability-coverage-bar');
  if (!bar) return;
  const total = matrix.total_requirements;
  if (total === 0) {
    bar.innerHTML = '';
    return;
  }

  const reqs = matrix.requirements || [];
  const coveredCount  = reqs.filter(r => r.coverage === 'covered').length;
  const partialCount  = reqs.filter(r => r.coverage === 'partial').length;
  const uncoveredCount = reqs.filter(r => r.coverage === 'uncovered').length;

  const coveredPct  = (coveredCount  / total * 100).toFixed(1);
  const partialPct  = (partialCount  / total * 100).toFixed(1);
  const uncoveredPct = (uncoveredCount / total * 100).toFixed(1);

  bar.innerHTML = `
    <div class="coverage-bar-covered"  style="width:${coveredPct}%"
      title="カバー済み: ${coveredCount}件 (${coveredPct}%)"></div>
    <div class="coverage-bar-partial"  style="width:${partialPct}%"
      title="部分カバー: ${partialCount}件 (${partialPct}%)"></div>
    <div class="coverage-bar-uncovered" style="width:${uncoveredPct}%"
      title="未カバー: ${uncoveredCount}件 (${uncoveredPct}%)"></div>`;
}

function _renderSummary(matrix) {
  const summary = document.getElementById('traceability-summary');
  if (!summary) return;
  const rate = (matrix.coverage_rate * 100).toFixed(1);
  summary.textContent =
    `要件 ${matrix.total_requirements} 件中 ${matrix.covered_count} 件カバー（カバレッジ率 ${rate}%）`;
}

function _renderTable(reqs) {
  const tbody = document.getElementById('traceability-tbody');
  if (!tbody) return;
  if (!reqs || reqs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="traceability-msg">要件データがありません</td></tr>';
    return;
  }
  tbody.innerHTML = reqs.map(renderTraceabilityRow).join('');
}

async function loadTraceabilityMatrix(domain) {
  const loading = document.getElementById('traceability-loading');
  const tbody   = document.getElementById('traceability-tbody');
  if (loading) loading.style.display = '';
  if (tbody) tbody.innerHTML = '';

  try {
    const res = await fetch('/traceability/matrix?domain=' + encodeURIComponent(domain));
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="5" class="traceability-msg is-error">エラー: ${escHtml(err.error || String(res.status))}</td></tr>`;
      }
      return;
    }
    const matrix = await res.json();
    _traceabilityMatrix = matrix;
    _renderSummary(matrix);
    renderCoverageBar(matrix);
    _renderTable(matrix.requirements || []);
  } catch (e) {
    if (tbody) {
      tbody.innerHTML = '<tr><td colspan="5" class="traceability-msg is-error">読み込みに失敗しました</td></tr>';
    }
  } finally {
    if (loading) loading.style.display = 'none';
  }
}

function initTraceability(domain) {
  if (domain) {
    loadTraceabilityMatrix(domain);
  } else {
    const loading = document.getElementById('traceability-loading');
    if (loading) {
      loading.textContent = 'ドメインが指定されていません。';
    }
  }
}
