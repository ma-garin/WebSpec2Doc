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

// 技法の定義は view-utils.js の TECH_META に一元化（色は tokens.css の --tech-*）

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
  const matrixRows = screens.map(sc => {
    const rec = _recommendFor(sc);
    const cells = TECH_META.map(t => {
      if (!rec[t.key]) return `<td class="tech-cell tech-miss" aria-label="非推奨">—</td>`;
      const tip = rec[t.key].join(' / ').replace(/"/g, '&quot;').slice(0, 120);
      return `<td class="tech-cell tech-hit" data-tip="${tip}">${techBadgeHtml(t.key, t.abbr)}</td>`;
    }).join('');
    return `<tr><td class="c-screen">${escHtml(sc.page_id)}</td><td class="design-title-cell">${escHtml(sc.title || '')}</td>${cells}</tr>`;
  }).join('');

  const matrixHead = TECH_META.map(t =>
    `<th><button type="button" class="tech-th-btn" data-tech-key="${t.key}" title="${escHtml(t.label)}のガイドを表示">${escHtml(t.abbr)}</button></th>`
  ).join('');

  // ---- 技法凡例 ----
  const legend = TECH_META.map(t => {
    const text = t.abbr === t.label ? t.label : `${t.abbr} = ${t.label}`;
    return `<span class="tech-legend-item"><span class="tech-legend-dot" data-tech="${t.key}"></span>${escHtml(text)}</span>`;
  }).join('');

  resultHero.innerHTML =
    '<div id="tech-guide-panel" class="tech-guide-panel" aria-hidden="true">' +
    '<div class="tech-guide-header"><span id="tech-guide-title" class="tech-guide-name"></span><button type="button" class="tech-guide-close" aria-label="閉じる">✕</button></div>' +
    '<div id="tech-guide-body" class="tech-guide-body"></div>' +
    '</div>' +
    '<div class="hero-pad">' +
    '<div class="hero-section-title design-section-title">テスト設計技法マトリクス</div>' +
    '<p class="design-section-note">技法列ヘッダーをクリックすると使い方ガイドが表示されます。バッジにカーソルを当てると推奨理由が確認できます。</p>' +
    `<div class="design-matrix-wrap"><table class="ov-screens design-matrix"><thead><tr><th>画面</th><th>タイトル</th>${matrixHead}</tr></thead><tbody>${matrixRows}</tbody></table></div>` +
    '<div class="hero-section-title">技法凡例</div>' +
    `<div class="tech-legend">${legend}</div>` +
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

  const detailCards = screens.map(sc => {
    const rec = _recommendFor(sc);
    const keys = Object.keys(rec);
    if (!keys.length) return `
      <div class="design-card">
        <div class="design-card-head">${escHtml(sc.page_id)} <span class="design-card-title">${escHtml(sc.title || '')}</span></div>
        <p class="design-card-none">フォームも遷移もないページのため、技法の推奨なし</p>
      </div>`;

    const badges = keys.map(k => {
      const t = TECH_META.find(x => x.key === k);
      return techBadgeHtml(k, t.label);
    }).join('');

    const rationale = keys.map(k => {
      const t = TECH_META.find(x => x.key === k);
      const reasons = rec[k];
      const stub = _tcStub(k, sc);
      return `<div class="design-rationale">
        <div class="design-rationale-title" data-tech="${k}">${escHtml(t.label)}</div>
        <ul class="design-rationale-list">
          ${reasons.map(r => `<li>${r}</li>`).join('')}
        </ul>
        ${stub ? `<div class="tc-stub-wrap"><div class="tc-stub-label">テストケース雛形</div><pre class="tc-stub">${escHtml(stub)}</pre><button type="button" class="tc-copy-btn" onclick="navigator.clipboard.writeText(this.previousElementSibling.textContent)" title="コピー">コピー</button></div>` : ''}
      </div>`;
    }).join('');

    return `
      <div class="design-card">
        <div class="design-card-head">
          ${escHtml(sc.page_id)}
          <span class="design-card-title"> ${escHtml(sc.title || '')}</span>
          <code class="design-card-url">${escHtml(sc.url || '')}</code>
        </div>
        <div class="design-card-badges">${badges}</div>
        <div class="design-card-body">${rationale}</div>
      </div>`;
  }).join('');

  resultHero.innerHTML =
    '<div class="hero-pad">' +
    '<div class="hero-section-title">画面別 推奨技法と根拠</div>' +
    '<p class="design-section-note">各画面の要素（フィールド種別・制約・選択肢数・遷移構造）から動的に導出した推奨技法と根拠です。</p>' +
    detailCards +
    '</div>';
}

// ============================================================
// カバレッジヒートマップ（解析＝取得状況3色 / AutoRun＝実行回数×成否）
// ============================================================
let _covHeatToken = 0;
function renderCoverageHeatmap() {
  const host = resultHero;
  const domain = (document.getElementById('r-domain') || {}).textContent.trim();
  host.innerHTML =
    '<div class="hero-pad">' +
    '<div class="hero-section-title">カバレッジヒートマップ</div>' +
    '<p class="design-section-note">解析＝画面の取得状況（取得済み／要ログイン／未取得）、AutoRun＝画面ごとの実行回数×成否。</p>' +
    '<div class="cov-mode" style="margin:6px 0 12px;font-size:13px">' +
    '<label style="margin-right:14px"><input type="radio" name="cov-kind" value="analysis" checked> 解析カバレッジ</label>' +
    '<label><input type="radio" name="cov-kind" value="autorun"> AutoRunカバレッジ</label></div>' +
    '<div class="tl-diff-frame" id="cov-frame"></div>' +
    '</div>';
  const load = () => _loadCoverageHeatmap(domain);
  document.querySelectorAll('input[name=cov-kind]').forEach(el => el.addEventListener('change', load));
  load();
}
async function _loadCoverageHeatmap(domain) {
  const box = document.getElementById('cov-frame');
  if (!box) return;
  const kind = (document.querySelector('input[name=cov-kind]:checked') || {}).value || 'analysis';
  const myToken = ++_covHeatToken;
  uiSkeleton(box, 'table');
  let html = '';
  try {
    const res = await fetch(`/api/coverage-heatmap?domain=${encodeURIComponent(domain)}&kind=${kind}`);
    html = await res.text();
    if (!res.ok) throw new Error(`サーバーエラー（HTTP ${res.status}）`);
  } catch (e) {
    if (myToken !== _covHeatToken) return;
    uiError(box, {
      title: 'ヒートマップの取得に失敗しました',
      message: e && e.message ? e.message : '通信エラー',
      onRetry: () => _loadCoverageHeatmap(domain),
    });
    return;
  }
  if (myToken !== _covHeatToken) return;
  box.replaceChildren();
  const iframe = document.createElement('iframe');
  iframe.title = kind === 'autorun' ? 'AutoRunカバレッジヒートマップ' : '解析カバレッジヒートマップ';
  iframe.srcdoc = html;
  box.appendChild(iframe);
}

// ============================================================
// 技法別設計（MBT）: 技法チップ → 対象画面 → モーダル（BVA/DT/PW/ST＋根拠）
// ============================================================
const MBT_TECH_META = [
  { key: 'bva', label: '境界値分析' },
  { key: 'dt', label: 'デシジョンテーブル' },
  { key: 'pw', label: 'ペアワイズ' },
  { key: 'st', label: '状態遷移' },
];
let _mbtDesign = null;
async function renderMbtDesign() {
  const host = resultHero;
  const domain = (document.getElementById('r-domain') || {}).textContent.trim();
  host.innerHTML =
    '<div class="hero-pad">' +
    '<div class="hero-section-title">技法別設計（MBT）</div>' +
    '<p class="design-section-note">設定「テスト設計」タブのパラメータで、各画面の境界値／デシジョンテーブル／ペアワイズ／状態遷移を機械生成します（実測＝確信度1.0、値カタログ＝0.9）。</p>' +
    '<div id="mbt-body"></div></div>';
  const body = document.getElementById('mbt-body');
  uiSkeleton(body, 'table');
  try {
    const res = await fetch('/api/test-design?domain=' + encodeURIComponent(domain));
    if (!res.ok) throw new Error(`サーバーエラー（HTTP ${res.status}）`);
    _mbtDesign = await res.json();
  } catch (e) {
    uiError(body, {
      title: 'テスト設計の生成に失敗しました',
      message: e && e.message ? e.message : '通信エラー',
      onRetry: renderMbtDesign,
    });
    return;
  }
  _renderMbtChips('bva');
}
function _mbtScreensWith(tech) {
  const screens = (_mbtDesign && _mbtDesign.screens) || [];
  return screens.filter(sc => {
    if (tech === 'bva') return (sc.bva || []).length > 0;
    if (tech === 'dt') return !!sc.decision_table;
    if (tech === 'pw') return !!sc.pairwise;
    if (tech === 'st') return !!sc.state_transitions;
    return false;
  });
}
function _renderMbtChips(active) {
  const body = document.getElementById('mbt-body');
  if (!body) return;
  const p = (_mbtDesign && _mbtDesign.params) || {};
  const chips = MBT_TECH_META.map(t => {
    const n = _mbtScreensWith(t.key).length;
    const on = t.key === active ? ' is-active' : '';
    return `<button type="button" class="mbt-chip${on}" data-tech="${t.key}">${escHtml(t.label)} <span class="mbt-chip-n">${n}</span></button>`;
  }).join('');
  const list = _mbtScreensWith(active).map(sc =>
    `<button type="button" class="mbt-screen-row" data-pid="${escHtml(sc.page_id)}" data-tech="${active}"><code>${escHtml(sc.page_id)}</code> ${escHtml(sc.title || '')}</button>`
  ).join('') || '<p class="design-card-none">この技法の対象画面はありません（該当する要素・制約・遷移が検出されませんでした）。</p>';
  body.innerHTML =
    `<div class="mbt-params">パラメータ: 境界オフセット=${escHtml(String(p.bva_offset ?? 1))} / ペアワイズ強度=${escHtml(String(p.pairwise_strength ?? 2))}-way / Nスイッチ=${escHtml(String(p.n_switch ?? 0))} / DT最大条件=${escHtml(String(p.max_dt_conditions ?? 4))}</div>` +
    `<div class="mbt-chips">${chips}</div>` +
    `<div class="mbt-screen-list">${list}</div>`;
  body.querySelectorAll('.mbt-chip').forEach(b => b.addEventListener('click', () => _renderMbtChips(b.dataset.tech)));
  body.querySelectorAll('.mbt-screen-row').forEach(b => b.addEventListener('click', () => _openMbtModal(b.dataset.pid, b.dataset.tech)));
}
function _mbtConfBadge(conf) {
  const measured = Number(conf) >= 1.0;
  return `<span class="mbt-badge ${measured ? 'is-measured' : 'is-catalog'}">${measured ? '実測 1.0' : 'カタログ ' + conf}</span>`;
}
function _mbtModalBody(sc, tech) {
  if (tech === 'bva') {
    return (sc.bva || []).map(tb => {
      const rows = tb.cases.map(c =>
        `<tr><td>${escHtml(c.label)}</td><td><code>${escHtml(c.value || '（空）')}</code></td><td>${escHtml(c.expected)}</td><td>${_mbtConfBadge(c.confidence)}</td></tr>`
      ).join('');
      return `<h4 class="mbt-h4">${escHtml(tb.field_name)} <small>(${escHtml(tb.field_type)})</small></h4>` +
        `<table class="ov-screens mbt-table"><thead><tr><th>ラベル</th><th>値</th><th>期待</th><th>根拠</th></tr></thead><tbody>${rows}</tbody></table>`;
    }).join('');
  }
  if (tech === 'dt') {
    const dt = sc.decision_table; if (!dt) return '';
    const head = dt.conditions.map(c => `<th>${escHtml(c)}</th>`).join('');
    const rows = dt.rules.map(r => `<tr>${r.conditions.map(b => `<td>${b ? '○' : '✗'}</td>`).join('')}<td>${escHtml(r.action)}</td></tr>`).join('');
    return `<p class="mbt-note">必須条件の全組み合わせ ${_mbtConfBadge(dt.confidence)}</p>` +
      `<table class="ov-screens mbt-table"><thead><tr>${head}<th>アクション（期待）</th></tr></thead><tbody>${rows}</tbody></table>`;
  }
  if (tech === 'pw') {
    const pw = sc.pairwise; if (!pw) return '';
    const head = pw.params.map(p => `<th>${escHtml(p.name)}</th>`).join('');
    const rows = pw.rows.map(row => `<tr>${row.map(v => `<td>${escHtml(v)}</td>`).join('')}</tr>`).join('');
    return `<p class="mbt-note">${pw.strength}-way 網羅・${pw.rows.length}行 ${_mbtConfBadge(pw.confidence)}</p>` +
      `<table class="ov-screens mbt-table"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table>`;
  }
  if (tech === 'st') {
    const st = sc.state_transitions; if (!st) return '';
    const seqs = st.sequences.map(s => `<li>${s.steps.map(x => escHtml(x)).join(' → ')}</li>`).join('');
    return `<p class="mbt-note">${st.n_switch}-スイッチ・${st.sequences.length}系列 ${_mbtConfBadge(st.confidence)}</p><ol class="mbt-seq">${seqs}</ol>`;
  }
  return '';
}
function _openMbtModal(pid, tech) {
  const sc = ((_mbtDesign && _mbtDesign.screens) || []).find(s => s.page_id === pid);
  if (!sc) return;
  const label = (MBT_TECH_META.find(t => t.key === tech) || {}).label || tech;
  const overlay = document.createElement('div');
  overlay.className = 'mbt-modal-overlay';
  overlay.setAttribute('style', 'position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:9999;padding:20px');
  overlay.innerHTML =
    '<div class="mbt-modal" role="dialog" aria-modal="true" aria-label="' + escHtml(label) + ' 設計" ' +
    'style="background:var(--surface,#fff);color:var(--text,#1b2027);max-width:760px;width:100%;max-height:85vh;overflow:auto;border-radius:12px;padding:20px;box-shadow:0 12px 40px rgba(0,0,0,.4)">' +
    '<div class="mbt-modal-head" style="display:flex;justify-content:space-between;align-items:center;gap:12px">' +
    '<strong>' + escHtml(sc.page_id) + ' — ' + escHtml(label) + '</strong>' +
    '<button type="button" class="mbt-modal-close" aria-label="閉じる" style="border:0;background:transparent;font-size:20px;cursor:pointer;color:inherit">✕</button></div>' +
    '<div class="mbt-modal-title" style="color:var(--text-muted,#5c6773);font-size:13px;margin:2px 0 12px">' + escHtml(sc.title || '') + '</div>' +
    '<div class="mbt-modal-body">' + _mbtModalBody(sc, tech) + '</div></div>';
  const close = () => overlay.remove();
  overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
  overlay.querySelector('.mbt-modal-close').addEventListener('click', close);
  document.addEventListener('keydown', function onKey(e) { if (e.key === 'Escape') { close(); document.removeEventListener('keydown', onKey); } });
  document.body.appendChild(overlay);
}

