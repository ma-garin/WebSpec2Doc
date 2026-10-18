/* トレーサビリティ外枠: プロジェクト選択・ステッパー・状態の共有（window.DVT） */
(function () {
  'use strict';
  var KEY = 'dvt.iid';
  var $ = function (id) { return document.getElementById(id); };
  var DVT = window.DVT = { iid: null, state: null, cur: 1 };

  try { DVT.iid = localStorage.getItem(KEY) || null; } catch (e) { /* 保存不可でも動く */ }

  DVT.toast = function (msg, kind) {
    if (window.DV && DV.toast) DV.toast(msg, kind);
  };

  DVT.api = function (path, opts) {
    opts = opts || {};
    if (!DVT.iid) return Promise.reject(new Error('プロジェクトを選んでください。'));
    var init = { method: opts.method || 'GET', headers: Object.assign({}, opts.headers || {}) };
    if (opts.json !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(opts.json); }
    if (opts.form) init.body = opts.form;
    if (opts.body !== undefined && init.body === undefined) init.body = opts.body;
    // 画面ごとの書き方の違い（'tier/x'・'/x'・'x'）を吸収する
    path = String(path || '').replace(/^\/?tier/, '').replace(/^(?!\/|$)/, '/');
    var url = '/api/docverify/inspections/' + encodeURIComponent(DVT.iid) + '/tier' + path;
    return fetch(url, init).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) throw new Error(d.error || '処理できませんでした。もう一度お試しください。');
        return d;
      });
    }).then(function (d) { DVT.setState(d); return d; });
  };

  DVT.setState = function (s) {
    DVT.state = s;
    document.dispatchEvent(new CustomEvent('dvt:state'));
  };

  function renderSteps() {
    var lis = document.querySelectorAll('#dvtSteps li');
    var done = DVT.state && DVT.state.step === 'done';
    Array.prototype.forEach.call(lis, function (li) {
      var n = +li.getAttribute('data-step');
      li.classList.toggle('on', n === DVT.cur);
      li.classList.toggle('done', n < DVT.cur || (done && n === 3));
    });
    Array.prototype.forEach.call(document.querySelectorAll('.dvt-pane'), function (p) {
      p.hidden = +p.getAttribute('data-pane') !== DVT.cur;
    });
  }

  DVT.go = function (step) {
    DVT.cur = step;
    renderSteps();
    window.scrollTo(0, 0);
  };

  DVT.refresh = function () {
    if (!DVT.iid) { $('dvtEmpty').hidden = false; $('dvtBody').hidden = true; return Promise.resolve(); }
    return fetch('/api/docverify/inspections/' + encodeURIComponent(DVT.iid) + '/tier')
      .then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || '読み込めませんでした。'); return d; }); })
      .then(function (d) {
        $('dvtEmpty').hidden = true; $('dvtBody').hidden = false;
        var first = !DVT.state;
        DVT.state = d;
        if (first) DVT.cur = d.step === 1 ? 1 : (d.step === 2 ? 2 : 3);
        renderSteps();
        document.dispatchEvent(new CustomEvent('dvt:state'));
      })
      .catch(function (e) {
        DVT.toast(e.message, 'err');
        if (/見つかりません/.test(e.message)) { DVT.iid = null; try { localStorage.removeItem(KEY); } catch (x) { /* 無視 */ } loadProjects(); }
      });
  };

  function choose(iid) {
    DVT.iid = iid || null; DVT.state = null; DVT.cur = 1;
    try { if (iid) localStorage.setItem(KEY, iid); else localStorage.removeItem(KEY); } catch (e) { /* 無視 */ }
    return DVT.refresh();
  }

  function loadProjects() {
    return fetch('/api/docverify/inspections').then(function (r) { return r.json(); }).then(function (d) {
      var list = Array.isArray(d) ? d : (d.inspections || d.items || []);
      var sel = $('dvtProj');
      sel.innerHTML = '<option value="">プロジェクトを選ぶ</option>' + list.map(function (x) {
        var id = x.id || x.iid;
        return '<option value="' + DV.esc(id) + '"' + (id === DVT.iid ? ' selected' : '') + '>' + DV.esc(x.name || id) + '</option>';
      }).join('');
      if (DVT.iid && !list.some(function (x) { return (x.id || x.iid) === DVT.iid; })) DVT.iid = null;
      return DVT.refresh();
    }).catch(function () { DVT.toast('プロジェクト一覧を読み込めませんでした。画面を開き直してください。', 'err'); });
  }

  document.addEventListener('DOMContentLoaded', function () {
    $('dvtProj').addEventListener('change', function (e) { choose(e.target.value); });
    $('dvtNew').addEventListener('click', function () {
      var name = window.prompt('プロジェクト名を入れてください。');
      if (!name || !name.trim()) return;
      fetch('/api/docverify/r4/inspections', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), goal: '', review_type: 'informal' }) })
        .then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || '作れませんでした。もう一度お試しください。'); return d; }); })
        .then(function (d) {
          var id = d.id || d.iid || (d.inspection && d.inspection.id);
          return loadProjects().then(function () { $('dvtProj').value = id; return choose(id); });
        })
        .catch(function (e) { DVT.toast(e.message, 'err'); });
    });
  });

  if (window.DV) DV.on('trace', loadProjects);
})();
