// ---- テスト活動支援 / 計画（マスタテスト計画） ----
// この画面は「決める」画面。9項目の記入状況から未決数をその場で数え、
// 全部埋まったら確定できるようにする。保存APIは無いため値は DOM 状態のみで保持する。
(function () {
  'use strict';

  const DOMAIN_KEY = 'webspec2doc.ta.domain';

  function currentDomain() {
    try {
      const v = sessionStorage.getItem(DOMAIN_KEY);
      if (v) return v;
    } catch (e) { /* 非対応環境 */ }
    return '';
  }

  async function resolveDomain() {
    const d = currentDomain();
    if (d) return d;
    try {
      const res = await fetch('/api/history');
      const data = await res.json();
      const first = (data.items || [])[0];
      if (first && first.domain) {
        try { sessionStorage.setItem(DOMAIN_KEY, first.domain); } catch (e) { /* noop */ }
        return first.domain;
      }
    } catch (e) { /* noop */ }
    return '';
  }

  function isFilled(el) { return !!(el && el.value && el.value.trim() !== ''); }

  function hasDynRow(container) {
    if (!container) return false;
    const inputs = container.querySelectorAll('.ta-dyn-row input');
    for (const inp of inputs) { if (isFilled(inp)) return true; }
    return false;
  }

  // ---- 動的な行の追加（保存先が無いのでDOMに足すだけ） ----
  function ensureEmpty(container, text) {
    if (!container.querySelector('.ta-dyn-row')) {
      container.innerHTML = '<div class="empty">' + text + '</div>';
    }
  }

  function addListRow(containerId, placeholder, emptyText) {
    const c = document.getElementById(containerId);
    if (!c) return;
    const empty = c.querySelector('.empty');
    if (empty) empty.remove();
    const row = document.createElement('div');
    row.className = 'ta-dyn-row';
    row.style.cssText = 'display:flex; align-items:center; gap:6px; margin-bottom:6px;';
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'input-compact';
    input.style.flex = '1';
    input.placeholder = placeholder;
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'ta-linkbtn';
    remove.textContent = '×';
    remove.setAttribute('aria-label', '削除');
    row.appendChild(input);
    row.appendChild(remove);
    c.appendChild(row);
    input.addEventListener('input', recompute);
    remove.addEventListener('click', () => { row.remove(); ensureEmpty(c, emptyText); recompute(); });
    input.focus();
    recompute();
  }

  function addTableRow(tbodyId, placeholders, emptyText) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;
    const emptyCell = tbody.querySelector('.empty');
    if (emptyCell) tbody.innerHTML = '';
    const tr = document.createElement('tr');
    tr.className = 'ta-dyn-row';
    placeholders.forEach((ph, i) => {
      const td = document.createElement('td');
      if (i === placeholders.length - 1) {
        td.style.cssText = 'display:flex; align-items:center; gap:6px;';
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'input-compact';
        input.style.flex = '1';
        input.placeholder = ph;
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'ta-linkbtn';
        remove.textContent = '×';
        remove.setAttribute('aria-label', '削除');
        td.appendChild(input);
        td.appendChild(remove);
        remove.addEventListener('click', () => { tr.remove(); ensureEmptyTable(tbody, placeholders.length, emptyText); recompute(); });
        input.addEventListener('input', recompute);
      } else {
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'input-compact';
        input.style.width = '100%';
        input.placeholder = ph;
        input.addEventListener('input', recompute);
        td.appendChild(input);
      }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
    const firstInput = tr.querySelector('input');
    if (firstInput) firstInput.focus();
    recompute();
  }

  function ensureEmptyTable(tbody, colCount, emptyText) {
    if (!tbody.querySelector('.ta-dyn-row')) {
      tbody.innerHTML = '<tr><td colspan="' + colCount + '"><div class="empty">' + emptyText + '</div></td></tr>';
    }
  }

  // ---- スコープ/リスク/工数見積のアコーディオン（既定で1件だけ開く） ----
  const ACCORDION_KEYS = ['scope-in', 'scope-out', 'assumptions', 'risk', 'estimate'];
  let openAccordionKey = 'scope-in';

  function applyAccordionState() {
    ACCORDION_KEYS.forEach((key) => {
      const item = document.querySelector('.ta-decision-item[data-decision="' + key + '"]');
      if (!item) return;
      const row = item.querySelector('[data-dec-row]');
      const body = item.querySelector('[data-acc-body]');
      const chevron = item.querySelector('[data-acc-chevron]');
      const isOpen = key === openAccordionKey;
      if (body) body.style.display = isOpen ? '' : 'none';
      if (chevron) chevron.textContent = isOpen ? '▾' : '▸';
      if (row) row.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    });
  }

  function toggleAccordion(key) {
    openAccordionKey = openAccordionKey === key ? null : key;
    applyAccordionState();
  }

  function initAccordion() {
    ACCORDION_KEYS.forEach((key) => {
      const item = document.querySelector('.ta-decision-item[data-decision="' + key + '"]');
      if (!item) return;
      const row = item.querySelector('[data-dec-row]');
      if (!row) return;
      row.addEventListener('click', (e) => {
        if (e.target.closest('button')) return;
        toggleAccordion(key);
      });
      row.addEventListener('keydown', (e) => {
        if (e.target.closest('button')) return;
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          toggleAccordion(key);
        }
      });
    });
    applyAccordionState();
  }

  // ---- 未決カウントと確定レールの更新 ----
  const DECISIONS = [
    { key: 'system', check: () => isFilled(document.getElementById('ta-plan-system')) },
    { key: 'release', check: () => isFilled(document.getElementById('ta-plan-release')) },
    { key: 'period', check: () => isFilled(document.getElementById('ta-plan-period-from')) && isFilled(document.getElementById('ta-plan-period-to')) },
    { key: 'team', check: () => isFilled(document.getElementById('ta-plan-team')) },
    { key: 'scope-in', check: () => hasDynRow(document.getElementById('ta-plan-scope-in')) },
    { key: 'scope-out', check: () => hasDynRow(document.getElementById('ta-plan-scope-out')) },
    { key: 'assumptions', check: () => hasDynRow(document.getElementById('ta-plan-assumptions')) },
    { key: 'risk', check: () => hasDynRow(document.getElementById('ta-plan-risk-body')) },
    { key: 'estimate', check: () => hasDynRow(document.getElementById('ta-plan-estimate-body')) },
  ];

  function recompute() {
    let decidedCount = 0;
    DECISIONS.forEach((d) => {
      const decided = d.check();
      if (decided) decidedCount += 1;
      const item = document.querySelector('.ta-decision-item[data-decision="' + d.key + '"]');
      if (!item) return;
      const row = item.querySelector('[data-dec-row]');
      const dot = item.querySelector('[data-dec-dot]');
      const hint = item.querySelector('[data-dec-hint]');
      if (row) {
        row.style.background = decided ? '' : 'rgba(251,189,35,.12)';
        row.style.borderLeftColor = decided ? 'transparent' : '#B77800';
      }
      if (dot) dot.style.color = decided ? '#16a34a' : '#B77800';
      if (hint) hint.style.display = decided ? 'none' : '';
    });

    const total = DECISIONS.length;
    const undecided = total - decidedCount;
    const countEl = document.getElementById('ta-plan-undecided-count');
    if (countEl) {
      countEl.textContent = undecided + ' / ' + total;
      countEl.classList.toggle('is-wa', undecided > 0);
      countEl.classList.toggle('is-ok', undecided === 0);
    }
    const badge = document.getElementById('ta-plan-status-badge');
    if (badge) {
      const confirmed = badge.dataset.confirmed === '1';
      if (!confirmed) {
        badge.textContent = undecided === 0 ? '確定可能' : '未確定';
        badge.classList.toggle('ta2-badge-wa', undecided > 0);
        badge.classList.toggle('ta2-badge-ok', undecided === 0);
      }
    }
    const confirmBtn = document.getElementById('ta-plan-confirm');
    const reason = document.getElementById('ta-plan-confirm-reason');
    if (confirmBtn && confirmBtn.dataset.confirmed !== '1') {
      confirmBtn.disabled = undecided > 0;
      if (reason) {
        reason.textContent = undecided > 0
          ? ('あと ' + undecided + ' 項目を決めると確定できます')
          : 'すべて決まりました。確定できます。';
      }
    }
  }

  function onConfirm() {
    const btn = document.getElementById('ta-plan-confirm');
    const badge = document.getElementById('ta-plan-status-badge');
    const reason = document.getElementById('ta-plan-confirm-reason');
    if (!btn || btn.disabled) return;
    btn.disabled = true;
    btn.dataset.confirmed = '1';
    btn.textContent = '確定済み';
    if (badge) {
      badge.dataset.confirmed = '1';
      badge.textContent = '確定済み';
      badge.classList.remove('ta2-badge-wa');
      badge.classList.add('ta2-badge-ok');
    }
    if (reason) reason.textContent = '保存先が未接続のため、再読込すると確定状態は消えます。';
  }

  // ---- 確定でアンロックされる次工程（実APIを参照） ----
  async function loadUnlock() {
    const list = document.getElementById('ta-plan-unlock-list');
    if (!list) return;
    const domain = await resolveDomain();
    if (!domain) {
      list.innerHTML = '<li>対象システム未選択のため確認できません</li>';
      return;
    }
    try {
      const res = await fetch('/api/ta/process?domain=' + encodeURIComponent(domain));
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || '取得失敗');
      const phases = Array.isArray(data.phases) ? data.phases : [];
      const idx = typeof data.unlocked_index === 'number' ? data.unlocked_index : -1;
      const next = phases[idx];
      if (next && next.label) {
        list.textContent = '';
        const li = document.createElement('li');
        li.textContent = next.label + ' に進めるようになります';
        list.appendChild(li);
      } else if (data.all_completed) {
        list.innerHTML = '<li>全工程が完了しています</li>';
      } else {
        list.innerHTML = '<li>次工程の情報がありません</li>';
      }
    } catch (e) {
      list.innerHTML = '<li>工程情報を取得できませんでした</li>';
    }
  }

  function init() {
    ['ta-plan-system', 'ta-plan-release', 'ta-plan-period-from', 'ta-plan-period-to', 'ta-plan-team']
      .forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('input', recompute);
      });

    document.getElementById('ta-plan-scope-in-add')?.addEventListener('click', () => addListRow('ta-plan-scope-in', '例: ログイン機能', '上の［追加］で今回扱う機能を1件ずつ入力します'));
    document.querySelector('[data-ta-action="plan-scope-out-add"]')?.addEventListener('click', () => addListRow('ta-plan-scope-out', '例: 旧管理画面（理由: 廃止予定）', '上の［追加］で今回扱わない範囲と理由を1件ずつ入力します'));
    document.querySelector('[data-ta-action="plan-assumption-add"]')?.addEventListener('click', () => addListRow('ta-plan-assumptions', '例: テスト環境は本番同等データを使用', '上の［追加］で環境・データ・依存の前提条件を1件ずつ入力します'));
    document.querySelector('[data-ta-action="plan-risk-add"]')?.addEventListener('click', () => addTableRow('ta-plan-risk-body', ['リスク', '影響', '発生度', '対応', '担当'], '上の［追加］でリスクを1件ずつ入力します'));
    document.getElementById('ta-plan-estimate-add')?.addEventListener('click', () => addTableRow('ta-plan-estimate-body', ['工程', '想定ケース数', '想定工数', '担当'], '上の［追加］で工程ごとの見積を入力します'));

    document.getElementById('ta-plan-confirm')?.addEventListener('click', onConfirm);

    initAccordion();
    recompute();
    loadUnlock();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
