'use strict';

/* オートヒーリング設定画面（templates/healing.html）: 共通: 定数・画面状態・DOM 参照・書式・API 呼び出し・URL ハッシュとビュー切替・上部の統計
   読み込み順: healing-core.js → healing-projects.js → healing-report.js → healing-run.js → healing-actions.js → healing-history.js → healing.js。
   ファイル間の共有は window.HealingApp（HL）だけ。他ファイルの関数は呼び出し時に HL から引く。 */
(function (HL) {
  /* ---- 他ファイルの宣言 ---- */
  function riskCounts() { return HL.riskCounts.apply(this, arguments); }

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
      'hl-f-domain', 'hl-f-domain-status',
      'hl-connect-submit', 'hl-connect-cancel', 'hl-back-to-projects',
      'hl-runs', 'hl-runs-empty', 'hl-runs-more',
      'hl-ws-status', 'hl-run-reason', 'hl-run-context', 'hl-blockers'
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

  var VIEW_NAMES = ['run', 'projects', 'history'];

  /* 画面状態は URL ハッシュに載せる（docverify と同じ書き方）。
     画面切替は pushState、実行の選択は replaceState。#run/<実行ID> #projects #history */
  function parseHash() {
    var m = /^#(run|projects|history)(?:\/(.+))?$/.exec(location.hash || '');
    if (!m) { return null; }
    var rid = '';
    try { rid = m[2] ? decodeURIComponent(m[2]) : ''; } catch (e) { rid = ''; }
    return { view: m[1], runId: rid };
  }

  function hashFor(view) {
    if (view === 'run' && state.selectedRunId) { return '#run/' + encodeURIComponent(state.selectedRunId); }
    return '#' + view;
  }

  function syncHash(push) {
    var want = location.pathname + location.search + hashFor(state.activeView);
    if (location.pathname + location.search + location.hash === want) { return; }
    try { history[push ? 'pushState' : 'replaceState'](null, '', want); } catch (e) { /* URL を書けなくても画面は動かす */ }
  }

  function switchView(view, opts) {
    opts = opts || {};
    state.activeView = view;
    // ビューそのものも要素の有無を確かめてから触る。テンプレート側で 1 つでも
    // 外れると、以降の初期化ごと落ちて画面が白くなるため。
    VIEW_NAMES.forEach(function (v) {
      var sec = $['hl-view-' + v];
      if (sec) { sec.hidden = v !== view; }
    });
    // サイドバーは共通部品（報告書 / 設定）に置き換わり、ビュー切替のナビは
    // この画面には無い。要素が無くても落とさない。
    VIEW_NAMES.forEach(function (v) {
      var nav = $['hl-nav-' + v];
      if (nav && nav.classList) { nav.classList.toggle('active', view === v); }
    });
    if (!opts.noUrl) { syncHash(!opts.replace); }
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

  /* ---- 他ファイルへ公開 ---- */
  HL.$ = $;
  HL.AGENT_DISPLAY_NAMES = AGENT_DISPLAY_NAMES;
  HL.CHECK_DEFS = CHECK_DEFS;
  HL.POLL_MS = POLL_MS;
  HL.POLL_STOP_STATUSES = POLL_STOP_STATUSES;
  HL.PROPOSAL_STATUS_KIND = PROPOSAL_STATUS_KIND;
  HL.PROPOSAL_STATUS_LABELS = PROPOSAL_STATUS_LABELS;
  HL.PROPOSAL_STATUS_TITLES = PROPOSAL_STATUS_TITLES;
  HL.SEVERITY_LABELS = SEVERITY_LABELS;
  HL.STATUS_LABELS = STATUS_LABELS;
  HL.TERMINAL_STATUSES = TERMINAL_STATUSES;
  HL.VIEW_NAMES = VIEW_NAMES;
  HL.agentDisplayName = agentDisplayName;
  HL.apiFetch = apiFetch;
  HL.applyFixedHint = applyFixedHint;
  HL.asList = asList;
  HL.asObj = asObj;
  HL.cacheDom = cacheDom;
  HL.clearError = clearError;
  HL.el = el;
  HL.flattenParens = flattenParens;
  HL.fmtDuration = fmtDuration;
  HL.fmtRelTime = fmtRelTime;
  HL.fmtTime = fmtTime;
  HL.getProject = getProject;
  HL.humanizeError = humanizeError;
  HL.loadStats = loadStats;
  HL.nextActionFor = nextActionFor;
  HL.on = on;
  HL.parseHash = parseHash;
  HL.selectedProjectName = selectedProjectName;
  HL.setPathTail = setPathTail;
  HL.setTail = setTail;
  HL.showError = showError;
  HL.state = state;
  HL.statusBadgeClass = statusBadgeClass;
  HL.switchView = switchView;
  HL.syncHash = syncHash;
  HL.tailText = tailText;
})(window.HealingApp = window.HealingApp || {});
