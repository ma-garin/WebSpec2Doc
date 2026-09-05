/* 報告書の一覧と本文。
 *
 * healing.js とはヘルパーを共有しない。あちらは IIFE の中に閉じていて
 * window に何も出していないため、外から呼べない。ここでは必要な分だけ
 * 作り直している（重複より、片方を直したときにもう片方が壊れる方が高くつく）。
 *
 * innerHTML は使わない。値は必ず textContent で入れる。
 */
(function () {
  'use strict';

  var IS_ADMIN = document.body.getAttribute('data-hl-admin') === 'true';

  /* ---------------- 小さなヘルパー ---------------- */

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text != null) { node.textContent = String(text); }
    return node;
  }

  function on(id, type, fn) {
    var node = document.getElementById(id);
    if (node) { node.addEventListener(type, fn); }
    return node;
  }

  function showError(message) {
    var box = document.getElementById('hl-error');
    if (!box) { return; }
    box.textContent = '';
    box.appendChild(el('div', null, message));
    box.hidden = false;
  }

  function clearError() {
    var box = document.getElementById('hl-error');
    if (box) { box.hidden = true; box.textContent = ''; }
  }

  function api(path, options) {
    return fetch(path, options || {}).then(function (res) {
      if (res.status === 403) {
        throw new Error('この操作には管理者権限が必要です。');
      }
      return res.json().then(function (data) {
        if (!res.ok) { throw new Error((data && data.error) || '処理に失敗しました'); }
        return data;
      });
    });
  }

  /* 相対時刻。24 時間以内は「3 分前」、それ以降は日付。 */
  function relTime(iso) {
    if (!iso) { return '—'; }
    var t = new Date(iso);
    if (isNaN(t.getTime())) { return iso; }
    var diff = (Date.now() - t.getTime()) / 1000;
    if (diff < 60) { return 'たった今'; }
    if (diff < 3600) { return Math.floor(diff / 60) + ' 分前'; }
    if (diff < 86400) { return Math.floor(diff / 3600) + ' 時間前'; }
    return iso.slice(0, 10);
  }

  /* パスは末尾を残して省略する。先頭を切らないと、どのリポジトリか分からなくなる。 */
  function tailPath(text, max) {
    var s = String(text || '');
    if (s.length <= max) { return s; }
    return '…' + s.slice(s.length - max + 1);
  }

  /* ---------------- 一覧 ---------------- */

  var state = { status: 'awaiting', projectId: '' };

  function verifyBadge(report) {
    if (report.verify_after_ok === true) { return el('span', 'hl-badge is-ok', report.verify_after); }
    if (report.verify_after_ok === false) { return el('span', 'hl-badge is-err', report.verify_after); }
    return el('span', 'hl-badge is-mute', report.verify_after || '未実行');
  }

  function attentionCell(report) {
    if (report.action_empty) {
      return el('span', 'hl-badge is-mute', '直っていません');
    }
    if (report.attention_high > 0) {
      return el('span', 'hl-badge is-err', report.attention_count + ' 件');
    }
    if (report.attention_count > 0) {
      return el('span', 'hl-badge is-warn', report.attention_count + ' 件');
    }
    return el('span', 'hl-badge is-mute', 'なし');
  }

  function renderRow(report) {
    var tr = el('tr');
    tr.setAttribute('role', 'link');
    tr.setAttribute('tabindex', '0');
    var href = '/healing/reports/' + encodeURIComponent(report.report_id);
    function open() { window.location.href = href; }
    tr.addEventListener('click', open);
    tr.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); open(); }
    });

    var tdProject = el('td', 'hl-cell-name');
    tdProject.appendChild(el('b', null, report.project_name || '—'));
    if (report.target_url) {
      tdProject.appendChild(el('small', null, tailPath(report.target_url, 34)));
    }
    tr.appendChild(tdProject);

    var tdTitle = el('td', 'hl-cell-name');
    tdTitle.appendChild(el('b', null, report.title || '（件名なし）'));
    var sub = [report.incident_screen_id, report.incident_screen_name].filter(Boolean).join(' ');
    if (sub) { tdTitle.appendChild(el('small', null, sub)); }
    tr.appendChild(tdTitle);

    var tdVerify = el('td');
    tdVerify.appendChild(verifyBadge(report));
    tr.appendChild(tdVerify);

    var tdAttention = el('td');
    tdAttention.appendChild(attentionCell(report));
    tr.appendChild(tdAttention);

    var tdWhen = el('td', 'hl-cell-when', relTime(report.created_at));
    tdWhen.title = report.created_at || '';
    tr.appendChild(tdWhen);

    var tdAction = el('td', 'hl-cell-action');
    var btn = el('button', 'hl-btn hl-btn-sm', '読む');
    btn.type = 'button';
    btn.addEventListener('click', function (ev) { ev.stopPropagation(); open(); });
    tdAction.appendChild(btn);
    tr.appendChild(tdAction);
    return tr;
  }

  function renderReports(reports) {
    var body = document.getElementById('hl-reports-body');
    var empty = document.getElementById('hl-reports-empty');
    var table = document.getElementById('hl-reports-table');
    if (!body) { return; }
    body.textContent = '';
    var has = reports && reports.length > 0;
    if (table) { table.hidden = !has; }
    if (empty) {
      empty.hidden = has;
      empty.textContent = state.status === 'awaiting'
        ? '承認待ちの報告書はありません。'
        : 'この状態の報告書はありません。';
    }
    (reports || []).forEach(function (r) { body.appendChild(renderRow(r)); });
  }

  function loadReports() {
    clearError();
    var params = new URLSearchParams({ status: state.status, limit: '200' });
    if (state.projectId) { params.set('project_id', state.projectId); }
    api('/api/healing/reports?' + params.toString())
      .then(function (data) { renderReports(data.reports || []); })
      .catch(function (e) { showError('報告書を読み込めませんでした: ' + e.message); });
  }

  function loadCount() {
    api('/api/healing/reports/count?status=awaiting')
      .then(function (data) {
        var badge = document.getElementById('hl-nav-count');
        if (!badge) { return; }
        var n = Number(data.count || 0);
        badge.textContent = n > 0 ? String(n) : '';
        badge.hidden = n === 0;
      })
      .catch(function () { /* バッジが出ないだけなので黙って諦める */ });
  }

  function loadProjects() {
    api('/api/healing/projects')
      .then(function (data) {
        var sel = document.getElementById('hl-project-filter');
        if (!sel) { return; }
        (data.projects || []).forEach(function (p) {
          var opt = el('option', null, p.name || p.project_id);
          opt.value = p.project_id;
          sel.appendChild(opt);
        });
      })
      .catch(function () { /* 絞り込みが効かないだけ */ });
  }

  function bindChips() {
    var chips = document.querySelectorAll('.hl-chip[data-status]');
    Array.prototype.forEach.call(chips, function (chip) {
      chip.addEventListener('click', function () {
        Array.prototype.forEach.call(chips, function (c) { c.classList.remove('is-on'); });
        chip.classList.add('is-on');
        state.status = chip.getAttribute('data-status') || 'awaiting';
        loadReports();
      });
    });
  }

  function init() {
    if (!document.getElementById('hl-reports-table')) { return; }
    bindChips();
    on('hl-project-filter', 'change', function (ev) {
      state.projectId = ev.target.value || '';
      loadReports();
    });
    loadProjects();
    loadReports();
    loadCount();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
