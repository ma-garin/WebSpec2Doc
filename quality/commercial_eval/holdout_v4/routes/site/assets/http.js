/* HTTP ヘルパー (大域)。fetch を包む層をここに集める */
const req = (m, u, body) =>
  fetch(u, {
    method: m,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });

function apiGet(path) {
  return req("GET", API_BASE + path);
}

function apiPost(path, body) {
  return req("POST", API_BASE + path, body);
}

function apiSend(method, path, body) {
  return req(method, API_BASE + path, body);
}

function getJson(path) {
  return apiGet(path).then(function (r) {
    return r.json();
  });
}

function loadList(resource) {
  return getJson("/" + resource);
}
