/* Circulation: checkout, return, holds, fines, reports, router, boot */

var MSG_LEDGER_FAIL = "Request to /api/v2/circulation/ledger failed. Please retry.";

var MOCK_LOANS = [
  { id: 1, title: "Sample Book A", self: "/api/v2/mock/loans/1" }
];

var FIXTURE_REQUESTS = [
  { method: "GET", url: "/api/v2/fixtures/members" },
  { method: "POST", url: "/api/v2/fixtures/checkout" }
];

function checkoutBook(memberId, isbn) {
  return fetch(CIRC_BASE + "/checkout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ memberId: memberId, isbn: isbn })
  });
}

function returnBook(loanId) {
  return http("POST", CIRC_BASE + "/return", { loanId: loanId });
}

function renewLoan(loanId) {
  return postJson(`${CIRC_BASE}/loans/${loanId}/renew`, {});
}

function loadOverdue(branch) {
  return fetch(`${CIRC_BASE}/overdue?branch=${branch}`).then(function (r) { return r.json(); });
}

function loadFines() {
  return fetch(FINES_URL).then(function (r) { return r.json(); });
}

function payFine(fineId) {
  return postJson(FINES_URL + "/" + fineId + "/pay", {});
}

function placeHold(memberId, isbn) {
  return fetch(CIRC_BASE + "/holds", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ memberId: memberId, isbn: isbn })
  });
}

function cancelHold(holdId) {
  var xhr = new XMLHttpRequest();
  xhr.open("DELETE", CIRC_BASE + "/holds/" + holdId);
  xhr.send();
}

function loadBranches() {
  return api("/branches");
}

function loadMonthlyReport(month) {
  return getJson(REPORT_URL + "/monthly?month=" + month);
}

// admin tool: resource name typed by the operator
function countResource() {
  var res = val("count-resource");
  return fetch(API + "/" + res + "/count").then(function (r) { return r.json(); });
}

// admin tool: whole URL typed by the operator
function probeEndpoint() {
  var target = val("probe-url");
  return fetch(target);
}

function legacyCheckout(memberId, isbn) {
  return checkoutBook(memberId, isbn);
  fetch(CIRC_BASE + "/legacy-checkout", { method: "POST" });
}

function syncLedger() {
  return Promise.resolve();
  getJson(FINES_URL + "/ledger");
}

function verboseHealth() {
  if (0) {
    getJson(API + "/internal/healthz-verbose");
  }
}

function reportToPartner(payload) {
  return fetch("https://stats.bookmetrics-partner.example.net/v1/collect", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

function showLoans() {
  var branch = val("branch-select") || "main";
  return loadOverdue(branch).then(function (loans) {
    var ul = document.getElementById("loan-list");
    if (!ul) { return; }
    ul.innerHTML = "";
    (loans.items || loans).forEach(function (l) {
      var li = document.createElement("li");
      li.textContent = l.title + " / due " + l.dueDate;
      ul.appendChild(li);
    });
  }).catch(function () { alert(MSG_LEDGER_FAIL); });
}

function showFines() {
  return loadFines().then(function (fines) {
    var ul = document.getElementById("fine-list");
    if (!ul) { return; }
    ul.innerHTML = "";
    (fines.items || fines).forEach(function (f) {
      var li = document.createElement("li");
      li.textContent = f.memberName + ": " + f.amount;
      ul.appendChild(li);
    });
  });
}

var ROUTES = {
  "/books": showBooks,
  "/members": showMembers,
  "/loans": showLoans,
  "/fines": showFines
};

function navigate() {
  var hash = location.hash.replace(/^#/, "") || "/books";
  var views = document.querySelectorAll("section");
  Array.prototype.forEach.call(views, function (s) { s.classList.remove("active"); });
  var active = document.getElementById("view-" + hash.slice(1));
  if (active) { active.classList.add("active"); }
  var handler = ROUTES[hash];
  if (handler) { handler(); }
}

function bindCirculation() {
  on("btn-checkout", "click", function () { checkoutBook(val("loan-member"), val("loan-isbn")); });
  on("btn-return", "click", function () { returnBook(val("loan-isbn")); });
  on("btn-renew", "click", function () { renewLoan(val("loan-isbn")); });
  on("btn-hold", "click", function () { placeHold(val("loan-member"), val("loan-isbn")); });
  on("btn-cancel-hold", "click", function () { cancelHold(val("loan-isbn")); });
  on("btn-pay-fine", "click", function () { payFine(val("loan-isbn")).then(showFines); });
  on("btn-count", "click", function () { countResource().then(console.log); });
  on("btn-probe", "click", function () { probeEndpoint(); });
  on("btn-report", "click", function () {
    loadMonthlyReport(val("report-month")).then(function (rep) { reportToPartner(rep); });
  });
  loadBranches().then(function (branches) {
    var sel = document.getElementById("branch-select");
    (branches || []).forEach(function (b) {
      var opt = document.createElement("option");
      opt.textContent = b.name;
      sel.appendChild(opt);
    });
  });
}

document.addEventListener("DOMContentLoaded", function () {
  document.getElementById("help-tip").textContent = HELP_TIP + " " + NGINX_NOTE;
  console.table(FIXTURE_REQUESTS.map(function (f) { return f.method; }));
  console.log(MOCK_LOANS.length);
  bindCatalog();
  bindMembers();
  bindCirculation();
  window.addEventListener("hashchange", navigate);
  navigate();
});
