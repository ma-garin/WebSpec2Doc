/* トップバー右上のユーザーメニュー。
 *
 * 「押したら即プロフィールへ飛ぶ」のをやめ、行き先を選ばせる形にした。
 * 個人設定・ユーザーガイド・フィードバックはいずれも画面内ビューへ切り替える
 * （表示方法を3通りに散らさない）。ログアウトだけは素の <form> なので、
 * JS が落ちても機能する。
 */
(function () {
  'use strict';

  const trigger = document.getElementById('usermenu-trigger');
  const pop = document.getElementById('usermenu-pop');
  // 未ログイン時はトップバーにメニュー自体が描画されない
  if (!trigger || !pop) return;

  function isOpen() {
    return trigger.getAttribute('aria-expanded') === 'true';
  }

  function openMenu() {
    pop.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    const first = pop.querySelector('.usermenu-item');
    if (first) first.focus();
  }

  function closeMenu(returnFocus) {
    pop.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
    if (returnFocus) trigger.focus();
  }

  trigger.addEventListener('click', (ev) => {
    ev.stopPropagation();
    if (isOpen()) closeMenu(false); else openMenu();
  });

  // メニュー外のクリックで閉じる。メニュー内のクリックは項目の処理に任せる。
  document.addEventListener('click', (ev) => {
    if (!isOpen()) return;
    if (pop.contains(ev.target) || trigger.contains(ev.target)) return;
    closeMenu(false);
  });

  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape' && isOpen()) closeMenu(true);
  });

  /** メニュー項目からビューへ移る。core.js の読み込み順が変わっても落とさない。 */
  function go(viewName) {
    closeMenu(false);
    if (typeof switchView === 'function') switchView(viewName);
  }

  document.getElementById('usermenu-account-btn')?.addEventListener('click', () => go('account'));
  // 管理者のときだけトップバーに描画される（templates/partials/topbar.html）
  document.getElementById('usermenu-users-btn')?.addEventListener('click', () => go('user-management'));
  document.getElementById('usermenu-tenants-btn')?.addEventListener('click', () => go('tenant-management'));
  document.getElementById('usermenu-guide-btn')?.addEventListener('click', () => go('user-guide'));
  // 「どの画面から来たか」は switchView が覚えているので、ここでは控えない
  document.getElementById('usermenu-feedback-btn')?.addEventListener('click', () => go('feedback'));
})();

/* 現在テナントの表示。
 *
 * テナントはテンプレート変数に渡っていない（context_processor が渡すのは auth_user だけ）ため、
 * /api/auth/me から取得してヘッダーのチップ・サイドメニュー・ユーザーメニューへ流し込む。
 * 上の IIFE とは独立させてあるので、ユーザーメニューが無い画面でも動く。
 */
(function () {
  'use strict';

  const chip = document.getElementById('topbar-tenant');
  const chipName = document.getElementById('topbar-tenant-name');
  const navName = document.getElementById('nav-tenant-name');
  const menuName = document.getElementById('usermenu-tenant-name');
  // 認証オフのときはどの要素も描画されない（{% if auth_user %} で囲ってある）
  if (!chip && !navName && !menuName) return;

  fetch('/api/auth/me', { credentials: 'same-origin' })
    .then((res) => (res.ok ? res.json() : null))
    .then((data) => {
      const tenant = data && data.tenant;
      const label = tenant && (tenant.name || tenant.slug);
      // テナント未選択（/auth/tenant へ行く前）は既定表示のままにする
      if (!label) return;
      if (navName) navName.textContent = label;
      if (menuName) {
        menuName.textContent = 'テナント: ' + label;
        menuName.hidden = false;
      }
      if (chip && chipName) {
        chipName.textContent = label;
        chip.style.display = 'inline-flex';
        chip.title = 'テナント: ' + label + '（クリックで切り替え）';
      }
    })
    .catch(() => {
      /* 表示が埋まらないだけで操作は妨げない（リンク自体は素の href で機能する） */
    });
})();
