/* WebSpec2Doc テスト自動化 (System 02) — 右側パネル群（FE-B）
 * #p-run   実行と結果
 * #p-drift サイトの変更
 * #p-site  サイトの地図
 * 数値はすべて API 応答から描く。モックデータは持たない。 */
(function () {
  'use strict';

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var esc = function (v) {
    return String(v == null ? '' : v).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  };

  var STATUS_LABEL = {
    pass: '成功', fail: '失敗', flaky: '不安定', fixed: '修正済 · 未実行',
    new: '未実行', running: '実行中'
  };
  var KIND_LABEL = {
    element: '要素が変わった', selector: '要素が変わった', ng: '要素が変わった',
    screen: '画面が増えた', new_screen: '画面が増えた', added: '画面が増えた', info: '画面が増えた',
    text: '文言が変わった', copy: '文言が変わった', mute: '文言が変わった',
    removed: '画面が消えた', transition: '遷移が変わった'
  };
  var KIND_PILL = { fail: 'p-fail', info: 'p-fixed', mute: 'p-new' };

  var pollTimer = null;      // run/status の 1 秒ポーリング
  var live = {};             // 実行中の速報 {id: {status,duration_ms,error}}
  var runs = [];             // /api/ta2/runs のキャッシュ
  var runsLoaded = false;
  var driftLoaded = false, driftLoading = false;
  var mapLoaded = false, mapLoading = false;
  var rendering = false;

  function TA() { return window.TA2; }
  function state() { return (window.TA2 && window.TA2.state) || {}; }
  function domain() { return state().domain || ''; }
  function tests() { return Array.isArray(state().tests) ? state().tests : []; }
  function toast(m, c) { if (TA() && TA().toast) TA().toast(m, c || ''); }
  function errText(e) { return (e && e.message) || 'サーバに接続できません'; }

  function screensList() {
    var m = state().map;
    var ms = Array.isArray(m) ? m : (m && Array.isArray(m.screens) ? m.screens : null);
    if (ms && ms.length) return ms;
    return Array.isArray(state().screens) ? state().screens : [];
  }
  function screenName(id) {
    var list = screensList();
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i].name || '';
    return '';
  }
  function fmtDur(ms) {
    if (ms == null || isNaN(ms)) return '—';
    return (Number(ms) / 1000).toFixed(1) + 's';
  }
  function histHTML(h) {
    if (!Array.isArray(h) || !h.length) return '<span style="color:var(--tx3);font-size:11px">履歴なし</span>';
    return '<span class="hist">' + h.map(function (v) {
      return '<i class="' + (v === 1 ? 'p' : v === 0 ? 'f' : 'w') + '"></i>';
    }).join('') + '</span>';
  }

  /* 実行中は run/status の速報で行を差し替える（元データは書き換えない） */
  function mergedTests() {
    return tests().map(function (t) {
      var lv = live[t.id];
      if (!lv) return t;
      var last = t.last || {};
      return Object.assign({}, t, {
        status: lv.status || t.status,
        last: Object.assign({}, last, {
          dur_ms: lv.duration_ms != null ? lv.duration_ms : last.dur_ms,
          error: lv.error != null ? lv.error : last.error
        })
      });
    });
  }
  // 実行状況 API は passed / failed で返す。一覧・KPI の語彙（pass / fail）にそろえる。
  // そろえないと実行中の失敗が既定の「成功」表示に落ち、KPI も数えられない。
  function liveStatus(v) {
    if (v === 'passed') return 'pass';
    if (v === 'failed') return 'fail';
    return v;
  }
  function counts(list) {
    var c = { all: list.length, pass: 0, fail: 0, flaky: 0, fixed: 0, new: 0, running: 0 };
    list.forEach(function (t) { if (c[t.status] != null) c[t.status] += 1; });
    return c;
  }

  /* ==================== 実行と結果 ==================== */
  function lastRun() {
    if (!runs.length) return null;
    var sorted = runs.slice().sort(function (a, b) {
      return String(b.at || '').localeCompare(String(a.at || ''));
    });
    return sorted[0];
  }
  /** 実行から除外されたテスト（契約 §5: {id, reason} の配列） */
  function skippedList() {
    var r = state().run || {};
    return Array.isArray(r.skipped) ? r.skipped : [];
  }
  function runMetaText() {
    var r = state().run || {};
    var sk = skippedList();
    var skTxt = sk.length ? ' · 実行できなかった ' + sk.length + ' 件' : '';
    if (r.running) {
      return '実行中 ' + (r.done || 0) + ' / ' + (r.total || 0) +
        ' · 成功 ' + (r.passed || 0) + ' · 失敗 ' + (r.failed || 0) + skTxt;
    }
    var l = lastRun();
    if (!l) return (runsLoaded ? 'まだ実行していません' : '') + skTxt;
    return '直近の実行 ' + (l.at || '') + ' · 成功 ' + (l.passed || 0) +
      ' / 失敗 ' + (l.failed || 0) + '（全 ' + (l.total || 0) + '）· ' + fmtDur(l.duration_ms) + skTxt;
  }
  function resultCell(t) {
    var last = t.last || {};
    if (t.status === 'fail') {
      var where = last.step != null ? 'ステップ ' + last.step : 'ステップ不明';
      var msg = String(last.error || '').split('\n')[0];
      return '<span class="pill p-fail">失敗</span> <span style="color:var(--tx2)" title="' +
        esc(String(last.error || '')) + '">' +
        esc(where) + (msg ? ' · ' + esc(msg.slice(0, 60)) + (msg.length > 60 ? '…' : '') : '') + '</span>';
    }
    if (t.status === 'flaky') return '<span class="pill p-flaky">不安定</span> <span style="color:var(--tx2)">再試行で回復</span>';
    if (t.status === 'fixed') return '<span class="pill p-fixed">修正済 · 未実行</span>';
    if (t.status === 'new') return '<span class="pill p-new">未実行</span>';
    if (t.status === 'running') return '<span class="pill p-running">実行中</span>';
    if (t.status === 'pass') return '<span class="pill p-pass">成功</span>';
    // 知らない状態を既定で「成功」にしない（成功を確かめていないものを成功と表示しない）
    return '<span class="pill p-new">状態不明</span>';
  }
  function renderRun() {
    var el = $('#p-run');
    if (!el) return;
    var junit = $('#junit-btn');
    if (junit) junit.remove();     // 書き出し API が無い機能はボタンごと置かない

    var list = mergedTests();
    var c = counts(list);
    var meta = $('#run-meta'); if (meta) meta.textContent = runMetaText();

    var kpis = $('#kpis');
    var rs = state().run || {};
    if (kpis && rs.running) {
      // 実行中は今回の実行だけを数える（帯と同じ値）。前回の結果と混ぜない。
      // 不安定は実行の完了後にしか判定できないので、0 ではなく「—」にする。
      kpis.innerHTML =
        '<div class="kpi ok"><b>' + (rs.passed || 0) + '</b><span>成功（今回）</span></div>' +
        '<div class="kpi ng"><b>' + (rs.failed || 0) + '</b><span>失敗（今回）</span></div>' +
        '<div class="kpi wa"><b>—</b><span>不安定（完了後に判定）</span></div>' +
        '<div class="kpi"><b>' + Math.max(0, (Number(rs.total) || 0) - (Number(rs.done) || 0)) + '</b><span>実行待ち</span></div>';
    } else if (kpis) {
      kpis.innerHTML =
        '<div class="kpi ok"><b>' + c.pass + '</b><span>成功</span></div>' +
        '<div class="kpi ng"><b>' + c.fail + '</b><span>失敗</span></div>' +
        '<div class="kpi wa"><b>' + c.flaky + '</b><span>不安定（再試行で回復）</span></div>' +
        '<div class="kpi"><b>' + (c.fixed + c.new) + '</b><span>未実行（新規・修正済）</span></div>';
    }

    var r = state().run || {};
    var skipped = skippedList();
    var prog = $('#prog');
    if (prog) {
      var bar = prog.querySelector('i');
      // total は除外分を含まない（サーバが除外後の件数を返す）。
      // done/total で 100% に到達させ、除外分は別行で明示する（B-3）
      var tot = Number(r.total) || 0;
      if (r.running && tot) {
        prog.classList.add('on');
        if (bar) bar.style.width = Math.min(100, Math.round((r.done || 0) / tot * 100)) + '%';
      } else {
        prog.classList.remove('on');
        if (bar) bar.style.width = '0';
      }
    }

    var body = $('#run-rows');
    if (!body) return;
    if (!list.length) {
      body.innerHTML = '<tr><td colspan="7" style="color:var(--tx3);padding:14px 12px">' +
        'テストがまだありません。「＋ 新しいテスト」から作成してください</td></tr>';
      return;
    }
    var order = { running: 0, fail: 1, flaky: 2, fixed: 3, new: 4, pass: 5 };
    var rows = list.slice().sort(function (a, b) {
      return (order[a.status] == null ? 9 : order[a.status]) - (order[b.status] == null ? 9 : order[b.status]) ||
        String(a.id).localeCompare(String(b.id));
    });
    var skipHTML = '';
    if (skipped.length) {
      skipHTML = '<tr class="skiph"><td colspan="7">実行できなかった ' + skipped.length +
        ' 件（この件数は成功率に含みません）</td></tr>' +
        skipped.map(function (s) {
          var id = (s && s.id) || '';
          var t = null;
          list.forEach(function (x) { if (x.id === id) t = x; });
          return '<tr class="rw skip" data-id="' + esc(id) + '">' +
            '<td><i class="i-new" style="display:inline-block;width:8px;height:8px;border-radius:50%"></i></td>' +
            '<td class="mono">' + esc(id) + '</td>' +
            '<td class="nm" title="' + esc((t && t.name) || '') + '">' + esc((t && t.name) || '') + '</td>' +
            '<td class="scr" style="color:var(--tx2)">' + esc((t && t.screen) || '') + ' ' +
            esc(t ? screenName(t.screen) : '') + '</td>' +
            '<td>' + histHTML(t && t.history) + '</td>' +
            '<td class="dur">—</td>' +
            '<td><span class="pill p-flaky">実行できず</span> <span style="color:var(--tx2)">' +
            esc((s && s.reason) || '理由は返されていません') + '</span></td></tr>';
        }).join('');
    }
    body.innerHTML = skipHTML + rows.map(function (t) {
      var last = t.last || {};
      return '<tr class="rw ' + esc(t.status) + '" data-id="' + esc(t.id) + '">' +
        '<td><i class="i-' + esc(t.status) + '" style="display:inline-block;width:8px;height:8px;border-radius:50%"></i></td>' +
        '<td class="mono">' + esc(t.id) + '</td>' +
        '<td class="nm" title="' + esc(t.name) + '">' + esc(t.name) + '</td>' +
        '<td class="scr" style="color:var(--tx2)" title="' + esc(t.screen + ' ' + screenName(t.screen)) + '">' + esc(t.screen) + ' ' + esc(screenName(t.screen)) + '</td>' +
        '<td>' + histHTML(t.history) + '</td>' +
        '<td class="dur">' + esc(fmtDur(last.dur_ms)) + '</td>' +
        '<td>' + resultCell(t) + '</td></tr>';
    }).join('');
  }

  /* ==================== サイトの変更 ==================== */
  /* drift は「items（配列）」と「meta（reason / baseline_at / current_at）」の 2 本立て。
     items が空でも reason があれば比較そのものが出来ていない（B-4）。両方をここで束ねる */
  function driftData() {
    var d = state().drift;
    var meta = state().driftMeta || {};
    var items = Array.isArray(d) ? d : (d && Array.isArray(d.items) ? d.items : []);
    var src = (d && !Array.isArray(d) && typeof d === 'object') ? d : {};
    return {
      items: items,
      reason: src.reason || meta.reason || '',
      baseline_at: src.baseline_at || meta.baseline_at || '',
      current_at: src.current_at || meta.current_at || '',
      loaded: driftLoaded || !!meta.loaded
    };
  }
  /** 差分ゼロのときの文言。基準が無いのに「差分なし」と言わない */
  function driftEmptyText(data, withPeriod) {
    if (data.reason) return data.reason;
    if (!data.loaded) return withPeriod ? '読み込み中です…' : '';
    if (data.baseline_at) return '前回のクロールとの差分はありません' + (withPeriod ? '。' : '');
    // 「ありません」で終えると手が止まる。基準の作り方をその場に書く
    return '比較の基準となる前回のクロールがありません'
      + (withPeriod ? '。右上の「再クロール」を押すと、いまのサイトを基準として記録します。次回以降は、変わった要素だけがここに並びます。' : '');
  }
  function testName(id) {
    var list = tests();
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i].name || '';
    return '';
  }
  function driftCard(d) {
    var impact = Array.isArray(d.impact) ? d.impact : [];
    var st = d.state || 'open';
    var label = KIND_LABEL[d.kind] || d.kind || '変更';
    var pill = impact.length ? KIND_PILL.fail : (d.old == null ? KIND_PILL.info : KIND_PILL.mute);
    var chip = '<span class="pill ' + pill + '">' + esc(label) + '</span>';

    var right = st === 'applied' ? '<span class="pill p-pass">対応済み</span>'
      : st === 'dismissed' ? '<span class="pill p-new">無視した変更</span>'
        : impact.length ? '<span class="pill p-flaky">テスト ' + impact.length + ' 件に影響</span>'
          : '<span class="pill p-new">影響なし</span>';

    var ba = d.old != null
      ? '<div class="ba"><div class="o">' + esc(d.old) + '</div><span>→</span><div class="n">' + esc(d.now) + '</div></div>'
      : '<ul><li>' + esc(d.now) + '</li></ul>';

    var list = impact.length
      ? '<ul>' + impact.map(function (id) {
        return '<li><code>' + esc(id) + '</code> ' + esc(testName(id)) + '</li>';
      }).join('') + '</ul>'
      : '';

    var why = d.fix && d.fix.loc
      ? '修正案: ' + d.fix.loc + (d.fix.stab ? '（安定度 ' + d.fix.stab + '）' : '')
      : impact.length ? '自動の修正案はありません。1 件ずつ内容を確認してください'
        : 'この変更を検証しているテストはありません';

    var act = '';
    if (st === 'open') {
      if (impact.length && d.fix && d.fix.loc) {
        act += '<button class="btn pri" data-apply="' + esc(d.id) + '">' + impact.length + ' 件のセレクタをまとめて修正</button>';
      }
      if (impact.length) {
        act += '<button class="btn" data-one="' + esc(impact[0]) + '">1 件ずつ確認する</button>';
      }
      act += '<button class="btn sm" data-dismiss="' + esc(d.id) + '">' +
        (impact.length ? 'この変更を無視' : '確認済みにする') + '</button>';
    }
    return '<div class="drift ' + (st === 'open' ? '' : 'done') + '"><div class="dh">' + chip +
      '<b>' + esc(d.screen || '') + ' ' + esc(d.title || '') + '</b><div class="sp"></div>' + right + '</div>' +
      '<div class="db">' + ba + list + '<div class="act">' + act +
      '<span class="why">' + esc(why) + '</span></div></div></div>';
  }
  function renderDrift() {
    var body = $('#drift-body');
    if (!body) return;
    var data = driftData();
    var items = Array.isArray(data.items) ? data.items : [];

    var head = $('#p-drift .ph span');
    if (head) {
      head.textContent = items.length
        ? '基準 ' + (data.baseline_at || '不明') + ' → 現在 ' + (data.current_at || '不明') +
        ' の差分 · ' + items.length + ' 件'
        : driftEmptyText(data, false);
    }
    if (!items.length) {
      body.innerHTML = '<div class="drift"><div class="db" style="color:var(--tx2)">' +
        esc(driftEmptyText(data, true)) + '</div></div>';
      return;
    }
    body.innerHTML = items.map(driftCard).join('');
  }

  /* ==================== サイトの地図 ==================== */
  function renderSite() {
    var wrap = $('#scr');
    if (!wrap) return;
    var list = screensList();
    var head = $('#p-site .ph span');
    if (head) {
      head.textContent = list.length
        ? 'クロール済み ' + list.length + ' 画面 · カードを押すと、その画面のテストを生成できます'
        : (mapLoaded ? 'クロール結果がありません。先にサイトをクロールしてください' : '');
    }
    if (!list.length) {
      wrap.innerHTML = '<div style="color:var(--tx2)">' +
        (mapLoaded ? 'クロール済みの画面がありません。' : '読み込み中です…') + '</div>';
      return;
    }
    wrap.innerHTML = list.map(function (s) {
      var own = tests().filter(function (t) { return t.screen === s.id; });
      var n = s.tests != null ? s.tests : own.length;
      var fails = s.fails != null ? s.fails : own.filter(function (t) { return t.status === 'fail'; }).length;
      var gaps = Array.isArray(s.gaps) ? s.gaps.length : 0;
      var cov = s.coverage != null ? Math.max(0, Math.min(100, Math.round(s.coverage))) : (n ? Math.round(n / (n + gaps) * 100) : 0);
      var col = cov >= 90 ? 'var(--ok)' : cov > 0 ? 'var(--wa)' : 'var(--ng)';
      return '<div class="scard" data-scr="' + esc(s.id) + '">' +
        '<div class="id">' + esc(s.id) + ' · ' + esc(s.path || '') + '</div>' +
        '<b>' + esc(s.name || s.id) + '</b>' +
        '<div class="bar"><i style="width:' + cov + '%;background:' + col + '"></i></div>' +
        '<small><span>' + n + ' テスト · 失敗 ' + fails + '</span><span>' +
        (gaps ? '穴 ' + gaps + ' 件' : n ? '網羅' : 'テストなし') + '</span></small></div>';
    }).join('');
  }

  /* ==================== データ取得 ==================== */
  function api() { return (TA() && TA().api) || {}; }

  function loadRuns(force) {
    if (!api().runs || !domain()) return Promise.resolve();
    if (runsLoaded && !force) return Promise.resolve();
    return api().runs(domain()).then(function (r) {
      runs = Array.isArray(r && r.runs) ? r.runs : [];
      runsLoaded = true;
      renderRun();
    }, function () { runsLoaded = true; });
  }
  function ensureDrift(force) {
    if (!api().drift || !domain() || driftLoading) return Promise.resolve();
    if (driftLoaded && !force) return Promise.resolve();
    driftLoading = true;
    return api().drift(domain()).then(function (r) {
      var s = TA().state;
      if (s) {
        // state.drift は配列が正。reason 等は driftMeta に分けて保つ（B-4）
        s.drift = (r && Array.isArray(r.items)) ? r.items : [];
        s.driftMeta = {
          baseline_at: (r && r.baseline_at) || null,
          current_at: (r && r.current_at) || null,
          reason: (r && r.reason) || '',
          loaded: true
        };
      }
      driftLoaded = true; driftLoading = false; renderDrift();
    }, function (e) {
      driftLoading = false; driftLoaded = true;
      var b = $('#drift-body');
      if (b) b.innerHTML = '<div class="drift"><div class="db" style="color:var(--ng-tx)">サイトの変更を取得できません: ' + esc(errText(e)) + '</div></div>';
    });
  }
  function ensureMap(force) {
    if (!api().map || !domain() || mapLoading) return Promise.resolve();
    if (mapLoaded && !force) return Promise.resolve();
    mapLoading = true;
    return api().map(domain()).then(function (r) {
      if (TA().state) TA().state.map = (r && r.screens) ? r.screens : [];
      mapLoaded = true; mapLoading = false; renderSite();
    }, function (e) {
      mapLoading = false; mapLoaded = true;
      var w = $('#scr');
      if (w) w.innerHTML = '<div style="color:var(--ng-tx)">サイトの地図を取得できません: ' + esc(errText(e)) + '</div>';
    });
  }
  function refreshTests() {
    if (!api().tests || !domain()) return Promise.resolve();
    return api().tests(domain()).then(function (r) {
      var s = TA().state;
      if (s && r) {
        if (r.tests) s.tests = r.tests;
        if (r.elements) s.elements = r.elements;
        if (r.screens) s.screens = r.screens;
      }
      if (TA().emit) TA().emit('tests', r);
    }, function (e) { toast('テストを取り込めません: ' + errText(e), 'ng'); });
  }

  /* ==================== 実行 ==================== */
  function stopPolling() { if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; } }

  function poll() {
    if (!api().runStatus || !domain()) return;
    api().runStatus(domain()).then(function (st) {
      live = {};
      (st.tests || []).forEach(function (x) {
        live[x.id] = { status: liveStatus(x.status), duration_ms: x.duration_ms, error: x.error };
      });
      if (st.running && st.current_id && !live[st.current_id]) live[st.current_id] = { status: 'running' };
      if (TA().state) {
        var prev = TA().state.run || {};
        if (st && !Array.isArray(st.skipped) && Array.isArray(prev.skipped)) st.skipped = prev.skipped;
        TA().state.run = st;
      }
      if (TA().emit) TA().emit('run', st);
      renderRun();
      if (st.running) { pollTimer = setTimeout(poll, 1000); return; }
      stopPolling();
      live = {};
      refreshTests().then(function () {
        return loadRuns(true);
      }).then(function () {
        if (TA().render) TA().render(); else render();
        toast('実行完了 · 成功 ' + (st.passed || 0) + ' / 失敗 ' + (st.failed || 0)
          + (st.failed ? '。最初の失敗を下に出しています' : ''),
          (st.failed ? 'ng' : 'ok'));
        // 失敗があるなら最初の失敗行まで送る（結果表の先頭は失敗順に並ぶ）
        if (st.failed) {
          // tr.rw には「実行できなかった」行も含まれる。失敗そのものの先頭へ送る
          var first = $('#run-rows tr.rw.fail') || $('#run-rows tr.rw:not(.skip)');
          if (first) {
            if (first.scrollIntoView) first.scrollIntoView({ block: 'center' });
            first.classList.add('flash');
            setTimeout(function () { first.classList.remove('flash'); }, 2000);
          }
        }
      });
    }, function (e) {
      stopPolling();
      live = {};
      toast('実行状況を取得できません: ' + errText(e), 'ng');
      renderRun();
    });
  }
  function startPolling() { stopPolling(); poll(); }

  function startRun(ids, label) {
    if (!domain()) { toast('対象サイトが選ばれていません', 'ng'); return; }
    if (!api().run) { toast('実行 API を利用できません', 'ng'); return; }
    api().run(domain(), ids).then(function (r) {
      if (TA().setView) TA().setView('run');
      var sk = Array.isArray(r.skipped) ? r.skipped : [];
      if (TA().state) {
        TA().state.run = {
          running: true, run_id: r.run_id, total: r.total, done: 0,
          passed: 0, failed: 0, tests: [], skipped: sk
        };
      }
      renderRun();
      toast(label + ' ' + (r.total || 0) + ' 件を開始しました' +
        (sk.length ? '（実行できなかった ' + sk.length + ' 件は下の表に出しています）' : ''),
        sk.length ? 'ng' : '');
      startPolling();
    }, function (e) {
      var m = errText(e);
      if (/実行中|409/.test(m)) {
        // 409 はサーバの文言をそのまま出す（勝手に言い換えない）
        if (TA().setView) TA().setView('run');
        toast(m, 'ng');
        startPolling();
      } else {
        toast('実行を開始できません: ' + m, 'ng');
      }
    });
  }
  function runAll() { startRun([], '全件実行'); }
  function rerunFailed() {
    var ids = tests().filter(function (t) {
      return t.status === 'fail' || t.status === 'flaky' || t.status === 'fixed';
    }).map(function (t) { return t.id; });
    if (!ids.length) { toast('再実行の対象がありません（失敗・不安定・修正済 が 0 件）'); return; }
    startRun(ids, '再実行');
  }
  function exportEvidence() {
    var id = state().sel;
    if (!id) { toast('証跡はテストごとに保存されています。一覧でテストを選んでから押してください', 'ng'); return; }
    window.open('/api/ta2/artifact?domain=' + encodeURIComponent(domain()) +
      '&id=' + encodeURIComponent(id) + '&kind=report', '_blank');
  }
  function recrawl(btn) {
    if (!api().recrawl) { toast('再クロール API を利用できません', 'ng'); return; }
    var old = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = 'クロール中…'; btn.title = '再クロールの完了を待っています'; }
    api().recrawl(domain()).then(function () {
      if (btn) { btn.disabled = false; btn.textContent = old; btn.title = ''; }
      toast('再クロールが完了しました', 'ok');
      driftLoaded = false; mapLoaded = false;
      ensureDrift(true); ensureMap(true);
    }, function (e) {
      if (btn) { btn.disabled = false; btn.textContent = old; btn.title = ''; }
      toast('再クロールできません: ' + errText(e), 'ng');
    });
  }

  /* ==================== 配線 ==================== */
  function bind() {
    document.addEventListener('click', function (e) {
      var t = e.target;
      var row = t.closest && t.closest('#run-rows tr[data-id]');
      if (row) { if (TA().select) TA().select(row.getAttribute('data-id')); return; }

      var card = t.closest && t.closest('#scr .scard');
      if (card) {
        var scr = card.getAttribute('data-scr');
        if (TA().modals && TA().modals.openNew) TA().modals.openNew(scr);
        else toast('この画面のテストを作成できません', 'ng');
        return;
      }
      var btn = t.closest && t.closest('button');
      if (!btn) return;

      if (btn.id === 'run-all-btn' || btn.id === 'run-all-btn2' || btn.id === 'go-run') { runAll(); return; }
      if (btn.id === 'rerun-fail-btn') { rerunFailed(); return; }
      if (btn.id === 'export-btn') { exportEvidence(); return; }
      if (btn.id === 'recrawl-btn') { recrawl(btn); return; }

      if (btn.hasAttribute('data-apply')) {
        var aid = btn.getAttribute('data-apply');
        btn.disabled = true; btn.title = '修正を適用しています';
        api().driftApply(domain(), aid).then(function (r) {
          var n = (r && r.applied || []).length;
          toast(n + ' 件のテストに修正を適用しました。実行して確認してください', 'ok');
          driftLoaded = false;
          refreshTests().then(function () { return ensureDrift(true); })
            .then(function () { if (TA().render) TA().render(); else render(); });
        }, function (e) {
          btn.disabled = false; btn.title = '';
          toast('修正を適用できません: ' + errText(e), 'ng');
        });
        return;
      }
      if (btn.hasAttribute('data-dismiss')) {
        var did = btn.getAttribute('data-dismiss');
        btn.disabled = true;
        api().driftDismiss(domain(), did).then(function () {
          toast('この変更を確認済みにしました');
          driftLoaded = false;
          ensureDrift(true);
        }, function (e) {
          btn.disabled = false;
          toast('操作できません: ' + errText(e), 'ng');
        });
        return;
      }
      if (btn.hasAttribute('data-one')) {
        var oid = btn.getAttribute('data-one');
        if (TA().select) TA().select(oid);
        if (TA().setView) TA().setView('test');
        return;
      }
    });
  }

  /* 直近の実行・変更・地図は表示中の画面に関係なく 1 度だけ取りに行く
     （レールのバッジと各パネルが同じデータを見るため）。*Loaded で多重取得を防ぐ */
  function ensureData() {
    loadRuns(false); ensureDrift(false); ensureMap(false);
  }
  function onView() { ensureData(); }

  function render() {
    if (rendering) return;
    rendering = true;
    try {
      renderRun(); renderDrift(); renderSite(); ensureData();
    } catch (e) {
      if (window.console) console.error('[ta2/panels] render:', e);
    } finally { rendering = false; }
  }

  function hookRender() {
    var t = TA();
    if (!t || typeof t.render !== 'function' || t.render.__ta2panels) return;
    var orig = t.render;
    var wrapped = function () {
      var r = orig.apply(this, arguments);
      render();
      return r;
    };
    wrapped.__ta2panels = true;
    t.render = wrapped;
  }

  function init() {
    if (!window.TA2) return;
    bind();
    hookRender();
    if (typeof TA2.on === 'function') {
      ['boot', 'render', 'tests', 'select', 'run', 'drift', 'map'].forEach(function (ev) {
        TA2.on(ev, function () { if (ev === 'boot') hookRender(); render(); });
      });
      TA2.on('view', onView);
    }
    TA2.panels = {
      render: render, renderRun: renderRun, renderDrift: renderDrift, renderSite: renderSite,
      runAll: runAll, rerunFailed: rerunFailed, startPolling: startPolling, stopPolling: stopPolling,
      ensureMap: ensureMap, ensureDrift: ensureDrift, refreshTests: refreshTests,
      resultCell: resultCell  // 状態表示の評価（scripts/commercial_eval/product_truth_eval.py）から呼ぶ
    };
    render();
  }

  if (window.TA2) init();
  else document.addEventListener('DOMContentLoaded', init);
})();
