// 実行傾向パネル（実行履歴画面）。
//
// 1 回の実行結果だけでは「そのテストが不安定なのか、今回だけ落ちたのか」が
// 判別できない。/api/runs/<domain>/trends の集計を出して、パス率の推移・
// 不安定なテスト・失敗が続いているテスト・自己修復したロケータを見せる。
//
// 対象サイトを選ばないと意味を持たない集計なので、サイト未選択のときは
// 数値を出さずに「選んでください」と言う（0 件と未選択を同じ見た目にしない）。
(function () {
  'use strict';

  var state = { domain: '', limit: 30, loading: false };
  // 履歴側が「このサイトを見たい」と伝えてきた希望。一覧取得より先に来ることがある。
  var preferred = '';
  // これまでに分かっているサイト（複数の情報源から統合する）
  var known = [];

  function $(id) { return document.getElementById(id); }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function setState(msg) {
    var el = $('rt-state');
    if (!el) return;
    el.textContent = msg;
    el.hidden = !msg;
  }

  function showBlocks(show) {
    ['rt-tiles', 'rt-chart', 'rt-tables'].forEach(function (id) {
      var el = $(id);
      if (el) el.hidden = !show;
    });
  }

  // パス率の推移。ライブラリを足さずに済む規模なので inline SVG で描く。
  function renderChart(trend) {
    var area = $('rt-chart-area');
    if (!area) return;
    // API は新しい順で返す。グラフは左が古い方が読みやすいので反転する。
    var points = trend.slice().reverse().filter(function (t) { return t.pass_rate !== null; });
    if (points.length < 2) {
      area.innerHTML = '<p class="rt-empty">推移を描くには実行回が 2 回以上必要です。</p>';
      return;
    }
    var w = Math.max(320, points.length * 44);
    var h = 120, padL = 34, padR = 10, padT = 10, padB = 22;
    var iw = w - padL - padR, ih = h - padT - padB;
    var xs = function (i) { return padL + (points.length === 1 ? iw / 2 : (i / (points.length - 1)) * iw); };
    var ys = function (v) { return padT + ih - (v / 100) * ih; };

    var grid = [0, 50, 100].map(function (v) {
      return '<line x1="' + padL + '" y1="' + ys(v) + '" x2="' + (w - padR) + '" y2="' + ys(v) +
        '" stroke="currentColor" stroke-opacity="0.15"/>' +
        '<text x="' + (padL - 6) + '" y="' + (ys(v) + 4) + '" text-anchor="end" font-size="10" fill="currentColor" fill-opacity="0.6">' + v + '</text>';
    }).join('');

    var path = points.map(function (p, i) { return (i ? 'L' : 'M') + xs(i) + ' ' + ys(p.pass_rate); }).join(' ');
    var dots = points.map(function (p, i) {
      var color = p.failed > 0 ? '#b42318' : (p.flaky > 0 ? '#b54708' : '#1a7f37');
      return '<circle cx="' + xs(i) + '" cy="' + ys(p.pass_rate) + '" r="3.5" fill="' + color + '">' +
        '<title>' + esc(p.run_id) + '\n' + p.pass_rate + '% (' + p.passed + '/' + p.total + ')' +
        (p.flaky ? '\n不安定 ' + p.flaky + ' 件' : '') + '</title></circle>';
    }).join('');

    area.innerHTML =
      '<svg width="' + w + '" height="' + h + '" role="img" aria-label="パス率の推移">' +
      grid +
      '<path d="' + path + '" fill="none" stroke="currentColor" stroke-width="1.5" stroke-opacity="0.7"/>' +
      dots +
      '</svg>';
  }

  function renderRows(tbodyId, rows, cols, emptyMsg) {
    var tb = $(tbodyId);
    if (!tb) return;
    if (!rows.length) {
      tb.innerHTML = '<tr><td colspan="' + cols.length + '" class="rt-empty">' + esc(emptyMsg) + '</td></tr>';
      return;
    }
    tb.innerHTML = rows.map(function (r) {
      return '<tr>' + cols.map(function (c) { return c(r); }).join('') + '</tr>';
    }).join('');
  }

  function render(data) {
    var s = data.summary || {};
    $('rt-pass-rate').textContent = s.latest_pass_rate === null || s.latest_pass_rate === undefined
      ? '—' : s.latest_pass_rate + '%';
    var delta = $('rt-pass-delta');
    if (s.pass_rate_delta === null || s.pass_rate_delta === undefined) {
      delta.textContent = '';
      delta.className = 'rt-tile-delta';
    } else {
      var d = s.pass_rate_delta;
      delta.textContent = (d > 0 ? '▲ +' : d < 0 ? '▼ ' : '± ') + d + 'pt';
      delta.className = 'rt-tile-delta ' + (d > 0 ? 'rt-up' : d < 0 ? 'rt-down' : '');
    }
    $('rt-unstable').textContent = s.unstable_tests != null ? s.unstable_tests : '—';
    $('rt-persist').textContent = s.persistently_failing != null ? s.persistently_failing : '—';
    $('rt-healed').textContent = s.healed_locators != null ? s.healed_locators : '—';

    renderChart(data.trend || []);

    renderRows('rt-flaky', data.flaky_ranking || [], [
      function (r) { return '<td>' + esc(r.title) + '</td>'; },
      function (r) { return '<td class="rt-num">' + r.flaky_runs + ' / ' + r.runs_seen + '</td>'; },
      function (r) { return '<td class="rt-num">' + r.flaky_rate + '%</td>'; },
      function (r) { return '<td class="rt-reason">' + esc(r.last_error || '—') + '</td>'; }
    ], '不安定なテストはありません。');

    renderRows('rt-failing', data.failing_ranking || [], [
      function (r) { return '<td>' + esc(r.title) + '</td>'; },
      function (r) { return '<td class="rt-num">' + r.consecutive_failures + '回</td>'; },
      function (r) { return '<td class="rt-num">' + r.failure_rate + '%</td>'; },
      function (r) { return '<td class="rt-reason">' + esc(r.last_error || '—') + '</td>'; }
    ], '失敗しているテストはありません。');

    renderRows('rt-healing', data.healing_ranking || [], [
      function (r) { return '<td class="rt-sel">' + esc(r.primary) + '</td>'; },
      function (r) { return '<td class="rt-sel">' + esc(r.used) + '</td>'; },
      function (r) { return '<td class="rt-num">' + r.count + '</td>'; },
      function (r) { return '<td>' + esc((r.fields || []).join(', ') || '—') + '</td>'; }
    ], '自己修復は発生していません。');

    var skipped = $('rt-skipped');
    var n = (data.runs_skipped || []).length;
    // 「集計対象外が何回あったか」を隠すと、少ない母数の数字を過信させてしまう。
    skipped.textContent = '集計した実行回: ' + data.runs_analyzed +
      (n ? '（結果ファイルが無く集計対象外: ' + n + ' 回）' : '');
    skipped.hidden = false;
    showBlocks(true);
    setState('');
  }

  async function load() {
    if (!state.domain) {
      showBlocks(false);
      setState('対象サイトを選ぶと傾向を集計します。');
      return;
    }
    if (state.loading) return;
    state.loading = true;
    setState('集計しています…');
    showBlocks(false);
    try {
      var url = '/api/runs/' + encodeURIComponent(state.domain) + '/trends?limit=' + state.limit;
      var res = await fetch(url);
      if (!res.ok) {
        setState('傾向を取得できませんでした（HTTP ' + res.status + '）。');
        return;
      }
      var data = await res.json();
      if (!data || !data.runs_analyzed) {
        // 0 件を 0% として描くと「全部落ちた」に見える。数字を出さない。
        setState('このサイトには集計できる実行結果がまだありません。');
        return;
      }
      render(data);
    } catch (e) {
      setState('傾向の取得に失敗しました: ' + (e && e.message ? e.message : e));
    } finally {
      state.loading = false;
    }
  }

  // 実行履歴の一覧が読み込まれたら、そこに出ているサイトを候補にする。
  function setSites(domains, want) {
    if (want) preferred = want;
    // 一覧は「置き換え」ではなく「統合」する。実行履歴（usage_log.jsonl 由来）と
    // 実行回の保管は別系統で、片方が空でももう片方には候補がある。置き換えにすると、
    // 後から来た空リストがパネルごと消してしまう（実際にそうなった）。
    (domains || []).filter(Boolean).forEach(function (d) {
      if (known.indexOf(d) < 0) known.push(d);
    });

    var sel = $('rt-site');
    var panel = $('rt-panel');
    if (!sel || !panel) return;
    panel.hidden = known.length === 0;
    if (!known.length) return;

    var keep = state.domain && known.indexOf(state.domain) >= 0
      ? state.domain
      : (preferred && known.indexOf(preferred) >= 0 ? preferred : known[0]);
    sel.innerHTML = known.map(function (d) {
      return '<option value="' + esc(d) + '"' + (d === keep ? ' selected' : '') + '>' + esc(d) + '</option>';
    }).join('');
    if (keep !== state.domain) {
      state.domain = keep;
      load();
    }
  }

  // 実行回が保存されているサイトを自分で取る。実行履歴（usage_log.jsonl 由来）
  // と実行回の保管は別系統なので、履歴側の一覧だけに頼ると傾向を出せない
  // サイトが生まれる。履歴側からの通知（rtSetSites）は「どれを選ぶか」の希望として扱う。
  async function loadSites() {
    try {
      var res = await fetch('/api/run-trends/sites');
      if (!res.ok) return;
      var data = await res.json();
      setSites((data.sites || []).map(function (s) { return s.domain; }), preferred);
    } catch (e) {
      // 取得できなければパネルは出さない（空の枠だけ見せない）
    }
  }

  function init() {
    var sel = $('rt-site');
    if (sel) {
      sel.addEventListener('change', function () { state.domain = sel.value; load(); });
    }
    var lim = $('rt-limit');
    if (lim) {
      lim.addEventListener('change', function () { state.limit = parseInt(lim.value, 10) || 30; load(); });
    }
    var btn = $('rt-reload');
    if (btn) btn.addEventListener('click', load);
    loadSites();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // 実行履歴側（view-run-history.js）から呼ぶ。
  window.rtSetSites = setSites;
  window.rtReload = load;
})();
