// 「…」メニュー(.c-menu) と分割ボタン(.c-split) の結線。[data-menu] を持つ要素を自動で結ぶ。
// 構造: <div class="c-menu" data-menu><button class="c-menu__toggle" aria-haspopup="menu">…</button>
//        <ul class="c-menu__list" role="menu" hidden><li role="none"><button role="menuitem" class="c-menu__item">…</button></li></ul></div>
// 分割ボタンは .c-split に data-menu を付け、トグルに c-menu__toggle c-split__toggle を使う。
(function () {
  'use strict';
  var openMenu = null;

  function items(root) {
    return Array.prototype.slice.call(root.querySelectorAll('.c-menu__list [role="menuitem"]:not([aria-disabled="true"]):not([disabled])'));
  }
  function close(root, returnFocus) {
    if (!root) return;
    var list = root.querySelector('.c-menu__list');
    var toggle = root.querySelector('.c-menu__toggle');
    if (list) list.hidden = true;
    if (toggle) {
      toggle.setAttribute('aria-expanded', 'false');
      if (returnFocus) toggle.focus();
    }
    if (openMenu === root) openMenu = null;
  }
  function open(root) {
    if (openMenu && openMenu !== root) close(openMenu, false);
    var list = root.querySelector('.c-menu__list');
    var toggle = root.querySelector('.c-menu__toggle');
    if (!list || !toggle) return;
    list.hidden = false;
    toggle.setAttribute('aria-expanded', 'true');
    openMenu = root;
  }
  function move(root, step) {
    var its = items(root);
    if (!its.length) return;
    var i = its.indexOf(document.activeElement);
    its[(i + step + its.length) % its.length].focus();
  }
  function bind(root) {
    if (root.dataset.menuBound) return;
    root.dataset.menuBound = '1';
    var toggle = root.querySelector('.c-menu__toggle');
    var list = root.querySelector('.c-menu__list');
    if (!toggle || !list) return;
    toggle.setAttribute('aria-haspopup', 'menu');
    toggle.setAttribute('aria-expanded', 'false');
    list.hidden = true;
    toggle.addEventListener('click', function (e) {
      e.stopPropagation();
      if (list.hidden) { open(root); var f = items(root)[0]; if (f && e.detail === 0) f.focus(); } else close(root, false);
    });
    toggle.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); open(root); move(root, 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); open(root); move(root, -1); }
    });
    list.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); move(root, 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); move(root, -1); }
      else if (e.key === 'Home') { e.preventDefault(); var a = items(root)[0]; if (a) a.focus(); }
      else if (e.key === 'End') { e.preventDefault(); var b = items(root); if (b.length) b[b.length - 1].focus(); }
      else if (e.key === 'Tab') close(root, false);
    });
    list.addEventListener('click', function (e) {
      if (e.target.closest('.c-menu__item')) close(root, true);
    });
  }
  function init(scope) {
    (scope || document).querySelectorAll('[data-menu]').forEach(bind);
  }
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && openMenu) { e.stopPropagation(); close(openMenu, true); }
  }, true);
  document.addEventListener('click', function (e) {
    if (openMenu && !openMenu.contains(e.target)) close(openMenu, false);
  });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { init(); });
  else init();
  window.UIMenus = { init: init, close: function () { close(openMenu, false); } };
})();
