/* Thin HTTP helpers shared by every screen */
function http(method, url, body) {
  var opts = { method: method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) {
    opts.body = JSON.stringify(body);
  }
  return fetch(url, opts).then(function (res) {
    if (!res.ok) {
      throw new Error("HTTP " + res.status);
    }
    return res.json();
  });
}

function getJson(url) {
  return http("GET", url);
}

function postJson(url, body) {
  return http("POST", url, body);
}

function sendDelete(url) {
  return http("DELETE", url);
}

// api("/x") -> getJson -> http -> fetch
function api(path) {
  return getJson(API + path);
}

function legacyRequest(verb, url, done) {
  var xhr = new XMLHttpRequest();
  xhr.open(verb, url, true);
  xhr.onload = function () {
    done(null, JSON.parse(xhr.responseText));
  };
  xhr.onerror = function () {
    done(new Error("network"));
  };
  xhr.send();
}

function on(id, evt, fn) {
  var el = document.getElementById(id);
  if (el) {
    el.addEventListener(evt, fn);
  }
}

function val(id) {
  var el = document.getElementById(id);
  return el ? el.value : "";
}
