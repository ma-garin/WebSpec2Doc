/* router.js - minimal client-side router (no framework, not minified) */
(function (global) {
  'use strict';

  var table = [];
  var redirects = [];

  function compile(pattern) {
    if (pattern.indexOf('*') === 0) {
      return { re: /.*/, names: [] };
    }
    var names = [];
    var source = pattern.replace(/:([A-Za-z]+)/g, function (_m, name) {
      names.push(name);
      return '([^/]+)';
    });
    return { re: new RegExp('^' + source + '/?$'), names: names };
  }

  function match(entry, pathname) {
    var m = entry.re.exec(pathname);
    if (!m) return null;
    var params = {};
    entry.names.forEach(function (n, i) {
      params[n] = decodeURIComponent(m[i + 1]);
    });
    return params;
  }

  function add(pattern, handler) {
    var c = compile(pattern);
    table.push({ pattern: pattern, re: c.re, names: c.names, handler: handler });
  }

  function redirect(from, to) {
    var c = compile(from);
    redirects.push({ re: c.re, names: c.names, to: to });
  }

  function applyRedirect(pathname) {
    for (var i = 0; i < redirects.length; i++) {
      var r = redirects[i];
      var params = match(r, pathname);
      if (params) {
        return r.to.replace(/:([A-Za-z]+)/g, function (_m, name) {
          return params[name];
        });
      }
    }
    return null;
  }

  function resolve(pathname) {
    var target = applyRedirect(pathname);
    if (target) {
      history.replaceState({}, '', target);
      pathname = target;
    }
    var fallback = null;
    for (var i = 0; i < table.length; i++) {
      var entry = table[i];
      if (entry.pattern.indexOf('*') === 0) {
        fallback = fallback || entry;
        continue;
      }
      var params = match(entry, pathname);
      if (params) return { handler: entry.handler, params: params };
    }
    return { handler: fallback && fallback.handler, params: {} };
  }

  function render() {
    var hit = resolve(location.pathname);
    if (hit.handler) hit.handler(hit.params, new URLSearchParams(location.search));
  }

  function navigateTo(path) {
    history.pushState({}, '', path);
    render();
  }

  function start() {
    window.addEventListener('popstate', render);
    document.addEventListener('click', function (ev) {
      var a = ev.target.closest && ev.target.closest('a[data-link]');
      if (!a) return;
      ev.preventDefault();
      navigateTo(a.getAttribute('href'));
    });
    render();
  }

  global.Router = {
    add: add,
    redirect: redirect,
    navigate: navigateTo,
    render: render,
    start: start
  };
})(window);
