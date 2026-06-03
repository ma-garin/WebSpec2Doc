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

