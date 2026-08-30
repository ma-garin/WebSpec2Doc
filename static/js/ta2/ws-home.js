/* ============================================================================
 * TA2 / ws-home.js — ホーム（A5: 一覧・空状態・サイト概要 / A6: 取り込み）
 *
 * データ源:
 *   一覧      GET  /api/history                （web/routes/history.py）
 *   削除      DELETE /api/site/<domain>        （static/js/history.js と同じ）
 *   画面発見  POST /api/discover-stream        （読み方は wizard.js discoverUrls と同じ）
 *   解析実行  POST /run                        （読み方は execution.js runWith と同じ）
 *   実況      GET  /api/live-screenshot?domain= （execution.js startPreviewPolling と同じ）
 *   停止      POST /api/cancel                 （form: run_id）
 * ========================================================================== */
(function () {
  'use strict';
  var T = window.TA2, S = T.state, $ = T.$, esc = T.esc;

  var selected = '';        // 一覧で選ばれているドメイン
  var busy = false;         // 取り込み中は二重起動させない
  var runId = '';
  var shotTimer = null, clockTimer = null, startedAt = 0;
  var reader = null, cancelled = false;

  T.wsHomeDomain = function () { return selected; };

  /* ---------------------------------------------------------------- 表示状態 */
  function stage(which) {
    ['home-empty', 'home-stage', 'home-summary'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.hidden = (id !== 'home-' + which);
    });
  }

  /* ------------------------------------------------------------------ 一覧 */
  function itemsOf() { return S.history || []; }

  var query = '';            // 一覧の絞り込み文字列
  var filterMounted = false;

  /** URL から host を取り出す。取れなければ空文字（推測で埋めない） */
  function hostOf(u) {
    if (!u) return '';
    try { return new URL(u).host.toLowerCase(); } catch (e) { return ''; }
  }
  /** 入力途中（スキーム省略）の URL にも耐える host 取り出し */
  function hostOfInput(u) {
    var s = String(u || '').trim();
    if (!s) return '';
    return hostOf(s) || hostOf('http://' + s.replace(/^\/+/, ''));
  }

  /** 入力 URL と同じサイトが一覧にあればそのディレクトリ名を返す。
   *  /api/history の site_url が空の行は判定できないため、host 一致でのみ拾う。 */
  function matchExistingDomain(url) {
    var h = hostOfInput(url);
    if (!h) return '';
    var items = itemsOf(), i;
    for (i = 0; i < items.length; i++) {
      if (hostOf(items[i].site_url) === h) return items[i].domain;
    }
    for (i = 0; i < items.length; i++) {
      if (String(items[i].domain || '').toLowerCase() === h) return items[i].domain;
    }
    return '';
  }

  function hasScreens(it) { return Number(it.screens) > 0; }
  function byRecency(a, b) { return (b.updated_ts || 0) - (a.updated_ts || 0); }

  function matchQuery(it) {
    if (!query) return true;
    var q = query.toLowerCase();
    return String(it.domain || '').toLowerCase().indexOf(q) >= 0
      || String(it.site_url || '').toLowerCase().indexOf(q) >= 0;
  }

  function groupHead(title, n, note) {
    return '<div class="grp"><b>' + esc(title) + '</b><span>' + n + '</span>'
      + (note ? '<small>' + esc(note) + '</small>' : '') + '</div>';
  }

  function rowHtml(it, opts) {
    opts = opts || {};
    var on = it.domain === selected ? ' on' : '';
    var foot = opts.reason || (esc(it.screens) + ' 画面 · ' + esc(it.updated || '—'));
    return '<div class="it' + on + (opts.dim ? ' dim' : '') + '" data-domain="' + esc(it.domain) + '"'
      + ' role="option" tabindex="0" aria-selected="' + (on ? 'true' : 'false') + '">'
      + '<i class="' + (hasScreens(it) ? 'i-pass' : 'i-new') + '"></i>'
      + '<span class="grow"><b>' + esc(it.domain) + '</b>'
      + (it.site_url ? '<small>' + esc(it.site_url) + '</small>' : '')
      + '<small>' + (opts.reason ? esc(foot) : foot) + '</small></span>'
      + '<button type="button" class="del" data-del="' + esc(it.domain) + '"'
      + ' title="「' + esc(it.domain) + '」の解析結果を削除" aria-label="削除">✕</button>'
      + '</div>';
  }

  /** 同じ host のサイトは新しい方を先頭に、古い方をその直下へ寄せて理由を書く。
   *  行そのものは消さない（消すと重複した方を削除できなくなる）。 */
  function rowsWithDuplicates(list) {
    var seen = {}, order = [], out = [];
    list.forEach(function (it) {
      var k = hostOf(it.site_url);
      if (!k) { order.push({ head: it, dups: [] }); return; }
      if (!seen[k]) { seen[k] = { head: it, dups: [] }; order.push(seen[k]); }
      else seen[k].dups.push(it);
    });
    order.forEach(function (g) {
      out.push(rowHtml(g.head));
      g.dups.forEach(function (d) {
        out.push(rowHtml(d, { dim: true, reason: '同じ URL（新しい方: ' + g.head.domain + '）' }));
      });
    });
    return out.join('');
  }

  /** 絞り込み欄は #site-items の直前に差し込む。#q はテスト一覧のものなので使わない */
  function ensureFilter() {
    if (filterMounted) return;
    var box = $('#site-items');
    if (!box || !box.parentNode) return;
    var wrap = document.createElement('div');
    wrap.className = 'search';
    wrap.id = 'site-search';
    wrap.hidden = S.view !== 'home';
    var input = document.createElement('input');
    input.id = 'site-q';
    input.type = 'search';
    input.placeholder = 'サイト名・URL で絞り込み';
    input.setAttribute('aria-label', 'サイトの絞り込み');
    input.addEventListener('input', function () { query = input.value.trim(); renderList(); });
    wrap.appendChild(input);
    box.parentNode.insertBefore(wrap, box);
    filterMounted = true;
  }

  function renderList() {
    var box = $('#site-items');
    if (!box) return;
    ensureFilter();
    var all = itemsOf();
    if (!all.length) { box.innerHTML = ''; return; }
    var items = all.filter(matchQuery);
    if (!items.length) {
      box.innerHTML = '<p class="list-empty">該当なし</p>';
      return;
    }
    var live = items.filter(hasScreens).sort(byRecency);
    var dead = items.filter(function (it) { return !hasScreens(it); }).sort(byRecency);
    var html = '';
    if (live.length) {
      html += groupHead('解析できたサイト', live.length);
      html += rowsWithDuplicates(live);
    }
    if (dead.length) {
      html += groupHead('解析できていないサイト', dead.length,
        '画面が 1 件も保存されていません。もう一度解析するか、削除できます。');
      html += dead.map(function (it) {
        return rowHtml(it, { dim: true, reason: '最終解析 ' + (it.updated || '—') + '・画面 0' });
      }).join('');
    }
    box.innerHTML = html;
  }

  function renderSummary() {
    var it = T.historyItem(selected);
    var kpis = $('#home-site-kpis');
    if (!it) { stage('empty'); return; }
    if (kpis) {
      kpis.innerHTML =
        kpi(it.screens, '画面') +
        kpi(it.fields, '入力項目') +
        kpi(it.snapshot_count, '解析回数') +
        kpi(it.has_diff ? 'あり' : 'なし', '未確認の変更', it.has_diff ? 'wa' : '');
    }
    setHref('#home-cta-spec', '/sites/' + encodeURIComponent(it.domain) + '/spec');
    setHref('#home-cta-tests', '/sites/' + encodeURIComponent(it.domain) + '/tests');
    setHref('#home-cta-drift', '/sites/' + encodeURIComponent(it.domain) + '/changes');
    var why = $('#home-cta-why');
    if (why) {
      why.textContent = '最終解析 ' + (it.updated || '—')
        + (it.site_url ? ' · 対象 ' + it.site_url : '');
    }
    stage('summary');
  }

  function kpi(value, label, cls) {
    return '<div class="kpi' + (cls ? ' ' + cls : '') + '"><b>' + esc(value) + '</b>'
      + '<span>' + esc(label) + '</span></div>';
  }
  function setHref(sel, href) { var a = $(sel); if (a) a.href = href; }

  function pick(domain) {
    selected = domain || '';
    renderList();
    renderSummary();
  }

  /** 一覧が読めたときの初期選択と、空状態の判断 */
  function syncHome() {
    if (S.view !== 'home' || busy) return;
    var items = itemsOf();
    renderList();
    if (!items.length) {
      selected = '';
      stage('empty');
      var input = $('#home-url');
      if (input && document.activeElement !== input) input.focus();
      return;
    }
    if (!T.historyItem(selected)) {
      var wanted = document.body.dataset.domain || '';
      selected = T.historyItem(wanted) ? wanted : items[0].domain;
    }
    pick(selected);
  }

  /* ------------------------------------------------------------------ 削除 */
  function doDelete(domain, btn) {
    if (!window.confirm('「' + domain + '」の画面一覧・スナップショット・スクリーンショットを'
      + 'すべて削除します。この操作は取り消せません。')) return;
    if (btn) btn.disabled = true;
    fetch('/api/site/' + encodeURIComponent(domain), { method: 'DELETE', credentials: 'same-origin' })
      .then(function (res) { return res.json().catch(function () { return {}; }).then(function (j) { return { ok: res.ok, j: j }; }); })
      .then(function (r) {
        if (!r.ok) throw new Error(r.j.error || '削除に失敗しました');
        T.toast('「' + domain + '」を削除しました', 'ok');
        if (selected === domain) selected = '';
        return T.loadHistory(true).then(syncHome);
      })
      .catch(function (e) {
        if (btn) btn.disabled = false;
        T.toast(e.message || '削除に失敗しました', 'ng');
      });
  }

  /* ------------------------------------------------------------ 取り込み表示 */
  function logLine(text, cls) {
    var box = $('#home-log');
    if (!box) return;
    var d = document.createElement('div');
    var t = document.createElement('span');
    t.className = 't';
    t.textContent = elapsed();
    var i = document.createElement('span');
    i.className = cls || '';
    i.textContent = cls === 'ok' ? '✓' : (cls === 'ng' ? '✕' : '·');
    var s = document.createElement('span');
    s.textContent = text;
    d.appendChild(t); d.appendChild(i); d.appendChild(s);
    box.insertBefore(d, box.firstChild);
    while (box.childNodes.length > 200) box.removeChild(box.lastChild);
  }

  function elapsed() {
    var s = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
    return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
  }

  var counts = { found: 0, done: 0, skipped: 0, saved: 0 };
  function renderStageKpis() {
    var box = $('#home-kpis');
    if (!box) return;
    box.innerHTML = kpi(counts.found, '見つけた画面') + kpi(counts.done, '解析済み')
      + kpi(counts.saved, '保存済み') + kpi(counts.skipped, 'スキップ');
  }
  function renderProgress() {
    var bar = document.querySelector('#home-prog i');
    if (!bar) return;
    var pct = counts.found ? Math.min(100, Math.round(counts.done / counts.found * 100)) : 0;
    bar.style.width = pct + '%';
  }

  function startClock() {
    startedAt = Date.now();
    var el = $('#home-stage-time');
    clockTimer = setInterval(function () {
      if (el) el.textContent = '経過 ' + elapsed();
    }, 500);
  }
  function stopClock() { clearInterval(clockTimer); clockTimer = null; }

  function startShots(domain) {
    var host = $('#home-shot');
    if (!host || !domain) return;
    var poll = function () {
      var img = new Image();
      img.onload = function () {
        host.textContent = '';
        host.appendChild(img);
      };
      img.src = '/api/live-screenshot?domain=' + encodeURIComponent(domain) + '&t=' + Date.now();
    };
    poll();
    shotTimer = setInterval(poll, 1500);
  }
  function stopShots() { clearInterval(shotTimer); shotTimer = null; }

  function finish(msg, cls) {
    busy = false;
    stopClock(); stopShots();
    runId = '';
    var pill = $('#home-stage-pill');
    if (pill) { pill.className = 'pill ' + (cls === 'ng' ? 'p-fail' : 'p-pass'); pill.textContent = msg; }
    var cancel = $('#home-cancel');
    if (cancel) { cancel.disabled = true; cancel.title = '解析は終了しています'; }
  }

  /* ---------------------------------------------------- 画面発見（discover） */
  function discover(url) {
    var body = new URLSearchParams({
      url: url, depth: '2', max_pages: '30', parallelism: '4'
    });
    var pages = [];
    return fetch('/api/discover-stream', { method: 'POST', body: body, credentials: 'same-origin' })
      .then(function (res) {
        if (!res.ok) {
          return res.json().catch(function () { return {}; }).then(function (j) {
            throw new Error(j.error || '画面の取得に失敗しました');
          });
        }
        reader = res.body.getReader();
        var dec = new TextDecoder(), buf = '';
        function pump() {
          return reader.read().then(function (r) {
            if (r.done) return pages;
            buf += dec.decode(r.value, { stream: true });
            var chunks = buf.split('\n\n');
            buf = chunks.pop() || '';
            for (var i = 0; i < chunks.length; i++) {
              var line = chunks[i].replace(/^data:\s?/, '').trim();
              if (!line) continue;
              var obj;
              try { obj = JSON.parse(line); } catch (e) { continue; }
              if (obj.run_id) { runId = obj.run_id; }
              else if (obj.page) {
                pages.push(obj.page);
                counts.found = pages.length;
                renderStageKpis();
                logLine((obj.page.title || obj.page.url || '') + ' を発見', 'ok');
              } else if (obj.crawl_event && obj.crawl_event.event === 'page_skipped') {
                counts.skipped++;
                renderStageKpis();
                logLine('除外: ' + (obj.crawl_event.url || ''), '');
              } else if (obj.error) {
                throw new Error(obj.error);
              }
            }
            return pump();
          });
        }
        return pump();
      });
  }

  /* ---------------------------------------------------------- 解析実行（run） */
  function runCrawl(urls, domainName) {
    var params = {
      urls: urls.join(','),
      depth: '2',
      max_pages: '30',
      parallelism: '4',
      format: 'json,md,html',
      compare: 'true'
    };
    /* 既存サイトの再解析。サーバ側が domain_name を見る実装になっていれば
       出力先が既存ディレクトリに揃い、一覧に 2 行目が増えない */
    if (domainName) params.domain_name = domainName;
    var body = new URLSearchParams(params);
    var summary = null, stopped = false;
    return fetch('/run', {
      method: 'POST',
      body: body.toString(),
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    }).then(function (res) {
      reader = res.body.getReader();
      var dec = new TextDecoder(), buf = '';
      function line(l) {
        if (!l) return;
        if (l.indexOf('RUN_ID:') === 0) { runId = l.slice(7).trim(); return; }
        if (l.indexOf('REPORT_PATH:') === 0 || l.indexOf('PDF_PATH:') === 0) return;
        if (l.indexOf('SUMMARY:') === 0) {
          try { summary = JSON.parse(l.slice(8).trim()); } catch (e) { /* 形式が違えば無視 */ }
          return;
        }
        if (l.indexOf('CRAWL_EVENT:') === 0) {
          var ev = null;
          try { ev = JSON.parse(l.slice(12)); } catch (e) { return; }
          crawlEvent(ev);
          return;
        }
        if (l.trim() === 'CRAWL_CANCELLED' || l.trim() === '停止しました。') { stopped = true; return; }
        logLine(l.trim(), '');
      }
      function pump() {
        return reader.read().then(function (r) {
          if (r.done) { line(buf); return { summary: summary, stopped: stopped }; }
          buf += dec.decode(r.value, { stream: true });
          var lines = buf.split('\n');
          buf = lines.pop() || '';
          lines.forEach(line);
          return pump();
        });
      }
      return pump();
    });
  }

  function crawlEvent(ev) {
    if (!ev) return;
    var total = Number(ev.total);
    if (isFinite(total) && total > 0) { counts.found = total; }
    if (ev.event === 'page_started') {
      var p = $('#home-shot-path');
      if (p) { try { p.textContent = new URL(ev.url).pathname; } catch (e) { p.textContent = ev.url || ''; } }
    } else if (ev.event === 'page_completed') {
      counts.done++;
      logLine((ev.url || '') + ' を解析', 'ok');
    } else if (ev.event === 'page_skipped') {
      counts.skipped++;
      logLine('除外（' + (ev.reason || '制約') + '）: ' + (ev.url || ''), '');
    } else if (ev.event === 'login_wall_detected') {
      counts.skipped++;
      logLine('ログインが必要なため除外: ' + (ev.url || ''), 'ng');
    } else if (ev.event === 'page_failed') {
      logLine('取得できませんでした: ' + (ev.url || ''), 'ng');
    } else if (ev.event === 'checkpoint_saved') {
      counts.saved = Number(ev.saved_count) || counts.saved;
    } else if (ev.event === 'generate_started') {
      logLine('仕様書を生成しています', '');
    } else if (ev.event === 'generate_step' && ev.label) {
      logLine(ev.label, '');
    }
    renderStageKpis();
    renderProgress();
  }

  /* ------------------------------------------------------------ ログイン壁 */
  function loginWall() {
    var box = $('#home-log');
    if (box) {
      var d = document.createElement('div');
      var s = document.createElement('span');
      s.textContent = 'ログインが必要なサイトです。詳細設定から認証情報を登録してください';
      var a = document.createElement('a');
      a.className = 'btn';
      a.href = '/generate';
      a.textContent = '詳細設定を開く';
      d.appendChild(s); d.appendChild(a);
      box.insertBefore(d, box.firstChild);
    }
    finish('要ログイン', 'ng');
  }

  /* -------------------------------------------------------------- 取り込み */
  function ingest(url) {
    if (busy) return;
    busy = true;
    cancelled = false;
    runId = '';
    counts = { found: 0, done: 0, skipped: 0, saved: 0 };
    var log = $('#home-log');
    if (log) log.textContent = '';
    var existing = matchExistingDomain(url);
    var title = $('#home-stage-title');
    if (title) {
      title.textContent = url + ' を解析しています'
        + (existing ? '（既存のサイト「' + existing + '」を再解析します）' : '');
    }
    var pill = $('#home-stage-pill');
    if (pill) { pill.className = 'pill p-running'; pill.textContent = '実行中'; }
    var cancel = $('#home-cancel');
    if (cancel) { cancel.disabled = false; cancel.title = ''; }
    renderStageKpis();
    renderProgress();
    stage('stage');
    startClock();

    var host = hostOfInput(url);
    startShots(existing || host);
    logLine('対象サイトへ接続しています', '');
    if (existing) {
      logLine('既存のサイト「' + existing + '」を再解析します（一覧に新しい行は増えません）', 'ok');
    }

    discover(url).then(function (pages) {
      if (cancelled) throw new Error('__cancelled__');
      var live = (pages || []).filter(function (p) { return p && p.url; });
      if (live.some(function (p) { return p.login_required; }) && !live.some(function (p) { return !p.login_required; })) {
        loginWall();
        throw new Error('__handled__');
      }
      if (!live.length) throw new Error('画面が 1 件も見つかりませんでした。URL を確認してください。');
      logLine(live.length + ' 画面を発見しました', 'ok');
      counts.found = live.length;
      renderStageKpis();
      return runCrawl(live.map(function (p) { return p.url; }), existing);
    }).then(function (r) {
      if (!r) return;
      if (r.stopped || cancelled) {
        finish('停止', 'ng');
        T.toast('停止しました', 'ng');
        return;
      }
      /* 既存サイトの再解析なら、サーバ応答のホスト名ではなく元のディレクトリ名へ戻す */
      var domain = existing || (r.summary && (r.summary.domain || r.summary.site)) || host;
      finish('完了', 'ok');
      T.toast('仕様書ができました', 'ok');
      location.assign('/sites/' + encodeURIComponent(domain) + '/spec');
    }).catch(function (e) {
      var msg = e && e.message;
      if (msg === '__handled__') return;
      if (msg === '__cancelled__' || cancelled) {
        finish('停止', 'ng');
        T.toast('停止しました', 'ng');
        return;
      }
      finish('失敗', 'ng');
      logLine(msg || '解析に失敗しました', 'ng');
      T.toast(msg || '解析に失敗しました', 'ng');
      var back = $('#home-cancel');
      if (back) {
        back.disabled = false;
        back.title = '';
        back.textContent = '入力に戻る';
      }
    });
  }

  function cancelIngest() {
    var btn = $('#home-cancel');
    if (btn && btn.textContent === '入力に戻る') {
      btn.textContent = '停止';
      stage(itemsOf().length ? 'summary' : 'empty');
      if (!itemsOf().length) { var i = $('#home-url'); if (i) i.focus(); }
      return;
    }
    cancelled = true;
    if (btn) { btn.disabled = true; btn.title = '停止しています…'; }
    if (runId) {
      fetch('/api/cancel', {
        method: 'POST', credentials: 'same-origin',
        body: new URLSearchParams({ run_id: runId })
      }).catch(function () { /* 停止要求が届かなくても、下の reader.cancel で読みは止まる */ });
    }
    if (reader) { try { reader.cancel(); } catch (e) { /* 既に閉じている */ } }
  }

  /* ------------------------------------------------------------------ 配線 */
  /** URL 欄に既存サイトと同じ host が入ったら、行が増えないことを先に伝える */
  function updateUrlHint() {
    var hint = $('#home-url-hint');
    var input = $('#home-url');
    if (!hint || !input) return;
    var d = matchExistingDomain(input.value);
    hint.textContent = d ? '既存のサイト「' + d + '」を再解析します（新しい行は増えません）' : '';
    hint.hidden = !d;
  }

  function bind() {
    ensureFilter();
    var form = $('#home-form');
    if (form) {
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        var input = $('#home-url');
        var url = (input && input.value || '').trim();
        if (!url) return;
        ingest(url);
      });
    }
    var urlInput = $('#home-url');
    if (urlInput) urlInput.addEventListener('input', updateUrlHint);

    var add = $('#home-add');
    if (add) {
      add.addEventListener('click', function () {
        if (busy) { T.toast('解析が終わるまでお待ちください', 'ng'); return; }
        stage('empty');
        var i = $('#home-url');
        if (i) { i.value = ''; i.focus(); }
      });
    }
    var cancel = $('#home-cancel');
    if (cancel) cancel.addEventListener('click', cancelIngest);

    var list = $('#site-items');
    if (list) {
      list.addEventListener('click', function (e) {
        var del = e.target.closest && e.target.closest('[data-del]');
        if (del) { e.stopPropagation(); doDelete(del.dataset.del, del); return; }
        var it = e.target.closest && e.target.closest('.it[data-domain]');
        if (it) pick(it.dataset.domain);
      });
      list.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' && e.key !== ' ' && e.key !== 'Spacebar') return;
        var it = e.target.closest && e.target.closest('.it[data-domain]');
        if (!it) return;
        e.preventDefault();
        pick(it.dataset.domain);
      });
    }
  }

  bind();

  T.on('boot', function () {
    if (S.view !== 'home') return;
    stage(itemsOf().length ? 'summary' : 'empty');
    T.loadHistory().then(syncHome);
  });
  T.on('history', syncHome);
  T.on('view', function (v) {
    if (v !== 'home' || busy) return;
    T.loadHistory().then(syncHome);
  });
})();
