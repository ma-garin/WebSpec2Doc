/* ws-reverse.js — リバース解析表示（C. Hybrid: window.WS2D の部品で描く）
 * T.reverseRender(host, domain): GET /api/reverse-analysis?domain=... と
 * GET /api/sites/<d>/static-routes/probe（System 03 の探索結果・無くても動く）を取得して host に描く。
 * テキストは必ず esc() / textContent 経由。内部 JSON は画面に出さない（id のみ出典欄）。
 * Product Truth: static を到達済みにしない／推論を実測にしない／method 不明を GET にしない／partial を成功にしない。
 */
(function () {
  'use strict';
  var T = window.TA2;
  if (!T) return;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /* API の state → WS2D.evidence の code（unknown は「未確認」。観測に格上げしない） */
  var EV_CODE = { observed: 'observed', static: 'static', inferred: 'inferred', ambiguous: 'ambiguous', unknown: 'unverified', unavailable: 'unavailable' };
  var EV_REASON = {
    observed: '実行時に観測した事実です。',
    static: '静的解析で見つけた候補です。実行・到達の証明ではありません。',
    inferred: '静的解析からの推論です。実行・到達の証明ではありません。',
    ambiguous: '解釈が複数あり、1 つに決められません。',
    unverified: '未確認です。確かめた記録がありません。',
    unavailable: '解析ツールが利用できず、確認できていません。'
  };
  var ORIGIN_LABEL = { runtime: '実行時に観測', static: '静的のみ' };
  var OUTCOME_LABEL = { partial: '一部のみ', success: '完了', failed: '失敗', unknown: '未確認' };
  var SEV_LABEL = { error: 'エラー', warning: '警告', info: '情報' };
  var TABS = [
    { key: 'all', label: 'すべて' },
    { key: 'route', label: 'Route' },
    { key: 'api', label: 'API' },
    { key: 'module', label: 'Module' },
    { key: 'source', label: 'Source' },
    { key: 'diag', label: '診断' }
  ];
  /* KPI の行 → 根拠一覧のタブ・区分（事実／推論／未確認） */
  var KPI_TAB = { static: 'all', route: 'route', api_static: 'api', api_runtime: 'api', module_dep: 'module', source_map: 'source', qa: 'all' };
  var KPI_CAT = { api_runtime: 'fact', qa: 'unverified' };
  var STATUS_LABEL = { complete: '完了', partial: '一部のみ', failed: '失敗' };
  var RESULT_TITLE = { success: '解析が完了しました', partial: '一部のみ取得しました', error: '失敗しました', busy: '実行中のため待機しています', no_runtime: '実行時の記録がありません' };
  var RESULT_KIND = { partial: 'partial', error: 'error', busy: 'unavailable', no_runtime: 'unverified' };
  var seq = 0;

  function isNum(v) { return typeof v === 'number' && isFinite(v); }
  function fmtTime(v) {
    var m = /^(\d{4})-(\d\d)-(\d\d)[T ](\d\d):(\d\d)/.exec(String(v || ''));
    return m ? m[1] + '/' + m[2] + '/' + m[3] + ' ' + m[4] + ':' + m[5] : '';
  }

  function reverseRender(host, domain) {
    if (!host) return;
    var W = window.WS2D;
    if (!W) {
      host.textContent = '共通部品を読み込めませんでした。ページを再読み込みしてください。';
      return;
    }
    var token = ++seq;
    var data = null;
    var lastGood = null;      // 直近に読めた正常な結果（読み込み失敗時も保持して見せる）
    var netErr = null;
    var probe = null;         // System 03 の探索結果 { state, byId }
    var tab = 'all';
    var runningLocal = false;
    var runMsg = null;
    var pollTimer = null;

    function evBadge(state, label) { return W.evidence.html(EV_CODE[state] || 'unverified', label); }
    function slot(name) { return host.querySelector('[data-slot="' + name + '"]'); }
    function fetchJson(url) {
      return fetch(url, { headers: { 'Accept': 'application/json' } })
        .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
    }
    function mainUrl() { return '/api/reverse-analysis?domain=' + encodeURIComponent(domain || ''); }
    function probeUrl() { return '/api/sites/' + encodeURIComponent(domain || '') + '/static-routes/probe'; }

    function showLoading() {
      host.setAttribute('aria-busy', 'true');
      host.innerHTML = '<div class="rv"><div data-slot="loading"></div></div>';
      W.state(slot('loading'), { kind: 'loading', message: 'リバース解析の結果を読み込んでいます…' });
    }
    function toProbe(j) {
      var byId = {};
      if (j && j.state === 'ok') (j.items || []).forEach(function (it) { if (it && it.evidence_id) byId[it.evidence_id] = it; });
      return { state: j ? j.state : 'error', byId: byId };
    }

    function load() {
      var my = ++seq; token = my;
      stopPoll();
      showLoading();
      Promise.all([fetchJson(mainUrl()), fetchJson(probeUrl()).catch(function () { return null; })])
        .then(function (res) {
          if (my !== token) return;
          data = res[0] || {};
          probe = toProbe(res[1]);
          netErr = null;
          if (data.state === 'ok') lastGood = data;
          host.removeAttribute('aria-busy');
          draw();
        })
        .catch(function () {
          if (my !== token) return;
          host.removeAttribute('aria-busy');
          netErr = { message: 'リバース解析の結果を取得できませんでした。', next_action: '通信状態を確認して、再読み込みしてください。' };
          data = lastGood || { state: 'error', message: netErr.message, next_action: netErr.next_action };
          draw();
        });
    }

    /* ---------- 状態の対応付け ---------- */
    function isRunning() { return runningLocal || !!(data && data.running); }
    function statusCode() {
      if (isRunning()) return 'running';
      var st = data.state;
      if (st === 'empty') return 'not_started';
      if (st === 'error') return 'failed';
      if (st === 'mismatch') return 'unverified';
      if (st === 'ok') {
        if (data.status === 'complete') return 'done';
        if (data.status === 'partial') return 'partial';
        if (data.status === 'failed') return 'failed';
        return 'unverified';
      }
      return 'unverified';
    }
    function reasonOf() {
      var d = data;
      if (isRunning()) return { t: 'リバース解析を実行しています（数十秒かかることがあります）。完了すると結果を更新します。', k: 'info' };
      if (netErr) return { t: netErr.message + '前回の結果を表示しています。', k: 'error' };
      if (d.state === 'empty') return { t: d.message || 'このサイトのリバース解析結果はまだありません。', k: 'info' };
      if (d.state === 'error') return { t: d.message || '結果を表示できません。', k: 'error' };
      if (d.state === 'mismatch') return { t: '保存済みの結果が現在のサイトの記録と対応しないため、未確認として扱い表示しません。', k: 'warning' };
      if (d.status !== 'complete') return { t: '一部のみ取得しました。取得できた範囲だけを表示しており、成功とは扱いません。', k: 'warning' };
      var warn = (d.diagnostics || []).filter(function (x) { return x.severity === 'warning'; })[0];
      if (warn) return { t: warn.message, k: 'warning' };
      return { t: '解析が完了しました。静的な根拠は「推論」であり、実行・到達の証明ではありません。', k: 'success' };
    }

    /* ---------- 上部（page header・context・理由） ---------- */
    function runLabel() {
      if (isRunning()) return '実行中…';
      return (data.state === 'ok' || data.last_run) ? '再実行' : 'リバース解析を実行';
    }
    function headHtml() {
      var d = data;
      var dis = isRunning() || !d.can_run || !d.site;
      var h = '<div class="c-page-head"><div class="c-page-head__main"><h2 class="c-page-head__title">リバース解析</h2>' +
        '<p class="c-page-head__desc">実行時観測だけでは見えなかった構造を、静的解析で補完します。静的な根拠は「推論」で、動作の確認ではありません。</p>' +
        '<div class="c-page-head__state">' + W.status.html(statusCode()) +
        '</div></div>';
      if (d.site) {
        h += '<div class="c-page-head__actions"><button type="button" class="c-btn c-btn--primary" data-rv="run"' + (dis ? ' disabled' : '') + '>' + esc(runLabel()) + '</button></div>';
      }
      return h + '</div>';
    }
    function contextHtml() {
      var d = data;
      if (!d.site) return '';
      var lr = d.last_run;
      var last = (lr && fmtTime(lr.finished_at)) ? esc(fmtTime(lr.finished_at)) : '<span class="rv-unk">未実行</span>';
      var secs = (lr && isNum(lr.seconds)) ? lr.seconds.toFixed(1) + ' 秒' : '<span class="rv-unk">未計測</span>';
      var h = '<div class="c-context" aria-label="現在の解析対象">' +
        '<span class="c-context__item">対象 <b>' + esc(d.site.domain) + '</b></span>' +
        '<span class="c-context__item">最終解析 <b>' + last + '</b></span>' +
        '<span class="c-context__item">所要 <b>' + secs + '</b></span>' +
        '<span class="c-context__item">状態 ' + W.status.html(statusCode()) +
        (lr && STATUS_LABEL[lr.status] ? ' <span class="rv-chip">前回: ' + esc(STATUS_LABEL[lr.status]) + '</span>' : '') + '</span>' +
        '</div>';
      if (!d.can_run && !isRunning() && d.state !== 'empty') {  // 結果が無い状態では下の状態カードが理由を出す
        if (d.cannot_run_reason) h += '<p class="rv-runhint rv-runhint-ng">実行できない理由: ' + esc(d.cannot_run_reason) + '</p>';
        if (d.cannot_run_next) h += '<p class="rv-runhint">次の行動: ' + esc(d.cannot_run_next) + '</p>';
      }
      return h;
    }
    function paintBar() {
      var bar = slot('bar');
      if (bar) bar.innerHTML = headHtml() + contextHtml();
      var r = reasonOf();
      W.reason(slot('reason'), r.t, r.k);
    }
    function refreshBar() { paintBar(); }

    /* ---------- 実行 ---------- */
    function stopPoll() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }
    function startPoll() {
      if (pollTimer) return;
      var my = token;
      pollTimer = setInterval(function () {
        if (my !== token || !document.contains(host)) { stopPoll(); return; }
        fetchJson(mainUrl())
          .then(function (j) {
            if (my !== token || !document.contains(host)) { stopPoll(); return; }
            if (!j || !j.running) { stopPoll(); load(); }
          })
          .catch(function () { /* 次の周期で再確認する */ });
      }, 3000);
    }
    function runAnalysis() {
      if (isRunning() || !data || !data.can_run) return;
      var my = token;
      runningLocal = true;
      runMsg = null;
      refreshBar();
      fetch('/api/sites/' + encodeURIComponent(domain || '') + '/reverse-analysis/run', { method: 'POST', credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
        .then(function (r) { return r.json().catch(function () { return null; }); })
        .then(function (j) {
          var ok = j && typeof j === 'object' && typeof j.result === 'string';
          runMsg = ok ? { result: j.result, message: j.message, next_action: j.next_action }
            : { result: 'error', message: 'リバース解析の応答を読み取れませんでした。', next_action: '時間をおいて再実行してください。' };
        })
        .catch(function () {
          runMsg = { result: 'error', message: 'リバース解析を実行できませんでした。', next_action: '通信状態を確認して、再実行してください。' };
        })
        .then(function () {
          runningLocal = false;
          if (my !== token || !document.contains(host)) return;
          if (runMsg && runMsg.result === 'success') W.toast('リバース解析が完了しました', 'success');
          else if (runMsg && runMsg.result === 'partial') W.toast('一部のみ取得しました', 'warning');
          else if (runMsg) W.toast('リバース解析を完了できませんでした', 'error');
          load();
        });
    }

    /* ---------- 状態表示（WS2D.state） ---------- */
    function paintState() {
      var el = slot('state');
      if (!el) return;
      var d = data;
      var cfg = null;
      if (netErr) {
        cfg = { kind: 'error', title: '最新の結果を取得できませんでした', message: netErr.message, next: netErr.next_action, retained: !!lastGood, actionLabel: '再読み込み', onAction: load };
      } else if (d.state === 'empty') {
        // 実行できないのに「実行を押す」と案内しない（理由と次の行動はサーバの判定どおりに出す）
        cfg = (!d.can_run && !isRunning() && d.cannot_run_reason)
          ? { kind: 'unavailable', title: 'リバース解析結果はまだありません（いまは実行できません）', message: d.cannot_run_reason, next: d.cannot_run_next }
          : { kind: 'empty', title: 'リバース解析結果はまだありません', next: d.next_action };
      } else if (d.state === 'error') {
        cfg = { kind: 'error', title: 'リバース解析の結果を表示できません', message: d.message, next: d.next_action, retained: true, actionLabel: '再読み込み', onAction: load };
      } else if (d.state === 'mismatch') {
        cfg = { kind: 'unverified', title: 'この結果は現在のサイトの記録と対応しません（未確認）', message: d.message, next: d.next_action, retained: true };
      } else if (d.state === 'ok' && d.status && d.status !== 'complete') {
        cfg = { kind: 'partial', title: '一部のみ取得しました', message: (d.message || '') + (d.status !== 'partial' ? ' 解析の状態: ' + d.status : ''), next: d.next_action };
      }
      if (cfg) W.state(el, cfg); else el.innerHTML = '';
    }
    function paintRunMsg() {
      var el = slot('msg');
      if (!el) return;
      var m = runMsg;
      runMsg = null;
      if (!m || m.result === 'success') { el.innerHTML = ''; return; }
      W.state(el, {
        kind: RESULT_KIND[m.result] || 'error', title: RESULT_TITLE[m.result] || '実行できませんでした',
        message: m.message, next: m.next_action, retained: data.state === 'ok'
      });
    }

    /* route を取得できなかった（取得不可）。0 件（見つからなかった）とは区別する */
    var ROUTE_NA = '取得不可';
    var ROUTE_NA_MSG = 'この解析では route を取得できません（対応外の書き方）。0 件という意味ではありません。';
    var ROUTE_NA_NEXT = '画面ルートは既存クロールの画面一覧（画面仕様）で確認してください。';
    function routeUnavailable() {
      var r = (data.summary || []).filter(function (x) { return x.key === 'route'; })[0];
      if (!r) return false;
      if (typeof r.unavailable === 'boolean') return r.unavailable;
      return r.after == null && isNum(r.before);
    }

    /* ---------- Before → After（WS2D.kpis） ---------- */
    function kpiItems() {
      var items = (data.summary || []).map(function (it) {
        var meas = isNum(it.before) && isNum(it.after);
        var sub;
        if (it.key === 'route' && routeUnavailable()) {
          return {
            label: it.label, value: ROUTE_NA, sub: 'この解析では取得不可・0 件ではない', category: 'unverified', unavailable: true,
            onClick: function () { selectTab('route', false); var b = host.querySelector('#rv-body'); if (b && b.scrollIntoView) b.scrollIntoView({ block: 'nearest' }); }
          };
        }
        if (it.key === 'api_runtime') {
          sub = (meas && it.after === it.before) ? '変化なし・増分に数えない' : '実行時の観測。増分に数えない';
        } else if (!meas) {
          sub = it.note || '未計測';
        } else {
          var diff = it.after - it.before;
          sub = (diff > 0 ? '増分 +' + diff : (diff === 0 ? '変化なし' : '増分 ' + diff)) + (it.note ? '・' + it.note : '');
        }
        var tabKey = KPI_TAB[it.key] || 'all';
        return {
          label: it.label,
          value: meas ? it.before + ' → ' + it.after : null,
          sub: sub,
          category: KPI_CAT[it.key] || 'inference',
          onClick: function () { selectTab(tabKey, false); var b = host.querySelector('#rv-body'); if (b && b.scrollIntoView) b.scrollIntoView({ block: 'nearest' }); }
        };
      });
      items.push({
        label: '追加解析時間',
        value: isNum(data.added_seconds) ? data.added_seconds.toFixed(3) + ' 秒' : null,
        sub: data.measured_once ? '単発測定' : (isNum(data.added_seconds) ? '' : '未計測'),
        category: 'fact'
      });
      return items;
    }

    /* ---------- 事実／推論／未確認の帯 ---------- */
    function splitHtml() {
      var n = { fact: 0, inference: 0, unverified: 0 };
      // System 03 の到達確認があれば route の区分を実測どおりに置き換える（指揮ホーム・System02 と同じ規則）
      var PROBE_CAT = { observed: 'fact', unreached: 'fact', auth_required: 'unverified', ambiguous: 'unverified', failed: 'unverified' };
      (data.evidence || []).forEach(function (e) {
        var p = e.group === 'route' ? probeOf(e) : null;
        n[(p && PROBE_CAT[p.status]) || W.evidence.category(EV_CODE[e.state] || 'unverified')]++;
      });
      function cell(k, label, v) {
        return '<div class="c-split__cell c-split__cell--' + k + '"><span class="c-split__label">' + label + '</span><span class="c-split__value">' + v + '</span></div>';
      }
      return '<div class="c-split" role="group" aria-label="根拠の区分（事実・推論・未確認）">' +
        cell('fact', '事実', n.fact) + cell('inference', '推論', n.inference) + cell('unverified', '未確認', n.unverified) + '</div>';
    }

    /* ---------- タブ ---------- */
    function group(g) { return (data.evidence || []).filter(function (e) { return e.group === g; }); }
    function rowsFor(key) { return key === 'all' ? (data.evidence || []) : group(key); }
    function count(key) {
      if (key === 'diag') return group('diagnostic').length + (data.diagnostics || []).length;
      if (key === 'route' && routeUnavailable()) return ROUTE_NA;
      return rowsFor(key).length;
    }
    function tabsHtml() {
      var h = '<div class="c-tabs rv-ctabs" role="tablist" aria-label="根拠の種類">';
      TABS.forEach(function (t) {
        var on = t.key === tab;
        h += '<button type="button" role="tab" class="rv-ctab' + (on ? ' on' : '') + '" id="rv-tab-' + t.key + '-' + token + '" data-tab="' + t.key +
          '" aria-selected="' + on + '" aria-controls="rv-panel-' + token + '" tabindex="' + (on ? '0' : '-1') + '">' +
          esc(t.label) + '<span class="rv-count">' + count(t.key) + '</span></button>';
      });
      return h + '</div>';
    }

    /* ---------- System 03 の探索結果（route のみ。無ければ未確認） ---------- */
    function probeOf(e) { return probe && probe.byId ? probe.byId[e.id] : null; }
    function probeBadge(e) {
      if (e.group !== 'route') return '<span class="rv-unk">対象外</span>';
      var p = probeOf(e);
      if (p && p.status === 'observed') {
        return p.authenticated ? W.evidence.html('observed_auth') : W.evidence.html('observed', '未認証実測');
      }
      var why = p ? (p.status_label || '到達未確認') : (probe && probe.state === 'ok' ? '探索対象外' : '探索未実施');
      return W.evidence.html('unverified') + '<div class="rv-sub">' + esc(why) + '</div>';
    }
    function probeNoteHtml() {
      if (routeUnavailable()) return '<p class="rv-probe-note">Route: ' + esc(ROUTE_NA_MSG) + '</p>';
      if (!probe || probe.state !== 'ok') {
        return '<p class="rv-probe-note">Route の到達は未確認です（System 03 の探索を実行すると、実測／未確認を併記します）。</p>';
      }
      var obs = 0, auth = 0, other = 0;
      group('route').forEach(function (e) {
        var p = probeOf(e);
        if (p && p.status === 'observed') { obs++; if (p.authenticated) auth++; } else other++;
      });
      return '<p class="rv-probe-note">System 03 の探索結果: 実測で到達 ' + obs + ' 件（うち認証済み ' + auth + ' 件）／未確認 ' + other +
        ' 件。到達は機能の正常動作を意味しません。</p>';
    }

    /* ---------- 一覧 ---------- */
    function originHtml(e) {
      if (e.group === 'api') {
        var m = e.method ? esc(e.method) : '不明';
        var o = ORIGIN_LABEL[e.origin] || '起点不明';
        return '<div class="rv-sub"><span class="rv-method' + (e.method ? '' : ' rv-unk') + '">' + m + '</span> <span class="rv-origin rv-or-' + esc(e.origin || 'x') + '">' + esc(o) + '</span></div>';
      }
      if (e.group === 'route') {
        var pr = probeOf(e);
        return '<div class="rv-sub">' + (pr && pr.status === 'observed' ? '静的候補・到達は System 03 で実測' : '静的候補・到達は未確認') + '</div>';
      }
      return '';
    }
    function tableHtml(rows) {
      if (!rows.length) return '<p class="rv-empty">該当する根拠はありません</p>';
      var h = '<div class="c-table-wrap"><table class="c-table"><thead><tr><th scope="col">種別</th><th scope="col">値</th><th scope="col">状態</th><th scope="col">探索結果</th><th scope="col">根拠の位置</th><th scope="col">出所</th></tr></thead><tbody>';
      rows.forEach(function (e) {
        var i = (data.evidence || []).indexOf(e);
        h += '<tr class="rv-row" tabindex="0" data-ev="' + i + '" aria-label="' + esc((e.kind_label || '') + ' ' + (e.value || '') + ' の詳細を開く') + '">' +
          '<td data-label="種別">' + esc(e.kind_label) + '</td>' +
          '<td data-label="値"><span class="rv-val">' + esc(e.value) + '</span>' + originHtml(e) + '</td>' +
          '<td data-label="状態">' + evBadge(e.state) + '</td>' +
          '<td data-label="探索結果">' + probeBadge(e) + '</td>' +
          '<td data-label="根拠の位置">' + (e.location ? '<code class="rv-loc">' + esc(e.location) + '</code>' : '<span class="rv-unk">位置なし</span>') + '</td>' +
          '<td data-label="出所">' + esc(e.provider) + '</td></tr>';
      });
      return h + '</tbody></table></div>';
    }
    function depsHtml() {
      var deps = data.dependencies || [];
      var h = '<h3 class="rv-h3">依存関係</h3>';
      if (!deps.length) return h + '<p class="rv-empty">該当する依存関係はありません</p>';
      h += '<ul class="rv-deps">';
      deps.forEach(function (d) {
        h += '<li class="rv-dep"><div class="rv-dep-line"><span class="rv-val">' + esc(d.source) + '</span> <span aria-hidden="true">→</span><span class="rv-vh"> から </span> <span class="rv-val">' + esc(d.target) + '</span>' +
          (d.external ? ' <span class="rv-chip">外部パッケージ</span>' : '') + '</div>' +
          '<div class="rv-dep-meta">' + esc(d.relation_label) + ' ' + evBadge(d.state) + ' ' +
          (d.location ? '<code class="rv-loc">' + esc(d.location) + '</code>' : '<span class="rv-unk">位置なし</span>') + '</div>';
        if (d.limitations && d.limitations.length) {
          h += '<details class="rv-dep-lim"><summary>制限事項（' + d.limitations.length + '）</summary><ul class="rv-lim">' +
            d.limitations.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul></details>';
        }
        h += '</li>';
      });
      return h + '</ul>';
    }
    function diagHtml() {
      var h = '';
      var sm = data.source_map || [];
      h += '<h3 class="rv-h3">解析ケースの結果</h3>';
      if (!sm.length) h += '<p class="rv-empty">該当する根拠はありません</p>';
      else {
        h += '<div class="c-table-wrap"><table class="c-table"><thead><tr><th scope="col">ケース</th><th scope="col">結果</th><th scope="col">意味</th></tr></thead><tbody>';
        sm.forEach(function (s) {
          var oc = s.outcome === 'success' ? 'done' : (s.outcome === 'partial' ? 'partial' : (s.outcome === 'failed' ? 'failed' : 'unverified'));
          h += '<tr><td data-label="ケース">' + esc(s.label || s.case) + '</td><td data-label="結果">' + W.status.html(oc, OUTCOME_LABEL[s.outcome] || s.outcome) + '</td><td data-label="意味">' + esc(s.meaning) + '</td></tr>';
        });
        h += '</tbody></table></div>';
      }
      var dg = data.diagnostics || [];
      h += '<h3 class="rv-h3">診断メッセージ</h3>';
      if (!dg.length) h += '<p class="rv-empty">診断メッセージはありません</p>';
      else {
        h += '<ul class="rv-diags">';
        dg.forEach(function (d) {
          var sv = SEV_LABEL[d.severity] ? d.severity : 'info';
          h += '<li class="rv-diag rv-sv-' + sv + '"><span class="rv-badge rv-sev-' + sv + '">' + esc(SEV_LABEL[sv]) + '</span> <span>' + esc(d.message) + '</span>' +
            (d.next_action ? '<div class="rv-sub">次の行動: ' + esc(d.next_action) + '</div>' : '') + '</li>';
        });
        h += '</ul>';
      }
      var cl = data.coverage_limitations || [];
      h += '<h3 class="rv-h3">網羅できていない範囲</h3>';
      if (!cl.length) h += '<p class="rv-empty">記載された制限はありません</p>';
      else h += '<ul class="rv-lim rv-lim-box">' + cl.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>';
      return h;
    }
    function panelHtml() {
      var h = '<div class="rv-panel" role="tabpanel" id="rv-panel-' + token + '" aria-labelledby="rv-tab-' + tab + '-' + token + '">';
      if (tab === 'diag') {
        var dr = group('diagnostic');
        if (dr.length) h += '<h3 class="rv-h3">診断の根拠</h3>' + tableHtml(dr);
        h += diagHtml();
      } else {
        var na = tab === 'route' && routeUnavailable();
        if (!na && (tab === 'route' || tab === 'all')) h += probeNoteHtml();
        if (na) h += '<div data-slot="route-na"></div>';
        else h += tableHtml(rowsFor(tab));
        if (tab === 'module') h += depsHtml();
      }
      return h + '</div>';
    }

    function paintPanel() {
      var el = slot('route-na');
      if (el) W.state(el, { kind: 'unavailable', title: 'Route はこの解析では取得不可', message: ROUTE_NA_MSG, next: ROUTE_NA_NEXT });
    }

    /* ---------- 全体 ---------- */
    function draw() {
      if (W.drawer) W.drawer.close();
      var hasBody = data.state === 'ok';
      var h = '<div class="rv"><div class="rv-bar" data-slot="bar"></div>' +
        '<div data-slot="reason"></div><div data-slot="msg" class="rv-slot"></div><div data-slot="state" class="rv-slot"></div>';
      if (hasBody) {
        h += '<section class="rv-sec" aria-label="実行時のみとリバース解析の比較"><h3 class="rv-h3 rv-h3-first">実行時のみ → ＋リバース解析（Before → After）</h3>' +
          '<div data-slot="kpis"></div>' + splitHtml() + '</section>' +
          '<div class="rv-card rv-main">' + tabsHtml() + '<div id="rv-body">' + panelHtml() + '</div></div>';
      }
      host.innerHTML = h + '</div>';
      paintBar();
      paintRunMsg();
      paintState();
      if (hasBody) {
        var items = kpiItems();
        W.kpis(slot('kpis'), items);
        var ks = slot('kpis') ? slot('kpis').children : [];
        items.forEach(function (it, i) {
          var v = it.unavailable && ks[i] && ks[i].querySelector('.c-kpi__value');
          if (v) v.classList.add('is-unmeasured');
        });
        paintPanel();
      }
      if (data.running && !runningLocal) startPoll();
    }
    function redrawBody() {
      var body = host.querySelector('#rv-body');
      var tabs = host.querySelector('.rv-ctabs');
      if (!body || !tabs) return;
      var tmp = document.createElement('div');
      tmp.innerHTML = tabsHtml();
      tabs.parentNode.replaceChild(tmp.firstChild, tabs);
      body.innerHTML = panelHtml();
      paintPanel();
    }

    /* ---------- ドロワー（WS2D.drawer 固定順: 主張→実測事実→推論→制限→出典） ---------- */
    function openDrawer(i, row) {
      var e = (data.evidence || [])[i];
      if (!e) return;
      var code = EV_CODE[e.state] || 'unverified';
      var p = e.group === 'route' ? probeOf(e) : null;
      var facts = [], inf = [], lim = (e.limitations || []).slice();
      if (e.origin === 'runtime') {
        facts.push({ label: '種別', value: e.kind_label }, { label: '値', value: e.value });
        if (e.group === 'api') facts.push({ label: 'メソッド', value: e.method || '不明' });
        facts.push({ label: '位置', value: e.location || '位置なし' });
      }
      if (p && p.status === 'observed') {
        facts.push({ label: '到達確認（System 03）', value: p.authenticated ? '認証済み実測（保存済みの認証状態で確認）' : '未認証実測' });
        if (p.http_status != null) facts.push({ label: 'HTTP ステータス', value: String(p.http_status) });
        if (p.final_url) facts.push({ label: '最終 URL', value: p.final_url });
        if (p.observed_at) facts.push({ label: '観測日時', value: fmtTime(p.observed_at) || String(p.observed_at) });
        if (p.limitation) lim.push(p.limitation);
      } else if (e.group === 'route') {
        lim.push('到達確認（System 03）: 未確認' + (p ? '（' + (p.status_label || '到達未確認') + (p.reason ? '：' + p.reason : '') + '）' : '（探索未実施）') + '。URL の到達は機能の正常動作を意味しません。');
      }
      var reached = !!(p && p.status === 'observed');
      if (e.origin === 'static') {
        if (e.group === 'route') {
          inf.push(reached ? 'ソースに画面ルートの宣言がある。到達は「実測事実」の System 03 の確認による（画面内容・機能の正しさは未確認）。'
            : 'ソースに画面ルートの宣言がある。実際に到達できるかは未確認。');
        }
        if (e.group === 'api') inf.push('ソースに API 呼び出しがある。実行されるか・HTTP method は' + (e.method ? ' ' + e.method + ' と記述されている。' : '不明のまま（GET とは見なさない）。'));
        if (e.relation) inf.push('実行時の記録との対応: ' + e.relation);
      }
      var src = [{ label: '出所', value: e.provider || '不明' }, { label: '起点', value: ORIGIN_LABEL[e.origin] || '不明' },
        { label: '位置', value: e.location || '位置なし' }, { label: '解析バージョン', value: e.engine_version || '不明' }, { label: 'ID', value: e.id || '' }];
      W.drawer.open({
        title: (e.kind_label || '根拠') + ': ' + (e.value || ''),
        state: code, stateReason: EV_REASON[code],
        claim: reached ? String(e.claim || '').replace('（到達は未確認）', '（到達は System 03 で実測。機能の正常動作は未確認）') : e.claim, facts: facts, inferences: inf, limitations: lim, sources: src, returnFocus: row
      });
    }

    /* ---------- イベント（host に 1 回だけ付け替える） ---------- */
    if (host._rvHandlers) {
      host.removeEventListener('click', host._rvHandlers.click);
      host.removeEventListener('keydown', host._rvHandlers.key);
    }
    function selectTab(key, focus) {
      tab = key;
      redrawBody();
      if (focus) { var b = host.querySelector('.rv-ctab[data-tab="' + key + '"]'); if (b) b.focus(); }
    }
    function onClick(ev) {
      var t = ev.target;
      var act = t.closest ? t.closest('[data-rv]') : null;
      if (act) {
        var a = act.getAttribute('data-rv');
        if (a === 'reload') { load(); return; }
        if (a === 'run') { runAnalysis(); return; }
      }
      var tb = t.closest ? t.closest('.rv-ctab') : null;
      if (tb && host.contains(tb)) { selectTab(tb.getAttribute('data-tab'), false); return; }
      var row = t.closest ? t.closest('.rv-row') : null;
      if (row && host.contains(row)) openDrawer(parseInt(row.getAttribute('data-ev'), 10), row);
    }
    function onKey(ev) {
      var k = ev.key, t = ev.target;
      if (t.classList && t.classList.contains('rv-ctab')) {
        var keys = TABS.map(function (x) { return x.key; });
        var idx = keys.indexOf(t.getAttribute('data-tab'));
        var n = -1;
        if (k === 'ArrowRight') n = (idx + 1) % keys.length;
        else if (k === 'ArrowLeft') n = (idx - 1 + keys.length) % keys.length;
        else if (k === 'Home') n = 0;
        else if (k === 'End') n = keys.length - 1;
        if (n >= 0) { ev.preventDefault(); selectTab(keys[n], true); }
        return;
      }
      if (t.classList && t.classList.contains('rv-row') && (k === 'Enter' || k === ' ')) {
        ev.preventDefault();
        openDrawer(parseInt(t.getAttribute('data-ev'), 10), t);
      }
    }
    host._rvHandlers = { click: onClick, key: onKey };
    host.addEventListener('click', onClick);
    host.addEventListener('keydown', onKey);

    load();
  }

  T.reverseRender = reverseRender;
})();
