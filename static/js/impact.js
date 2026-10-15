/* 影響度分析（System 08）の画面。API: /api/impact/*（web/routes/impact.py）。
 * 表示は ホーム（入口と分析の一覧）・文書庫・分析（入力 → 変更点と検索 → 影響と優先度）の 3 つ。
 * どれを開いているかは URL（?job= / ?view=library）に持つ。 */
(function () {
  'use strict';
  var $ = function (s) { return document.querySelector(s); };
  var $$ = function (s) { return Array.prototype.slice.call(document.querySelectorAll(s)); };
  var esc = function (v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  var API = '/api/impact/jobs';
  var STEPS = [{ id: 'intake', name: '入力' }, { id: 'search', name: '変更点と検索' }, { id: 'impact', name: '影響と優先度' }];
  var ROLES = { 'new': '変更後', old: '変更前', store: '検索先' };
  var STORES = ['設計書', '画面仕様書', 'テストケース', 'その他'];
  var LVN = { 4: '致命', 3: '大', 2: '中', 1: '小', 0: '未確認' };
  var RV = { accepted: '採用', rejected: '除外' };
  var state = { view: 'home', jobs: null, job: null, step: 'intake', pri: 0, lib: [], engine: null };

  /* ---- 共通 ---- */
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
  function busy(el, on, label) {
    if (!el) return;
    el.classList.toggle('bt-busy', on); el.disabled = on;
    if (label) { if (on) { el.dataset.label = el.textContent; el.textContent = label; } else if (el.dataset.label) el.textContent = el.dataset.label; }
  }
  function run(el, p, okMsg, label) {
    banner(''); busy(el, true, label);
    return p.then(function (d) {
      if (d.job) setJob(d.job);
      if (d.library) { state.lib = d.library.docs; renderLibBadge(); }
      if (d.notes && d.notes.length) banner('取り込めなかった文書があります: ' + d.notes.join(' / '));
      if (okMsg) toast(okMsg);
      return d;
    }).catch(function (e) { banner(e.message); }).then(function (d) { busy(el, false); return d; });
  }
  function fmtTime(t) {
    var d = t ? new Date(t) : null;
    return d && !isNaN(d) ? d.toLocaleString('ja-JP', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
  }
  function effPri(r) { return (r.review && r.review.priority) || r.priority; }
  function summarize(job) {
    return Object.assign({}, job, { impact_count: job.impacts.length,
      p1_count: job.impacts.filter(function (r) { return effPri(r) === 1 && !(r.review && r.review.status === 'rejected'); }).length });
  }

  /* ---- 表示の切り替え ---- */
  function go(view, push) {
    state.view = view;
    if (view !== 'job') state.job = null;
    var url = view === 'library' ? '?view=library' : view === 'job' && state.job ? '?job=' + state.job.id : location.pathname;
    history[push ? 'pushState' : 'replaceState'](null, '', url);
    render();
  }
  function render() {
    $$('[data-view-panel]').forEach(function (p) { p.hidden = p.dataset.viewPanel !== state.view; });
    $$('.app-nav-item[data-view]').forEach(function (b) {
      var on = b.dataset.view === state.view; b.classList.toggle('is-active', on);
      if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
    var inJob = state.view === 'job' && !!state.job;
    $('#im-navjob-h').hidden = !inJob;
    $$('.app-nav-item[data-step]').forEach(function (b) {
      b.hidden = !inJob;
      b.classList.toggle('is-active', inJob && b.dataset.step === state.step);
      b.disabled = inJob && b.dataset.step !== 'intake' && !state.job.analyzed_at;
    });
    var crumb = $('.app-topbar-crumb, #topbar-crumb');
    var title = { home: 'ダッシュボード', library: '文書庫' }[state.view] || (state.job ? state.job.name : '');
    $('#topbar-title').textContent = title;
    if (crumb) crumb.textContent = state.view === 'job' ? '影響度分析 › ' + (STEPS.find(function (s) { return s.id === state.step; }) || {}).name : '影響度分析';
    document.title = title + ' - 影響度分析 - WebSpec2Doc';
    renderEngine();
    if (state.view === 'home') renderHome();
    if (state.view === 'library') renderLibrary();
    if (inJob) renderJob();
  }
  function renderEngine() {
    var e = state.engine;
    var txt = !e ? '' : e.available ? 'AI で判定（' + e.model + '）' : '規則で判定（AI 未接続）';
    $('#im-hero-engine').textContent = txt ? '判定: ' + txt : '';
    var eg = $('#im-engine'); eg.hidden = !e; eg.textContent = txt;
    eg.className = 'pill ' + (e && e.available ? 'p-pass' : 'p-new');
  }
  function renderLibBadge() {
    var bd = $('#im-libbd'); bd.hidden = !state.lib.length; bd.textContent = state.lib.length;
  }

  /* ---- ホーム ---- */
  function renderHome() {
    var body = $('#im-home-body');
    if (state.jobs === null) { body.innerHTML = '<div class="empty">読み込み中...</div>'; return; }
    if (!state.jobs.length) {
      body.innerHTML = '<div class="dashboard-empty">'
        + '<div class="dashboard-empty-icon" aria-hidden="true">🎯</div>'
        + '<div class="dashboard-empty-title">まだ分析がありません</div>'
        + '<div class="dashboard-empty-desc">変更の内容と仕様書を入れると、影響する設計書・画面・既存テストを探し、テストの優先度を根拠つきで出します。</div>'
        + '<div class="onboard-steps">'
        + '<div class="onboard-step"><span class="onboard-num">1</span><strong>変更と文書を入れる</strong><span>変更の内容と、変更前後の仕様書を取り込む</span></div><div class="onboard-arrow">→</div>'
        + '<div class="onboard-step"><span class="onboard-num">2</span><strong>変更点を抜き出して検索</strong><span>差分から検索語を作り、検索先の文書を探す</span></div><div class="onboard-arrow">→</div>'
        + '<div class="onboard-step"><span class="onboard-num">3</span><strong>影響と優先度を判断</strong><span>根拠を見て採否と優先度を決め、書き出す</span></div></div>'
        + '<button type="button" class="btn-primary im-bigbtn" data-act="new">最初の分析を始める</button>'
        + '<button type="button" class="btn-sample-report" data-act="sample">見本で試す<span class="sample-zero">文書なし</span></button>'
        + '<p class="im-hint">所要時間の目安: 文書 10 本で数秒（AI 判定ありは 10〜30 秒）</p></div>';
      return;
    }
    body.innerHTML = '<div class="im-jobs">' + state.jobs.map(function (j) {
      var status = j.analyzed_at ? (j.p1_count ? '<span class="pill p-fail">P1 ' + j.p1_count + ' 件</span>' : '<span class="pill p-pass">P1 なし</span>')
        : '<span class="pill p-new">未分析</span>';
      return '<article class="im-jobcard"><button type="button" class="im-jobmain" data-job="' + esc(j.id) + '">'
        + '<span class="im-jobname">' + esc(j.name) + '</span>'
        + '<span class="im-joborder">' + esc(j.order || '変更の内容はまだありません') + '</span>'
        + '<span class="im-jobfoot">' + status + '<span>影響 ' + (j.impact_count || 0) + ' 件</span><span>文書 ' + j.docs.length + ' 件</span><span>' + esc(fmtTime(j.updated_at)) + '</span></span>'
        + '</button><button type="button" class="bt-x im-jobdel" data-deljob="' + esc(j.id) + '" aria-label="' + esc(j.name) + ' を消す" title="この分析を消す">×</button></article>';
    }).join('') + '</div>';
  }

  /* ---- 文書庫 ---- */
  function renderLibrary() {
    var counts = STORES.map(function (s) {
      var n = state.lib.filter(function (d) { return d.store === s; }).length;
      return '<div class="kpi"><b>' + n + '</b><span>' + s + '</span></div>';
    });
    $('#im-libsum').innerHTML = '<div class="kpis">' + counts.join('') + '</div>';
    $('#im-lib-body').innerHTML = state.lib.length ? '<div class="bt-card bt-card-flush"><div class="bt-tblwrap"><table class="bt-tbl" aria-label="文書庫の文書">'
      + '<thead><tr><th>文書</th><th>種類</th><th>断片</th><th>読み取り</th><th><span class="visually-hidden">削除</span></th></tr></thead><tbody>'
      + state.lib.map(function (d) {
        var n = esc(d.name);
        return '<tr><td>' + n + '</td><td><select data-libdoc="' + n + '" aria-label="' + n + ' の種類">' + STORES.map(function (k) {
          return '<option' + (d.store === k ? ' selected' : '') + '>' + k + '</option>'; }).join('') + '</select></td>'
          + '<td>' + d.passages + '</td><td>' + esc(fmtTime(d.indexed_at)) + '</td>'
          + '<td><button type="button" class="bt-x" data-dellib="' + n + '" aria-label="' + n + ' を文書庫から外す">×</button></td></tr>';
      }).join('') + '</tbody></table></div></div>'
      : '<div class="dashboard-empty"><div class="dashboard-empty-icon" aria-hidden="true">📚</div><div class="dashboard-empty-title">文書庫はまだ空です</div>'
        + '<div class="dashboard-empty-desc">いつも検索先にする設計書・画面仕様書・既存テストケースを入れておくと、分析のたびに取り込み直さずに済みます。</div>'
        + '<label class="btn-primary im-bigbtn" for="im-libfile">文書を入れる</label></div>';
  }

  /* ---- 分析 ---- */
  function setJob(job) {
    state.job = job;
    if (state.jobs) {
      var i = state.jobs.findIndex(function (j) { return j.id === job.id; });
      if (i >= 0) state.jobs[i] = summarize(job); else state.jobs.unshift(summarize(job));
    }
    if (state.view === 'job') render();
  }
  function openJob(id, step, push) {
    return api('GET', API + '/' + id).then(function (d) {
      state.job = d.job; state.view = 'job'; state.pri = 0;
      state.step = step || (d.job.analyzed_at ? 'impact' : 'intake');
      history[push ? 'pushState' : 'replaceState'](null, '', '?job=' + id); render();
    }).catch(function (e) { banner(e.message); go('home'); });
  }
  function renderJob() {
    var j = state.job;
    $('#im-jobname').textContent = j.name;
    $('#im-jobmeta').textContent = j.analyzed_at ? '分析 ' + fmtTime(j.analyzed_at) + (j.engine && j.engine.mode === 'llm' ? '（AI）' : '（規則）') : 'まだ分析していません';
    var at = STEPS.findIndex(function (s) { return s.id === state.step; });
    var done = { intake: j.docs.length + (j.order ? 1 : 0) > 0, search: !!j.analyzed_at, impact: !!j.analyzed_at };
    $('#im-steps').innerHTML = STEPS.map(function (s, i) {
      var cls = i === at ? ' on' : (done[s.id] ? ' done' : '');
      var ok = i === 0 || j.analyzed_at;
      return '<button type="button" role="tab" class="bt-step' + cls + '" data-go="' + s.id + '" aria-selected="' + (i === at) + '"' + (ok ? '' : ' disabled title="先に分析してください"') + '><b>' + (done[s.id] && i !== at ? '✓' : i + 1) + '</b><span>' + s.name + '</span></button>';
    }).join('');
    $$('[data-panel]').forEach(function (p) { p.hidden = p.dataset.panel !== state.step; });
    var notes = (j.notes || []).concat(j.engine && j.engine.mode === 'rule' && j.engine.reason && j.analyzed_at ? [j.engine.reason] : []);
    $('#im-notes').hidden = !notes.length || state.step === 'intake';
    $('#im-notes').textContent = notes.join(' ');
    var p1 = j.impacts.filter(function (r) { return effPri(r) === 1 && !(r.review && r.review.status === 'rejected'); }).length;
    $('#im-p1bd').hidden = !p1; $('#im-p1bd').textContent = p1;
    renderIntake(j); renderSearch(j); renderImpact(j);
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
        + '<td>' + d.passages + '</td>'
        + '<td>' + (d.role === 'store' ? '<button type="button" class="btn-outline-sm" data-tolib="' + n + '" title="どの分析でも検索先に使う">文書庫へ</button>' : '') + '</td>'
        + '<td><button type="button" class="bt-x" data-deldoc="' + n + '" aria-label="' + n + ' を外す">×</button></td></tr>';
    }).join('') : '<tr><td colspan="6" class="bt-none">まだ文書がありません。変更の内容だけでも分析できます。</td></tr>';
    $('#im-stores').innerHTML = STORES.map(function (s) {
      var mine = j.docs.filter(function (d) { return d.store === s && d.role !== 'old'; });
      var lib = state.lib.filter(function (d) { return d.store === s; });
      var n = mine.length + lib.length;
      return '<li><b>' + s + '</b><small>この分析 ' + mine.length + ' ・ 文書庫 ' + lib.length + '</small>'
        + '<span class="pill ' + (n ? 'p-pass' : 'p-new') + '">' + (n ? 'あり' : 'なし') + '</span></li>';
    }).join('');
    $('#im-libcnt').textContent = state.lib.length;
    var hasNew = j.docs.some(function (d) { return d.role === 'new'; });
    var hasOld = j.docs.some(function (d) { return d.role === 'old'; });
    $('#im-intake-note').textContent = hasNew && hasOld ? '変更前と変更後の差分から変更箇所を抜き出します。'
      : '変更前の版が無いので、変更の内容（指示）から変更箇所を作ります。';
    $('#im-run').textContent = j.analyzed_at ? '分析し直す →' : '分析する →';
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
  function reviewCell(r) {
    var v = r.review || {};
    return '<div class="im-rv" data-iid="' + esc(r.id) + '">'
      + ['accepted', 'rejected'].map(function (k) {
        return '<button type="button" class="im-rvbtn' + (v.status === k ? ' on ' + k : '') + '" data-rv="' + k + '" aria-pressed="' + (v.status === k) + '">' + RV[k] + '</button>';
      }).join('')
      + '<select data-rvpri aria-label="優先度を直す"><option value="">P 自動</option>' + [1, 2, 3].map(function (p) {
        return '<option value="' + p + '"' + (v.priority === p ? ' selected' : '') + '>P' + p + '</option>'; }).join('') + '</select>'
      + '<input data-rvnote maxlength="500" placeholder="メモ（理由）" value="' + esc(v.note || '') + '" aria-label="判断のメモ"></div>';
  }
  function renderImpact(j) {
    var cnt = {};
    j.impacts.forEach(function (r) { cnt[r.level] = (cnt[r.level] || 0) + 1; });
    $('#im-kpis').innerHTML = [4, 3, 2, 1, 0].map(function (lv) {
      return '<div class="kpi' + (lv === 4 && cnt[4] ? ' ng' : '') + '"><b>' + (cnt[lv] || 0) + '</b><span>影響度 ' + LVN[lv] + '</span></div>';
    }).join('');
    $('#im-filter').innerHTML = [0, 1, 2, 3].map(function (p) {
      var n = p ? j.impacts.filter(function (r) { return effPri(r) === p; }).length : j.impacts.length;
      return '<button type="button" class="fchip' + (state.pri === p ? ' on' : '') + '" data-pri="' + p + '">' + (p ? 'P' + p : 'すべて') + ' <em>' + n + '</em></button>';
    }).join('');
    var rows = j.impacts.filter(function (r) { return !state.pri || effPri(r) === state.pri; });
    var rv = j.impacts.filter(function (r) { return r.review && r.review.status; }).length;
    $('#im-shown').textContent = '判断済み ' + rv + ' / ' + j.impacts.length;
    ['xlsx', 'csv'].forEach(function (k) {
      var a = $('#im-' + k); a.href = API + '/' + j.id + '/export.' + k; a.setAttribute('aria-disabled', String(!j.impacts.length));
    });
    $('#im-rows').innerHTML = rows.length ? rows.map(function (r) {
      var p = effPri(r), rej = r.review && r.review.status === 'rejected';
      return '<tr' + (rej ? ' class="im-rej"' : '') + '><td><span class="im-pri p' + p + '">P' + p + '</span>' + (p !== r.priority ? '<small>元 P' + r.priority + '</small>' : '') + '</td>'
        + '<td>' + esc(r.place || r.location) + '<small>' + esc(r.doc || '') + (r.doc ? ' · ' : '') + '変更 ' + esc(r.changes.join('・')) + '</small></td>'
        + '<td><span class="im-lv l' + r.level + '">' + esc(r.level_name) + '</span><small>' + (r.method === 'llm' ? 'AI' : '規則') + '</small></td>'
        + '<td>' + esc(r.why) + '</td>'
        + '<td>' + (r.doc ? esc(r.doc) + ' ' + esc(r.location) + '<q>' + esc(r.quote) + '</q>' : '<span class="bt-mut">見つからない</span>') + '</td>'
        + '<td>' + esc(r.test) + '</td><td>' + reviewCell(r) + '</td></tr>';
    }).join('') : '<tr><td colspan="7" class="bt-none">' + (j.analyzed_at ? 'この優先度の影響はありません。' : 'まだ分析していません。') + '</td></tr>';
  }
  function saveReview(box, status) {
    var cur = (state.job.impacts.find(function (r) { return r.id === box.dataset.iid; }) || {}).review || {};
    var st = status == null ? (cur.status || '') : (cur.status === status ? '' : status);
    run(null, api('PATCH', API + '/' + state.job.id + '/impacts/' + box.dataset.iid,
      { status: st, priority: box.querySelector('[data-rvpri]').value, note: box.querySelector('[data-rvnote]').value }));
  }

  /* ---- 操作 ---- */
  function openModal(order) {
    $('#im-modal').hidden = false; $('#im-neworder').value = order || '';
    $('#im-newname').value = order ? order.replace(/\s+/g, ' ').slice(0, 30) : '';
    $('#im-newname').focus();
  }
  function closeModal() { $('#im-modal').hidden = true; }
  function upload(files, path, okMsg, el) {
    if (!files.length) return;
    var fd = new FormData();
    Array.prototype.forEach.call(files, function (f) { fd.append('files', f); });
    return run(el, api('POST', path, fd), files.length + ' 件の文書を' + okMsg, '読み取り中...');
  }
  document.addEventListener('click', function (e) {
    var t = e.target.closest('[data-act],[data-view],[data-go],[data-step],[data-pri],[data-job],[data-deljob],[data-deldoc],[data-tolib],[data-dellib],[data-rv],#im-run');
    if (!t || t.disabled) return;
    var act = t.dataset.act;
    if (act === 'new') { openModal(''); return; }
    if (act === 'close') { closeModal(); return; }
    if (act === 'reload') { loadJobs(); return; }
    if (act === 'sample') {
      run(t, api('POST', '/api/impact/sample'), '見本の分析を作りました', '作成中...').then(function (d) {
        if (d && d.job) { state.jobs = null; loadJobs(); openJob(d.job.id, 'impact', true); }
      });
      return;
    }
    if (t.dataset.view) { go(t.dataset.view, true); return; }
    if (t.dataset.go || t.dataset.step) {
      state.step = t.dataset.go || t.dataset.step; render();
      var c = $('#app-content'); if (c) c.scrollTop = 0;
      return;
    }
    if (t.dataset.pri != null) { state.pri = Number(t.dataset.pri); renderImpact(state.job); return; }
    if (t.dataset.job) { openJob(t.dataset.job, null, true); return; }
    if (t.dataset.rv) { saveReview(t.closest('.im-rv'), t.dataset.rv); return; }
    if (t.dataset.deljob) {
      var id = t.dataset.deljob, j = (state.jobs || []).find(function (x) { return x.id === id; });
      if (!window.confirm('「' + (j ? j.name : '') + '」を消します。取り込んだ文書と判断も消え、元に戻せません。')) return;
      run(t, api('DELETE', API + '/' + id), '分析を消しました').then(function (d) {
        if (d) { state.jobs = state.jobs.filter(function (x) { return x.id !== id; }); renderHome(); }
      });
      return;
    }
    if (t.dataset.deldoc) { run(t, api('DELETE', API + '/' + state.job.id + '/docs/' + encodeURIComponent(t.dataset.deldoc)), '文書を外しました'); return; }
    if (t.dataset.tolib) { run(t, api('POST', API + '/' + state.job.id + '/docs/' + encodeURIComponent(t.dataset.tolib) + '/library'), '文書庫に入れました'); return; }
    if (t.dataset.dellib) {
      if (!window.confirm('「' + t.dataset.dellib + '」を文書庫から外します。以後の分析で検索先に使われなくなります。')) return;
      run(t, api('DELETE', '/api/impact/library/' + encodeURIComponent(t.dataset.dellib)), '文書庫から外しました').then(function () { render(); });
      return;
    }
    if (t.id === 'im-run') {
      run(t, api('POST', API + '/' + state.job.id + '/analyze', { order: $('#im-order').value }), '分析しました', '分析中...').then(function (d) {
        if (d && d.job) { state.step = 'impact'; state.pri = 0; render(); }
      });
    }
  });
  document.addEventListener('change', function (e) {
    var s = e.target.closest('select[data-doc]');
    if (s) { var b = {}; b[s.dataset.key] = s.value; run(null, api('PATCH', API + '/' + state.job.id + '/docs/' + encodeURIComponent(s.dataset.doc), b)); return; }
    var l = e.target.closest('select[data-libdoc]');
    if (l) { run(null, api('PATCH', '/api/impact/library/' + encodeURIComponent(l.dataset.libdoc), { store: l.value }), '種類を変えました'); return; }
    if (e.target.matches('[data-rvpri],[data-rvnote]')) { saveReview(e.target.closest('.im-rv'), null); return; }
    if (e.target.id === 'im-file') { upload(e.target.files, API + '/' + state.job.id + '/docs', '取り込みました', $('#im-drop')); e.target.value = ''; return; }
    if (e.target.id === 'im-libfile') {
      var p = upload(e.target.files, '/api/impact/library', '文書庫に入れました', null); e.target.value = '';
      if (p) p.then(function () { render(); });
      return;
    }
    if (e.target.id === 'im-order' && state.job) run(null, api('PATCH', API + '/' + state.job.id, { order: e.target.value }));
  });
  $('#im-hero-form').addEventListener('submit', function (e) { e.preventDefault(); openModal($('#im-hero-order').value.trim()); });
  $('#im-newform').addEventListener('submit', function (e) {
    e.preventDefault();
    var name = $('#im-newname').value.trim(), order = $('#im-neworder').value.trim();
    if (!name) return;
    var btn = e.submitter;
    run(btn, api('POST', API, { name: name }).then(function (d) {
      return order ? api('PATCH', API + '/' + d.job.id, { order: order }) : d;
    }), '分析を作りました').then(function (d) {
      if (d && d.job) { closeModal(); $('#im-hero-order').value = ''; if (state.jobs) state.jobs.unshift(summarize(d.job)); openJob(d.job.id, 'intake', true); }
    });
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !$('#im-modal').hidden) closeModal(); });
  $('#im-modal').addEventListener('click', function (e) { if (e.target.id === 'im-modal') closeModal(); });
  var drop = $('#im-drop');
  ['dragover', 'dragenter'].forEach(function (ev) { drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add('over'); }); });
  ['dragleave', 'drop'].forEach(function (ev) { drop.addEventListener(ev, function () { drop.classList.remove('over'); }); });
  drop.addEventListener('drop', function (e) { e.preventDefault(); upload(e.dataTransfer.files, API + '/' + state.job.id + '/docs', '取り込みました', drop); });

  /* サイドバーの折りたたみ（ドキュメント作成と同じ保存キー） */
  var SIDEBAR_KEY = 'webspec2doc.sidebar-collapsed';
  function applyCollapsed(c) { $('.app-shell').classList.toggle('sidebar-collapsed', c); $('#sidebar-toggle-btn').title = c ? 'サイドバーを広げる' : 'サイドバーを折りたたむ'; }
  try { applyCollapsed(localStorage.getItem(SIDEBAR_KEY) === '1'); } catch (err) { /* 保存できない環境では既定のまま */ }
  $('#sidebar-toggle-btn').addEventListener('click', function () {
    var c = !$('.app-shell').classList.contains('sidebar-collapsed'); applyCollapsed(c);
    try { localStorage.setItem(SIDEBAR_KEY, c ? '1' : '0'); } catch (err) { /* 同上 */ }
  });

  /* ---- 読み込み ---- */
  function loadJobs() {
    return api('GET', API).then(function (d) { state.jobs = d.jobs; if (state.view === 'home') renderHome(); })
      .catch(function (e) { state.jobs = []; banner(e.message); renderHome(); });
  }
  function boot() {
    var q = new URLSearchParams(location.search);
    if (q.get('job')) openJob(q.get('job'));
    else go(q.get('view') === 'library' ? 'library' : 'home');
  }
  window.addEventListener('popstate', boot);
  api('GET', '/api/impact/engine').then(function (d) { state.engine = d; renderEngine(); }).catch(function () {});
  api('GET', '/api/impact/library').then(function (d) { state.lib = d.library.docs; renderLibBadge(); render(); }).catch(function (e) { banner(e.message); });
  loadJobs();
  boot();
})();
