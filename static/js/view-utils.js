// クエリ重複を統合した正規化済み画面のみを返す。
// 旧 report.json（is_canonical 無し）は全画面を canonical 扱いにフォールバック。
function canonicalScreens(rj) {
  return (rj.screens || []).filter(sc => sc.is_canonical !== false);
}
function allFields(rj) {
  const rows = [];
  for (const sc of canonicalScreens(rj)) {
    for (const fm of (sc.forms || [])) {
      for (const fld of (fm.fields || [])) rows.push({ screen: sc.page_id, title: sc.title || '', field: fld });
    }
  }
  return rows;
}
function countRequired(rj) { return allFields(rj).filter(r => r.field.required).length; }
function constraintText(f) {
  const p = [];
  if (f.maxlength != null) p.push('最大' + f.maxlength + '文字');
  if (f.minlength != null) p.push('最小' + f.minlength + '文字');
  if (f.min_value) p.push('min=' + f.min_value);
  if (f.max_value) p.push('max=' + f.max_value);
  if (f.pattern) p.push('pattern=' + f.pattern);
  if (f.placeholder) p.push('例: ' + f.placeholder);
  return p.join(' / ');
}
function defaultOptionsText(f) {
  if (f.options && f.options.length) return f.options.filter(Boolean).join(', ').slice(0, 120);
  return f.default || '';
}

// Trace ID プレフィックスと QA 用語にホバーツールチップを付与する。
const TRACE_TERM_MAP = {
  'SCR': '画面（Screen）: クロールで検出した個々のページ。SCR-001 のように番号で識別します。',
  'FLD': '入力項目（Field）: フォーム内の個々の入力欄・選択肢。FLD-001 のように番号で識別します。',
  'TRN': '画面遷移（Transition）: リンクやボタン操作で画面が切り替わる経路。TRN-001 で識別します。',
  'BTN': '操作要素（Button）: ボタン・リンクなどのクリック可能な要素。BTN-001 で識別します。',
  'COND': 'テスト条件（Condition）: 境界値・同値分割などから機械導出したテスト観点。',
};

function wrapTraceTerms(containerEl) {
  if (!containerEl) return;
  containerEl.querySelectorAll('th').forEach(th => {
    if (th.textContent.trim() === 'Trace' && !th.querySelector('.term')) {
      th.innerHTML = '<span class="term" data-term="Trace ID: 画面(SCR)・項目(FLD)・遷移(TRN)・操作(BTN)・条件(COND)の識別子。テストケースと仕様の紐付けに使います。">Trace</span>';
    }
  });
  containerEl.querySelectorAll('td').forEach(td => {
    const text = td.textContent.trim();
    const match = text.match(/^(SCR|FLD|TRN|BTN|COND)-\d+$/);
    if (match && !td.querySelector('.term')) {
      const definition = TRACE_TERM_MAP[match[1]] || match[1];
      td.innerHTML = `<span class="term" data-term="${escHtml(definition)}">${escHtml(text)}</span>`;
    }
  });
  containerEl.querySelectorAll('.term').forEach(term => {
    const section = term.closest('.qa-readable-section');
    if (!section) return;
    term.addEventListener('mouseenter', () => { section.style.overflow = 'visible'; });
    term.addEventListener('mouseleave', () => { section.style.removeProperty('overflow'); });
  });
}
