// ---- 探索カバレッジタブ（ヒートマップ・次の探索チャーター提案） ----
// データソース: /api/result の files.exploration_json（exploration_coverage.json）
//               files.exploration_heatmap（exploration_heatmap.html・/preview で iframe 表示）

async function renderCoverage() {
  const host = resultHero;
  const files = (resultData && resultData.files) || {};

  if (!files.exploration_json) {
    uiEmpty(host, {
      icon: '🗺️',
      title: '探索セッション未集計',
      desc: 'CLI の --record-session → --exploration-coverage を実行してください。',
    });
    return;
  }

  uiSkeleton(host, 'table');
  let coverage;
  try {
    coverage = await fetch('/preview?path=' + encodeURIComponent(files.exploration_json)).then(res => res.json());
  } catch (e) {
    uiError(host, {
      title: '探索カバレッジを読み込めませんでした',
      message: String(e),
      onRetry: () => renderCoverage(),
    });
    return;
  }

  const summary = coverage.summary || {};
  const ratio = Math.round((summary.coverage_ratio || 0) * 100);
  const cards = [
    { label: '画面カバレッジ', val: `${summary.explored_screens || 0}/${summary.total_screens || 0}` },
    { label: 'カバレッジ率', val: `${ratio}%` },
    { label: '画面状態カバー', val: `${summary.touched_states || 0}/${summary.total_states || 0}` },
  ].map(c =>
    `<div class="stat-card runs-stat-card"><div class="num">${escHtml(String(c.val))}</div><div class="lbl">${escHtml(c.label)}</div></div>`
  ).join('');

  const heatmapFrame = files.exploration_heatmap
    ? `<iframe class="coverage-heatmap-frame" src="/preview?path=${encodeURIComponent(files.exploration_heatmap)}" title="探索カバレッジヒートマップ"></iframe>`
    : '';

  const charters = coverage.charters || [];
  const charterRows = charters.map(c => {
    const flowText = (c.flows || []).map(f => `${f.flow_name || ''}（${f.path_id || ''}）`).join('、') || '—';
    return `<tr>
      <td>${escHtml(c.page_id || '')}</td>
      <td>${escHtml(c.title || '')}</td>
      <td>${escHtml(c.reason || '')}</td>
      <td>${escHtml(flowText)}</td>
      <td><span class="runs-status-badge ${c.priority === '高' ? 'status-critical' : 'status-default'}">${escHtml(c.priority || '')}</span></td>
    </tr>`;
  }).join('');
  const charterSection = charters.length
    ? '<div class="hero-section-title" style="margin-top:1.5rem">次の探索チャーター（提案）</div>' +
      '<table class="ov-screens runs-table"><thead><tr><th>ID</th><th>画面</th><th>理由</th><th>根拠（フロー）</th><th>優先度</th></tr></thead>' +
      `<tbody>${charterRows}</tbody></table>`
    : '';

  host.innerHTML =
    '<div class="hero-pad">' +
    '<div class="hero-section-title">探索カバレッジ</div>' +
    `<div class="runs-summary-row"><div class="runs-stat-grid">${cards}</div></div>` +
    heatmapFrame +
    charterSection +
    '</div>';
}
