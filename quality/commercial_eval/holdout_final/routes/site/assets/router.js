/* router.js - tiny history based router (not minified) */
(function (global) {
  var table = [];
  var aliases = [];
  var fallback = null;

  function compile(pattern) {
    var names = [];
    var source = pattern.replace(/:([A-Za-z]+)/g, function (_, name) {
      names.push(name);
      return '([^/]+)';
    });
    return { re: new RegExp('^' + source + '$'), names: names };
  }

  var Router = {
    add: function (pattern, handler) {
      var c = compile(pattern);
      table.push({ pattern: pattern, re: c.re, names: c.names, handler: handler });
    },
    redirect: function (from, to) {
      aliases.push({ from: compile(from), to: to });
    },
    notFound: function (handler) {
      fallback = handler;
    },
    navigate: function (path) {
      history.pushState(null, '', path);
      Router.render();
    },
    render: function () {
      var path = location.pathname.replace(/(.)\/$/, '$1');
      for (var i = 0; i < aliases.length; i++) {
        var a = aliases[i].from.re.exec(path);
        if (a) {
          history.replaceState(null, '', aliases[i].to.replace(':id', a[1]));
          return Router.render();
        }
      }
      for (var j = 0; j < table.length; j++) {
        var m = table[j].re.exec(path);
        if (m) {
          var params = {};
          table[j].names.forEach(function (n, k) { params[n] = m[k + 1]; });
          return table[j].handler(params);
        }
      }
      if (fallback) { fallback(); }
    },
    start: function () {
      window.addEventListener('popstate', Router.render);
      document.addEventListener('click', function (ev) {
        var a = ev.target.closest && ev.target.closest('a[data-nav]');
        if (a) { ev.preventDefault(); Router.navigate(a.getAttribute('href')); }
      });
      Router.render();
    }
  };
  global.Router = Router;
})(window);
