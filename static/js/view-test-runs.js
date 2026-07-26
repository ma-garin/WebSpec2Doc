// ---- テスト実行タブ（テストケース表から実行した結果の表示） ----
// データソース: testcases/run_result.json（テストケースタブの「実行」で作られる）。
// 実行していないサイトでは必ず「未実行」を出す（他系統の古い結果を流用しない）。

async function renderTestRuns() {
  // await 中にタブ切替で resultHero シムが差し替わっても自パネルへ描き続ける
  const host = resultHero;
  const files = (resultData && resultData.files) || {};
  const domain = (document.getElementById('r-domain') || {}).textContent || '';

  if (!files.playwright_json) {
    host.innerHTML =
      '<div class="hero-pad"><div class="runs-empty">' +
      '<div class="runs-empty-icon" aria-hidden="true">🧪</div>' +
      '<div class="hero-section-title" style="margin:0">まだ実行していません</div>' +
      '<p class="muted-copy">「自動化可」のテストケースを実行すると、ケースごとの PASS/FAIL が' +
      'ここに表示されます。対象を絞って実行したい場合はテストケースタブから実行してください。</p>' +
      _runsControlsHtml() +
      '</div></div>';
    _bindRunsControls(host);
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
    '<div class="runs-header-actions">' +
    _runsControlsHtml() +
    `${linkBtn(files.playwright_html, '実行レポートを開く', true)} ${devLink} ${dlSpec}</div>` +
    '</div>' +
    (r.interrupted ? `<div class="runs-stale-note">⚠ ${escHtml(r.error || '実行が途中で中断されました。')}</div>` : '') +
    (stale ? '<div class="runs-stale-note">⚠ この実行結果は最終クロール（' + escHtml(crawledAt) + '）より前のものです。仕様が更新されている可能性があるため、再実行を推奨します。</div>' : '') +
    `<div class="runs-summary-row">${ring}<div class="runs-stat-grid">${cards}</div></div>` +
    (tests.length
      ? '<table class="ov-screens runs-table"><thead><tr><th>テストケースID</th><th>結果</th><th>時間</th><th>エラー</th></tr></thead><tbody>' + rows + '</tbody></table>'
      : (r.error ? `<div class="runs-unavailable-card"><div class="runs-unavailable-title">⚠ 実行エラー</div><p class="runs-unavailable-reason">${escHtml(r.error)}</p></div>` : '')) +
    '</div>';
  _bindRunsControls(host);
}

// ---- このタブから直接テストを実行する ----
// 起動導線がテストケースタブにしか無く、「テスト実行」タブを開いても実行できなかった。
// 対象は「自動化可」の全ケース（絞り込んで実行したい場合はテストケースタブを使う）。
const RUNS_HEADED_KEY = 'webspec2doc.runs.headed';

function _runsDomain() {
  return (document.getElementById('r-domain') || {}).textContent || '';
}
function _runsHeadedPref() {
  try { return localStorage.getItem(RUNS_HEADED_KEY) === '1'; } catch (e) { return false; }
}

// 実行ボタンとヘッド表示トグル。未実行の空状態と実行済みヘッダの両方で使う。
function _runsControlsHtml() {
  const checked = _runsHeadedPref() ? ' checked' : '';
  return '<span class="runs-controls">' +
    '<label class="checkbox-chip" title="ブラウザ画面を表示して実行します（このアプリが動くマシンに開きます）">' +
    `<input type="checkbox" id="runs-headed"${checked}> ブラウザを表示</label>` +
    '<button type="button" class="btn-primary btn-run" id="runs-run-btn">▶ テストを実行</button>' +
    '</span>';
}

function _bindRunsControls(host) {
  host.querySelector('#runs-run-btn')?.addEventListener('click', () => runTestsFromRunsTab());
  host.querySelector('#runs-headed')?.addEventListener('change', e => {
    try { localStorage.setItem(RUNS_HEADED_KEY, e.target.checked ? '1' : '0'); } catch (err) {}
  });
}

// 実行中の画面。進捗 NDJSON（onTestEnd ごとに追記される）とスクショを一定間隔で読む。
// 実行 API は完了までレスポンスを返さないため、進捗は別 API から取る。
function _renderRunsLive(host, headed) {
  host.innerHTML =
    '<div class="hero-pad"><div class="runs-live">' +
    '<div class="runs-live-head">' +
    '<span class="spinner"></span>' +
    '<strong id="runs-live-title">実行を準備しています…</strong>' +
    `<span class="muted-copy">${headed ? 'ブラウザ表示あり' : 'ヘッドレス'}／完了までこのタブを開いたままにしてください</span>` +
    '</div>' +
    '<div class="runs-live-body">' +
    '<figure class="runs-live-shot">' +
    '<img id="runs-live-img" alt="実行中の画面">' +
    '<figcaption id="runs-live-cap" class="muted-copy">スクリーンショットを待っています…</figcaption>' +
    '</figure>' +
    '<ol class="runs-live-list" id="runs-live-list"></ol>' +
    '</div></div></div>';
}

function _startRunsPolling(domain, started) {
  const STATUS_MARK = { passed: '✓', failed: '✗', skipped: '−' };
  let lastShotAt = 0;

  return setInterval(async () => {
    const elapsed = Math.round((Date.now() - started) / 1000);
    let p = null;
    try {
      p = await fetch('/api/testcases/live-progress?domain=' + encodeURIComponent(domain))
        .then(r => r.ok ? r.json() : null);
    } catch (e) { /* 実行中の一時的な失敗は次の周期で拾う */ }

    const title = document.getElementById('runs-live-title');
    if (title) {
      title.textContent = p && p.total
        ? `実行中 ${p.done} / ${p.total} 件　PASS ${p.passed} ／ FAIL ${p.failed}　経過 ${elapsed}秒`
        : `実行中… 経過 ${elapsed}秒`;
    }

    const list = document.getElementById('runs-live-list');
    if (list && p && p.tests) {
      // 直近が上に来るよう反転して出す（長い実行でも今どこかが分かる）
      list.replaceChildren(...[...p.tests].reverse().map(t => {
        const li = document.createElement('li');
        li.className = 'runs-live-item is-' + (t.status || 'unknown');
        const mark = document.createElement('span');
        mark.className = 'runs-live-mark';
        mark.textContent = STATUS_MARK[t.status] || '?';
        const name = document.createElement('span');
        name.className = 'runs-live-name';
        name.textContent = t.title || '(名称なし)';
        const ms = document.createElement('span');
        ms.className = 'runs-live-ms';
        ms.textContent = t.duration_ms ? `${(t.duration_ms / 1000).toFixed(1)}s` : '';
        li.append(mark, name, ms);
        return li;
      }));
    }

    // スクショはファイル書き出しが追いつかないので、進捗より粗い間隔で更新する
    if (Date.now() - lastShotAt > 1500) {
      lastShotAt = Date.now();
      const img = document.getElementById('runs-live-img');
      const cap = document.getElementById('runs-live-cap');
      if (img) {
        img.onload = () => { if (cap) cap.textContent = '実行中の画面（自動更新）'; };
        img.src = '/api/testcases/live-screenshot?domain=' + encodeURIComponent(domain)
          + '&t=' + Date.now();
      }
    }
  }, 1000);
}

async function runTestsFromRunsTab() {
  const domain = _runsDomain();
  if (!domain) { showToast('対象サイトを特定できませんでした', 'error'); return; }
  const headed = !!document.getElementById('runs-headed')?.checked;
  const ok = await confirmDialog({
    title: 'テストを実行',
    message: '自動化可のテストケースを実行します。対象サイトへ実際にアクセスします。'
      + (headed ? '\nブラウザ画面を表示して実行します。' : ''),
    confirmLabel: '実行する',
  });
  if (!ok) return;

  const host = resultHero;
  const started = Date.now();
  _renderRunsLive(host, headed);
  const tick = _startRunsPolling(domain, started);

  try {
    const res = await fetch('/api/testcases/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ domain, headed }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '実行に失敗しました');
    const s = (data.run && data.run.summary) || {};
    showToast(
      `実行完了: PASS ${s.passed || 0} / FAIL ${s.failed || 0} / 全${s.total || 0}件`,
      data.ok ? 'success' : 'error');
    clearInterval(tick);
    await showResults(domain, 'runs');
  } catch (e) {
    clearInterval(tick);
    uiError(host, {
      title: 'テストを実行できませんでした',
      message: e.message,
      onRetry: () => renderTestRuns(),
    });
  } finally {
    clearInterval(tick);
  }
}
