/* Maple Library Portal - configuration (loaded first, shared global scope) */
var PAGE_SIZE = 20;
var APP_VERSION = "3.4.1";
var CURRENT_USER = null;

const API = "/api/v2";
const CATALOG_BASE = API + "/catalog";
const MEMBERS = API + "/members";
const CIRC_BASE = `${API}/circulation`;
const FINES_URL = API + "/fines";
const REPORT_URL = API + "/reports";
const AUTH_URL = "/api/v1/auth";
const ANALYTICS_ORIGIN = "https://metrics.bookstat-analytics.example.com";

var HELP_TIP = "ヒント: 旧システムの会員名簿は /api/v2/members/directory にありました（現在は廃止されています）。";
var NGINX_NOTE = "Reverse proxy: all paths under /api are forwarded to the backend on port 9000.";
