'use strict';

/* オートヒーリング設定画面（templates/healing.html）: 接続先: 確認行と行メニュー・接続先一覧・定期実行・登録フォーム・リポジトリ選択・接続確認
   読み込み順: healing-core.js → healing-projects.js → healing-report.js → healing-run.js → healing-actions.js → healing-history.js → healing.js。
   ファイル間の共有は window.HealingApp（HL）だけ。他ファイルの関数は呼び出し時に HL から引く。 */
(function (HL) {
  /* ---- 他ファイルの宣言 ---- */
  var $ = HL.$;
  var CHECK_DEFS = HL.CHECK_DEFS;
  function agentDisplayName() { return HL.agentDisplayName.apply(this, arguments); }
  function apiFetch() { return HL.apiFetch.apply(this, arguments); }
  function asList() { return HL.asList.apply(this, arguments); }
  function asObj() { return HL.asObj.apply(this, arguments); }
  function clearError() { return HL.clearError.apply(this, arguments); }
  function clearRunView() { return HL.clearRunView.apply(this, arguments); }
  function el() { return HL.el.apply(this, arguments); }
  function flattenParens() { return HL.flattenParens.apply(this, arguments); }
  function getProject() { return HL.getProject.apply(this, arguments); }
  function loadStats() { return HL.loadStats.apply(this, arguments); }
  function selectProject() { return HL.selectProject.apply(this, arguments); }
  function setPathTail() { return HL.setPathTail.apply(this, arguments); }
  function setTail() { return HL.setTail.apply(this, arguments); }
  function showError() { return HL.showError.apply(this, arguments); }
  var state = HL.state;
  function switchView() { return HL.switchView.apply(this, arguments); }
  function tailText() { return HL.tailText.apply(this, arguments); }


  /* 確認行は hidden だけでは Tab で到達し Enter で破壊操作が走る。
     hidden と inert は必ず同時に切り替える。開くときは他の確認行を必ず閉じる。 */
  var CONFIRM_IDS = ['hl-start-confirm', 'hl-cancel-confirm', 'hl-merge-confirm', 'hl-reject-confirm'];
  var rowConfirms = [];
  var openRowMenu = null;
  /* 管理者だけが実行できる操作（web/routes/healing.py の require_admin()）を
     JS 生成部分でも出し分ける。値は templates/healing.html の body 要素の data 属性から読む。
     属性が無い・読めないときは安全側に倒して false（操作を出さない）。 */
  var IS_ADMIN = false;

  function setConfirmOpen(node, open) {
    if (!node) { return; }
    node.hidden = !open;
    if (open) { node.removeAttribute('inert'); } else { node.setAttribute('inert', ''); }
  }

  function registerRowConfirm(node) {
    if (node && rowConfirms.indexOf(node) === -1) { rowConfirms.push(node); }
    return node;
  }

  function closeAllConfirms(except) {
    CONFIRM_IDS.forEach(function (id) {
      if ($[id] && $[id] !== except) { setConfirmOpen($[id], false); }
    });
    rowConfirms.forEach(function (n) {
      if (n !== except) { setConfirmOpen(n, false); }
    });
  }

  // 確認は開いたら中の最初のボタンへフォーカスを移し、Esc で閉じて開いた元へ戻す
  var confirmOpener = null;
  function openConfirm(node) {
    if (!node) { return; }
    closeAllConfirms(node);
    confirmOpener = document.activeElement;
    setConfirmOpen(node, true);
    var first = node.querySelector('button:not([disabled]), [href], input, textarea');
    if (first) { first.focus(); }
    if (!node.dataset.escBound) {
      node.dataset.escBound = '1';
      node.addEventListener('keydown', function (ev) {
        if (ev.key !== 'Escape' && ev.key !== 'Esc') { return; }
        ev.preventDefault(); ev.stopPropagation();
        setConfirmOpen(node, false);
        var o = confirmOpener; confirmOpener = null;
        if (o && o.isConnected && o.focus) { o.focus(); }
      });
    }
  }

  /* メニューは表のはみ出し制御（overflow）を持つラッパの中にある。行が末尾にあると
     下へ開いたリストが切り取られ、「…」を押しても何も出ないように見える
     （登録直後の行は必ず末尾に来るため、そこだけ再現していた）。
     開くあいだだけ body 直下へ移し、position: fixed で座標を与えて切り取りを避ける。 */
  function closeRowMenu() {
    if (!openRowMenu) { return; }
    var m = openRowMenu;
    openRowMenu = null;
    m.list.hidden = true;
    m.list.setAttribute('inert', '');
    m.list.classList.remove('hl-row-menu-float');
    m.list.style.top = '';
    m.list.style.left = '';
    if (m.wrap && m.list.parentNode !== m.wrap) { m.wrap.appendChild(m.list); }
    m.btn.setAttribute('aria-expanded', 'false');
  }

  function openRowMenuAt(wrap, btn, list) {
    closeRowMenu();
    list.hidden = false;
    list.removeAttribute('inert');
    list.classList.add('hl-row-menu-float');
    document.body.appendChild(list);
    var r = btn.getBoundingClientRect();
    var w = list.offsetWidth || 160;
    var h = list.offsetHeight || 0;
    var left = Math.max(8, Math.min(r.right - w, window.innerWidth - w - 8));
    var top = r.bottom + 4;
    // 下に入らないときはボタンの上へ開く。画面外の項目は存在しないのと同じ。
    if (h && top + h > window.innerHeight - 8) { top = Math.max(8, r.top - h - 4); }
    list.style.left = left + 'px';
    list.style.top = top + 'px';
    btn.setAttribute('aria-expanded', 'true');
    openRowMenu = { wrap: wrap, btn: btn, list: list };
  }

  /* IS_ADMIN と開いている行メニューは、このファイルだけが書き換える。初期化からはこの 2 つで触る。 */
  function setAdminFlag(value) { IS_ADMIN = value; }

  function closeRowMenuOnOutsideClick(ev) {
    if (!openRowMenu) { return; }
    if (openRowMenu.wrap.contains(ev.target) || openRowMenu.list.contains(ev.target)) { return; }
    closeRowMenu();
  }

  /* ---------------- 接続先（プロジェクト） ---------------- */

  function loadProjects() {
    return apiFetch('/projects').then(function (data) {
      state.projects = asList(data, 'projects');
      renderProjects();
      renderProjectSelect();
      if (state.selectedProjectId) { updateProjectMeta(); }
    }).catch(function (e) { showError('接続先の一覧を取得できませんでした: ' + e.message); });
  }

  function renderProjectSelect() {
    var sel = $['hl-project-select'];
    var prevValue = sel.value;
    sel.textContent = '';
    // 未選択なのに先頭の接続先が選ばれて見えると、一覧の「対象」表示と食い違う。
    if (!state.selectedProjectId) {
      var ph = el('option', null, '（未選択）');
      ph.value = '';
      sel.appendChild(ph);
    }
    state.projects.forEach(function (p) {
      var opt = el('option', null, p.name || p.project_id);
      opt.value = p.project_id;
      sel.appendChild(opt);
    });
    if (state.selectedProjectId && getProject(state.selectedProjectId)) {
      sel.value = state.selectedProjectId;
    } else if (prevValue && getProject(prevValue)) {
      sel.value = prevValue;
    }
  }

  function checkProject(projectId) {
    return apiFetch('/projects/' + projectId + '/check', { method: 'POST', body: JSON.stringify({}) })
      .then(function (data) {
        var list = asList(data, 'checks');
        if (!list.length) {
          list = CHECK_DEFS.map(function (def) {
            return getCheckItem(data, def.key) || { key: def.key, label: def.label, ok: false, detail: '' };
          });
        }
        var okAll = list.length > 0 && list.every(function (item) { return item.ok === true; });
        state.checkResults[projectId] = okAll;
        return { list: list, okAll: okAll };
      });
  }

  function getCheckItem(data, key) {
    var list = asList(data, 'checks');
    for (var i = 0; i < list.length; i++) {
      if (list[i].key === key || list[i].name === key) { return list[i]; }
    }
    if (data && data[key] && typeof data[key] === 'object') { return data[key]; }
    return null;
  }


  /* ---------------- 毎日の見張り ---------------- */

  /* 人がテストを回すまで、壊れていることは誰も知らない。時刻を決めておけば
     朝いちばんに報告書の下書きが出ている、という状態を作るための列。 */
  function pad2(n) { return (n < 10 ? '0' : '') + n; }

  function todayStr() {
    var d = new Date();
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
  }

  function nowHHMM() {
    var d = new Date();
    return pad2(d.getHours()) + ':' + pad2(d.getMinutes());
  }

  /* 「次はいつ動くのか」を、設定値ではなく起きることで書く。 */
  function monitorNextLabel(p) {
    if (!p.domain) { return 'サイト未設定'; }
    if (!p.monitor_enabled || !p.monitor_time) { return '見張っていません'; }
    if (p.monitor_last_run_on === todayStr()) {
      return '今日は実行済み・次は明日 ' + p.monitor_time;
    }
    if (nowHHMM() < p.monitor_time) { return '今日 ' + p.monitor_time + ' に実行'; }
    return 'まもなく実行します';
  }

  function saveMonitor(p, updates, note) {
    return apiFetch('/projects/' + encodeURIComponent(p.project_id), {
      method: 'PATCH',
      body: JSON.stringify(updates)
    }).then(function (data) {
      var saved = asObj(data, 'project');
      for (var i = 0; i < state.projects.length; i += 1) {
        if (state.projects[i].project_id === p.project_id) {
          state.projects[i] = saved || state.projects[i];
          break;
        }
      }
      if (note) { note.textContent = monitorNextLabel(saved || p); }
      showToast('毎日の見張りを保存しました');
    }).catch(function (e) { showError(e.message); });
  }

  function buildMonitorCell(p) {
    var td = el('td', 'hl-monitor-cell');
    var note = el('div', 'hl-monitor-note', monitorNextLabel(p));
    if (!IS_ADMIN) {
      td.appendChild(note);
      return td;
    }

    var row = el('div', 'hl-monitor-row');
    var label = el('label', 'hl-monitor-toggle');
    var box = document.createElement('input');
    box.type = 'checkbox';
    box.checked = !!p.monitor_enabled;
    box.setAttribute('aria-label', (p.name || p.project_id) + ' を毎日見張る');
    label.appendChild(box);
    label.appendChild(el('span', null, '見張る'));

    var time = document.createElement('input');
    time.type = 'time';
    time.className = 'hl-monitor-time';
    time.value = p.monitor_time || '09:00';
    time.setAttribute('aria-label', '見張る時刻');

    box.addEventListener('change', function () {
      p.monitor_enabled = box.checked;
      p.monitor_time = time.value || '09:00';
      saveMonitor(p, { monitor_enabled: box.checked, monitor_time: p.monitor_time }, note);
    });
    time.addEventListener('change', function () {
      p.monitor_time = time.value;
      saveMonitor(p, { monitor_time: time.value }, note);
    });

    var nowBtn = el('button', 'btn-outline-sm hl-monitor-now', '今すぐ');
    nowBtn.type = 'button';
    nowBtn.title = '時刻を待たずに 1 回だけ回します';
    nowBtn.addEventListener('click', function () {
      // 押した直後に何も起きないように見えると、二度押しで二重に回る。
      nowBtn.disabled = true;
      nowBtn.textContent = '実行中…';
      apiFetch('/projects/' + encodeURIComponent(p.project_id) + '/monitor/run-now', {
        method: 'POST',
        body: '{}'
      }).then(function (data) {
        if (data && data.run) {
          showToast('失敗を見つけました。報告書を下書きしています');
        } else {
          showToast((data && data.message) || 'テストは全部通りました');
        }
      }).catch(function (e) {
        showError(e.message);
      }).then(function () {
        nowBtn.disabled = false;
        nowBtn.textContent = '今すぐ';
      });
    });

    row.appendChild(label);
    row.appendChild(time);
    row.appendChild(nowBtn);
    td.appendChild(row);
    td.appendChild(note);
    return td;
  }

  function renderProjects() {
    var tbody = $['hl-projects'];
    tbody.textContent = '';
    rowConfirms = [];
    closeRowMenu();
    $['hl-projects-empty'].hidden = state.projects.length > 0;
    // 全行同じ検証コマンドなら情報量が無い。薄字にして全文は title に残す。
    var cmds = state.projects.map(function (x) { return String(x.verify_command == null ? '' : x.verify_command).trim(); });
    var uniformCmd = cmds.length > 1 && cmds.every(function (c) { return c === cmds[0]; });
    // 同じリポジトリパスの接続が複数あることを、名前の横で知らせる（エラーではない）。
    var repoPeers = {};
    state.projects.forEach(function (x) {
      var key = String(x.repo_path == null ? '' : x.repo_path).trim();
      if (!key) { return; }
      if (!repoPeers[key]) { repoPeers[key] = []; }
      repoPeers[key].push({ id: x.project_id, label: x.name || x.project_id || '(名称未設定)' });
    });
    state.projects.forEach(function (p) {
      // 選択は塗りボタンではなく行そのもので示す（塗りが縦に並ぶと名前もパスも読めない）。
      var isSelected = p.project_id === state.selectedProjectId;
      var rowClass = isSelected ? 'hl-row-selected' : '';
      // 登録直後の行は「選択」ではなく目印で示す。選んでいないものを選択扱いにしない。
      if (p.project_id === state.highlightProjectId) { rowClass += (rowClass ? ' ' : '') + 'hl-row-added'; }
      var tr = el('tr', rowClass || null);
      var pLabel = p.name || p.project_id || '(名称未設定)';
      var tdName = el('td', 'hl-name-cell');
      // 名前が主情報。注記を同じ行に並べると名前が先に切れて読めなくなるので下の行へ落とす。
      var nameLine = el('div', 'hl-proj-name hl-tail', pLabel);
      nameLine.title = pLabel;
      tdName.appendChild(nameLine);
      // サイトが未設定だと見張りも照合も動かない。設定済みかを一覧で分かるようにする。
      var siteName = String(p.domain == null ? '' : p.domain).trim();
      if (siteName) {
        var siteLine = el('div', 'hl-dup-note', siteName);
        siteLine.title = 'サイト: ' + siteName;
        tdName.appendChild(siteLine);
      }
      var repoKey = String(p.repo_path == null ? '' : p.repo_path).trim();
      var peers = (repoKey ? (repoPeers[repoKey] || []) : []).filter(function (x) { return x.id !== p.project_id; });
      if (peers.length) {
        var dupNote = el('div', 'hl-dup-note', '重複 ' + peers.length + ' 件');
        dupNote.title = '同じリポジトリを指す接続が他に ' + peers.length + ' 件あります:\n'
          + peers.map(function (x) { return x.label; }).join('\n');
        tdName.appendChild(dupNote);
      }
      tr.appendChild(tdName);
      tr.appendChild(setPathTail(el('td', 'hl-kv hl-tail'), p.repo_path, 34));
      tr.appendChild(el('td', null, p.default_branch || p.branch || ''));
      // 全行同じ検証コマンドのときは薄字にする。色は .hl-muted（CSS）に任せ、
      // opacity で全体を薄くしない（読めなくなるため）。
      var tdCmd = setTail(el('td', 'hl-kv hl-tail' + (uniformCmd ? ' hl-muted' : '')), p.verify_command, 30);
      tr.appendChild(tdCmd);
      var tdAgent = el('td', null, p.agent ? agentDisplayName(p.agent) : '');
      if (p.agent) { tdAgent.title = p.agent; }
      tr.appendChild(tdAgent);
      tr.appendChild(buildMonitorCell(p));

      // 行内は 2 つまで。4 つ並べると 1280px で押し出されて押せなくなる。
      var tdActions = el('td', 'hl-row-actions');
      // 既に対象の行は「実行へ進む」にする。接続先が 1 件だけだと、ここ以外に実行画面へ入る導線が無いため
      var useBtn = el('button', isSelected ? 'btn-primary' : 'btn-outline-sm', isSelected ? '対象 · 実行へ進む' : '対象にする');
      useBtn.type = 'button';
      useBtn.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
      useBtn.addEventListener('click', function () { selectProject(p.project_id); switchView('run'); });

      // 「対象にする」は行の選択と閲覧（GET /runs）だけで、書き込み API を叩かない。
      // 誰でも押せるので管理者判定の外に置く。
      tdActions.appendChild(useBtn);

      // 「…」の中身（接続を確認 / 編集 / 削除）は require_admin() が掛かる操作。
      // この行は JS が組み立てるため Jinja の hl_admin が届かない。同じ条件をここで持つ。
      if (IS_ADMIN) {
        var checkResult = el('span', 'hl-row-check-result');
        var projectLabel = p.name || p.project_id || '';

        var menuWrap = el('div', 'hl-row-menu');
        var menuBtn = el('button', 'btn-outline-sm hl-row-menu-btn', '…');
        menuBtn.type = 'button';
        menuBtn.setAttribute('aria-haspopup', 'true');
        menuBtn.setAttribute('aria-expanded', 'false');
        menuBtn.setAttribute('aria-label', 'その他の操作');
        menuBtn.title = projectLabel + ' のその他の操作';
        menuBtn.setAttribute('data-testid', 'hl-row-menu-btn');
        var menuList = el('div', 'hl-row-menu-list');
        menuList.setAttribute('role', 'menu');
        menuList.hidden = true;
        menuList.setAttribute('inert', '');

        function addMenuItem(label, extraClass, onPick) {
          var b = el('button', 'hl-row-menu-item' + (extraClass ? ' ' + extraClass : ''), label);
          b.type = 'button';
          b.setAttribute('role', 'menuitem');
          b.addEventListener('click', function () { closeRowMenu(); onPick(); });
          menuList.appendChild(b);
          return b;
        }

        addMenuItem('接続を確認', null, function () {
          checkResult.textContent = '確認中…';
          checkProject(p.project_id).then(function (result) {
            checkResult.textContent = result.okAll ? '接続OK' : '接続エラー';
          }).catch(function (e) {
            checkResult.textContent = '確認失敗';
            showError('接続確認に失敗しました: ' + e.message);
          });
        });
        addMenuItem('編集', null, function () { showConnectForm(p); });
        addMenuItem('削除', 'hl-btn-danger', function () { openConfirm(deleteConfirm); });

        menuBtn.addEventListener('click', function (ev) {
          ev.stopPropagation();
          var wasOpen = !!openRowMenu && openRowMenu.list === menuList;
          closeRowMenu();
          if (wasOpen) { return; }
          openRowMenuAt(menuWrap, menuBtn, menuList);
        });
        menuWrap.appendChild(menuBtn);
        menuWrap.appendChild(menuList);

        var deleteConfirm = registerRowConfirm(el('div', 'hl-confirm hl-row-confirm'));
        setConfirmOpen(deleteConfirm, false);
        deleteConfirm.appendChild(el('span', null, '「' + projectLabel + '」の接続を削除しますか？'));
        var delYes = el('button', 'btn-primary hl-btn-danger', 'はい、削除する');
        delYes.type = 'button';
        delYes.addEventListener('click', function () { setConfirmOpen(deleteConfirm, false); deleteProject(p.project_id); });
        var delNo = el('button', 'btn-outline-sm', 'やめる');
        delNo.type = 'button';
        delNo.addEventListener('click', function () { setConfirmOpen(deleteConfirm, false); });
        deleteConfirm.appendChild(delYes);
        deleteConfirm.appendChild(delNo);

        tdActions.appendChild(menuWrap);
        tdActions.appendChild(checkResult);
        tdActions.appendChild(deleteConfirm);
      }
      tr.appendChild(tdActions);
      tbody.appendChild(tr);
    });
  }

  function showConnectForm(project) {
    state.editingProjectId = project ? project.project_id : null;
    $['hl-connect-form'].hidden = false;
    setupRepoPicker(!project);
    if (project) {
      $['hl-form-title'].textContent = '接続を編集する';
      $['hl-connect-submit'].textContent = '保存する';
      $['hl-f-name'].value = project.name || '';
      $['hl-f-path'].value = project.repo_path || '';
      $['hl-f-branch'].value = project.default_branch || project.branch || 'main';
      $['hl-f-cmd'].value = project.verify_command || '';
      $['hl-f-remote'].value = project.remote || 'origin';
      $['hl-f-github'].value = project.github_repo || '';
      if (project.agent) { $['hl-f-agent'].value = project.agent; }
      $['hl-f-max-iter'].value = project.max_iterations || 3;
      $['hl-f-concurrency'].value = project.max_parallel_agents || 3;
    } else {
      $['hl-form-title'].textContent = 'コードベースを接続する';
      $['hl-connect-submit'].textContent = '接続する';
      $['hl-f-name'].value = '';
      $['hl-f-path'].value = '';
      $['hl-f-branch'].value = 'main';
      $['hl-f-cmd'].value = '';
      $['hl-f-remote'].value = 'origin';
      $['hl-f-github'].value = '';
      $['hl-f-max-iter'].value = 3;
      $['hl-f-concurrency'].value = 3;
    }
    loadSiteOptions(project ? (project.domain || '') : '');
  }
  function hideConnectForm() {
    $['hl-connect-form'].hidden = true;
  }

  /* ---------------- サイトの選択リスト ----------------
     サイト（01 の解析結果）は毎日の見張り・画面仕様との照合・失敗箇所の限局が
     使う。手入力させると綴りのずれで全部が静かに効かなくなるので、サーバが
     列挙した候補（GET /api/healing/sites）から選ばせる。 */

  function siteOptionLabel(site) {
    var domain = String(site.domain == null ? '' : site.domain).trim();
    var title = String(site.title == null ? '' : site.title).trim();
    var screens = parseInt(site.screens, 10);
    var notes = [];
    if (title) { notes.push(title); }
    if (screens > 0) { notes.push(screens + ' 画面'); }
    return notes.length ? (domain + '（' + notes.join('・') + '）') : domain;
  }

  function setSiteOptions(sites, current) {
    var select = $['hl-f-domain'];
    if (!select) { return; }
    var selected = String(current == null ? '' : current).trim();
    select.textContent = '';
    var none = el('option', null, '（未設定）');
    none.value = '';
    select.appendChild(none);
    var known = false;
    sites.forEach(function (site) {
      var domain = String(site.domain == null ? '' : site.domain).trim();
      if (!domain) { return; }
      if (domain === selected) { known = true; }
      var opt = el('option', null, siteOptionLabel(site));
      opt.value = domain;
      if (site.updated_at) { opt.title = '最終更新 ' + String(site.updated_at).replace('T', ' '); }
      select.appendChild(opt);
    });
    // 保存済みの値は候補に無くても残す。解析結果を消しただけで設定が消えるのは事故。
    if (selected && !known) {
      var kept = el('option', null, selected + '（一覧にありません）');
      kept.value = selected;
      select.appendChild(kept);
    }
    select.value = selected;
    var status = $['hl-f-domain-status'];
    if (status) {
      var empty = !sites.length && !selected;
      status.hidden = !empty;
      status.textContent = empty ? '01 で解析したサイトがまだありません。' : '';
    }
  }

  function loadSiteOptions(current) {
    setSiteOptions(state.sites || [], current);
    return apiFetch('/sites').then(function (data) {
      state.sites = (data && Array.isArray(data.sites)) ? data.sites : [];
      setSiteOptions(state.sites, current);
    }).catch(function () { /* 取れなくても保存済みの値は選べるまま残す */ });
  }

  /* ---------------- 接続するリポジトリの選択リスト ----------------
     許可ルートは長大な絶対パスで、手入力は現実的でない。サーバが列挙した候補
     （GET /api/healing/discover）から選ばせる。API が無い・落ちている間は
     従来どおりパス手入力に落ちる（一覧が出ないだけで接続はできる）。 */

  var repoPickerUi = null;

  function setIdIfFree(node, id) {
    if (!document.getElementById(id)) { node.id = id; }
    return node;
  }

  function pathFieldWrap() {
    var input = $['hl-f-path'];
    return input && input.parentNode ? input.parentNode : null;
  }

  function ensureRepoPicker() {
    if (repoPickerUi) { return repoPickerUi; }
    var form = $['hl-connect-form'];
    var grid = form ? form.querySelector('.hl-form-grid') : null;
    if (!form || !grid) { return null; }

    var box = el('div', 'hl-repo-picker');
    setIdIfFree(box, 'hl-repo-picker');
    box.hidden = true;

    var head = el('div', 'hl-repo-head');
    var label = el('label', 'hl-field-label', '接続するリポジトリ');
    var count = el('span', 'hl-repo-count');
    head.appendChild(label);
    head.appendChild(count);

    var filter = el('input', 'hl-field hl-repo-filter');
    filter.type = 'search';
    filter.placeholder = '名前・パスで絞り込む';
    filter.autocomplete = 'off';
    setIdIfFree(filter, 'hl-repo-filter');
    if (filter.id) { label.setAttribute('for', filter.id); }

    var list = el('div', 'hl-repo-list');
    list.setAttribute('role', 'list');

    var status = el('p', 'hl-repo-status');
    status.hidden = true;

    var manual = el('button', 'hl-repo-manual-toggle', '一覧に無い場所を指定する');
    manual.type = 'button';
    setIdIfFree(manual, 'hl-repo-manual-toggle');

    box.appendChild(head);
    box.appendChild(filter);
    box.appendChild(list);
    box.appendChild(status);
    box.appendChild(manual);
    form.insertBefore(box, grid);

    filter.addEventListener('input', function () { renderRepoList(); });
    manual.addEventListener('click', function () { setManualPath(true); });

    repoPickerUi = { box: box, filter: filter, list: list, count: count, status: status, manual: manual };
    return repoPickerUi;
  }

  /* パス入力欄は消さない。選択リストが使えるときだけ既定で畳む。 */
  function setManualPath(open) {
    var wrap = pathFieldWrap();
    if (wrap) { wrap.hidden = !open; }
    if (repoPickerUi) { repoPickerUi.manual.hidden = open; }
    if (open && $['hl-f-path'] && $['hl-f-path'].focus) { $['hl-f-path'].focus(); }
  }

  function connectedPaths() {
    var used = {};
    state.projects.forEach(function (p) {
      var k = String(p.repo_path == null ? '' : p.repo_path).trim();
      if (k) { used[k] = true; }
    });
    return used;
  }

  /* 埋めるだけ。どの欄も編集可能なまま残す（提案を上書きできないと使えない）。 */
  function fillFormFromRepo(repo) {
    if ($['hl-f-name']) { $['hl-f-name'].value = repo.name || ''; }
    if ($['hl-f-path']) { $['hl-f-path'].value = repo.path || ''; }
    if ($['hl-f-branch'] && repo.branch) { $['hl-f-branch'].value = repo.branch; }
    if ($['hl-f-cmd'] && repo.suggested_command) { $['hl-f-cmd'].value = repo.suggested_command; }
    if ($['hl-f-github'] && repo.github_repo) { $['hl-f-github'].value = repo.github_repo; }
    state.selectedRepoPath = repo.path || '';
    renderRepoList();
  }

  function renderRepoList() {
    var ui = ensureRepoPicker();
    if (!ui) { return; }
    var repos = state.discoverRepos || [];
    var q = ui.filter.value.trim().toLowerCase();
    var used = connectedPaths();
    var shown = repos.filter(function (r) {
      if (!q) { return true; }
      var hay = (String(r.name || '') + ' ' + String(r.display_path || r.path || '')).toLowerCase();
      return hay.indexOf(q) !== -1;
    });
    var countText = q ? (shown.length + ' / ' + repos.length + ' 件') : (repos.length + ' 件');
    ui.count.textContent = countText + (state.discoverTruncated ? '（一部のみ）' : '');
    ui.list.textContent = '';
    if (!shown.length) {
      ui.status.hidden = false;
      ui.status.textContent = repos.length
        ? '絞り込みに一致するリポジトリがありません。'
        : '許可された場所にリポジトリが見つかりませんでした。';
      return;
    }
    ui.status.hidden = true;
    shown.forEach(function (r) {
      var connected = r.already_connected === true || used[String(r.path || '')] === true;
      var item = el('button', 'hl-repo-item');
      item.type = 'button';
      item.setAttribute('role', 'listitem');
      if (state.selectedRepoPath && state.selectedRepoPath === r.path) { item.classList.add('is-picked'); }
      var main = el('span', 'hl-repo-main');
      main.appendChild(el('span', 'hl-repo-name', r.name || r.path || ''));
      main.appendChild(setPathTail(el('span', 'hl-repo-path'), r.display_path || r.path || '', 54));
      if (r.suggested_command) {
        main.appendChild(setTail(el('span', 'hl-repo-cmd'), '検証: ' + r.suggested_command, 52));
      }
      item.appendChild(main);
      var badges = el('span', 'hl-repo-badges');
      if (r.branch) { badges.appendChild(el('span', 'hl-repo-badge', r.branch)); }
      if (connected) { badges.appendChild(el('span', 'hl-repo-badge is-connected', '接続済み')); }
      item.appendChild(badges);
      if (connected) {
        item.disabled = true;
        item.title = String(r.path || '') + '\nこの場所はすでに接続済みです。';
      } else {
        item.title = String(r.path || '');
        item.addEventListener('click', function () { fillFormFromRepo(r); });
      }
      ui.list.appendChild(item);
    });
  }

  function applyDiscoverState() {
    var ui = ensureRepoPicker();
    if (!ui) { return; }
    var repos = state.discoverRepos || [];
    // 一覧が使えないときは空のリストを見せず、従来のパス手入力へ落とす。
    if (state.discoverFailed || !repos.length) {
      ui.box.hidden = true;
      setManualPath(true);
      return;
    }
    ui.box.hidden = false;
    setManualPath(false);
    renderRepoList();
  }

  function loadDiscover() {
    if (state.discoverLoading) { return; }
    state.discoverLoading = true;
    apiFetch('/discover').then(function (data) {
      state.discoverLoading = false;
      state.discoverFailed = false;
      state.discoverRepos = asList(data, 'repos');
      state.discoverTruncated = !!(data && data.truncated);
      applyDiscoverState();
    }).catch(function () {
      state.discoverLoading = false;
      state.discoverFailed = true;
      state.discoverRepos = [];
      applyDiscoverState();
    });
  }

  /* 編集中は一覧を出さない（既存の接続先のパスを直す操作なので手入力が正しい）。 */
  function setupRepoPicker(isNew) {
    state.selectedRepoPath = '';
    var ui = ensureRepoPicker();
    if (!ui) { return; }
    if (!isNew) {
      ui.box.hidden = true;
      setManualPath(true);
      return;
    }
    ui.filter.value = '';
    if (state.discoverRepos || state.discoverFailed) { applyDiscoverState(); return; }
    ui.box.hidden = false;
    ui.list.textContent = '';
    ui.status.hidden = false;
    ui.status.textContent = 'リポジトリを探しています…';
    setManualPath(false);
    loadDiscover();
  }

  /* 成功を知らせる。hl-error は失敗専用のバナーなので流用しない。 */
  var toastTimer = null;
  function showToast(text) {
    var host = document.getElementById('hl-toast');
    if (!host) {
      host = el('div', 'hl-toast');
      host.id = 'hl-toast';
      host.setAttribute('role', 'status');
      host.setAttribute('aria-live', 'polite');
      document.body.appendChild(host);
    }
    host.textContent = '';
    host.appendChild(el('span', 'hl-toast-text', text));
    var close = el('button', 'hl-toast-close', '×');
    close.type = 'button';
    close.setAttribute('aria-label', '閉じる');
    close.addEventListener('click', function () { host.hidden = true; });
    host.appendChild(close);
    host.hidden = false;
    if (toastTimer) { clearTimeout(toastTimer); }
    toastTimer = setTimeout(function () { host.hidden = true; }, 4000);
  }

  /* 選択肢に利用可否を出す。取得に失敗したらサーバ描画のまま残す（落とさない）。 */
  function loadAgentOptions() {
    var sel = $['hl-f-agent'];
    if (!sel) { return; }
    apiFetch('/agents').then(function (data) {
      var list = asList(data, 'agents');
      if (!list.length) { return; }
      var byName = {};
      list.forEach(function (a) { if (a && a.name) { byName[a.name] = a; } });
      Array.prototype.forEach.call(sel.options, function (opt) {
        var a = byName[opt.value];
        if (!a) { return; }
        var detail = String(a.detail || '');
        var mark = a.available ? (detail || '利用可') : (detail || '利用できません');
        opt.textContent = flattenParens((a.label || opt.value) + '（' + tailText(mark, 26) + '）');
        opt.disabled = !a.available;
        if (detail) { opt.title = detail; }
      });
    }).catch(function () { /* 現状のまま出す */ });
  }

  function submitConnectForm() {
    var name = $['hl-f-name'].value.trim();
    var path = $['hl-f-path'].value.trim();
    if (!name || !path) { showError('名前とリポジトリのパスは必須です。'); return; }
    // キー名は API（web/routes/healing.py）の受け口と 1 文字も違えられない。
    var payload = {
      name: name,
      repo_path: path,
      default_branch: $['hl-f-branch'].value.trim() || 'main',
      verify_command: $['hl-f-cmd'].value.trim(),
      remote: $['hl-f-remote'].value.trim() || 'origin',
      github_repo: $['hl-f-github'].value.trim(),
      domain: $['hl-f-domain'] ? $['hl-f-domain'].value.trim() : '',
      agent: $['hl-f-agent'].value,
      max_iterations: parseInt($['hl-f-max-iter'].value, 10) || 3,
      max_parallel_agents: parseInt($['hl-f-concurrency'].value, 10) || 3
    };
    clearError();
    var editingId = state.editingProjectId;
    var req = editingId
      ? apiFetch('/projects/' + editingId, { method: 'PATCH', body: JSON.stringify(payload) })
      : apiFetch('/projects', { method: 'POST', body: JSON.stringify(payload) });
    req.then(function (data) {
      hideConnectForm();
      var created = editingId ? null : asObj(data, 'project');
      var newId = (created && created.project_id) ? created.project_id : null;
      // 登録しただけで実行対象を勝手に差し替えない。一覧で目印を出し、選ぶのは利用者。
      state.highlightProjectId = editingId || newId || null;
      return loadProjects().then(function () {
        loadStats();
        showToast(editingId
          ? ('「' + name + '」の接続を更新しました。')
          : ('「' + name + '」を接続しました。実行するには一覧で「対象にする」を押してください。'));
        var row = $['hl-projects'] ? $['hl-projects'].querySelector('.hl-row-added') : null;
        if (row && row.scrollIntoView) { row.scrollIntoView({ block: 'nearest' }); }
      });
    }).catch(function (e) { showError((editingId ? '更新' : '接続') + 'に失敗しました: ' + e.message); });
  }

  function deleteProject(projectId) {
    clearError();
    apiFetch('/projects/' + projectId, { method: 'DELETE' }).then(function () {
      return loadProjects().then(function () {
        loadStats();
        if (state.selectedProjectId === projectId) {
          if (state.projects.length) {
            selectProject(state.projects[0].project_id);
          } else {
            state.selectedProjectId = null;
            clearRunView();
          }
        }
      });
    }).catch(function (e) { showError('接続の削除に失敗しました: ' + e.message); });
  }

  /* ---------------- 実行ビュー: 対象・接続確認 ---------------- */

  function updateProjectMeta() {
    var p = getProject(state.selectedProjectId);
    if (!p) { $['hl-project-meta'].textContent = ''; return; }
    var meta = $['hl-project-meta'];
    meta.textContent = '';
    var items = [];
    var branch = p.default_branch || p.branch || '';
    if (branch) {
      var item1 = el('span', 'hl-meta-item');
      item1.appendChild(el('span', 'hl-meta-key', 'ブランチ: '));
      item1.appendChild(el('span', 'hl-meta-val', branch));
      items.push(item1);
    }
    var cmd = p.verify_command || '';
    if (cmd) {
      var item2 = el('span', 'hl-meta-item');
      item2.appendChild(el('span', 'hl-meta-key', '検証: '));
      var val2 = el('span', 'hl-meta-val');
      setPathTail(val2, cmd, 42);
      item2.appendChild(val2);
      items.push(item2);
    }
    var agent = p.agent || '';
    if (agent) {
      var item3 = el('span', 'hl-meta-item');
      item3.appendChild(el('span', 'hl-meta-key', '実行者: '));
      item3.appendChild(el('span', 'hl-meta-val', agentDisplayName(agent)));
      items.push(item3);
    }
    var limits = '最大 ' + (p.max_iterations || 3) + ' 周・同時 ' + (p.max_parallel_agents || 3) + ' 本';
    var item4 = el('span', 'hl-meta-item');
    item4.appendChild(el('span', 'hl-meta-key', '上限: '));
    item4.appendChild(el('span', 'hl-meta-val', limits));
    items.push(item4);
    items.forEach(function (item) {
      meta.appendChild(item);
    });
  }

  function updateRunSub(run) {
    if (run) {
      $['hl-run-sub'].textContent = (run.project_name || '') + '・ブランチ ' + (run.branch || '');
      return;
    }
    var p = getProject(state.selectedProjectId);
    $['hl-run-sub'].textContent = p ? ((p.name || '') + '・ブランチ ' + (p.default_branch || p.branch || '')) : '';
  }

  function runCheck() {
    if (!state.selectedProjectId) { return; }
    clearError();
    clearCheckState();
    checkProject(state.selectedProjectId).then(function (result) {
      renderChecksList(result.list);
    }).catch(function (e) { showError('接続確認に失敗しました: ' + e.message); });
  }

  /* 接続確認の重大度。required の NG は実行そのものが成立しない。
     optional の NG は検証と修正のループは動き、PR を作るときだけ効く。
     severity を返さない古い API は安全側（required）として扱う。 */
  function checkSeverityOf(item) {
    return (item && item.severity === 'optional') ? 'optional' : 'required';
  }

  var checkUi = null;

  /* 判断の直前で見せるため、要約行は開始ボタンの直上に差し込む。
     テンプレート側に器が無いので JS で 1 度だけ作る。 */
  function ensureCheckSummary() {
    if (checkUi) { return checkUi; }
    var anchorBtn = $['hl-start'] || $['hl-check-btn'];
    var row = anchorBtn ? anchorBtn.parentNode : null;
    if (!row || !row.parentNode) { return null; }
    var box = el('div', 'hl-check-summary-box');
    box.hidden = true;
    var summary = el('button', 'hl-check-summary');
    summary.type = 'button';
    summary.addEventListener('click', function () {
      var ul = $['hl-checks'];
      if (ul && ul.scrollIntoView) { ul.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
    });
    var note = el('p', 'hl-check-blocked-note');
    note.hidden = true;
    box.appendChild(summary);
    box.appendChild(note);
    row.parentNode.insertBefore(box, row);
    checkUi = { box: box, summary: summary, note: note };
    return checkUi;
  }

  /* 接続確認をまだ実行していない状態（＝確認は任意）に戻す。 */
  function clearCheckState() {
    var ul = $['hl-checks'];
    if (ul) { ul.textContent = ''; ul.hidden = true; }
    if ($['hl-start']) { $['hl-start'].disabled = false; }
    if (!checkUi) { return; }
    checkUi.box.hidden = true;
    checkUi.box.classList.remove('is-blocking');
    checkUi.summary.textContent = '';
    checkUi.note.hidden = true;
    checkUi.note.textContent = '';
  }

  /* 必須の NG が 1 件でもあれば開始を止める。任意の NG だけなら止めない。 */
  function applyCheckState(list) {
    var blocking = 0;
    var optional = 0;
    (list || []).forEach(function (item) {
      if (item && item.ok === true) { return; }
      if (checkSeverityOf(item) === 'optional') { optional += 1; } else { blocking += 1; }
    });
    if ($['hl-start']) { $['hl-start'].disabled = blocking > 0; }
    if (blocking > 0) { setConfirmOpen($['hl-start-confirm'], false); }
    var ui = ensureCheckSummary();
    if (!ui) { return; }
    if (!blocking && !optional) {
      ui.box.hidden = true;
      ui.box.classList.remove('is-blocking');
      ui.note.hidden = true;
      return;
    }
    ui.box.hidden = false;
    if (blocking > 0) { ui.box.classList.add('is-blocking'); } else { ui.box.classList.remove('is-blocking'); }
    ui.summary.textContent = '確認: 実行できない項目 ' + blocking + ' 件 / PR 作成に必要な項目 ' + optional + ' 件';
    ui.summary.title = '確認結果へ移動します';
    ui.note.hidden = blocking === 0;
    ui.note.textContent = blocking > 0 ? '実行できない項目があるため開始できません。下の確認結果を直してください。' : '';
  }

  function renderChecksList(list) {
    var ul = $['hl-checks'];
    ul.textContent = '';
    ul.hidden = !list.length;
    list.forEach(function (item) {
      var ok = item.ok === true;
      var optional = !ok && checkSeverityOf(item) === 'optional';
      var rowClass = 'hl-check-row';
      if (!ok) { rowClass += optional ? ' hl-check-row-warn' : ' hl-check-row-blocking'; }
      var li = el('li', rowClass);
      var icon = ok ? '✓' : (optional ? '△' : '✕');
      var iconClass = ok ? 'is-ok' : (optional ? 'is-warn' : 'is-bad');
      li.appendChild(el('span', 'hl-check-icon ' + iconClass, icon));
      li.appendChild(el('span', 'hl-check-label', item.label || item.key || ''));
      var detail = item.detail || (ok ? '' : '確認できませんでした');
      if (!ok) {
        var lead = optional ? 'PR を作るときに必要' : '実行できません';
        li.appendChild(el('span', 'hl-check-tag ' + (optional ? 'is-warn' : 'is-bad'), lead));
      }
      li.appendChild(el('span', 'hl-check-detail', detail));
      li.title = detail;
      ul.appendChild(li);
    });
    applyCheckState(list);
  }

  /* ---- 他ファイルへ公開 ---- */
  HL.clearCheckState = clearCheckState;
  HL.closeAllConfirms = closeAllConfirms;
  HL.closeRowMenu = closeRowMenu;
  HL.closeRowMenuOnOutsideClick = closeRowMenuOnOutsideClick;
  HL.hideConnectForm = hideConnectForm;
  HL.loadAgentOptions = loadAgentOptions;
  HL.loadProjects = loadProjects;
  HL.openConfirm = openConfirm;
  HL.renderProjects = renderProjects;
  HL.runCheck = runCheck;
  HL.setAdminFlag = setAdminFlag;
  HL.setConfirmOpen = setConfirmOpen;
  HL.showConnectForm = showConnectForm;
  HL.submitConnectForm = submitConnectForm;
  HL.updateProjectMeta = updateProjectMeta;
  HL.updateRunSub = updateRunSub;
})(window.HealingApp = window.HealingApp || {});
