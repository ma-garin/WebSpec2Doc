// ---- テスト実行タブ（AutoRun / Playwright 実行結果の一元表示） ----
// データソース: /api/result の files.playwright_json（qa_process/playwright_report.json）

async function renderTestRuns() {
  // await 中にタブ切替で resultHero シムが差し替わっても自パネルへ描き続ける
  const host = resultHero;
  const files = (resultData && resultData.files) || {};
  const domain = (document.getElementById('r-domain') || {}).textContent || '';

  if (!files.playwright_json) {
    uiEmpty(host, {
      icon: '🧪',
      title: 'テスト実行結果はまだありません',
      desc: 'AutoRun でこのサイトの自動テストを実行すると、PASS/FAIL の結果と実行レポートがここに表示されます。',
      actionLabel: 'AutoRun で自動テストを実行 →',
      onAction: () => switchView('auto-run'),
    });
    return;
  }

  uiSkeleton(host, 'table');
  let r;
  try {
    r = await fetch('/preview?path=' + encodeURIComponent(files.playwright_json)).then(res => res.json());
  } catch (e) {
    uiError(host, {
      title: 'テスト実行結果を読み込めませんでした',
      message: String(e),
      onRetry: () => renderTestRuns(),
    });
    return;
  }

  // Playwright 未セットアップ等で実行できなかった場合は、成功と誤認させない警告表示にする
  if (r.unavailable) {
    host.innerHTML =
      '<div class="hero-pad">' +
      '<div class="runs-unavailable-card">' +
      '<div class="runs-unavailable-title">⚠ テストを実行できませんでした</div>' +
      `<p class="runs-unavailable-reason">${escHtml(r.error || '実行環境が見つかりません。')}</p>` +
      '<div class="runs-unavailable-help">' +
      '<div class="runs-unavailable-help-title">セットアップ手順</div>' +
      '<pre class="runs-setup-pre">cd output/.playwright_env\nnpm install -D @playwright/test\nnpx playwright install chromium</pre>' +
      '<p class="muted-copy">セットアップ後、AutoRun から再実行してください。</p>' +
      '</div></div></div>';
    return;
  }

  const total = r.total || 0;
  const passRate = total ? Math.round(((r.passed || 0) / total) * 100) : 0;
  const runAt = resultData.playwright_run_at || '';
  const crawledAt = (reportJson && reportJson.meta && reportJson.meta.crawled_at) || '';
  // 実行がクロールより古い場合、結果が現行仕様を反映していない可能性を注記する
  const stale = runAt && crawledAt && runAt < crawledAt;

  const cards = [
    { label: 'PASS', val: r.passed || 0, cls: 'status-low' },
    { label: 'FAIL', val: r.failed || 0, cls: 'status-critical' },
    { label: 'SKIP', val: r.skipped || 0, cls: 'status-muted' },
    { label: 'TOTAL', val: total, cls: 'status-default' },
  ].map(c =>
    `<div class="stat-card runs-stat-card"><div class="num ${c.cls}">${c.val}</div><div class="lbl">${c.label}</div></div>`
  ).join('');

  const ringCls = r.failed ? 'is-fail' : 'is-pass';
  const ring =
    `<div class="runs-passrate ${ringCls}" role="img" aria-label="PASS率 ${passRate}%">` +
    `<svg viewBox="0 0 36 36"><circle class="runs-ring-bg" cx="18" cy="18" r="15.9"></circle>` +
    `<circle class="runs-ring-fill" cx="18" cy="18" r="15.9" stroke-dasharray="${passRate} 100"></circle></svg>` +
    `<div class="runs-passrate-label"><strong>${passRate}%</strong><span>PASS率</span></div></div>`;

  const tests = r.tests || [];
  const rows = tests.map(t => {
    const cls = t.status === 'passed' ? 'status-low' : t.status === 'skipped' ? 'status-muted' : 'status-critical';
    const err = t.error
      ? `<details class="runs-error-detail"><summary>エラーを表示</summary><pre class="runs-error-pre">${escHtml(t.error)}</pre></details>`
      : '—';
    return `<tr>
      <td class="cell-title">${escHtml(t.title || '')}</td>
      <td><span class="runs-status-badge ${cls}">${escHtml(t.status || '')}</span></td>
      <td class="num">${t.duration_ms || 0}ms</td>
      <td class="runs-error-cell">${err}</td>
    </tr>`;
  }).join('');

  const linkBtn = (path, label, primary) => path
    ? `<button type="button" class="${primary ? 'btn-primary' : 'btn-outline-sm'} qa-preview-btn" data-path="${escHtml(path)}" data-label="${escHtml(label)}">${escHtml(label)}</button>`
    : '';
  const dlSpec = files.spec_ts
    ? `<a class="btn-outline-sm" href="/download?path=${encodeURIComponent(files.spec_ts)}" download>spec.ts をダウンロード</a>`
    : '';

  host.innerHTML =
    '<div class="hero-pad">' +
    '<div class="runs-header">' +
    '<div><div class="hero-section-title" style="margin:0">テスト実行結果</div>' +
    `<p class="muted-copy runs-meta">実行日時: ${escHtml(runAt || '不明')}${r.duration_ms ? ' ／ 所要 ' + Math.round(r.duration_ms / 1000) + '秒' : ''}</p></div>` +
    `<div class="runs-header-actions">${linkBtn(files.playwright_html, '実行レポートを開く', true)} ${linkBtn(files.qa_process_report, 'QAレポート', false)} ${dlSpec}</div>` +
    '</div>' +
    (stale ? '<div class="runs-stale-note">⚠ この実行結果は最終クロール（' + escHtml(crawledAt) + '）より前のものです。仕様が更新されている可能性があるため、AutoRun での再実行を推奨します。</div>' : '') +
    `<div class="runs-summary-row">${ring}<div class="runs-stat-grid">${cards}</div></div>` +
    (tests.length
      ? '<table class="ov-screens runs-table"><thead><tr><th>テスト</th><th>結果</th><th>時間</th><th>エラー</th></tr></thead><tbody>' + rows + '</tbody></table>'
      : (r.error ? `<div class="runs-unavailable-card"><div class="runs-unavailable-title">⚠ 実行エラー</div><p class="runs-unavailable-reason">${escHtml(r.error)}</p></div>` : '')) +
    '</div>';
}
