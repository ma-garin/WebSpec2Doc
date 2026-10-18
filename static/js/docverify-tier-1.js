(function () {
  'use strict';
  var R = document.querySelector('#dvtS1 .dvt-s1') || document.querySelector('.dvt-s1');
  if (!R) return;
  var $ = function (s) { return R.querySelector(s); };
  var body = $('[data-body]'), lead = $('[data-lead]'), drop = $('[data-drop]'),
      fileIn = $('[data-file]'), msg = $('[data-msg]'), pri = $('[data-approve]');
  var confirmed = {};   // この画面で格を選んだ文書（カードを残す）
  var busy = false;
  var approving = false;
  var notice = $('[data-notice]');
  var pendingDel = {};   // 取り消せる間だけ画面から隠している削除（id -> {timer, name, note}）
  var UNDO_MS = 6000;
  var chev = '<svg class="cv" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 6 6 6-6 6"/></svg>';
  var warnI = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8v5m0 3.5v.01M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>';
  var okI = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 5 5 9-10"/></svg>';
  var docI = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5"/></svg>';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function st() { return (window.DVT && window.DVT.state) || null; }
  function tiers() { return (st() && st().tiers) || []; }
  function tname(id) {
    var t = tiers().filter(function (x) { return x.id === id; })[0];
    return t ? '格' + t.id + ' ' + t.label : '格' + id;
  }
  function toast(m, k) { if (window.DVT) window.DVT.toast(m, k || 'error'); }
  function userName() {
    var el = document.querySelector('[data-user-name],#userName,.user-name,.dv-user');
    var v = el && (el.value || el.textContent || '').trim();
    return v || 'ゲスト';
  }
  function isNeed(d, low) {
    return d.confidence < low && d.tier_source !== 'human' && !confirmed[d.id];
  }

  function call(path, opts, okMsg) {
    if (busy) return Promise.resolve();
    busy = true;
    return Promise.resolve(window.DVT.api(path, opts)).then(function () {
      return window.DVT.refresh();
    }).then(function () { busy = false; render(); }, function (e) {
      busy = false;
      render();
      toast((e && e.message) || '通信できませんでした。少し待ってからもう一度お試しください。');
    });
  }
  function json(method, obj) {
    return { method: method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(obj || {}) };
  }

  function note(kind, inner, actionLabel, onAction) {
    var el = document.createElement('div');
    el.className = 'nt ' + kind;
    el.innerHTML = '<div>' + inner + '</div>';
    var b = document.createElement('button');
    b.type = 'button';
    b.textContent = actionLabel || '閉じる';
    b.addEventListener('click', function () { if (onAction) onAction(); if (el.parentNode) el.parentNode.removeChild(el); });
    el.appendChild(b);
    notice.appendChild(el);
    return el;
  }
  function dropNote(el) { if (el && el.parentNode) el.parentNode.removeChild(el); }
  function rejectList(list) {
    return '<ul>' + list.map(function (x) {
      return '<li>「' + esc(x.name) + '」: ' + esc(x.reason) + '</li>';
    }).join('') + '</ul>';
  }

  function upload(files) {
    if (!files || !files.length || busy) return;
    var fd = new FormData();
    for (var i = 0; i < files.length; i++) fd.append('file', files[i]);
    busy = true;
    Promise.resolve(window.DVT.api('tier/documents', { method: 'POST', body: fd })).then(function (d) {
      var rep = (d && d.upload_report) || {};
      if (rep.rejected && rep.rejected.length) {
        note('er', '<strong>' + (rep.added || 0) + ' 件を登録しました。次の ' + rep.rejected.length + ' 件は登録できませんでした。</strong>' +
          rejectList(rep.rejected) + '形式と内容を確かめて、もう一度選んでください。');
      }
      if (rep.replaced && rep.replaced.length) {
        note('ok', '同じ名前の文書を新しい内容に置き換えました: ' + rep.replaced.map(function (n) { return '「' + esc(n) + '」'; }).join('、') +
          '。置き換えた文書は格を決め直しています。');
      }
      return window.DVT.refresh();
    }).then(function () { busy = false; render(); }, function (e) {
      busy = false;
      render();
      note('er', esc((e && e.message) || '登録できませんでした。通信を確かめて、もう一度お試しください。'));
    });
  }
  function flushDeletes() {
    return Promise.all(Object.keys(pendingDel).map(function (id) { return runDelete(id); }));
  }
  function runDelete(id) {
    var p = pendingDel[id];
    if (!p) return Promise.resolve();
    clearTimeout(p.timer);
    delete pendingDel[id];
    dropNote(p.note);
    return Promise.resolve(window.DVT.api('tier/documents/' + id, { method: 'DELETE' })).then(function () {
      return window.DVT.refresh();
    }).then(function () { render(); }, function (e) {
      render();
      toast((e && e.message) || '削除できませんでした。少し待ってからもう一度お試しください。');
    });
  }
  function softDelete(id, name) {
    var el = note('ok', '「' + esc(name) + '」を削除しました。', '元に戻す', function () {
      var p = pendingDel[id];
      if (p) { clearTimeout(p.timer); delete pendingDel[id]; }
      render();
    });
    pendingDel[id] = { name: name, note: el, timer: setTimeout(function () { runDelete(id); }, UNDO_MS) };
    render();
  }
  function setTier(did, tier) {
    confirmed[did] = true;
    call('tier/documents/' + did, json('PATCH', { tier: tier }));
  }

  function kindLabel(d) {
    if (d.kind_label) return d.kind_label;
    var n = (((st() || {}).links || {}).nodes || []).filter(function (x) { return x.id === d.id; })[0];
    return (n && n.kind_label) || 'その他';
  }

  function render() {
    // 実行が変わったら、前の実行で出した通知を残さない
    if (render._iid !== window.DVT.iid) { notice.innerHTML = ''; render._iid = window.DVT.iid; }
    var s = st();
    if (!s) return;
    var docs = (s.documents || []).filter(function (d) { return !pendingDel[d.id]; }), low = s.low == null ? 0.6 : s.low;
    var need = docs.filter(function (d) { return isNeed(d, low); });
    var pending = docs.filter(function (d) { return !isNeed(d, low) && confirmed[d.id] && d.confidence < low; });
    var auto = docs.filter(function (d) { return !need.includes(d) && !confirmed[d.id]; });
    var empty = docs.length === 0;
    var nManual = docs.filter(function (d) { return d.tier_source === 'human' && need.indexOf(d) < 0; }).length;
    var nAuto = docs.length - need.length - nManual;

    drop.classList.toggle('big', empty);
    $('[data-droptext]').textContent = empty
      ? '文書をここにドロップ、またはクリックして選びます'
      : '文書を追加する（ドロップ、またはクリック）';

    var h = '';
    if (!empty) {
      h += '<div class="sum"><span><strong>' + docs.length + '</strong>件を登録</span>' +
        '<span class="ok">' + okI + '自動で格を決めた <strong>' + nAuto + '</strong> 件</span>' +
        (nManual ? '<span class="ok">' + okI + '自分で格を決めた <strong>' + nManual + '</strong> 件</span>' : '') +
        '<span class="' + (need.length ? 'wa' : 'ok') + '">' + (need.length ? warnI : okI) +
        '確認が要る <strong>' + need.length + '</strong> 件</span></div>';
      var cards = need.concat(pending);
      cards.forEach(function (d) {
        var done = !need.includes(d);
        h += '<div class="card' + (done ? ' done' : '') + '" data-id="' + esc(d.id) + '"><div class="top">' + docI + esc(d.name) +
          (done ? '<span class="tag g">確認済み・' + esc(tname(d.tier)) + '</span>' : '<span class="tag w">確認が要る</span>') + '</div>' +
          '<p class="why">AI は<em>' + esc(tname(d.tier)) + '</em>と推定しました。' + esc(d.reason || '') + (done ? '' : ' 確信が持てないため、格を選んでください。') + '</p>' +
          '<div class="opts">' + tiers().map(function (t) {
            return '<button type="button" data-set="' + t.id + '" class="' + (t.id === d.tier ? (done ? 'sel' : 'rec') : '') + '"><b>格' + t.id + ' ' + esc(t.label) + '</b><span>例: ' + esc(t.hint) + '</span></button>';
          }).join('') + '</div></div>';
      });
      var rest = docs.filter(function (d) { return cards.indexOf(d) < 0; });
      if (rest.length) {
        h += '<h2>自動で決まった文書（' + rest.length + ' 件）</h2>' +
          '<p class="lead">格は文書どうしの上下関係です。格1 方針 → 格2 決まりごと → 格3 仕様 → 格4 メモ の順に、下の格の文書が上の格の文書に従います。</p>';
        tiers().forEach(function (t) {
          var L = rest.filter(function (d) { return d.tier === t.id; });
          if (!L.length) return;
          var kinds = {};
          L.forEach(function (d) { var k = kindLabel(d); kinds[k] = (kinds[k] || 0) + 1; });
          var open = R._open && t.id in R._open ? R._open[t.id] : true;
          h += '<details data-t="' + t.id + '"' + (open ? ' open' : '') + '><summary>' + chev + '格' + t.id + ' ' + esc(t.label) +
            '<span class="kds">' + Object.keys(kinds).map(function (k) { return esc(k) + ' ' + kinds[k]; }).join('・') + '</span>' +
            '<span class="n">' + L.length + ' 件</span></summary>' + L.map(function (d) {
              return '<div class="row" data-id="' + esc(d.id) + '"><span class="kd">' + esc(kindLabel(d)) + '</span><span class="nm">' + esc(d.name) +
                (d.reason ? '<span class="rsn">分類理由: ' + esc(d.reason) + '</span>' : '') + '</span>' +
                '<span class="mini">' + (d.tier_source === 'human' ? '手動' : '自動') + '</span>' +
                '<select data-chg aria-label="格を変更"><option value="">変更</option>' + tiers().map(function (x) {
                  return '<option value="' + x.id + '">' + esc('格' + x.id + ' ' + x.label) + '</option>';
                }).join('') + '</select>' +
                '<button type="button" class="lk" data-del>削除</button></div>';
            }).join('') + '</details>';
        });
      }
    }
    body.innerHTML = h;

    lead.textContent = empty ? '文書を登録すると、AI が文書の格を決めます。'
      : need.length ? 'AI が文書の格を決めました。確認が要るのは ' + need.length + ' 件だけです。選んでから承認してください。'
      : 'すべての文書の格が決まりました。内容を確かめて承認してください。';
    var approved = !!s.approved;
    pri.disabled = empty || need.length > 0 || busy || approving;
    pri.setAttribute('aria-busy', approving ? 'true' : 'false');
    pri.textContent = approving ? '検査しています…' : 'この内容で承認';
    msg.textContent = approving ? '検査しています。そのままお待ちください。'
      : empty ? '文書を登録すると、承認できます。'
      : need.length ? '確認が要る文書を ' + need.length + ' 件選ぶと、承認できます。'
      : approved ? '承認済みです。もう一度承認すると検査をやり直します。'
      : '承認すると、次の「AI が検査」へ進みます。';
  }

  drop.addEventListener('keydown', function (e) {
    if (e.target !== drop) return;
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') { e.preventDefault(); fileIn.click(); }
  });
  drop.addEventListener('click', function (e) { if (e.target !== fileIn) { e.preventDefault(); fileIn.click(); } });
  fileIn.addEventListener('change', function () { upload(fileIn.files); fileIn.value = ''; });
  ['dragenter', 'dragover'].forEach(function (ev) {
    drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add('over'); });
  });
  ['dragleave', 'drop'].forEach(function (ev) {
    drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove('over'); });
  });
  drop.addEventListener('drop', function (e) { upload(e.dataTransfer && e.dataTransfer.files); });

  body.addEventListener('toggle', function (e) {
    var d = e.target; if (!d.dataset || !d.dataset.t) return;
    R._open = R._open || {}; R._open[d.dataset.t] = d.open;
  }, true);
  body.addEventListener('click', function (e) {
    var b = e.target.closest('[data-set]');
    if (b) { setTier(b.closest('.card').dataset.id, +b.dataset.set); return; }
    var del = e.target.closest('[data-del]');
    if (del) {
      var row = del.closest('.row');
      softDelete(row.dataset.id, (row.querySelector('.nm').firstChild || {}).textContent || '文書');
    }
  });
  body.addEventListener('change', function (e) {
    var sel = e.target.closest('[data-chg]');
    if (sel && sel.value) setTier(sel.closest('.row').dataset.id, +sel.value);
  });
  pri.addEventListener('click', function () {
    if (pri.disabled || approving) return;
    approving = true;
    render();
    flushDeletes().then(function () {
      return window.DVT.api('tier/approve', json('POST', { by: userName() }));
    }).then(function () {
      return window.DVT.refresh();
    }).then(function () { approving = false; render(); window.DVT.go(2); }, function (err) {
      approving = false;
      toast((err && err.message) || '承認できませんでした。文書を登録してからもう一度お試しください。');
      render();
    });
  });

  document.addEventListener('dvt:state', render);
  render();
})();
