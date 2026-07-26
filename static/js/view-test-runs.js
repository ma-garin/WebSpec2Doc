// ---- テスト実行タブ（テストケース表から実行した結果の表示） ----
// データソース: testcases/run_result.json（テストケースタブの「実行」で作られる）。
// 実行していないサイトでは必ず「未実行」を出す（他系統の古い結果を流用しない）。

async function renderTestRuns() {
  // await 中にタブ切替で resultHero シムが差し替わっても自パネルへ描き続ける
  const host = resultHero;
  const files = (resultData && resultData.files) || {};
  const domain = (document.getElementById('r-domain') || {}).textContent || '';

  if (!files.playwright_json) {
    uiEmpty(host, {
      icon: '🧪',
      title: 'まだ実行していません',
      desc: 'テストケースタブで対象を選び「実行」を押すと、ケースごとの PASS/FAIL がここに表示されます。',
      actionLabel: 'テストケースタブを開く →',
      onAction: () => selectResultTab('testcases'),
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
      '<p class="muted-copy">セットアップ後に再実行してください。</p>' +
      '</div></div></div>';
    return;
  }

  const safeNumber = value => Number.isFinite(Number(value)) ? Number(value) : 0;
  const summary = r.summary || {};
  const total = safeNumber(summary.total);
  const passed = safeNumber(summary.passed);
  const failed = safeNumber(summary.failed);
  const skipped = safeNumber(summary.skipped);
  // ケース単位の結果を表示用の配列へ（テスト名ではなくケースIDで並べる）
  const tests = Object.entries(r.cases || {})
    .map(([caseId, v]) => ({
      title: caseId,
      status: v.status,
      duration_ms: v.duration_ms,
      error: v.error,
    }))
    .sort((a, b) => a.title.localeCompare(b.title));
  r = { ...r, error: summary.error || '', duration_ms: summary.duration_ms, tests };

  // evidence-only: エラーがあり、かつ回収できた結果が1件も無い場合は「実行エラー」を
  // 明示する（PASS率リングや0/0/0のカードを描画しない）。AutoRunで188件実行したのに
  // 結果が全件0で「成功したかのように」表示され続けた致命的UX破綻の再発防止。
  if (r.error && total === 0) {
    host.innerHTML =
      '<div class="hero-pad">' +
      '<div class="runs-unavailable-card">' +
      '<div class="runs-unavailable-title">⚠ 実行エラー（結果は0件です）</div>' +
      `<p class="runs-unavailable-reason">${escHtml(r.error)}</p>` +
      '</div></div>';
    return;
  }

  const passRate = total ? Math.round((passed / total) * 100) : 0;
  const runAt = resultData.playwright_run_at || '';
  const crawledAt = (reportJson && reportJson.meta && reportJson.meta.crawled_at) || '';
  // 実行がクロールより古い場合、結果が現行仕様を反映していない可能性を注記する
  const runTime = Date.parse(runAt);
  const crawlTime = Date.parse(crawledAt);
  const stale = Number.isFinite(runTime) && Number.isFinite(crawlTime) && runTime < crawlTime;

  const cards = [
    { label: 'PASS', val: passed, cls: 'status-low' },
    { label: 'FAIL', val: failed, cls: 'status-critical' },
    { label: 'SKIP', val: skipped, cls: 'status-muted' },
    { label: 'TOTAL', val: total, cls: 'status-default' },
  ].map(c =>
    `<div class="stat-card runs-stat-card"><div class="num ${c.cls}">${c.val}</div><div class="lbl">${c.label}</div></div>`
  ).join('');

  const ringCls = (failed || r.error || r.interrupted) ? 'is-fail' : 'is-pass';
  const ring =
    `<div class="runs-passrate ${ringCls}" role="img" aria-label="PASS率 ${passRate}%">` +
    `<svg viewBox="0 0 36 36"><circle class="runs-ring-bg" cx="18" cy="18" r="15.9"></circle>` +
    `<circle class="runs-ring-fill" cx="18" cy="18" r="15.9" stroke-dasharray="${passRate} 100"></circle></svg>` +
    `<div class="runs-passrate-label"><strong>${passRate}%</strong><span>PASS率</span></div></div>`;

  const rows = tests.map(t => {
    const cls = t.status === 'passed' ? 'status-low' : t.status === 'skipped' ? 'status-muted' : 'status-critical';
    const err = t.error
      ? `<details class="runs-error-detail"><summary>エラーを表示</summary><pre class="runs-error-pre">${escHtml(t.error)}</pre></details>`
      : '—';
    return `<tr>
      <td class="cell-title"><code>${escHtml(t.title || '')}</code></td>
      <td><span class="runs-status-badge ${cls}">${escHtml(t.status || '')}</span></td>
      <td class="num">${safeNumber(t.duration_ms)}ms</td>
      <td class="runs-error-cell">${err}</td>
    </tr>`;
  }).join('');

  const linkBtn = (path, label, primary) => path
    ? `<button type="button" class="${primary ? 'btn-primary' : 'btn-outline-sm'} qa-preview-btn" data-path="${escHtml(path)}" data-label="${escHtml(label)}">${escHtml(label)}</button>`
    : '';
  const dlSpec = files.spec_ts
    ? `<a class="btn-outline-sm" href="/download?path=${encodeURIComponent(files.spec_ts)}" download>spec.ts をダウンロード</a>`
    : '';
  const devLink = linkBtn(files.playwright_native_html, '詳細（開発者向け）', false);

  host.innerHTML =
    '<div class="hero-pad">' +
    '<div class="runs-header">' +
    '<div><div class="hero-section-title" style="margin:0">テスト実行結果</div>' +
    `<p class="muted-copy runs-meta">実行日時: ${escHtml(runAt || '不明')}${r.duration_ms ? ' ／ 所要 ' + Math.round(r.duration_ms / 1000) + '秒' : ''}</p></div>` +
    `<div class="runs-header-actions">${linkBtn(files.playwright_html, '実行レポートを開く', true)} ${devLink} ${dlSpec}</div>` +
    '</div>' +
    (r.interrupted ? `<div class="runs-stale-note">⚠ ${escHtml(r.error || '実行が途中で中断されました。')}</div>` : '') +
    (stale ? '<div class="runs-stale-note">⚠ この実行結果は最終クロール（' + escHtml(crawledAt) + '）より前のものです。仕様が更新されている可能性があるため、再実行を推奨します。</div>' : '') +
    `<div class="runs-summary-row">${ring}<div class="runs-stat-grid">${cards}</div></div>` +
    (tests.length
      ? '<table class="ov-screens runs-table"><thead><tr><th>テストケースID</th><th>結果</th><th>時間</th><th>エラー</th></tr></thead><tbody>' + rows + '</tbody></table>'
      : (r.error ? `<div class="runs-unavailable-card"><div class="runs-unavailable-title">⚠ 実行エラー</div><p class="runs-unavailable-reason">${escHtml(r.error)}</p></div>` : '')) +
    '</div>';
}
