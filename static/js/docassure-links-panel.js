/* Document Assurance パネル: 連携（System01 観測 / System02 テスト / System09 影響）。window.DAPanels.links。 */
(function () {
  'use strict';
  window.DAPanels = window.DAPanels || {};
  var STATE = {
    ALIGNED_CANDIDATE: ['観測と一致する候補', 'ok'],
    NOT_OBSERVED: ['観測できませんでした。存在しないとは限りません', 'warn'],
    UNMATCHED_OBSERVATION: ['仕様に無い観測', 'info']
  };
  var NOTE01 = '表示は確定ではなく候補です。観測できなかったことは、存在しないことを意味しません。';

  function fail(esc, r, what) {
    if (r && r.status === 403) { return '<p class="dal-error" role="alert">この操作の権限がありません。管理者に権限を依頼してください。</p>'; }
    var m = r && r.body && r.body.error;
    return '<p class="dal-error" role="alert">' + esc(m || (what + 'を取得できませんでした。時間をおいて再度お試しください。')) + '</p>';
  }
  function netfail(box) { box.innerHTML = '<p class="dal-error" role="alert">通信に失敗しました。接続を確認して再度お試しください。</p>'; }
  function confLabel(c) {
    if (typeof c === 'number') { return c >= 0.7 ? '高' : (c >= 0.4 ? '中' : '低'); }
    var m = { high: '高', medium: '中', low: '低' };
    return m[String(c).toLowerCase()] || (c == null ? '不明' : String(c));
  }
  function evText(ev) {
    return (ev || []).map(function (e) { return typeof e === 'string' ? e : (e && (e.text || e.quote || JSON.stringify(e))) || ''; }).filter(Boolean);
  }
  function detail(esc, src) {
    var ev = evText(src && src.evidence);
    return '<p class="dal-rel">関連度: ' + esc(confLabel(src && src.confidence)) + '</p>' +
      '<details class="dal-det"><summary>詳細（根拠・confidence）</summary><p class="dal-meta">confidence: ' + esc(src && src.confidence != null ? src.confidence : '不明') +
      '　出典: ' + esc((src && src.document) || '') + ' ' + esc((src && src.item_code) || '') + '</p>' +
      (ev.length ? '<ul class="dal-ev">' + ev.map(function (t) { return '<li>' + esc(t) + '</li>'; }).join('') + '</ul>' : '<p class="dal-muted">根拠は記録されていません。</p>') + '</details>';
  }

  /* ---- System01 ---- */
  function bind01(box, ctx) {
    var esc = ctx.esc;
    box.innerHTML = '<p class="dal-muted">読み込み中…</p>';
    ctx.get('system01/sources').then(function (r) {
      if (!r.ok) { box.innerHTML = fail(esc, r, '観測元'); return; }
      var list = (r.body && r.body.sources) || [];
      if (!list.length) { box.innerHTML = '<p class="dal-empty">観測済みのスキャンがありません。System01 でサイトを観測してから再度開いてください。</p>'; return; }
      box.innerHTML = '<label class="dal-label" for="dal-src">観測元のスキャン</label><select id="dal-src" class="dal-sel">' +
        list.map(function (s) { return '<option value="' + esc(s.source_id) + '">' + esc(s.source_id) + '（' + esc(s.target_url) + ' / ' + esc(s.screens) + ' 画面）</option>'; }).join('') +
        '</select> <button type="button" class="c-btn c-btn--secondary" data-dal-load>候補を表示</button><div class="dal-res" data-dal-c aria-live="polite"></div>';
      var res = box.querySelector('[data-dal-c]');
      box.querySelector('[data-dal-load]').addEventListener('click', function () {
        var id = box.querySelector('#dal-src').value;
        res.innerHTML = '<p class="dal-muted">読み込み中…</p>';
        ctx.get('system01/candidates?source=' + encodeURIComponent(id)).then(function (c) {
          if (!c.ok) { res.innerHTML = fail(esc, c, '候補'); return; }
          var cs = (c.body && c.body.candidates) || [];
          if (!cs.length) { res.innerHTML = '<p class="dal-empty">候補がありません。要件を分析してから再度お試しください。</p>'; return; }
          res.innerHTML = '<p class="dal-summary">観測 ' + esc(c.body.observed_count) + ' 件</p>' + cs.map(function (x) {
            var st = STATE[x.state] || [x.state, 'info'], loc = x.location || {};
            return '<article class="dal-item"><h4><span class="dal-badge dal-' + st[1] + '">' + esc(st[0]) + '</span> ' + esc(x.requirement_id || '（要件なし）') + '</h4>' +
              '<p class="dal-meta">source: ' + esc(x.source) + (loc.url ? '　location: ' + esc(loc.url) + ' ' + esc(loc.kind || '') + ' ' + esc(loc.label || '') : '') + '</p>' +
              (x.state === 'NOT_OBSERVED' || x.limitation ? '<p class="dal-note">' + esc(x.limitation || '') + '</p>' : '') + '</article>';
          }).join('');
        }).catch(function () { netfail(res); });
      });
    }).catch(function () { netfail(box); });
  }

  /* ---- System02 ---- */
  function cell(v, yes) { return v === true ? yes : (v === false ? '未' : '未実施'); }
  function loadStatus(box, ctx) {
    var esc = ctx.esc;
    box.innerHTML = '<p class="dal-muted">読み込み中…</p>';
    ctx.get('system02/status').then(function (r) {
      if (!r.ok) { box.innerHTML = fail(esc, r, '状態'); return; }
      var st = (r.body && r.body.status) || {}, ids = Object.keys(st);
      if (!ids.length) { box.innerHTML = '<p class="dal-empty">登録されたテスト案がありません。「テスト案を System02 へ登録」を押してください。</p>'; return; }
      var RES = { PASSED: '合格', FAILED: '不合格', NONE: '未実施' };
      box.innerHTML = '<div class="dal-tw"><table class="dal-tbl"><thead><tr><th scope="col">要件</th><th scope="col">設計済み</th><th scope="col">生成済み</th><th scope="col">実行済み</th><th scope="col">合否</th><th scope="col">検証済み</th></tr></thead><tbody>' +
        ids.map(function (id) {
          var s = st[id];
          return '<tr><th scope="row">' + esc(id) + '</th><td>' + cell(s.designed === true, '設計済み').replace('未実施', '未') + '</td><td>' + (s.generated ? '生成済み' : '未') +
            '</td><td>' + (s.executed === true ? '実行済み' : '未実施') + '</td><td>' + esc(s.executed === true ? (RES[s.result] || s.result) : '未実施') +
            '</td><td>' + (s.verified === true ? '検証済み' : '未検証') + '</td></tr>';
        }).join('') + '</tbody></table></div><p class="dal-muted">テスト案があるだけでは実行済みになりません。</p>';
    }).catch(function () { netfail(box); });
  }
  function bind02(box, ctx, root) {
    var esc = ctx.esc, btn = root.querySelector('[data-dal-push]'), dlg = root.querySelector('[data-dal-dlg]'), msg = root.querySelector('[data-dal-pmsg]');
    var rqb = ctx.data && ctx.data.requirements && ctx.data.requirements.body, n = rqb && rqb.requirements ? rqb.requirements.length : null;
    root.querySelector('[data-dal-count]').textContent = n == null ? '分析した要件のうち、テスト案を作れるもの' : '最大 ' + n + ' 要件分';
    function close() { if (dlg.close) { dlg.close(); } else { dlg.removeAttribute('open'); } btn.focus(); }
    btn.addEventListener('click', function () { if (dlg.showModal) { dlg.showModal(); } else { dlg.setAttribute('open', ''); } dlg.querySelector('[data-dal-ok]').focus(); });
    dlg.querySelector('[data-dal-cancel]').addEventListener('click', close);
    dlg.addEventListener('cancel', function (e) { e.preventDefault(); close(); });
    dlg.querySelector('[data-dal-ok]').addEventListener('click', function () {
      var ok = dlg.querySelector('[data-dal-ok]'); ok.disabled = true;
      ctx.post('system02/push', {}).then(function (r) {
        ok.disabled = false; close();
        if (!r.ok) { msg.innerHTML = fail(esc, r, '登録'); return; }
        var b = r.body || {};
        msg.innerHTML = '<p class="dal-okmsg" role="status">テスト案 ' + esc((b.created || []).length) + ' 件を登録しました（実行はされていません）。前から登録済みで今回は登録しなかったもの ' + esc(Array.isArray(b.already_registered) ? b.already_registered.length : (Number(b.already_registered) || 0)) + ' 件。</p>';
        loadStatus(box, ctx);
      }).catch(function () { ok.disabled = false; close(); netfail(msg); });
    });
    loadStatus(box, ctx);
  }

  /* ---- System09 ---- */
  function list09(esc, title, arr, key) {
    if (!arr || !arr.length) { return '<h5>' + title + '</h5><p class="dal-muted">候補はありません。</p>'; }
    return '<h5>' + title + '</h5>' + arr.map(function (x) {
      var name = x[key] || x.document || '';
      var inner = x.items ? x.items.map(function (it) { return '<div class="dal-sub">' + esc(it.text || it.reason || '') + detail(esc, it) + '</div>'; }).join('') : detail(esc, x.source);
      return '<div class="dal-item"><strong>' + esc(name) + '</strong> <span class="dal-badge dal-info">候補</span>' + (x.basis ? '<p class="dal-meta">' + esc(x.basis) + '</p>' : '') + inner + '</div>';
    }).join('');
  }
  function render09(box, ctx, o) {
    var esc = ctx.esc, a = o.affected || {}, html = '<p class="dal-note">影響範囲は候補です。人の確認で確定します。</p>';
    if (o.status === 'NO_FINDING') { html += '<p class="dal-empty">検出なし（影響なしの証明ではありません）</p>'; }
    if (o.status === 'NOT_EVALUATED') { html += '<p class="dal-empty">評価できませんでした。理由は下記を確認してください。</p>'; }
    html += list09(esc, '影響を受ける文書', a.documents, 'document') + list09(esc, 'モジュール', a.modules, 'module') +
      list09(esc, 'ルート', a.routes, 'route') + list09(esc, 'テスト', a.tests, 'test');
    var ne = o.not_evaluated || [];
    if (ne.length) {
      html += '<h5>評価できなかった範囲</h5><ul class="dal-ev">' + ne.map(function (n) {
        return '<li><strong>' + esc(n.status === 'NO_FINDING' ? '検出なし' : '未評価') + '</strong> ' + esc(n.scope) + '：' + esc(n.reason) + '</li>';
      }).join('') + '</ul>';
    }
    box.innerHTML = html;
  }
  function load09(box, ctx) {
    box.innerHTML = '<p class="dal-muted">読み込み中…</p>';
    return ctx.get('system09/impact').then(function (r) {
      if (r.status === 404) { box.innerHTML = '<p class="dal-empty">まだ影響分析を実行していません。「影響を分析する」を押してください。</p>'; return; }
      if (!r.ok) { box.innerHTML = fail(ctx.esc, r, '影響'); return; }
      render09(box, ctx, r.body || {});
    }).catch(function () { netfail(box); });
  }
  function bind09(box, ctx, root) {
    var btn = root.querySelector('[data-dal-an]'), sys = root.querySelector('[data-dal-sys]'), esc = ctx.esc;
    btn.addEventListener('click', function () {
      btn.disabled = true; box.innerHTML = '<p class="dal-muted">分析中…</p>';
      var body = sys.value.trim() ? { system_id: sys.value.trim() } : {};
      ctx.post('system09/analyze', body).then(function (r) {
        btn.disabled = false;
        if (r.status === 404 && r.body && r.body.code === 'no_previous') { box.innerHTML = '<p class="dal-empty">前の版がありません。文書を更新して再分析してください。</p>'; return; }
        if (r.body && r.body.code === 'no_system') { box.innerHTML = '<p class="dal-error" role="alert">対象システムのIDを入力してから、もう一度分析してください。</p>'; sys.focus(); return; }
        if (!r.ok) { box.innerHTML = fail(esc, r, '分析'); return; }
        render09(box, ctx, r.body || {});
      }).catch(function () { btn.disabled = false; netfail(box); });
    });
    load09(box, ctx);
  }

  window.DAPanels.links = {
    label: '連携',
    html: function (ctx) {
      return '<section class="dal" aria-labelledby="dal-h"><h3 id="dal-h">連携</h3>' +
        '<section class="dal-sec" aria-labelledby="dal-h1"><h4 id="dal-h1">System01 サイト観測</h4><p class="dal-note">' + NOTE01 + '</p><div data-dal-s1></div></section>' +
        '<section class="dal-sec" aria-labelledby="dal-h2"><h4 id="dal-h2">System02 テスト自動化</h4>' +
        '<div class="dal-actions"><button type="button" class="c-btn c-btn--secondary" data-dal-push>テスト案を System02 へ登録</button></div><div data-dal-pmsg aria-live="polite"></div><div data-dal-s2></div>' +
        '<dialog class="dal-dialog" data-dal-dlg aria-labelledby="dal-dh"><h4 id="dal-dh">テスト案を登録しますか</h4>' +
        '<p>登録件数: <span data-dal-count></span></p><p>登録するのは設計案で、実行済みではありません。</p>' +
        '<div class="dal-actions"><button type="button" class="c-btn c-btn--primary" data-dal-ok>登録する</button><button type="button" class="c-btn c-btn--secondary" data-dal-cancel>やめる</button></div></dialog></section>' +
        '<section class="dal-sec" aria-labelledby="dal-h9"><h4 id="dal-h9">System09 影響分析</h4>' +
        '<div class="dal-actions"><label class="dal-label" for="dal-sys">対象システムID（初回のみ）</label><input id="dal-sys" class="dal-sel" data-dal-sys type="text" autocomplete="off">' +
        '<button type="button" class="c-btn c-btn--secondary" data-dal-an>影響を分析する</button></div><div data-dal-s9 aria-live="polite"></div></section></section>';
    },
    bind: function (root, ctx) {
      var b1 = root.querySelector('[data-dal-s1]'), b2 = root.querySelector('[data-dal-s2]'), b9 = root.querySelector('[data-dal-s9]');
      if (!b1 || !b2 || !b9) { return; }
      bind01(b1, ctx); bind02(b2, ctx, root); bind09(b9, ctx, root);
    }
  };
})();
