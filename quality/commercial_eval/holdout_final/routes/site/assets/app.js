/* app.js - views, route table and event wiring (not minified) */
(function () {
  'use strict';

  var root = document.getElementById('view');
  var goTo = Router.navigate;

  function paint(html) { root.innerHTML = html; }

  function log(msg) {
    console.log('retrying POST /api/v2/bookings/retry-queue after: ' + msg);
  }

  // ---------- views ----------

  function dashboardView() {
    paint('<h1>Dashboard</h1><button id="new">New booking</button> ' +
          '<button id="receipt">Print receipt</button> <a id="help" href="#">Support</a>');
    document.getElementById('new').addEventListener('click', function () {
      goTo('/bookings/new');
    });
    document.getElementById('receipt').addEventListener('click', function () {
      fetch('/healthz').then(function () { goTo('/receipts/print'); });
    });
    document.getElementById('help').addEventListener('click', function (ev) {
      ev.preventDefault();
      history.pushState(null, '', '/support');
      Router.render();
    });
    fetch(API_BASE + '/bookings?status=open').then(function (r) { return r.json(); });
  }

  function bookingsView() {
    paint('<h1>Bookings</h1><ul id="rows"></ul>');
    Api.listBookings('open').then(function (rows) {
      document.getElementById('rows').innerHTML = rows.map(function (b) {
        return '<li><a href="/bookings/' + b.id + '" data-nav>' + b.title + '</a></li>';
      }).join('');
    });
  }

  function newBookingView() {
    paint('<h1>New booking</h1><form id="f"></form>');
    document.getElementById('f').addEventListener('submit', function (ev) {
      ev.preventDefault();
      Api.createBooking({ title: 'x' }).then(function (b) { goTo('/bookings/' + b.id); });
    });
  }

  function bookingView(p) {
    paint('<h1>Booking ' + p.id + '</h1><button id="cancel">Cancel</button> ' +
          '<button id="remove">Delete</button> <button id="edit">Edit</button>');
    Api.getBooking(p.id);
    document.getElementById('cancel').addEventListener('click', function () {
      Api.setBookingStatus(p.id, 'cancelled');
    });
    document.getElementById('remove').addEventListener('click', function () {
      Api.deleteBooking(p.id).then(function () { goTo('/bookings'); });
    });
    document.getElementById('edit').addEventListener('click', function () {
      goTo('/bookings/' + p.id + '/edit');
    });
  }

  function editBookingView(p) {
    paint('<h1>Edit ' + p.id + '</h1>');
    Api.updateBooking(p.id, { title: 'changed' });
  }

  function customerView(p) {
    paint('<h1>Customer ' + p.customerId + '</h1><button id="memo">Add memo</button>');
    document.getElementById('memo').addEventListener('click', function () {
      fetch(`/api/v2/customers/${p.customerId}/notes`, {
        method: 'POST',
        body: JSON.stringify({ text: 'called' })
      });
    });
  }

  function customerSearch(q) {
    return fetch('/api/v2/customers?q=' + encodeURIComponent(q)).then(function (r) { return r.json(); });
  }

  function calendarView() {
    paint('<h1>Calendar</h1><input id="q" placeholder="customer">');
    document.getElementById('q').addEventListener('input', function (ev) {
      customerSearch(ev.target.value);
    });
  }

  function resourceCalendarView(p) {
    paint('<h1>' + p.resourceId + ' / ' + p.date + '</h1>');
    Api.listSlots(p.resourceId, p.date);
  }

  function adminView() {
    paint('<h1>Admin</h1><a href="/admin/settings/notifications" data-nav>Notifications</a> ' +
          '<a href="/admin/users/u-1/roles" data-nav>Roles</a>');
    Api.legacyPing();
  }

  function notificationSettingsView() {
    paint('<h1>Notifications</h1><button id="save">Save</button>');
    document.getElementById('save').addEventListener('click', function () {
      fetch(API_BASE + '/settings/notifications', {
        method: 'PUT',
        body: JSON.stringify({ email: true })
      }).catch(function (e) { log(String(e)); });
    });
  }

  function userRolesView(p) {
    paint('<h1>Roles of ' + p.userId + '</h1>');
  }

  function billingView() {
    paint('<h1>Billing</h1>');
    fetch('https://payments.example.com/v1/charges', { method: 'POST' });
  }

  function notFoundView() {
    paint('<h1>Page not found</h1>');
  }

  function plainPage(title) {
    return function () { paint('<h1>' + title + '</h1>'); };
  }

  // never called: left over from the old admin screen
  function purgeCache() {
    return fetch('/api/v2/admin/cache', { method: 'DELETE' });
  }

  function syncOnce(flag) {
    if (flag) {
      return null;
    }
    if (false) {
      fetch('/api/v2/beta/waitlist', { method: 'POST' });
    }
    return Api.listBookings('open');
    fetch('/api/v2/legacy/sync');
  }

  // Router.add('/beta/calendar', plainPage('Beta calendar'));

  // ---------- route table ----------

  Router.add('/', dashboardView);
  Router.add('/bookings', bookingsView);
  Router.add('/bookings/new', newBookingView);
  Router.add('/bookings/:id', bookingView);
  Router.add('/bookings/:id/edit', editBookingView);
  Router.add('/customers/:customerId', customerView);
  Router.add('/calendar', calendarView);
  Router.add('/resources/:resourceId/calendar/:date', resourceCalendarView);
  Router.add('/admin', adminView);
  Router.add('/admin/settings/notifications', notificationSettingsView);
  Router.add('/admin/users/:userId/roles', userRolesView);
  Router.add('/admin/billing', billingView);
  Router.add('/404', notFoundView);

  Router.redirect('/reservations', '/bookings');
  Router.redirect('/reservations/:id', '/bookings/:id');
  Router.redirect('/home', '/');

  Router.notFound(notFoundView);

  Router.start();
})();
