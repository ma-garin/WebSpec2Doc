// ---- テスト活動支援 / テスト設計ビュー ----
// 生成テストケースは System 01（ドキュメント作成）の生成結果を共用する。
// データ源: /api/history（ドメイン一覧）, /api/testcases/table?domain=...（ケース一覧）
(function () {
  'use strict';

  const esc = (v) => String(v == null ? '' : v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const $ = (id) => document.getElementById(id);

  function setBadge(text) {
    const el = $('ta-design-count');
    if (el) el.textContent = text;
  }

  // ケース表は System 01 のグリッドを共用マウントする（tcgMountGrid）。
  // 状態メッセージはマウント先ごと差し替える（グリッドと同居させない）。
  function showMessage(msg) {
    const host = $('ta-case-grid-host');
    if (host) host.innerHTML = `<div class="empty">${esc(msg)}</div>`;
  }

  // 分析ビューが保存した引き継ぎデータを読む。契約: キー ta.conditions.v1 /
  // 値 {"domain", "items": [{id,title,url,condition,category,priority,note}]}。
  // 壊れた JSON・形不一致はデータ無しとして扱う（例外を画面に出さない）。
  function readConditions() {
    let raw = null;
    try { raw = sessionStorage.getItem('ta.conditions.v1'); } catch (_) { return null; }
    if (!raw) return null;
    try {
      const data = JSON.parse(raw);
      if (!data || !Array.isArray(data.items) || !data.items.length) return null;
      return data;
    } catch (_) { return null; }
  }

  function renderConditions() {
    const list = $('ta-design-condition-list');
    if (!list) return;
    const data = readConditions();
    if (!data) {
      list.innerHTML = '<div class="empty">分析画面で「テスト条件を抽出」を実行すると、ここに引き継がれます</div>';
      return;
    }
    // 選択中ドメインと抽出元が異なっても一覧は出し、出所だけを明示する。
    const sel = $('ta-design-domain');
    const current = sel ? sel.value : '';
    const sourceNote = (current && data.domain && current !== data.domain)
      ? `<div class="muted-copy">抽出元: ${esc(data.domain)}</div>` : '';
    list.innerHTML = sourceNote + data.items.map((it) => `<div>
      <label><input type="checkbox" value="${esc(it.id)}"> ${esc(it.id)}: ${esc(it.condition)}</label>
      <div class="muted-copy">${esc(it.title)} ${esc(it.url)}</div>
    </div>`).join('');
  }

  // マウント済みかどうか。他画面がグリッドを作るとこの画面の DOM は破棄されるため、
  // 画面へ戻ったときに作り直すかの判定に使う。
  let _mounted = false;

  async function loadCases(domain) {
    const host = $('ta-case-grid-host');
    if (!host) return;
    _mounted = false;
    if (!domain) {
      setBadge('');
      showMessage('ドメインを選択してください');
      return;
    }
    if (typeof tcgMountGrid !== 'function') {
      setBadge('');
      showMessage('テストケース表を読み込めませんでした（グリッドが未ロードです）');
      return;
    }
    setBadge('');
    showMessage('読み込み中…');
    // 見出し帯は出さない（パネル見出し「生成テストケース」と重複するため）。
    // 実行ボタンも出さない（実行は実行画面の責務）。
    const count = await tcgMountGrid(host, domain, { title: '', setTabCount: false, showRun: false });
    if (count === null) {
      // 取得失敗時は tcgMountGrid が再試行つきのエラーを host 内に描画済み。
      setBadge('');
      return;
    }
    if (!count) {
      setBadge('');
      showMessage('このドメインには生成テストケースがありません');
      return;
    }
    _mounted = true;
    setBadge(count + ' 件');
  }

  async function loadDomains() {
    const sel = $('ta-design-domain');
    if (!sel) return;
    try {
      const res = await fetch('/api/history');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      // ケース表を組めるのは report.json（JSON 形式の成果物）を持つドメインだけ。
      // 絞らないと既定選択が未生成ドメインに当たり、開いた瞬間に 404 になる。
      const items = (data.items || []).filter(
        (it) => it.domain && Number(it.screens) > 0 && (it.formats || []).includes('JSON'),
      );
      const current = sel.value;
      sel.innerHTML = '<option value="">ドメインを選択</option>'
        + items.map((it) => `<option value="${esc(it.domain)}">${esc(it.domain)}</option>`).join('');
      if (items.length) {
        // 再取得のときは選択中のドメインを保つ（一覧を更新しただけで表が別サイトに飛ばない）
        sel.value = items.some((it) => it.domain === current) ? current : items[0].domain;
        loadCases(sel.value);
        renderConditions(); // ドメイン確定後に抽出元表記を正しくする
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
    if (sel) sel.addEventListener('change', () => { loadCases(sel.value); renderConditions(); });
    // 「読み込み直す」はドメイン一覧ごと取り直す。System 01 で新しく生成された
    // サイトは一覧に無いままになるため、ケース表だけの再取得では追いつかない。
    const reload = $('ta-design-reload');
    if (reload) reload.addEventListener('click', () => { loadDomains(); renderConditions(); });
    // すべて選択: 引き継ぎ条件のチェックボックスを一括で選択状態にする
    //（選択状態は後続工程で使う。この画面では選択までを提供する）。
    const selectAll = document.querySelector('#view-test-design [data-ta-action="design-condition-select-all"]');
    if (selectAll) selectAll.addEventListener('click', () => {
      const list = $('ta-design-condition-list');
      if (list) list.querySelectorAll('input[type="checkbox"]').forEach((cb) => { cb.checked = true; });
    });
    renderConditions();
    loadDomains();
  }

  // 画面へ入るたびに呼ばれる。初回は init（リスナー登録は 1 回だけ）。
  // 2 回目以降は、他画面のグリッド生成でこの画面のグリッドが破棄されている場合に限り
  // 作り直す。テスト条件の引き継ぎは分析画面で更新され得るため毎回描き直す。
  function onEnter() {
    if (!_booted) { init(); return; }
    // グリッドが無ければ作り直す。_mounted を条件にすると、取得失敗で残った
    // エラー表示が他画面のマウントで消えたときに空白のまま復帰できなくなる。
    const host = $('ta-case-grid-host');
    const sel = $('ta-design-domain');
    if (host && !host.querySelector('.tcg-wrap') && sel && sel.value) {
      loadCases(sel.value);
    }
    renderConditions();
  }

  // core.js の VIEW_INIT へ登録する（core.js は編集しない）。
  // このファイルは defer 読み込みのため、core.js のグローバルは定義済み。
  if (typeof onViewEnter === 'function') {
    onViewEnter('test-design', onEnter);
  } else {
    document.addEventListener('DOMContentLoaded', init);
  }
})();
