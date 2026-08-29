// ---- テスト活動支援 / 実行ビュー ----
// 既存の実行基盤（/api/history/runs）を共用し、実行起動（POST /api/testcases/run）も
// この画面から行う。停止・スケジュール登録・結果書き出し・環境/並列度は未配線。
(function () {
  'use strict';

  // テスト実行に該当する種別だけを扱う（クロール等のドキュメント作成は混ぜない）。
  // testcase_run はこの画面からの実行分（snapshot_run(event="testcase_run") →
  // usage_tracker.py の build_run_history が event をそのまま type に入れる）。
  const TA_EXEC_TYPES = ['autorun', 'testcase_run'];
  const TA_STATUS_LABELS = { complete: '完了', failed: '失敗', cancelled: '中断', running: '実行中' };
  let _loaded = false;

  const esc = (v) => (typeof escHtml === 'function'
    ? escHtml(String(v))
    : String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));

  function fmtDuration(sec) {
    const n = Number(sec);
    if (!isFinite(n) || n <= 0) return '—';
    if (n < 60) return `${Math.round(n)}秒`;
    return `${Math.floor(n / 60)}分${Math.round(n % 60)}秒`;
  }

  function statusBadge(status) {
    const label = TA_STATUS_LABELS[status] || TA_STATUS_LABELS.running;
    const cls = TA_STATUS_LABELS[status] ? status : 'running';
    return `<span class="rh-status-badge rh-status-${esc(cls)}">${esc(label)}</span>`;
  }

  // 集計はサーバが返す stats（絞り込み後の全件が母数）を使う。
  // 表示中の行だけを数えると、ページングで「実行数 200」のような誤った値になる。
  function renderStats(stats) {
    const total = document.getElementById('ta-exec-stat-total');
    const rate = document.getElementById('ta-exec-stat-rate');
    const failedEl = document.getElementById('ta-exec-stat-failed');
    const s = stats || {};
    const completeN = s.complete || 0;
    const failedN = s.failed || 0;
    const cancelledN = s.cancelled || 0;
    const totalN = Number(s.total) || 0;
    const finished = completeN + failedN + cancelledN;
    const ratePct = finished ? Math.round((completeN / finished) * 100) : null;
    if (total) total.textContent = String(totalN);
    if (rate) {
      rate.textContent = ratePct === null ? '—' : `${ratePct}%`;
      rate.classList.remove('is-ok', 'is-ng');
      if (ratePct !== null) rate.classList.add(ratePct >= 80 ? 'is-ok' : 'is-ng');
    }
    if (failedEl) {
      failedEl.textContent = String(failedN);
      failedEl.classList.remove('is-ok', 'is-ng');
      failedEl.classList.add(failedN > 0 ? 'is-ng' : 'is-ok');
    }
    updateGauge(completeN, failedN, Math.max(0, totalN - completeN - failedN));
  }

  // 積み上げゲージ: 成功/失敗/未実行（実行中・中断を含む残り）の比率を形で見せる。
  // 数字を読む前に「赤の幅」で状態が入るようにする。
  function updateGauge(okN, ngN, waitN) {
    const sum = okN + ngN + waitN;
    const pct = (n) => (sum ? `${(n / sum) * 100}%` : '0%');
    const okBar = document.getElementById('ta-exec-gauge-ok');
    const ngBar = document.getElementById('ta-exec-gauge-ng');
    const waitBar = document.getElementById('ta-exec-gauge-wait');
    if (okBar) okBar.style.width = pct(okN);
    if (ngBar) ngBar.style.width = pct(ngN);
    if (waitBar) waitBar.style.width = pct(waitN);
    const okLegend = document.getElementById('ta-exec-legend-ok');
    const ngLegend = document.getElementById('ta-exec-legend-ng');
    const waitLegend = document.getElementById('ta-exec-legend-wait');
    if (okLegend) okLegend.textContent = `成功 ${okN.toLocaleString()}`;
    if (ngLegend) ngLegend.textContent = `失敗 ${ngN.toLocaleString()}`;
    if (waitLegend) waitLegend.textContent = `未実行 ${waitN.toLocaleString()}`;
  }

  // 行の左端 4px 帯の色（状態ごと）。band のみ＝目印。背景まで塗るのは失敗行だけ。
  function rowBandColor(status) {
    if (status === 'failed') return 'var(--d-ng-text)';
    if (status === 'complete') return 'var(--d-ok-text)';
    if (status === 'cancelled') return 'var(--d-wa-text)';
    return 'var(--d-info)'; // running / 不明
  }

  // 失敗を上に固定する（見るべきは失敗のため）。同じ状態内は元の順序を保つ安定ソート。
  function sortForDisplay(runs) {
    const failed = [];
    const rest = [];
    runs.forEach((run) => (run.status === 'failed' ? failed : rest).push(run));
    return failed.concat(rest);
  }

  function renderRows(runs) {
    const tbody = document.getElementById('ta-exec-result-body');
    if (!tbody) return;
    if (!runs.length) {
      tbody.innerHTML = '<tr><td colspan="5"><div class="empty">テスト実行の履歴がありません</div></td></tr>';
      return;
    }
    tbody.innerHTML = sortForDisplay(runs).map((run) => {
      const s = run.summary || {};
      // 失敗ステップ: 集計がある実行だけ件数を出す。集計を持たない実行は — （測って0ではない）
      const failedCell = Number(s.total) > 0 ? `${esc(s.failed ?? 0)} 件` : '—';
      const url = run.result_url
        || (run.domain && run.run_id ? `/runs/${encodeURIComponent(run.domain)}/${encodeURIComponent(run.run_id)}` : '');
      const evidence = url
        ? `<a href="${esc(url)}" class="ta-linkbtn">結果を開く</a>`
        : '<span class="muted-copy">—</span>';
      const band = rowBandColor(run.status);
      const bg = run.status === 'failed' ? 'color-mix(in srgb, var(--d-ng-text) 8%, var(--d-surface))' : 'transparent';
      return `<tr style="border-left:4px solid ${band};background:${bg};">
        <td>${esc(run.run_id || '—')}<div class="muted-copy">${esc(run.type_label || run.type || '')} ／ ${esc(run.domain || '')}</div></td>
        <td>${statusBadge(run.status)}</td>
        <td class="num">${esc(fmtDuration(s.duration_sec))}</td>
        <td class="num">${failedCell}</td>
        <td>${evidence}</td>
      </tr>`;
    }).join('');
  }

  function renderError(message) {
    const tbody = document.getElementById('ta-exec-result-body');
    if (tbody) tbody.innerHTML = `<tr><td colspan="5"><div class="empty">${esc(message)}</div></td></tr>`;
    ['ta-exec-stat-total', 'ta-exec-stat-rate', 'ta-exec-stat-failed'].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.textContent = '—';
    });
  }

  // 履歴は使うほど増えるため、直近 PAGE_SIZE 件だけ描画し「さらに表示」で継ぎ足す（INC-P01）。
  const PAGE_SIZE = 200;
  let _loadedRuns = [];
  let _totalRuns = 0;

  // 「さらに表示」行は DOM API で組む（innerHTML を経由させない）
  function _appendMoreRow(tbody) {
    const rest = _totalRuns - _loadedRuns.length;
    if (rest <= 0) return;
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 5;
    td.className = 'ta-exec-more-cell';
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn-outline-sm';
    btn.id = 'ta-exec-more';
    btn.textContent = `さらに ${Math.min(PAGE_SIZE, rest).toLocaleString()} 件を読み込む`
      + `（残り ${rest.toLocaleString()} 件）`;
    btn.addEventListener('click', () => loadMoreRuns(btn));
    td.appendChild(btn);
    tr.appendChild(td);
    tbody.appendChild(tr);
  }

  function _renderLoaded() {
    renderRows(_loadedRuns);
    const tbody = document.getElementById('ta-exec-result-body');
    if (tbody && _loadedRuns.length) _appendMoreRow(tbody);
    const countEl = document.getElementById('ta-exec-shown-count');
    if (countEl) {
      countEl.textContent = _totalRuns
        ? `${_totalRuns.toLocaleString()} 件中 ${_loadedRuns.length.toLocaleString()} 件を表示`
        : '';
    }
  }

  async function _fetchPage(offset) {
    const query = `type=${encodeURIComponent(TA_EXEC_TYPES.join(','))}`
      + `&limit=${PAGE_SIZE}&offset=${offset}`;
    const res = await fetch(`/api/history/runs?${query}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '実行履歴を取得できませんでした');
    return data;
  }

  async function loadTaExecution() {
    const tbody = document.getElementById('ta-exec-result-body');
    if (tbody) tbody.innerHTML = '<tr><td colspan="5"><div class="empty">読み込んでいます…</div></td></tr>';
    try {
      const data = await _fetchPage(0);
      _loadedRuns = data.runs || [];
      _totalRuns = Number(data.total) || 0;
      renderStats(data.stats);
      _renderLoaded();
      _loaded = true;
    } catch (e) {
      renderError(String(e && e.message ? e.message : e));
    }
  }

  async function loadMoreRuns(btn) {
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = '読み込んでいます…';
    try {
      const data = await _fetchPage(_loadedRuns.length);
      _loadedRuns = _loadedRuns.concat(data.runs || []);
      _totalRuns = Number(data.total) || _totalRuns;
      _renderLoaded();
    } catch (e) {
      // 追加分の失敗で既に表示している行を消さない。ボタンだけ戻して再試行できるようにする
      btn.disabled = false;
      btn.textContent = original;
      const countEl = document.getElementById('ta-exec-shown-count');
      if (countEl) countEl.textContent = '追加の読み込みに失敗しました（もう一度お試しください）';
    }
  }

  // ---- 実行起動（POST /api/testcases/run は同期実行。完了までレスポンスが返らない） ----
  const runBtn = document.getElementById('ta-exec-run');
  const suiteSel = document.getElementById('ta-exec-suite');
  const logEl = document.getElementById('ta-exec-log');
  const runBadge = document.getElementById('ta-exec-run-badge');
  const runProgressEl = document.getElementById('ta-exec-run-progress');
  const stopBtn = document.getElementById('ta-exec-stop');
  const envSel = document.getElementById('ta-exec-env');
  const parallelInput = document.getElementById('ta-exec-parallel');
  const exportBtn = document.getElementById('ta-exec-export');
  const exportStatusEl = document.getElementById('ta-exec-export-status');
  const logClearBtn = document.getElementById('ta-exec-log-clear');
  const logClearStatusEl = document.getElementById('ta-exec-log-clear-status');

  // 成功/失敗の単発フィードバック（ボタン脇のバッジに出す。ログとは別枠）
  function showStatusBadge(el, ok, message) {
    if (!el) return;
    el.textContent = message;
    el.className = `ta2-badge ${ok ? 'ta2-badge-ok' : 'ta2-badge-ng'}`;
    el.style.display = '';
  }

  // 並列度は 1〜16 に丸める（number input の min/max は入力自体を止めないため JS でも担保する）
  function clampParallel() {
    if (!parallelInput) return;
    const raw = Number(parallelInput.value);
    if (!parallelInput.value || !isFinite(raw)) {
      parallelInput.value = '1';
      return;
    }
    parallelInput.value = String(Math.min(16, Math.max(1, Math.round(raw))));
  }
  parallelInput?.addEventListener('change', clampParallel);

  // ログをクリア: フロントのみ（APIなし）。クリア後の空表示自体が結果の証跡になる。
  logClearBtn?.addEventListener('click', () => {
    if (logEl) logEl.textContent = '';
    showStatusBadge(logClearStatusEl, true, 'クリアしました');
  });

  function csvFilenameFromHeader(res, fallback) {
    const cd = res.headers.get('Content-Disposition') || '';
    const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
    return m ? decodeURIComponent(m[1]) : fallback;
  }

  async function exportResults() {
    if (!exportBtn) return;
    const domain = suiteSel && suiteSel.value;
    if (!domain) {
      showStatusBadge(exportStatusEl, false, '実行対象を選択してください');
      return;
    }
    const orig = exportBtn.textContent;
    exportBtn.disabled = true;
    exportBtn.textContent = '書き出し中…';
    showStatusBadge(exportStatusEl, true, '書き出し中…');
    try {
      const res = await fetch(`/api/ta/export?domain=${encodeURIComponent(domain)}&kind=results&format=csv`);
      if (!res.ok) {
        let msg = res.status === 503 ? 'LLMが未設定です' : '書き出しに失敗しました';
        try {
          const data = await res.clone().json();
          msg = data.error || msg;
        } catch (_e) {
          // CSV以外の応答（本文なし等）は既定メッセージのまま
        }
        throw new Error(msg);
      }
      const blob = await res.blob();
      const filename = csvFilenameFromHeader(res, `${domain}_results.csv`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      showStatusBadge(exportStatusEl, true, '書き出しました');
    } catch (e) {
      showStatusBadge(exportStatusEl, false, String(e && e.message ? e.message : e));
    } finally {
      exportBtn.disabled = false;
      exportBtn.textContent = orig;
    }
  }
  exportBtn?.addEventListener('click', exportResults);

  // 実行中かどうかを画面のどこにも示していなかったため、バッジ＋経過時間で明示する。
  let _elapsedTimer = null;
  let _startedAt = 0;
  function fmtElapsed(ms) {
    const totalSec = Math.max(0, Math.floor(ms / 1000));
    const mm = String(Math.floor(totalSec / 60)).padStart(2, '0');
    const ss = String(totalSec % 60).padStart(2, '0');
    return `${mm}:${ss}`;
  }
  function showRunBadge() {
    // 実行中は「実行」を隠し「実行を停止」だけ見せる（排他表示。両方出ていた不具合の修正）
    if (runBtn) runBtn.style.display = 'none';
    if (stopBtn) stopBtn.style.display = '';
    if (!runBadge) return;
    runBadge.style.display = '';
    _startedAt = Date.now();
    if (runProgressEl) runProgressEl.textContent = '00:00';
    _elapsedTimer = setInterval(() => {
      if (runProgressEl) runProgressEl.textContent = fmtElapsed(Date.now() - _startedAt);
    }, 1000);
  }
  function hideRunBadge() {
    if (runBtn) runBtn.style.display = '';
    if (stopBtn) stopBtn.style.display = 'none';
    if (runBadge) runBadge.style.display = 'none';
    if (_elapsedTimer) clearInterval(_elapsedTimer);
    _elapsedTimer = null;
  }

  // ログは追記のみ。クリア・折りたたみをしない（実行ログ常時表示のユーザー規約）。
  function appendLog(line) {
    if (!logEl) return;
    logEl.textContent += (logEl.textContent ? '\n' : '') + line;
  }

  function syncRunButton() {
    if (!runBtn || !suiteSel) return;
    // 実行中は select を変えてもボタンを再有効化しない（走っているのは選択前の対象のため）
    if (_running) return;
    const ready = Boolean(suiteSel.value);
    runBtn.disabled = !ready;
    runBtn.title = ready ? '選択した対象のテストを実行します' : '実行対象を選択してください';
  }

  let _suitesLoaded = false;
  async function loadSuites() {
    if (!suiteSel) return;
    try {
      const res = await fetch('/api/history');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || '実行対象を取得できませんでした');
      // ケース表を組める report.json（JSON 形式の成果物）を持つドメインだけを実行対象にする
      const items = (data.items || []).filter(
        (it) => Number(it.screens) > 0 && (it.formats || []).includes('JSON'),
      );
      suiteSel.innerHTML = '<option value="">テストスイートを選択</option>'
        + items.map((it) => `<option value="${esc(it.domain)}">${esc(it.domain)}</option>`).join('');
      _suitesLoaded = true;
    } catch (e) {
      appendLog(`実行対象の取得に失敗しました: ${String(e && e.message ? e.message : e)}`);
    }
    syncRunButton();
  }

  // 実行中の途中経過。live-progress の tests は追記順（古い→新しい）の直近窓のため、
  // 出力済み件数（_lastCompleted）との差分だけを末尾から取り出して追記する。
  let _running = false;
  let _lastCompleted = 0;
  // 実行中のサーバ側 run_id。停止 API に渡す。live-progress が実行中だけ返す。
  let _execRunId = '';
  async function pollProgress(domain) {
    try {
      const res = await fetch(`/api/testcases/live-progress?domain=${encodeURIComponent(domain)}`);
      const data = await res.json();
      // 応答が実行完了後に届いた分は捨てる（要約行の後にケース行が混ざらないように）
      if (!res.ok || !_running) return;
      // run_id が届いて初めてサーバ側の実行を止められる（それ以前は止める相手がいない）。
      if (data.run_id) _execRunId = String(data.run_id);
      const completed = Number(data.done) || 0;
      const total = Number(data.total) || 0;
      // slice(-0) は全件コピーになるため、差分 0 件は明示的に空にする
      const delta = Math.max(0, completed - _lastCompleted);
      const fresh = delta > 0 ? (data.tests || []).slice(-delta) : [];
      fresh.forEach((t, i) => {
        const mark = t.status === 'passed' ? 'PASS'
          : (t.status === 'failed' ? 'FAIL' : String(t.status || '').toUpperCase());
        appendLog(`[${_lastCompleted + i + 1}/${total || '?'}] ${t.title || ''} ${mark}`);
      });
      _lastCompleted = Math.max(_lastCompleted, completed);
    } catch (_e) {
      // ポーリングの単発失敗は無視する（結果の正は POST の応答）
    }
  }

  let _runAbort = null;
  let _pollTimer = null;

  async function runSuite() {
    if (!runBtn || !suiteSel || !suiteSel.value || _running) return;
    const domain = suiteSel.value;
    const env = envSel && envSel.value ? envSel.value : 'local';
    clampParallel();
    const parallel = parallelInput ? Number(parallelInput.value) || 1 : 1;
    const origLabel = runBtn.textContent;
    runBtn.disabled = true;
    runBtn.textContent = '実行中…';
    _running = true;
    _lastCompleted = 0;
    _execRunId = '';
    appendLog(`実行を開始します: ${domain}（環境: ${env} / 並列度: ${parallel}）`);
    showRunBadge();
    _runAbort = new AbortController();
    _pollTimer = setInterval(() => pollProgress(domain), 2000);
    try {
      const res = await fetch('/api/testcases/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain, per_test_timeout_sec: 20, env, parallel }),
        signal: _runAbort.signal,
      });
      const data = await res.json();
      _running = false;
      clearInterval(_pollTimer);
      _pollTimer = null;
      if (!res.ok || data.error) throw new Error(data.error || '実行に失敗しました');
      const s = (data.run && data.run.summary) || {};
      appendLog(`実行完了: PASS ${s.passed ?? 0} / FAIL ${s.failed ?? 0} / 全${s.total ?? 0}件（run_id: ${data.run_id || '—'}）`);
      await loadTaExecution();
    } catch (e) {
      _running = false;
      if (_pollTimer) {
        clearInterval(_pollTimer);
        _pollTimer = null;
      }
      if (e && e.name === 'AbortError') {
        appendLog('停止しました');
      } else {
        appendLog(`エラー: ${String(e && e.message ? e.message : e)}`);
      }
    } finally {
      _runAbort = null;
      runBtn.textContent = origLabel;
      hideRunBadge();
      syncRunButton();
    }
  }

  // 実行の停止。以前はフロントの fetch を abort するだけで、サーバ側の Playwright は
  // 走り続けていた（画面上は止まったように見えるだけの偽の停止）。いまは先に
  // /api/testcases/cancel でサーバ側のプロセスを落としてから abort する。
  stopBtn?.addEventListener('click', async () => {
    if (!_running) return;
    stopBtn.disabled = true;
    const label = stopBtn.textContent;
    stopBtn.textContent = '停止中…';
    try {
      if (_execRunId) {
        const body = new URLSearchParams({ run_id: _execRunId });
        const res = await fetch('/api/testcases/cancel', { method: 'POST', body });
        const data = await res.json().catch(() => ({}));
        // 止める相手がいなかったことは隠さない（既に終わっていた場合など）。
        if (!data || !data.ok) appendLog('サーバ側の実行は見つかりませんでした（既に終了した可能性があります）');
      } else {
        appendLog('実行の識別子がまだ届いていないため、サーバ側は停止できませんでした');
      }
    } catch (e) {
      appendLog(`停止要求に失敗しました: ${String(e && e.message ? e.message : e)}`);
    } finally {
      stopBtn.disabled = false;
      stopBtn.textContent = label;
      if (_runAbort) _runAbort.abort();
    }
  });

  if (typeof onViewEnter === 'function') {
    onViewEnter('test-execution', () => {
      if (!_loaded) loadTaExecution();
      if (!_suitesLoaded) loadSuites();
    });
  }
  document.getElementById('ta-exec-reload')?.addEventListener('click', loadTaExecution);
  suiteSel?.addEventListener('change', syncRunButton);
  runBtn?.addEventListener('click', runSuite);
})();
