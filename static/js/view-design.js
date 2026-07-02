// ---- 設計（テスト設計技法 推奨） ----

const TECHNIQUE_GUIDE = {
  ep:   { name:'同値分割', when:'入力フィールドが存在する画面すべてに適用', how:'1. 仕様から有効値クラスと無効値クラスを定義する\n2. 各クラスから代表値を1〜2件選んでテスト\n3. 境界には注意（境界値分析と組み合わせると効果的）', example:'メールアドレス欄\n✓ 有効値: user@example.com\n✗ 無効値: @@invalid, 空欄, スペースのみ' },
  bva:  { name:'境界値分析', when:'maxlength / min / max / pattern などの制約がある入力', how:'1. 上限値・下限値・その±1を必ずテスト\n2. 「ちょうど」「超える」「未満」の3点を押さえる\n3. NULL / 空値 / 0 は必ず含める', example:'文字数 100文字制限の欄\n✓ 99文字（OK）/ 100文字（OK）/ 101文字（NG）\n✓ 0文字・空欄（NG）' },
  dt:   { name:'デシジョンテーブル', when:'複数の必須条件が組み合わさる画面（ビジネスルールの検証）', how:'1. 条件列（各必須フィールドの入力有無）を並べる\n2. 各条件の真偽の全組み合わせを行として展開\n3. 期待される「アクション」（バリデーション結果）を記入', example:'必須フィールドA×B の2条件\n条件A=○, B=○ → 送信成功\n条件A=○, B=✗ → Bエラー表示\n条件A=✗, B=○ → Aエラー表示\n条件A=✗, B=✗ → 両エラー表示' },
  st:   { name:'状態遷移テスト', when:'複数の遷移先を持つ画面・ログイン/フロー制御がある画面', how:'1. 状態（画面）と遷移（操作）を一覧化\n2. 各遷移を最低1回テスト（全遷移カバレッジ）\n3. 不正な遷移（直接URLアクセス等）も確認', example:'ログイン画面\n正常: ログイン → ダッシュボード\n異常: ログイン → エラー表示\n不正遷移: 未ログインでダッシュボード直アクセス → リダイレクト確認' },
  ct:   { name:'分類木（Classification Tree）', when:'選択肢・ラジオ・チェックボックスがある画面、入力パラメータが3つ以上', how:'1. パラメータごとに「分類クラス」を列挙してツリーを描く\n2. ツリーの葉の組み合わせからテストケースを生成\n3. 全クラスが少なくとも1回カバーされることを確認', example:'検索条件: カテゴリ(3種) × 価格帯(4種) × 在庫あり(yes/no)\n→ 代表的な組み合わせを選択してテストケースを設計' },
  pw:   { name:'ペアワイズ（Pairwise）', when:'4パラメータ以上の入力がある画面（全組み合わせが膨大な場合）', how:'1. 全パラメータの2因子間の全組み合わせをカバーするセットを選択\n2. ツール（PICT等）で最小テストセットを生成\n3. 重要な組み合わせは追加でカバー', example:'5パラメータ（各2〜4値）\n全組み合わせ: 512通り\nペアワイズ: 約8〜16通りに削減（2因子間は全網羅）' },
  uc:   { name:'ユースケーステスト', when:'フォームと遷移が組み合わさるエンドツーエンドの操作フロー', how:'1. ユーザーのゴール（ユースケース）を起点にシナリオを設計\n2. 正常シナリオ（基本フロー）と代替・例外シナリオを網羅\n3. 前提条件・操作・期待結果を明記', example:'新規会員登録ユースケース\n前提: 未ログイン状態\n操作: 登録フォーム入力 → 確認メール受信 → 認証リンク押下\n期待: ログイン状態でダッシュボードへ遷移' },
  comb: { name:'組み合わせテスト', when:'選択肢フィールドが2つ以上・全パラメータ数が5以下の画面（全数テストが現実的）', how:'1. 各選択肢の値を列挙し、全組み合わせを表に展開\n2. 全てのセルにテストケースを割り当て\n3. パラメータ数が多い場合はペアワイズに切り替え', example:'性別(2種) × 年齢区分(3種)\n→ 2×3=6パターンを全数テスト\n（男×10代, 男×20代, ... 女×40代以上）' },
};

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

const _FIELD_TYPE_EXAMPLES = {
  email:    { valid: 'user@example.com', invalid: '@@invalid, 空欄' },
  password: { valid: 'Abc@1234（8文字以上・記号含む）', invalid: '短すぎる, 空欄' },
  tel:      { valid: '090-1234-5678', invalid: 'abc, 空欄' },
  number:   { valid: '42', invalid: '-1, abc, 空欄' },
  url:      { valid: 'https://example.com', invalid: 'example, 空欄' },
  date:     { valid: '2025-06-01', invalid: '99/99/99, 空欄' },
  text:     { valid: '有効なテキスト', invalid: '空欄, スペースのみ' },
  textarea: { valid: '有効なテキスト', invalid: '空欄, 最大文字数超過' },
  select:   { valid: '有効な選択肢を選択', invalid: '未選択（初期値のまま）' },
  radio:    { valid: 'いずれかを選択', invalid: '未選択（必須の場合）' },
  checkbox: { valid: 'チェックあり', invalid: 'チェックなし（必須の場合）' },
};

function _tcStub(key, sc) {
  const fields = _designInputFields(sc);
  const boundary = fields.filter(f => f.maxlength || f.minlength || f.min_value || f.max_value);
  const required = fields.filter(f => f.required);
  const selects  = fields.filter(f => ['select','radio','checkbox'].includes(f.field_type));
  const withOpts = fields.filter(f => f.options && f.options.length > 0);

  if (key === 'bva' && boundary.length) {
    return boundary.slice(0, 3).map(f => {
      const parts = [];
      if (f.maxlength) parts.push(`「${f.name || f.field_type}」\n  ✓ ${f.maxlength}文字 → 正常\n  ✗ ${Number(f.maxlength)+1}文字 → エラー\n  ✗ 空欄 → エラー`);
      else if (f.minlength) parts.push(`「${f.name || f.field_type}」\n  ✓ ${f.minlength}文字以上 → 正常\n  ✗ ${Math.max(0,Number(f.minlength)-1)}文字 → エラー`);
      else if (f.min_value || f.max_value) parts.push(`「${f.name || f.field_type}」\n  ✓ ${f.min_value ?? ''}〜${f.max_value ?? ''} → 正常\n  ✗ 範囲外の値 → エラー`);
      return parts.join('\n');
    }).filter(Boolean).join('\n---\n');
  }
  if (key === 'ep' && fields.length) {
    return fields.slice(0, 3).map(f => {
      const ex = _FIELD_TYPE_EXAMPLES[f.field_type] || _FIELD_TYPE_EXAMPLES.text;
      return `「${f.name || f.field_type}」\n  ✓ 有効値: ${ex.valid}\n  ✗ 無効値: ${ex.invalid}`;
    }).join('\n---\n');
  }
  if (key === 'dt' && required.length >= 2) {
    const names = required.slice(0, 4).map(f => f.name || f.field_type);
    const rows = [
      `条件:  ${names.join(' | ')}`,
      `TT${names.length > 2 ? '..T' : ''}: ${names.map(() => '入力あり').join(' | ')} → 送信成功`,
      `TF${names.length > 2 ? '...' : ''}: ${names.map((_, i) => i === names.length-1 ? '未入力' : '入力あり').join(' | ')} → ${names[names.length-1]}エラー`,
      `FT${names.length > 2 ? '...' : ''}: ${names.map((_, i) => i === 0 ? '未入力' : '入力あり').join(' | ')} → ${names[0]}エラー`,
    ];
    return rows.join('\n');
  }
  if (key === 'comb' && withOpts.length >= 2) {
    const f1 = withOpts[0], f2 = withOpts[1];
    const opts1 = (f1.options || []).slice(0, 3).map(o => o.label || o.value || o);
    const opts2 = (f2.options || []).slice(0, 3).map(o => o.label || o.value || o);
    const rows = [`${f1.name || 'フィールド1'} × ${f2.name || 'フィールド2'}`];
    opts1.forEach(v1 => opts2.forEach(v2 => rows.push(`  ${v1} × ${v2}`)));
    return rows.join('\n');
  }
  if (key === 'pw' && fields.length >= 4) {
    return `パラメータ数: ${fields.length}件\n全組み合わせ: ${fields.length <= 8 ? Math.pow(2, fields.length) : '多数'}通り\n→ ペアワイズツール（例: PICT）で最小テストセットを生成\nhttps://github.com/microsoft/pict`;
  }
  return '';
}

function renderDesign() {
  if (!reportJson || !(reportJson.screens || []).length) {
    resultHero.innerHTML = '<div class="hero-msg"><p>設計データ（report.json）がありません。クロールを実行してください。</p></div>';
    return;
  }
  const screens = reportJson.screens;

  // ---- マトリクス ----
  const TECH_BADGE_COLORS = {
    ep: '#0F62FE', bva: '#6929C4', dt: '#005D5D', st: '#9F1853',
    ct: '#198038', pw: '#B12704', uc: '#0043CE', comb: '#6E6E6E',
  };
  const matrixRows = screens.map(sc => {
    const rec = _recommendFor(sc);
    const cells = DESIGN_TECHNIQUES.map(t => {
      if (!rec[t.key]) return `<td class="tech-cell tech-miss" aria-label="非推奨">—</td>`;
      const tip = rec[t.key].join(' / ').replace(/"/g, '&quot;').slice(0, 120);
      const col = TECH_BADGE_COLORS[t.key] || '#444';
      return `<td class="tech-cell tech-hit" data-tip="${tip}"><span class="tech-badge" style="background:${col}">${escHtml(t.abbr)}</span></td>`;
    }).join('');
    return `<tr><td class="c-screen">${escHtml(sc.page_id)}</td><td style="font-size:12px;color:var(--text-muted)">${escHtml(sc.title || '')}</td>${cells}</tr>`;
  }).join('');

  const matrixHead = DESIGN_TECHNIQUES.map(t =>
    `<th><button type="button" class="tech-th-btn" data-tech-key="${t.key}" title="${escHtml(t.label)}のガイドを表示">${escHtml(t.abbr)}</button></th>`
  ).join('');

  // ---- 技法凡例 ----
  const TECH_COLORS = {
    ep: '#0F62FE', bva: '#6929C4', dt: '#005D5D', st: '#9F1853',
    ct: '#198038', pw: '#B12704', uc: '#0043CE', comb: '#6E6E6E',
  };
  const legend = DESIGN_TECHNIQUES.map(t => {
    const col = TECH_COLORS[t.key] || '#444';
    return `<span style="display:inline-flex;align-items:center;gap:4px;margin:2px 8px 2px 0;font-size:12px">
      <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${col}"></span>${escHtml(t.abbr)} = ${escHtml(t.label)}
    </span>`;
  }).join('');

  resultHero.innerHTML =
    '<div id="tech-guide-panel" class="tech-guide-panel" aria-hidden="true">' +
    '<div class="tech-guide-header"><span id="tech-guide-title" class="tech-guide-name"></span><button type="button" class="tech-guide-close" aria-label="閉じる">✕</button></div>' +
    '<div id="tech-guide-body" class="tech-guide-body"></div>' +
    '</div>' +
    '<div class="hero-pad">' +
    '<div class="hero-section-title" style="margin-bottom:4px">テスト設計技法マトリクス</div>' +
    '<p style="color:var(--text-muted);font-size:12px;margin:0 0 8px">技法列ヘッダーをクリックすると使い方ガイドが表示されます。✓バッジにカーソルを当てると推奨理由が確認できます。</p>' +
    `<div style="overflow-x:auto;margin-bottom:20px"><table class="ov-screens design-matrix" style="min-width:max-content"><thead><tr><th>画面</th><th>タイトル</th>${matrixHead}</tr></thead><tbody>${matrixRows}</tbody></table></div>` +
    '<div class="hero-section-title" style="margin-top:4px">技法凡例</div>' +
    `<div style="margin-bottom:12px;line-height:2">${legend}</div>` +
    '</div>';

  _bindTechGuide();
}

function _bindTechGuide() {
  const panel = document.getElementById('tech-guide-panel');
  const titleEl = document.getElementById('tech-guide-title');
  const bodyEl = document.getElementById('tech-guide-body');
  if (!panel) return;

  document.querySelectorAll('.tech-th-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const key = btn.dataset.techKey;
      const g = TECHNIQUE_GUIDE[key];
      if (!g) return;
      titleEl.textContent = g.name;
      bodyEl.innerHTML =
        '<div class="tg-section"><div class="tg-label">📋 適用条件</div><p>' + escHtml(g.when) + '</p></div>' +
        '<div class="tg-section"><div class="tg-label">🔧 設計手順</div><pre class="tg-pre">' + escHtml(g.how) + '</pre></div>' +
        '<div class="tg-section"><div class="tg-label">💡 テストケース例</div><pre class="tg-pre tg-example">' + escHtml(g.example) + '</pre></div>';
      panel.classList.add('is-open');
      panel.setAttribute('aria-hidden', 'false');
    });
  });

  panel.querySelector('.tech-guide-close')?.addEventListener('click', () => {
    panel.classList.remove('is-open');
    panel.setAttribute('aria-hidden', 'true');
  });
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
      const stub = _tcStub(k, sc);
      return `<div style="margin-bottom:12px">
        <div style="font-size:12px;font-weight:700;color:${col};margin-bottom:4px">${escHtml(t.label)}</div>
        <ul style="margin:0 0 4px 0;padding-left:18px">
          ${reasons.map(r => `<li style="font-size:12px;color:var(--text);margin-bottom:2px">${r}</li>`).join('')}
        </ul>
        ${stub ? `<div class="tc-stub-wrap"><div class="tc-stub-label">テストケース雛形</div><pre class="tc-stub">${escHtml(stub)}</pre><button type="button" class="tc-copy-btn" onclick="navigator.clipboard.writeText(this.previousElementSibling.textContent)" title="コピー">コピー</button></div>` : ''}
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

