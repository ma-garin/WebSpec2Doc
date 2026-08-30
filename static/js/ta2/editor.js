/* ============================================================================
 * TA2 / editor.js — 中央のエディタ（ヘッダ・ステップ・要素ピッカー・実行） FE-A 所有
 * ========================================================================== */
(function () {
  'use strict';
  var T = window.TA2, S = T.state, $ = T.$, $$ = T.$$, esc = T.esc;
  var stabLabel = T.stabLabel, statusLabel = T.statusLabel;

  /* --------------------------------------------------- 要素辞書のヘルパ */
  function elsOf(screen) { return (S.elements && S.elements[screen]) || {}; }

  /** 要素辞書の 1 件を、画面上の見た目の種類に分類する（契約 §2.2 の形から推定） */
  function elKind(meta, key) {
    if (meta && meta.kind) return meta.kind;
    if (key === 'alert') return 'alert';
    if (key === 'hero') return 'hero';
    if (/^btn_/.test(key)) return 'button';
    var type = meta && meta.type ? String(meta.type).toLowerCase() : '';
    if (type === 'select') return 'select';
    if (type === 'submit' || type === 'button') return 'button';
    if (type) return 'input';
    return 'text';
  }
  T.elKind = elKind;
  T.elsOf = elsOf;

  function metaOf(screen, key) {
    var m = elsOf(screen)[key];
    return m || { key: key, label: key, loc: key, stab: 'mid' };
  }

  /* ---------------------------------------------------------- ヘッダ */
  function historyHTML(h) {
    return (h || []).map(function (v) {
      return '<i class="' + (v === 1 ? 'p' : v === 0 ? 'f' : 'w') + '"></i>';
    }).join('');
  }

  function hasRun(t) {
    return !!(t && t.last && (t.last.run_id || t.last.at));
  }

  function renderHeader() {
    var box = $('#ed-h');
    if (!box) return;
    var t = T.current();
    if (!t) {
      box.innerHTML = '<h1>テストがありません</h1><div class="sp"></div>'
        + '<span style="color:var(--tx3);font-size:12px">「＋ 新しいテスト」から作れます</span>';
      return;
    }
    var running = t.status === 'running' || (S.run.running && S.run.current_id === t.id);
    var streak = t.status === 'fail' && (t.history || []).length >= 3
      && (t.history || []).slice(-3).every(function (v) { return v === 0; });
    var runBtn = S.run.running
      ? '<button class="btn sm" id="run-btn" title="実行中です。押すと中止します">■ 実行を中止</button>'
      : '<button class="btn sm pri" id="run-btn">▶ このテストを実行</button>';
    // Trace は実行の証跡があるときだけ出す（無い機能のボタンは置かない）
    var traceBtn = hasRun(t) ? '<button class="btn sm" id="trace-btn">Trace</button>' : '';

    box.innerHTML = '<h1 contenteditable="true" spellcheck="false" id="ttl">' + esc(t.name) + '</h1>'
      + '<code>' + esc(t.id) + ' · ' + esc(t.screen) + (t.case_id ? ' · ' + esc(t.case_id) : '') + '</code>'
      + '<span class="pill p-' + esc(running ? 'running' : t.status) + '">'
      + esc(statusLabel[running ? 'running' : t.status] || t.status) + (streak ? ' · 3回連続' : '') + '</span>'
      + '<div class="sp"></div>'
      + '<div class="hist">' + historyHTML(t.history) + '<span>直近10回</span></div>'
      + traceBtn
      + '<button class="btn sm" id="dup-btn" title="複製">⧉</button>'
      + runBtn;

    var ttl = $('#ttl');
    ttl.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); e.target.blur(); }
    });
    ttl.addEventListener('blur', function (e) {
      var v = e.target.textContent.trim();
      if (!v || v === t.name) { e.target.textContent = t.name; return; }
      T.api.update(S.domain, t.id, { name: v }).then(function (r) {
        Object.assign(t, r.test || {});
        T.toast('名前を保存しました');
        T.render();
      }, function (err) {
        e.target.textContent = t.name;
        T.toast(err.message, 'ng');
      });
    });

    $('#dup-btn').addEventListener('click', function () {
      T.api.duplicate(S.domain, t.id).then(function (r) {
        return T.loadTests().then(function () {
          if (r.test && r.test.id) T.select(r.test.id); else T.render();
          T.toast('複製しました', 'ok');
        });
      }, function (err) { T.toast(err.message, 'ng'); });
    });

    var tr = $('#trace-btn');
    if (tr) {
      tr.addEventListener('click', function () {
        // modals.js が 'trace' を受けるならモーダル、無ければ証跡ファイルを直接開く
        if (T.has('trace')) T.emit('trace', t);
        else window.open(T.api.artifactUrl(S.domain, t.id, 'trace'), '_blank');
      });
    }

    $('#run-btn').addEventListener('click', function () {
      if (S.run.running) { T.cancelRun().catch(function () { }); return; }
      runCurrent();
    });
  }

  /* ---------------------------------------------------------- ステップ */
  function locHTML(s) {
    if (s.loc === 'page.goto' || s.loc === 'page.url') return '<span>' + esc(s.loc) + '</span>';
    var issue = s.issue || null;
    var useFix = s.fixed && issue && issue.fix && issue.type === 'missing';
    var loc = useFix ? issue.fix : s.loc;
    var stab = (s.fixed && issue && issue.fix_stab) ? issue.fix_stab : s.stab;
    var out = '<span>' + esc(loc) + '</span>';
    if (stab) out += '<span class="h h-' + esc(stab) + '">' + esc(stabLabel[stab] || stab) + '</span>';
    return out;
  }

  function stepLine(t, i) {
    var s = t.steps[i];
    var showIssue = s.issue && !s.fixed && (t.status === 'fail' || t.status === 'flaky');
    var cls = ['st', i === S.step ? 'on' : '', showIssue ? 'ng' : '', s._run ? 'run' : '', s._done ? 'done' : ''].join(' ');
    var n = s.kind === 'pre' ? '–' : i;
    var extra = '';
    if (showIssue) {
      var fix = s.issue.fix
        ? '修正案 <code>' + esc(s.issue.fix) + '</code>'
          + (s.issue.fix_stab ? '<span class="h h-' + esc(s.issue.fix_stab) + '">' + esc(stabLabel[s.issue.fix_stab] || s.issue.fix_stab) + '</span>' : '')
          + '<button class="btn sm pri" data-fix="' + i + '" style="margin-left:auto">適用</button>'
        : '<span class="nofix">修正案なし</span>'
          + '<span style="color:var(--tx3)">'
          + esc(String(s.issue.detail || s.issue.msg || '原因を確認してから直してください').split('\n')[0].slice(0, 90))
          + '</span>';
      extra = '<div class="err"><b>' + esc(s.issue.msg || '') + '</b>' + esc(s.issue.detail || '') + '</div>'
        + '<div class="fix">' + fix + '</div>';
    } else if (s.fixed) {
      extra = '<div class="fixed-note">✓ 修正を適用済み · 実行して確認してください</div>';
    }
    return '<div class="' + cls + '" data-i="' + i + '"><div class="n">' + n + '</div>'
      + '<div><div class="v">' + esc(s.action) + ' <em>' + esc(s.arg || '') + '</em></div>'
      + '<div class="loc">' + locHTML(s)
      + (s.wait_ms ? '<span style="color:var(--tx3)">待機 ' + (s.wait_ms / 1000).toFixed(1) + 's</span>' : '')
      + (s._ms ? '<span style="color:var(--tx3)">' + esc(s._ms) + '</span>' : '')
      + '</div></div>'
      + '<button class="x" data-del="' + i + '" title="ステップを削除">✕</button>' + extra + '</div>';
  }

  function renderSteps() {
    var box = $('#steps');
    if (!box) return;
    var t = T.current();
    if (!t) { box.innerHTML = ''; return; }
    var groups = [['前提', 'pre'], ['操作', 'act'], ['検証', 'ver']];
    var html = '';
    groups.forEach(function (g) {
      var idx = [];
      (t.steps || []).forEach(function (s, i) { if (s.kind === g[1]) idx.push(i); });
      if (!idx.length) return;
      html += '<div class="sec">' + g[0] + '<span>' + idx.length + '</span></div>';
      idx.forEach(function (i) { html += stepLine(t, i); });
    });
    html += '<button class="add" id="add-step">＋ ステップを追加 · 右の画面上の要素を選ぶ</button>';
    box.innerHTML = html;
    if (picking) {
      var a = $('#add-step');
      a.classList.add('on');
      a.textContent = '右の画面で要素をクリックしてください（Esc で中止）';
    }
    $('#add-step').addEventListener('click', togglePick);
  }

  function saveSteps(t, msg) {
    return T.api.update(S.domain, t.id, { steps: t.steps }).then(function (r) {
      Object.assign(t, r.test || {});
      if (S.step >= (t.steps || []).length) S.step = Math.max(0, (t.steps || []).length - 1);
      if (msg) T.toast(msg, 'ok');
      T.render();
    }, function (err) {
      T.toast(err.message, 'ng');
      return T.loadTests().then(function () { T.render(); });
    });
  }

  var stepsBox = $('#steps');
  if (stepsBox) {
    stepsBox.addEventListener('click', function (e) {
      var t = T.current();
      if (!t) return;
      var fx = e.target.closest('[data-fix]');
      if (fx) {
        var idx = +fx.dataset.fix;
        fx.disabled = true;
        T.api.fix(S.domain, t.id, idx).then(function (r) {
          Object.assign(t, r.test || {});
          // 契約 §3.1: 修正案が無いのは正常系。applied:false + reason で返る
          if (r && r.applied === false) {
            fx.disabled = false;
            T.toast(r.reason || '修正案がありません', 'ng');
          } else {
            T.toast('修正案を適用しました。実行して確認してください', 'ok');
          }
          T.render();
        }, function (err) { fx.disabled = false; T.toast(err.message, 'ng'); });
        return;
      }
      var dl = e.target.closest('[data-del]');
      if (dl) {
        if ((t.steps || []).length <= 1) { T.toast('最後のステップは削除できません', 'ng'); return; }
        t.steps.splice(+dl.dataset.del, 1);
        S.step = Math.min(S.step, t.steps.length - 1);
        saveSteps(t, 'ステップを削除しました');
        return;
      }
      var st = e.target.closest('.st');
      if (st) {
        S.step = +st.dataset.i;
        renderSteps();
        T.emit('select', t);
      }
    });
  }

  /* ------------------------------------------------------ 要素ピッカー */
  var picking = false, pop = null;

  function togglePick() {
    if (picking) { stopPick(); return; }
    picking = true;
    var page = $('#page'); if (page) page.classList.add('pick');
    var a = $('#add-step');
    if (a) { a.classList.add('on'); a.textContent = '右の画面で要素をクリックしてください（Esc で中止）'; }
    var bar = document.createElement('div');
    bar.className = 'pickbar';
    bar.id = 'pickbar';
    bar.innerHTML = '画面上の要素を選ぶと、ステップの候補が出ます <button id="pick-cancel">中止</button>';
    var view = document.querySelector('.view');
    if (view) view.appendChild(bar);
    var c = $('#pick-cancel'); if (c) c.addEventListener('click', stopPick);
  }

  function stopPick() {
    picking = false;
    var page = $('#page'); if (page) page.classList.remove('pick');
    var b = $('#pickbar'); if (b) b.remove();
    if (pop) { pop.remove(); pop = null; }
    renderSteps();
  }

  function actionsFor(kind) {
    if (kind === 'input') return ['入力する', '入力欄を空のままにする', '表示される'];
    if (kind === 'select') return ['選ぶ', '表示される'];
    if (kind === 'button') return ['押す', '表示される', '無効になっている'];
    return ['表示される', '含む'];
  }

  function openPicker(el) {
    var t = T.current();
    if (!t) return;
    var key = el.dataset.el;
    var meta = metaOf(t.screen, key);
    var kind = elKind(meta, key);
    if (pop) pop.remove();
    pop = document.createElement('div');
    pop.className = 'pop';
    var stage = document.querySelector('.stage');
    var pr = stage.getBoundingClientRect(), r = el.getBoundingClientRect();
    pop.style.left = Math.max(0, Math.min(r.left - pr.left, pr.width - 320)) + 'px';
    pop.style.top = (r.bottom - pr.top + 8) + 'px';
    var acts = actionsFor(kind);
    pop.innerHTML = '<h6>' + esc(meta.label || key) + '</h6>'
      + '<code>' + esc(meta.loc || key)
      + (meta.stab ? ' <span class="h h-' + esc(meta.stab) + '">' + esc(stabLabel[meta.stab] || meta.stab) + '</span>' : '')
      + '</code>'
      + '<select id="pk-act">' + acts.map(function (a) { return '<option>' + esc(a) + '</option>'; }).join('') + '</select>'
      + '<input id="pk-arg" placeholder="値・期待する文言（任意）">'
      + '<div class="r"><button class="btn sm" id="pk-x">やめる</button>'
      + '<button class="btn sm pri" id="pk-ok">ステップに追加</button></div>';
    stage.appendChild(pop);
    $('#pk-x').addEventListener('click', stopPick);
    $('#pk-ok').addEventListener('click', function () {
      var act = $('#pk-act').value, arg = $('#pk-arg').value.trim();
      var stepKind = /表示|含む|無効/.test(act) ? 'ver' : 'act';
      var s = {
        kind: stepKind, action: act, target: key,
        arg: arg || (act === '押す' ? (meta.label || '') : ''),
        loc: meta.loc || key, stab: meta.stab || 'mid'
      };
      // 挿入位置: 検証は末尾、操作は最後の操作の直後
      var at = t.steps.length;
      if (stepKind === 'act') {
        var li = -1;
        t.steps.forEach(function (x, i) { if (x.kind === 'act') li = i; });
        if (li >= 0) at = li + 1;
        else {
          var fv = t.steps.findIndex(function (x) { return x.kind === 'ver'; });
          at = fv >= 0 ? fv : t.steps.length;
        }
      }
      t.steps.splice(at, 0, s);
      S.step = at;
      stopPick();
      saveSteps(t, 'ステップを追加しました');
    });
  }

  document.addEventListener('click', function (e) {
    if (!picking) return;
    var page = $('#page');
    if (!page || !page.contains(e.target)) return;
    var el = e.target.closest('[data-el]');
    if (!el) return;
    e.stopPropagation();
    openPicker(el);
  }, true);

  /* -------------------------------------------------------------- 実行 */
  function runCurrent() {
    var t = T.current();
    if (!t) return;
    T.setView('test');
    T.runIds([t.id]).catch(function () { });
  }
  T.runCurrent = runCurrent;

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { if (picking) stopPick(); return; }
    var a = document.activeElement;
    if (a && (a.tagName === 'INPUT' || a.tagName === 'SELECT' || a.tagName === 'TEXTAREA' || a.isContentEditable)) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (S.view !== 'test') return;
    if (e.key.toLowerCase() === 'r') { e.preventDefault(); runCurrent(); }
  });

  /* ---------------------------------------------------------- 再描画 */
  var draw = T.repaint(function () { renderHeader(); renderSteps(); });
  T.on('render', draw);
  T.on('select', draw);
  T.on('run', draw);
  T.on('tests', draw);
})();
