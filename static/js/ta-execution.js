// ---- テスト活動支援 / 実行ビュー ----
// 既存の実行基盤（/api/history/runs）を読み取り専用で共用する。
// この画面からの実行起動は未実装（起動系のボタンは HTML 側で無効化済み）。
(function () {
  'use strict';

  // テスト実行に該当する種別だけを扱う（クロール等のドキュメント作成は混ぜない）。
  // 実測（2026-08-22・/api/history/runs 3752件）で存在する type は autorun / crawl のみ。
  const TA_EXEC_TYPES = ['autorun'];
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

  if (typeof onViewEnter === 'function') {
    onViewEnter('test-execution', () => { if (!_loaded) loadTaExecution(); });
  }
  document.getElementById('ta-exec-reload')?.addEventListener('click', loadTaExecution);
})();
