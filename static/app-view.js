function allFields(rj) {
  const rows = [];
  for (const sc of (rj.screens || [])) {
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

// ---- 概要 ----
function renderOverview() {
  if (!reportJson) {
    resultHero.innerHTML = '<div class="hero-pad">' +
      '<p style="color:var(--text-muted);font-size:13px;margin-bottom:12px">このサイトは旧バージョンで生成されたため画面別の構造化データがありません。「<strong>再クロール</strong>」で最新のテスト条件マトリクスを生成できます。詳細は「画面別仕様」タブを参照してください。</p>' +
      '</div>';
    return;
  }
  const screens = reportJson.screens || [];
  const meta = reportJson.meta || {};
  const rows = screens.map(sc => {
    const fields = (sc.forms || []).reduce((n, fm) => n + (fm.fields || []).length, 0);
    const to = (sc.transitions && sc.transitions.to || []).join(', ') || '—';
    return `<tr><td class="c-screen">${escHtml(sc.page_id)}</td><td>${escHtml(sc.title || '')}</td>` +
      `<td><code style="font-size:.78rem;color:var(--text-muted)">${escHtml(sc.url || '')}</code></td>` +
      `<td class="num">${(sc.forms || []).length}</td><td class="num">${fields}</td><td>${escHtml(to)}</td></tr>`;
  }).join('');
  resultHero.innerHTML = '<div class="hero-pad">' +
    `<p style="color:var(--text-muted);font-size:13px;margin-bottom:12px">対象 ${escHtml(meta.target_url || '')} ／ クロール: 深さ${meta.crawl_depth ?? '-'} ・最大${meta.max_pages ?? '-'}ページ ／ ${escHtml(meta.crawled_at || '')}</p>` +
    '<div class="hero-section-title">画面インベントリ</div>' +
    '<table class="ov-screens"><thead><tr><th>画面ID</th><th>タイトル</th><th>URL</th><th>フォーム</th><th>入力項目</th><th>遷移先</th></tr></thead><tbody>' +
    (rows || '<tr><td colspan="6" style="color:var(--text-muted)">画面がありません</td></tr>') + '</tbody></table>' +
    '</div>';
}

// ---- 入力項目・テスト条件マトリクス ----
function renderMatrix() {
  if (!reportJson) { resultHero.innerHTML = '<div class="hero-msg">マトリクスデータ（report.json）を読み込めませんでした。</div>'; return; }
  const screens = (reportJson.screens || []).map(s => s.page_id);
  resultHero.innerHTML =
    '<div class="matrix-toolbar">' +
    '<select id="mx-screen"><option value="">全画面</option>' + screens.map(s => `<option value="${escHtml(s)}">${escHtml(s)}</option>`).join('') + '</select>' +
    '<input type="search" id="mx-search" placeholder="項目名・条件で検索" />' +
    '<label><input type="checkbox" id="mx-required"> 必須のみ</label>' +
    '<button type="button" class="btn-outline-sm" id="mx-csv">CSVで書き出し</button>' +
    '<span class="matrix-count" id="mx-count"></span>' +
    '<span class="cond-legend">種別:' +
    '<span class="cond-pill cc-req">必須</span>' +
    '<span class="cond-pill cc-bound">境界値</span>' +
    '<span class="cond-pill cc-format">形式</span>' +
    '<span class="cond-pill cc-opt">選択肢</span>' +
    '<span class="cond-pill cc-other">その他</span>' +
    '</span>' +
    '</div><div id="mx-table-wrap"></div>';
  let t = null;
  const debounced = () => { clearTimeout(t); t = setTimeout(drawMatrix, 150); };
  document.getElementById('mx-screen').addEventListener('change', drawMatrix);
  document.getElementById('mx-search').addEventListener('input', debounced);
  document.getElementById('mx-required').addEventListener('change', drawMatrix);
  document.getElementById('mx-csv').addEventListener('click', exportMatrixCsv);
  drawMatrix();
}
function condClass(c) {
  if (c.includes('必須')) return 'cc-req';
  if (c.includes('最大長') || c.includes('最小長') || c.includes('範囲') || c.includes('境界')) return 'cc-bound';
  if (c.includes('形式') || c.includes('メール') || c.includes('パターン') || c.includes('日付') || c.includes('電話') || c.includes('数値') || c.includes('パスワード')) return 'cc-format';
  if (c.includes('選択肢') || c.includes('ON / OFF') || c.includes('未選択')) return 'cc-opt';
  return 'cc-other';
}
function matrixRows() {
  const scFilter = (document.getElementById('mx-screen') || {}).value || '';
  const q = ((document.getElementById('mx-search') || {}).value || '').toLowerCase();
  const reqOnly = (document.getElementById('mx-required') || {}).checked;
  return allFields(reportJson).filter(r => {
    if (scFilter && r.screen !== scFilter) return false;
    if (reqOnly && !r.field.required) return false;
    if (q) {
      const hay = (r.field.name + ' ' + (r.field.test_conditions || []).join(' ') + ' ' + constraintText(r.field)).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}
function drawMatrix() {
  const rows = matrixRows();
  document.getElementById('mx-count').textContent = rows.length + ' 項目';
  const body = rows.map(r => {
    const f = r.field;
    return '<tr>' +
      `<td class="c-screen">${escHtml(r.screen)}</td>` +
      `<td>${escHtml(f.name || '(無名)')}</td>` +
      `<td>${escHtml(f.field_type || '')}</td>` +
      `<td>${f.required ? '<span class="c-req">必須</span>' : '-'}</td>` +
      `<td>${escHtml(constraintText(f)) || '-'}</td>` +
      `<td>${escHtml(defaultOptionsText(f)) || '-'}</td>` +
      `<td class="c-loc">${escHtml((f.locators || []).join(' / ')) || '-'}</td>` +
      `<td class="c-cond">${(f.test_conditions || []).map(c => `<span class="cond-pill ${condClass(c)}">${escHtml(c)}</span>`).join('') || '-'}</td>` +
    '</tr>';
  }).join('');
  document.getElementById('mx-table-wrap').innerHTML =
    '<table class="matrix"><thead><tr><th>画面</th><th>項目名</th><th>型</th><th>必須</th><th>制約</th><th>既定/選択肢</th><th>ロケータ候補</th><th>導出テスト条件</th></tr></thead><tbody>' +
    (body || '<tr><td colspan="8" style="padding:16px;color:var(--text-muted)">該当する入力項目がありません</td></tr>') + '</tbody></table>';
}
function exportMatrixCsv() {
  const head = ['画面', '項目名', '型', '必須', '制約', '既定/選択肢', 'ロケータ候補', '導出テスト条件'];
  const esc = v => '"' + String(v).replace(/"/g, '""') + '"';
  const lines = [head.map(esc).join(',')];
  for (const r of matrixRows()) {
    const f = r.field;
    lines.push([r.screen, f.name || '(無名)', f.field_type || '', f.required ? '必須' : '', constraintText(f), defaultOptionsText(f), (f.locators || []).join(' / '), (f.test_conditions || []).join(' / ')].map(esc).join(','));
  }
  const blob = new Blob(['\\uFEFF' + lines.join('\\r\\n')], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'test_conditions.csv';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(a.href);
}

// ---- 画面別仕様（リデザイン：全幅スクショ・フォームカード・クリック展開テスト条件）----
function renderReport() {
  if (!reportJson || !(reportJson.screens || []).length) {
    resultHero.innerHTML = '<div class="hero-msg"><p>画面別仕様データ（report.json）がありません。</p></div>';
    return;
  }
  const screens = reportJson.screens;
  const pageIds = new Set(screens.map(s => s.page_id));
  const allShots = (resultData.screenshots || []).filter(p => pageIds.has(p.split('/').pop().replace(/\.png$/, '')));

  resultHero.innerHTML =
    '<div class="rpt-pane-wrap">' +
    '<div class="rpt-list" id="rpt-list"></div>' +
    '<div class="rpt-detail" id="rpt-detail"><p class="hero-msg" style="padding:24px">左の一覧から画面を選択してください。</p></div>' +
    '</div>';

  const list = document.getElementById('rpt-list');
  screens.forEach((sc, idx) => {
    const item = document.createElement('div');
    item.className = 'rpt-list-item' + (idx === 0 ? ' is-active' : '');
    item.dataset.pid = sc.page_id;
    const hasForm = (sc.forms || []).some(f => (f.fields || []).length > 0);
    item.innerHTML =
      `<strong>${escHtml(sc.page_id)}</strong>` +
      `<span>${escHtml(sc.title || '')}</span>` +
      (hasForm ? '<span style="font-size:10px;color:var(--primary);font-weight:700">フォームあり</span>' : '');
    item.addEventListener('click', () => {
      list.querySelectorAll('.rpt-list-item').forEach(el => el.classList.remove('is-active'));
      item.classList.add('is-active');
      renderReportDetail(sc, allShots);
    });
    list.appendChild(item);
  });
  renderReportDetail(screens[0], allShots);
}

function renderReportDetail(sc, allShots) {
  const detail = document.getElementById('rpt-detail');
  if (!detail) return;

  const shotPath = allShots.find(p => p.split('/').pop().replace(/\.png$/, '') === sc.page_id);
  const shotSrc = shotPath ? `/preview?path=${encodeURIComponent(shotPath)}` : '';
  const shotHtml = shotPath
    ? `<img src="${escHtml(shotSrc)}" class="rpt-screenshot" loading="lazy" alt="${escHtml(sc.page_id)}" onclick="openLightbox('${escHtml(shotSrc)}')" /><p class="rpt-screenshot-caption">クリックで全画面表示</p>`
    : '';

  const transTo = (sc.transitions && sc.transitions.to) || [];
  const transFrom = (sc.transitions && sc.transitions.from) || [];
  const transHtml = (transTo.length || transFrom.length)
    ? `<div class="rpt-transitions">遷移先: ${transTo.length ? transTo.map(escHtml).join('、') : '—'} ／ 遷移元: ${transFrom.length ? transFrom.map(escHtml).join('、') : '—'}</div>`
    : '';

  const nonEmptyForms = (sc.forms || []).filter(f => (f.fields || []).length > 0);
  let formsHtml = '';
  if (!nonEmptyForms.length) {
    // フォームがない場合でも見出し・ボタン・リンクを表示
    const headings = (sc.headings || []).filter(Boolean);
    const buttons = (sc.buttons || []).filter(Boolean);
    const links = (sc.transitions && sc.transitions.to || []).filter(Boolean);
    const rows = [
      ...headings.map(h => `<div class="rpt-element-row"><span class="rpt-element-kind">見出し</span><span class="rpt-element-val">${escHtml(h)}</span></div>`),
      ...buttons.map(b => `<div class="rpt-element-row"><span class="rpt-element-kind">ボタン</span><span class="rpt-element-val">${escHtml(b)}</span></div>`),
      ...links.map(l => `<div class="rpt-element-row"><span class="rpt-element-kind">遷移先</span><span class="rpt-element-val">${escHtml(l)}</span></div>`),
    ];
    formsHtml = '<div class="rpt-page-elements">' +
      '<div class="rpt-page-elements-title">ページ要素（フォームなし）</div>' +
      (rows.length ? rows.join('') : '<p style="color:var(--text-muted);font-size:12px;margin:0">解析可能な要素が見つかりませんでした。</p>') +
      '</div>';
  } else {
    formsHtml = nonEmptyForms.map((fm, fi) => {
      const fieldRows = (fm.fields || []).map(f => {
        const condCount = (f.test_conditions || []).length;
        const condHtml = condCount
          ? `<details class="rpt-cond-expand"><summary class="rpt-cond-summary">${condCount}件</summary><div class="rpt-cond-pills">${(f.test_conditions || []).map(c => `<span class="cond-pill ${condClass(c)}">${escHtml(c)}</span>`).join('')}</div></details>`
          : '—';
        return `<tr>
          <td style="font-weight:600">${escHtml(f.name || '(無名)')}</td>
          <td>${escHtml(f.field_type || '')}</td>
          <td style="text-align:center">${f.required ? '<span style="color:var(--critical);font-weight:700">●</span>' : ''}</td>
          <td style="font-size:11px">${escHtml(constraintText(f)) || '—'}</td>
          <td><code class="loc-hint">${escHtml((f.locators || [])[0] || '')}</code></td>
          <td>${condHtml}</td>
        </tr>`;
      }).join('');
      return `<div class="rpt-form-card">
        <div class="rpt-form-card-header">
          フォーム ${fi + 1}
          <span class="rpt-form-card-method">${escHtml(fm.method || 'get')}</span>
          <span style="font-weight:400;margin-left:4px">${escHtml(fm.action || '')}</span>
        </div>
        <div style="overflow-x:auto">
          <table class="rpt-field-table">
            <thead><tr><th>項目名</th><th>型</th><th>必須</th><th>制約</th><th>ロケータ候補</th><th>テスト条件</th></tr></thead>
            <tbody>${fieldRows}</tbody>
          </table>
        </div>
      </div>`;
    }).join('');
  }

  detail.innerHTML =
    `<div class="rpt-detail-header" style="margin-bottom:12px">
      <h3 style="font-size:16px;margin-bottom:4px">${escHtml(sc.title || sc.page_id)}</h3>
      <code class="rpt-url">${escHtml(sc.url || '')}</code>
    </div>` +
    shotHtml + transHtml + formsHtml;
}

// ---- 設計（テスト設計技法 推奨） ----

const DESIGN_TECHNIQUES = [
  { key: 'ep',   label: '同値分割',               abbr: '同値分割'  },
  { key: 'bva',  label: '境界値分析',             abbr: '境界値分析' },
  { key: 'dt',   label: 'デシジョンテーブル',     abbr: '決定表'    },
  { key: 'st',   label: '状態遷移テスト',         abbr: '状態遷移'  },
  { key: 'ct',   label: 'クラシフィケーションツリー', abbr: '分類木'  },
  { key: 'pw',   label: 'ペアワイズ',             abbr: 'PW法'      },
  { key: 'uc',   label: 'ユースケーステスト',     abbr: 'UCテスト'  },
  { key: 'comb', label: '組み合わせ',             abbr: '組合せ'    },
];

function _designInputFields(sc) {
  const SKIP = new Set(['hidden','submit','button','reset','image']);
  return (sc.forms || []).flatMap(f => (f.fields || []).filter(x => !SKIP.has(x.field_type)));
}

function _recommendFor(sc) {
  const fields = _designInputFields(sc);
  const boundary = fields.filter(f => f.maxlength || f.minlength || f.min_value || f.max_value || f.pattern);
  const required = fields.filter(f => f.required);
  const withOpts  = fields.filter(f => f.options && f.options.length > 0);
  const selects   = fields.filter(f => f.field_type === 'select' || f.field_type === 'radio' || f.field_type === 'checkbox');
  const to   = (sc.transitions && sc.transitions.to)   || [];
  const from = (sc.transitions && sc.transitions.from) || [];
  const hasForm = fields.length > 0;

  const rec = {};

  // 同値分割: 入力フィールドがあれば適用
  if (hasForm) {
    rec.ep = fields.map(f =>
      `${escHtml(f.name || f.field_type)}: 有効値 / 無効値・空値クラス`
    );
  }

  // 境界値分析: 上限・下限・パターン制約がある
  if (boundary.length) {
    rec.bva = boundary.map(f => {
      const parts = [];
      if (f.maxlength)  parts.push(`maxlength=${f.maxlength}`);
      if (f.minlength)  parts.push(`minlength=${f.minlength}`);
      if (f.min_value)  parts.push(`min=${f.min_value}`);
      if (f.max_value)  parts.push(`max=${f.max_value}`);
      if (f.pattern)    parts.push(`pattern 制約あり`);
      return `${escHtml(f.name || f.field_type)}: ${parts.join('、')}`;
    });
  }

  // デシジョンテーブル: 必須フィールドが 2 件以上
  if (required.length >= 2) {
    rec.dt = [
      `必須フィールド ${required.length}件 → 入力有無の組み合わせで ${Math.pow(2, Math.min(required.length, 4))} パターン`,
      required.map(f => escHtml(f.name || f.field_type)).join('、') + ' の有効/無効マトリクス',
    ];
  }

  // 状態遷移テスト: 遷移先が存在する or 複数の遷移元
  if (to.length > 0 || from.length > 1) {
    const reasons = [];
    if (to.length)   reasons.push(`遷移先: ${to.map(escHtml).join('、')}`);
    if (from.length > 1) reasons.push(`複数の遷移元 (${from.length}件): ${from.map(escHtml).join('、')}`);
    rec.st = reasons;
  }

  // クラシフィケーションツリー: select/radio/checkbox が 1 件以上 OR 入力が 3 件以上
  if (selects.length >= 1 || fields.length >= 3) {
    const reasons = [];
    if (selects.length) reasons.push(...selects.map(f =>
      `${escHtml(f.name || f.field_type)}: ${f.options.length || '複数'} 選択肢 → 独立した分類軸`
    ));
    if (!selects.length && fields.length >= 3)
      reasons.push(`入力パラメータ ${fields.length}件 → 分類ツリーで網羅的カバー`);
    rec.ct = reasons;
  }

  // ペアワイズ: 入力パラメータが 4 件以上
  if (fields.length >= 4) {
    rec.pw = [
      `入力パラメータ ${fields.length}件 → 全組み合わせは ${fields.length <= 8 ? Math.pow(2, fields.length) + ' 件' : '膨大'} → ペアワイズで削減`,
    ];
  }

  // ユースケーステスト: フォームがあり遷移先が存在 or ボタンが複数
  const buttons = sc.buttons || [];
  if (hasForm && (to.length > 0 || buttons.length >= 2)) {
    const reasons = [`入力→送信→${to.length ? to.map(escHtml).join('、') + ' への遷移' : 'レスポンス確認'} の一連シナリオ`];
    if (buttons.length >= 2) reasons.push(`操作ボタン: ${buttons.slice(0, 4).map(escHtml).join('、')}`);
    rec.uc = reasons;
  }

  // 組み合わせ: 選択肢フィールドが 2 件以上 かつ 全パラメータ数 ≤ 5
  if (withOpts.length >= 2 && fields.length <= 5) {
    const total = withOpts.reduce((n, f) => n * Math.max(f.options.length, 2), 1);
    rec.comb = [
      `選択肢フィールド ${withOpts.length}件 → 全組み合わせ ${total} パターン（全数テスト可能範囲）`,
      withOpts.map(f => `${escHtml(f.name)}: ${f.options.length}値`).join('、'),
    ];
  }

  return rec;
}

function renderDesign() {
  if (!reportJson || !(reportJson.screens || []).length) {
    resultHero.innerHTML = '<div class="hero-msg"><p>設計データ（report.json）がありません。クロールを実行してください。</p></div>';
    return;
  }
  const screens = reportJson.screens;

  // ---- マトリクス ----
  const matrixRows = screens.map(sc => {
    const rec = _recommendFor(sc);
    const cells = DESIGN_TECHNIQUES.map(t =>
      rec[t.key]
        ? `<td style="text-align:center;color:#24A148;font-size:15px">✓</td>`
        : `<td style="text-align:center;color:var(--text-muted);font-size:12px">—</td>`
    ).join('');
    return `<tr><td class="c-screen">${escHtml(sc.page_id)}</td><td style="font-size:12px;color:var(--text-muted)">${escHtml(sc.title || '')}</td>${cells}</tr>`;
  }).join('');

  const matrixHead = DESIGN_TECHNIQUES.map(t =>
    `<th style="font-size:11px;writing-mode:vertical-lr;min-width:28px;padding:6px 4px">${escHtml(t.abbr)}</th>`
  ).join('');

  // ---- 画面別詳細 ----
  const TECH_COLORS = {
    ep: '#0F62FE', bva: '#6929C4', dt: '#005D5D', st: '#9F1853',
    ct: '#198038', pw: '#B12704', uc: '#0043CE', comb: '#6E6E6E',
  };
  const detailCards = screens.map(sc => {
    const rec = _recommendFor(sc);
    const keys = Object.keys(rec);
    if (!keys.length) return `
      <div style="border:1px solid var(--border);border-radius:6px;padding:14px 16px;margin-bottom:12px">
        <div style="font-weight:600;margin-bottom:4px">${escHtml(sc.page_id)} <span style="color:var(--text-muted);font-weight:400">${escHtml(sc.title || '')}</span></div>
        <p style="color:var(--text-muted);font-size:12px;margin:0">フォームも遷移もないページのため、技法の推奨なし</p>
      </div>`;

    const badges = keys.map(k => {
      const t = DESIGN_TECHNIQUES.find(x => x.key === k);
      const col = TECH_COLORS[k] || '#444';
      return `<span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;color:#fff;background:${col};margin:2px 3px 2px 0">${escHtml(t.label)}</span>`;
    }).join('');

    const rationale = keys.map(k => {
      const t = DESIGN_TECHNIQUES.find(x => x.key === k);
      const reasons = rec[k];
      const col = TECH_COLORS[k] || '#444';
      return `<div style="margin-bottom:8px">
        <span style="font-size:12px;font-weight:700;color:${col}">${escHtml(t.label)}</span>
        <ul style="margin:2px 0 0 0;padding-left:18px">
          ${reasons.map(r => `<li style="font-size:12px;color:var(--text);margin-bottom:2px">${r}</li>`).join('')}
        </ul>
      </div>`;
    }).join('');

    return `
      <div style="border:1px solid var(--border);border-radius:6px;padding:14px 16px;margin-bottom:12px">
        <div style="font-weight:600;margin-bottom:6px">
          ${escHtml(sc.page_id)}
          <span style="color:var(--text-muted);font-weight:400"> ${escHtml(sc.title || '')}</span>
          <code style="font-size:11px;color:var(--text-muted);margin-left:8px">${escHtml(sc.url || '')}</code>
        </div>
        <div style="margin-bottom:10px">${badges}</div>
        <details style="font-size:12px">
          <summary style="cursor:pointer;color:var(--text-muted);font-size:12px">根拠を表示</summary>
          <div style="margin-top:8px;padding-left:4px">${rationale}</div>
        </details>
      </div>`;
  }).join('');

  // ---- 技法凡例 ----
  const legend = DESIGN_TECHNIQUES.map(t => {
    const col = TECH_COLORS[t.key] || '#444';
    return `<span style="display:inline-flex;align-items:center;gap:4px;margin:2px 8px 2px 0;font-size:12px">
      <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${col}"></span>${escHtml(t.abbr)} = ${escHtml(t.label)}
    </span>`;
  }).join('');

  resultHero.innerHTML =
    '<div class="hero-pad">' +
    '<div class="hero-section-title">テスト設計技法マトリクス</div>' +
    '<p style="color:var(--text-muted);font-size:12px;margin:0 0 8px">画面要素（入力フィールド・選択肢・遷移）に基づき推奨技法を自動判定します。「技法詳細」タブで各画面の根拠を確認できます。</p>' +
    `<div style="overflow-x:auto;margin-bottom:20px"><table class="ov-screens" style="min-width:max-content"><thead><tr><th>画面</th><th>タイトル</th>${matrixHead}</tr></thead><tbody>${matrixRows}</tbody></table></div>` +
    '<div class="hero-section-title" style="margin-top:4px">技法凡例</div>' +
    `<div style="margin-bottom:12px;line-height:2">${legend}</div>` +
    '</div>';
}

// ---- 技法詳細（画面ごとの推奨技法と根拠・動的導出） ----
function renderTechniqueDetail() {
  if (!reportJson || !(reportJson.screens || []).length) {
    resultHero.innerHTML = '<div class="hero-msg"><p>設計データ（report.json）がありません。クロールを実行してください。</p></div>';
    return;
  }
  const screens = reportJson.screens;

  const TECH_COLORS = {
    ep: '#0F62FE', bva: '#6929C4', dt: '#005D5D', st: '#9F1853',
    ct: '#198038', pw: '#B12704', uc: '#0043CE', comb: '#6E6E6E',
  };

  const detailCards = screens.map(sc => {
    const rec = _recommendFor(sc);
    const keys = Object.keys(rec);
    if (!keys.length) return `
      <div style="border:1px solid var(--border);border-radius:6px;padding:14px 16px;margin-bottom:12px">
        <div style="font-weight:600;margin-bottom:4px">${escHtml(sc.page_id)} <span style="color:var(--text-muted);font-weight:400">${escHtml(sc.title || '')}</span></div>
        <p style="color:var(--text-muted);font-size:12px;margin:0">フォームも遷移もないページのため、技法の推奨なし</p>
      </div>`;

    const badges = keys.map(k => {
      const t = DESIGN_TECHNIQUES.find(x => x.key === k);
      const col = TECH_COLORS[k] || '#444';
      return `<span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;color:#fff;background:${col};margin:2px 3px 2px 0">${escHtml(t.label)}</span>`;
    }).join('');

    const rationale = keys.map(k => {
      const t = DESIGN_TECHNIQUES.find(x => x.key === k);
      const reasons = rec[k];
      const col = TECH_COLORS[k] || '#444';
      return `<div style="margin-bottom:8px">
        <span style="font-size:12px;font-weight:700;color:${col}">${escHtml(t.label)}</span>
        <ul style="margin:4px 0 0 0;padding-left:18px">
          ${reasons.map(r => `<li style="font-size:12px;color:var(--text);margin-bottom:2px">${r}</li>`).join('')}
        </ul>
      </div>`;
    }).join('');

    return `
      <div style="border:1px solid var(--border);border-radius:6px;padding:14px 16px;margin-bottom:12px">
        <div style="font-weight:600;margin-bottom:6px">
          ${escHtml(sc.page_id)}
          <span style="color:var(--text-muted);font-weight:400"> ${escHtml(sc.title || '')}</span>
          <code style="font-size:11px;color:var(--text-muted);margin-left:8px">${escHtml(sc.url || '')}</code>
        </div>
        <div style="margin-bottom:10px">${badges}</div>
        <div style="font-size:12px">${rationale}</div>
      </div>`;
  }).join('');

  resultHero.innerHTML =
    '<div class="hero-pad">' +
    '<div class="hero-section-title">画面別 推奨技法と根拠</div>' +
    '<p style="color:var(--text-muted);font-size:12px;margin:0 0 12px">各画面の要素（フィールド種別・制約・選択肢数・遷移構造）から動的に導出した推奨技法と根拠です。</p>' +
    detailCards +
    '</div>';
}

// ---- 画面遷移図（vis.js / ADR-0003）----
function renderTransition() {
  if (!reportJson || !(reportJson.screens || []).length) {
    resultHero.innerHTML = '<div class="hero-msg">遷移データがありません。クロールを実行してください。</div>';
    return;
  }
  resultHero.innerHTML =
    '<div style="display:flex;flex-direction:column;height:100%">' +
    '<div class="vis-legend">' +
    '<span class="vis-legend-item"><span class="vis-legend-dot" style="background:#0F62FE"></span>フォームあり</span>' +
    '<span class="vis-legend-item"><span class="vis-legend-dot" style="background:#6B7280"></span>リンクのみ</span>' +
    '<span class="vis-legend-item"><span style="display:inline-block;width:18px;height:2px;background:#D32F2F;border-bottom:2px dashed #D32F2F"></span>フォーム送信</span>' +
    '<span style="margin-left:auto;font-size:11px">共通ナビ（50%以上から出る遷移）は非表示。ノードをクリックすると仕様を表示します。</span>' +
    '</div>' +
    '<div id="vis-network" style="flex:1;min-height:0"></div>' +
    '</div>';
  _loadVisJs(() => _drawVisNetwork(reportJson.screens));
}

function _loadVisJs(cb) {
  if (window.vis) { cb(); return; }
  const s = document.createElement('script');
  s.src = 'https://cdn.jsdelivr.net/npm/vis-network/standalone/umd/vis-network.min.js';
  s.onload = cb;
  document.head.appendChild(s);
}

function _commonNavTargets(screens) {
  const n = screens.length;
  const count = {};
  screens.forEach(sc => {
    (sc.transitions && sc.transitions.to || []).forEach(to => { count[to] = (count[to] || 0) + 1; });
  });
  const threshold = Math.max(2, Math.floor(n * 0.5));
  return new Set(Object.entries(count).filter(([, c]) => c >= threshold).map(([k]) => k));
}

function _drawVisNetwork(screens) {
  const container = document.getElementById('vis-network');
  if (!container || !window.vis) return;
  const common = _commonNavTargets(screens);
  const urlToId = {};
  screens.forEach(sc => { urlToId[sc.url] = sc.page_id; });

  const nodes = screens.map(sc => {
    const hasForm = (sc.forms || []).some(f => f.fields && f.fields.length);
    const label = sc.page_id + '\n' + (sc.title || '').replace(/\s*[|｜]\s*.*/g, '').slice(0, 20);
    return {
      id: sc.page_id,
      label,
      title: `<b>${escHtml(sc.page_id)}</b> ${escHtml(sc.title || '')}<br><code>${escHtml(sc.url || '')}</code>`,
      color: {
        background: hasForm ? '#1D4ED8' : '#4B5563',
        border: hasForm ? '#93C5FD' : '#9CA3AF',
        highlight: { background: hasForm ? '#1E40AF' : '#374151', border: '#E5E7EB' },
        hover: { background: hasForm ? '#2563EB' : '#374151', border: '#E5E7EB' },
      },
      font: { color: '#fff', size: 12, face: 'system-ui, sans-serif' },
      shape: 'box',
      borderWidth: 1,
      borderWidthSelected: 2,
      margin: { top: 8, bottom: 8, left: 12, right: 12 },
      shadow: { enabled: true, size: 4, x: 0, y: 2, color: 'rgba(0,0,0,.15)' },
    };
  });

  const edges = [];
  screens.forEach(sc => {
    (sc.transitions && sc.transitions.to || []).forEach(to => {
      if (!common.has(to)) edges.push({
        from: sc.page_id, to, arrows: { to: { enabled: true, scaleFactor: 0.7 } },
        color: { color: '#9CA3AF', highlight: '#374151', hover: '#4B5563' }, width: 1, smooth: { type: 'curvedCW', roundness: 0.1 },
      });
    });
    (sc.forms || []).forEach(f => {
      const toId = f.action ? urlToId[f.action] : null;
      if (toId && toId !== sc.page_id) edges.push({
        from: sc.page_id, to: toId, arrows: { to: { enabled: true, scaleFactor: 0.9 } },
        dashes: [6, 3], color: { color: '#DC2626', highlight: '#991B1B', hover: '#B91C1C' }, width: 2,
        label: 'フォーム送信', font: { size: 10, color: '#DC2626', strokeWidth: 2, strokeColor: '#fff' },
        smooth: { type: 'curvedCCW', roundness: 0.15 },
      });
    });
  });

  const network = new vis.Network(container,
    { nodes: new vis.DataSet(nodes), edges: new vis.DataSet(edges) },
    {
      layout: { randomSeed: 2 },
      physics: {
        enabled: true,
        solver: 'forceAtlas2Based',
        forceAtlas2Based: { gravitationalConstant: -80, centralGravity: 0.01, springLength: 160, springConstant: 0.05, damping: 0.4 },
        stabilization: { iterations: 300, updateInterval: 25 },
      },
      interaction: { hover: true, navigationButtons: true, keyboard: true, tooltipDelay: 100 },
      nodes: { borderRadius: 6 },
      edges: { selectionWidth: 2 },
    }
  );
  network.once('stabilizationIterationsDone', () => { network.setOptions({ physics: { enabled: false } }); });
  network.on('click', params => {
    if (params.nodes.length) {
      selectResultTab('report');
      setTimeout(() => {
        const item = document.querySelector(`.rpt-list-item[data-pid="${params.nodes[0]}"]`);
        if (item) item.click();
      }, 80);
    }
  });
}

// ---- 画面遷移表（ISTQB 状態遷移テスト標準フォーマット）----
function renderTransitionTable() {
  if (!reportJson || !(reportJson.screens || []).length) {
    resultHero.innerHTML = '<div class="hero-msg">遷移データがありません。</div>';
    return;
  }
  const screens = reportJson.screens;
  const common = _commonNavTargets(screens);
  const idToTitle = {};
  screens.forEach(sc => { idToTitle[sc.page_id] = sc.title || sc.page_id; });

  const urlToId = {};
  screens.forEach(s => { urlToId[s.url] = s.page_id; });
  const idToUrl = {};
  screens.forEach(s => { idToUrl[s.page_id] = s.url; });

  const rows = [];
  screens.forEach(sc => {
    (sc.transitions && sc.transitions.to || []).forEach(to => {
      if (common.has(to)) return;
      const destUrl = idToUrl[to] || '';
      let linkPath = destUrl;
      try { linkPath = new URL(destUrl).pathname; } catch (e) {}
      rows.push({ fromId: sc.page_id, fromTitle: sc.title || sc.page_id, event: 'リンク', eventDetail: linkPath, toId: to, toTitle: idToTitle[to] || to, action: destUrl });
    });
    (sc.forms || []).forEach(f => {
      if (!f.action) return;
      const toId = urlToId[f.action] || f.action;
      const toTitle = idToTitle[toId] || '（未取得）';
      rows.push({ fromId: sc.page_id, fromTitle: sc.title || sc.page_id, event: 'フォーム送信', eventDetail: `${(f.method || 'GET').toUpperCase()}`, toId, toTitle, action: f.action });
    });
  });

  if (!rows.length) { resultHero.innerHTML = '<div class="hero-msg">遷移情報がありません（共通ナビのみ検出）。</div>'; return; }

  const tableRows = rows.map(r =>
    `<tr>
      <td class="c-screen">${escHtml(r.fromId)}</td>
      <td>${escHtml(r.fromTitle)}</td>
      <td>
        <span class="cond-pill ${r.event === 'フォーム送信' ? 'cc-format trans-event-form' : 'cc-other trans-event-link'}">${escHtml(r.event)}</span>
        <span class="trans-link-detail">${escHtml(r.eventDetail)}</span>
      </td>
      <td class="c-screen">${escHtml(r.toId)}</td>
      <td>${escHtml(r.toTitle)}</td>
      <td style="font-size:11px;font-family:monospace;color:var(--text-muted);word-break:break-all">${escHtml(r.action)}</td>
    </tr>`
  ).join('');

  resultHero.innerHTML =
    '<div class="hero-pad">' +
    '<div class="hero-section-title">画面遷移表 — ISTQB 状態遷移テスト</div>' +
    `<p style="color:var(--text-muted);font-size:12px;margin:0 0 12px">${rows.length}件の遷移。共通ナビ（${Math.floor(screens.length * 0.5)}件以上から発生）は除外しています。</p>` +
    '<div style="overflow-x:auto">' +
    '<table class="trans-table">' +
    '<thead><tr><th>現在の画面</th><th>タイトル</th><th>イベント</th><th>遷移先</th><th>遷移先タイトル</th><th>アクション</th></tr></thead>' +
    `<tbody>${tableRows}</tbody>` +
    '</table></div></div>';
}

// ---- スクリーンショット一覧 ----
function renderShots() {
  if (!reportJson) {
    resultHero.innerHTML = '<div class="hero-msg">スクリーンショットの対応情報がありません。</div>';
    return;
  }
  const pageIds = new Set((reportJson.screens || []).map(s => s.page_id));
  const shots = (resultData.screenshots || []).filter(p => pageIds.has(p.split('/').pop().replace(/\.png$/, '')));
  if (!shots.length) {
    resultHero.innerHTML = '<div class="hero-msg">スクリーンショットがありません。</div>';
    return;
  }
  const items = shots.map(p => {
    const name = p.split('/').pop();
    const src = `/preview?path=${encodeURIComponent(p)}`;
    return `<figure class="shots-item"><img src="${escHtml(src)}" loading="lazy" alt="${escHtml(name)}" class="shots-thumb" onclick="openLightbox('${escHtml(src)}')" /><figcaption>${escHtml(name)}</figcaption></figure>`;
  }).join('');
  resultHero.innerHTML = '<div class="shots-grid">' + items + '</div>';
}

// ---- ライトボックス ----
function openLightbox(src) {
  const lb = document.getElementById('lightbox');
  const img = document.getElementById('lightbox-img');
  if (!lb || !img) return;
  img.src = src;
  lb.style.display = 'flex';
  document.addEventListener('keydown', closeLightboxOnEsc);
}
function closeLightbox() {
  const lb = document.getElementById('lightbox');
  if (lb) lb.style.display = 'none';
  document.removeEventListener('keydown', closeLightboxOnEsc);
}
function closeLightboxOnEsc(e) { if (e.key === 'Escape') closeLightbox(); }
(function initLightbox() {
  const lb = document.getElementById('lightbox');
  if (!lb) return;
  lb.addEventListener('click', (e) => { if (e.target === lb) closeLightbox(); });
  document.getElementById('lightbox-close').addEventListener('click', closeLightbox);
})();

// ---- エクスポート ----
function renderExport() {
  const files = resultData.files || {};
  const rows = EXPORT_DEFS.map(d => {
    const path = files[d.key];
    if (path) {
      return `<div class="export-row"><div class="export-main"><strong>${escHtml(d.label)}</strong><span class="export-desc">${escHtml(d.desc)}</span></div>` +
        `<a class="btn-outline-sm" href="/preview?path=${encodeURIComponent(path)}" target="_blank">開く</a>` +
        `<a class="btn-primary" style="height:36px;padding:0 16px;font-size:13px;display:inline-flex;align-items:center" href="/download?path=${encodeURIComponent(path)}" download>DL</a></div>`;
    }
    return `<div class="export-row export-missing"><div class="export-main"><strong>${escHtml(d.label)}</strong><span class="export-desc">未生成（出力形式で選択すると生成されます）</span></div></div>`;
  }).join('');
  resultHero.innerHTML = '<div class="hero-pad"><div class="export-grid">' +
    `<div class="export-row" style="background:var(--info-bg);border-color:var(--info-border)"><div class="export-main"><strong>すべてまとめてダウンロード</strong><span class="export-desc">生成物一式を ZIP で取得</span></div>` +
    `<a class="btn-primary" style="height:36px;padding:0 16px;font-size:13px;display:inline-flex;align-items:center" href="/download-zip?domain=${encodeURIComponent(resultData_domain())}">ZIP DL</a></div>` +
    rows + '</div></div>';
}
function resultData_domain() { return document.getElementById('r-domain').textContent || ''; }

// ---- 設定サブタブ ----
document.querySelectorAll('.set-tab').forEach(t => t.addEventListener('click', () => {
  document.querySelectorAll('.set-tab').forEach(x => x.classList.toggle('is-active', x === t));
  document.querySelectorAll('.set-panel').forEach(p => p.classList.toggle('is-active', p.id === 'set-panel-' + t.dataset.tab));
}));

// ---- API設定（.env にサーバ保存）----
function flash(id) { const m = document.getElementById(id); m.classList.add('show'); setTimeout(() => m.classList.remove('show'), 2000); }
async function loadApiSettings() {
  try {
    const res = await fetch('/api/settings'); const s = await res.json();
    document.getElementById('api-model').value = s.openai_model || 'gpt-5.4-mini';
    document.getElementById('api-org').value = s.openai_org_id || '';
    document.getElementById('api-project').value = s.openai_project_id || '';
    document.getElementById('api-key-current').textContent = s.openai_key_set ? s.openai_key_masked : '未設定';
  } catch (e) {}
}
document.getElementById('save-api').addEventListener('click', async () => {
  await fetch('/api/settings', { method: 'POST', body: new URLSearchParams({
    api_key: document.getElementById('api-key').value,
    org_id: document.getElementById('api-org').value,
    project_id: document.getElementById('api-project').value,
  }) });
  document.getElementById('api-key').value = ''; flash('api-msg'); loadApiSettings();
});
document.getElementById('save-model').addEventListener('click', async () => {
  await fetch('/api/settings', { method: 'POST', body: new URLSearchParams({ model: document.getElementById('api-model').value }) });
  flash('model-msg'); loadApiSettings();
});

// ---- URL履歴 datalist ----
async function loadUrlHistory() {
  try {
    const res = await fetch('/api/history'); const data = await res.json();
    const dl = document.getElementById('url-history-list');
    dl.innerHTML = (data.items || []).map(it => `<option value="https://${escHtml(it.domain)}/">`).join('');
  } catch (e) {}
}

// 初期化
applySettings(); loadSettingsForm(); loadApiSettings(); loadUrlHistory(); updateTargetPreview(); switchView('dashboard');
