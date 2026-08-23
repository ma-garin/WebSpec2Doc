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

  function renderStats(runs) {
    const total = document.getElementById('ta-exec-stat-total');
    const rate = document.getElementById('ta-exec-stat-rate');
    const failedEl = document.getElementById('ta-exec-stat-failed');
    const failed = runs.filter((r) => r.status === 'failed').length;
    const complete = runs.filter((r) => r.status === 'complete').length;
    const finished = failed + complete + runs.filter((r) => r.status === 'cancelled').length;
    if (total) total.textContent = String(runs.length);
    if (rate) rate.textContent = finished ? `${Math.round((complete / finished) * 100)}%` : '—';
    if (failedEl) failedEl.textContent = String(failed);
  }

  function renderRows(runs) {
    const tbody = document.getElementById('ta-exec-result-body');
    if (!tbody) return;
    if (!runs.length) {
      tbody.innerHTML = '<tr><td colspan="5"><div class="empty">テスト実行の履歴がありません</div></td></tr>';
      return;
    }
    tbody.innerHTML = runs.map((run) => {
      const s = run.summary || {};
      // 失敗ステップ: 集計がある実行だけ件数を出す。集計を持たない実行は — （測って0ではない）
      const failedCell = Number(s.total) > 0 ? `${esc(s.failed ?? 0)} 件` : '—';
      const url = run.result_url
        || (run.domain && run.run_id ? `/runs/${encodeURIComponent(run.domain)}/${encodeURIComponent(run.run_id)}` : '');
      const evidence = url
        ? `<a href="${esc(url)}" class="btn-outline-sm">結果を開く</a>`
        : '<span class="muted-copy">—</span>';
      return `<tr>
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

  async function loadTaExecution() {
    const tbody = document.getElementById('ta-exec-result-body');
    if (tbody) tbody.innerHTML = '<tr><td colspan="5"><div class="empty">読み込んでいます…</div></td></tr>';
    try {
      const res = await fetch('/api/history/runs');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || '実行履歴を取得できませんでした');
      const runs = (data.runs || []).filter((r) => TA_EXEC_TYPES.includes(r.type));
      renderStats(runs);
      renderRows(runs);
      _loaded = true;
    } catch (e) {
      renderError(String(e && e.message ? e.message : e));
    }
  }

  // ---- 実行起動（POST /api/testcases/run は同期実行。完了までレスポンスが返らない） ----
  const runBtn = document.getElementById('ta-exec-run');
  const suiteSel = document.getElementById('ta-exec-suite');
  const logEl = document.getElementById('ta-exec-log');

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
  async function pollProgress(domain) {
    try {
      const res = await fetch(`/api/testcases/live-progress?domain=${encodeURIComponent(domain)}`);
      const data = await res.json();
      // 応答が実行完了後に届いた分は捨てる（要約行の後にケース行が混ざらないように）
      if (!res.ok || !_running) return;
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

  async function runSuite() {
    if (!runBtn || !suiteSel || !suiteSel.value || _running) return;
    const domain = suiteSel.value;
    const origLabel = runBtn.textContent;
    runBtn.disabled = true;
    runBtn.textContent = '実行中…';
    _running = true;
    _lastCompleted = 0;
    appendLog(`実行を開始します: ${domain}`);
    const timer = setInterval(() => pollProgress(domain), 2000);
    try {
      const res = await fetch('/api/testcases/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain, per_test_timeout_sec: 20 }),
      });
      const data = await res.json();
      _running = false;
      clearInterval(timer);
      if (!res.ok || data.error) throw new Error(data.error || '実行に失敗しました');
      const s = (data.run && data.run.summary) || {};
      appendLog(`実行完了: PASS ${s.passed ?? 0} / FAIL ${s.failed ?? 0} / 全${s.total ?? 0}件（run_id: ${data.run_id || '—'}）`);
      await loadTaExecution();
    } catch (e) {
      _running = false;
      clearInterval(timer);
      appendLog(`エラー: ${String(e && e.message ? e.message : e)}`);
    } finally {
      runBtn.textContent = origLabel;
      syncRunButton();
    }
  }

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
