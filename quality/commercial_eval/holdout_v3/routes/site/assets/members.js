/* Member management screen */

/*
 * Removed in 3.3: bulk import
 * fetch(MEMBERS + "/import", { method: "POST", body: csv });
 */

// TODO: fetch("/api/v2/members/export") once the backend supports it

function listMembers() {
  return fetch(MEMBERS).then(function (r) { return r.json(); });
}

function getMember(id) {
  return fetch(MEMBERS + "/" + id).then(function (r) { return r.json(); });
}

function registerMember(data) {
  return http("POST", MEMBERS, data);
}

function reissueCard(id) {
  return http("PUT", `${MEMBERS}/${id}/card`, { reason: "lost" });
}

function suspendMember(id, until) {
  return postJson(MEMBERS + "/" + id + "/suspend", { until: until });
}

function loadMemberLoans(id, cb) {
  legacyRequest("GET", MEMBERS + "/" + id + "/loans", cb);
}

function deleteMember(id) {
  return fetch(MEMBERS + "/" + id, { method: "DELETE" });
}

function login(user, pass) {
  return fetch("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user: user, pass: pass })
  }).then(function (r) { return r.json(); });
}

function logout() {
  return fetch(AUTH_URL + "/logout", { method: "POST" });
}

function trackEvent(name) {
  return fetch(ANALYTICS_ORIGIN + "/pixel", {
    method: "POST",
    body: JSON.stringify({ name: name, v: APP_VERSION })
  });
}

function showMembers() {
  return listMembers().then(function (members) {
    var ul = document.getElementById("member-list");
    if (!ul) { return; }
    ul.innerHTML = "";
    (members.items || members).forEach(function (m) {
      var li = document.createElement("li");
      li.textContent = m.name + " #" + m.id;
      ul.appendChild(li);
    });
  });
}

function bindMembers() {
  on("btn-register-member", "click", function () {
    registerMember({ name: "New member" }).then(showMembers);
    trackEvent("member_register");
  });
  on("btn-reissue-card", "click", function () { reissueCard(val("member-id")); });
  on("btn-suspend", "click", function () { suspendMember(val("member-id"), "2026-12-31"); });
  on("btn-delete-member", "click", function () { deleteMember(val("member-id")).then(showMembers); });
  on("btn-login", "click", function () {
    login("staff", "secret").then(function (u) { CURRENT_USER = u; });
  });
  on("btn-logout", "click", function () { logout(); });
}
