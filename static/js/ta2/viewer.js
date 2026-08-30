/* ============================================================================
 * TA2 / viewer.js — 右ペイン（実画面ワイヤーフレーム・ハイライト・フィルム） FE-A 所有
 *
 * 失敗時 … 直近失敗のスクリーンショット（/api/ta2/artifact?kind=screenshot）
 * 期待 / いま … report.json 由来の要素辞書（state.elements[screen]）から組み立てる
 * ========================================================================== */
(function () {
  'use strict';
  var T = window.TA2, S = T.state, $ = T.$, $$ = T.$$, esc = T.esc;

  function atLabel(iso) {
    if (!iso) return '';
    var m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(String(iso));
    return m ? (m[2] + '/' + m[3] + ' ' + m[4] + ':' + m[5]) : String(iso);
  }
  function hasRun(t) { return !!(t && t.last && (t.last.run_id || t.last.at)); }

  /* ------------------------------------------------ ステップ → 実要素 */
  /* ステップの target は必ずしも要素辞書のキーと同じ名前ではない
     （例: 送信ボタンは辞書側が btn_0）。名前で引けないときは、
     同じロケータを持つ要素へ読み替える。推測はせず、一致したときだけ結びつける。 */
  function resolveTarget(t, s) {
    if (!s || !s.target || s.target === 'page') return null;
    var els = T.elsOf(t.screen);
    if (els[s.target]) return s.target;
    var loc = (s.fixed && s.issue && s.issue.fix) ? s.issue.fix : s.loc;
    if (!loc) return s.target;
    var hit = null;
    Object.keys(els).forEach(function (k) {
      if (!hit && els[k] && els[k].loc === loc) hit = k;
    });
    return hit || s.target;
  }

  /* -------------------------------------------- ステップからの値の反映 */
  function valueOf(t, key, def) {
    var val = def === undefined ? '' : def;
    (t.steps || []).slice(0, S.step + 1).forEach(function (s) {
      if (resolveTarget(t, s) !== key) return;
      if (s.action === '入力する' || s.action === '選ぶ') val = s.arg || '';
      if (s.action === '入力欄を空のままにする') val = '';
    });
    return val;
  }

  function alertState(t) {
    var st = (t.steps || [])[S.step];
    if (!st || resolveTarget(t, st) !== 'alert') return { cls: 'hidden', txt: '' };
    // 期待モード、または成功しているときだけ検証対象の文言を出す
    if (S.mode === 'expect' || t.status === 'pass' || (S.mode === 'now' && t.status !== 'fail')) {
      return { cls: '', txt: st.arg || '' };
    }
    return { cls: 'hidden', txt: st.arg || '' };
  }

  /* ---------------------------------------------------- ワイヤーフレーム */
  function wireframe(t) {
    var scr = t.screen;
    var meta = T.screenOf(scr);
    var els = T.elsOf(scr);
    var keys = Object.keys(els);
    var step = (t.steps || [])[S.step] || null;
    var stepKey = step ? resolveTarget(t, step) : null;
    var focus = function (k) { return stepKey === k ? ' focus' : ''; };

    var hero = '', fields = '', buttons = '', hasAlert = false;
    keys.forEach(function (k) {
      var m = els[k] || {};
      var kind = T.elKind(m, k);
      if (kind === 'alert') { hasAlert = true; return; }
      if (kind === 'hero') {
        hero += '<div class="hero" data-el="' + esc(k) + '">' + esc(m.label || meta.name || k) + '</div>';
        return;
      }
      if (kind === 'button') {
        buttons += '<span class="cta" data-el="' + esc(k) + '">' + esc(m.label || k) + '</span>';
        return;
      }
      if (kind === 'input' || kind === 'select') {
        var v = valueOf(t, k, '');
        var isSel = kind === 'select';
        // 項目名は必ず label（人が読むラベル）。placeholder は入力欄の中に薄字で置く（B-7）
        var ph = m.placeholder || '';
        var inner = v ? esc(v)
          : (ph ? '<span class="ph">' + esc(ph) + '</span>' : '');
        fields += '<div class="fld">' + esc(m.label || k)
          + '<div class="inp' + focus(k) + '" data-el="' + esc(k) + '">'
          + inner + (isSel ? ' ▾' : '') + '</div></div>';
        return;
      }
      // 文言・見出しなどの読み取り対象
      fields += '<div class="total" data-el="' + esc(k) + '"><span>' + esc(m.label || k) + '</span>'
        + '<span>' + esc(valueOf(t, k, '')) + '</span></div>';
    });

    var a = alertState(t);
    var alertHTML = hasAlert
      ? '<div class="alert ' + a.cls + '" data-el="alert">' + esc(a.txt || '（この画面のエラー表示領域）') + '</div>'
      : '';

    var body = hero + fields + buttons + alertHTML;
    if (!body) {
      body = '<div style="color:var(--tx3);padding:8px 0">この画面の要素はクロール結果に含まれていません</div>';
    }
    return '<h3>' + esc(meta.name || scr) + '</h3>' + body;
  }

  /* ---------------------------------------------------------- 失敗時の絵 */
  function noEvidence(msg) {
    return '<div style="display:grid;place-items:center;height:100%;color:var(--tx3);font-size:12.5px;text-align:center">'
      + esc(msg) + '</div>';
  }

  function renderFailShot(page, t) {
    if (!hasRun(t)) { page.innerHTML = noEvidence('この実行の証跡はありません（まだ実行していません）'); return; }
    /* 証跡は最新の実行分しか残らない。過去の実行での失敗を開いたときに
       取りに行くと、必ず 404 になってコンソールを汚す。実行 ID を先に
       突き合わせ、残っていないと分かっている場合は要求しない。 */
    var latest = (S.runs && S.runs.length) ? String(S.runs[0].run_id || '') : '';
    var mine = String((t.last || {}).run_id || '');
    if (latest && mine && mine !== latest) {
      page.innerHTML = noEvidence('この失敗は過去の実行のものです。証跡は最新の実行分だけ残ります');
      return;
    }
    var url = T.api.artifactUrl(S.domain, t.id, 'screenshot');
    var token = ++failShotSeq;
    page.innerHTML = noEvidence('証跡を読み込んでいます…');
    fetch(url, { credentials: 'same-origin' }).then(function (r) {
      if (token !== failShotSeq) return null;          // 別のテストへ移った後の応答は捨てる
      if (!r.ok) { page.innerHTML = noEvidence('この実行の証跡はありません'); return null; }
      return r.blob();
    }).then(function (blob) {
      if (!blob || token !== failShotSeq) return;
      var src = URL.createObjectURL(blob);
      page.innerHTML = '<img id="fail-shot" alt="失敗時のスクリーンショット"'
        + ' style="display:block;width:100%;height:100%;object-fit:contain;object-position:top center">';
      var img = $('#fail-shot', page);
      if (img) {
        img.addEventListener('load', function () { URL.revokeObjectURL(src); });
        img.src = src;
      }
    }).catch(function () {
      if (token === failShotSeq) page.innerHTML = noEvidence('この実行の証跡を読み込めませんでした');
    });
  }

  var failShotSeq = 0;   // 連続で選び替えたとき、古い応答で上書きしないための世代番号

  /* ------------------------------------------------------------ 描画本体 */
  function renderHighlight(t) {
    var hl = $('#hl');
    if (!hl) return;
    var st = (t.steps || [])[S.step];
    var key = st ? resolveTarget(t, st) : null;
    var el = key ? $('#page [data-el="' + CSS.escape(key) + '"]') : null;
    if (!el) { hl.className = 'hl hide'; return; }
    var browser = document.querySelector('.browser');
    if (!browser) { hl.className = 'hl hide'; return; }
    var pr = browser.getBoundingClientRect(), r = el.getBoundingClientRect();
    hl.style.left = (r.left - pr.left - 3) + 'px';
    hl.style.top = (r.top - pr.top - 3) + 'px';
    hl.style.width = (r.width + 6) + 'px';
    hl.style.height = (r.height + 6) + 'px';
    var issue = st.issue && !st.fixed && (t.status === 'fail' || t.status === 'flaky');
    hl.className = 'hl' + (issue ? ' ng' : st.fixed ? ' ok' : '');
    if (issue) hl.dataset.l = String(st.issue.msg || st.loc).split(' ·')[0];
    else if (st.fixed) hl.dataset.l = '修正後: ' + ((st.issue && st.issue.fix) || st.loc);
    else hl.dataset.l = st.loc || st.target;
  }

  function renderStrip(t) {
    var strip = $('#strip');
    if (!strip) return;
    var failStep = (t.status === 'fail' && t.last && t.last.step !== null && t.last.step !== undefined)
      ? t.last.step : null;
    var n = (t.steps || []).length;
    strip.innerHTML = (t.steps || []).map(function (s, i) {
      var reached = failStep === null || i <= failStep;
      var ng = failStep !== null && i === failStep;
      var lab = (s.kind === 'pre' ? '前提' : 'ステップ ' + i) + ' · ' + (s.action || '')
        + (s.arg ? ' ' + s.arg : '') + (ng ? ' · ここで停止' : reached ? '' : ' · ここまで届いていない');
      return '<div class="th ' + (i === S.step ? 'on' : '') + ' ' + (ng ? 'ng' : '') + ' ' + (reached ? '' : 'na') + '"'
        + ' data-i="' + i + '" role="button" tabindex="0" title="' + esc(lab) + '" aria-label="' + esc(lab) + '">'
        + '<b>' + (s.kind === 'pre' ? '開' : i) + '</b></div>';
    }).join('') + '<span class="lab">' + n + ' ステップ</span>';
  }

  function render() {
    var t = T.current();
    var page = $('#page');
    if (!page) return;
    if (!t) {
      page.innerHTML = noEvidence('テストを選ぶと、その画面が出ます');
      var hl0 = $('#hl'); if (hl0) hl0.className = 'hl hide';
      var strip0 = $('#strip'); if (strip0) strip0.innerHTML = '';
      var url0 = $('#url'); if (url0) url0.textContent = '';
      var vi0 = $('#view-info'); if (vi0) vi0.textContent = '';
      return;
    }

    var meta = T.screenOf(t.screen);
    var url = $('#url');
    if (url) url.textContent = String(meta.path || '').replace(/^https?:\/\//, '');

    $$('#seg button').forEach(function (b) { b.classList.toggle('on', b.dataset.m === S.mode); });

    if (S.mode === 'fail') renderFailShot(page, t);
    else page.innerHTML = wireframe(t);

    var when;
    var at = atLabel(t.last && t.last.at);
    if (t.status === 'fail' && t.last && t.last.step !== null && t.last.step !== undefined) {
      when = 'ステップ ' + t.last.step + ' で停止' + (at ? ' · ' + at : '');
    } else if (hasRun(t)) {
      when = 'ステップ ' + S.step + (at ? ' · 直近の実行 ' + at : '');
    } else {
      when = 'ステップ ' + S.step + ' · 未実行（クロール時の画面）';
    }
    var vi = $('#view-info'); if (vi) vi.textContent = when;

    renderHighlight(t);
    renderStrip(t);
  }

  var draw = T.repaint(render);
  T.on('render', draw);
  T.on('select', draw);
  T.on('run', draw);
  T.on('tests', draw);

  /* ---------------------------------------------------------- bindings */
  var strip = $('#strip');
  if (strip) {
    strip.addEventListener('click', function (e) {
      var th = e.target.closest('.th');
      if (!th) return;
      S.step = +th.dataset.i;
      T.emit('select', T.current());
    });
    strip.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ' && e.key !== 'Spacebar') return;
      var th = e.target.closest && e.target.closest('.th');
      if (!th) return;
      e.preventDefault();
      S.step = +th.dataset.i;
      T.emit('select', T.current());
    });
  }

  $$('#seg button').forEach(function (b) {
    b.addEventListener('click', function () { S.mode = b.dataset.m; draw(); });
  });

  window.addEventListener('resize', draw);
})();
