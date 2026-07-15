// ==================== アカウントアバターのドロップダウン ====================
// 認証 ON 時のみ topbar に描画される（未ログイン時は要素自体が存在しない）。
(function () {
  const btn = document.getElementById('topbar-avatar-btn');
  const menu = document.getElementById('topbar-avatar-menu');
  if (!btn || !menu) return;

  function open() {
    menu.hidden = false;
    btn.setAttribute('aria-expanded', 'true');
  }
  function close() {
    menu.hidden = true;
    btn.setAttribute('aria-expanded', 'false');
  }

  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (menu.hidden) open();
    else close();
  });
  document.addEventListener('click', (e) => {
    if (!e.target.closest('#topbar-avatar')) close();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !menu.hidden) {
      close();
      btn.focus();
    }
  });
})();
