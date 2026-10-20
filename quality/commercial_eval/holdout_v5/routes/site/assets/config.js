/* 粗大ごみ収集 申込ポータル 共通設定 */

var API_PREFIX = "/api";
var API_VERSION = "v2";
var API_BASE = API_PREFIX + "/" + API_VERSION;
var COLLECTION_BASE = API_BASE + "/collections";
var AREA_BASE = API_BASE + "/areas";
var AREA_LOOKUP = AREA_BASE + "/lookup";

// 運営担当者向け API は別系統
var ADMIN_BASE = "/admin-api/v1";

// 外部サービス
var GEOCODE_ENDPOINT = "https://geocode.example-maps.jp/v1/search";
var CHAT_WEBHOOK = "https://hooks.example-chat.com/services/T000/B000/xxxx";

// v1 時代の料金表エンドポイント（現在は参照していない）
var LEGACY_FEE_URL = "/api/v1/fees";

var DEFAULT_INIT = { credentials: "include" };

var APP_SETTINGS = {
  timeoutMs: 8000,
  locale: "ja-JP",
  maxItemsPerRequest: 10
};
