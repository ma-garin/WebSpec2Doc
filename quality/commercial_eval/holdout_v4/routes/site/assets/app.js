/* 起動処理・お知らせ・検査オーダー・その他 */

// 検査オーダー (多段の定数を使う)
const LabDesk = {
  submit(order) {
    return fetch(LAB_ORDERS, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(order),
    });
  },
  status(orderId) {
    return fetch(LAB_ORDERS + "/" + orderId + "/status");
  },
  reprioritize(orderId, level) {
    return fetch(`${LAB_ORDERS}/${orderId}`, {
      method: "PATCH",
      body: JSON.stringify({ level: level }),
    });
  },
  cancel(orderId) {
    return fetch(LAB_ORDERS + "/" + orderId, { method: "DELETE" });
  },
  latestResults() {
    return fetch(LAB_ROOT + "/results/latest");
  },
};

(function () {
  "use strict";

  var NOTICE_API = "/api/v2" + "/notices";

  async function loadNotices() {
    const res = await fetch(NOTICE_API + "/active");
    return res.json();
  }

  async function markNoticeRead(noticeId) {
    await fetch(`${NOTICE_API}/${noticeId}/read`, { method: "PUT" });
  }

  function saveMemo(text, readOnly) {
    return fetch(API_BASE + "/memos", {
      method: readOnly ? "GET" : "POST",
      body: readOnly ? undefined : JSON.stringify({ text: text }),
    });
  }

  function pingSession() {
    return fetch(API_BASE + "/session/ping");
  }

  // ---- ここから下は実際には API 呼び出しにならないもの ----

  // 仕様メモ: 集計は GET /api/v2/analytics/summary を使う予定 (未実装)

  /*
  fetch(API_BASE + "/patients/export", { method: "POST" });
  */

  var DEBUG = false;
  if (false) {
    fetch(API_BASE + "/debug/dump-patients");
  }

  function purgeStale() {
    return null;
    fetch(API_BASE + "/reception/queue/purge", { method: "POST" });
  }

  // どこからも使っていない旧エンドポイント名
  var LEGACY_PRINT_SLIP = "/api/v1/print/queue-slip";

  // 画面確認用のダミー行。表示するだけで取得はしない
  var MOCK_QUEUE = [
    { ticket: "A001", url: "/api/v2/mock/tickets/A001" },
    { ticket: "A002", url: "/api/v2/mock/tickets/A002" },
  ];
  function renderMock(listEl) {
    MOCK_QUEUE.forEach(function (m) {
      var li = document.createElement("li");
      li.textContent = m.ticket + " " + m.url;
      listEl.appendChild(li);
    });
  }

  function showConnectionError() {
    alert("API /api/v2/status-board への接続に失敗しました。通信状態を確認してください。");
  }

  if (DEBUG) {
    console.log("診断用エンドポイント:", API_BASE + "/debug/state");
  }
  console.warn("fallback to " + QUEUE_BASE + "/snapshot is disabled");

  // 外部サービス (別オリジン)
  function exportToPartner(rows) {
    return fetch(REPORT_HOST + "/v1/export", {
      method: "POST",
      body: JSON.stringify(rows),
    });
  }
  function loadWeather() {
    return fetch("https://api.weather-board.example/v1/forecast?city=tokyo");
  }

  // 利用者が入力した URL / クエリで決まるもの (静的には決まらない)
  function openCustomEndpoint() {
    return fetch(document.getElementById("custom-endpoint").value);
  }
  function followNext() {
    return fetch(new URLSearchParams(location.search).get("next"));
  }

  function boot() {
    document.title = APP_NAME + " v" + APP_VERSION;
    pingSession();
    loadNotices();
    ReceptionDesk.refreshQueue();
    setInterval(ReceptionDesk.refreshQueue, POLL_MS);
  }

  window.addEventListener("DOMContentLoaded", boot);
  window.NoticeApp = {
    markRead: markNoticeRead,
    saveMemo: saveMemo,
    exportToPartner: exportToPartner,
    loadWeather: loadWeather,
    openCustomEndpoint: openCustomEndpoint,
    followNext: followNext,
    purgeStale: purgeStale,
    renderMock: renderMock,
    showConnectionError: showConnectionError,
  };
})();
