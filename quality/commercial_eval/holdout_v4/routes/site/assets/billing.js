/* 会計 (XMLHttpRequest を使う古い部分) */
function xhrRequest(method, url, onDone) {
  var x = new XMLHttpRequest();
  x.open(method, url, true);
  x.onload = function () {
    onDone(x.status, x.responseText);
  };
  x.send();
}

function loadInvoice(visitId, onDone) {
  var xhr = new XMLHttpRequest();
  xhr.open("GET", BILLING_BASE + "/invoices/" + visitId);
  xhr.onload = function () {
    onDone(JSON.parse(xhr.responseText));
  };
  xhr.send();
}

function submitPayment(payload, onDone) {
  var xhr = new XMLHttpRequest();
  xhr.open("POST", `${BILLING_BASE}/payments`, true);
  xhr.setRequestHeader("Content-Type", "application/json");
  xhr.onload = function () {
    onDone(xhr.status);
  };
  xhr.send(JSON.stringify(payload));
}

function downloadReceipt(paymentId, onDone) {
  xhrRequest("GET", BILLING_BASE + "/payments/" + paymentId + "/receipt", onDone);
}

function voidPayment(paymentId, onDone) {
  xhrRequest("DELETE", BILLING_BASE + "/payments/" + paymentId, onDone);
}

function recalcCopay(visitId) {
  return apiSend("POST", "/billing/copay/recalc", { visitId: visitId });
}
