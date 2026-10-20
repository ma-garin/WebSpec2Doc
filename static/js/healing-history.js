'use strict';

/* オートヒーリング設定画面（templates/healing.html）: 実行履歴: 一覧・もっと見る・表のラベル
   読み込み順: healing-core.js → healing-projects.js → healing-report.js → healing-run.js → healing-actions.js → healing-history.js → healing.js。
   ファイル間の共有は window.HealingApp（HL）だけ。他ファイルの関数は呼び出し時に HL から引く。 */
(function (HL) {
  /* ---- 他ファイルの宣言 ---- */
  var $ = HL.$;
  var STATUS_LABELS = HL.STATUS_LABELS;
  function apiFetch() { return HL.apiFetch.apply(this, arguments); }
  function asList() { return HL.asList.apply(this, arguments); }
  function el() { return HL.el.apply(this, arguments); }
  function flattenParens() { return HL.flattenParens.apply(this, arguments); }
  function fmtDuration() { return HL.fmtDuration.apply(this, arguments); }
  function fmtRelTime() { return HL.fmtRelTime.apply(this, arguments); }
  function fmtTime() { return HL.fmtTime.apply(this, arguments); }
  function getProject() { return HL.getProject.apply(this, arguments); }
  function hasWS() { return HL.hasWS.apply(this, arguments); }
  function humanizeError() { return HL.humanizeError.apply(this, arguments); }
  function selectProject() { return HL.selectProject.apply(this, arguments); }
  function setTail() { return HL.setTail.apply(this, arguments); }
  function showError() { return HL.showError.apply(this, arguments); }
  var state = HL.state;
  function statusBadgeClass() { return HL.statusBadgeClass.apply(this, arguments); }
  function switchView() { return HL.switchView.apply(this, arguments); }


  /* ---------------- 実行履歴ビュー ---------------- */

  function loadHistory(limit) {
    limit = limit || 20;
    state.historyLimit = limit;
    return apiFetch('/runs?limit=' + limit).then(function (data) {
      state.historyRuns = asList(data, 'runs');
      renderHistory();
    }).catch(function (e) {
      showError('実行履歴を取得できませんでした: ' + e.message);
      var host = document.getElementById('hl-runs-state');
      if (hasWS() && window.WS2D.state && host) {
        var kept = (state.historyRuns || []).length > 0;
        window.WS2D.state(host, {
          kind: 'error', title: '実行履歴を取得できませんでした', message: e.message,
          retained: kept, next: '通信を確認して、もう一度読み込んでください。',
          actionLabel: '再読み込み', onAction: function () { loadHistory(limit); }
        });
      }
    });
  }

  function projectPath(projectId) {
    var p = getProject(projectId);
    if (!p) { return ''; }
    return p.root_path || p.repo_path || p.path || p.local_path || '';
  }

  function projectMaxIterations(projectId) {
    var p = getProject(projectId);
    if (!p) { return 0; }
    var n = p.max_iterations || p.max_rounds || 0;
    return (typeof n === 'number' && n > 0) ? n : 0;
  }

  /* 件数と並び順を表の外に出す。もっと見るがある間は「全件」と言わない。 */
  function renderHistoryMeta(count, truncated) {
    var tbody = $['hl-runs'];
    var table = tbody ? tbody.parentNode : null;
    if (!table || !table.parentNode) { return; }
    var meta = document.getElementById('hl-runs-meta');
    if (!meta) {
      meta = el('div', 'hl-list-meta');
      meta.id = 'hl-runs-meta';
      table.parentNode.insertBefore(meta, table);
    }
    meta.hidden = count === 0;
    meta.textContent = count === 0 ? ''
      : (truncated ? '新しい順・新しい ' + count + ' 件を表示中' : '新しい順・全 ' + count + ' 件');
  }

  function renderHistory() {
    var tbody = $['hl-runs'];
    tbody.textContent = '';
    var runs = state.historyRuns || [];
    var limit = state.historyLimit || 20;
    var stateHost = document.getElementById('hl-runs-state');
    if (stateHost) { stateHost.textContent = ''; }
    if (runs.length === 0 && stateHost && window.WS2D && window.WS2D.state) {
      // 空状態は共通部品で出す（旧い空表示は重複するので隠す）。
      $['hl-runs-empty'].hidden = true;
      window.WS2D.state(stateHost, {
        kind: 'empty', title: 'まだ実行がありません',
        message: '実行の履歴はここに並びます。',
        next: '「実行」で対象のコードベースを選び、ヒーリングを開始してください。'
      });
    } else {
      $['hl-runs-empty'].hidden = runs.length > 0;
    }
    $['hl-runs-more'].hidden = runs.length < limit;
    renderHistoryMeta(runs.length, runs.length >= limit);
    runs.forEach(function (r) {
      var tr = el('tr', 'hl-runs-row');
      tr.tabIndex = 0;
      tr.setAttribute('role', 'link');
      tr.title = 'この行を開くと実行の詳細に移動します';
      var open = function () {
        selectProject(r.project_id, { openRunId: r.run_id });
        switchView('run');
      };
      tr.addEventListener('click', open);
      tr.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter') { ev.preventDefault(); open(); }
      });

      var tdStatus = el('td');
      tdStatus.appendChild(el('span', 'hl-badge ' + statusBadgeClass(r.status), STATUS_LABELS[r.status] || r.status));
      // 失敗は理由が無いと次の手が決まらない。冒頭だけ出し、全文は title に入れる。
      if (r.status === 'failed' && r.error) {
        var reason = el('div', 'hl-run-reason', humanizeError(flattenParens(String(r.error))).slice(0, 60));
        reason.title = String(r.error);
        tdStatus.appendChild(reason);
      }
      tr.appendChild(tdStatus);

      var tdStart = el('td', null, fmtRelTime(r.started_at));
      tdStart.title = fmtTime(r.started_at);
      tr.appendChild(tdStart);

      var dur = fmtDuration(r.started_at, r.finished_at);
      var tdDur = el('td', 'num', dur || '—');
      tdDur.title = dur ? ('終了 ' + fmtTime(r.finished_at)) : '終了していません';
      tr.appendChild(tdDur);

      var tdTarget = el('td');
      tdTarget.appendChild(el('div', 'hl-runs-name', r.project_name || r.project_id || ''));
      var path = projectPath(r.project_id);
      if (path) { tdTarget.appendChild(setTail(el('div', 'hl-runs-path hl-tail'), path, 32)); }
      tr.appendChild(tdTarget);

      var maxIt = projectMaxIterations(r.project_id);
      var itText = '—';
      if (r.iterations != null) { itText = String(r.iterations) + (maxIt ? ' / ' + maxIt : ''); }
      var tdIter = el('td', 'num', itText);
      if (maxIt) { tdIter.title = '周回 ' + r.iterations + ' / 上限 ' + maxIt; }
      tr.appendChild(tdIter);

      var fixed = r.fixed_count != null ? r.fixed_count : 0;
      var detected = r.defect_count != null ? r.defect_count : 0;
      var tdFixed = el('td', 'num', fixed + ' / ' + detected);
      tdFixed.title = '直した ' + fixed + ' 件 / 検出 ' + detected + ' 件';
      tr.appendChild(tdFixed);

      var tdPr = el('td');
      if (r.pr_number) {
        var label = '#' + r.pr_number;
        if (r.pr_url) {
          var link = el('a', 'hl-pr-link', label);
          link.href = r.pr_url;
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
          link.title = (r.pr_state ? r.pr_state + ' — ' : '') + r.pr_url;
          link.addEventListener('click', function (ev) { ev.stopPropagation(); });
          tdPr.appendChild(link);
        } else {
          var plain = el('span', null, label);
          if (r.pr_state) { plain.title = r.pr_state; }
          tdPr.appendChild(plain);
        }
      } else {
        tdPr.appendChild(el('span', 'hl-none', '—'));
      }
      tr.appendChild(tdPr);

      var tdActions = el('td');
      var openBtn = el('button', 'btn-outline-sm hl-btn-ghost', '開く');
      openBtn.type = 'button';
      openBtn.addEventListener('click', function (ev) { ev.stopPropagation(); open(); });
      tdActions.appendChild(openBtn);
      tr.appendChild(tdActions);

      tbody.appendChild(tr);
    });
  }

  /* ---------------- 初期化 ---------------- */

  /* c-table は 816px 以下で行をカードにする。カードでは列見出しが消えるので、
     各セルに見出しを data-label として付ける。行は JS が差し替えるので監視して付け直す。 */
  function labelTableCells(tbody) {
    var table = tbody && tbody.parentNode;
    if (!table || !table.tHead) { return; }
    var heads = Array.prototype.map.call(table.tHead.rows[0].cells, function (th) { return th.textContent.trim(); });
    Array.prototype.forEach.call(tbody.rows, function (tr) {
      Array.prototype.forEach.call(tr.cells, function (td, i) {
        if (heads[i] && td.getAttribute('data-label') !== heads[i]) { td.setAttribute('data-label', heads[i]); }
      });
    });
  }

  function watchTableLabels(tbody) {
    if (!tbody || typeof MutationObserver === 'undefined') { return; }
    new MutationObserver(function () { labelTableCells(tbody); }).observe(tbody, { childList: true });
    labelTableCells(tbody);
  }

  /* ---- 他ファイルへ公開 ---- */
  HL.loadHistory = loadHistory;
  HL.watchTableLabels = watchTableLabels;
})(window.HealingApp = window.HealingApp || {});
