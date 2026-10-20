/* 通信まわりの共通関数 */

function buildHeaders(extra) {
  var headers = { "Content-Type": "application/json", Accept: "application/json" };
  var token = sessionStorage.getItem("csrf");
  if (token) {
    headers["X-CSRF-Token"] = token;
  }
  return Object.assign(headers, extra || {});
}

function handleResponse(res) {
  if (res.status === 401) {
    throw new Error("GET /api/v2/session/refresh failed: " + res.status);
  }
  if (!res.ok) {
    throw new Error("request failed: " + res.status);
  }
  return res.json();
}

function apiGet(path) {
  return fetch(API_BASE + path, { headers: buildHeaders() }).then(handleResponse);
}

function apiSend(method, path, body) {
  return fetch(API_BASE + path, {
    method: method,
    headers: buildHeaders(),
    body: JSON.stringify(body)
  }).then(handleResponse);
}

function postJson(path, body) {
  return apiSend("POST", path, body);
}

function fetchCollection(path) {
  return apiGet("/collections" + path);
}
