// ---- 軽量 Markdown レンダラ（依存なし・XSS安全） ----
// 対応: 見出し(#〜######) / 太字・斜体 / インラインコード / コードブロック(```)
// / テーブル(|a|b|) / 箇条書き(-,*,数字.) / リンク([text](https://...)) / 段落
//
// 安全設計: まず全文を HTML エスケープしてから、エスケープ済みテキストに対して
// 自前で挿入するタグだけを正規表現で足していく（＝生成されるタグは全てこの
// 関数が書いたものだけであり、入力由来のタグは決して出現しない）。

function _mdEscape(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function _mdInline(escaped) {
  return escaped
    // インラインコード `code`
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    // 太字 **text**
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    // 斜体 *text*
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    // リンク [text](https://...) — http(s) スキームのみ許可
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
}

function renderMarkdownLite(source) {
  const lines = _mdEscape(source || '').split('\n');
  const html = [];
  let i = 0;
  let para = [];
  let list = null; // 'ul' | 'ol'
  let table = null; // { header: [...], rows: [...] }

  const flushPara = () => {
    if (para.length) {
      html.push('<p>' + _mdInline(para.join(' ')) + '</p>');
      para = [];
    }
  };
  const flushList = () => {
    if (list) {
      html.push('</' + list + '>');
      list = null;
    }
  };
  const flushTable = () => {
    if (table) {
      const thead = '<thead><tr>' + table.header.map(c => `<th>${_mdInline(c.trim())}</th>`).join('') + '</tr></thead>';
      const tbody = '<tbody>' + table.rows.map(r => '<tr>' + r.map(c => `<td>${_mdInline(c.trim())}</td>`).join('') + '</tr>').join('') + '</tbody>';
      html.push('<table class="md-table">' + thead + tbody + '</table>');
      table = null;
    }
  };

  while (i < lines.length) {
    const line = lines[i];

    // コードブロック ```
    if (/^```/.test(line.trim())) {
      flushPara(); flushList(); flushTable();
      const code = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i].trim())) {
        code.push(lines[i]);
        i++;
      }
      html.push('<pre class="md-code"><code>' + code.join('\n') + '</code></pre>');
      i++;
      continue;
    }

    // テーブル（ヘッダ行 + 区切り行 |---|---|）
    const tableMatch = line.match(/^\|(.+)\|\s*$/);
    const nextIsDivider = tableMatch && lines[i + 1] && /^\|[\s:|-]+\|\s*$/.test(lines[i + 1]);
    if (!table && tableMatch && nextIsDivider) {
      flushPara(); flushList();
      table = { header: tableMatch[1].split('|'), rows: [] };
      i += 2;
      continue;
    }
    if (table && tableMatch) {
      table.rows.push(tableMatch[1].split('|'));
      i++;
      continue;
    }
    if (table) flushTable();

    // 見出し
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      flushPara(); flushList();
      const level = heading[1].length;
      html.push(`<h${level} class="md-h${level}">` + _mdInline(heading[2]) + `</h${level}>`);
      i++;
      continue;
    }

    // 箇条書き
    const ulItem = line.match(/^\s*[-*]\s+(.*)$/);
    const olItem = line.match(/^\s*\d+\.\s+(.*)$/);
    if (ulItem || olItem) {
      flushPara();
      const kind = ulItem ? 'ul' : 'ol';
      if (list !== kind) { flushList(); html.push('<' + kind + '>'); list = kind; }
      html.push('<li>' + _mdInline((ulItem || olItem)[1]) + '</li>');
      i++;
      continue;
    }
    flushList();

    // 空行 = 段落区切り
    if (!line.trim()) {
      flushPara();
      i++;
      continue;
    }

    para.push(line.trim());
    i++;
  }
  flushPara(); flushList(); flushTable();
  return html.join('\n');
}
