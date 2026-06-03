
const SETTINGS_KEY = 'webspec2doc.settings';
const VIEW_HEADER = {
  dashboard: { trail: ['ダッシュボード'], title: '監視対象サイト' },
  generate: { trail: ['ダッシュボード', 'サイトを追加'], title: 'サイトを追加 / 再クロール' },
  'qa-process': { trail: ['ダッシュボード', 'QAプロセス'], title: 'QAプロセス' },
  'qa-models': { trail: ['ダッシュボード', 'モデル/カバレッジ'], title: 'モデル/カバレッジ' },
  'qa-automation': { trail: ['ダッシュボード', '自動テスト候補'], title: '自動テスト候補' },
  'qa-quality': { trail: ['ダッシュボード', '品質観点'], title: '品質観点' },
  'auto-run': { trail: ['ダッシュボード', 'AutoRun'], title: 'AutoRun — 全自動テスト実行' },
  'user-guide': { trail: ['ダッシュボード', 'ユーザーガイド'], title: 'ユーザーガイド' },
  settings: { trail: ['ダッシュボード', '設定'], title: '設定' },
};
const escHtml = (s) => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// ---- ヘッダー（パンくず＋タイトル）----
function setHeader(trail, title) {
  const bc = document.getElementById('topbar-breadcrumb');
  bc.innerHTML = trail.map((t, i) => i === 0
    ? `<a data-bc-root="1">${escHtml(t)}</a>`
    : `<span class="sep">›</span><span>${escHtml(t)}</span>`).join('');
  const root = bc.querySelector('[data-bc-root]');
  if (root && trail.length > 1) root.addEventListener('click', () => switchView('dashboard'));
  document.getElementById('topbar-title').textContent = title;
  document.getElementById('topbar-actions').innerHTML = '';
}

// ---- ナビ切替 ----
document.querySelectorAll('.app-nav-item').forEach(btn => btn.addEventListener('click', () => switchView(btn.dataset.view)));
function switchView(name) {
  document.querySelectorAll('.app-nav-item').forEach(b => b.classList.toggle('is-active', b.dataset.view === name));
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('is-active', v.id === 'view-' + name));
  const h = VIEW_HEADER[name];
  if (h) setHeader(h.trail, h.title);
  if (name === 'dashboard') loadHistory();
  if (name === 'qa-process') loadQaProcessSites();
  if (['qa-models', 'qa-automation', 'qa-quality'].includes(name)) loadQaToolSites(name);
  // A: 2ペインツール画面では全高モードに切り替え
  const appContentEl = document.getElementById('app-content');
  if (appContentEl) appContentEl.classList.toggle('is-qa-tool', ['qa-models', 'qa-automation', 'qa-quality', 'auto-run'].includes(name));
  // レポートモード解除（generate以外に遷移した時）
  if (name !== 'generate') {
    if (appContentEl) appContentEl.classList.remove('is-reporting');
    const shell = document.querySelector('.app-shell');
    if (shell) shell.classList.remove('is-reporting');
  }
}
// ---- ウィザード ステップ管理 ----
function showWizardStep(n) {
  const p1 = document.getElementById('wizard-p1');
  const p2 = document.getElementById('wizard-p2');
  const bar = document.getElementById('wizard-progress-bar');
  if (p1) p1.style.display = (n === 1) ? '' : 'none';
  if (p2) p2.style.display = (n === 2) ? '' : 'none';
  if (bar) bar.style.display = (n === 4) ? 'none' : '';
  [1, 2, 3, 4].forEach(i => {
    const node = document.getElementById('ws-' + i);
    if (!node) return;
    node.classList.toggle('is-active', i === n);
    node.classList.toggle('is-done', i < n);
  });
  [1, 2, 3].forEach(i => {
    const line = document.getElementById('wl-' + i);
    if (line) line.classList.toggle('is-done', i < n);
  });
}

// 「+ サイトを追加」: 新規ウィザードを開く（P1から）
function openAddSite() {
  switchView('generate');
  executionView.classList.add('hidden'); resultPanel.classList.add('hidden');
  appContent.classList.remove('is-executing', 'is-reporting');
  const _shell = document.querySelector('.app-shell');
  if (_shell) _shell.classList.remove('is-reporting');
  genPanel.style.display = '';
  document.getElementById('url-input').value = '';
  document.getElementById('p1-summary').style.display = 'none';
  clearDiscovered(); updateTargetPreview(); showWizardStep(1);
}
document.getElementById('add-site-btn').addEventListener('click', openAddSite);
document.getElementById('add-site-btn-2').addEventListener('click', openAddSite);

// P1 → P2: 「次へ」ボタン
document.getElementById('p1-next-btn').addEventListener('click', () => {
  showWizardStep(2);
  // 画面リストと必要なら認証パネルを表示
  if (discovered.length) {
    document.getElementById('discovered-url-panel').style.display = '';
    updateTargetPreview();
  }
});

// P2 → P1: 「解析に戻る」ボタン
document.getElementById('p2-back-btn').addEventListener('click', () => {
  showWizardStep(1);
});

