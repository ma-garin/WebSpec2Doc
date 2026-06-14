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

