// ---- テスト活動支援 / テスト完了 ----
// テスト計画で定めた終了基準に、実測値を突き合わせて判定する。
// 判定は表示するだけで、完了そのものは人が承認する（自動でクローズしない）。
(function () {
  'use strict';

  let _loaded = false;

  const esc = (v) => (typeof escHtml === 'function'
    ? escHtml(String(v))
    : String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));

  function domain() {
    const sel = document.getElementById('ta-design-domain') || document.getElementById('ta-exec-suite');
    return sel && sel.value ? sel.value : '';
  }

  function renderCriteria(criteria) {
    const tbody = document.getElementById('ta-completion-criteria-body');
    if (!tbody) return;
    if (!criteria || !criteria.length) {
      tbody.innerHTML = '<tr><td colspan="4"><div class="empty">終了基準がまだありません（テスト計画で設定します）</div></td></tr>';
      return;
    }
    tbody.innerHTML = criteria.map((c) => `<tr>
      <td>${esc(c.label)}</td>
      <td class="num">${esc(c.target)}</td>
      <td class="num">${esc(c.current)}</td>
      <td><span class="ta2-badge ta2-badge-${c.met ? 'ok' : 'ng'}">${c.met ? '達成' : '未達'}</span></td>
    </tr>`).join('');
  }

  function renderVerdict(overall) {
    const el = document.getElementById('ta-completion-verdict');
    if (!el) return;
    const met = overall && overall.met;
    el.textContent = '総合判定: ' + (overall && overall.label ? overall.label : '判定待ち');
    el.className = 'ta2-badge ta2-badge-' + (met ? 'ok' : 'ng');
  }

  function renderBlockers(blockers) {
    const box = document.getElementById('ta-completion-blockers');
    if (!box) return;
    if (!blockers || !blockers.length) {
      box.innerHTML = '<div class="empty">完了を妨げている重大な不具合はありません</div>';
      return;
    }
    box.innerHTML = blockers.map((b) => `<div class="ta-source-row">
      <span class="ta2-badge ta2-badge-wa">${esc(b.state_label || b.state || '')}</span>
      <b>${esc(b.id || '')}</b> ${esc(b.summary || '')}
    </div>`).join('');
  }

  async function load() {
    const dom = domain();
    const tbody = document.getElementById('ta-completion-criteria-body');
    if (!dom) {
      if (tbody) tbody.innerHTML = '<tr><td colspan="4"><div class="empty">対象ドメインを選択してください（テストケース実装の画面で選べます）</div></td></tr>';
      return;
    }
    if (tbody) tbody.innerHTML = '<tr><td colspan="4"><div class="empty">読み込んでいます…</div></td></tr>';
    try {
      const res = await fetch('/api/ta/completion?domain=' + encodeURIComponent(dom));
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || '判定を取得できませんでした');
      renderCriteria(data.criteria);
      renderVerdict(data.overall);
      renderBlockers(data.blockers);
      _loaded = true;
    } catch (e) {
      if (tbody) tbody.innerHTML = `<tr><td colspan="4"><div class="empty">${esc(String(e && e.message ? e.message : e))}</div></td></tr>`;
    }
  }

  if (typeof onViewEnter === 'function') {
    onViewEnter('test-completion', () => { if (!_loaded) load(); });
  }
  // 承認・レポート生成はバックエンド未実装。押しても黙って何も起きない状態にしない。
  document.getElementById('ta-completion-approve')?.addEventListener('click', () => {
    const el = document.getElementById('ta-completion-verdict');
    if (el) el.insertAdjacentHTML('afterend',
      '<span class="muted-copy">承認の記録機能は未実装です（判定の表示のみ動作します）</span>');
  });
})();
