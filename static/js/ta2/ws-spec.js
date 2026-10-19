/* ws-spec.js — 仕様ワークスペース
 * A7: 画面一覧（#screen-items）＋画面仕様（#spec-screen）
 * A8: テストケース表（#spec-cases）＋書き出し（#spec-export-pop）＋CTA（#spec-cta-tests）
 * マークアップと CSS は docs/design/ideas/workspace-mockup.html の #p-spec から写す。
 * 画面仕様の中身は static/js/view-report.js renderReportDetail の移植（bbox ハイライトは持たない）。
 */
(function () {
  'use strict';
  var T = window.TA2;
  if (!T) return;
  var S = T.state, esc = T.esc;

  /* テストケース表（view-testcase-grid.js / testcase-grid-edit.js）は core.js の
     グローバルを前提にしている。core.js は旧シェル専用で読み込めないため、
     表が実際に呼ぶ 2 つだけを最小実装で補う（未定義なら ReferenceError で表が落ちる）。 */
  if (typeof window.escHtml !== 'function') {
    window.escHtml = function (s) { return T.esc(s); };
  }
  if (typeof window.confirmDialog !== 'function') {
    window.confirmDialog = function (o) {
      o = o || {};
      var msg = (o.title ? o.title + '\n\n' : '') + (o.message || '');
      return Promise.resolve(window.confirm(msg));
    };
  }

  var $ = function (s) { return document.querySelector(s); };
  var enc = encodeURIComponent;
  var mode = 'screen';      // screen | cases
  var loading = null;       // 読み込み中の Promise（多重取得を防ぐ）
  var casesDomain = '';     // テストケース表をマウント済みのドメイン
  var bound = false;

  /* ------------------------------------------------------------------ data */

  // 一般 API は T.api.get を通す（A3 で公開）。未公開の環境でも動くよう素の fetch に落とす。
  function getJson(url) {
    if (T.api && typeof T.api.get === 'function') return T.api.get(url);
    return rawJson(url);
  }
  // /preview は JSON 以外も返す共用ルートで Content-Type 判定に乗らないため素で読む。
  function rawJson(url) {
    return fetch(url, { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
      .then(function (res) {
        return res.json().then(function (json) {
          if (json && json.error) throw new Error(json.error);
          if (!res.ok) throw new Error('通信に失敗しました（HTTP ' + res.status + '）');
          return json;
        }, function () { throw new Error('サーバの応答を解釈できませんでした'); });
      }, function () { throw new Error('サーバに接続できませんでした'); });
  }

  function loadReport(domain) {
    return getJson('/api/result?domain=' + enc(domain)).then(function (res) {
      var files = (res && res.files) || {};
      var path = files.json || files['report.json'];   // /api/result は論理名（json）で返す
      if (!path) throw new Error('この解析には report.json がありません');
      // 撮れている画面を先に知る。無い画面へ画像を取りに行くと 404 になり、
      // 利用者には見えない失敗（コンソールエラー）だけが増える
      var shots = {};
      ((res && res.screenshots) || []).forEach(function (p) {
        var base = String(p).split('/').pop().replace(/\.png$/, '');
        if (/_full$/.test(base)) return;   // 全体版は拡大用。カードにはビューポート版を出す
        shots[base] = String(p);
      });
      return rawJson('/preview?path=' + enc(path)).then(function (report) {
        return { report: report, shots: shots };
      });
    });
  }

  function loadSpec() {
    var domain = T.state.domain;
    if (!domain) return Promise.reject(new Error('対象サイトが選ばれていません'));
    var cur = T.state.spec;
    if (cur && cur.domain === domain) return Promise.resolve(cur);
    if (loading) return loading;
    loading = Promise.all([
      T.api.map(domain).then(null, function () { return { screens: [] }; }),
      loadReport(domain)
    ]).then(function (r) {
      loading = null;
      var rep = r[1] || {};
      T.state.spec = {
        domain: domain, map: r[0] || { screens: [] },
        report: rep.report || {}, shots: rep.shots || {}, sel: ''
      };
      return T.state.spec;
    }, function (e) { loading = null; throw e; });
    return loading;
  }

  /* --------------------------------------------------------------- helpers */

  function screensOf() {
    var sp = T.state.spec;
    return (sp && sp.report && sp.report.screens) || [];
  }
  function pathOf(sc) {
    var u = String(sc.url || '');
    try { var o = new URL(u); return (o.pathname || '/') + (o.search || ''); } catch (e) { return u; }
  }
  function titleOf(id) {
    var list = screensOf();
    for (var i = 0; i < list.length; i++) if (list[i].page_id === id) return list[i].title || id;
    return id;
  }
  // 項目名は人が読める名前を優先する。placeholder は「入力例」であって項目名ではないので使わない。
  function fieldLabel(f) {
    return String(f.label || f.label_text || f.aria_label || f.name || '(無名)');
  }
  function constraintText(f) {
    var p = [];
    if (f.maxlength !== null && f.maxlength !== undefined) p.push('最大' + f.maxlength + '文字');
    if (f.minlength !== null && f.minlength !== undefined) p.push('最小' + f.minlength + '文字');
    if (f.min_value) p.push('min=' + f.min_value);
    if (f.max_value) p.push('max=' + f.max_value);
    if (f.pattern) p.push('pattern=' + f.pattern);
    if (f.placeholder) p.push('例: ' + f.placeholder);
    if (f.options && f.options.length) p.push('選択肢: ' + f.options.filter(Boolean).join(' / ').slice(0, 120));
    return p.join(' · ');
  }
  function coverageOf(id) {
    var sp = T.state.spec;
    var list = (sp && sp.map && sp.map.screens) || [];
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
    return null;
  }

  /* ---------------------------------------------------------------- render */

  function renderList() {
    var box = $('#screen-items');
    if (!box) return;
    var sp = T.state.spec;
    var sel = (sp && sp.sel) || '';
    var html = screensOf().map(function (sc) {
      var cv = coverageOf(sc.page_id) || {};
      var pct = Math.max(0, Math.min(100, Number(cv.coverage || 0)));
      var color = pct >= 80 ? 'var(--ok)' : (pct > 0 ? 'var(--wa)' : 'var(--line2)');
      // 親が role="listbox" なので、子は role="option" でなければならない（WCAG 1.3.1）。
      // role="button" を入れると支援技術には「選べる一覧」として伝わらない。
      return '<div class="it' + (sc.page_id === sel ? ' on' : '')
        + '" role="option" aria-selected="' + (sc.page_id === sel ? 'true' : 'false')
        + '" tabindex="' + (sc.page_id === sel ? '0' : '-1') + '"' +
        ' data-pid="' + T.esc(sc.page_id) + '">' +
        '<span class="cov"><i style="width:' + pct + '%;background:' + color + '"></i></span>' +
        '<span class="grow"><b>' + T.esc(sc.title || sc.page_id) + '</b>' +
        '<small>' + T.esc(sc.page_id + ' · ' + pathOf(sc)) + '</small></span>' +
        '</div>';
    }).join('');
    box.innerHTML = html || '<div class="it"><span class="grow"><b>画面がありません</b>' +
      '<small>解析結果に画面が含まれていません</small></span></div>';
  }

  function fieldsCardHtml(sc) {
    var forms = (sc.forms || []).filter(function (f) { return (f.fields || []).length > 0; });
    if (!forms.length) return elementsCardHtml(sc);
    return forms.map(function (fm, fi) {
      var fields = fm.fields || [];
      var req = fields.filter(function (f) { return f.required; }).length;
      var rows = fields.map(function (f) {
        var label = fieldLabel(f);
        var name = String(f.name || '');
        var loc = (f.locators || [])[0] || '';
        var cons = constraintText(f);
        var conds = (f.test_conditions || []).filter(Boolean);
        return '<tr>' +
          '<td><b>' + T.esc(label) + '</b>' + (name && name !== label ? '<br><code>' + T.esc(name) + '</code>' : '') + '</td>' +
          '<td>' + T.esc(f.field_type || '') + '</td>' +
          '<td>' + (f.required ? '<span class="req">必須</span>' : '<span class="opt">任意</span>') + '</td>' +
          '<td>' + (loc ? '<code>' + T.esc(loc) + '</code>' : '') +
          (cons ? (loc ? ' · ' : '') + T.esc(cons) : (loc ? '' : '—')) +
          (conds.length
            ? '<ul class="cond">' + conds.map(function (c) { return '<li>' + T.esc(c) + '</li>'; }).join('') + '</ul>'
            : '') +
          '</td></tr>';
      }).join('');
      return '<div class="card" style="margin-bottom:14px">' +
        '<h3>入力項目' + (forms.length > 1 ? '（フォーム ' + (fi + 1) + '）' : '') + '</h3>' +
        '<div class="sub">' + fields.length + ' 項目 · 必須 ' + req +
        (fm.action ? ' · フォーム送信先 ' + T.esc(fm.action) + '（' + T.esc(String(fm.method || 'get').toUpperCase()) + '）' : '') +
        '</div>' +
        '<table class="fields"><thead><tr>' +
        '<th style="width:150px">項目</th><th style="width:70px">種別</th><th style="width:60px">必須</th>' +
        '<th>制約とテスト条件</th></tr></thead><tbody>' + rows + '</tbody></table>' +
        '</div>';
    }).join('');
  }

  // フォームが無い画面でもカードを空にしない（何も無いのか取れなかったのかが分からなくなるため）
  function elementsCardHtml(sc) {
    var rows = []
      .concat((sc.headings || []).filter(Boolean).map(function (h) { return ['見出し', h]; }))
      .concat((sc.buttons || []).filter(Boolean).map(function (b) { return ['ボタン', b]; }));
    var body = rows.length
      ? rows.map(function (r) {
        return '<tr><td style="width:90px">' + T.esc(r[0]) + '</td><td>' + T.esc(r[1]) + '</td></tr>';
      }).join('')
      : '<tr><td colspan="2">解析できる要素が見つかりませんでした。</td></tr>';
    return '<div class="card" style="margin-bottom:14px">' +
      '<h3>ページ要素</h3><div class="sub">入力フォームはありません</div>' +
      '<table class="fields"><thead><tr><th style="width:90px">種別</th><th>内容</th></tr></thead>' +
      '<tbody>' + body + '</tbody></table></div>';
  }

  function transitionsCardHtml(sc) {
    var tr = sc.transitions || {};
    var col = function (label, ids) {
      var items = (ids || []).filter(Boolean);
      return '<div><b style="font-size:11px;color:var(--tx3)">' + label + '</b>' +
        '<ul class="cond" style="padding-left:15px">' +
        (items.length
          ? items.map(function (id) { return '<li>' + T.esc(titleOf(id)) + '</li>'; }).join('')
          : '<li>—</li>') +
        '</ul></div>';
    };
    return '<div class="card"><h3>この画面から / この画面へ</h3><div class="sub">遷移表より</div>' +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;font-size:12.5px">' +
      col('遷移先', tr.to) + col('遷移元', tr.from) + '</div></div>';
  }

  function shotCardHtml(sc) {
    var sp = T.state.spec;
    var meta = (sp && sp.report && sp.report.meta) || {};
    var when = meta.crawled_at ? '解析 ' + T.esc(meta.crawled_at) : '';
    var file = ((sp && sp.shots) || {})[sc.page_id] || '';
    var src = T.api.screenshotUrl(T.state.domain, sc.page_id);
    // 代替は同じ画像の直接配信。/api/ta2/screenshot が返せないときでも証跡を見せる
    var alt = file ? '/preview?path=' + enc(file) : '';
    var body = file
      ? '<img id="spec-shot-img" src="' + T.esc(src) + '" data-alt="' + T.esc(alt) + '"' +
        ' alt="' + T.esc(sc.title || sc.page_id) + '"' +
        ' style="width:100%;height:100%;object-fit:contain;object-position:top center;display:block">'
      : '<p style="padding:16px;font-size:12px;color:var(--tx3)" role="status">' +
        'この画面のスクリーンショットはありません</p>';
    return '<div class="shot-card">' +
      '<div class="ph2"><span>実画面</span><span>' + when + '</span></div>' +
      '<div class="im" id="spec-shot">' + body + '</div></div>';
  }


  /** この画面から設計されたテストの要約。仕様だけ見せて終わると
   *  「分析したその先」が別モードに隠れたままになる。件数と技法、
   *  まだテストしていない箇所を、同じ画面で示す。 */
  function testsCardHtml(sc) {
    var pid = String(sc.page_id || '');
    var sp = T.state.spec || {};
    var m = ((sp.map && sp.map.screens) || []).filter(function (x) { return x.id === pid; })[0];
    if (!m) return '';
    var gaps = m.gaps || [];
    var body;
    if (!m.tests) {
      body = '<div class="sub">この画面のテストはまだありません。'
        + '地図から生成できます。</div>';
    } else {
      body = '<div class="spec-tests-row">'
        + '<span><b>' + m.tests + '</b> 件のテスト</span>'
        + (m.fails ? '<span class="ng"><b>' + m.fails + '</b> 件が失敗</span>' : '')
        + '<span class="tx3">網羅 ' + m.coverage + '%</span>'
        + '</div>';
    }
    var holes = gaps.length
      ? '<div class="sub" style="margin-top:8px">まだテストしていない箇所（' + gaps.length + '）</div>'
        + '<ul class="cond">' + gaps.slice(0, 4).map(function (g) {
            return '<li>' + esc(g.title || '') + '</li>';
          }).join('') + '</ul>'
      : '';
    return '<div class="card"><h3>この画面のテスト</h3>'
      + '<div class="sub">設計したケースと、足りていない箇所</div>'
      + body + holes
      + '<div class="spec-tests-act">'
      + '<a class="btn sm" href="/sites/' + encodeURIComponent(S.domain) + '/tests">テストを見る</a>'
      + '<button type="button" class="btn sm" data-spec-mode="cases">テストケース表を開く</button>'
      + '</div></div>';
  }

  function renderDetail(sc) {
    var host = $('#spec-screen');
    if (!host) return;
    if (!sc) {
      host.innerHTML = '<div class="card"><h3>画面がありません</h3>' +
        '<div class="sub">この解析には画面が含まれていません。</div></div>';
      return;
    }
    // #spec-screen 自身が .spec-grid（左＝仕様カード列 / 右＝実画面）
    host.innerHTML =
      '<div style="overflow:auto;min-height:0">' + fieldsCardHtml(sc)
        + testsCardHtml(sc) + transitionsCardHtml(sc) + '</div>' +
      shotCardHtml(sc);
    // 証跡が無いことを黙って隠さない（撮れていないのか出せていないのかが分からなくなるため）
    var img = host.querySelector('#spec-shot-img');
    if (img) {
      img.addEventListener('error', function () {
        var next = img.dataset.alt;
        if (next) { img.dataset.alt = ''; img.src = next; return; }
        var box = host.querySelector('#spec-shot');
        if (box) {
          box.innerHTML = '<p style="padding:16px;font-size:12px;color:var(--tx3)" role="status">' +
            'この画面のスクリーンショットはありません</p>';
        }
      });
    }
    var h1 = $('#spec-title') || $('#p-spec .ph h1');
    if (h1) h1.textContent = sc.title || sc.page_id;
    var code = $('#spec-sub') || $('#p-spec .ph code');
    if (code) code.textContent = sc.page_id + ' · ' + pathOf(sc);
  }

  function showError(msg) {
    var host = $('#spec-screen');
    if (host) {
      host.innerHTML = '<div class="card"><h3>仕様を読み込めませんでした</h3>' +
        '<div class="sub">' + T.esc(msg || '通信エラー') + '</div></div>';
    }
  }


  /** 最初に開く画面。並び順の先頭は入力フォームが無いトップページのことが多く、
   *  「ページ要素 4 行」だけの画面が最初に出ると、何ができるツールなのか伝わらない。
   *  入力項目を持つ画面があれば、その中で項目が最も多いものを開く。 */
  function firstInformative(list) {
    var best = null, bestN = 0;
    (list || []).forEach(function (sc) {
      var n = 0;
      (sc.forms || []).forEach(function (f) { n += ((f && f.fields) || []).length; });
      if (n > bestN) { bestN = n; best = sc; }
    });
    if (best) return best.page_id;
    return (list && list[0] && list[0].page_id) || '';
  }

  function selectScreen(pid) {
    var sp = T.state.spec;
    if (!sp) return;
    var target = null;
    screensOf().forEach(function (sc) { if (sc.page_id === pid) target = sc; });
    if (!target) return;
    sp.sel = pid;
    if (mode === 'tech' && T.techRender) T.techRender(pid);
    var box = $('#screen-items');
    if (box) {
      Array.prototype.forEach.call(box.querySelectorAll('.it'), function (el) {
        el.classList.toggle('on', el.dataset.pid === pid);
      });
    }
    renderDetail(target);
  }

  /* ------------------------------------------------------------ mode / A8 */

  function setMode(m) {
    mode = m;
    var screen = $('#spec-screen'), cases = $('#spec-cases');
    // hidden 属性だけだとパネル側の display 指定に負けることがあるため両方で切る
    var tech = $('#spec-tech');
    if (screen) { screen.hidden = (m !== 'screen'); screen.style.display = m === 'screen' ? '' : 'none'; }
    if (cases) { cases.hidden = (m !== 'cases'); cases.style.display = m === 'cases' ? '' : 'none'; }
    if (tech) { tech.hidden = (m !== 'tech'); tech.style.display = m === 'tech' ? '' : 'none'; }
    var reverse = $('#spec-reverse');
    if (reverse) { reverse.hidden = (m !== 'reverse'); reverse.style.display = m === 'reverse' ? '' : 'none'; }
    var seg = $('#spec-seg');
    if (seg) {
      Array.prototype.forEach.call(seg.querySelectorAll('button'), function (b, i) {
        var key = b.dataset.m || ['screen', 'cases', 'tech', 'map'][i];
        b.classList.toggle('on', key === m);
      });
    }
    if (m === 'cases') mountCases();
    if (m === 'tech' && T.techRender) T.techRender((T.state.spec || {}).sel || '');
    if (m === 'reverse' && T.reverseRender && reverse) T.reverseRender(reverse, T.state.domain);
  }

  function mountCases() {
    var host = $('#spec-cases');
    var domain = T.state.domain;
    if (!host || !domain) return;
    if (typeof window.tcgMountGrid !== 'function') {
      host.innerHTML = '<div class="card"><h3>テストケース表を表示できません</h3>' +
        '<div class="sub">テストケース表のスクリプトが読み込まれていません。</div></div>';
      return;
    }
    if (casesDomain === domain && host.querySelector('.tcg-wrap')) return;
    casesDomain = domain;
    Promise.resolve(window.tcgMountGrid(host, domain, {})).then(null, function () { casesDomain = ''; });
  }

  function syncLinks() {
    var domain = T.state.domain || '';
    var pop = $('#spec-export-pop');
    if (pop) {
      // 中身はモック（#ex-pop）と同じ 3 項目。テンプレートは空の器だけを持つ
      pop.innerHTML =
        '<a role="menuitem" id="spec-ex-xlsx" href="/api/export/spec-xlsx?domain=' + T.esc(enc(domain)) + '">' +
        'Excel（仕様書）<small>.xlsx</small></a>' +
        '<a role="menuitem" id="spec-ex-zip" href="/download-zip?domain=' + T.esc(enc(domain)) + '">' +
        '全成果物<small>.zip</small></a>' +
        '<a role="menuitem" id="spec-ex-ts" href="/api/report/' + T.esc(enc(domain)) + '/spec-ts"' +
        ' title="Playwright 用の候補データがある解析でのみ書き出せます（無い解析では開いた先で理由を表示します）">' +
        'Playwright 用スペック<small>.spec.ts</small></a>';
    }
    var cta = $('#spec-cta-tests');
    if (cta) cta.href = '/sites/' + enc(domain) + '/tests';
  }

  // 開閉は app.js bindUserMenu と同方式（外側クリックと Escape で閉じる）
  function bindExport() {
    var btn = $('#spec-export-btn'), pop = $('#spec-export-pop');
    if (!btn || !pop) return;
    function setOpen(v) {
      pop.hidden = !v;
      btn.setAttribute('aria-expanded', v ? 'true' : 'false');
      if (v) { var f = pop.querySelector('a,button'); if (f) f.focus(); }
    }
    setOpen(false);
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      setOpen(pop.hidden);
    });
    document.addEventListener('click', function (e) {
      if (pop.hidden) return;
      if (e.target.closest && e.target.closest('.pop-wrap')) return;
      setOpen(false);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape' || pop.hidden) return;
      setOpen(false);
      btn.focus();
    });
  }

  function bindOnce() {
    /* spec-mode-delegate: カード内から表モードへ移れるようにする */
    document.addEventListener('click', function (e) {
      var b = e.target.closest && e.target.closest('[data-spec-mode]');
      if (b) { e.preventDefault(); setMode(b.getAttribute('data-spec-mode')); }
    });

    if (bound) return;
    bound = true;
    var box = $('#screen-items');
    if (box) {
      box.addEventListener('click', function (e) {
        var it = e.target.closest && e.target.closest('.it[data-pid]');
        if (!it) return;
        if (T.state.view !== 'spec') { T.setView('spec'); }
        setMode('screen');
        selectScreen(it.dataset.pid);
      });
      box.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        var it = e.target.closest && e.target.closest('.it[data-pid]');
        if (!it) return;
        e.preventDefault();
        it.click();
      });
    }
    var seg = $('#spec-seg');
    if (seg) {
      Array.prototype.forEach.call(seg.querySelectorAll('button'), function (b, i) {
        var key = b.dataset.m || ['screen', 'cases', 'map'][i];
        b.addEventListener('click', function () {
          if (key === 'map') { T.setView('site'); return; }
          setMode(key);
        });
      });
    }
    bindExport();
  }

  /* ------------------------------------------------------------------ boot */

  function ensure(withDetail) {
    if (!$('#p-spec') && !$('#screen-items')) return;
    bindOnce();
    syncLinks();
    loadSpec().then(function (sp) {
      renderList();
      if (!withDetail) return;
      var list = screensOf();
      var sel = sp.sel || firstInformative(list) || '';
      setMode(mode);
      if (sel) selectScreen(sel); else renderDetail(null);
    }, function (e) {
      if (withDetail) showError(e && e.message);
    });
  }

  T.on('view', function (v) {
    if (v === 'spec') ensure(true);
    else if (v === 'site') ensure(false);
  });
  T.on('boot', function () {
    if (T.state.view === 'spec') ensure(true);
    else if (T.state.view === 'site') ensure(false);
  });
})();
