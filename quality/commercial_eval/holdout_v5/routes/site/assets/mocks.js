/* 画面確認用のダミーデータ（本番では使わない） */

var MOCK_REQUEST = {
  id: "mock-1",
  detailUrl: "/api/v2/collections/mock-1",
  ticketUrl: "/api/v2/collections/mock-1/ticket",
  items: [{ name: "ソファ", size: "L" }]
};

var MOCK_ROUTES = {
  "/api/v2/slots/mock": { slots: [] }
};

function runSelfCheck() {
  var fake = "/api/v2/collections/__selftest__";
  return Promise.resolve({ url: fake, ok: true });
}
