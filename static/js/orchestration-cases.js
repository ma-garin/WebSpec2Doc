/* 指揮ホーム「案件概況」。/api/home/cases を読み、案件 → 段 → 名指し → 判定 を描く（読み取りのみ）。
   状態は #cs-root の data-state（normal/empty/no-match/loading/error/forbidden/dirty/conflict/restored）。 */
(function () {
  'use strict';
  var root = document.getElementById('cs-root');
  if (!root) return;
  var $ = function (id) { return document.getElementById(id); };
  var data = null, selected = null, lastUpdated = null;
  var params = new URLSearchParams(location.search);
  var restoredId = params.get('case');
  var STATE_TEXT = {
    loading: '案件の状況を読み込んでいます。',
    empty: 'QA 案件がまだありません。サイトを追加するか、仕様評価で検査を作ると、ここに案件として並びます。',
    'no-match': '条件に合う案件がありません。絞り込みの文字を消すと全件に戻ります。',
    error: '案件の状況を読み込めませんでした。再読み込みしてください。続く場合は管理者に連絡してください。',
    forbidden: '案件を見る権限がありません。閲覧の役割を管理者に依頼してください。',
    dirty: 'この画面は読み取りのみです。未保存の変更はありません。編集は各段の画面で行います。',
    conflict: '読み込み中に他の人が記録を更新しました。再読み込みして最新の状態を確認してください。',
    restored: '前回開いていた案件を復元しました。'
  };
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function setState(st, extra) {
    root.setAttribute('data-state', st);
    var msg = STATE_TEXT[st] || '';
    var b = $('cs-banner');
    b.className = 'cs-banner' + (msg && st !== 'normal' ? ' is-' + st : '');
    b.innerHTML = msg && st !== 'normal' ? '<p>' + esc(msg) + (extra ? ' ' + esc(extra) : '') + '</p>' +
      (st === 'error' || st === 'conflict' ? '<button type="button" class="c-btn" data-act="reload">再読み込み</button>' : '') : '';
    $('cs-empty').innerHTML = (st === 'empty' || st === 'no-match') ? '<p>' + esc(msg) + '</p>' +
      (st === 'empty' ? '<p><a class="c-btn" href="/orchestration?mode=detail">サイトを追加</a> <a class="c-btn" href="/docverify">仕様評価を始める</a></p>'
        : '<p><button type="button" class="c-btn" data-act="clear">絞り込みを解除</button></p>') : '';
  }
  function stageOf(c, key) { return c.stages.filter(function (s) { return s.key === key; })[0]; }
  function rowHtml(c) {
    var cur = stageOf(c, c.current_stage);
    var n = c.counts;
    var named = (n['重大'] ? '<span class="cs-k k-crit">重大 ' + n['重大'] + '</span>' : '') +
      (n['欠落'] ? '<span class="cs-k k-miss">欠落 ' + n['欠落'] + '</span>' : '') +
      (n['未検証'] ? '<span class="cs-k k-unv">未検証 ' + n['未検証'] + '</span>' : '');
    return '<tr class="cs-row' + (selected === c.id ? ' is-sel' : '') + '" data-id="' + esc(c.id) + '" tabindex="0" aria-selected="' + (selected === c.id) + '">' +
      '<td><span class="cs-title">' + esc(c.title) + '</span><span class="cs-sub">' + (c.kind === 'site' ? 'サイト案件' : '仕様評価案件') + '</span></td>' +
      '<td><span class="cs-st st-' + esc(cur.state) + '">' + esc(cur.label) + '・' + esc(cur.state_label) + '</span></td>' +
      '<td class="cs-ks">' + named + '</td></tr>';
  }
  function visible() {
    var q = ($('cs-q').value || '').trim().toLowerCase();
    return data.cases.filter(function (c) { return !q || String(c.title).toLowerCase().indexOf(q) >= 0; });
  }
  function renderDetail(c) {
    if (!c) { $('cs-stages').innerHTML = ''; $('cs-stage-body').innerHTML = ''; $('cs-named').innerHTML = ''; $('cs-evidence').innerHTML = ''; return; }
    $('cs-stages').innerHTML = c.stages.map(function (s, i) {
      return '<li class="cs-step st-' + esc(s.state) + (s.key === c.current_stage ? ' is-cur' : '') + '">' +
        '<span class="cs-step__no">' + (i + 1) + '</span><span class="cs-step__name">' + esc(s.label) + '</span>' +
        '<span class="cs-step__st">' + esc(s.state_label) + '</span></li>';
    }).join('');
    $('cs-stage-body').innerHTML = '<h3 class="cs-case">' + esc(c.title) + '</h3>' +
      '<table class="cs-stagetbl"><thead><tr><th scope="col">段</th><th scope="col">状態</th><th scope="col">いまの事実</th><th scope="col">入口</th></tr></thead><tbody>' +
      c.stages.map(function (s) {
        return '<tr><th scope="row">' + esc(s.label) + '<span class="cs-sub">System ' + esc(s.owner) + '</span></th>' +
          '<td><span class="cs-st st-' + esc(s.state) + '">' + esc(s.state_label) + '</span></td>' +
          '<td>' + esc(s.summary) + '</td><td>' + (s.href ? '<a class="cs-go" href="' + esc(s.href) + '">' + esc(s.label) + 'を開く</a>' : '<span class="cs-sub">入口はまだありません</span>') + '</td></tr>';
      }).join('') + '</tbody></table>' +
      (c.target ? '<p class="cs-sub"><a href="' + esc(c.detail_href) + '">この案件の実行の進み具合を詳しく見る</a></p>' : '');
    $('cs-named').innerHTML = c.named.length ? '<ul class="cs-namedlist">' + c.named.map(function (i) {
      var k = i.kind === '重大' ? 'k-crit' : i.kind === '欠落' ? 'k-miss' : 'k-unv';
      return '<li><span class="cs-k ' + k + '">' + esc(i.kind) + '</span><span class="cs-sub">' + esc(i.stage) + '</span>' +
        (i.href ? '<a href="' + esc(i.href) + '">' + esc(i.text) + '</a>' : '<span>' + esc(i.text) + '</span>') + '</li>';
    }).join('') + '</ul>' : '<p class="cs-sub">止めているものはありません。</p>';
    $('cs-evidence').innerHTML = '<dl class="cs-ev"><dt>最終更新</dt><dd>' + esc(c.updated_at || '記録なし') + '</dd>' +
      '<dt>人の判定</dt><dd>' + esc(c.verdict.decision_note) + '</dd></dl>';
    var g = function (id, v) {
      var row = $(id); row.querySelector('.cs-gate__val').textContent = v.value;
      row.querySelector('.cs-gate__why').textContent = v.reason;
      row.setAttribute('data-verdict', v.value);
    };
    g('cs-gate-all', c.verdict.overall); g('cs-gate-chg', c.verdict.changed);
  }
  function render() {
    var list = visible();
    if (!data.cases.length) { setState('empty'); $('cs-rows').innerHTML = ''; renderDetail(null); return; }
    if (!list.length) { setState('no-match'); $('cs-rows').innerHTML = ''; renderDetail(null); return; }
    if (!selected || !list.some(function (c) { return c.id === selected; })) selected = list[0].id;
    $('cs-rows').innerHTML = list.map(rowHtml).join('');
    renderDetail(list.filter(function (c) { return c.id === selected; })[0]);
    var partial = data.partial_errors && data.partial_errors.length;
    if (root.getAttribute('data-state') === 'loading' || root.getAttribute('data-state') === 'empty' || root.getAttribute('data-state') === 'no-match') setState('normal');
    if (partial) {
      $('cs-banner').className = 'cs-banner is-error';
      $('cs-banner').innerHTML = '<p>一部の記録を読めませんでした。該当する段は「未検証」として扱っています。再読み込みしてください。</p>';
    }
  }
  function select(id) {
    selected = id; setState("normal");
    var u = new URL(location.href); u.searchParams.set('case', id); history.replaceState(null, '', u);
    render();
  }
  function load() {
    setState('loading');
    fetch('/api/home/cases', { headers: { Accept: 'application/json' }, credentials: 'same-origin' })
      .then(function (r) {
        if (r.status === 403) { setState('forbidden'); return null; }
        return r.json().then(function (j) { if (!r.ok) throw new Error((j.error && j.error.message) || ''); return j; });
      })
      .then(function (j) {
        if (!j) return;
        var conflict = lastUpdated && data && JSON.stringify(data.cases) !== JSON.stringify(j.cases);
        data = j; lastUpdated = j.updated_at;
        if (restoredId && j.cases.some(function (c) { return c.id === restoredId; })) {
          selected = restoredId; restoredId = null; render(); setState('restored'); return;
        }
        render();
        if (conflict) setState('conflict');
        var forced = params.get('state'); if (forced) force(forced);
      })
      .catch(function () { setState('error'); });
  }
  function force(st) {
    if (st === 'normal') { if (data) render(); return; }
    if (st === 'empty') { $('cs-rows').innerHTML = ''; renderDetail(null); }
    if (st === 'no-match') { $('cs-rows').innerHTML = ''; renderDetail(null); }
    setState(st);
  }
  root.addEventListener('click', function (e) {
    var tr = e.target.closest('.cs-row'); if (tr) { select(tr.getAttribute('data-id')); return; }
    var a = e.target.closest('[data-act]'); if (!a) return;
    if (a.getAttribute('data-act') === 'reload') load();
    if (a.getAttribute('data-act') === 'clear') { $('cs-q').value = ''; render(); }
  });
  root.addEventListener('keydown', function (e) {
    var tr = e.target.closest && e.target.closest('.cs-row');
    if (tr && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); select(tr.getAttribute('data-id')); }
  });
  $('cs-q').addEventListener('input', function () { if (data) render(); });
  $('cs-reload').addEventListener('click', load);
  document.querySelectorAll('.cs-statebtn').forEach(function (b) {
    b.addEventListener('click', function () { force(b.getAttribute('data-force')); });
  });
  load();
})();
