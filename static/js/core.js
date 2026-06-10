
const SETTINGS_KEY = 'webspec2doc.settings';
const SIDEBAR_KEY  = 'webspec2doc.sidebar-collapsed';

// ---- サイドバー折りたたみ（全画面共通・localStorage 永続） ----
function _applySidebarCollapsed(collapsed) {
  document.querySelector('.app-shell').classList.toggle('sidebar-collapsed', collapsed);
  const btn = document.getElementById('sidebar-toggle-btn');
  if (btn) btn.title = collapsed ? 'サイドバーを広げる' : 'サイドバーを折りたたむ';
}
_applySidebarCollapsed(localStorage.getItem(SIDEBAR_KEY) === '1');
document.getElementById('sidebar-toggle-btn')?.addEventListener('click', () => {
  const collapsed = !document.querySelector('.app-shell').classList.contains('sidebar-collapsed');
  _applySidebarCollapsed(collapsed);
  localStorage.setItem(SIDEBAR_KEY, collapsed ? '1' : '0');
});
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
  if (name !== 'generate' && appContentEl) appContentEl.classList.remove('is-reporting');
}
// ---- ウィザード ステップ管理 ----
function showWizardStep(n) {
  const p1 = document.getElementById('wizard-p1');
  const p2 = document.getElementById('wizard-p2');
  const bar = document.getElementById('wizard-progress-bar');
  if (p1) p1.style.display = (n === 1) ? '' : 'none';
  if (p2) p2.style.display = (n === 2) ? '' : 'none';
  // ステップ3（実行中）と4（レポート）ではウィザードバー不要（それぞれ専用UIあり）
  if (bar) bar.style.display = (n >= 3) ? 'none' : '';
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

// ---- テーマ（ライト/ダーク）切替・localStorage 永続 ----
const THEME_KEY = 'webspec2doc.theme';
function _applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  const btn = document.getElementById('theme-toggle-btn');
  if (btn) btn.title = theme === 'dark' ? 'ライトモードに切替' : 'ダークモードに切替';
}
_applyTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light');
document.getElementById('theme-toggle-btn')?.addEventListener('click', () => {
  const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  _applyTheme(next);
  try { localStorage.setItem(THEME_KEY, next); } catch (e) {}
});

// ---- トースト通知 ----
const TOAST_ICONS = { success: '✓', error: '⚠', info: 'ℹ' };
function showToast(message, type = 'info', duration = 3500) {
  const wrap = document.getElementById('toast-container');
  if (!wrap) return;
  const el = document.createElement('div');
  el.className = 'toast toast-' + (TOAST_ICONS[type] ? type : 'info');
  el.setAttribute('role', 'status');
  const icon = document.createElement('span');
  icon.className = 'toast-icon';
  icon.textContent = TOAST_ICONS[type] || TOAST_ICONS.info;
  const msg = document.createElement('span');
  msg.textContent = message;
  el.append(icon, msg);
  wrap.appendChild(el);
  requestAnimationFrame(() => el.classList.add('show'));
  setTimeout(() => {
    el.classList.remove('show');
    setTimeout(() => el.remove(), 300);
  }, duration);
}

// ---- 確認モーダル（confirm() 代替・Promise<boolean>）----
function confirmDialog({ title = '確認', message = '', confirmLabel = 'OK', danger = false } = {}) {
  return new Promise((resolve) => {
    const ov = document.getElementById('confirm-overlay');
    const okBtn = document.getElementById('confirm-ok-btn');
    const cancelBtn = document.getElementById('confirm-cancel-btn');
    if (!ov || !okBtn || !cancelBtn) { resolve(window.confirm(message)); return; }
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-message').textContent = message;
    okBtn.textContent = confirmLabel;
    okBtn.classList.toggle('btn-danger', !!danger);
    ov.classList.remove('hidden');
    const prevFocus = document.activeElement;
    cancelBtn.focus();
    const close = (result) => {
      ov.classList.add('hidden');
      okBtn.removeEventListener('click', onOk);
      cancelBtn.removeEventListener('click', onCancel);
      ov.removeEventListener('click', onOverlay);
      document.removeEventListener('keydown', onKey);
      if (prevFocus && typeof prevFocus.focus === 'function') prevFocus.focus();
      resolve(result);
    };
    const onOk = () => close(true);
    const onCancel = () => close(false);
    const onOverlay = (e) => { if (e.target === ov) close(false); };
    const onKey = (e) => { if (e.key === 'Escape') { e.stopPropagation(); close(false); } };
    okBtn.addEventListener('click', onOk);
    cancelBtn.addEventListener('click', onCancel);
    ov.addEventListener('click', onOverlay);
    document.addEventListener('keydown', onKey);
  });
}

// ---- キーボードショートカット（? でヘルプ / Alt+D / Alt+N）----
function toggleShortcutHelp(force) {
  const ov = document.getElementById('shortcut-overlay');
  if (!ov) return;
  const show = force !== undefined ? force : ov.classList.contains('hidden');
  ov.classList.toggle('hidden', !show);
}
document.getElementById('shortcut-help-btn')?.addEventListener('click', () => toggleShortcutHelp(true));
document.getElementById('shortcut-close-btn')?.addEventListener('click', () => toggleShortcutHelp(false));
document.getElementById('shortcut-overlay')?.addEventListener('click', (e) => {
  if (e.target === e.currentTarget) toggleShortcutHelp(false);
});
document.addEventListener('keydown', (e) => {
  const tag = (e.target.tagName || '').toLowerCase();
  const typing = ['input', 'textarea', 'select'].includes(tag) || e.target.isContentEditable;
  if (e.key === '?' && !typing && !e.altKey && !e.ctrlKey && !e.metaKey) {
    e.preventDefault(); toggleShortcutHelp();
  } else if (e.key === 'Escape') {
    toggleShortcutHelp(false);
  } else if (e.altKey && !e.ctrlKey && !e.metaKey && (e.key === 'd' || e.key === 'D')) {
    e.preventDefault(); switchView('dashboard');
  } else if (e.altKey && !e.ctrlKey && !e.metaKey && (e.key === 'n' || e.key === 'N')) {
    e.preventDefault(); openAddSite();
  }
});

