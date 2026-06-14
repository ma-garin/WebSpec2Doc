// ====================== 結果ページ（QAビュー軸） ======================
const resultPanel = document.getElementById('result-panel');
const resultHero = document.getElementById('result-hero');
const VIEW_MODE_KEY = 'wsd_view_mode';
// テスト技法（設計・技法詳細）は本製品の中核成果物のため、概要モードでも常に表示する。
// 概要モードで隠すのは補助的な詳細タブ（遷移表・履歴/差分）のみ。
const SUMMARY_HIDE_TABS = new Set(['transition-table', 'history']);
const EXPORT_DEFS = [
  { key: 'html', label: 'HTMLレポート', desc: 'テスト分析インプット文書（画面別カード＋テスト条件）' },
  { key: 'pdf', label: 'PDF', desc: '配布・印刷用（HTMLレポートのPDF版）' },
  { key: 'screens_md', label: 'Markdown（画面一覧）', desc: 'screens.md' },
  { key: 'forms_md', label: 'Markdown（フォーム）', desc: 'forms.md' },
  { key: 'excel', label: 'Excel', desc: 'spec.xlsx（表計算で編集）' },
  { key: 'json', label: 'JSON（機械可読）', desc: '自動化・連携用の構造化データ' },
  { key: 'diff', label: '差分レポート', desc: '前回スナップショットとの差分' },
];
let resultData = null, reportJson = null, activeResultTab = 'overview';

async function showResults(domain) {
  let data;
  try {
    const res = await fetch('/api/result?domain=' + encodeURIComponent(domain));
    data = await res.json();
    if (!res.ok) throw new Error(data.error || '結果の取得に失敗しました');
  } catch (e) {
    // 実行ビューが隠れている（履歴から開いた）場合は結果領域にエラーを表示
    executionView.classList.add('hidden'); resultPanel.classList.remove('hidden');
    appContent.classList.add('is-executing');
    setHeader(['ダッシュボード', domain], domain);
    resultHero.innerHTML = `<div class="hero-msg"><p>結果の取得に失敗しました。</p><p style="font-size:13px;color:var(--text-muted)">${escHtml(e.message)}</p></div>`;
    return;
  }
  resultData = data;
  reportJson = null;
  if (data.files && data.files.json) {
    try { reportJson = await fetch('/preview?path=' + encodeURIComponent(data.files.json)).then(r => r.json()); } catch (e) {}
  }
  const s = data.summary || {};
  const required = reportJson ? countRequired(reportJson) : 0;
  const crawledAt = reportJson && reportJson.meta ? reportJson.meta.crawled_at : '';
  document.getElementById('r-crawled').textContent = crawledAt ? ('最終クロール: ' + crawledAt) : '';
  document.getElementById('r-domain').textContent = domain;
  document.getElementById('r-screens').textContent = s.screens || 0;
  document.getElementById('r-forms').textContent = s.forms || 0;
  document.getElementById('r-fields').textContent = s.fields || 0;
  document.getElementById('r-required').textContent = required;
  document.getElementById('r-buttons').textContent = s.buttons || 0;

  // 差分バッジ（DOM APIで構築 — innerHTML を使わない）
  const diffBadge = document.getElementById('r-diff-badge');
  if (diffBadge) {
    const hasDiff = data.files && data.files.diff;
    diffBadge.replaceChildren();
    if (hasDiff) {
      const span = document.createElement('span');
      span.className = 'diff-badge';
      span.style.cursor = 'pointer';
      span.title = '履歴・差分タブを開く';
      span.textContent = '差分あり';
      span.addEventListener('click', () => selectResultTab('history'));
      diffBadge.appendChild(span);
      diffBadge.style.display = '';
    } else {
      diffBadge.style.display = 'none';
    }
  }

  // タブ件数バッジ
  const screenCount = s.screens || 0;
  const fieldCount = s.fields || 0;
  const snapCount = data.snapshot_count || 0;
  const setTabCount = (id, n) => { const el = document.getElementById(id); if (el) el.textContent = n > 0 ? ` ${n}` : ''; };
  setTabCount('tab-count-report', screenCount);
  setTabCount('tab-count-matrix', fieldCount);
  setTabCount('tab-count-history', snapCount);

  setHeader(['ダッシュボード', domain], domain);

  executionView.classList.add('hidden'); resultPanel.classList.remove('hidden');
  appContent.classList.add('is-reporting');
  _buildExportDropdown(data);
  showWizardStep(4);
  selectResultTab('overview');
}

function _buildExportDropdown(data) {
  const menu = document.getElementById('export-dropdown-menu');
  if (!menu) return;
  const files = (data && data.files) || {};
  const domain = (document.getElementById('r-domain') || {}).textContent || '';
  const defs = [
    { key: 'html', label: 'HTMLレポート' },
    { key: 'pdf', label: 'PDF' },
    { key: 'json', label: 'JSON' },
    { key: 'excel', label: 'Excel' },
    { key: 'screens_md', label: 'Markdown（画面一覧）' },
    { key: 'forms_md', label: 'Markdown（フォーム）' },
    { key: 'transition_mmd', label: '遷移図（Mermaid）' },
    { key: 'diff', label: '差分レポート' },
  ];
  const zipRow = `<div class="export-dropdown-item is-zip"><span>すべてZIPでダウンロード</span><a href="/download-zip?domain=${encodeURIComponent(domain)}" class="btn-primary" style="height:28px;padding:0 10px;font-size:12px">DL</a></div>`;
  const fileRows = defs.map(d => {
    if (files[d.key]) {
      return `<div class="export-dropdown-item"><span>${escHtml(d.label)}</span><div style="display:flex;gap:4px"><a href="/preview?path=${encodeURIComponent(files[d.key])}" target="_blank" class="btn-outline-sm" style="height:28px;padding:0 8px;font-size:12px">開く</a><a href="/download?path=${encodeURIComponent(files[d.key])}" class="btn-outline-sm" style="height:28px;padding:0 8px;font-size:12px" download>DL</a></div></div>`;
    }
    return `<div class="export-dropdown-item is-missing"><span>${escHtml(d.label)}（未生成）</span></div>`;
  }).join('');
  menu.innerHTML = zipRow + fileRows;
}

// エクスポートドロップダウンの開閉
document.getElementById('export-dropdown-btn').addEventListener('click', (e) => {
  e.stopPropagation();
  document.getElementById('export-dropdown').classList.toggle('is-open');
});
document.addEventListener('click', () => {
  const dd = document.getElementById('export-dropdown');
  if (dd) dd.classList.remove('is-open');
});

document.querySelectorAll('.result-tab').forEach(t => {
  t.addEventListener('click', () => selectResultTab(t.dataset.tab));
  t.addEventListener('keydown', e => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const tabs = [...document.querySelectorAll('.result-tab')].filter(x => x.offsetParent !== null);
    const i = tabs.indexOf(t);
    const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
    if (next) { selectResultTab(next.dataset.tab); next.focus(); }
  });
});
function selectResultTab(tab) {
  activeResultTab = tab;
  document.querySelectorAll('.result-tab').forEach(t => {
    const on = t.dataset.tab === tab;
    t.classList.toggle('is-active', on);
    t.setAttribute('aria-selected', on ? 'true' : 'false');
    t.tabIndex = on ? 0 : -1;
  });
  if (tab === 'overview') renderOverview();
  else if (tab === 'matrix') renderMatrix();
  else if (tab === 'report') renderReport();
  else if (tab === 'design') renderDesign();
  else if (tab === 'technique-detail') renderTechniqueDetail();
  else if (tab === 'transition') renderTransition();
  else if (tab === 'transition-table') renderTransitionTable();
  else if (tab === 'history') renderTimeline();
}

function applyViewMode(mode) {
  const selectedMode = mode === 'detail' ? 'detail' : 'summary';
  document.querySelectorAll('.result-tabs .result-tab[data-tab]').forEach(tab => {
    const hide = selectedMode === 'summary' && SUMMARY_HIDE_TABS.has(tab.dataset.tab);
    tab.style.display = hide ? 'none' : '';
    if (hide && tab.classList.contains('is-active')) {
      document.querySelector('.result-tab[data-tab="overview"]')?.click();
    }
  });
  document.getElementById('view-mode-summary')?.classList.toggle('is-active', selectedMode === 'summary');
  document.getElementById('view-mode-detail')?.classList.toggle('is-active', selectedMode === 'detail');
  try { localStorage.setItem(VIEW_MODE_KEY, selectedMode); } catch (_) {}
}

// ---- 履歴・差分（クロール履歴タイムライン＋任意2点の仕様ドリフト比較）----
let timelineDomain = '';
async function renderTimeline() {
  const domain = document.getElementById('r-domain').textContent.trim();
  timelineDomain = domain;
  resultHero.innerHTML = '<div class="hero-msg">クロール履歴を読み込み中…</div>';
  let snaps = [];
  try {
    const data = await fetch('/api/snapshots?domain=' + encodeURIComponent(domain)).then(r => r.json());
    snaps = data.snapshots || [];
  } catch (e) {}
  if (snaps.length < 2) {
    resultHero.innerHTML = '<div class="hero-pad"><div class="hero-section-title">クロール履歴</div>' +
      '<p style="color:var(--text-muted);font-size:13px">履歴が' + snaps.length + '件です。<strong>再クロール</strong>すると、前回との仕様ドリフト（追加/削除された画面・変更されたフォーム）を時系列で比較できます。</p>' +
      _ciGuidanceCard(domain) + '</div>';
    _bindCiCopy();
    return;
  }
  // 既定: to=最新(0), from=ひとつ前(1)
  const rows = snaps.map((s, i) => `
    <tr>
      <td style="text-align:center"><input type="radio" name="snap-from" value="${escHtml(s.id)}" ${i === 1 ? 'checked' : ''}></td>
      <td style="text-align:center"><input type="radio" name="snap-to" value="${escHtml(s.id)}" ${i === 0 ? 'checked' : ''}></td>
      <td>${escHtml(s.label)}${i === 0 ? ' <span class="tl-latest">最新</span>' : ''}</td>
      <td class="num">${s.screens}</td><td class="num">${s.forms}</td><td class="num">${s.fields}</td>
    </tr>`).join('');
  resultHero.innerHTML = '<div class="hero-pad">' +
    '<div class="hero-section-title">クロール履歴（' + snaps.length + '件）</div>' +
    '<p style="color:var(--text-muted);font-size:13px;margin-bottom:10px">比較する2時点を選び、仕様ドリフトを確認します（比較元＝古い／比較先＝新しい）。</p>' +
    '<table class="ov-screens tl-table"><thead><tr><th>比較元</th><th>比較先</th><th>クロール日時</th><th>画面</th><th>フォーム</th><th>入力項目</th></tr></thead><tbody>' +
    rows + '</tbody></table>' +
    '<div style="margin:12px 0"><button type="button" class="btn-primary" id="tl-diff-btn">この2時点の差分を表示</button></div>' +
    '<div class="tl-diff-frame" id="tl-diff"></div>' +
    _ciGuidanceCard(domain) + '</div>';
  document.getElementById('tl-diff-btn').addEventListener('click', showTimelineDiff);
  _bindCiCopy();
  showTimelineDiff();
}
function _bindCiCopy() {
  const btn = document.getElementById('ci-copy-btn');
  if (!btn) return;
  btn.addEventListener('click', () => {
    const cmd = document.getElementById('ci-cmd');
    if (!cmd) return;
    navigator.clipboard.writeText(cmd.textContent).then(() => {
      const orig = btn.textContent;
      btn.textContent = 'コピーしました';
      setTimeout(() => { btn.textContent = orig; }, 1500);
    }).catch(() => {});
  });
}
function _ciGuidanceCard(domain) {
  // CI連携先（Jenkins/GitHub Actions等）は顧客環境次第のため断定せず、中立的に提示する。
  const cmd = `python src/main.py --url https://${domain}/ --compare --fail-on-drift`;
  return '<div class="ci-guidance">' +
    '<div class="ci-guidance-title">⚙️ CI/CD で自動ドリフト検知</div>' +
    '<p style="font-size:12.5px;color:var(--text-muted);margin:4px 0 8px">' +
    '定期実行ジョブに組み込むと、前回から仕様ドリフトが出たとき <code>exit code 1</code> で失敗し、パイプラインを止められます。お使いのCIのジョブに以下を追加してください。</p>' +
    '<div class="ci-guidance-cmd"><code id="ci-cmd">' + escHtml(cmd) + '</code>' +
    '<button type="button" class="btn-outline-sm" id="ci-copy-btn">コピー</button></div></div>';
}

function showTimelineDiff() {
  const from = (document.querySelector('input[name=snap-from]:checked') || {}).value;
  const to = (document.querySelector('input[name=snap-to]:checked') || {}).value;
  const box = document.getElementById('tl-diff');
  if (!from || !to) { box.innerHTML = '<div class="hero-msg">2時点を選択してください。</div>'; return; }
  if (from === to) { box.innerHTML = '<div class="hero-msg">異なる2時点を選択してください。</div>'; return; }
  box.innerHTML = `<iframe src="/api/snapshot-diff?domain=${encodeURIComponent(timelineDomain)}&from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}" title="仕様ドリフト差分"></iframe>`;
}

// ====================== タブ最大化 ======================
function _toggleMaximize() {
  document.body.classList.toggle('result-maximized');
}

document.getElementById('r-maximize-btn')?.addEventListener('click', _toggleMaximize);
document.getElementById('view-mode-summary')?.addEventListener('click', () => applyViewMode('summary'));
document.getElementById('view-mode-detail')?.addEventListener('click', () => applyViewMode('detail'));
document.getElementById('r-maximize-exit-btn')?.addEventListener('click', () => {
  document.body.classList.remove('result-maximized');
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && document.body.classList.contains('result-maximized')) {
    document.body.classList.remove('result-maximized');
  }
});

// ====================== 完了ポップアップ ======================
function _showCompletionPopup(elapsedSec) {
  const overlay = document.getElementById('completion-overlay');
  const elapsedEl = document.getElementById('popup-elapsed');
  if (!overlay) return;
  const m = Math.floor(elapsedSec / 60);
  const s = elapsedSec % 60;
  elapsedEl.textContent = `${m}:${String(s).padStart(2, '0')}`;
  overlay.classList.remove('hidden');
}

document.getElementById('popup-close-btn').addEventListener('click', () => {
  document.getElementById('completion-overlay').classList.add('hidden');
});
document.getElementById('popup-view-report-btn').addEventListener('click', () => {
  document.getElementById('completion-overlay').classList.add('hidden');
  showResults(activeDomain);
});
document.getElementById('completion-overlay').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) document.getElementById('completion-overlay').classList.add('hidden');
});

(function initViewMode() {
  let saved = 'summary';
  try { saved = localStorage.getItem(VIEW_MODE_KEY) || 'summary'; } catch (_) {}
  applyViewMode(saved);
}());
