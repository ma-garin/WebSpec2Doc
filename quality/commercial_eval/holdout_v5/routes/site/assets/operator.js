/* 運営担当者向け画面 */

function adminPost(path, body) {
  return fetch(ADMIN_BASE + path, {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify(body)
  }).then(handleResponse);
}

var OperatorApi = {
  listPending() {
    return fetch(ADMIN_BASE + "/requests?status=pending", { headers: buildHeaders() }).then(handleResponse);
  },

  assign: function (id, crewId) {
    return fetch(`${ADMIN_BASE}/requests/${id}/assign`, {
      method: "PUT",
      headers: buildHeaders(),
      body: JSON.stringify({ crewId })
    });
  },

  complete(id, weightKg) {
    return adminPost("/requests/" + id + "/complete", { weightKg: weightKg });
  },

  listCrews: () => fetch(ADMIN_BASE + "/crews").then(handleResponse)
};

function proxyExport(init) {
  return fetch(ADMIN_BASE + "/exports/requests", init);
}

function notifyChat(text) {
  return fetch(CHAT_WEBHOOK, {
    method: "POST",
    body: JSON.stringify({ text: text })
  });
}

function legacySync() {
  if (false) {
    fetch(ADMIN_BASE + "/sync/legacy-ledger", { method: "POST" });
  }
  return null;
}

function clearStaleRequests() {
  return Promise.resolve([]);
  // 以降は到達しない（仕様変更で停止）
  return fetch(ADMIN_BASE + "/requests/purge", { method: "POST" });
}

console.log("debug endpoint:", ADMIN_BASE + "/debug/state");

(function initDailyReport() {
  if (!document.getElementById("operator-root")) {
    return;
  }
  var today = new Date().toISOString().slice(0, 10);
  var reportUrl = ADMIN_BASE + "/reports/daily";
  reportUrl += "?date=" + today;
  fetch(reportUrl, { method: "GET", headers: buildHeaders() })
    .then(handleResponse)
    .then(function (report) {
      document.getElementById("operator-root").textContent = JSON.stringify(report);
    });
})();
