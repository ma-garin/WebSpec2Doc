/* api.js - thin data layer (not minified) */
(function (global) {
  'use strict';

  // TODO: GET /api/reports/export is planned for Q3 but the backend has no handler yet.
  var LEGACY_ENDPOINT = '/api/legacy';

  var JSON_HEADERS = { 'Content-Type': 'application/json' };

  function json(res) {
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.json();
  }

  // generic helpers: the path is passed in by the caller
  function request(method, path, body) {
    return fetch(path, {
      method: method,
      headers: JSON_HEADERS,
      body: body ? JSON.stringify(body) : undefined
    }).then(json);
  }

  function apiGet(path) {
    return request('GET', path);
  }

  function apiPost(path, body) {
    return request('POST', path, body);
  }

  function warnLegacy() {
    console.warn('LEGACY_ENDPOINT is deprecated: ' + LEGACY_ENDPOINT +
      ' (switch to /api/v2/items when it ships)');
  }

  function listItems() {
    return fetch('/api/items').then(json);
  }

  function getItem(id) {
    return fetch(`/api/items/${id}`).then(json);
  }

  function updateItem(id, body) {
    return fetch(`/api/items/${id}`, {
      method: 'PUT',
      headers: JSON_HEADERS,
      body: JSON.stringify(body)
    }).then(json);
  }

  function deleteItem(id) {
    return fetch(`/api/items/${id}`, { method: 'DELETE' }).then(json);
  }

  function createOrder(order) {
    return fetch('/api/orders', {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify(order)
    }).then(json);
  }

  function cancelOrder(orderId) {
    return fetch('/api/orders/' + orderId + '/cancel', { method: 'POST' }).then(json);
  }

  function updateCartItem(itemId, quantity) {
    return fetch(`/api/cart/items/${itemId}`, {
      method: 'PATCH',
      headers: JSON_HEADERS,
      body: JSON.stringify({ quantity: quantity })
    }).then(json);
  }

  function login(user, password) {
    return fetch('/api/auth/login', {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify({ user: user, password: password })
    }).then(json);
  }

  function me() {
    return fetch("/api/users/me", { credentials: 'same-origin' }).then(json);
  }

  function listNotifications() {
    return fetch('/api/notifications').then(json);
  }

  // XMLHttpRequest style call
  function checkHealth(callback) {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/health');
    xhr.onload = function () { callback(xhr.status === 200); };
    xhr.onerror = function () { callback(false); };
    xhr.send();
  }

  // Defined but nothing in the bundle ever calls it.
  function exportAll() {
    return fetch('/api/export/all').then(json);
  }

  if (false) {
    // feature removed; kept by the bundler
    fetch('/api/beta/metrics');
  }

  warnLegacy();

  global.apiGet = apiGet;
  global.apiPost = apiPost;
  global.listItems = listItems;
  global.getItem = getItem;
  global.updateItem = updateItem;
  global.deleteItem = deleteItem;
  global.createOrder = createOrder;
  global.cancelOrder = cancelOrder;
  global.updateCartItem = updateCartItem;
  global.login = login;
  global.me = me;
  global.listNotifications = listNotifications;
  global.checkHealth = checkHealth;
  global.exportAll = exportAll;
})(window);
