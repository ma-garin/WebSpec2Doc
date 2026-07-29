// ---- テストケース表: 編集・キーボード操作・履歴 ----
// 表示側（view-testcase-grid.js）と状態 TCG を共有する。
//
// キー操作:
//   矢印/Tab      セル移動
//   Enter / F2 / ダブルクリック   セル編集（複数項目の列は改行で項目を分ける）
//   Esc           編集の取消      Delete   セルを空にする
//   Ctrl+C / Ctrl+V  コピー・貼り付け（タブ区切りで複数セル）
//   Ctrl+Z / Ctrl+Shift+Z  取り消し・やり直し

const TCG_MAX_PASTE_CELLS = 500;

function tcgBindEditing() {
  const scroll = document.getElementById('tcg-scroll');
  if (!scroll) return;

  scroll.addEventListener('scroll', () => tcgMaybeAppendChunk());
  scroll.addEventListener('click', _tcgOnClick);
  scroll.addEventListener('dblclick', (e) => {
    _tcgOnClick(e);
    tcgStartInlineEdit('');
  });
  scroll.addEventListener('keydown', _tcgOnKeyDown);
  scroll.addEventListener('paste', _tcgOnPaste);
  scroll.addEventListener('copy', _tcgOnCopy);

  document.getElementById('tcg-add-row').addEventListener('click', tcgAddRow);
  document.getElementById('tcg-del-row').addEventListener('click', tcgDeleteRow);
  document.getElementById('tcg-reset-cell').addEventListener('click', tcgResetCell);
  document.getElementById('tcg-history-btn').addEventListener('click', tcgToggleHistory);
  document.getElementById('tcg-run').addEventListener('click', tcgRunCases);
}

// ============================================================
// 選択
// ============================================================
function _tcgOnClick(e) {
  if (TCG.editing) return;
  if (e.target.classList && e.target.classList.contains('tcg-row-check')) {
    const id = e.target.dataset.caseId;
    if (e.target.checked) TCG.selected.add(id); else TCG.selected.delete(id);
    _tcgUpdateCount();
    return;
  }
  const cell = e.target.closest('.tcg-td');
  const rowEl = e.target.closest('.tcg-tr');
  if (!cell || !rowEl || cell.dataset.col === undefined) return;
  TCG.sel = { row: Number(rowEl.dataset.index), col: Number(cell.dataset.col) };
  _tcgPaintSelection();
  document.getElementById('tcg-scroll').focus();
}

function _tcgMove(dRow, dCol) {
  const maxRow = TCG.view.length - 1;
  const maxCol = TCG.columns.length - 1;
  const nextRow = Math.min(maxRow, Math.max(0, TCG.sel.row + dRow));
  // 未描画の行へ移動する場合は先に描画する（行数無制限＋追加描画のため）
  while (nextRow >= TCG.rendered && TCG.rendered < TCG.view.length) tcgMaybeAppendChunkForce();
  TCG.sel.row = nextRow;
  TCG.sel.col = Math.min(maxCol, Math.max(0, TCG.sel.col + dCol));
  _tcgPaintSelection();
  const cell = tcgCellElAt(TCG.sel.row, TCG.sel.col);
  if (cell) cell.scrollIntoView({ block: 'nearest', inline: 'nearest' });
}

// _tcgAppendChunk は表示側の内部関数。移動時は下端判定を待たずに足す。
function tcgMaybeAppendChunkForce() {
  const before = TCG.rendered;
  const rowsEl = document.getElementById('tcg-rows');
  if (!rowsEl) return;
  const end = Math.min(TCG.view.length, TCG.rendered + 150);
  const frag = document.createDocumentFragment();
  for (let i = TCG.rendered; i < end; i++) frag.appendChild(_tcgRowEl(TCG.view[i], i));
  rowsEl.appendChild(frag);
  TCG.rendered = end;
  if (TCG.rendered === before) TCG.rendered = TCG.view.length;  // 無限ループ防止
}

// ============================================================
// キー操作
// ============================================================
function _tcgOnKeyDown(e) {
  if (TCG.editing) return;
  const ctrl = e.ctrlKey || e.metaKey;

  if (ctrl && e.key.toLowerCase() === 'z') {
    e.preventDefault();
    return e.shiftKey ? tcgRedo() : tcgUndo();
  }
  if (ctrl && e.key.toLowerCase() === 'y') { e.preventDefault(); return tcgRedo(); }
  if (ctrl) return;  // Ctrl+C/V はブラウザの copy/paste イベントで処理する

  switch (e.key) {
    case 'ArrowDown':  e.preventDefault(); return _tcgMove(1, 0);
    case 'ArrowUp':    e.preventDefault(); return _tcgMove(-1, 0);
    case 'ArrowRight': e.preventDefault(); return _tcgMove(0, 1);
    case 'ArrowLeft':  e.preventDefault(); return _tcgMove(0, -1);
    case 'Tab':        e.preventDefault(); return _tcgMove(0, e.shiftKey ? -1 : 1);
    case 'Enter':
    case 'F2':         e.preventDefault(); return tcgStartInlineEdit('');
    case 'Home':       e.preventDefault(); TCG.sel.col = 0; return _tcgMove(0, 0);
    case 'End':        e.preventDefault(); TCG.sel.col = TCG.columns.length - 1; return _tcgMove(0, 0);
    case 'PageDown':   e.preventDefault(); return _tcgMove(10, 0);
    case 'PageUp':     e.preventDefault(); return _tcgMove(-10, 0);
    case 'Delete':
    case 'Backspace':  e.preventDefault(); return tcgCommit('');
    default: break;
  }
  if (e.key.length === 1 && !e.altKey) {
    e.preventDefault();
    tcgStartInlineEdit(e.key);
  }
}

// ============================================================
// セル内編集（全文表示のままセル内で編集する）
// ============================================================
function tcgStartInlineEdit(initial) {
  const col = TCG.columns[TCG.sel.col] || {};
  const row = tcgSelectedRow();
  if (!row || !col.editable || TCG.editing) return;
  const cell = tcgCellElAt(TCG.sel.row, TCG.sel.col);
  if (!cell) return;

  TCG.editing = true;
  const isList = col.kind === 'list';
  const editor = document.createElement('textarea');
  editor.className = 'tcg-cell-editor' + (isList ? ' is-list' : '');
  editor.value = initial !== '' ? initial : tcgCellRaw(row, col.key);
  editor.rows = isList ? Math.max(3, editor.value.split('\n').length) : 1;
  editor.spellcheck = false;
  editor.setAttribute('aria-label', `${row.case_id} の${col.label}を編集`);
  const restore = () => _tcgFillCell(cell, row, col);
  cell.replaceChildren(editor);
  editor.focus();
  if (initial === '') editor.setSelectionRange(editor.value.length, editor.value.length);

  const finish = (commit) => {
    if (!TCG.editing) return;
    TCG.editing = false;
    const value = editor.value;
    restore();
    document.getElementById('tcg-scroll').focus();
    if (commit) tcgCommit(value);
  };
  editor.addEventListener('keydown', (ev) => {
    ev.stopPropagation();
    // 複数項目の列は改行で項目を分けるため、確定は Ctrl+Enter に割り当てる
    const commitKey = isList ? (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) : ev.key === 'Enter';
    if (commitKey) { ev.preventDefault(); finish(true); _tcgMove(1, 0); }
    else if (ev.key === 'Escape') { ev.preventDefault(); finish(false); }
    else if (ev.key === 'Tab') { ev.preventDefault(); finish(true); _tcgMove(0, ev.shiftKey ? -1 : 1); }
  });
  editor.addEventListener('blur', () => finish(true));
  tcgSetStatus(isList
    ? '改行で項目を分けます。Ctrl+Enter で確定 / Esc で取消'
    : 'Enter で確定 / Esc で取消');
}

// ============================================================
// 保存
// ============================================================
async function tcgSaveCell(caseId, column, value) {
  const res = await fetch('/api/testcases/cell', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ domain: TCG.domain, case_id: caseId, column, value }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || '保存に失敗しました');
  return data;
}

function _tcgReplaceRow(updated) {
  TCG.rows = TCG.rows.map(r => (r.case_id === updated.case_id ? updated : r));
  const index = TCG.view.findIndex(r => r.case_id === updated.case_id);
  if (index >= 0) TCG.view[index] = updated;
  // 該当行だけ描き替える（全体を再構築すると編集位置とスクロールが飛ぶ）
  const rowEl = tcgRowEl(index);
  if (rowEl) rowEl.replaceWith(_tcgRowEl(updated, index));
  _tcgPaintSelection();
  _tcgUpdateCount();
}

async function tcgCommit(value, opts = {}) {
  const row = tcgSelectedRow();
  const col = TCG.columns[TCG.sel.col] || {};
  if (!row || !col.editable) return;
  const before = tcgCellRaw(row, col.key);
  if (before === value) return;
  tcgSetStatus('保存中…');
  try {
    const data = await tcgSaveCell(row.case_id, col.key, value);
    if (data.row) _tcgReplaceRow(data.row);
    if (!opts.silent) {
      TCG.undoStack.push({ caseId: row.case_id, column: col.key, before, after: value });
      TCG.redoStack = [];
    }
    tcgSetStatus(`保存しました（${row.case_id} / ${col.label || col.key}）`);
  } catch (e) {
    tcgSetStatus(e.message, true);
  }
}

// ============================================================
// 取り消し・やり直し
// ============================================================
async function _tcgApplyDirect(entry, value) {
  tcgSetStatus('反映中…');
  try {
    const data = await tcgSaveCell(entry.caseId, entry.column, value);
    if (data.row) _tcgReplaceRow(data.row);
    tcgSetStatus(`反映しました（${entry.caseId} / ${entry.column}）`);
  } catch (e) {
    tcgSetStatus(e.message, true);
  }
}

async function tcgUndo() {
  const entry = TCG.undoStack.pop();
  if (!entry) { tcgSetStatus('取り消せる操作がありません'); return; }
  await _tcgApplyDirect(entry, entry.before);
  TCG.redoStack.push(entry);
}

async function tcgRedo() {
  const entry = TCG.redoStack.pop();
  if (!entry) { tcgSetStatus('やり直せる操作がありません'); return; }
  await _tcgApplyDirect(entry, entry.after);
  TCG.undoStack.push(entry);
}

// ============================================================
// コピー・貼り付け
// ============================================================
function _tcgOnCopy(e) {
  const row = tcgSelectedRow();
  if (!row || TCG.editing) return;
  e.clipboardData.setData('text/plain', tcgCellRaw(row, tcgSelectedKey()));
  e.preventDefault();
  tcgSetStatus('セルをコピーしました');
}

async function _tcgOnPaste(e) {
  if (TCG.editing) return;
  const text = (e.clipboardData || {}).getData ? e.clipboardData.getData('text/plain') : '';
  if (!text) return;
  e.preventDefault();
  const matrix = text.replace(/\r/g, '').split('\n')
    .filter((l, i, a) => !(i === a.length - 1 && l === ''))
    .map(line => line.split('\t'));
  const targets = [];
  matrix.forEach((cells, dr) => {
    cells.forEach((value, dc) => {
      const row = TCG.view[TCG.sel.row + dr];
      const col = TCG.columns[TCG.sel.col + dc];
      if (!row || !col || !col.editable) return;
      targets.push({ row, col, value });
    });
  });
  if (!targets.length) { tcgSetStatus('貼り付け先が編集できない列です', true); return; }
  if (targets.length > TCG_MAX_PASTE_CELLS) {
    tcgSetStatus(`貼り付けは一度に${TCG_MAX_PASTE_CELLS}セルまでです（${targets.length}セル指定）`, true);
    return;
  }
  tcgSetStatus(`${targets.length}セルを貼り付けています…`);
  let ok = 0;
  for (const t of targets) {
    try {
      const data = await tcgSaveCell(t.row.case_id, t.col.key, t.value);
      TCG.undoStack.push({
        caseId: t.row.case_id, column: t.col.key,
        before: tcgCellRaw(t.row, t.col.key), after: t.value,
      });
      if (data.row) _tcgReplaceRow(data.row);
      ok++;
    } catch (err) { /* 個別失敗は件数に反映する */ }
  }
  TCG.redoStack = [];
  tcgSetStatus(`${ok}/${targets.length}セルを貼り付けました`, ok !== targets.length);
}

// ============================================================
// 行操作・セルの復元
// ============================================================
async function _tcgRowAction(action, caseId) {
  const res = await fetch('/api/testcases/row', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ domain: TCG.domain, action, case_id: caseId || '' }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || '操作に失敗しました');
  return data;
}

async function _tcgReload(message) {
  const res = await fetch('/api/testcases/table?domain=' + encodeURIComponent(TCG.domain));
  const data = await res.json();
  if (res.ok) {
    TCG.rows = data.rows || [];
    _tcgSetTabCount(TCG.rows.length);
    tcgApplyFilters();
  }
  tcgSetStatus(message);
}

async function tcgAddRow() {
  try {
    const data = await _tcgRowAction('add', '');
    await _tcgReload(`行を追加しました（${data.row.case_id}）`);
  } catch (e) { tcgSetStatus(e.message, true); }
}

async function tcgDeleteRow() {
  const row = tcgSelectedRow();
  if (!row) return;
  const okDelete = await confirmDialog({
    title: 'テストケースを削除',
    message: `${row.case_id} を削除します。履歴に残り、生成された行は復元できます。`,
    confirmLabel: '削除する',
    danger: true,
  });
  if (!okDelete) return;
  try {
    await _tcgRowAction('delete', row.case_id);
    await _tcgReload(`${row.case_id} を削除しました`);
  } catch (e) { tcgSetStatus(e.message, true); }
}

async function tcgResetCell() {
  const row = tcgSelectedRow();
  const col = TCG.columns[TCG.sel.col] || {};
  if (!row || !col.editable) return;
  try {
    const res = await fetch('/api/testcases/cell/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ domain: TCG.domain, case_id: row.case_id, column: col.key }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '復元に失敗しました');
    if (data.row) _tcgReplaceRow(data.row);
    tcgSetStatus(`生成値に戻しました（${row.case_id} / ${col.label}）`);
  } catch (e) { tcgSetStatus(e.message, true); }
}

// ============================================================
// 実行（表の内容から Playwright コードを生成して実行する）
// ============================================================
async function tcgRunCases() {
  const btn = document.getElementById('tcg-run');
  const targets = tcgRunTargets();
  if (!targets.length) {
    tcgSetStatus('実行できるケースがありません（「自動化可」の行を選択、またはフィルタを見直してください）', true);
    return;
  }
  const scope = TCG.selected.size ? '選択した' : '表示中の';
  const ok = await confirmDialog({
    title: 'テストケースを実行',
    message: `${scope} ${targets.length} 件を実行します。対象サイトへ実際にアクセスします。`,
    confirmLabel: '実行する',
  });
  if (!ok) return;
  btn.disabled = true;
  const started = Date.now();
  const tick = setInterval(() => {
    tcgSetStatus(`実行中… ${targets.length}件 / 経過 ${Math.round((Date.now() - started) / 1000)}秒`);
  }, 1000);
  try {
    const res = await fetch('/api/testcases/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ domain: TCG.domain, case_ids: targets.map(r => r.case_id) }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '実行に失敗しました');
    const s = (data.run && data.run.summary) || {};
    await _tcgReload(
      `実行完了: PASS ${s.passed || 0} / FAIL ${s.failed || 0} / 全${s.total || 0}件` +
      (s.error ? ` — ${s.error}` : ''));
    // 「テスト実行」タブと概要の実績も同時に更新する。
    // これが無いと、実行して結果が保存されたのにレポートを開き直すまで
    // 「まだ実行していません」と表示され続けた。
    if (typeof refreshRunResults === 'function') await refreshRunResults();
  } catch (e) {
    tcgSetStatus(e.message, true);
  } finally {
    clearInterval(tick);
    btn.disabled = false;
  }
}

// ============================================================
// 履歴
// ============================================================
async function tcgToggleHistory() {
  const panel = document.getElementById('tcg-history');
  if (!panel) return;
  if (!panel.hidden) { panel.hidden = true; return; }
  panel.hidden = false;
  panel.textContent = '読み込み中…';
  try {
    const res = await fetch('/api/testcases/history?domain=' + encodeURIComponent(TCG.domain));
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '履歴を取得できませんでした');
    const items = data.items || [];
    if (!items.length) { panel.textContent = '編集履歴はまだありません。'; return; }
    panel.replaceChildren(_tcgHistoryTable(items));
  } catch (e) {
    panel.textContent = e.message;
  }
}

const _TCG_ACTION_LABEL = {
  edit: '編集', reset: '生成値に戻す', add: '行追加', delete: '行削除', restore: '行復元',
};

function _tcgHistoryTable(items) {
  const table = document.createElement('table');
  table.className = 'ov-screens tcg-history-table';
  const head = document.createElement('thead');
  const headRow = document.createElement('tr');
  for (const label of ['時刻', '操作', 'ID', '列', '変更前', '変更後']) {
    const th = document.createElement('th');
    th.textContent = label;
    headRow.appendChild(th);
  }
  head.appendChild(headRow);
  const body = document.createElement('tbody');
  const colLabel = (key) => (TCG.columns.find(c => c.key === key) || {}).label || key || '—';
  const text = (v) => (Array.isArray(v) ? v.join(' / ') : (v === null || v === undefined ? '—' : String(v)));
  for (const it of items) {
    const tr = document.createElement('tr');
    for (const value of [
      String(it.ts || '').replace('T', ' '),
      _TCG_ACTION_LABEL[it.action] || it.action || '',
      it.case_id || '',
      colLabel(it.column),
      text(it.before),
      text(it.after),
    ]) {
      const td = document.createElement('td');
      td.textContent = value;
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }
  table.appendChild(head);
  table.appendChild(body);
  return table;
}
