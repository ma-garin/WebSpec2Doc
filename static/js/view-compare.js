// ---- 現新比較ワークスペース ----
// 従来は comparison.html を iframe に埋めるだけで、画面ペアを選ぶ・差分を辿る・
// 根拠を見る、が画面上でできなかった。ここでその一連の操作を担う。
// データは GET /api/snapshot-comparison.json（ペア単位に整形済み）。

const CMP_CATEGORY_LABELS = {
  inoperable: '操作不可',
  incomprehensible: '理解不可能',
  text_garbled: '文字化け・意味消失',
  layout_broken: '表示崩れ',
  unclassified: '未分類（要確認）',
};
const CMP_SEVERITY_LABELS = { high: '高', medium: '中', low: '低' };
// 比較できなかった画面。「指摘0件」と同じ見た目にしない。
const CMP_STATE_LABELS = { added: '追加', removed: '削除' };

const CMP = {
  domain: '',
  snapshots: [],
  from: '',
  to: '',
  data: null,
  selected: 0,      // 選択中のペア index
  filter: 'all',    // all | high | <category>
  loading: false,
};

function cmpPanel() { return document.getElementById('rp-compare'); }

// ---- 入口（results.js のタブ登録から呼ばれる） ----
// 描画関数は引数なしで呼ばれる規約（results.js:322-324）。ドメインは
// renderTimeline と同じく #r-domain から取る。
async function renderCompare() {
  const domain = document.getElementById('r-domain')?.textContent?.trim() || '';
  const panel = cmpPanel();
  if (!panel) return;
  if (!domain) {
    panel.innerHTML = '<div class="hero-msg">対象サイトが特定できませんでした。</div>';
    return;
  }
  // ドメインが変わったら前回の選択を持ち越さない（別サイトの2時点が残る）
  if (CMP.domain !== domain) { CMP.from = ''; CMP.to = ''; CMP.data = null; }
  CMP.domain = domain;
  panel.innerHTML = '<div class="hero-msg">スナップショットを読み込んでいます…</div>';
  try {
    const data = await fetch('/api/snapshots?domain=' + encodeURIComponent(domain)).then(r => r.json());
    // API は新しい順の {id, label, screens, ...}。古い順に直して「1つ前 → 最新」を既定にする。
    CMP.snapshots = (data.snapshots || []).slice().reverse();
  } catch (e) {
    panel.innerHTML = '<div class="hero-msg">スナップショット一覧を取得できませんでした。</div>';
    return;
  }
  if (CMP.snapshots.length < 2) {
    // 何が足りないかを書く。「比較できません」だけだと次に何をすればよいか分からない。
    panel.innerHTML = '<div class="hero-msg">比較には2時点以上のスナップショットが必要です。' +
      `現在 ${CMP.snapshots.length} 件です。再解析すると1件増えます。</div>`;
    return;
  }
  const last = CMP.snapshots.length - 1;
  CMP.from = CMP.from || CMP.snapshots[last - 1].id;
  CMP.to = CMP.to || CMP.snapshots[last].id;
  await cmpLoad();
}

async function cmpLoad() {
  const panel = cmpPanel();
  if (!panel || CMP.loading) return;
  CMP.loading = true;
  panel.innerHTML = '<div class="hero-msg">比較しています…（画面数によっては時間がかかります）</div>';
  try {
    const url = `/api/snapshot-comparison.json?domain=${encodeURIComponent(CMP.domain)}` +
      `&from=${encodeURIComponent(CMP.from)}&to=${encodeURIComponent(CMP.to)}`;
    const res = await fetch(url);
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || '比較に失敗しました');
    CMP.data = data;
    CMP.selected = 0;
    cmpRender();
  } catch (e) {
    panel.innerHTML = `<div class="hero-msg">比較に失敗しました: ${escHtml(e.message || e)}</div>`;
  } finally {
    CMP.loading = false;
  }
}

// ---- 描画 ----
function cmpRender() {
  const panel = cmpPanel();
  if (!panel || !CMP.data) return;
  panel.innerHTML =
    '<section class="cmp-card">' +
      cmpHead() +
      '<div class="cmp-layout">' + cmpRail() + cmpMain() + '</div>' +
    '</section>';
  cmpBind();
}

function cmpHead() {
  const c = CMP.data.counts || {};
  return '<header class="cmp-head">' +
    '<h3>現新比較</h3>' +
    '<p class="cmp-lede">画面対応・画面差分・仕様差分を同じ根拠で確認します。' +
    '比較できない対象は未確認として残します。</p>' +
    '<div class="cmp-context">' +
      `<b>比較対象</b><span class="cmp-date">${escHtml(CMP.data.from)}</span>` +
      '<span class="cmp-arrow">→</span>' +
      `<span class="cmp-date">${escHtml(CMP.data.to)}</span>` +
      `<span class="cmp-context-sum">対応 ${c.matched || 0} / ${c.pairs || 0}　` +
      `追加 ${c.added || 0}　削除 ${c.removed || 0}　指摘 ${c.findings || 0}</span>` +
      '<button type="button" class="btn-outline-sm" id="cmp-change-btn">比較条件を変更</button>' +
    '</div>' +
  '</header>';
}

function cmpRail() {
  const pairs = CMP.data.pairs || [];
  const rows = pairs.map((p, i) => {
    const badge = p.state === 'matched'
      ? (p.finding_count
        ? `<span class="cmp-badge cmp-cat-${escHtml(p.top_category)}">` +
          `${escHtml(CMP_CATEGORY_LABELS[p.top_category] || p.top_category)}</span>`
        : '<span class="cmp-badge cmp-none">変更なし</span>')
      : `<span class="cmp-badge cmp-unmatched">${escHtml(CMP_STATE_LABELS[p.state] || p.state)}</span>`;
    return `<button type="button" class="cmp-pair${i === CMP.selected ? ' is-active' : ''}" data-cmp-pair="${i}">` +
      `<span class="cmp-pair-title">${escHtml(p.title || p.old_page_id || p.new_page_id)}</span>` +
      `<span class="cmp-pair-url">${escHtml(p.url || '—')}</span>${badge}</button>`;
  }).join('');
  return '<aside class="cmp-rail">' +
    `<div class="cmp-rail-head">画面対応<span>${pairs.length} 件</span></div>` +
    `<div class="cmp-rail-list">${rows}</div></aside>`;
}

function cmpMain() {
  const pair = (CMP.data.pairs || [])[CMP.selected];
  if (!pair) return '<section class="cmp-main"><div class="hero-msg">画面を選択してください。</div></section>';
  if (pair.state !== 'matched') {
    return '<section class="cmp-main"><div class="cmp-unmatched-pane">' +
      `<p><b>${escHtml(CMP_STATE_LABELS[pair.state] || pair.state)}</b>: ${escHtml(pair.title)}</p>` +
      `<p class="cmp-note">${escHtml(pair.unmatched_reason || '比較対象がありません')}</p>` +
      '</div></section>';
  }
  return '<section class="cmp-main">' + cmpFilters(pair) + cmpStage(pair) + cmpIssues(pair) + '</section>';
}

function cmpFilters(pair) {
  // 出す選択肢は、その画面に実在するものだけにする。
  // 空振りするフィルタを並べると、押しても何も起きない理由が分からない。
  const findings = pair.findings || [];
  if (!findings.length) return '';
  const btn = (key, label) =>
    `<button type="button" class="cmp-filter${CMP.filter === key ? ' is-active' : ''}"` +
    ` data-cmp-filter="${escHtml(key)}">${escHtml(label)}</button>`;
  const buttons = [btn('all', 'すべて')];
  if (findings.some(f => f.severity === 'high')) buttons.push(btn('high', '重要度 高'));
  [...new Set(findings.map(f => f.category))].forEach(c => {
    buttons.push(btn(c, CMP_CATEGORY_LABELS[c] || c));
  });
  return `<div class="cmp-filters">${buttons.join('')}</div>`;
}

function cmpMatchesFilter(finding) {
  if (CMP.filter === 'all') return true;
  if (CMP.filter === 'high') return finding.severity === 'high';
  return finding.category === CMP.filter;
}

function cmpStage(pair) {
  const s = pair.screenshots || {};
  const afterSrc = s.diff || s.after;
  const note = s.same_capture
    ? '<p class="cmp-warn">この2時点は同じキャプチャを指しています（世代別の画像が保存される前に取得されたスナップショットです）。' +
      '画像の比較はできません。再解析すると次回から比較できます。</p>'
    : '';
  if (!s.before && !s.after) {
    return '<div class="cmp-stage"><p class="cmp-note">この画面のキャプチャは取得されていません（未確認）。</p></div>';
  }
  return '<div class="cmp-stage">' + note +
    '<div class="cmp-split">' +
      cmpShot('現行', CMP.data.from, s.before) +
      cmpShot(s.diff ? '新（変更箇所を赤枠）' : '新', CMP.data.to, afterSrc) +
    '</div>' +
    `<p class="cmp-metrics">変化 ${((s.diff_ratio || 0) * 100).toFixed(1)}%` +
    ` / SSIM ${(s.structural_similarity != null ? s.structural_similarity : 1).toFixed(2)}` +
    `${s.is_significant ? '' : '（有意差なし）'}</p>` +
  '</div>';
}

function cmpShot(caption, stamp, src) {
  const body = src
    ? `<img src="/preview?path=${encodeURIComponent(src)}" alt="${escHtml(caption)}" loading="lazy">`
    : '<div class="cmp-shot-missing">キャプチャなし</div>';
  return '<figure class="cmp-shot">' +
    `<figcaption>${escHtml(caption)}<span>${escHtml(stamp || '')}</span></figcaption>` +
    `<div class="cmp-shot-body">${body}</div></figure>`;
}

function cmpIssues(pair) {
  const items = (pair.findings || []).filter(cmpMatchesFilter);
  if (!items.length) {
    return (pair.findings || []).length
      ? '<p class="cmp-note">この絞り込みに該当する指摘はありません。</p>'
      : '<p class="cmp-note">この画面に指摘はありません。</p>';
  }
  const rows = items.map(f =>
    `<button type="button" class="cmp-issue" data-cmp-issue="${f.index}">` +
    `<span class="cmp-badge cmp-cat-${escHtml(f.category)}">${escHtml(CMP_CATEGORY_LABELS[f.category] || f.category)}</span>` +
    `<span class="cmp-sev">${escHtml(CMP_SEVERITY_LABELS[f.severity] || f.severity || '')}</span>` +
    `<span class="cmp-issue-detail">${escHtml(f.detail || '')}</span></button>`).join('');
  return `<div class="cmp-issues">${rows}</div>`;
}

// ---- 操作 ----
function cmpBind() {
  const panel = cmpPanel();
  if (!panel) return;
  panel.querySelectorAll('[data-cmp-pair]').forEach(b => {
    b.addEventListener('click', () => {
      CMP.selected = Number(b.dataset.cmpPair);
      CMP.filter = 'all';  // 画面が変われば分類の顔ぶれも変わる
      cmpRender();
    });
  });
  panel.querySelectorAll('[data-cmp-filter]').forEach(b => {
    b.addEventListener('click', () => { CMP.filter = b.dataset.cmpFilter; cmpRender(); });
  });
}
