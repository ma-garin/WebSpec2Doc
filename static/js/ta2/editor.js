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

  /* 削除は取り消せない。押しただけで消えないよう、その場で確認を出す
     （ネイティブの confirm は画面外に出る・文言を揃えられないので使わない） */
  function bindDelete(t) {
    var slot = $('#del-slot');
    if (!slot) return;
    var btn = $('#del-btn');
    if (!btn) return;
    btn.addEventListener('click', function () {
      slot.innerHTML = '<span class="delconf">削除すると戻せません'
        + '<button class="btn sm dang" id="del-yes">削除する</button>'
        + '<button class="btn sm" id="del-no">キャンセル</button></span>';
      var no = $('#del-no'), yes = $('#del-yes');
      if (no) no.addEventListener('click', function () { renderHeader(); });
      if (!yes) return;
      yes.focus();
      yes.addEventListener('click', function () {
        yes.disabled = true;
        var name = t.name, id = t.id;
        T.api.remove(S.domain, id).then(function () {
          return T.loadTests().then(function () {
            S.step = 0;
            T.render();
            T.toast('「' + name + '」（' + id + '）を削除しました', 'ok');
          });
        }, function (err) {
          T.toast('削除できません: ' + err.message, 'ng');
          renderHeader();
        });
      });
    });
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

    box.innerHTML = '<h1 contenteditable="true" spellcheck="false" id="ttl" role="textbox"'
      + ' title="クリックして名前を編集 · Enter で保存 / Esc で取り消し">' + esc(t.name) + '</h1>'
      + '<code>' + esc(t.id) + ' · ' + esc(t.screen) + (t.case_id ? ' · ' + esc(t.case_id) : '') + '</code>'
      + '<span class="pill p-' + esc(running ? 'running' : t.status) + '">'
      + esc(statusLabel[running ? 'running' : t.status] || t.status) + (streak ? ' · 3回連続' : '') + '</span>'
      + '<div class="sp"></div>'
      + '<div class="hist">' + historyHTML(t.history) + '<span>直近10回</span></div>'
      + traceBtn
      + '<button class="btn sm" id="dup-btn" title="このテストを複製">⧉ 複製</button>'
      + '<span id="del-slot"><button class="btn sm dang" id="del-btn" title="このテストを削除">削除</button></span>'
      + runBtn;

    var ttl = $('#ttl');
    var ttlCancel = false;
    ttl.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); e.target.blur(); return; }
      // Esc は「取り消して元の名前へ戻す」。押しても何も戻らないと編集を続けられない
      if (e.key === 'Escape') {
        e.preventDefault(); e.stopPropagation();
        ttlCancel = true;
        e.target.textContent = t.name;
        e.target.blur();
      }
    });
    ttl.addEventListener('blur', function (e) {
      if (ttlCancel) { ttlCancel = false; e.target.textContent = t.name; return; }
      var v = e.target.textContent.trim();
      if (!v || v === t.name) { e.target.textContent = t.name; return; }
      var before = t.name;
      T.api.update(S.domain, t.id, { name: v }).then(function (r) {
        Object.assign(t, r.test || {});
        T.toast('名前を「' + v + '」に変えました', 'ok', {
          label: '元に戻す',
          fn: function () {
            T.api.update(S.domain, t.id, { name: before }).then(function (r2) {
              Object.assign(t, r2.test || {});
              T.toast('名前を戻しました', 'ok');
              T.render();
            }, function (e2) { T.toast(e2.message, 'ng'); });
          }
        });
        T.render();
      }, function (err) {
        e.target.textContent = t.name;
        T.toast(err.message, 'ng');
      });
    });

    $('#dup-btn').addEventListener('click', function () {
      T.api.duplicate(S.domain, t.id).then(function (r) {
        var nid = (r.test && r.test.id) || '';
        return T.loadTests().then(function () {
          if (nid) T.select(nid); else T.render();
          T.toast('「' + t.name + '」を複製しました' + (nid ? ' · ' + nid : '') + '。複製を開いています', 'ok');
        });
      }, function (err) { T.toast(err.message, 'ng'); });
    });

    bindDelete(t);

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
  /** ロケータは画面から直せる（クリック → 入力 → Enter で保存）。
      page.goto / page.url は「開く」「URL が」の擬似ロケータなので編集させない（値の方を直す） */
  function locHTML(s, i) {
    if (s.loc === 'page.goto' || s.loc === 'page.url') return '<span>' + esc(s.loc) + '</span>';
    var issue = s.issue || null;
    var useFix = s.fixed && issue && issue.fix && issue.type === 'missing';
    var loc = useFix ? issue.fix : s.loc;
    var stab = (s.fixed && issue && issue.fix_stab) ? issue.fix_stab : s.stab;
    var out = '<span class="ed" data-edit="loc" data-i="' + i + '" tabindex="0" role="button"'
      + ' title="クリックしてロケータを編集 · Enter で保存 / Esc で取り消し">' + esc(loc) + '</span>';
    if (stab) out += '<span class="h h-' + esc(stab) + '">' + esc(stabLabel[stab] || stab) + '</span>';
    return out;
  }

  /** 直近の失敗の理由をステップ表の先頭に出す。
      これが無いと、失敗の原因は Trace を開くまで画面のどこにも出ていなかった */
  function failSummary(t) {
    if (t.status !== 'fail' && t.status !== 'flaky') return '';
    var last = t.last || {};
    var err = String(last.error || '').trim();
    var hasAt = !!(last.at || last.run_id);
    if (!err && !hasAt) return '';
    var lines = err ? err.split('\n') : [];
    var head = lines.length ? lines[0] : '失敗の理由はサーバから返っていません';
    var rest = lines.slice(1).join('\n').trim();
    var hasStep = last.step !== null && last.step !== undefined;
    var meta = (hasStep ? 'ステップ ' + last.step + ' で停止' : '停止したステップは記録されていません')
      + (last.at ? ' · ' + last.at : '')
      + (last.dur_ms !== null && last.dur_ms !== undefined ? ' · ' + (Number(last.dur_ms) / 1000).toFixed(1) + 's' : '');
    var acts = '';
    if (hasStep) acts += '<button class="btn sm" data-jump="' + last.step + '">止まったステップへ</button>';
    if (hasRun(t)) {
      acts += '<button class="btn sm" id="fs-shot">失敗時の画面</button>'
        + '<button class="btn sm" id="fs-trace">証跡（Trace）</button>';
    }
    return '<div class="failsum"><b>' + esc(head) + '</b>'
      + '<div class="fmeta">' + esc(meta) + '</div>'
      + (rest ? '<pre>' + esc(rest.slice(0, 400)) + '</pre>' : '')
      + (acts ? '<div class="facts">' + acts + '</div>' : '') + '</div>';
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
    var arg = '<em class="ed" data-edit="arg" data-i="' + i + '" tabindex="0" role="button"'
      + ' title="クリックして値を編集 · Enter で保存 / Esc で取り消し">'
      + (s.arg ? esc(s.arg) : '<span class="noval">値なし</span>') + '</em>';
    return '<div class="' + cls + '" data-i="' + i + '" tabindex="' + (i === S.step ? '0' : '-1') + '">'
      + '<div class="n">' + n + '</div>'
      + '<div><div class="v">' + esc(s.action) + ' ' + arg + '</div>'
      + '<div class="loc">' + locHTML(s, i)
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
    var html = failSummary(t);
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
      a.textContent = '右の画面で要素をクリックしてください（Esc でキャンセル）';
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
      var ed = e.target.closest('[data-edit]');
      if (ed) { e.stopPropagation(); startEdit(t, ed); return; }
      var jp = e.target.closest('[data-jump]');
      if (jp) {
        S.step = +jp.dataset.jump;
        renderSteps();
        T.emit('select', t);
        return;
      }
      if (e.target.closest('#fs-shot')) { S.mode = 'fail'; T.emit('select', t); return; }
      if (e.target.closest('#fs-trace')) {
        if (T.has('trace')) T.emit('trace', t);
        else window.open(T.api.artifactUrl(S.domain, t.id, 'trace'), '_blank');
        return;
      }
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
        var di = +dl.dataset.del;
        var gone = t.steps[di];
        var label = (gone.action || '') + (gone.arg ? ' ' + gone.arg : '');
        t.steps.splice(di, 1);
        S.step = Math.min(S.step, t.steps.length - 1);
        // 何を消したかを名指しし、その場で戻せるようにする（消してから気づくのが普通）
        saveSteps(t, '').then(function () {
          T.toast('ステップ「' + label + '」を削除しました', 'ok', {
            label: '元に戻す',
            fn: function () {
              var cur = T.current();
              if (!cur) return;
              cur.steps.splice(Math.min(di, cur.steps.length), 0, gone);
              S.step = di;
              saveSteps(cur, 'ステップを戻しました');
            }
          });
        });
        return;
      }
      var st = e.target.closest('.st');
      if (st) {
        S.step = +st.dataset.i;
        renderSteps();
        T.emit('select', t);
      }
    });

    /* キーボードだけで使えるようにする。ステップカードは Enter/Space で選択、
       ロケータ・値は Enter で編集開始（クリックと同じ入口） */
    stepsBox.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ' && e.key !== 'Spacebar') return;
      var t = T.current();
      if (!t) return;
      var ed = e.target.closest && e.target.closest('[data-edit]');
      if (ed && !ed.querySelector('input')) { e.preventDefault(); startEdit(t, ed); return; }
      var st = e.target.closest && e.target.closest('.st');
      if (st && st === e.target) {
        e.preventDefault();
        S.step = +st.dataset.i;
        renderSteps();
        T.emit('select', t);
        var again = $('#steps .st[data-i="' + S.step + '"]');
        if (again) again.focus();
      }
    });
  }

  /* --------------------------------------------- ロケータ・値のその場編集 */
  function startEdit(t, el) {
    if (el.querySelector('input')) return;
    var i = +el.dataset.i, field = el.dataset.edit, s = (t.steps || [])[i];
    if (!s) return;
    var useFix = !!(s.fixed && s.issue && s.issue.fix && s.issue.type === 'missing');
    var cur = field === 'arg' ? (s.arg || '') : (useFix ? s.issue.fix : (s.loc || ''));
    var inp = document.createElement('input');
    inp.type = 'text';
    inp.className = 'edin';
    inp.value = cur;
    inp.setAttribute('aria-label', field === 'arg' ? '値を編集' : 'ロケータを編集');
    el.textContent = '';
    el.classList.add('editing');
    el.appendChild(inp);
    inp.focus();
    inp.select();
    var done = false;
    function cancel() { if (done) return; done = true; renderSteps(); }
    function save() {
      if (done) return;
      done = true;
      var v = inp.value.trim();
      if (v === cur) { renderSteps(); return; }
      if (field === 'loc' && !v) { T.toast('ロケータは空にできません', 'ng'); renderSteps(); return; }
      if (field === 'arg') s.arg = v;
      else if (useFix) s.issue.fix = v;
      else s.loc = v;
      saveSteps(t, (field === 'arg' ? '値' : 'ロケータ') + 'を保存しました · 実行して確認してください');
    }
    inp.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') { ev.preventDefault(); save(); }
      else if (ev.key === 'Escape') { ev.preventDefault(); ev.stopPropagation(); cancel(); }
    });
    inp.addEventListener('blur', save);
  }

  /* ------------------------------------------------------ 要素ピッカー */
  var picking = false, pop = null;

  function togglePick() {
    if (picking) { stopPick(); return; }
    // 「失敗時」はスクリーンショットなので選べる要素が 1 つも無い。
    // そのまま選択モードに入ると、どこを押しても反応しない行き止まりになる
    var switched = false;
    if (S.mode === 'fail') { S.mode = 'now'; switched = true; T.emit('select', T.current()); }
    picking = true;
    var page = $('#page'); if (page) page.classList.add('pick');
    var a = $('#add-step');
    if (a) { a.classList.add('on'); a.textContent = '右の画面で要素をクリックしてください（Esc でキャンセル）'; }
    var bar = document.createElement('div');
    bar.className = 'pickbar';
    bar.id = 'pickbar';
    bar.innerHTML = (switched ? '「いま」の画面に切り替えました。' : '')
      + '画面上の要素を選ぶと、ステップの候補が出ます <button id="pick-cancel">キャンセル</button>';
    var view = document.querySelector('.view');
    if (view) view.appendChild(bar);
    var c = $('#pick-cancel'); if (c) c.addEventListener('click', stopPick);
    // 何が選べる画面なのかを先に言う。入力欄が無い画面で探し回らせない
    // （描画は次フレームなので、実際に置かれた要素を見てから書く）
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        if (!picking) return;
        var all = $$('#page [data-el]');
        if (!all.length) {
          stopPick();
          T.toast('この画面はクロール結果に要素がありません。◈ サイトの変更で再クロールしてください', 'ng');
          return;
        }
        var n = { inp: $$('#page .inp[data-el]').length, cta: $$('#page .cta[data-el]').length };
        var kinds = [];
        if (n.inp) kinds.push('入力欄 ' + n.inp);
        if (n.cta) kinds.push('ボタン ' + n.cta);
        var other = all.length - n.inp - n.cta;
        if (other > 0) kinds.push('文言・見出し ' + other);
        var b = $('#pickbar');
        if (b) {
          b.innerHTML = (switched ? '「いま」の画面に切り替えました。' : '')
            + 'この画面で選べるのは ' + kinds.join(' · ')
            + ' <button id="pick-cancel">キャンセル</button>';
          var c2 = $('#pick-cancel'); if (c2) c2.addEventListener('click', stopPick);
        }
      });
    });
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
    var acts = actionsFor(kind);
    pop.innerHTML = '<h6>' + esc(meta.label || key) + '</h6>'
      + '<code>' + esc(meta.loc || key)
      + (meta.stab ? ' <span class="h h-' + esc(meta.stab) + '">' + esc(stabLabel[meta.stab] || meta.stab) + '</span>' : '')
      + '</code>'
      + '<select id="pk-act">' + acts.map(function (a) { return '<option>' + esc(a) + '</option>'; }).join('') + '</select>'
      + '<input id="pk-arg" placeholder="値・期待する文言（任意）">'
      + '<div class="r"><button class="btn sm" id="pk-x">キャンセル</button>'
      + '<button class="btn sm pri" id="pk-ok">ステップに追加</button></div>';
    stage.appendChild(pop);
    // 右端・下端の要素でも stage の外へ出さない。実寸を測ってから位置を決める。
    // 下に置けないときは要素の上へ回す（画面外に落ちて操作できなくなるのを防ぐ）
    var pad = 8, pw = pop.offsetWidth, ph = pop.offsetHeight;
    var left = Math.min(Math.max(r.left - pr.left, pad), Math.max(pad, pr.width - pw - pad));
    var top = r.bottom - pr.top + pad;
    if (top + ph + pad > pr.height) {
      var above = r.top - pr.top - ph - pad;
      top = above >= pad ? above : Math.max(pad, pr.height - ph - pad);
    }
    pop.style.left = left + 'px';
    pop.style.top = top + 'px';
    var arg = $('#pk-arg'); if (arg) arg.focus();
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

  /* 選択モード中に関係ない場所を押したら中止する。
     押しても何も起きない状態が続くと「壊れている」ように見えるため（Esc と同じ扱い）*/
  document.addEventListener('click', function (e) {
    if (!picking) return;
    var t = e.target;
    if (!t.closest) return;
    if (t.closest('.pop') || t.closest('#page') || t.closest('#pickbar') || t.closest('#add-step')) return;
    stopPick();
  });

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
