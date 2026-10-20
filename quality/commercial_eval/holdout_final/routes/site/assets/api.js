/* api.js - thin client over the booking REST API (not minified) */
function http(method, url, body) {
  var opts = { method: method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) { opts.body = JSON.stringify(body); }
  return fetch(url, opts).then(function (r) { return r.json(); });
}

var Api = {
  listBookings: function (status) {
    return http('GET', API_BASE + '/bookings?status=' + encodeURIComponent(status));
  },
  getBooking: function (id) {
    return http('GET', `${API_BASE}/bookings/${id}`);
  },
  createBooking: function (payload) {
    return http('POST', API_BASE + '/bookings', payload);
  },
  updateBooking: function (id, payload) {
    return http('PUT', `${API_BASE}/bookings/${id}`, payload);
  },
  setBookingStatus: function (id, status) {
    return http('PATCH', API_BASE + '/bookings/' + id + '/status', { status: status });
  },
  deleteBooking: function (id) {
    return http('DELETE', API_BASE + '/bookings/' + id);
  },
  listSlots: function (resourceId, date) {
    return http('GET', `/api/v2/resources/${resourceId}/slots?date=${date}`);
  },
  legacyPing: function () {
    return http('GET', LEGACY_BASE + '/ping');
  },

  // never wired to a screen: kept for a planned report export
  exportEndpoint: '/api/v2/reports/export',

  // retired in v2, the old route was removed from the server
  /* oldList: function () { return http('GET', '/api/v2/old-bookings'); } */

  // TODO: GET /api/v2/audit-trail once the server supports paging
};

// test doubles used by the browser smoke page only; nothing in this app reads them
var TEST_MOCKS = [
  { method: 'GET', url: '/api/v2/__mock__/bookings', response: [] },
  { method: 'POST', url: '/api/v2/__mock__/payments', response: { ok: true } }
];
