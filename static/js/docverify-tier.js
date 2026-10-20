/* トレーサビリティ外枠: 実行の開始・ステッパー・状態の共有（window.DVT）と、履歴画面の実行一覧 */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var DVT = window.DVT = { iid: null, state: null, cur: 1 };
  var TIERS = [{ id: 1, label: '方針', hint: 'ビジョン・憲章' }, { id: 2, label: '決まりごと', hint: '規約・ガイドライン・用語集' },
    { id: 3, label: '仕様', hint: 'PRD・設計書・ADR' }, { id: 4, label: 'メモ', hint: '議事録・台帳・メモ' }];
  var LEVEL = { pass: '合格', conditional: '条件付き', fail: '不合格' };
  var opening = null;   // 履歴から開く実行の id

  DVT.toast = function (msg, kind) {
    if (window.DV && DV.toast) DV.toast(msg, kind);
  };

  function json(r) {
    return r.json().catch(function () { return {}; }).then(function (d) {
      if (!r.ok) throw new Error(d.error || '処理できませんでした。もう一度お試しください。');
      return d;
    });
  }

  // 検査途中の実行を覚えておき、新しい実行の画面から続きを開けるようにする
  function remember(id, name) { try { sessionStorage.setItem('dvt-last', JSON.stringify({ id: id, name: name || '' })); } catch (e) { /* 保存できなければ導線を出さないだけ */ } }
  function forget() { try { sessionStorage.removeItem('dvt-last'); } catch (e) { /* 同上 */ } }
  function last() { try { return JSON.parse(sessionStorage.getItem('dvt-last') || 'null'); } catch (e) { return null; } }
  function renderResume() {
    var b = $('dvtResume'); if (!b) return;
    var l = last();
    b.hidden = !l || l.id === DVT.iid;
    if (l) b.title = l.name ? '「' + l.name + '」の続きを開きます' : '';
  }

  // 実行は最初の操作（文書の登録）のときに作る。開いただけでは作らない
  function ensureRun() {
    if (DVT.iid) return Promise.resolve(DVT.iid);
    var name = 'トレーサビリティ ' + new Date().toLocaleString('ja-JP', { dateStyle: 'short', timeStyle: 'medium' });
    return fetch('/api/docverify/r4/inspections', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name, goal: '', review_type: 'informal' }) })
      .then(json)
      .then(function (d) { DVT.iid = d.id || d.iid || (d.inspection && d.inspection.id); DVT.runName = name; remember(DVT.iid, name); return DVT.iid; });
  }

  DVT.api = function (path, opts) {
    opts = opts || {};
    var init = { method: opts.method || 'GET', headers: Object.assign({}, opts.headers || {}) };
    if (opts.json !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(opts.json); }
    if (opts.form) init.body = opts.form;
    if (opts.body !== undefined && init.body === undefined) init.body = opts.body;
    // 画面ごとの書き方の違い（'tier/x'・'/x'・'x'）を吸収する
    path = String(path || '').replace(/^\/?tier/, '').replace(/^(?!\/|$)/, '/');
    return ensureRun().then(function (iid) {
      return fetch('/api/docverify/inspections/' + encodeURIComponent(iid) + '/tier' + path, init);
    }).then(json).then(function (d) { DVT.setState(d); return d; });
  };

  // level_label は {pass,conditional,fail} の表で届く。画面は今の結論の文言 1 つを使う
  function norm(d) {
    if (d && d.level_label && typeof d.level_label === 'object') {
      var lv = (d.conclusion && d.conclusion.level) || d.auto_level;
      d.level_labels = d.level_label; d.level_label = d.level_labels[lv] || '';
    }
    return d;
  }

  DVT.setState = function (s) {
    DVT.state = norm(s);
    if (s && s.conclusion && DVT.iid && last() && last().id === DVT.iid) forget();
    renderHead();
    document.dispatchEvent(new CustomEvent('dvt:state'));
  };

  function renderSteps() {
    var done = DVT.state && DVT.state.step === 'done';
    Array.prototype.forEach.call(document.querySelectorAll('#dvtSteps li'), function (li) {
      var n = +li.getAttribute('data-step');
      li.classList.toggle('on', n === DVT.cur);
      li.classList.toggle('done', n < DVT.cur || (done && n === 3));
    });
    Array.prototype.forEach.call(document.querySelectorAll('.dvt-pane'), function (p) {
      p.hidden = +p.getAttribute('data-pane') !== DVT.cur;
    });
  }

  function renderHead() {
    var s = DVT.state || {};
    $('dvtRunName').textContent = DVT.iid ? (s.name || DVT.runName || '') : '新しい実行';
    $('dvtRestart').hidden = !DVT.iid;
  }

  DVT.go = function (step) {
    DVT.cur = step;
    renderSteps();
    window.scrollTo(0, 0);
  };

  function emptyState() {
    return { step: 1, documents: [], tiers: TIERS, low: 0.6, approved: null, findings: [], reports: {},
      rules: [], conclusion: null, level_label: '' };
  }

  DVT.refresh = function () {
    if (!DVT.iid) {
      DVT.state = emptyState(); DVT.cur = 1;
      renderHead(); renderSteps();
      document.dispatchEvent(new CustomEvent('dvt:state'));
      return Promise.resolve();
    }
    return fetch('/api/docverify/inspections/' + encodeURIComponent(DVT.iid) + '/tier').then(json)
      .then(function (d) {
        var first = !DVT.state || !DVT.state.step || DVT.state._empty;
        DVT.state = norm(d);
        if (first) DVT.cur = d.step === 1 ? 1 : (d.step === 2 ? 2 : 3);
        renderHead(); renderSteps();
        document.dispatchEvent(new CustomEvent('dvt:state'));
      })
      .catch(function (e) { DVT.toast(e.message, 'err'); });
  };

  // サイドから開くたびに新しい実行。履歴から開いたときだけ、その実行を表示する
  function start() {
    DVT.iid = opening ? opening.id : null; DVT.runName = opening ? opening.name : ''; opening = null; DVT.state = null; DVT.cur = 1;
    renderResume();
    return DVT.refresh();
  }

  DVT.open = function (iid, name) {
    opening = { id: iid, name: name || '' };
    remember(iid, name);
    // ハッシュを変えると core の popstate/hashchange が画面を開く。続けて DV.show を呼ぶと
    // start が二度走り、二度目は opening が空のため新しい実行になる。だから片方だけにする
    if (location.hash !== '#trace') location.hash = '#trace';
    else if (window.DV && DV.show) DV.show('trace');
  };

  // 履歴: トレーサビリティの実行一覧を先頭に出す
  function renderHistory() {
    var view = document.querySelector('.dv-view[data-view="metrics"]');
    if (!view) return;
    var box = $('dvtHist');
    if (!box) {
      box = document.createElement('section');
      box.id = 'dvtHist'; box.className = 'dvt-hist';
      view.insertBefore(box, view.firstChild);
    }
    fetch('/api/docverify/inspections').then(json).then(function (d) {
      var list = (d.inspections || []).filter(function (x) { return x.tier && (x.tier.documents || []).length; })
        .sort(function (a, b) { return String(b.updated_at || '').localeCompare(String(a.updated_at || '')); });
      var esc = DV.esc;
      box.innerHTML = '<h2 class="dvg-h">トレーサビリティの実行履歴</h2>' + (list.length
        ? '<table class="dv-table"><thead><tr><th>実行</th><th>日時</th><th>文書</th><th>結論</th></tr></thead><tbody>'
          + list.map(function (x) {
            var c = x.tier.conclusion;
            var lv = c ? LEVEL[c.level] + '（確定）' : (x.tier.approved ? '検査済み・未確定' : '登録中');
            return '<tr data-iid="' + esc(x.id) + '" tabindex="0"><td>' + esc(x.name || x.id) + '</td><td>'
              + esc(new Date(x.updated_at).toLocaleString('ja-JP', { dateStyle: 'short', timeStyle: 'short' }))
              + '</td><td>' + x.tier.documents.length + ' 件</td><td>' + esc(lv) + '</td></tr>';
          }).join('') + '</tbody></table>'
        : '<p class="mut">まだ実行がありません。サイドの「トレーサビリティ」から文書を登録すると、ここに残ります。</p>');
      Array.prototype.forEach.call(box.querySelectorAll('tr[data-iid]'), function (tr) {
        var go = function () { DVT.open(tr.getAttribute('data-iid'), tr.cells[0].textContent); };
        tr.addEventListener('click', go);
        tr.addEventListener('keydown', function (e) { if (e.key === 'Enter') go(); });
      });
    }).catch(function () { box.innerHTML = '<p class="mut">実行履歴を読み込めませんでした。画面を開き直してください。</p>'; });
  }

  document.addEventListener('DOMContentLoaded', function () {
    // 再読み込みしても途中の実行に戻る（前回の続きを自動で開く。新しく始めるときは「新しく始める」）
    var prev = last();
    if (prev && !DVT.iid && !opening) opening = { id: prev.id, name: prev.name };
    $('dvtRestart').addEventListener('click', function () { opening = null; start(); });
    var rs = $('dvtResume');
    if (rs) rs.addEventListener('click', function () { var l = last(); if (!l) return; opening = { id: l.id, name: l.name }; start(); });
  });

  if (window.DV) {
    DV.on('trace', start);
    DV.on('metrics', renderHistory);
  }
})();
