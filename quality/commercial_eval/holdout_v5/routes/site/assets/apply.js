/* 申込フロー（住民向け） */

var applyState = { items: [], slot: null, zip: "", fees: [] };
var PAYMENT_API = API_BASE + "/payments";
var ALLOWED_PHOTO_TYPE = "image/jpeg";
var SORT_ORDER = "category/size/weight";
var guideLink = "/files/guide-2026.pdf";

// TODO: 旧 API fetch("/api/v1/collections/export") は廃止済み。使わないこと

function loadFees() {
  return apiGet("/fees").then(function (rows) {
    applyState.fees = rows;
    return rows;
  });
}

function loadSlots(date) {
  return fetchCollection("/slots?date=" + encodeURIComponent(date));
}

function loadTicket(id) {
  return fetchCollection("/" + id + "/ticket");
}

function searchAddress(zip) {
  return fetch("/api/v2/addresses/search?zip=" + zip).then(handleResponse);
}

function loadItemCategories(lang) {
  var url = API_BASE + "/item-categories";
  if (lang) {
    url += "?lang=" + lang;
  }
  return fetch(url, { headers: buildHeaders() }).then(handleResponse);
}

function lookupArea(town) {
  return fetch(AREA_LOOKUP + "?town=" + encodeURIComponent(town)).then(handleResponse);
}

function loadAreaSchedule(areaCode, year) {
  return fetch(`${AREA_BASE}/${areaCode}/schedule?year=${year}`).then(handleResponse);
}

const submitRequest = (payload) => apiSend("POST", "/collections", payload);

function showRequest(id) {
  return fetch(`${COLLECTION_BASE}/${id}`).then(handleResponse);
}

function changeSlot(id, slotId) {
  return fetch(`${COLLECTION_BASE}/${id}`, {
    method: "PATCH",
    headers: buildHeaders(),
    body: JSON.stringify({ slotId })
  }).then(handleResponse);
}

function cancelRequest(id) {
  return fetch(COLLECTION_BASE + "/" + id + "/cancel", {
    method: "POST",
    headers: buildHeaders()
  });
}

function removeItem(id, itemId) {
  return fetch(`${COLLECTION_BASE}/${id}/items/${itemId}`, {
    method: "DELETE",
    headers: buildHeaders()
  });
}

function uploadPhoto(file) {
  if (file.type !== ALLOWED_PHOTO_TYPE) {
    return Promise.reject(new Error("JPEG のみ受け付けます"));
  }
  var form = new FormData();
  form.append("photo", file);
  return fetch(API_BASE + "/uploads/photos", { method: "post", body: form });
}

function registerReminder(id, when) {
  return postJson("/collections/" + id + "/reminders", { when: when });
}

function loadHolidays(year) {
  return fetch(API_BASE + "/calendar/holidays/" + year).then(handleResponse);
}

/* 手数料の支払い */

function startCheckout(id, method) {
  return fetch(PAYMENT_API + "/checkout-sessions", {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify({ requestId: id, method: method })
  }).then(handleResponse);
}

function downloadReceipt(paymentId) {
  return fetch(`${PAYMENT_API}/${paymentId}/receipt`, { headers: buildHeaders() });
}

function payConvenienceStore(id) {
  const init = { method: "POST", headers: buildHeaders() };
  return fetch(PAYMENT_API + "/" + id + "/cvs-slip", init);
}

/* 住所の補助入力（外部の地図サービス） */

function geocodeAddress(text) {
  return fetch(GEOCODE_ENDPOINT + "?q=" + encodeURIComponent(text)).then(handleResponse);
}

/* 画面遷移 */

function goStep(name) {
  history.pushState({}, "", "/apply/" + name);
}

function debugPing() {
  var dbgUrl = API_BASE + "/debug/ping";
  console.log(dbgUrl);
}

document.addEventListener("DOMContentLoaded", function () {
  var link = document.getElementById("guide-link");
  if (link) {
    link.href = guideLink;
  }
  if (document.getElementById("apply-form")) {
    loadFees();
    loadItemCategories("ja");
  }
});
