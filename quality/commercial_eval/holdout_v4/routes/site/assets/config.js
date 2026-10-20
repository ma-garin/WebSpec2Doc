/* 外来受付システム 共通設定 (大域スコープ。他のスクリプトから参照される) */
const APP_NAME = "外来受付ボード";
const APP_VERSION = "2.4.1";
const POLL_MS = 15000;

// API のベース。以降の定数はここから派生させる
const API_BASE = "/api/v2";
const RECEPTION_BASE = API_BASE + "/reception";
const QUEUE_BASE = RECEPTION_BASE + "/queue";
const BILLING_BASE = `${API_BASE}/billing`;
const LAB_ROOT = API_BASE + "/lab";
const LAB_ORDERS = LAB_ROOT + "/orders";
const DEPT_URL = API_BASE + "/departments";

// 外部の配信先 (このサイト自身の API ではない)
const CDN_HOST = "https://static.clinic-assets.example";
const REPORT_HOST = "https://reports.partner-lab.example";
