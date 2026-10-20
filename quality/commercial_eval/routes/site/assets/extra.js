/* extra.js - late-loaded module, starts the router (not minified) */
(function () {
  'use strict';

  var app = document.getElementById('app');

  function receiptView(params) {
    app.innerHTML = '<h1>Receipt ' + params.id + '</h1><button id="cancel">Cancel order</button>';
    document.getElementById('cancel').addEventListener('click', function () {
      cancelOrder(params.id);
    });
  }

  function aboutViewV2() {
    app.innerHTML = '<h1>About (v2)</h1>';
  }

  Router.add('/orders/:id/receipt', receiptView);

  // second registration of the same path as in app.js
  Router.add('/about', aboutViewV2);

  fetch('https://cdn.example.org/config.json').then(function (r) { return r.json(); });

  listNotifications();
  login('guest', '');
  me();

  Router.start();
})();
