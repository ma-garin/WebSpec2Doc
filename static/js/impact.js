/* 影響度分析（System 08）の画面。API: /api/impact/*（web/routes/impact.py）。
 * 工程: 入力（入力受付・文書確認）→ 変更点と検索（クエリ生成・文書検索・統合）→ 影響と優先度（影響度・優先度の判定）。
 * 選んだ分析は URL の ?job= に持つ。 */
(function () {
  'use strict';
  var $ = function (s) { return document.querySelector(s); };
  var esc = function (v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  var API = '/api/impact/jobs';
  var STEPS = [{ id: 'intake', name: '入力' }, { id: 'search', name: '変更点と検索' }, { id: 'impact', name: '影響と優先度' }];
  var ROLES = { 'new': '変更後', old: '変更前', store: '検索先' };
  var STORES = ['設計書', '画面仕様書', 'テストケース', 'その他'];
  var LVS = [4, 3, 2, 1, 0];
  var LVN = { 4: '致命', 3: '大', 2: '中', 1: '小', 0: '未確認' };
  var state = { jobs: [], job: null, step: 'intake', pri: 0 };

  function api(method, path, body) {
    var opt = { method: method, headers: {} };
    if (body instanceof FormData) opt.body = body;
    else if (body) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    return fetch(path, opt).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) throw new Error(d.error || '処理できませんでした（' + r.status + '）。時間をおいてもう一度お試しください。');
        return d;
      });
    }, function () { throw new Error('サーバにつながりません。画面を再読み込みしてください。'); });
  }
  function banner(msg) { var b = $('#bt-banner'); b.textContent = msg || ''; b.hidden = !msg; }
  function toast(msg) {
    var t = $('#bt-toast'); t.textContent = msg; t.hidden = false;
    clearTimeout(toast.id); toast.id = setTimeout(function () { t.hidden = true; }, 3000);
  }
  function busy(el, on) { if (el) { el.classList.toggle('bt-busy', on); el.disabled = on; } }
  function run(el, p, okMsg) {
    banner(''); busy(el, true);
    return p.then(function (d) {
      if (d.job) setJob(d.job);
      if (d.notes && d.notes.length) banner('取り込めなかった文書があります: ' + d.notes.join(' / '));
      if (okMsg) toast(okMsg);
      return d;
    }).catch(function (e) { banner(e.message); }).then(function (d) { busy(el, false); return d; });
  }
  function fmtTime(t) {
    var d = t ? new Date(t) : null;
    return d && !isNaN(d) ? d.toLocaleString('ja-JP', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
  }

  /* ---- 分析一覧 ---- */
  function loadJobs() {
    return api('GET', API).then(function (d) { state.jobs = d.jobs; renderJobs(); }).catch(function (e) { banner(e.message); });
  }
  function renderJobs() {
    $('#im-cnt').textContent = state.jobs.length;
    var cur = state.job && state.job.id;
    $('#im-jobs').innerHTML = state.jobs.length ? state.jobs.map(function (j) {
      var on = j.id === cur;
      var foot = j.analyzed_at ? '影響 ' + j.impact_count + ' 件（P1 ' + j.p1_count + '）' : '未分析';
      return '<div class="it' + (on ? ' on' : '') + '" role="listitem"><button type="button" class="it-main" data-job="' + esc(j.id) + '" aria-current="' + on + '">'
        + '<i class="' + (j.analyzed_at ? (j.p1_count ? 'i-flaky' : 'i-pass') : 'i-new') + '"></i>'
        + '<span class="grow"><b>' + esc(j.name) + '</b><small>文書 ' + j.docs.length + ' 件 · ' + esc(foot) + '</small><small>' + esc(fmtTime(j.updated_at)) + '</small></span></button>'
        + '<button type="button" class="bt-x" data-deljob="' + esc(j.id) + '" title="この分析を消す" aria-label="' + esc(j.name) + ' を消す">×</button></div>';
    }).join('') : '<div class="it empty">まだ分析がありません</div>';
  }
  function setJob(job) {
    state.job = job;
    var i = state.jobs.findIndex(function (j) { return j.id === job.id; });
    var sum = Object.assign({}, job, { impact_count: job.impacts.length,
      p1_count: job.impacts.filter(function (r) { return r.priority === 1; }).length });
    if (i >= 0) state.jobs[i] = sum; else state.jobs.unshift(sum);
    renderJobs(); render();
  }
  function openJob(id) {
    return api('GET', API + '/' + id).then(function (d) {
      state.step = d.job.analyzed_at ? 'impact' : 'intake'; state.pri = 0;
      history.replaceState(null, '', '?job=' + id); setJob(d.job);
    }).catch(function (e) { banner(e.message); });
  }

  /* ---- 描画 ---- */
  function render() {
    var j = state.job;
    $('#im-empty').hidden = !!j;
    var at = STEPS.findIndex(function (s) { return s.id === state.step; });
    var done = { intake: j && j.docs.length + (j.order ? 1 : 0) > 0, search: j && !!j.analyzed_at, impact: j && !!j.analyzed_at };
    $('#im-steps').innerHTML = STEPS.map(function (s, i) {
      var cls = i === at ? ' on' : (done[s.id] ? ' done' : '');
      var ok = j && (i === 0 || j.analyzed_at);
      return '<button type="button" role="tab" class="bt-step' + cls + '" data-go="' + s.id + '" aria-selected="' + (i === at) + '"' + (ok ? '' : ' disabled') + '><b>' + (done[s.id] && i !== at ? '✓' : i + 1) + '</b><span>' + s.name + '</span></button>';
    }).join('');
    document.querySelectorAll('.rail [data-step]').forEach(function (b) {
      b.classList.toggle('on', !!j && b.dataset.step === state.step);
      b.disabled = !j || (b.dataset.step !== 'intake' && !j.analyzed_at);
    });
    document.querySelectorAll('[data-panel]').forEach(function (p) { p.hidden = !j || p.dataset.panel !== state.step; });
    $('#topbar-title').textContent = STEPS[at].name;
    var notes = j && j.notes && j.notes.length ? j.notes : [];
    $('#im-notes').hidden = !notes.length || state.step === 'intake';
    $('#im-notes').textContent = notes.join(' ');
    if (!j) return;
    renderIntake(j);
    renderSearch(j);
    renderImpact(j);
  }

  function renderIntake(j) {
    var order = $('#im-order');
    if (document.activeElement !== order) order.value = j.order || '';
    $('#im-docs').innerHTML = j.docs.length ? j.docs.map(function (d) {
      var n = esc(d.name);
      return '<tr><td>' + n + '</td>'
        + '<td><select data-doc="' + n + '" data-key="role" aria-label="' + n + ' の使い方">' + Object.keys(ROLES).map(function (k) {
          return '<option value="' + k + '"' + (d.role === k ? ' selected' : '') + '>' + ROLES[k] + '</option>'; }).join('') + '</select></td>'
        + '<td><select data-doc="' + n + '" data-key="store" aria-label="' + n + ' の種類">' + STORES.map(function (k) {
          return '<option' + (d.store === k ? ' selected' : '') + '>' + k + '</option>'; }).join('') + '</select></td>'
        + '<td>' + d.passages + '</td><td><button type="button" class="bt-x" data-deldoc="' + n + '" aria-label="' + n + ' を外す">×</button></td></tr>';
    }).join('') : '<tr><td colspan="5" class="bt-none">まだ文書がありません。変更の内容だけでも分析できます。</td></tr>';
    var stores = STORES.map(function (s) {
      var docs = j.docs.filter(function (d) { return d.store === s && d.role !== 'old'; });
      var last = docs.map(function (d) { return d.indexed_at; }).sort().pop();
      var n = docs.reduce(function (a, d) { return a + d.passages; }, 0);
      return '<li><b>' + s + '</b><small>' + docs.length + ' 文書 ・ ' + n + ' 断片' + (last ? ' ・ 読み取り ' + esc(fmtTime(last)) : '') + '</small>'
        + '<span class="pill ' + (docs.length ? 'p-pass' : 'p-new') + '">' + (docs.length ? 'あり' : 'なし') + '</span></li>';
    });
    $('#im-stores').innerHTML = stores.join('');
    var hasNew = j.docs.some(function (d) { return d.role === 'new'; });
    var hasOld = j.docs.some(function (d) { return d.role === 'old'; });
    $('#im-intake-note').textContent = hasNew && hasOld ? '変更前と変更後の差分から変更箇所を抜き出します。'
      : '変更前の版が無いので、変更の内容（指示）から変更箇所を作ります。';
  }

  function renderSearch(j) {
    $('#im-diffs').innerHTML = j.changes.length ? j.changes.map(function (c) {
      return '<div class="im-diff"><code>' + esc(c.id) + ' ' + esc(c.kind) + '</code><span>' + esc(c.location) + '</span>'
        + '<span>' + (c.before ? '<del>' + esc(c.before) + '</del>' : '<span class="bt-mut">（なし）</span>') + '</span>'
        + '<span>' + (c.after ? '<ins>' + esc(c.after) + '</ins>' : '<span class="bt-mut">（なし）</span>') + '</span></div>';
    }).join('') : '<p class="bt-none">変更箇所はまだありません。</p>';
    var hit = 0;
    $('#im-queries').innerHTML = j.queries.length ? j.queries.map(function (q) {
      hit += q.hit;
      return '<tr><td><code>' + esc(q.id) + '</code></td><td>' + esc(q.from) + '</td><td>' + esc(q.subject.join('・')) + '</td>'
        + '<td>' + esc(q.diff.join('・') || '—') + '</td><td>' + esc(q.stores.join('・') || '—') + '</td><td>' + q.hit + '</td><td>' + q.merged + '</td></tr>';
    }).join('') : '<tr><td colspan="7" class="bt-none">クエリはまだありません。</td></tr>';
    $('#im-qsum').textContent = j.queries.length ? 'ヒット ' + hit + ' 件 → 統合後 ' + j.impacts.filter(function (r) { return r.confirmed; }).length + ' 件' : '';
  }

  function renderImpact(j) {
    var cnt = {};
    j.impacts.forEach(function (r) { cnt[r.level] = (cnt[r.level] || 0) + 1; });
    $('#im-kpis').innerHTML = LVS.map(function (lv) {
      return '<div class="kpi' + (lv === 4 && cnt[4] ? ' ng' : '') + '"><b>' + (cnt[lv] || 0) + '</b><span>影響度 ' + LVN[lv] + '</span></div>';
    }).join('');
    $('#im-filter').innerHTML = [0, 1, 2, 3].map(function (p) {
      return '<button type="button" class="fchip' + (state.pri === p ? ' on' : '') + '" data-pri="' + p + '">' + (p ? 'P' + p : 'すべて') + '</button>';
    }).join('');
    var rows = j.impacts.filter(function (r) { return !state.pri || r.priority === state.pri; });
    $('#im-shown').textContent = rows.length + ' 件';
    $('#im-csv').href = API + '/' + j.id + '/export.csv';
    $('#im-csv').setAttribute('aria-disabled', String(!j.impacts.length));
    $('#im-rows').innerHTML = rows.length ? rows.map(function (r) {
      return '<tr><td><span class="im-pri p' + r.priority + '">P' + r.priority + '</span></td>'
        + '<td>' + esc(r.place || r.location) + '<small>' + esc(r.doc || '') + ' · 変更 ' + esc(r.changes.join('・')) + '</small></td>'
        + '<td><span class="im-lv l' + r.level + '">' + esc(r.level_name) + '</span></td><td>' + esc(r.why) + '</td>'
        + '<td>' + (r.doc ? esc(r.doc) + ' ' + esc(r.location) + '<q>' + esc(r.quote) + '</q>' : '<span class="bt-mut">見つからない</span>') + '</td>'
        + '<td>' + esc(r.test) + '</td></tr>';
    }).join('') : '<tr><td colspan="6" class="bt-none">' + (j.analyzed_at ? 'この優先度の影響はありません。' : 'まだ分析していません。') + '</td></tr>';
  }

  /* ---- 操作 ---- */
  function upload(files) {
    if (!state.job || !files.length) return;
    var fd = new FormData();
    Array.prototype.forEach.call(files, function (f) { fd.append('files', f); });
    run($('#im-drop'), api('POST', API + '/' + state.job.id + '/docs', fd), files.length + ' 件の文書を取り込みました');
  }
  document.addEventListener('click', function (e) {
    var t = e.target.closest('[data-go],[data-step],[data-pri],[data-job],[data-deljob],[data-deldoc],#im-new,#im-newcancel,#im-run');
    if (!t || t.disabled) return;
    if (t.dataset.go || t.dataset.step) { state.step = t.dataset.go || t.dataset.step; render(); return; }
    if (t.dataset.pri != null) { state.pri = Number(t.dataset.pri); renderImpact(state.job); return; }
    if (t.dataset.job) { openJob(t.dataset.job); return; }
    if (t.dataset.deljob) {
      var id = t.dataset.deljob;
      run(t, api('DELETE', API + '/' + id), '分析を消しました').then(function () {
        state.jobs = state.jobs.filter(function (j) { return j.id !== id; });
        if (state.job && state.job.id === id) { state.job = null; history.replaceState(null, '', location.pathname); }
        renderJobs(); render();
      });
      return;
    }
    if (t.dataset.deldoc) { run(t, api('DELETE', API + '/' + state.job.id + '/docs/' + encodeURIComponent(t.dataset.deldoc)), '文書を外しました'); return; }
    if (t.id === 'im-new') { $('#im-newform').hidden = false; $('#im-newname').focus(); return; }
    if (t.id === 'im-newcancel') { $('#im-newform').hidden = true; return; }
    if (t.id === 'im-run') {
      run(t, api('POST', API + '/' + state.job.id + '/analyze', { order: $('#im-order').value }), '分析しました').then(function (d) {
        if (d && d.job) { state.step = 'impact'; state.pri = 0; render(); }
      });
    }
  });
  document.addEventListener('change', function (e) {
    var s = e.target.closest('select[data-doc]');
    if (s) { var b = {}; b[s.dataset.key] = s.value; run(null, api('PATCH', API + '/' + state.job.id + '/docs/' + encodeURIComponent(s.dataset.doc), b)); }
    if (e.target.id === 'im-file') { upload(e.target.files); e.target.value = ''; }
    if (e.target.id === 'im-order' && state.job) run(null, api('PATCH', API + '/' + state.job.id, { order: e.target.value }));
  });
  $('#im-newform').addEventListener('submit', function (e) {
    e.preventDefault();
    var name = $('#im-newname').value.trim();
    if (!name) return;
    run(null, api('POST', API, { name: name }), '分析を作りました').then(function (d) {
      if (d && d.job) { $('#im-newform').hidden = true; $('#im-newname').value = ''; state.step = 'intake'; history.replaceState(null, '', '?job=' + d.job.id); render(); }
    });
  });
  var drop = $('#im-drop');
  ['dragover', 'dragenter'].forEach(function (ev) { drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add('over'); }); });
  ['dragleave', 'drop'].forEach(function (ev) { drop.addEventListener(ev, function () { drop.classList.remove('over'); }); });
  drop.addEventListener('drop', function (e) { e.preventDefault(); upload(e.dataTransfer.files); });

  loadJobs().then(function () {
    var id = new URLSearchParams(location.search).get('job') || (state.jobs[0] && state.jobs[0].id);
    if (id) openJob(id); else render();
  });
})();
