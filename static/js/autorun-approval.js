function arShowPreview() {
  const panel = document.getElementById('autorun-preview-panel');
  if (!panel) return;
  const isOpen = panel.style.display === 'flex';
  if (isOpen) {
    panel.style.display = 'none';
    return;
  }
  panel.style.display = 'flex';
  if (!_autoRunPreviewLoaded) {
    _autoRunPreviewLoaded = true;
    _autorunLoadPreview();
  }
}

function _autorunClosePreviewOnBackdrop(e) {
  if (e.target === document.getElementById('autorun-preview-panel')) arShowPreview();
}

// ---- AutoRun: テストプレビュー ----
async function _autorunLoadPreview() {
  if (!_autoRunJobId) return;
  const loadingEl = document.getElementById('autorun-preview-loading');
  if (loadingEl) loadingEl.textContent = '読み込み中…';
  try {
    const data = await fetch('/api/autorun/preview?job_id=' + encodeURIComponent(_autoRunJobId)).then(r => r.json());
    _autoRunPreviewData = data;
    _autorunRenderPreview(data);
    if (loadingEl) loadingEl.textContent = '';
  } catch (e) {
    if (loadingEl) loadingEl.textContent = '(読み込みエラー)';
  }
}

function _autorunRenderPreview(data) {
  const summaryEl = document.getElementById('autorun-preview-summary');
  const tableWrap = document.getElementById('autorun-preview-table-wrap');
  const specEl    = document.getElementById('autorun-preview-spec');

  const summary    = data.summary || {};
  const candidates = data.candidates || [];
  const byStatus   = summary.by_status || {};
  const byTitle    = summary.by_title || {};

  // サマリーバー
  if (summaryEl) {
    const autoCount  = byStatus.auto || 0;
    const skipCount  = (byStatus['manual-review'] || 0) + (byStatus.review || 0);
    const titleBadges = Object.entries(byTitle)
      .map(([t, c]) => `<span class="fmt-badge">${escHtml(t)}: ${c}</span>`)
      .join('');
    summaryEl.innerHTML = `
      <div class="autorun-preview-counts">
        <span><strong>${summary.total || 0}</strong> 件</span>
        <span class="status-low">自動: ${autoCount}</span>
        <span class="status-muted">スキップ: ${skipCount}</span>
      </div>
      <div class="fmt-badges autorun-preview-badges">${titleBadges}</div>`;
  }

  // テストケーステーブル（行クリックで手順・期待結果の全文を別行に展開する。
  // 従来は steps がどこにも表示されず、期待結果も60文字で打ち切られていた。）
  if (tableWrap) {
    if (candidates.length) {
      const rows = candidates.map((c, i) => {
        const statusCls = c.automation_status === 'auto' ? 'status-low' : 'status-muted';
        const steps = Array.isArray(c.steps) ? c.steps : [];
        const stepsHtml = steps.length
          ? '<ol class="autorun-case-steps">' + steps.map(s => `<li>${escHtml(String(s))}</li>`).join('') + '</ol>'
          : '<p class="muted-copy">手順の記録なし</p>';
        return `<tr class="autorun-case-row" data-case-idx="${i}" tabindex="0" role="button" aria-expanded="false">
          <td class="cell-id">${escHtml(c.id || '')}</td>
          <td class="cell-title">${escHtml(c.title || '')} <span class="autorun-case-detail-toggle">詳細 ▶</span></td>
          <td class="cell-status ${statusCls}">${escHtml(c.automation_status || '')}</td>
          <td class="cell-id">${escHtml(c.trace_id || '')}</td>
          <td class="cell-muted">${escHtml((c.expected || '').substring(0, 60))}</td>
        </tr>
        <tr class="autorun-case-detail-row" data-case-detail="${i}" hidden>
          <td colspan="5">
            <div class="autorun-case-detail-body">
              <div><strong>手順</strong>${stepsHtml}</div>
              <div><strong>期待結果</strong><p>${escHtml(c.expected || '(記録なし)')}</p></div>
            </div>
          </td>
        </tr>`;
      }).join('');
      tableWrap.innerHTML = `<table class="data autorun-preview-table">
        <thead><tr><th>ID</th><th>タイトル</th><th>自動化</th><th>Trace</th><th>期待結果</th></tr></thead>
        <tbody>${rows}</tbody></table>`;
      tableWrap.querySelectorAll('.autorun-case-row').forEach(row => {
        const toggle = () => {
          const idx = row.dataset.caseIdx;
          const detailRow = tableWrap.querySelector(`[data-case-detail="${idx}"]`);
          const toggleLabel = row.querySelector('.autorun-case-detail-toggle');
          if (!detailRow) return;
          const nowOpen = detailRow.hasAttribute('hidden');
          if (nowOpen) detailRow.removeAttribute('hidden'); else detailRow.setAttribute('hidden', '');
          row.setAttribute('aria-expanded', String(nowOpen));
          if (toggleLabel) toggleLabel.textContent = nowOpen ? '詳細 ▼' : '詳細 ▶';
        };
        row.addEventListener('click', toggle);
        row.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } });
      });
    } else {
      tableWrap.innerHTML = '<div class="empty arm-empty">テストケースなし</div>';
    }
  }

  // スクリプト
  if (specEl) specEl.textContent = data.spec_content || '(スクリプトなし)';
}

// ---- AutoRun: 承認（共通ロジック） ----
async function _autorunDoApprove(filterMode, perTestTimeoutSec) {
  if (!_autoRunJobId) return false;
  try {
    const res = await fetch('/api/autorun/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: _autoRunJobId, filter_mode: filterMode, per_test_timeout_sec: perTestTimeoutSec }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || '承認に失敗しました');
    _autorunHideApprovalModal();
    _autorunStartPolling();
    _autorunStartElapsed();
    return true;
  } catch (e) {
    autorunSetStartStatus(String(e), true);
    return false;
  }
}

// 承認モーダルの承認ボタン（承認UIはこのモーダルに一本化）
async function autorunApprovalModalApprove() {
  const btn = document.getElementById('arm-approve-btn');
  if (btn) { btn.disabled = true; btn.textContent = '開始中…'; }
  const filterMode = document.querySelector('input[name="arm-filter"]:checked')?.value || 'all';
  const perTestTimeoutSec = parseInt(document.getElementById('arm-timeout')?.value || '30', 10);
  await _autorunDoApprove(filterMode, perTestTimeoutSec);
  if (btn) { btn.disabled = false; btn.textContent = 'テスト実行を開始'; }
}

// ---- AutoRun: 承認モーダル ----
async function _autorunPrepareAndShowApprovalModal() {
  if (!_autoRunPreviewLoaded) {
    _autoRunPreviewLoaded = true;
    await _autorunLoadPreview();
  }
  _autorunShowApprovalModal();
}

function _autorunShowApprovalModal() {
  const modal = document.getElementById('autorun-approval-modal');
  if (!modal) return;
  _autorunPopulateApprovalModal();
  modal.style.display = 'flex';
}

function _autorunHideApprovalModal() {
  const modal = document.getElementById('autorun-approval-modal');
  if (modal) modal.style.display = 'none';
}

function _autorunPopulateApprovalModal() {
  if (!_autoRunPreviewData) return;
  const summary = _autoRunPreviewData.summary || {};
  const counts = summary.filter_counts || {};
  const byStatus = summary.by_status || {};

  // サマリー数値ストリップ
  const summaryEl = document.getElementById('arm-summary');
  if (summaryEl) {
    const total = summary.total || 0;
    const auto  = byStatus.auto || 0;
    const skip  = (byStatus['manual-review'] || 0) + (byStatus.review || 0);
    summaryEl.textContent = '';
    [
      { n: total, label: 'テストケース', cls: 'status-default' },
      { n: auto,  label: '自動実行',    cls: 'status-low' },
      { n: skip,  label: 'スキップ',    cls: 'status-muted' },
    ].forEach(({ n, label, cls }) => {
      const wrap = document.createElement('div');
      wrap.className = 'arm-summary-stat';
      const num = document.createElement('strong');
      num.className = cls;
      num.textContent = String(n);
      const lbl = document.createElement('span');
      lbl.textContent = label;
      wrap.appendChild(num); wrap.appendChild(lbl);
      summaryEl.appendChild(wrap);
    });
  }

  // フィルターカウントバッジ
  const fcMap = { all: 'arm-fc-all', smoke: 'arm-fc-smoke', transition: 'arm-fc-transition', form: 'arm-fc-form' };
  for (const [key, id] of Object.entries(fcMap)) {
    const el = document.getElementById(id);
    if (el) el.textContent = counts[key] != null ? `${counts[key]}件` : '';
  }

}

// テストケース一覧: 専用ビュー（テストケース画面）へ遷移する
document.getElementById('arm-view-testcases-btn')?.addEventListener('click', () => {
  const domain = _autoRunPreviewData?.domain || '';
  if (typeof tcNavigateFromApproval === 'function') tcNavigateFromApproval(domain);
});

// ---- AutoRun: 停止 ----
