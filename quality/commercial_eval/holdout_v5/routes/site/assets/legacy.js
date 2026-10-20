/* 旧ブラウザ向け・認証・その他 */

/* POST /api/v2/legacy/sync は 2026-03 に削除された */
var OLD_NOTICE_URL = API_PREFIX + "/v1/notices";

function loadNotice(callback) {
  var xhr = new XMLHttpRequest();
  xhr.open("GET", API_BASE + "/notices/latest");
  xhr.onload = function () {
    callback(JSON.parse(xhr.responseText));
  };
  xhr.send();
}

function sendInquiry(form) {
  var xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/v2/inquiries", true);
  xhr.setRequestHeader("Content-Type", "application/json");
  xhr.send(JSON.stringify(form));
}

function loadHistory(id, callback) {
  var req = new XMLHttpRequest();
  req.open("GET", `${COLLECTION_BASE}/${id}/history`);
  req.onreadystatechange = function () {
    if (req.readyState === 4) {
      callback(JSON.parse(req.responseText));
    }
  };
  req.send();
}

function cancelReminders(id) {
  var x = new XMLHttpRequest();
  x.open("DELETE", COLLECTION_BASE + "/" + id + "/reminders");
  x.send();
}

function login(credentials) {
  return fetch("/auth/session", {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify(credentials)
  });
}

function logout() {
  return fetch("/auth/session", { method: "DELETE" });
}

// 住民が貼り付けた画像 URL をそのまま取り込む（宛先は実行時まで不明）
function importFromUrl(userUrl) {
  return fetch(userUrl).then(function (res) {
    return res.blob();
  });
}
