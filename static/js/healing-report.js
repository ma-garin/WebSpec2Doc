'use strict';

/* オートヒーリング設定画面（templates/healing.html）: 報告の整形: Markdown・表・差分の描画（textContent のみで組み立てる）
   読み込み順: healing-core.js → healing-projects.js → healing-report.js → healing-run.js → healing-actions.js → healing-history.js → healing.js。
   ファイル間の共有は window.HealingApp（HL）だけ。他ファイルの関数は呼び出し時に HL から引く。 */
(function (HL) {
  /* ---- 他ファイルの宣言 ---- */
  var AGENT_DISPLAY_NAMES = HL.AGENT_DISPLAY_NAMES;
  var SEVERITY_LABELS = HL.SEVERITY_LABELS;
  function agentDisplayName() { return HL.agentDisplayName.apply(this, arguments); }
  function el() { return HL.el.apply(this, arguments); }
  function renderEvidence() { return HL.renderEvidence.apply(this, arguments); }


  /* ---------------- 最小の Markdown 変換（見出し・表・箇条書き・コードフェンスのみ） ----------------
     ライブラリも CDN も足さない。innerHTML を一切使わず DOM を組み立てるため、
     レポート本文がマークアップとして解釈されることはない（XSS 防止）。 */

  function appendInline(parent, text) {
    var rest = String(text == null ? '' : text);
    var re = /(`[^`]+`|\*\*[^*]+\*\*)/;
    while (rest) {
      var m = re.exec(rest);
      if (!m) { parent.appendChild(document.createTextNode(rest)); break; }
      if (m.index > 0) { parent.appendChild(document.createTextNode(rest.slice(0, m.index))); }
      var token = m[0];
      if (token.charAt(0) === '`') {
        parent.appendChild(el('code', 'hl-report-inline-code', token.slice(1, -1)));
      } else {
        parent.appendChild(el('b', null, token.slice(2, -2)));
      }
      rest = rest.slice(m.index + token.length);
    }
  }

  function isTableDivider(line) {
    return /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/.test(line);
  }

  // 行頭・行末の `|` は表の枠であってセルではない。枠由来の空要素を落とさないと
  // 「3 列のはずが 4 列目に空列が出る」形で列数が壊れる。
  function splitTableRow(line) {
    var text = line.trim();
    var cells = text.split('|');
    if (cells.length > 1 && text.charAt(0) === '|') { cells.shift(); }
    if (cells.length > 1 && text.charAt(text.length - 1) === '|') { cells.pop(); }
    return cells.map(function (c) { return c.trim(); });
  }

  // セル値が既知のエージェント ID なら画面では表示名に直す。レポート本文の
  // Markdown はサーバ側が組み立てるため、置き換えはここでしかできない。
  function tableCellText(value) {
    return Object.prototype.hasOwnProperty.call(AGENT_DISPLAY_NAMES, value)
      ? agentDisplayName(value) : value;
  }

  // 列数は見出し行を正とする。あふれた分は最後のセルへ畳み、足りない分は空で埋める。
  function fitRowToColumns(cells, colCount) {
    var row = cells.slice();
    while (row.length > colCount && row[row.length - 1] === '') { row.pop(); }
    if (row.length > colCount) {
      var tail = row.slice(colCount - 1).filter(function (c) { return c !== ''; });
      row = row.slice(0, colCount - 1).concat([tail.join(' | ')]);
    }
    while (row.length < colCount) { row.push(''); }
    return row;
  }

  function buildReportTable(rows) {
    var table = el('table', 'data hl-report-table');
    // 区切り行（|---|---|）は行ではないので、組み立てる前に落とす。
    var body = rows.filter(function (raw) { return !isTableDivider(raw); })
      .map(function (raw) { return splitTableRow(raw); });
    if (body.length === 0) { return table; }
    var headCells = body[0].slice();
    while (headCells.length > 1 && headCells[headCells.length - 1] === '') { headCells.pop(); }
    var colCount = headCells.length;

    var thead = el('thead');
    var trh = el('tr', 'hl-report-tr');
    headCells.forEach(function (c) {
      var th = el('th', 'hl-report-th');
      appendInline(th, c);
      trh.appendChild(th);
    });
    thead.appendChild(trh);
    table.appendChild(thead);

    var tbody = el('tbody');
    body.slice(1).forEach(function (cells) {
      var tr = el('tr', 'hl-report-tr');
      fitRowToColumns(cells, colCount).forEach(function (c) {
        var td = el('td', 'hl-report-td');
        appendInline(td, tableCellText(c));
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    return table;
  }

  // 段落を打ち切るべき行。太字だけの行（小見出し）と引用を含めないと、
  // 「**事象**」と次行の本文が同じ段落に流し込まれる。
  function isStrongHeadingLine(line) {
    return /^\s*\*\*[^*]+\*\*\s*$/.test(line);
  }
  function isBlockStart(line) {
    return /^\s*(```|#{1,6}\s|[-*+]\s|\d+[.)]\s|\||>)/.test(line) || isStrongHeadingLine(line);
  }

  function renderMarkdown(md) {
    var root = el('div', 'hl-report-body');
    var lines = String(md || '').split('\n');
    var i = 0;
    while (i < lines.length) {
      var line = lines[i];

      if (/^\s*```/.test(line)) {
        var info = line.replace(/^\s*```/, '').trim().toLowerCase();
        i += 1;
        var code = [];
        while (i < lines.length && !/^\s*```/.test(lines[i])) { code.push(lines[i]); i += 1; }
        i += 1;
        // 差分は行色を残したまま、レポートの明るい面に載せる（実行ログの黒背景は使わない）。
        if (info === 'diff' || info === 'patch') {
          root.appendChild(buildDiffElement(code.join('\n'), 'hl-report-code hl-report-diff'));
        } else {
          root.appendChild(el('pre', 'hl-report-code', code.join('\n')));
        }
        continue;
      }

      var h = /^\s*(#{1,6})\s+(.*)$/.exec(line);
      if (h) {
        // レポートは画面の一部なので、見出しレベルは h3 以下に押し下げる。
        var head = el('h' + Math.min(6, h[1].length + 2), 'hl-report-h hl-report-head');
        appendInline(head, h[2]);
        root.appendChild(head);
        i += 1;
        continue;
      }

      if (isStrongHeadingLine(line)) {
        var sub = /^\s*\*\*([^*]+)\*\*\s*$/.exec(line);
        root.appendChild(el('h5', 'hl-report-h', sub[1].trim()));
        i += 1;
        continue;
      }

      if (/^\s*>/.test(line)) {
        var quote = el('blockquote', 'hl-report-quote');
        while (i < lines.length && /^\s*>/.test(lines[i])) {
          quote.appendChild(
            el('div', 'hl-report-quote-line', lines[i].replace(/^\s*>\s?/, ''))
          );
          i += 1;
        }
        root.appendChild(quote);
        continue;
      }

      if (/^\s*\|/.test(line)) {
        var rows = [];
        while (i < lines.length && /^\s*\|/.test(lines[i])) { rows.push(lines[i]); i += 1; }
        root.appendChild(buildReportTable(rows));
        continue;
      }

      if (/^\s*[-*+]\s+/.test(line) || /^\s*\d+[.)]\s+/.test(line)) {
        var ordered = /^\s*\d+[.)]\s+/.test(line);
        var listEl = el(ordered ? 'ol' : 'ul',
                        ordered ? 'hl-report-list hl-report-ol' : 'hl-report-list hl-report-ul');
        var itemRe = ordered ? /^\s*\d+[.)]\s+/ : /^\s*[-*+]\s+/;
        while (i < lines.length && itemRe.test(lines[i])) {
          var li = el('li', 'hl-report-li');
          appendInline(li, lines[i].replace(itemRe, ''));
          listEl.appendChild(li);
          i += 1;
        }
        root.appendChild(listEl);
        continue;
      }

      if (!line.trim()) { i += 1; continue; }

      var para = [];
      while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i])) {
        para.push(lines[i].trim());
        i += 1;
      }
      if (para.length) {
        var p = el('p', 'hl-report-p');
        appendInline(p, para.join(' '));
        root.appendChild(p);
      } else {
        i += 1;
      }
    }
    return root;
  }

  function renderDefectsTable(defects) {
    if (!defects || defects.length === 0) {
      return el('p', 'hl-hint', '検出した不具合はありません。');
    }
    var table = el('table', 'data dashboard-table');
    var thead = el('thead');
    var trh = el('tr');
    ['重大度', '事象', '失敗したテスト'].forEach(function (t) { trh.appendChild(el('th', 'hl-th-nowrap', t)); });
    thead.appendChild(trh);
    table.appendChild(thead);
    var tbody = el('tbody');
    defects.forEach(function (d) {
      var tr = el('tr');
      var tdSev = el('td');
      tdSev.appendChild(el('span', 'hl-sev is-' + d.severity, SEVERITY_LABELS[d.severity] || d.severity));
      tr.appendChild(tdSev);
      tr.appendChild(el('td', null, d.title || d.message || ''));
      var tdTest = el('td', 'hl-kv hl-ellipsis', d.test_id || '');
      tdTest.title = d.test_id || '';
      tr.appendChild(tdTest);
      // 疑わしいファイルは直下の「該当箇所の根拠」に確度つきで出るため、列は持たない。
      tbody.appendChild(tr);

      // なぜそのファイルが疑われるのかを、欠陥のすぐ下に出す。
      var evTr = el('tr', 'hl-evidence-row');
      var evTd = el('td');
      evTd.colSpan = 3;
      evTd.appendChild(renderEvidence(d.locations));
      evTr.appendChild(evTd);
      tbody.appendChild(evTr);
    });
    table.appendChild(tbody);
    return table;
  }

  function buildDiffElement(diffText, className) {
    // className で配色の面を差し替える（黒背景の実行ログ / 明るいレポート面）。行色は共通。
    var pre = el('pre', className || 'hl-diff');
    (diffText || '').split('\n').forEach(function (line) {
      // メタ行（ファイル境界・ハンク）を追加削除と同色にすると差分が読めない。
      var cls = 'hl-diff-ctx';
      if (/^(diff --git|index |@@|\+\+\+|---|new file mode|deleted file mode|old mode|new mode|similarity index|rename )/.test(line)) {
        cls = 'hl-diff-meta';
      } else if (line.charAt(0) === '+') {
        cls = 'hl-diff-add add';
      } else if (line.charAt(0) === '-') {
        cls = 'hl-diff-del del';
      }
      pre.appendChild(el('span', cls, line));
    });
    return pre;
  }

  /* ---- 他ファイルへ公開 ---- */
  HL.buildDiffElement = buildDiffElement;
  HL.renderDefectsTable = renderDefectsTable;
  HL.renderMarkdown = renderMarkdown;
})(window.HealingApp = window.HealingApp || {});
