/* SkyBook — 共有ロジック (window.SkyBook)
 * 状態は sessionStorage のキー 'skybook' に JSON で保持する。
 * 各ページはこのファイルが公開する SkyBook オブジェクトだけを使う。
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'skybook';

  var AIRPORTS = [
    { code: 'HND', name: '羽田' },
    { code: 'NRT', name: '成田' },
    { code: 'ITM', name: '伊丹' },
    { code: 'KIX', name: '関西' },
    { code: 'CTS', name: '新千歳' },
    { code: 'FUK', name: '福岡' },
    { code: 'OKA', name: '那覇' }
  ];

  var FLIGHTS = [
    { id: 'SB101', from: 'HND', to: 'CTS', dep: '07:30', arr: '09:05', price: 18900, direct: true, stops: 0, via: null },
    { id: 'SB205', from: 'HND', to: 'CTS', dep: '10:15', arr: '11:50', price: 15400, direct: true, stops: 0, via: null },
    { id: 'SB330', from: 'HND', to: 'CTS', dep: '18:40', arr: '20:15', price: 22100, direct: true, stops: 0, via: null },
    { id: 'SB412', from: 'HND', to: 'FUK', dep: '08:00', arr: '09:55', price: 21000, direct: true, stops: 0, via: null },
    { id: 'SB520', from: 'ITM', to: 'OKA', dep: '09:20', arr: '11:35', price: 24800, direct: true, stops: 0, via: null },
    { id: 'SB777', from: 'NRT', to: 'OKA', dep: '13:00', arr: '17:10', price: 19300, direct: false, stops: 1, via: 'FUK' }
  ];

  var INITIAL_STATE = {
    loggedIn: false,
    email: '',
    search: { from: 'HND', to: 'CTS', depart: '', return: '', adults: 1, seatClass: 'economy' },
    flight: null,
    seat: '',
    passengers: [],
    payment: null,
    couponApplied: false,
    bookings: []
  };

  function cloneInitial() {
    return JSON.parse(JSON.stringify(INITIAL_STATE));
  }

  function persist(s) {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(s));
    } catch (e) {
      /* sessionStorage 不可（プライベートモード等）は静かに無視する */
    }
  }

  function getState() {
    var stored = null;
    try {
      var raw = sessionStorage.getItem(STORAGE_KEY);
      if (raw) stored = JSON.parse(raw);
    } catch (e) {
      stored = null;
    }
    var base = cloneInitial();
    if (!stored || typeof stored !== 'object') return base;
    var merged = Object.assign({}, base, stored);
    merged.search = Object.assign({}, base.search, stored.search || {});
    return merged;
  }

  function save(patch) {
    var current = getState();
    var next = Object.assign({}, current, patch || {});
    if (patch && patch.search) {
      next.search = Object.assign({}, current.search, patch.search);
    }
    persist(next);
    return next;
  }

  function resetState() {
    var base = cloneInitial();
    persist(base);
    return base;
  }

  function requireLogin(redirect) {
    redirect = redirect || 'login.html';
    var s = getState();
    if (!s.loggedIn) {
      var sep = redirect.indexOf('?') >= 0 ? '&' : '?';
      location.href = redirect + sep + 'login_required=1';
      return false;
    }
    return true;
  }

  function classFactor() {
    var s = getState();
    var map = { economy: 1.0, premium: 1.4, business: 2.2 };
    return map[s.search.seatClass] || 1.0;
  }

  function subtotal() {
    var s = getState();
    if (!s.flight) return 0;
    var adults = s.search.adults || 1;
    return Math.round(s.flight.price * adults * classFactor());
  }

  function total() {
    var s = getState();
    var sub = subtotal();
    if (s.couponApplied) sub = Math.round(sub * 0.9);
    return sub;
  }

  function newPnr() {
    var chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    var out = '';
    for (var i = 0; i < 6; i++) {
      out += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return out;
  }

  function yen(n) {
    var v = Number(n) || 0;
    return v.toLocaleString('ja-JP') + '円';
  }

  function setError(id, msg) {
    var el = document.getElementById(id + '_error');
    if (el) el.textContent = msg || '';
  }

  function clearErrors(form) {
    var scope = form || document;
    var nodes = scope.querySelectorAll('.error');
    for (var i = 0; i < nodes.length; i++) nodes[i].textContent = '';
  }

  function openDialog(id) {
    var d = document.getElementById(id);
    if (d && typeof d.showModal === 'function') d.showModal();
  }

  function closeDialog(id) {
    var d = document.getElementById(id);
    if (d && typeof d.close === 'function') d.close();
  }

  function initNav(current) {
    var map = { search: 'nav_search', mypage: 'nav_mypage', settings: 'nav_settings' };
    Object.keys(map).forEach(function (key) {
      var el = document.getElementById(map[key]);
      if (!el) return;
      if (key === current) {
        el.classList.add('active');
        el.setAttribute('aria-current', 'page');
      } else {
        el.classList.remove('active');
        el.removeAttribute('aria-current');
      }
    });
  }

  window.SkyBook = {
    AIRPORTS: AIRPORTS,
    FLIGHTS: FLIGHTS,
    state: getState,
    save: save,
    requireLogin: requireLogin,
    classFactor: classFactor,
    subtotal: subtotal,
    total: total,
    newPnr: newPnr,
    yen: yen,
    setError: setError,
    clearErrors: clearErrors,
    openDialog: openDialog,
    closeDialog: closeDialog,
    initNav: initNav,
    resetState: resetState
  };
})();

// 入力し直したらその項目のエラーを消す（全ページ共通。<id>_error の規約に依存）
document.addEventListener('input', function (e) {
  var t = e.target; if (!t || !t.id) return;
  var err = document.getElementById(t.id + '_error'); if (err) err.textContent = '';
});
document.addEventListener('change', function (e) {
  var t = e.target; if (!t || !t.id) return;
  var err = document.getElementById(t.id + '_error'); if (err) err.textContent = '';
});
