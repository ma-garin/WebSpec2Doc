'use strict';

(function () {
  var API_BASE = '/api/healing';
  var POLL_MS = 2000;

  // エージェント表示名の対応表
  var AGENT_DISPLAY_NAMES = {
    'claude': 'Claude Code',
    'codex': 'Codex',
    'openai': 'OpenAI',
    'ollama': 'Ollama',
    'dryrun': '動作確認用'
  };

  function agentDisplayName(agentId) {
    return AGENT_DISPLAY_NAMES[agentId] || agentId;
  }

  var STATUS_LABELS = {
    queued: '受付', preparing: '準備', verifying: '検証', analyzing: '欠陥の切り出し',
    fixing: '修正', reverifying: '再検証', awaiting_human: '人の判断待ち',
    succeeded: '完了', no_defects: '不具合なし', failed: '失敗', cancelled: '中止'
  };
  var TERMINAL_STATUSES = ['succeeded', 'no_defects', 'failed', 'cancelled'];
  // ポーリングを止めてよい状態。awaiting_human は「終わった」わけではないが、
  // 人が操作するまで中身は 1 文字も変わらない。ここで回し続けると、利用者が
  // まさに差分を読んでいる最中に 2 秒ごとに再描画され、開いた差分が閉じる。
  var POLL_STOP_STATUSES = TERMINAL_STATUSES.concat(['awaiting_human']);
  var SEVERITY_LABELS = { critical: '重大', high: '高', medium: '中', low: '低' };
  var PROPOSAL_STATUS_LABELS = { proposed: '未適用', applied: '済', failed: '失敗', skipped: '対象外', timeout: '時間切れ' };
  // 状態バッジは成功・注意・失敗・対象外で色を分ける（色そのものは CSS）。
  var PROPOSAL_STATUS_KIND = {
    applied: 'ok', proposed: 'warn', failed: 'err', timeout: 'err', skipped: 'mute'
  };
  var PROPOSAL_STATUS_TITLES = {
    applied: '作業ツリーに適用済み', proposed: '差分はあるが未適用', failed: '修正に失敗',
    skipped: '変更が不要で対象外', timeout: '制限時間を超えて中断'
  };
  var CHECK_DEFS = [
    { key: 'repository', label: 'リポジトリ' },
    { key: 'git', label: 'git' },
    { key: 'remote', label: 'リモート' },
    { key: 'github', label: 'GitHub' },
    { key: 'verify_command', label: '検証コマンド' }
  ];

  var state = {
    projects: [],
    //: project_id -> 接続確認の結果（true/false）。未確認なら未定義。
    checkResults: {},
    //: 直近に描画した run の JSON 文字列。同じなら描き直さない。
    lastRenderedRun: null,
    selectedProjectId: null,
    selectedRunId: null,
    currentRun: null,
    pollRunId: null,
    pollTimer: null,
    historyRuns: [],
    historyLimit: 20,
    editingProjectId: null,
    focusRunId: '',
    activeView: 'run',
    //: 許可ルート配下のリポジトリ一覧（GET /discover）。null は未取得。
    discoverRepos: null,
    discoverLoading: false,
    discoverFailed: false,
    discoverTruncated: false,
    //: 選択リストで選んだリポジトリのパス（見た目の選択状態にだけ使う）。
    selectedRepoPath: '',
    //: 登録直後の行に付ける目印。選択（実行対象）とは別物。
    highlightProjectId: null
  };

  var $ = {};

  function cacheDom() {
    var ids = [
      'hl-error', 'hl-nav-run', 'hl-nav-projects', 'hl-nav-history',
      'hl-view-run', 'hl-view-projects', 'hl-view-history',
      'hl-project-select', 'hl-project-meta', 'hl-instructions', 'hl-start',
      'hl-start-confirm', 'hl-start-yes', 'hl-start-no',
      'hl-check-btn', 'hl-checks',
      'hl-stat-projects', 'hl-stat-runs', 'hl-stat-fixed', 'hl-stat-pr',
      'hl-run-sub', 'hl-status',
      'hl-create-pr', 'hl-rerun', 'hl-approve', 'hl-merge', 'hl-reject', 'hl-cancel',
      'hl-merge-confirm', 'hl-merge-yes', 'hl-merge-no',
      'hl-reject-confirm', 'hl-reject-yes', 'hl-reject-no',
      'hl-cancel-confirm', 'hl-cancel-yes', 'hl-cancel-no',
      'hl-decision-note', 'hl-pr-info', 'hl-run-error',
      'hl-loop', 'hl-loop-empty', 'hl-log',
      'hl-unverified', 'hl-unverified-list',
      'hl-projects', 'hl-projects-empty',
      'hl-connect-form', 'hl-form-title',
      'hl-f-name', 'hl-f-path', 'hl-f-branch', 'hl-f-cmd', 'hl-f-remote',
      'hl-f-github', 'hl-f-agent', 'hl-f-max-iter', 'hl-f-concurrency',
      'hl-connect-submit', 'hl-connect-cancel',
      'hl-runs', 'hl-runs-empty', 'hl-runs-more'
    ];
    ids.forEach(function (id) { $[id] = document.getElementById(id); });
  }

  /* 非管理者では Jinja が操作ボタンを描画しないので要素が存在しない。
     無い要素への addEventListener で init() ごと落ちると閲覧もできなくなる。 */
  function on(id, type, handler) {
    if ($[id]) { $[id].addEventListener(type, handler); }
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  /* 末尾を残す省略。パスやコマンドは末尾に意味があるので先頭を落とす
     （…/scratchpad/demo-134145）。全文は title に入れてホバーで読ませる。 */
  function tailText(value, max) {
    var s = String(value == null ? '' : value);
    if (s.length <= max) { return s; }
    return '…' + s.slice(s.length - (max - 1));
  }

  function setTail(node, value, max) {
    var s = String(value == null ? '' : value);
    node.textContent = tailText(s, max);
    if (s) { node.title = s; }
    return node;
  }

  /* パスは末尾（リポジトリ名）が識別子。先頭だけを落とし、末尾は必ず残す。
     切るのは必ずセグメント境界（/）。個人名の途中で切れると読めない断片になる。
     入る限り末尾から段を増やす（…/dev/active/webspec2doc）。 */
  function setPathTail(node, value, max) {
    var s = String(value == null ? '' : value);
    var text = s;
    if (s.length > max) {
      var parts = s.split('/').filter(function (x) { return x !== ''; });
      text = parts.length ? ('…/' + parts[parts.length - 1]) : s;
      for (var i = parts.length - 2; i >= 0; i -= 1) {
        var wider = '…/' + parts.slice(i).join('/');
        if (wider.length > max) { break; }
        text = wider;
      }
    }
    node.textContent = text;
    if (s) { node.title = s; }
    return node;
  }

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

  function openConfirm(node) {
    if (!node) { return; }
    closeAllConfirms(node);
    setConfirmOpen(node, true);
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

  function selectedProjectName() {
    var id = state.selectedProjectId;
    for (var i = 0; i < state.projects.length; i++) {
      if (state.projects[i].project_id === id) {
        return state.projects[i].name || state.projects[i].repo_path || String(id || '');
      }
    }
    return '';
  }

  /* 括弧の入れ子をほどく。「A（B（C） D）」→「A（B C D）」。 */
  function flattenParens(text) {
    var s = String(text == null ? '' : text);
    var out = '';
    var depth = 0;
    for (var i = 0; i < s.length; i += 1) {
      var ch = s.charAt(i);
      if (ch === '（' || ch === '(') {
        depth += 1;
        out += depth === 1 ? '（' : ' ';
      } else if (ch === '）' || ch === ')') {
        if (depth > 0) { out += depth === 1 ? '）' : ' '; depth -= 1; } else { out += ch; }
      } else {
        out += ch;
      }
    }
    return out.replace(/[ 　]{2,}/g, ' ').replace(/（ +/g, '（').replace(/ +）/g, '）').trim();
  }

  // エラーは「何が起きたか」だけでは足りない。次にとる行動を必ず 1 行添える。
  var NEXT_ACTION_RULES = [
    { re: /適用|提案|エージェント/, text: 'エージェントの設定を見直してから再検証してください。' },
    { re: /検証コマンド|コマンド|テスト/, text: '接続先の検証コマンドを見直してから再実行してください。' },
    { re: /GitHub|リモート|権限|認証|token/i, text: 'GitHub の接続設定を確認してから再実行してください。' },
    { re: /中止|キャンセル/, text: '原因を確認したうえで、もう一度実行してください。' }
  ];

  function nextActionFor(text) {
    var s = String(text == null ? '' : text);
    for (var i = 0; i < NEXT_ACTION_RULES.length; i += 1) {
      if (NEXT_ACTION_RULES[i].re.test(s)) { return NEXT_ACTION_RULES[i].text; }
    }
    return '実行ログを確認し、接続先の設定を見直してから再実行してください。';
  }

  /* 利用者向けエラーメッセージに言い換える。内部用語・技術用語を避ける。 */
  function humanizeError(text) {
    var s = String(text == null ? '' : text);
    /* 「構造化」「シリアライズ」などの内部用語を排除 */
    if (/構造化|シリアライズ|パース/.test(s)) {
      /* 内部用語が含まれている場合、その文をそのまま出さず、
         実行ログ確認を勧める（正確な原因はログにある）。 */
      return '検証は失敗しましたが、原因を特定できませんでした';
    }
    /* 「No such file or directory」の場合、コマンドが見つからないと言い換える */
    var m = s.match(/No such file or directory:\s*['"](.*?)['"]/);
    if (m) {
      return '検証コマンドが見つかりません: ' + m[1];
    }
    if (/No such file or directory/.test(s)) {
      return '検証コマンドが見つかりません';
    }
    return s;
  }

  function showError(message) {
    $['hl-error'].textContent = message;
    $['hl-error'].hidden = false;
  }
  function clearError() {
    $['hl-error'].hidden = true;
    $['hl-error'].textContent = '';
  }

  function apiFetch(path, opts) {
    opts = opts || {};
    var headers = { 'X-Requested-With': 'XMLHttpRequest' };
    if (opts.body) { headers['Content-Type'] = 'application/json'; }
    var fetchOpts = { credentials: 'same-origin', method: opts.method || 'GET', headers: headers };
    if (opts.body) { fetchOpts.body = opts.body; }
    return fetch(API_BASE + path, fetchOpts).then(function (res) {
      return res.text().then(function (text) {
        var data = null;
        if (text) { try { data = JSON.parse(text); } catch (e) { data = null; } }
        if (!res.ok) {
          if (res.status === 403) {
            throw new Error('この操作には管理者権限が必要です。');
          }
          var msg = (data && (data.error || data.message)) || ('通信に失敗しました（コード ' + res.status + '）');
          throw new Error(msg);
        }
        return data;
      });
    });
  }

  function asList(data, key) {
    if (Array.isArray(data)) { return data; }
    if (data && Array.isArray(data[key])) { return data[key]; }
    return [];
  }
  function asObj(data, key) {
    if (data && data[key] && typeof data[key] === 'object') { return data[key]; }
    return data || {};
  }
  function fmtTime(s) {
    if (!s) { return ''; }
    return String(s).replace('T', ' ').slice(0, 19);
  }

  function parseTs(s) {
    if (!s) { return null; }
    var d = new Date(String(s));
    if (isNaN(d.getTime())) { d = new Date(String(s).replace(' ', 'T')); }
    return isNaN(d.getTime()) ? null : d;
  }

  /* 24 時間以内は相対表記。絶対時刻は呼び出し側が title に残す。 */
  function fmtRelTime(s) {
    var d = parseTs(s);
    if (!d) { return fmtTime(s); }
    var diff = Date.now() - d.getTime();
    if (diff < 0 || diff >= 86400000) { return fmtTime(s); }
    var min = Math.floor(diff / 60000);
    if (min < 1) { return 'たった今'; }
    if (min < 60) { return min + ' 分前'; }
    return Math.floor(min / 60) + ' 時間前';
  }

  /* 所要時間。終了していなければ null（「実行中」と「0 秒」を混ぜない）。 */
  function fmtDuration(startedAt, finishedAt) {
    var a = parseTs(startedAt);
    var b = parseTs(finishedAt);
    if (!a || !b) { return null; }
    var sec = Math.round((b.getTime() - a.getTime()) / 1000);
    if (sec < 0) { return null; }
    if (sec < 60) { return sec + ' 秒'; }
    var m = Math.floor(sec / 60);
    if (m < 60) { return m + ' 分 ' + (sec % 60) + ' 秒'; }
    return Math.floor(m / 60) + ' 時間 ' + (m % 60) + ' 分';
  }

  function statusBadgeClass(status) {
    if (status === 'succeeded' || status === 'no_defects') { return 'is-done'; }
    if (status === 'failed') { return 'is-failed'; }
    if (status === 'cancelled') { return 'is-cancelled'; }
    if (status === 'awaiting_human') { return 'is-waiting'; }
    return 'is-running';
  }

  function getProject(id) {
    var found = null;
    state.projects.forEach(function (p) { if (p.project_id === id) { found = p; } });
    return found;
  }

  /* ---------------- ビュー切り替え ---------------- */

  function switchView(view) {
    state.activeView = view;
    ['run', 'projects', 'history'].forEach(function (v) {
      $['hl-view-' + v].hidden = v !== view;
    });
    // サイドバーは共通部品（報告書 / 設定）に置き換わり、ビュー切替のナビは
    // この画面には無い。要素が無くても落とさない。
    ['run', 'projects', 'history'].forEach(function (v) {
      var nav = $['hl-nav-' + v];
      if (nav && nav.classList) { nav.classList.toggle('active', view === v); }
    });
  }

  /* ---------------- 統計 ---------------- */

  /* data-empty-hint は「0 のときだけ」意味を持つ補助テキスト。値が入ったら必ず消す。 */
  function setStatHint(id, text, title) {
    var num = $[id];
    var card = num && num.closest ? num.closest('.stat-card') : null;
    if (!card) { return; }
    var old = card.querySelector('.hl-stat-hint');
    if (old && old.parentNode) { old.parentNode.removeChild(old); }
    if (!text) { return; }
    /* 補助文はカード幅を超えると 2 行になって数字を押し下げる。本文は短く保ち、
       省いた説明は title に入れる（読みたい人はホバーで読める）。 */
    var hint = el('div', 'hl-stat-hint', text);
    if (title) { hint.title = title; }
    card.appendChild(hint);
  }

  function setStat(id, value, isEmpty) {
    var num = $[id];
    if (!num) { return; }
    num.textContent = String(value);
    var card = num.closest ? num.closest('.stat-card') : null;
    if (!card) { return; }
    setStatHint(id, isEmpty ? card.getAttribute('data-empty-hint') : '');
  }

  /* 「直した不具合」カードの内訳。再検証が緑になった実行だけを数え、
     そうでない実行の修正件数は別に持って補助テキストへ出す。 */
  var statFixedValue = 0;
  var statFixedUnverified = 0;

  /* 「直した不具合 N」は件数だけで質を示さない。要確認が残っていること、
     再検証が通らず数に入れなかった修正があることを同じカードに出す。 */
  function applyFixedHint() {
    var parts = [];
    var high = riskCounts().high;
    if (statFixedValue > 0 && high > 0) { parts.push('うち要確認 ' + high + ' 件'); }
    var title = '';
    if (statFixedUnverified > 0) {
      title = '再検証が通っていない修正 ' + statFixedUnverified + ' 件は数えていません';
      parts.push(parts.length ? ('未計上 ' + statFixedUnverified + ' 件')
        : ('未計上 ' + statFixedUnverified + ' 件（再検証が未通過）'));
    }
    if (parts.length) { setStatHint('hl-stat-fixed', parts.join(' / '), title); }
  }

  /* カードの見出しは HTML 側にあるが、数える対象を変えたら見出しも一緒に変える。
     「PR の数」と「人が待たされている実行の数」は別物で、後者が利用者の関心。 */
  function setStatLabel(id, text) {
    var num = $[id];
    var card = num && num.closest ? num.closest('.stat-card') : null;
    var label = card ? card.querySelector('.stat-card-label') : null;
    if (label) { label.textContent = text; }
  }

  /* 補助文は「どの範囲を数えたか」の宣言。数える範囲を変えたら必ず一緒に変える。 */
  function setStatSub(id, text) {
    var num = $[id];
    var card = num && num.closest ? num.closest('.stat-card') : null;
    var sub = card ? card.querySelector('.stat-card-sub') : null;
    if (sub) { sub.textContent = text; }
  }

  function loadStats() {
    setStat('hl-stat-projects', state.projects.length, state.projects.length === 0);
    /* 実行・直した不具合・判断待ちは「選択中の接続先」で絞る。全体の数を出しながら
       「この接続先の実行」と書くとラベルが嘘になる。未選択のときは全体を出し、
       補助文も「全体の実行」に変える（ラベルと中身のどちらかを必ず合わせる）。 */
    var pid = state.selectedProjectId || '';
    setStatSub('hl-stat-runs', pid ? 'この接続先の実行' : '全体の実行');
    var statUrl = '/runs?limit=200' + (pid ? '&project_id=' + encodeURIComponent(pid) : '');
    apiFetch(statUrl).then(function (data) {
      // 集計の途中で接続先が切り替わったら、古い範囲の数字は書かない。
      if ((state.selectedProjectId || '') !== pid) { return; }
      var runs = asList(data, 'runs');
      // 「直した」は再検証が緑になった実行（status: succeeded）だけを数える。
      // 修正を当てただけの実行を足すと、テストが壊れたままでも直ったと読めてしまう。
      var fixed = 0;
      // 判断待ちは PR の有無ではなく実行の状態で数える。PR が無くても人は待っている。
      var awaiting = 0;
      // 実行回数だけを出すと、成功しなかった回が画面から消える。
      var lost = 0;
      statFixedUnverified = 0;
      runs.forEach(function (r) {
        var applied = r.fixed_count || 0;
        if (applied > 0) {
          if (r.status === 'succeeded') { fixed += applied; }
          else { statFixedUnverified += applied; }
        }
        if (r.status === 'awaiting_human') { awaiting += 1; }
        if (r.status === 'failed' || r.status === 'cancelled') { lost += 1; }
      });
      setStat('hl-stat-runs', runs.length, runs.length === 0);
      if (lost > 0) { setStatHint('hl-stat-runs', 'うち失敗 ' + lost + ' 件'); }
      statFixedValue = fixed;
      setStat('hl-stat-fixed', fixed, fixed === 0);
      setStatLabel('hl-stat-pr', '判断待ちの実行');
      setStat('hl-stat-pr', awaiting, awaiting === 0);
      applyFixedHint();
    }).catch(function () {
      if ((state.selectedProjectId || '') !== pid) { return; }
      statFixedValue = 0;
      statFixedUnverified = 0;
      setStat('hl-stat-runs', '-', false);
      setStat('hl-stat-fixed', '-', false);
      setStatLabel('hl-stat-pr', '判断待ちの実行');
      setStat('hl-stat-pr', '-', false);
      applyFixedHint();
    });
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

      // 行内は 2 つまで。4 つ並べると 1280px で押し出されて押せなくなる。
      var tdActions = el('td', 'hl-row-actions');
      var useBtn = el('button', isSelected ? 'btn-primary' : 'btn-outline-sm', isSelected ? '対象' : '対象にする');
      useBtn.type = 'button';
      useBtn.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
      if (isSelected) {
        // 既に対象の行で押せるように見せない。押しても何も起きない操作は出さない。
        useBtn.disabled = true;
      } else {
        useBtn.addEventListener('click', function () { selectProject(p.project_id); switchView('run'); });
      }

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
  }
  function hideConnectForm() {
    $['hl-connect-form'].hidden = true;
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

  /* ---------------- 実行の選択・切り替え ---------------- */

  function hideAllConfirms() {
    closeAllConfirms(null);
  }

  function clearRunView() {
    state.selectedRunId = null;
    state.currentRun = null;
    state.lastRenderedRun = null;
    stopPolling();
    hideAllConfirms();
    // 接続先を切り替えたら前の接続確認の結果は無効。表示も開始ボタンの無効化も戻す。
    clearCheckState();
    updateProjectMeta();
    updateRunSub(null);
    renderLoop(null);
    renderLogLines([]);
    renderStatusBadge(null);
    renderPrInfo(null);
    renderUnverified(null);
    updateActionButtons(null);
  }

  function selectProject(id, opts) {
    opts = opts || {};
    state.highlightProjectId = null;
    state.selectedProjectId = id || null;
    if ($['hl-project-select']) { $['hl-project-select'].value = id || ''; }
    // 統計は選択中の接続先で絞るので、切り替えのたびに数え直す。
    loadStats();
    // 選択中の行の見た目を入れ替えるため、接続先の表を描き直す。
    if ($['hl-projects']) { renderProjects(); }
    clearRunView();
    if (!id) { return; }
    if (opts.openRunId) { openRun(opts.openRunId); return; }
    apiFetch('/runs?project_id=' + encodeURIComponent(id) + '&limit=1').then(function (data) {
      var runs = asList(data, 'runs');
      if (runs.length) { openRun(runs[0].run_id); }
    }).catch(function (e) { showError('実行状況の取得に失敗しました: ' + e.message); });
  }

  function startRun() {
    if (!state.selectedProjectId) { return; }
    clearError();
    var payload = {
      project_id: state.selectedProjectId,
      extra_instructions: ($['hl-instructions'] ? $['hl-instructions'].value.trim() : '')
    };
    if ($['hl-start']) { $['hl-start'].disabled = true; }
    apiFetch('/runs', { method: 'POST', body: JSON.stringify(payload) }).then(function (data) {
      if ($['hl-start']) { $['hl-start'].disabled = false; }
      var run = asObj(data, 'run');
      if (run && run.run_id) {
        openRun(run.run_id);
        loadStats();
        loadHistory(state.historyLimit || 20);
      }
    }).catch(function (e) {
      if ($['hl-start']) { $['hl-start'].disabled = false; }
      showError('ヒーリングの開始に失敗しました: ' + e.message);
    });
  }

  function openRun(runId) {
    state.selectedRunId = runId;
    hideAllConfirms();
    stopPolling();
    // 別の実行を開くときは前回の署名を捨てる（同じ内容でも描き直す必要がある）。
    state.lastRenderedRun = null;
    fetchAndRenderRun(runId);
  }

  function fetchAndRenderRun(runId) {
    return apiFetch('/runs/' + encodeURIComponent(runId)).then(function (data) {
      var run = asObj(data, 'run');
      state.currentRun = run;
      // 中身が 1 文字も変わっていないなら描き直さない。描き直すと、開いてある
      // 差分・スクロール位置・選択がその都度失われる（差分は毎回閉じる）。
      var signature = JSON.stringify(run);
      if (signature !== state.lastRenderedRun) {
        state.lastRenderedRun = signature;
        renderRun(run);
        loadStats();
      }
      if (POLL_STOP_STATUSES.indexOf(run.status) === -1) {
        startPolling(runId);
      } else {
        stopPolling();
      }
    }).catch(function (e) { showError('実行状況を取得できませんでした: ' + e.message); });
  }

  function startPolling(runId) {
    state.pollRunId = runId;
    if (document.hidden) { return; }
    clearPollTimer();
    state.pollTimer = setInterval(function () { fetchAndRenderRun(runId); }, POLL_MS);
  }
  function clearPollTimer() {
    if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
  }
  function stopPolling() {
    state.pollRunId = null;
    clearPollTimer();
  }
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
      clearPollTimer();
    } else if (state.pollRunId) {
      var id = state.pollRunId;
      fetchAndRenderRun(id);
      state.pollTimer = setInterval(function () { fetchAndRenderRun(id); }, POLL_MS);
    }
  });

  /* ---------------- 実行の描画 ---------------- */

  function renderRun(run) {
    state.riskCounts = collectRiskCounts(run);
    renderStatusBadge(run);
    updateRunSub(run);
    renderLoop(run);
    renderLogLines(run.log || [], run.error || '');
    renderPrInfo(run);
    renderUnverified(run);
    updateActionButtons(run);
    renderRiskSummary(run);
    applyFixedHint();
  }

  /* ---------------- リスク要約（判断の直前に出す） ----------------
     危険な兆候が画面のはるか下にしか無いと、判断者はスクロールせずに PR を出す。
     判断ボタンと同じ視野に 1 行で出し、押せば該当箇所まで送る。 */

  function collectRiskCounts(run) {
    var counts = { total: 0, high: 0, medium: 0, low: 0 };
    var iterations = (run && run.iterations) ? run.iterations : [];
    iterations.forEach(function (iter) {
      (iter.proposals || []).forEach(function (p) {
        (p.risks || []).forEach(function (r) {
          // severity は大文字で来ることがある。取りこぼすと「重大 0 件」と誤って出る。
          var sev = String(r.severity || 'low').toLowerCase();
          counts.total += 1;
          if (sev === 'critical' || sev === 'high') { counts.high += 1; }
          else if (sev === 'medium') { counts.medium += 1; }
          else { counts.low += 1; }
        });
      });
    });
    return counts;
  }

  function riskCounts() {
    return state.riskCounts || { total: 0, high: 0, medium: 0, low: 0 };
  }

  // 該当箇所は畳まれた詳細行の中にある。開いてから送らないと空振りする。
  function revealFirstRisk() {
    var loop = $['hl-loop'];
    if (!loop) { return; }
    var target = loop.querySelector('.hl-risk-item.is-critical')
      || loop.querySelector('.hl-risk-item.is-high')
      || loop.querySelector('.hl-risk');
    if (!target) { return; }
    var row = target.closest ? target.closest('.hl-detail-row') : null;
    if (row && row.hidden) {
      row.hidden = false;
      var headRow = row.previousElementSibling;
      var toggle = headRow ? headRow.querySelector('[data-testid="hl-toggle-detail"]') : null;
      if (toggle) {
        toggle.setAttribute('aria-expanded', 'true');
        toggle.textContent = '詳細を閉じる';
      }
    }
    target.scrollIntoView({ block: 'center' });
  }

  function riskSummaryText(counts) {
    if (counts.total === 0) {
      return '機械的に検出できる兆候はありませんでした。';
    }
    var text = '⚠ 確認が必要な点が ' + counts.total + ' 件';
    if (counts.high > 0) { text += '（重大 ' + counts.high + ' 件）'; }
    return text + 'あります。差分を確認してください。';
  }

  function renderRiskSummary(run) {
    var badge = $['hl-status'];
    var head = badge && badge.closest ? badge.closest('.dashboard-section-head') : null;
    if (!head || !head.parentNode) { return; }
    var old = head.parentNode.querySelector('.hl-risk-summary');
    if (old && old.parentNode) { old.parentNode.removeChild(old); }
    if (!run) { state.riskCounts = null; return; }
    var counts = riskCounts();
    var level = counts.high > 0 ? 'high' : (counts.medium > 0 ? 'medium' : 'none');
    var btn = el('button', 'hl-risk-summary hl-risk-summary-' + level, riskSummaryText(counts));
    btn.type = 'button';
    btn.setAttribute('data-testid', 'hl-risk-summary');
    btn.addEventListener('click', revealFirstRisk);
    /* 判断ボタン群の直下・「判断のメモ」より前に置く。メモは label と input が
       1 組で意味を持つので、その間には絶対に割り込ませない（行ごと前に入れる）。 */
    var noteRow = head.parentNode.querySelector('.hl-decision-note-row');
    var anchor = (noteRow && noteRow.parentNode === head.parentNode) ? noteRow : head.nextSibling;
    head.parentNode.insertBefore(btn, anchor);
  }

  /* 実行が 1 件も選ばれていないのに「未選択」バッジと対象名を出すと、
     直下の空状態（まだ実行がありません）と矛盾する。見出しごと隠す。 */
  /* 実行が 1 件も選ばれていないと、空の黒い箱だけが 140px 居座る。見出しごと隠す。
     実行を選んだ／開始した時点で表示に戻し、実行中・実行後は常時表示のまま（折りたたまない）。 */
  function setLogSectionVisible(visible) {
    var logEl = $['hl-log'];
    var card = logEl && logEl.closest ? logEl.closest('.hl-log-card') : null;
    if (!card) { return; }
    card.hidden = !visible;
    // .card 側の display 指定に hidden が負けることがあるため、表示も明示で落とす。
    card.style.display = visible ? '' : 'none';
    var head = card.previousElementSibling;
    if (head && head.classList && head.classList.contains('dashboard-section-head')) {
      head.hidden = !visible;
      head.style.display = visible ? '' : 'none';
    }
  }

  function setRunSectionVisible(visible) {
    var badge = $['hl-status'];
    var head = badge && badge.closest ? badge.closest('.dashboard-section-head') : null;
    if (head) { head.hidden = !visible; }
    var noteRow = document.querySelector('.hl-decision-note-row');
    if (noteRow) { noteRow.hidden = !visible; }
    setLogSectionVisible(visible);
  }

  function renderStatusBadge(run) {
    var badge = $['hl-status'];
    setRunSectionVisible(!!run);
    badge.className = 'hl-badge';
    if (!run) {
      badge.textContent = '未選択';
      renderRunError(null);
      return;
    }
    badge.classList.add(statusBadgeClass(run.status));
    /* 高リスクが 1 件でもあるなら、状態が何であれ危険でない実行と同じ見た目にしない。
       状態で絞ると「人の判断待ち（上限到達）」のように status が別名の実行で付かない。 */
    if (riskCounts().high > 0) {
      badge.classList.add('hl-badge-attention');
    }
    var label = STATUS_LABELS[run.status] || run.status || '';
    var step = run.step_label || '';
    // step_label は状態名で始まることが多い（status=fixing / step_label="修正（1周目・1件）"）。
    // そのまま連結すると二重になるため、細かい方が状態名を含むならそちらだけを出す。
    if (step && step.indexOf(label) === 0) {
      badge.textContent = step;
    } else {
      badge.textContent = label + (step ? '（' + step + '）' : '');
    }
    renderRunError(run);
  }

  // エラー文は括弧の入れ子をほどき、内部用語を言い換え、次にとる行動を 1 行添える。
  // box を作り直すので重複は起きない。「次にすること」は消さない——
  // 何が起きたかだけ伝えて、どうすればよいかを伝えないのは不親切（2026-09-05）。
  function renderRunError(run) {
    var box = $['hl-run-error'];
    box.textContent = '';
    var raw = run && run.error ? String(run.error) : '';
    if (!raw) { box.hidden = true; return; }
    box.hidden = false;
    var flat = flattenParens(raw);
    var msg = el('div', 'hl-run-error-msg');
    msg.textContent = humanizeError(flat);
    box.appendChild(msg);
    var next = nextActionFor(flat);
    if (next) {
      box.appendChild(el('div', 'hl-run-error-next', '次にすること: ' + next));
    }
  }

  // 押せない操作は disabled で並べず、表示から外す（選べないものを見せない）。
  function actionAvailability(run) {
    var map = {
      'hl-create-pr': false, 'hl-rerun': false, 'hl-approve': false,
      'hl-merge': false, 'hl-reject': false, 'hl-cancel': false
    };
    if (!run) { return map; }
    var hasPr = !!(run.pull_request && run.pull_request.number);
    var isTerminal = TERMINAL_STATUSES.indexOf(run.status) !== -1;
    var isAwaiting = run.status === 'awaiting_human';
    if (!isTerminal && !isAwaiting) {
      map['hl-cancel'] = true;
      return map;
    }
    map['hl-rerun'] = true;
    map['hl-create-pr'] = !hasPr;
    map['hl-merge'] = hasPr;
    if (isAwaiting) {
      map['hl-approve'] = true;
      map['hl-reject'] = true;
    }
    return map;
  }

  /* 判断ボタンが全部同じ見た目だと、何を選べばよいかが画面から読み取れない。
     並びは「承認 / PR を作成 / 再検証 | 却下」。破壊的な却下だけを間隔で離す。 */
  var TOOLBAR_ORDER = ['hl-approve', 'hl-create-pr', 'hl-rerun', 'hl-merge'];
  var toolbarLaidOut = false;

  function setBtnWeight(btn, primary) {
    if (!btn) { return; }
    btn.classList.remove('btn-primary');
    btn.classList.remove('btn-outline-sm');
    btn.classList.add(primary ? 'btn-primary' : 'btn-outline-sm');
  }

  /* 並べ替えは 1 度だけ。ポーリングのたびに DOM を動かすとフォーカスが飛ぶ。 */
  function layoutToolbar() {
    if (toolbarLaidOut) { return; }
    var reject = $['hl-reject'];
    var bar = reject && reject.parentNode ? reject.parentNode : null;
    if (!bar) { toolbarLaidOut = true; return; }
    TOOLBAR_ORDER.forEach(function (id) { if ($[id]) { bar.appendChild($[id]); } });
    var spacer = bar.querySelector('.hl-toolbar-spacer') || el('span', 'hl-toolbar-spacer');
    bar.appendChild(spacer);
    bar.appendChild(reject);
    if ($['hl-cancel']) { bar.appendChild($['hl-cancel']); }
    toolbarLaidOut = true;
  }

  function updateActionButtons(run) {
    var map = actionAvailability(run);
    Object.keys(map).forEach(function (id) {
      var btn = $[id];
      if (!btn) { return; }
      btn.disabled = false;
      btn.hidden = !map[id];
    });
    layoutToolbar();

    // 高リスクが残るなら「承認」を塗って誘導しない。押すこと自体は妨げない（判断は人がする）。
    var risky = riskCounts().high > 0;
    setBtnWeight($['hl-approve'], !risky);
    // PR 作成・再検証は主動線ではない。常に輪郭のままにする。
    setBtnWeight($['hl-create-pr'], false);
    setBtnWeight($['hl-rerun'], false);
    // 却下は取り消せない。塗らずに文字色だけで破壊的だと示す。
    if ($['hl-reject']) {
      setBtnWeight($['hl-reject'], false);
      $['hl-reject'].classList.add('hl-btn-danger');
    }

    if (!$['hl-cancel'] || $['hl-cancel'].hidden) { setConfirmOpen($['hl-cancel-confirm'], false); }
    if (!$['hl-merge'] || $['hl-merge'].hidden) { setConfirmOpen($['hl-merge-confirm'], false); }
    if (!$['hl-reject'] || $['hl-reject'].hidden) { setConfirmOpen($['hl-reject-confirm'], false); }
  }

  /* ---------------- ループ表示 ---------------- */

  function allProposalsFailed(proposals) {
    var list = proposals || [];
    if (!list.length) { return false; }
    return list.every(function (p) { return p.status === 'failed' || p.status === 'timeout'; });
  }

  // 再検証は「走ったか」と「通ったか」が別。error だけで見ると、
  // 失敗したままの再検証・打ち切られた実行まで緑（完了）になる。
  function verifyFailed(v) {
    if (!v) { return false; }
    if (v.ok === false) { return true; }
    return typeof v.failed === 'number' && v.failed > 0;
  }

  /* 「走らなかった」を「落ちた」と描かない。上限到達で再検証していない実行まで
     赤（失敗）にすると、直っていないのか実行していないのかが判別できなくなる。 */
  function verifyRan(v) {
    return !!v && !v.error;
  }

  // 済み / 実行中 / 未実行 / 失敗 の 4 状態を返す。同じ色で並べると
  // 「終わったもの」と「これから」の区別が付かない。
  function stepStates(iter, isActive) {
    function next(prev, value, failed) {
      if (prev !== 'done') { return 'idle'; }
      if (!value) { return isActive ? 'active' : 'idle'; }
      return failed ? 'failed' : 'done';
    }
    var s1;
    if (!iter.verify_before) { s1 = isActive ? 'active' : 'idle'; }
    else { s1 = iter.verify_before.error ? 'failed' : 'done'; }
    var s2 = next(s1, iter.defects, false);
    var s3 = next(s2, iter.proposals, allProposalsFailed(iter.proposals));
    var s4 = next(s3, verifyRan(iter.verify_after) ? iter.verify_after : null, verifyFailed(iter.verify_after));
    return [s1, s2, s3, s4];
  }

  function renderStepper(states) {
    var labels = ['検証', '欠陥', '修正', '再検証'];
    var wrap = el('div', 'hl-stepper');
    states.forEach(function (st, i) {
      var legacy = st === 'done' ? ' is-done' : (st === 'active' ? ' is-current' : '');
      var cls = 'hl-step hl-step-' + st + legacy;
      var step = el('div', cls);
      step.appendChild(el('span', 'hl-step-dot'));
      step.appendChild(el('span', null, labels[i]));
      wrap.appendChild(step);
    });
    return wrap;
  }

  function renderVerifyResult(v) {
    var wrap = el('div', 'hl-verify-result');
    if (!v) { wrap.appendChild(el('span', null, '未実行')); return wrap; }
    // 検証そのものが動かなかった場合、件数だけを出すと「不具合が無かった」と読めてしまう。
    // 理由を最初に、目立つ形で出す。
    if (v.error) {
      wrap.appendChild(el('b', 'hl-verify-error', '検証を実行できませんでした'));
      wrap.appendChild(el('span', 'hl-verify-error-detail', v.error));
      if (v.command) { wrap.title = v.command; }
      return wrap;
    }
    var summary = '失敗 ' + (v.failed != null ? v.failed : '?') + ' / 全 ' + (v.total != null ? v.total : '?');
    if (typeof v.duration_sec === 'number') { summary += '（' + v.duration_sec.toFixed(1) + ' 秒）'; }
    wrap.appendChild(el('b', null, summary));
    // 検証コマンドはメタ情報に既に出ている。同じ値を 2 箇所に出さず title に残す。
    if (v.command) { wrap.title = v.command; }
    return wrap;
  }

  /* pytest の終了コードのうち意味が確定しているものだけを 1 行にする。
     知らないコードに勝手な意味を付けると、事実でない説明が画面に出る。 */
  var VERIFY_EXIT_NOTES = {
    2: 'テストを収集できませんでした（終了コード 2）。テストの読み込み自体が失敗しています。',
    5: '実行できるテストが 1 件もありませんでした（終了コード 5）。'
  };

  /* 収集できたテストの件数が前後で変われば、それ自体が異常の兆候。
     数字を並べるだけでは見落とされるので、文で出す。 */
  function totalShiftNote(before, after) {
    if (!before || !after) { return ''; }
    if (typeof before.total !== 'number' || typeof after.total !== 'number') { return ''; }
    if (before.total === after.total) { return ''; }
    var head = '収集できたテストが ' + before.total + ' 件 → ' + after.total + ' 件に';
    if (after.total < before.total) {
      return head + '減っています。テストが壊れている可能性があります。';
    }
    return head + '増えています。検証の対象が変わっている可能性があります。';
  }

  /* 再検証は「直ったのか」を利用者が知る唯一の場所。未実行・失敗・件数の変化を
     すべてここに出す。出さないと、修正を当てただけで直ったと読まれる。 */
  function renderReverifyResult(iter) {
    var wrap = el('div', 'hl-verify-after');
    var v = iter.verify_after;
    if (!v) {
      wrap.appendChild(el('div', 'hl-verify-result hl-muted', '再検証: 未実行'));
      return wrap;
    }
    if (v.error) {
      wrap.appendChild(renderVerifyResult(v));
      return wrap;
    }
    var failed = typeof v.failed === 'number' ? v.failed : null;
    var summary = '再検証: 失敗 ' + (failed != null ? failed : '?')
      + ' / 全 ' + (v.total != null ? v.total : '?');
    if (typeof v.duration_sec === 'number') { summary += '（' + v.duration_sec.toFixed(1) + ' 秒）'; }
    var passed = failed === 0 && v.ok !== false;
    var line = el('div', 'hl-verify-result');
    var badge = el('b', passed ? 'hl-verify-ok hl-badge-ok' : 'hl-verify-bad hl-badge-err', summary);
    if (v.command) { badge.title = v.command; }
    line.appendChild(badge);
    wrap.appendChild(line);
    var shift = totalShiftNote(iter.verify_before, v);
    if (shift) { wrap.appendChild(el('div', 'hl-verify-warn hl-note', shift)); }
    var note = VERIFY_EXIT_NOTES[v.exit_code];
    if (typeof note === 'string') { wrap.appendChild(el('div', 'hl-verify-note hl-muted', note)); }
    return wrap;
  }

  // 該当箇所の根拠に付く理由コードの和訳。API が知らないコードを返しても
  // そのまま出す（空欄にすると「根拠が無い」と読めてしまう）。
  var REASON_LABELS = {
    traceback: '実行時トレース',
    'import': 'import 関係',
    'recent-change': '直近の変更',
    'test-name': 'テスト名'
  };
  var SEVERITY_RANK = { critical: 0, high: 1, medium: 2, low: 3 };

  function severityRank(sev) {
    var r = SEVERITY_RANK[sev];
    return r === undefined ? 9 : r;
  }

  /* 該当箇所の根拠。locations は古い実行履歴には存在しないので undefined 前提で守る。 */
  function renderEvidence(locations) {
    var wrap = el('div', 'hl-evidence');
    wrap.appendChild(el('div', 'hl-evidence-title', '該当箇所の根拠'));
    var list = (locations || []).slice();
    if (list.length === 0) {
      wrap.appendChild(el('p', 'hl-evidence-empty', '根拠を特定できませんでした。'));
      return wrap;
    }
    list.sort(function (a, b) { return (b.score || 0) - (a.score || 0); });
    // 入れ子テーブルは外側の表と列が揃わず破綻する。行の並び（定義リスト形式）にする。
    var strengthTip = '複数の根拠を重ねたスコア。100% が最も強い';
    var listEl = el('div', 'hl-evidence-list');
    // 1 件 = 3 カラム（ファイル / 根拠 / 確度）。列の割り付けは CSS 側が持つ。
    var head = el('div', 'hl-evidence-item hl-evidence-head');
    head.appendChild(el('span', 'hl-evidence-path', 'ファイル'));
    head.appendChild(el('span', 'hl-evidence-why', '根拠'));
    var headScore = el('span', 'hl-evidence-score', 'この根拠の強さ');
    headScore.title = strengthTip;
    head.appendChild(headScore);
    listEl.appendChild(head);
    list.forEach(function (loc) {
      var path = loc.path || '';
      var row = el('div', 'hl-evidence-item');
      var file = setTail(el('span', 'hl-evidence-path'), path, 46);
      if (loc.detail) { file.title = path + ' — ' + loc.detail; }
      row.appendChild(file);
      var badge = el('span', 'hl-evidence-why', REASON_LABELS[loc.reason] || loc.reason || '不明');
      if (loc.detail) { badge.title = loc.detail; }
      row.appendChild(badge);
      // score は 0〜1 で来る想定だが、0〜100 で来ても壊さない。
      var pct = null;
      if (typeof loc.score === 'number' && isFinite(loc.score)) {
        pct = loc.score <= 1 ? Math.round(loc.score * 100) : Math.round(loc.score);
        pct = Math.max(0, Math.min(100, pct));
      }
      var strength = el('span', 'hl-evidence-score');
      strength.title = strengthTip;
      var bar = el('span', 'hl-evidence-bar');
      var fill = el('span', 'hl-evidence-bar-fill');
      fill.style.width = (pct === null ? 0 : pct) + '%';
      bar.appendChild(fill);
      strength.appendChild(bar);
      strength.appendChild(el('span', 'hl-evidence-pct num', pct === null ? '—' : pct + '%'));
      row.appendChild(strength);
      listEl.appendChild(row);
    });
    wrap.appendChild(listEl);
    return wrap;
  }

  /* 確認が必要な点。risks が空でも黙らない（「兆候が無い＝正しい」ではないため）。 */
  function renderRisks(risks) {
    var wrap = el('div', 'hl-risk');
    wrap.appendChild(el('div', 'hl-subhead', '確認が必要な点'));
    var list = (risks || []).slice();
    if (list.length === 0) {
      wrap.appendChild(el('p', 'hl-risk-none',
        '機械的に検出できる兆候はありませんでした。テストの通過は正しさを保証しません。差分を確認してください。'));
      return wrap;
    }
    list.sort(function (a, b) { return severityRank(a.severity) - severityRank(b.severity); });
    var ul = el('ul', 'hl-risk-list');
    list.forEach(function (r) {
      var sev = r.severity || 'low';
      // 1 件 = バッジ・ラベル・詳細の 3 要素。入れ子の行ラッパは置かない。
      var li = el('li', 'hl-risk-item is-' + sev);
      li.appendChild(el('span', 'hl-risk-badge is-' + sev, SEVERITY_LABELS[sev] || sev));
      li.appendChild(el('span', 'hl-risk-label', r.label || r.code || ''));
      if (r.detail) { li.appendChild(el('div', 'hl-risk-detail', r.detail)); }
      ul.appendChild(li);
    });
    wrap.appendChild(ul);
    return wrap;
  }

  /* ---------------- 最小の Markdown 変換（見出し・表・箇条書き・コードフェンスのみ） ----------------
     ライブラリも CDN も足さない。innerHTML を一切使わず DOM を組み立てるため、
     レポート本文がマークアップとして解釈されることはない（XSS 防止）。 */

  function appendInline(parent, text) {
    var rest = String(text == null ? '' : text);
    var re = /(`[^`]+`|\*\*[^*]+\*\*)/;
    while (rest) {
      var m = re.exec(rest);
      if (!m) { parent.appendChild(document.createTextNode(rest)); break; }
      if (m.index > 0) { parent.appendChild(document.createTextNode(rest.slice(0, m.index))); }
      var token = m[0];
      if (token.charAt(0) === '`') {
        parent.appendChild(el('code', 'hl-report-inline-code', token.slice(1, -1)));
      } else {
        parent.appendChild(el('b', null, token.slice(2, -2)));
      }
      rest = rest.slice(m.index + token.length);
    }
  }

  function isTableDivider(line) {
    return /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/.test(line);
  }

  // 行頭・行末の `|` は表の枠であってセルではない。枠由来の空要素を落とさないと
  // 「3 列のはずが 4 列目に空列が出る」形で列数が壊れる。
  function splitTableRow(line) {
    var text = line.trim();
    var cells = text.split('|');
    if (cells.length > 1 && text.charAt(0) === '|') { cells.shift(); }
    if (cells.length > 1 && text.charAt(text.length - 1) === '|') { cells.pop(); }
    return cells.map(function (c) { return c.trim(); });
  }

  // セル値が既知のエージェント ID なら画面では表示名に直す。レポート本文の
  // Markdown はサーバ側が組み立てるため、置き換えはここでしかできない。
  function tableCellText(value) {
    return Object.prototype.hasOwnProperty.call(AGENT_DISPLAY_NAMES, value)
      ? agentDisplayName(value) : value;
  }

  // 列数は見出し行を正とする。あふれた分は最後のセルへ畳み、足りない分は空で埋める。
  function fitRowToColumns(cells, colCount) {
    var row = cells.slice();
    while (row.length > colCount && row[row.length - 1] === '') { row.pop(); }
    if (row.length > colCount) {
      var tail = row.slice(colCount - 1).filter(function (c) { return c !== ''; });
      row = row.slice(0, colCount - 1).concat([tail.join(' | ')]);
    }
    while (row.length < colCount) { row.push(''); }
    return row;
  }

  function buildReportTable(rows) {
    var table = el('table', 'data hl-report-table');
    // 区切り行（|---|---|）は行ではないので、組み立てる前に落とす。
    var body = rows.filter(function (raw) { return !isTableDivider(raw); })
      .map(function (raw) { return splitTableRow(raw); });
    if (body.length === 0) { return table; }
    var headCells = body[0].slice();
    while (headCells.length > 1 && headCells[headCells.length - 1] === '') { headCells.pop(); }
    var colCount = headCells.length;

    var thead = el('thead');
    var trh = el('tr', 'hl-report-tr');
    headCells.forEach(function (c) {
      var th = el('th', 'hl-report-th');
      appendInline(th, c);
      trh.appendChild(th);
    });
    thead.appendChild(trh);
    table.appendChild(thead);

    var tbody = el('tbody');
    body.slice(1).forEach(function (cells) {
      var tr = el('tr', 'hl-report-tr');
      fitRowToColumns(cells, colCount).forEach(function (c) {
        var td = el('td', 'hl-report-td');
        appendInline(td, tableCellText(c));
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    return table;
  }

  // 段落を打ち切るべき行。太字だけの行（小見出し）と引用を含めないと、
  // 「**事象**」と次行の本文が同じ段落に流し込まれる。
  function isStrongHeadingLine(line) {
    return /^\s*\*\*[^*]+\*\*\s*$/.test(line);
  }
  function isBlockStart(line) {
    return /^\s*(```|#{1,6}\s|[-*+]\s|\d+[.)]\s|\||>)/.test(line) || isStrongHeadingLine(line);
  }

  function renderMarkdown(md) {
    var root = el('div', 'hl-report-body');
    var lines = String(md || '').split('\n');
    var i = 0;
    while (i < lines.length) {
      var line = lines[i];

      if (/^\s*```/.test(line)) {
        var info = line.replace(/^\s*```/, '').trim().toLowerCase();
        i += 1;
        var code = [];
        while (i < lines.length && !/^\s*```/.test(lines[i])) { code.push(lines[i]); i += 1; }
        i += 1;
        // 差分は行色を残したまま、レポートの明るい面に載せる（実行ログの黒背景は使わない）。
        if (info === 'diff' || info === 'patch') {
          root.appendChild(buildDiffElement(code.join('\n'), 'hl-report-code hl-report-diff'));
        } else {
          root.appendChild(el('pre', 'hl-report-code', code.join('\n')));
        }
        continue;
      }

      var h = /^\s*(#{1,6})\s+(.*)$/.exec(line);
      if (h) {
        // レポートは画面の一部なので、見出しレベルは h3 以下に押し下げる。
        var head = el('h' + Math.min(6, h[1].length + 2), 'hl-report-h hl-report-head');
        appendInline(head, h[2]);
        root.appendChild(head);
        i += 1;
        continue;
      }

      if (isStrongHeadingLine(line)) {
        var sub = /^\s*\*\*([^*]+)\*\*\s*$/.exec(line);
        root.appendChild(el('h5', 'hl-report-h', sub[1].trim()));
        i += 1;
        continue;
      }

      if (/^\s*>/.test(line)) {
        var quote = el('blockquote', 'hl-report-quote');
        while (i < lines.length && /^\s*>/.test(lines[i])) {
          quote.appendChild(
            el('div', 'hl-report-quote-line', lines[i].replace(/^\s*>\s?/, ''))
          );
          i += 1;
        }
        root.appendChild(quote);
        continue;
      }

      if (/^\s*\|/.test(line)) {
        var rows = [];
        while (i < lines.length && /^\s*\|/.test(lines[i])) { rows.push(lines[i]); i += 1; }
        root.appendChild(buildReportTable(rows));
        continue;
      }

      if (/^\s*[-*+]\s+/.test(line) || /^\s*\d+[.)]\s+/.test(line)) {
        var ordered = /^\s*\d+[.)]\s+/.test(line);
        var listEl = el(ordered ? 'ol' : 'ul',
                        ordered ? 'hl-report-list hl-report-ol' : 'hl-report-list hl-report-ul');
        var itemRe = ordered ? /^\s*\d+[.)]\s+/ : /^\s*[-*+]\s+/;
        while (i < lines.length && itemRe.test(lines[i])) {
          var li = el('li', 'hl-report-li');
          appendInline(li, lines[i].replace(itemRe, ''));
          listEl.appendChild(li);
          i += 1;
        }
        root.appendChild(listEl);
        continue;
      }

      if (!line.trim()) { i += 1; continue; }

      var para = [];
      while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i])) {
        para.push(lines[i].trim());
        i += 1;
      }
      if (para.length) {
        var p = el('p', 'hl-report-p');
        appendInline(p, para.join(' '));
        root.appendChild(p);
      } else {
        i += 1;
      }
    }
    return root;
  }

  function renderDefectsTable(defects) {
    if (!defects || defects.length === 0) {
      return el('p', 'hl-hint', '検出した不具合はありません。');
    }
    var table = el('table', 'data dashboard-table');
    var thead = el('thead');
    var trh = el('tr');
    ['重大度', '事象', '失敗したテスト'].forEach(function (t) { trh.appendChild(el('th', 'hl-th-nowrap', t)); });
    thead.appendChild(trh);
    table.appendChild(thead);
    var tbody = el('tbody');
    defects.forEach(function (d) {
      var tr = el('tr');
      var tdSev = el('td');
      tdSev.appendChild(el('span', 'hl-sev is-' + d.severity, SEVERITY_LABELS[d.severity] || d.severity));
      tr.appendChild(tdSev);
      tr.appendChild(el('td', null, d.title || d.message || ''));
      var tdTest = el('td', 'hl-kv hl-ellipsis', d.test_id || '');
      tdTest.title = d.test_id || '';
      tr.appendChild(tdTest);
      // 疑わしいファイルは直下の「該当箇所の根拠」に確度つきで出るため、列は持たない。
      tbody.appendChild(tr);

      // なぜそのファイルが疑われるのかを、欠陥のすぐ下に出す。
      var evTr = el('tr', 'hl-evidence-row');
      var evTd = el('td');
      evTd.colSpan = 3;
      evTd.appendChild(renderEvidence(d.locations));
      evTr.appendChild(evTd);
      tbody.appendChild(evTr);
    });
    table.appendChild(tbody);
    return table;
  }

  function buildDiffElement(diffText, className) {
    // className で配色の面を差し替える（黒背景の実行ログ / 明るいレポート面）。行色は共通。
    var pre = el('pre', className || 'hl-diff');
    (diffText || '').split('\n').forEach(function (line) {
      // メタ行（ファイル境界・ハンク）を追加削除と同色にすると差分が読めない。
      var cls = 'hl-diff-ctx';
      if (/^(diff --git|index |@@|\+\+\+|---|new file mode|deleted file mode|old mode|new mode|similarity index|rename )/.test(line)) {
        cls = 'hl-diff-meta';
      } else if (line.charAt(0) === '+') {
        cls = 'hl-diff-add add';
      } else if (line.charAt(0) === '-') {
        cls = 'hl-diff-del del';
      }
      pre.appendChild(el('span', cls, line));
    });
    return pre;
  }

  function pillEl(status) {
    var kind = PROPOSAL_STATUS_KIND[status] || 'mute';
    var pill = el('span', 'hl-pill hl-badge-' + kind + ' ' + (status || ''),
      PROPOSAL_STATUS_LABELS[status] || status || '不明');
    if (PROPOSAL_STATUS_TITLES[status]) { pill.title = PROPOSAL_STATUS_TITLES[status]; }
    return pill;
  }

  function renderProposalsTable(proposals) {
    if (!proposals || proposals.length === 0) {
      // 修正が無くても「確認が必要な点」は必ず出す（沈黙を「問題なし」と読ませない）。
      var empty = el('div', 'hl-proposals-empty');
      empty.appendChild(el('p', 'hl-hint', '修正はまだありません。'));
      empty.appendChild(renderRisks(null));
      return empty;
    }
    // 列幅は CSS で決める（「差分を見る」が 3 行に折れないだけの幅が要る）。
    var table = el('table', 'data dashboard-table hl-proposals-table');
    var thead = el('thead');
    var trh = el('tr');
    ['実行者', '状態', '何をどう直したか', '変更ファイル', '詳細'].forEach(function (t) { trh.appendChild(el('th', 'hl-th-nowrap', t)); });
    thead.appendChild(trh);
    table.appendChild(thead);
    var tbody = el('tbody');
    proposals.forEach(function (p) {
      var tr = el('tr');
      var tdAgent = el('td', null, agentDisplayName(p.agent) || '');
      tdAgent.title = p.agent || '';
      tr.appendChild(tdAgent);

      var tdStatus = el('td');
      tdStatus.appendChild(pillEl(p.status));
      tr.appendChild(tdStatus);

      var tdSummary = el('td');
      tdSummary.appendChild(document.createTextNode(p.summary || ''));
      // 失敗/時間切れ/変更なしの理由は必ず出す（2 エージェントの競合など、他に出典が無いため）。
      if ((p.status === 'failed' || p.status === 'timeout' || p.status === 'skipped') && p.error) {
        var errEl = el('div', 'hl-err', p.error);
        tdSummary.appendChild(errEl);
      }
      tr.appendChild(tdSummary);

      var files = p.files_changed || [];
      var tdFiles = el('td', 'num');
      if (files.length === 1) {
        tdFiles.className = 'hl-kv';
        setTail(tdFiles, files[0], 28);
      } else {
        tdFiles.textContent = String(files.length);
        tdFiles.title = files.join('\n');
      }
      tr.appendChild(tdFiles);

      // 差分もバグレポートも同じ詳細行に入れる。行内の入口はトグル 1 つだけ。
      var tdDetail = el('td');
      tr.appendChild(tdDetail);
      tbody.appendChild(tr);

      var detailTr = el('tr', 'hl-detail-row');
      detailTr.hidden = true;
      var detailTd = el('td');
      detailTd.colSpan = 5;
      // 確認が必要な点は常に出す（空でも「兆候が無かった」と書く）。
      detailTd.appendChild(renderRisks(p.risks));
      if (p.diff) {
        detailTd.appendChild(el('div', 'hl-subhead', '差分'));
        detailTd.appendChild(buildDiffElement(p.diff));
      }
      if (p.report_md) {
        detailTd.appendChild(el('div', 'hl-subhead', 'バグレポート'));
        detailTd.appendChild(renderMarkdown(p.report_md));
      }
      detailTr.appendChild(detailTd);
      tbody.appendChild(detailTr);

      var toggle = el('button', 'btn-outline-sm hl-btn-ghost', '詳細を見る');
      toggle.type = 'button';
      toggle.setAttribute('data-testid', 'hl-toggle-detail');
      toggle.setAttribute('aria-expanded', 'false');
      toggle.addEventListener('click', function () {
        detailTr.hidden = !detailTr.hidden;
        toggle.setAttribute('aria-expanded', detailTr.hidden ? 'false' : 'true');
        toggle.textContent = detailTr.hidden ? '詳細を見る' : '詳細を閉じる';
      });
      tdDetail.appendChild(toggle);
    });
    table.appendChild(tbody);
    return table;
  }

  function renderLoop(run) {
    var loopEl = $['hl-loop'];
    loopEl.textContent = '';
    var iterations = run && run.iterations ? run.iterations : [];
    $['hl-loop-empty'].hidden = iterations.length > 0;
    if (iterations.length === 0) { return; }

    var isRunTerminal = run && TERMINAL_STATUSES.indexOf(run.status) !== -1;
    iterations.forEach(function (iter, idx) {
      var isActive = !isRunTerminal && idx === iterations.length - 1;
      var block = el('div', 'hl-iter');
      block.appendChild(el('h3', 'hl-iter-head', '第 ' + iter.index + ' 周'));
      block.appendChild(renderStepper(stepStates(iter, isActive)));
      block.appendChild(el('h4', 'hl-sub', '検証結果'));
      block.appendChild(renderVerifyResult(iter.verify_before));
      if (iter.defects) {
        block.appendChild(el('h4', 'hl-sub', '検出した不具合'));
        block.appendChild(renderDefectsTable(iter.defects));
      }
      if (iter.proposals) {
        block.appendChild(el('h4', 'hl-sub', '修正'));
        block.appendChild(renderProposalsTable(iter.proposals));
      }
      // 再検証は「無い」ことも情報。ブロックごと消すと、直ったのか実行していないのかが分からない。
      block.appendChild(el('h4', 'hl-sub', '再検証結果'));
      block.appendChild(renderReverifyResult(iter));
      loopEl.appendChild(block);
    });
  }

  var LOG_TS_RE = /^\[(\d{2}):(\d{2}):(\d{2})\]\s?/;

  /* 時刻だけでは前後関係が読めないので、最初の行からの経過秒を並記する。 */
  function renderLogLines(lines, errorText) {
    var logEl = $['hl-log'];
    logEl.textContent = '';
    var list = lines || [];
    if (!list.length && !errorText) {
      // 空の黒い箱だけを置くと「壊れている」ように見える。何が入る場所かを書く。
      logEl.appendChild(el('div', 'hl-log-placeholder', 'ヒーリングを開始すると、ここに進行が 1 行ずつ出ます。'));
      return;
    }
    var base = null;
    list.forEach(function (line) {
      var raw = String(line);
      var m = LOG_TS_RE.exec(raw);
      var text = raw;
      if (m) {
        var sec = (Number(m[1]) * 3600) + (Number(m[2]) * 60) + Number(m[3]);
        if (base === null) { base = sec; }
        var diff = sec - base;
        if (diff < 0) { diff += 86400; }
        text = '[' + m[1] + ':' + m[2] + ':' + m[3] + ' +' + diff.toFixed(1) + 's] ' + raw.slice(m[0].length);
      }
      logEl.appendChild(el('div', 'hl-log-line', text));
    });
    // 失敗の理由はバナーだけでなくログの末尾にも残す（後から読み返す先はログのため）。
    if (errorText) {
      logEl.appendChild(el('div', 'hl-log-line hl-log-error', '失敗の理由: ' + humanizeError(flattenParens(errorText))));
    }
    logEl.scrollTop = logEl.scrollHeight;
  }

  /* ---------------- PR・判断 ---------------- */

  function renderPrInfo(run) {
    var wrap = $['hl-pr-info'];
    wrap.textContent = '';
    var pr = run && run.pull_request;
    if (!pr || !pr.number) { wrap.hidden = true; return; }
    wrap.hidden = false;
    wrap.appendChild(el('span', 'hl-badge', pr.state || ''));
    wrap.appendChild(el('div', null, '#' + pr.number + ' ' + (pr.title || '')));
    var link = el('a', null, pr.url || '');
    link.href = pr.url || '#';
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    wrap.appendChild(link);
    if (run.decisions && run.decisions.length > 0) {
      var hist = el('ul');
      run.decisions.forEach(function (d) {
        var actionLabel = d.action === 'approve' ? '承認' : (d.action === 'merge' ? 'マージ' : (d.action === 'reject' ? '却下' : d.action));
        var text = fmtTime(d.at) + ' ' + actionLabel + (d.actor ? '（' + d.actor + '）' : '') + (d.note ? ': ' + d.note : '');
        hist.appendChild(el('li', null, text));
      });
      wrap.appendChild(hist);
    }
  }

  function createPullRequest() {
    if (!state.selectedRunId) { return; }
    clearError();
    apiFetch('/runs/' + state.selectedRunId + '/pull-request', { method: 'POST', body: JSON.stringify({}) })
      .then(function () { return fetchAndRenderRun(state.selectedRunId); })
      .catch(function (e) { showError('PR の作成に失敗しました: ' + e.message); });
  }

  function cancelRun() {
    if (!state.selectedRunId) { return; }
    clearError();
    apiFetch('/runs/' + state.selectedRunId + '/cancel', { method: 'POST', body: JSON.stringify({}) })
      .then(function () { return fetchAndRenderRun(state.selectedRunId); })
      .catch(function (e) { showError('実行の中止に失敗しました: ' + e.message); });
  }

  function submitDecision(action) {
    if (!state.selectedRunId) { return; }
    clearError();
    var note = $['hl-decision-note'] ? $['hl-decision-note'].value.trim() : '';
    apiFetch('/runs/' + state.selectedRunId + '/decision', { method: 'POST', body: JSON.stringify({ action: action, note: note }) })
      .then(function () {
        if ($['hl-decision-note']) { $['hl-decision-note'].value = ''; }
        return fetchAndRenderRun(state.selectedRunId);
      })
      .catch(function (e) { showError('判断の記録に失敗しました: ' + e.message); });
  }

  function renderUnverified(run) {
    var block = $['hl-unverified'];
    var list = run && run.unverified ? run.unverified : [];
    if (!list || list.length === 0) { block.hidden = true; return; }
    block.hidden = false;
    $['hl-unverified-list'].textContent = '';
    list.forEach(function (item) {
      // 過去の実行データには内部用語のままの文言が残っている。表示側でも言い換える。
      $['hl-unverified-list'].appendChild(
        el('li', null, humanizeError(flattenParens(String(item))))
      );
    });
  }

  /* ---------------- 実行履歴ビュー ---------------- */

  function loadHistory(limit) {
    limit = limit || 20;
    state.historyLimit = limit;
    return apiFetch('/runs?limit=' + limit).then(function (data) {
      state.historyRuns = asList(data, 'runs');
      renderHistory();
    }).catch(function (e) { showError('実行履歴を取得できませんでした: ' + e.message); });
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
    $['hl-runs-empty'].hidden = runs.length > 0;
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

  function init() {
    cacheDom();
    state.focusRunId = document.body.getAttribute('data-focus-run-id') || '';
    IS_ADMIN = document.body.getAttribute('data-hl-admin') === 'true';

    on('hl-nav-run', 'click', function () { switchView('run'); });
    on('hl-nav-projects', 'click', function () { switchView('projects'); });
    on('hl-nav-history', 'click', function () { switchView('history'); });
    // 接続先ビューの右上が正規の入口。空状態にも同じ入口を置く。
    var addOnList = document.getElementById('hl-add-project-2');
    if (addOnList) { addOnList.addEventListener('click', function () { showConnectForm(null); }); }
    // #hl-add-project-2 / #hl-projects-empty-add は Jinja 側（hl_admin）が出し分ける。
    // ここで IS_ADMIN を再判定すると二重管理になるため、存在確認だけで結び付ける。
    var addOnEmpty = document.getElementById('hl-projects-empty-add');
    if (addOnEmpty) { addOnEmpty.addEventListener('click', function () { showConnectForm(null); }); }

    document.addEventListener('click', function (ev) {
      if (!openRowMenu) { return; }
      if (openRowMenu.wrap.contains(ev.target) || openRowMenu.list.contains(ev.target)) { return; }
      closeRowMenu();
    });
    // body 直下・position: fixed で開くため、スクロールやリサイズで座標がずれる。追従させず閉じる。
    window.addEventListener('scroll', function () { closeRowMenu(); }, true);
    window.addEventListener('resize', function () { closeRowMenu(); });
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape' || ev.key === 'Esc') { closeRowMenu(); }
    });

    on('hl-project-select', 'change', function () { selectProject(this.value); });

    on('hl-connect-submit', 'click', submitConnectForm);
    on('hl-connect-cancel', 'click', hideConnectForm);

    on('hl-check-btn', 'click', runCheck);

    on('hl-start', 'click', function () {
      var target = document.getElementById('hl-confirm-target');
      if (target) { target.textContent = selectedProjectName(); }
      openConfirm($['hl-start-confirm']);
    });
    on('hl-start-yes', 'click', function () { setConfirmOpen($['hl-start-confirm'], false); startRun(); });
    on('hl-start-no', 'click', function () { setConfirmOpen($['hl-start-confirm'], false); });

    on('hl-cancel', 'click', function () { openConfirm($['hl-cancel-confirm']); });
    on('hl-cancel-yes', 'click', function () { setConfirmOpen($['hl-cancel-confirm'], false); cancelRun(); });
    on('hl-cancel-no', 'click', function () { setConfirmOpen($['hl-cancel-confirm'], false); });

    on('hl-merge', 'click', function () { openConfirm($['hl-merge-confirm']); });
    on('hl-merge-yes', 'click', function () { setConfirmOpen($['hl-merge-confirm'], false); submitDecision('merge'); });
    on('hl-merge-no', 'click', function () { setConfirmOpen($['hl-merge-confirm'], false); });

    on('hl-reject', 'click', function () { openConfirm($['hl-reject-confirm']); });
    on('hl-reject-yes', 'click', function () { setConfirmOpen($['hl-reject-confirm'], false); submitDecision('reject'); });
    on('hl-reject-no', 'click', function () { setConfirmOpen($['hl-reject-confirm'], false); });

    on('hl-approve', 'click', function () { submitDecision('approve'); });
    on('hl-create-pr', 'click', createPullRequest);
    on('hl-rerun', 'click', function () { submitDecision('rerun'); });

    on('hl-runs-more', 'click', function () {
      loadHistory((state.historyLimit || 20) + 20);
    });

    loadAgentOptions();
    switchView('run');

    loadProjects().then(function () {
      loadStats();
      if (!state.projects.length) { clearRunView(); return; }
      if (state.focusRunId) {
        var fid = state.focusRunId;
        state.focusRunId = '';
        apiFetch('/runs/' + encodeURIComponent(fid)).then(function (data) {
          var run = asObj(data, 'run');
          selectProject(run.project_id || state.projects[0].project_id, { openRunId: fid });
        }).catch(function () { selectProject(state.projects[0].project_id); });
      } else {
        selectProject(state.projects[0].project_id);
      }
    });

    loadHistory(20);
  }

  document.addEventListener('DOMContentLoaded', init);
})();
