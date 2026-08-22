// ---- テスト活動支援 / テスト設計ビュー ----
// 生成テストケースは System 01（ドキュメント作成）の生成結果を共用する。
// データ源: /api/history（ドメイン一覧）, /api/testcases/table?domain=...（ケース一覧）
(function () {
  'use strict';

  const esc = (v) => String(v == null ? '' : v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const $ = (id) => document.getElementById(id);

  // 実データに値が無いセルは「—」を出す。推測で埋めない。
  const DASH = '—';
  function cellText(v) {
    return (v == null || v === '') ? DASH : esc(v);
  }
  function cellList(v) {
    if (Array.isArray(v)) return v.length ? v.map(esc).join('<br>') : DASH;
    return cellText(v);
  }

  function setBadge(text) {
    const el = $('ta-design-count');
    if (el) el.textContent = text;
  }

  function showMessage(msg) {
    const body = $('ta-case-body');
    if (body) body.innerHTML = `<tr><td colspan="7"><div class="empty">${esc(msg)}</div></td></tr>`;
  }

  function renderRows(rows) {
    if (!rows.length) {
      showMessage('このドメインには生成テストケースがありません');
      return;
    }
    // 列マップ: ケースID=case_id / 目的=name / 事前条件=preconditions /
    // 手順=steps / 期待結果=expected / 対応するテスト条件=viewpoint（観点）。
    // 優先度は実データに存在しないため常に「—」。
    $('ta-case-body').innerHTML = rows.map((r) => `<tr>
      <td>${cellText(r.case_id)}</td>
      <td>${cellText(r.name)}</td>
      <td>${cellList(r.preconditions)}</td>
      <td>${cellList(r.steps)}</td>
      <td>${cellList(r.expected)}</td>
      <td>${cellText(r.viewpoint)}</td>
      <td>${DASH}</td>
    </tr>`).join('');
  }

  async function loadCases(domain) {
    if (!domain) {
      setBadge('');
      showMessage('ドメインを選択してください');
      return;
    }
    setBadge('');
    showMessage('読み込み中…');
    try {
      const res = await fetch('/api/testcases/table?domain=' + encodeURIComponent(domain));
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      const rows = data.rows || [];
      setBadge(rows.length + ' 件');
      renderRows(rows);
    } catch (e) {
      setBadge('');
      showMessage('テストケースの読み込みに失敗しました（' + (e && e.message ? e.message : e) + '）');
    }
  }

  async function loadDomains() {
    const sel = $('ta-design-domain');
    if (!sel) return;
    try {
      const res = await fetch('/api/history');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      const items = (data.items || []).filter((it) => it.domain);
      sel.innerHTML = '<option value="">ドメインを選択</option>'
        + items.map((it) => `<option value="${esc(it.domain)}">${esc(it.domain)}</option>`).join('');
      if (items.length) {
        sel.value = items[0].domain;
        loadCases(sel.value);
      } else {
        showMessage('ドキュメント作成の実行履歴がありません');
      }
    } catch (e) {
      showMessage('ドメイン一覧の取得に失敗しました（' + (e && e.message ? e.message : e) + '）');
    }
  }

  let _booted = false;
  function init() {
    if (_booted) return;
    _booted = true;
    const sel = $('ta-design-domain');
    if (sel) sel.addEventListener('change', () => loadCases(sel.value));
    const reload = $('ta-design-reload');
    if (reload) reload.addEventListener('click', () => loadCases(sel ? sel.value : ''));
    loadDomains();
  }

  // core.js の VIEW_INIT へ登録する（core.js は編集しない）。
  // このファイルは defer 読み込みのため、core.js のグローバルは定義済み。
  if (typeof onViewEnter === 'function') {
    onViewEnter('test-design', init);
  } else {
    document.addEventListener('DOMContentLoaded', init);
  }
})();
