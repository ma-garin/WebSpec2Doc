/* app.js - views and route table (not minified) */
(function () {
  'use strict';

  var app = document.getElementById('app');
  var navigate = Router.navigate;

  function view(html) {
    app.innerHTML = html;
  }

  function trackPageView() {
    fetch('https://example.com/api/analytics', {
      method: 'POST',
      body: JSON.stringify({ path: location.pathname })
    });
  }

  // ---------- views ----------

  function homeView() {
    view('<h1>Home</h1><a href="/products" data-link>Shop</a> ' +
         '<button id="to-cart">Cart</button> ' +
         '<button id="to-account">Account</button> ' +
         '<a id="help-link" href="#">Help</a>');
    document.getElementById('to-cart').addEventListener('click', function () {
      navigate('/cart');
    });
    document.getElementById('to-account').addEventListener('click', async function () {
      const res = await fetch('/api/profile');
      const profile = await res.json();
      console.log('profile loaded', profile.name);
      navigate('/account/settings');
    });
    document.getElementById('help-link').addEventListener('click', function (ev) {
      ev.preventDefault();
      history.pushState({}, '', '/help');
      Router.render();
    });
    trackPageView();
  }

  function productsView() {
    view('<h1>Products</h1><ul id="list"></ul>');
    listItems().then(function (items) {
      document.getElementById('list').innerHTML = items.map(function (it) {
        return '<li><a href="/products/' + it.id + '" data-link>' + it.name + '</a></li>';
      }).join('');
    });
  }

  function productView(params) {
    view('<h1>Product ' + params.id + '</h1>' +
         '<button id="save">Save</button> <button id="remove">Delete</button> ' +
         '<button id="add">Add to cart</button>');
    getItem(params.id);
    document.getElementById('save').addEventListener('click', function () {
      updateItem(params.id, { name: 'edited' });
    });
    document.getElementById('remove').addEventListener('click', function () {
      deleteItem(params.id);
    });
    document.getElementById('add').addEventListener('click', function () {
      updateCartItem(params.id, 1);
    });
  }

  function categoryItemView(params) {
    view('<h1>' + params.slug + ' / ' + params.itemId + '</h1>');
    fetch(`/api/categories/${params.slug}/items`).then(function (r) { return r.json(); });
  }

  function searchView(_params, query) {
    var q = query.get('q') || '';
    view('<h1>Search</h1><p>' + q + '</p>');
    fetch('/api/search?q=' + encodeURIComponent(q)).then(function (r) { return r.json(); });
  }

  function checkoutView() {
    view('<h1>Checkout</h1><button id="pay">Pay</button>');
    document.getElementById('pay').addEventListener('click', function () {
      createOrder({ items: [] }).then(function () {
        navigate('/checkout');
      });
    });
  }

  function newView() {
    view('<h1>New arrivals</h1>');
  }

  function articleView(params) {
    view('<h1>Article ' + params.slug + '</h1>');
  }

  function aboutView() {
    view('<h1>About</h1><form id="fb"><input name="text"><button>Send</button></form>');
    document.getElementById('fb').addEventListener('submit', function (ev) {
      ev.preventDefault();
      apiPost('/api/feedback', { text: ev.target.text.value });
    });
  }

  function auditLogView() {
    view('<h1>Audit log</h1>');
  }

  function notFoundView() {
    view('<h1>Not found</h1>');
  }

  function betaDashboardView() {
    view('<h1>Beta</h1>');
  }

  // ---------- route table ----------

  Router.add('/', homeView);
  Router.add('/products', productsView);
  Router.add('/products/:id', productView);
  Router.add('/categories/:slug/items/:itemId', categoryItemView);
  Router.add('/search', searchView);
  Router.add('/checkout', checkoutView);
  Router.add('/new', newView);
  Router.add('/articles/:slug', articleView);
  Router.add('/about', aboutView);
  // No link or navigate() call in the bundle leads here.
  Router.add('/admin/audit-log', auditLogView);

  Router.redirect('/old', '/new');
  Router.redirect('/legacy-home', '/');
  Router.redirect('/blog/:slug', '/articles/:slug');

  /* Router.add('/internal/debug', debugView) was removed in v1.4 */

  if (false) {
    Router.add('/beta/dashboard', betaDashboardView);
  }

  Router.add('*', notFoundView);

  // ---------- background work ----------

  checkHealth(function (ok) {
    if (!ok) console.warn('backend health check failed');
  });

  setInterval(function () {
    fetch('/api/notifications').then(function (r) { return r.json(); });
  }, 60000);

  // Docs: https://docs.example.com/guide/getting-started
})();
