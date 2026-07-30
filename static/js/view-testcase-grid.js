// ---- テストケース表: データ・フィルタ・描画 ----
// 編集・キーボード操作・履歴は testcase-grid-edit.js が担当する（状態は TCG を共有）。
//
// 設計方針:
//   - 視認性を最優先する。手順・期待結果は省略せず、番号付きで全文を表示する
//     （Excel 風の 1 行固定表示は、内容が読めなくなるため採用しない）
//   - ページングは持たない。行数の上限を設けず、スクロールで追加描画する
//   - 編集は表の見た目を保ったまま、セル内で行う

const TCG = {
  domain: '',
  columns: [],
  rows: [],          // サーバから受け取った全行（不変。編集時は差し替えで更新）
  view: [],          // フィルタ・ソート適用後の表示対象
  filters: {},       // { columnKey: string }
  query: '',
  sort: { key: '', dir: 0 },  // dir: 1=昇順 -1=降順 0=なし
  compact: false,    // true で 1 行省略表示（既定は全文表示）
  rendered: 0,       // 描画済み行数（追加描画の起点）
  sel: { row: 0, col: 1 },
  selected: new Set(),   // チェックした case_id（フィルタや再描画をまたいで保持）
  editing: false,
  undoStack: [],
  redoStack: [],
};

const TCG_CHUNK = 150;   // 一度に描画する行数
const TCG_COL_WIDTH = {
  case_id: 128, name: 230, screen: 124, function: 108, viewpoint: 150,
  preconditions: 300, steps: 400, expected: 340, automation: 96, result: 92,
};

function tcgColumn(key) { return TCG.columns.find(c => c.key === key) || {}; }
function tcgIsList(key) { return tcgColumn(key).kind === 'list'; }
function tcgIsEnum(key) { return tcgColumn(key).kind === 'enum'; }
function tcgCellText(row, key) {
  const v = row[key];
  return Array.isArray(v) ? v.join(' / ') : String(v ?? '');
}
function tcgCellRaw(row, key) {
  const v = row[key];
  return Array.isArray(v) ? v.join('\n') : String(v ?? '');
}

// ============================================================
// 読み込み
// ============================================================
async function renderResultTestcases() {
  const host = resultHero;
  TCG.domain = ((document.getElementById('r-domain') || {}).textContent || '').trim();
  host.innerHTML =
    '<div class="tcg-wrap">' +
      '<div class="tcg-head">' +
        '<div class="hero-section-title">テストケース</div>' +
        '<p class="design-section-note">テスト設計から生成したローレベルテストケースです。手順・期待結果は省略せず全文を表示します。セルをダブルクリック（または Enter）で編集でき、編集内容と履歴はサーバに保存されます。</p>' +
      '</div>' +
      '<div id="tcg-body"></div>' +
    '</div>';
  const body = document.getElementById('tcg-body');
  uiSkeleton(body, 'table');
  let data;
  try {
    const res = await fetch('/api/testcases/table?domain=' + encodeURIComponent(TCG.domain));
    data = await res.json();
    if (!res.ok) throw new Error(data.error || 'テストケースを取得できませんでした');
  } catch (e) {
    uiError(body, {
      title: 'テストケースの取得に失敗しました',
      message: e && e.message ? e.message : '通信エラー',
      onRetry: renderResultTestcases,
    });
    return;
  }
  TCG.columns = data.columns || [];
  TCG.rows = data.rows || [];
  TCG.commonPreconditions = data.common_preconditions || [];
  TCG.filters = {};
  TCG.query = '';
  TCG.sort = { key: '', dir: 0 };
  TCG.sel = { row: 0, col: 1 };
  TCG.undoStack = [];
  TCG.redoStack = [];
  _tcgSetTabCount(TCG.rows.length);
  _tcgBuildShell(body);
  tcgApplyFilters();
}

function _tcgSetTabCount(n) {
  const el = document.getElementById('tab-count-testcases');
  if (el) el.textContent = n > 0 ? ` ${n}` : '';
}

// ============================================================
// 外枠（ツールバー・ヘッダ・スクロール領域）
// ============================================================
function _tcgBuildShell(body) {
  const gridTemplate = '40px ' + TCG.columns.map(c => (TCG_COL_WIDTH[c.key] || 160) + 'px').join(' ');
  body.innerHTML =
    _tcgCommonPreconditionsHtml() +
    '<div class="tcg-cond-banner" id="tcg-cond-banner" role="status" hidden></div>' +
    '<div class="tcg-toolbar">' +
      '<div class="tc-search">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>' +
        '<input type="search" id="tcg-query" placeholder="全列を横断して検索" autocomplete="off" aria-label="テストケースを全列検索">' +
      '</div>' +
      '<button type="button" class="btn-outline-sm" id="tcg-clear-filters">フィルタ解除</button>' +
      '<button type="button" class="btn-outline-sm" id="tcg-compact">表示: 全文</button>' +
      '<span class="tcg-sep"></span>' +
      '<button type="button" class="btn-outline-sm" id="tcg-add-row">＋ 行を追加</button>' +
      '<button type="button" class="btn-outline-sm" id="tcg-del-row">− 行を削除</button>' +
      '<button type="button" class="btn-outline-sm" id="tcg-reset-cell">セルを生成値に戻す</button>' +
      '<button type="button" class="btn-outline-sm" id="tcg-history-btn">履歴</button>' +
      '<button type="button" class="btn-primary tcg-run-btn" id="tcg-run">▶ 実行</button>' +
      '<span class="tcg-count" id="tcg-count" aria-live="polite"></span>' +
    '</div>' +
    `<div class="tcg-grid" id="tcg-grid" style="--tcg-cols:${gridTemplate}">` +
      '<div class="tcg-scroll" id="tcg-scroll" tabindex="0">' +
        '<div class="tcg-headrow" id="tcg-headrow"></div>' +
        '<div class="tcg-filterrow" id="tcg-filterrow"></div>' +
        '<div class="tcg-rows" id="tcg-rows"></div>' +
      '</div>' +
    '</div>' +
    '<div class="tcg-status" id="tcg-status">セルを選択して Enter またはダブルクリックで編集／Esc で取消／Ctrl+Z で取り消し</div>' +
    '<div class="tcg-history" id="tcg-history" hidden></div>';

  _tcgBuildHeader();
  _tcgBindToolbar();
  tcgBindEditing();  // testcase-grid-edit.js
}

// 全ケース共通の前提条件は表の上に一度だけ出す（各行に複製すると表が読みづらくなる）
function _tcgCommonPreconditionsHtml() {
  const items = TCG.commonPreconditions || [];
  if (!items.length) return '';
  return '<div class="tcg-common"><strong>全ケース共通の前提</strong><ul>' +
    items.map(x => `<li>${escHtml(x)}</li>`).join('') +
    '</ul></div>';
}

function _tcgBuildHeader() {
  const head = document.getElementById('tcg-headrow');
  const filterRow = document.getElementById('tcg-filterrow');
  const checkTh = document.createElement('div');
  checkTh.className = 'tcg-th tcg-th-check';
  const allBox = document.createElement('input');
  allBox.type = 'checkbox';
  allBox.id = 'tcg-check-all';
  allBox.title = '表示中のすべてを選択 / 解除';
  allBox.setAttribute('aria-label', '表示中のすべてを選択');
  allBox.addEventListener('change', () => {
    if (allBox.checked) TCG.view.forEach(r => TCG.selected.add(r.case_id));
    else TCG.view.forEach(r => TCG.selected.delete(r.case_id));
    tcgRenderRows();
    tcgUpdateRunButton();
  });
  checkTh.appendChild(allBox);

  head.replaceChildren(checkTh, ...TCG.columns.map(c => {
    const cell = document.createElement('button');
    cell.type = 'button';
    cell.className = 'tcg-th';
    cell.dataset.key = c.key;
    cell.textContent = c.label;
    const arrow = document.createElement('span');
    arrow.className = 'tcg-sort';
    cell.appendChild(arrow);
    cell.addEventListener('click', () => _tcgToggleSort(c.key));
    return cell;
  }));

  const checkFilter = document.createElement('div');
  checkFilter.className = 'tcg-filter-cell';
  filterRow.replaceChildren(checkFilter, ...TCG.columns.map(c => {
    const wrap = document.createElement('div');
    wrap.className = 'tcg-filter-cell';
    if (tcgIsEnum(c.key)) {
      const sel = document.createElement('select');
      sel.dataset.key = c.key;
      sel.className = 'tcg-filter-select';
      sel.appendChild(new Option('すべて', ''));
      for (const v of _tcgDistinct(c.key)) sel.appendChild(new Option(v, v));
      sel.addEventListener('change', () => {
        TCG.filters[c.key] = sel.value;
        _tcgHideConditionBanner();  // 利用者が自分で絞り始めたら、条件由来の帯は外す
        tcgApplyFilters();
      });
      wrap.appendChild(sel);
    } else {
      const input = document.createElement('input');
      input.type = 'search';
      input.dataset.key = c.key;
      input.className = 'tcg-filter-input';
      input.placeholder = '絞り込み';
      input.addEventListener('input', () => {
        TCG.filters[c.key] = input.value;
        _tcgHideConditionBanner();
        tcgApplyFilters();
      });
      wrap.appendChild(input);
    }
    return wrap;
  }));
  _tcgPaintSortArrows();
}

// 選択肢の候補。「境界値分析／上限超過」のような階層値は、上位（境界値分析）でも
// 絞り込めるように前半だけの候補も足す。照合は前方一致。
function _tcgDistinct(key) {
  const values = new Set();
  for (const row of TCG.rows) {
    const text = tcgCellText(row, key);
    if (!text) continue;
    values.add(text);
    if (text.includes('／')) values.add(text.split('／')[0]);
  }
  return [...values].sort();
}

// 画面別設計の条件行から飛んできたときの絞り込み（P2-4）。
// 条件とテストケースは独立に生成されており、両者を結ぶ安定 ID がまだ無い。
// そのため「画面＋由来した要素」で絞る。厳密な対応ではないため、
// 何で絞っているかを帯に明示し、断定しない書き方にする。
function tcgFilterFromCondition({ pageId = '', screenLabel = '', source = '' } = {}) {
  TCG.filters = {};
  TCG.query = source || '';
  const q = document.getElementById('tcg-query');
  if (q) q.value = TCG.query;
  document.querySelectorAll('.tcg-filter-input').forEach(i => { i.value = ''; });
  document.querySelectorAll('.tcg-filter-select').forEach(s => { s.value = ''; });

  // 画面の選択肢は「P001 タイトル」の形。絞り込みだけ効かせて選択肢を空のままにすると
  // 絞られているのに「すべて」と見えるため、対応する選択肢自体を選ぶ。
  const sel = document.querySelector('.tcg-filter-select[data-key="screen"]');
  if (pageId && sel) {
    const opt = [...sel.options].find(o => o.value && o.value.startsWith(pageId));
    if (opt) { sel.value = opt.value; TCG.filters.screen = opt.value; }
    else TCG.filters.screen = pageId;
  } else if (pageId) {
    TCG.filters.screen = pageId;
  }
  tcgApplyFilters();
  _tcgShowConditionBanner({ screenLabel: screenLabel || pageId, source });
}

function _tcgShowConditionBanner({ screenLabel = '', source = '' } = {}) {
  const host = document.getElementById('tcg-cond-banner');
  if (!host) return;
  const shown = TCG.view.length;
  const total = TCG.rows.length;
  host.innerHTML =
    '<span class="tcg-cond-tag">絞り込み中</span>' +
    `<span class="tcg-cond-key">画面: ${escHtml(screenLabel || '—')}</span>` +
    (source ? `<span class="tcg-cond-key">由来: ${escHtml(source)}</span>` : '') +
    `<span class="tcg-cond-count">該当 ${shown} 件 / 全 ${total} 件</span>` +
    // 対応が厳密でないことを黙っていると、出た件数を「これが全て」と読まれる
    '<span class="tcg-cond-note">由来が一致するケースを表示しています</span>' +
    '<button type="button" class="btn-outline-sm" id="tcg-cond-clear">絞り込みを解除</button>';
  host.hidden = false;
  document.getElementById('tcg-cond-clear').addEventListener('click', () => {
    document.getElementById('tcg-clear-filters').click();
  });
}

function _tcgHideConditionBanner() {
  const host = document.getElementById('tcg-cond-banner');
  if (!host) return;
  host.hidden = true;
  host.innerHTML = '';
}

function _tcgBindToolbar() {
  document.getElementById('tcg-query').addEventListener('input', (e) => {
    TCG.query = e.target.value;
    _tcgHideConditionBanner();
    tcgApplyFilters();
  });
  document.getElementById('tcg-clear-filters').addEventListener('click', () => {
    TCG.filters = {};
    TCG.query = '';
    document.getElementById('tcg-query').value = '';
    document.querySelectorAll('.tcg-filter-input').forEach(i => { i.value = ''; });
    document.querySelectorAll('.tcg-filter-select').forEach(s => { s.value = ''; });
    _tcgHideConditionBanner();
    tcgApplyFilters();
  });
  const compactBtn = document.getElementById('tcg-compact');
  compactBtn.addEventListener('click', () => {
    TCG.compact = !TCG.compact;
    compactBtn.textContent = '表示: ' + (TCG.compact ? '1行' : '全文');
    document.getElementById('tcg-grid').classList.toggle('is-compact', TCG.compact);
  });
}

// ============================================================
// フィルタ・ソート
// ============================================================
function tcgApplyFilters() {
  const q = TCG.query.trim().toLowerCase();
  const active = Object.entries(TCG.filters).filter(([, v]) => v);
  TCG.view = TCG.rows.filter(row => {
    for (const [key, needle] of active) {
      const hay = tcgCellText(row, key).toLowerCase();
      if (tcgIsEnum(key)) { if (!hay.startsWith(String(needle).toLowerCase())) return false; }
      else if (!hay.includes(String(needle).toLowerCase())) return false;
    }
    if (!q) return true;
    return TCG.columns.some(c => tcgCellText(row, c.key).toLowerCase().includes(q));
  });
  if (TCG.sort.dir !== 0 && TCG.sort.key) {
    const { key, dir } = TCG.sort;
    TCG.view = [...TCG.view].sort((a, b) =>
      tcgCellText(a, key).localeCompare(tcgCellText(b, key), 'ja') * dir);
  }
  if (TCG.sel.row >= TCG.view.length) TCG.sel.row = Math.max(0, TCG.view.length - 1);
  _tcgUpdateCount();
  tcgRenderRows();
}

function _tcgToggleSort(key) {
  if (TCG.sort.key !== key) TCG.sort = { key, dir: 1 };
  else TCG.sort = { key, dir: TCG.sort.dir === 1 ? -1 : (TCG.sort.dir === -1 ? 0 : 1) };
  _tcgPaintSortArrows();
  tcgApplyFilters();
}

function _tcgPaintSortArrows() {
  document.querySelectorAll('#tcg-headrow .tcg-th').forEach(th => {
    const arrow = th.querySelector('.tcg-sort');
    if (!arrow) return;
    arrow.textContent = (th.dataset.key === TCG.sort.key && TCG.sort.dir !== 0)
      ? (TCG.sort.dir === 1 ? '▲' : '▼') : '';
  });
}

function _tcgUpdateCount() {
  const el = document.getElementById('tcg-count');
  if (!el) return;
  const edited = TCG.rows.filter(r => (r.edited_columns || []).length).length;
  el.textContent = `${TCG.view.length}件表示 / 全${TCG.rows.length}件` +
    (TCG.selected.size ? ` ・ 選択 ${TCG.selected.size}件` : '') +
    (edited ? ` ・ 編集済み ${edited}行` : '');
  tcgUpdateRunButton();
}

// ============================================================
// 描画（全件・スクロールで追加描画）
// ============================================================
function tcgRenderRows() {
  const rowsEl = document.getElementById('tcg-rows');
  if (!rowsEl) return;
  rowsEl.replaceChildren();
  TCG.rendered = 0;
  if (!TCG.view.length) {
    const empty = document.createElement('div');
    empty.className = 'tcg-empty';
    empty.textContent = '条件に一致するテストケースがありません。';
    rowsEl.appendChild(empty);
    return;
  }
  _tcgAppendChunk();
  _tcgPaintSelection();
}

// スクロールが下端に近づいたら次のかたまりを足す（行数に上限を設けないため）
function _tcgAppendChunk() {
  const rowsEl = document.getElementById('tcg-rows');
  if (!rowsEl || TCG.rendered >= TCG.view.length) return;
  const end = Math.min(TCG.view.length, TCG.rendered + TCG_CHUNK);
  const frag = document.createDocumentFragment();
  for (let i = TCG.rendered; i < end; i++) frag.appendChild(_tcgRowEl(TCG.view[i], i));
  rowsEl.appendChild(frag);
  TCG.rendered = end;
}

function tcgMaybeAppendChunk() {
  const scroll = document.getElementById('tcg-scroll');
  if (!scroll || TCG.rendered >= TCG.view.length) return;
  if (scroll.scrollTop + scroll.clientHeight >= scroll.scrollHeight - 400) {
    _tcgAppendChunk();
    _tcgPaintSelection();
  }
}

function _tcgRowEl(row, index) {
  const el = document.createElement('div');
  el.className = 'tcg-tr' + (row.origin === 'manual' ? ' is-manual' : '');
  el.dataset.index = String(index);
  el.appendChild(_tcgCheckCell(row));
  TCG.columns.forEach((c, ci) => el.appendChild(_tcgCellEl(row, c, ci)));
  return el;
}

// 実行対象を選ぶチェックボックス。自動化できない行は選べない（実行に含められない）。
function _tcgCheckCell(row) {
  const cell = document.createElement('div');
  cell.className = 'tcg-td tcg-td-check';
  const box = document.createElement('input');
  box.type = 'checkbox';
  box.className = 'tcg-row-check';
  box.dataset.caseId = row.case_id;
  box.checked = TCG.selected.has(row.case_id);
  box.disabled = row.automation !== '自動化可';
  box.title = box.disabled ? 'このケースは自動実行できません（要目視）' : row.case_id + ' を実行対象にする';
  box.setAttribute('aria-label', row.case_id + ' を実行対象にする');
  cell.appendChild(box);
  return cell;
}

function _tcgCellEl(row, col, ci) {
  const cell = document.createElement('div');
  cell.className = 'tcg-td';
  if (!col.editable) cell.classList.add('is-readonly');
  if ((row.edited_columns || []).includes(col.key)) cell.classList.add('is-edited');
  if (col.key === 'automation') {
    cell.classList.add(row.automation === '要目視' ? 'is-manual-check' : 'is-auto');
  }
  if (col.key === 'result') {
    const label = String(row.result || '');
    if (label === 'PASS') cell.classList.add('is-pass');
    else if (label && label !== '—') cell.classList.add('is-fail');
    if (row.result_error) cell.title = row.result_error;
  }
  cell.dataset.key = col.key;
  cell.dataset.col = String(ci);
  _tcgFillCell(cell, row, col);
  return cell;
}

// 複数項目の列は番号付きリストで出す（1 行に潰すと手順が読めなくなる）
function _tcgFillCell(cell, row, col) {
  const value = row[col.key];
  if (Array.isArray(value)) {
    if (!value.length) { cell.textContent = '—'; return; }
    const ol = document.createElement('ol');
    ol.className = 'tcg-cell-list';
    for (const item of value) {
      const li = document.createElement('li');
      li.textContent = item;
      ol.appendChild(li);
    }
    cell.replaceChildren(ol);
    return;
  }
  cell.textContent = String(value ?? '');
}

// ============================================================
// 選択の描画（行を作り直さずクラスだけ差し替える）
// ============================================================
function tcgRowEl(index) {
  return document.querySelector(`#tcg-rows .tcg-tr[data-index="${index}"]`);
}
function tcgCellElAt(index, col) {
  const row = tcgRowEl(index);
  return row ? row.querySelector(`.tcg-td[data-col="${col}"]`) : null;
}

function _tcgPaintSelection() {
  document.querySelectorAll('#tcg-rows .is-selected').forEach(e => e.classList.remove('is-selected'));
  document.querySelectorAll('#tcg-rows .is-selrow').forEach(e => e.classList.remove('is-selrow'));
  const cell = tcgCellElAt(TCG.sel.row, TCG.sel.col);
  if (!cell) return;
  cell.classList.add('is-selected');
  const row = cell.closest('.tcg-tr');
  if (row) row.classList.add('is-selrow');
}

function tcgSelectedRow() { return TCG.view[TCG.sel.row] || null; }
function tcgSelectedKey() { return (TCG.columns[TCG.sel.col] || {}).key || ''; }

// 実行ボタンは「何を実行するか」をラベルに出す（選択があれば選択、無ければ表示中）
function tcgUpdateRunButton() {
  const btn = document.getElementById('tcg-run');
  if (!btn) return;
  const n = tcgRunTargets().length;
  btn.textContent = TCG.selected.size
    ? `▶ 選択した ${n} 件を実行`
    : `▶ 表示中の ${n} 件を実行`;
  btn.disabled = n === 0;
}

// 実行対象: 選択があればその行、無ければ表示中の行。いずれも「自動化可」に限る。
function tcgRunTargets() {
  const base = TCG.selected.size
    ? TCG.rows.filter(r => TCG.selected.has(r.case_id))
    : TCG.view;
  return base.filter(r => r.automation === '自動化可');
}

function tcgSetStatus(message, isError) {
  const el = document.getElementById('tcg-status');
  if (!el) return;
  el.textContent = message || '';
  el.classList.toggle('is-error', !!isError);
}
