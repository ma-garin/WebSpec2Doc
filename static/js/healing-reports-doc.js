/* オートヒーリングの報告書（templates/healing_reports.html・healing_report.html）: 報告書の本文: 根拠・差分・原文・承認履歴・編集・承認／差し戻し／却下（確認を経由）
   読み込み順: healing-reports-core.js → healing-reports-list.js → healing-reports-doc.js → healing-reports-bundle.js → healing-reports.js。
   ファイル間の共有は window.HealingReports（HL）だけ。他ファイルの関数は呼び出し時に HL から引く。 */
(function (HL) {
  'use strict';

  /* ---- 他ファイルの宣言 ---- */
  var IS_ADMIN = HL.IS_ADMIN;
  var STATUS_LABELS = HL.STATUS_LABELS;
  var WS_REPORT_REASON = HL.WS_REPORT_REASON;
  var WS_REPORT_STATUS = HL.WS_REPORT_STATUS;
  function api() { return HL.api.apply(this, arguments); }
  function askConfirm() { return HL.askConfirm.apply(this, arguments); }
  function clearError() { return HL.clearError.apply(this, arguments); }
  function el() { return HL.el.apply(this, arguments); }
  function renderContext() { return HL.renderContext.apply(this, arguments); }
  function renderHead() { return HL.renderHead.apply(this, arguments); }
  function showError() { return HL.showError.apply(this, arguments); }
  function showState() { return HL.showState.apply(this, arguments); }
  var state = HL.state;


  /* ---------------- 報告書の本文 ---------------- */

  var SEVERITY_LABELS = { high: '高', medium: '中', low: '低' };
  var REASON_LABELS = {
    traceback: '実行時トレース',
    'import': 'import 関係',
    'recent-change': '直近の変更',
    'test-name': 'テスト名',
    selector: '画面の文言',
    route: 'URL のルート',
    screen: '画面仕様'
  };
  /* 出所ラベル。節見出しの右に薄字で置く（AI か実測か人の入力かを自分で確かめずに区別できるように）。 */
  var SOURCE_LABELS = { measured: '実測', user: '入力', llm: 'AIの提案', assumed: '前提', unverified: '未確認' };

  function section(title, sourceKey) {
    var h = el('h2', 'hl-doc-h');
    h.appendChild(document.createTextNode(title));
    if (sourceKey) {
      h.appendChild(el('span', 'hl-src', SOURCE_LABELS[sourceKey] || sourceKey));
    }
    return h;
  }

  /* 節の本文＋右のスクリーンショット。画像が無ければ 1 列で組む。 */
  function sectionBody(nodes, shotPath) {
    var wrap = el('div', 'hl-doc-sec' + (shotPath ? '' : ' is-single'));
    var main = el('div');
    nodes.forEach(function (n) { if (n) { main.appendChild(n); } });
    wrap.appendChild(main);
    if (shotPath) {
      var box = el('div', 'hl-doc-shot');
      var img = document.createElement('img');
      img.src = '/api/healing/reports/' + encodeURIComponent(state.reportId) +
                '/screenshot?path=' + encodeURIComponent(shotPath);
      img.alt = '画面の状態';
      img.loading = 'lazy';
      img.addEventListener('error', function () { box.remove(); });
      box.appendChild(img);
      wrap.appendChild(box);
    }
    return wrap;
  }

  function verifyBox(label, text, kind) {
    var box = el('div', 'hl-verify-box is-' + kind);
    box.appendChild(el('small', null, label));
    box.appendChild(el('b', null, text || '—'));
    return box;
  }

  function details(summaryText, badgeText, open) {
    var d = document.createElement('details');
    if (open) { d.open = true; }
    var sum = document.createElement('summary');
    sum.appendChild(el('span', 'hl-sum-tri', '▸'));
    sum.appendChild(el('b', null, summaryText));
    if (badgeText) { sum.appendChild(el('span', 'hl-sum-note', badgeText)); }
    d.appendChild(sum);
    return d;
  }

  function renderAttention(report) {
    var high = report.attention.filter(function (a) { return a.severity === 'high'; }).length;
    var d = details('確認が必要な点 ' + report.attention.length + ' 件',
                    high > 0 ? '重大 ' + high : '', true);
    if (!report.attention.length) {
      d.appendChild(el('p', 'hl-doc-p',
        '機械的に検出できる兆候はありませんでした。テストの通過は正しさを保証しません。差分を確認してください。'));
      return d;
    }
    var ul = el('ul', 'hl-attn');
    report.attention.forEach(function (a) {
      var li = el('li');
      li.appendChild(el('span', 'hl-badge is-' +
        (a.severity === 'high' ? 'err' : a.severity === 'medium' ? 'warn' : 'mute'),
        SEVERITY_LABELS[a.severity] || a.severity));
      var body = el('div');
      body.appendChild(el('b', null, a.label || ''));
      if (a.detail) { body.appendChild(el('small', null, a.detail)); }
      li.appendChild(body);
      ul.appendChild(li);
    });
    d.appendChild(ul);
    return d;
  }

  function renderDiff(proposal, openIt) {
    var files = (proposal && proposal.files_changed) || [];
    var d = details('変更内容（差分 ' + files.length + ' ファイル）', '開発者向け', !!openIt);
    if (!proposal || !proposal.diff) {
      d.appendChild(el('p', 'hl-doc-p', '差分はありません。'));
      return d;
    }
    var pre = el('pre', 'hl-diff');
    proposal.diff.split('\n').forEach(function (line) {
      var cls = 'hl-diff-line';
      if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('@@') ||
          line.startsWith('diff ') || line.startsWith('index ')) { cls += ' is-meta'; }
      else if (line.startsWith('+')) { cls += ' is-add'; }
      else if (line.startsWith('-')) { cls += ' is-del'; }
      pre.appendChild(el('div', cls, line));
    });
    d.appendChild(pre);
    return d;
  }

  /* AI の説明の原文をここに置く。顧客向けの本文は言い直したものを出すため、
     元の文面（英語のまま・環境の言い訳つき）を読む場所が要る。 */
  function appendOriginal(box, label, text) {
    if (!text) { return; }
    box.appendChild(el('p', 'hl-doc-note', label));
    box.appendChild(el('blockquote', 'hl-quote', text));
  }

  /* 原文をそのまま出すと Markdown の装飾が画面に漏れる（** ` # 表 罫線）。
     規則は report_present.strip_markup と同じものを画面側にも持つ。 */
  function stripMarkup(text) {
    var body = String(text || '').replace(/```[\s\S]*?```/g, ' ');
    var kept = [];
    body.split('\n').forEach(function (line) {
      if (/^\s*\|/.test(line)) { return; }                    // 表の行
      if (/^\s*[─-╿=_*-]{3,}\s*$/.test(line)) { return; }  // 罫線
      var table = line.match(/\|[^|\n]*\|/);
      kept.push(table ? line.slice(0, table.index).replace(/\s+$/, '') : line);
    });
    return kept.join('\n')
      .replace(/\*\*([^*]+)\*\*/g, '$1')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/^\s*[-*+]\s+/gm, '')
      .replace(/^#{1,6}\s*/gm, '')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }

  /* 同じ説明が原因欄・対応欄・実行ログの 3 か所に入っていることがある。
     先頭 80 字が同じものは 1 つにまとめ（長いほうを残し）、何の原文かを名乗らせる。 */
  function originalTexts(proposal, report) {
    var rows = [
      { label: '原因欄の原文（AI の説明）', text: stripMarkup(report && report.cause_text_original) },
      { label: '対応欄の原文（AI の説明）', text: stripMarkup(report && report.action_text_original) },
      { label: 'AI の説明（実行時の全文）', text: stripMarkup(proposal && proposal.rationale) }
    ];
    var seen = {}, out = [];
    rows.forEach(function (row) {
      if (!row.text) { return; }
      var key = 'k' + row.text.replace(/\s+/g, ' ').slice(0, 80);
      if (!(key in seen)) {
        row.labels = [row.label];
        seen[key] = row;
        out.push(row);
        return;
      }
      var kept = seen[key];
      kept.labels.push(row.label);  // 同じ文が何の原文でもあることを名乗らせる
      if (row.text.length > kept.text.length) { kept.text = row.text; }  // 詰めていないほうを残す
    });
    return out.map(function (row) {
      return { label: row.labels.join('・'), text: row.text };
    });
  }

  function renderEvidence(proposal, report) {
    var d = details('該当箇所の根拠と、AI の説明', '開発者向け', false);
    var locations = (proposal && proposal.locations) || [];
    if (locations.length) {
      var table = el('table', 'hl-evidence');
      var thead = el('thead'), htr = el('tr');
      ['ファイル', '根拠', '強さ'].forEach(function (t) { htr.appendChild(el('th', null, t)); });
      thead.appendChild(htr); table.appendChild(thead);
      var tbody = el('tbody');
      locations.slice().sort(function (a, b) { return (b.score || 0) - (a.score || 0); })
        .forEach(function (loc) {
          var tr = el('tr');
          tr.appendChild(el('td', 'hl-ev-path', loc.path || ''));
          tr.appendChild(el('td', null, REASON_LABELS[loc.reason] || loc.reason || ''));
          var td = el('td', 'hl-ev-score');
          var bar = el('span', 'hl-bar');
          var fill = el('i');
          fill.style.width = Math.round((loc.score || 0) * 100) + '%';
          bar.appendChild(fill);
          td.appendChild(bar);
          td.appendChild(el('small', null, Math.round((loc.score || 0) * 100) + '%'));
          tr.appendChild(td);
          tbody.appendChild(tr);
        });
      table.appendChild(tbody);
      d.appendChild(table);
    } else {
      d.appendChild(el('p', 'hl-doc-p', '該当箇所を特定できませんでした。'));
    }
    var origins = originalTexts(proposal, report);
    origins.forEach(function (row) { appendOriginal(d, row.label, row.text); });
    if (origins.length) {
      d.appendChild(el('p', 'hl-doc-note', 'AI の自己申告です。差分で確認してください。'));
    }
    return d;
  }

  function renderApprovals(report) {
    var roles = { proposed: '提案', approved: '承認', returned: '差し戻し', rejected: '却下', customer: '顧客確認' };
    var parts = report.approvals.map(function (a) {
      return (roles[a.role] || a.role) + ': ' + (a.who || '—') + ' ' + (a.at || '').slice(0, 16).replace('T', ' ');
    });
    if (report.fix_target === 'script') {
      parts.push('PR: 不要（テスト側の修正）');
    } else {
      parts.push(report.pr_number ? 'PR: #' + report.pr_number : 'PR: 承認後に作成');
    }
    return el('p', 'hl-doc-p hl-sign', parts.join(' ／ '));
  }

  function renderDoc(data) {
    var report = data.report;
    var proposal = data.proposal;
    var sources = report.sources || {};
    var doc = document.getElementById('hl-doc');
    doc.textContent = '';
    doc.setAttribute('aria-busy', 'false');

    doc.appendChild(el('h1', 'hl-doc-title', '保守対応報告書'));
    var meta = el('p', 'hl-doc-meta');
    [
      '案件: ' + (report.project_name || '—'),
      report.target_url ? '対象: ' + report.target_url : '',
      report.incident_detected_at ? '対応日: ' + report.incident_detected_at.slice(0, 10) : ''
    ].filter(Boolean).forEach(function (t) { meta.appendChild(el('span', null, t)); });
    meta.appendChild(el('span', 'hl-badge is-ac', STATUS_LABELS[report.status] || report.status));
    doc.appendChild(meta);

    // 1. 事象
    doc.appendChild(section('1. 事象', sources.incident));
    doc.appendChild(sectionBody([
      el('p', 'hl-doc-p', report.incident_text || '記録なし'),
      el('p', 'hl-doc-note',
        [report.incident_screen_name, report.incident_test_id, report.incident_verify]
          .filter(Boolean).join(' ／ '))
    ], report.incident_screenshot));

    // 2. 原因
    doc.appendChild(section('2. 原因', sources.cause));
    var causeNodes = [];
    if (canEditDoc(report)) {
      /* 編集欄は顧客に出る文そのもの。人が仕上げるのはこの文なので 1 つだけ置く。
         AI の説明の原文は折りたたみ「該当箇所の根拠と、AI の説明」に出し続ける。 */
      causeNodes.push(fieldEditor('hl-cause-edit', report.cause_text || '',
        '例: 合計金額の計算で税率が適用されていませんでした', saveCause));
      causeNodes.push(el('p', 'hl-doc-note', report.cause_text_original
        ? 'この文面はそのまま顧客に出ます。AI の説明の原文は下の「該当箇所の根拠と、AI の説明」にあります。書き直すと保存されます。'
        : 'この文面はそのまま顧客に出ます。書き直すと保存されます。'));
    } else {
      causeNodes.push(el('p', 'hl-doc-p', report.cause_text || '—'));
    }
    if (report.cause_location) {
      var loc = el('p', 'hl-doc-note');
      loc.appendChild(document.createTextNode('箇所: '));
      loc.appendChild(el('code', null, report.cause_location));
      causeNodes.push(loc);
    }
    doc.appendChild(sectionBody(causeNodes, ''));

    // 3. 対応
    doc.appendChild(section('3. 対応', sources.action));
    var actionNodes = [];
    if (canEditDoc(report)) {
      /* 対応が書かれていない報告書では、表示文はこちらで足したもの。編集欄は
         空で始めて、消し忘れたまま保存されないようにする。 */
      actionNodes.push(fieldEditor('hl-action-edit',
        report.action_text_generated ? '' : (report.action_text || ''),
        '例: 手順を確認し、設定値を修正しました', saveAction));
      actionNodes.push(el('p', 'hl-doc-note', report.action_text_generated
        ? '空のままだと「' + report.action_text + '」と顧客に出ます。書き直すと保存されます。'
        : 'この文面はそのまま顧客に出ます。書き直すと保存されます。'));
    } else {
      actionNodes.push(el('p', 'hl-doc-p', report.action_text || '—'));
    }
    var actionInfo = [report.action_by, report.action_diff_stats].filter(Boolean).join(' ／ ');
    if (actionInfo) { actionNodes.push(el('p', 'hl-doc-note', actionInfo)); }
    if (report.fix_target === 'script') {
      actionNodes.push(el('p', 'hl-doc-note', 'サイトのコードは変更していません。テストの探し方だけを直しました'));
    }
    doc.appendChild(sectionBody(actionNodes, report.action_screenshot));

    // 4. 検証
    doc.appendChild(section('4. 検証', sources.verify));
    var ver = el('div', 'hl-verify');
    ver.appendChild(verifyBox('修正前', report.verify_before, 'err'));
    ver.appendChild(verifyBox('修正後', report.verify_after,
      report.verify_after_ok === true ? 'ok' : report.verify_after_ok === false ? 'err' : 'mute'));
    ver.appendChild(verifyBox('画面仕様との照合', report.spec_match,
      report.spec_match === '未照合' ? 'mute' : 'ok'));
    doc.appendChild(ver);

    // 折りたたみ 3 つ
    doc.appendChild(renderAttention(report));
    doc.appendChild(renderDiff(proposal, report.status === 'awaiting'));
    doc.appendChild(renderEvidence(proposal, report));

    // 5. 承認
    doc.appendChild(section('5. 承認'));
    doc.appendChild(renderApprovals(report));

    renderReportHead(report, data.run);
    renderActions(report);
  }

  function renderReportHead(report, run) {
    var m = WS_REPORT_STATUS[report.status] || ['unverified', report.status || '状態不明'];
    renderHead({
      title: '保守対応報告書' + (report.title ? '：' + report.title : ''),
      desc: '1 つの欠陥について、事象・原因・対応・検証を上から順に読み、最後に承認します。',
      statusCode: m[0], statusLabel: m[1],
      reason: WS_REPORT_REASON[report.status] || '状態の理由を取得できませんでした。',
      reasonKind: report.status === 'awaiting' ? 'warning' : (report.status === 'rejected' ? 'error' : 'info')
    });
    renderContext([
      { label: '案件', value: report.project_name },
      { label: '対象', value: report.target_url },
      { label: '実行', value: report.run_id ? String(report.run_id).slice(0, 12) : '',
        href: report.run_id ? '/healing/runs/' + encodeURIComponent(report.run_id) : '' },
      { label: 'PR', value: report.pr_number ? '#' + report.pr_number : (report.fix_target === 'script' ? '不要（テスト側の修正）' : '未作成'),
        href: report.pr_url || '', external: true }
    ]);
  }

  /* 書き直せるのは承認待ちの報告書だけ。承認・差し戻しの後に本文が動くと、
     顧客に出した文と証跡が食い違う。原因欄と対応欄で同じ判定を使う。 */
  function canEditDoc(report) {
    return IS_ADMIN && report.status === 'awaiting';
  }

  /* 顧客に出る文面を人が仕上げる欄。原因と対応で作りを共有する。
     値が変わっていない blur では保存しない（同じ内容で監査ログが増えるため）。
     クラス hl-action-edit は幅の指定を借りているだけ（CSS は別担当のファイル）。 */
  function fieldEditor(id, text, placeholder, save) {
    var ta = el('textarea', 'hl-field hl-action-edit');
    ta.id = id;
    ta.rows = 3;
    ta.value = text || '';
    ta.placeholder = placeholder;
    // 見出し（原因／対応）は欄の外の section にあるため、読み上げ用の名前を欄そのものに付ける
    ta.setAttribute('aria-label', id === 'hl-cause-edit' ? '原因（顧客向けの文面）' : '対応（顧客向けの文面）');
    var saved = ta.value;
    ta.addEventListener('blur', function () {
      if (ta.value === saved) { return; }
      saved = ta.value;
      save(ta.value);
    });
    return ta;
  }

  function saveCause(text) {
    api('/api/healing/reports/' + encodeURIComponent(state.reportId), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cause_text: text })
    }).then(function () { toast('原因を保存しました'); })
      .catch(function (e) { showError('保存できませんでした: ' + e.message); });
  }

  function saveAction(text) {
    api('/api/healing/reports/' + encodeURIComponent(state.reportId), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action_text: text })
    }).then(function () { toast('対応を保存しました'); })
      .catch(function (e) { showError('保存できませんでした: ' + e.message); });
  }

  function toast(message) {
    var box = document.getElementById('hl-toast');
    if (!box) { return; }
    box.textContent = message;
    box.hidden = false;
    setTimeout(function () { box.hidden = true; }, 3000);
  }

  /* 承認ボタンの横に出す阻害理由。件数 0 も「0 件」と出す（出ない＝問題なし、と読ませない）。 */
  function blockersBox(parts, note) {
    var box = el('div', 'hl-blockers');
    box.setAttribute('aria-live', 'polite');
    box.appendChild(el('b', 'hl-blockers-lead', '承認の前に確認'));
    var ul = el('ul', 'hl-blockers-list');
    parts.forEach(function (p) {
      var li = el('li');
      li.appendChild(el('span', 'hl-blocker' + (p.n > 0 ? ' ' + p.kind : ''), p.n + ' 件'));
      li.appendChild(document.createTextNode(' ' + p.label));
      ul.appendChild(li);
    });
    box.appendChild(ul);
    box.appendChild(el('p', 'hl-doc-note', note));
    return box;
  }

  function reportBlockers(report) {
    var attn = report.attention || [];
    var unresolved = attn.length;
    var failed = (report.verify_after_ok === false ? 1 : 0) + (report.action_empty ? 1 : 0);
    var unverified = (report.verify_after_ok == null ? 1 : 0) + (report.spec_match === '未照合' ? 1 : 0);
    var total = unresolved + failed + unverified;
    return blockersBox([
      { n: failed, label: '失敗（検証が通っていない・直っていない）', kind: 'is-err' },
      { n: unresolved, label: '未解決（確認が必要な点）', kind: 'is-warn' },
      { n: unverified, label: '未確認（検証の未実行・画面仕様の未照合）', kind: 'is-warn' }
    ], total > 0 ? '残っているものを読んでから判断してください。' : '機械的に分かる残りはありません。テストの通過は正しさの保証ではありません。');
  }

  function renderActions(report) {
    var box = document.getElementById('hl-doc-actions');
    if (!box) { return; }
    box.textContent = '';
    var high = report.attention.filter(function (a) { return a.severity === 'high'; }).length;
    var canDecide = IS_ADMIN && report.status === 'awaiting';
    box.hidden = false;

    if (canDecide) {
      var note = el('textarea', 'hl-field');
      note.id = 'hl-report-note';
      note.rows = 3;
      note.placeholder = '承認のメモ（報告書と証跡に残ります）';
      note.setAttribute('aria-label', '承認のメモ');
      box.appendChild(note);

      var approveLabel = report.fix_target === 'script' ? '承認' : '承認して修正を送る';
      box.appendChild(reportBlockers(report));
      var approve = el('button', 'hl-btn' + (high > 0 ? '' : ' is-primary'), approveLabel);
      approve.type = 'button';
      approve.addEventListener('click', function () {
        var script = report.fix_target === 'script';
        askConfirm({
          title: 'この報告書を承認しますか？',
          message: script
            ? '承認は報告書と証跡に記録され、以後は書き直せません。サイトのコードは変更しません。'
            : '承認すると、この修正が接続先の GitHub リポジトリへ PR として送られます。外部のリポジトリに記録が残り、承認は取り消せません（PR は後から閉じられます）。',
          detail: '案件: ' + (report.project_name || '—'),
          confirmLabel: script ? '承認する' : '承認して PR を送る'
        }).then(function (ok) { if (ok) { decide('approve', note.value, approve); } });
      });
      box.appendChild(approve);
      if (report.fix_target !== 'script') {
        box.appendChild(el('p', 'hl-doc-note', '開発者には PR として届きます'));
      }

      var back = el('button', 'hl-btn', '差し戻す');
      back.type = 'button';
      back.addEventListener('click', function () {
        if (!note.value.trim()) {
          showError('差し戻すときは、どう直してほしいかをメモに書いてください。');
          note.focus();
          return;
        }
        decide('return', note.value, back);
      });
      box.appendChild(back);

      var reject = el('button', 'hl-btn is-danger', '却下');
      reject.type = 'button';
      var confirm = el('div', 'hl-confirm');
      confirm.hidden = true;
      confirm.setAttribute('inert', '');
      confirm.appendChild(el('span', null, '本当に却下しますか？'));
      var yes = el('button', 'hl-btn hl-btn-sm is-danger', '却下する');
      yes.type = 'button';
      yes.addEventListener('click', function () { decide('reject', note.value, yes); });
      var no = el('button', 'hl-btn hl-btn-sm', 'やめる');
      no.addEventListener('click', function () {
        confirm.hidden = true; confirm.setAttribute('inert', '');
      });
      confirm.appendChild(yes); confirm.appendChild(no);
      reject.addEventListener('click', function () {
        confirm.hidden = false; confirm.removeAttribute('inert');
      });
      box.appendChild(reject);
      box.appendChild(confirm);

      if (high > 0) {
        box.appendChild(el('p', 'hl-doc-note', '確認が必要な点が残っているため、承認は強調していません。'));
      }
    } else if (!IS_ADMIN) {
      box.appendChild(el('p', 'hl-doc-note', '判断するには管理者権限が必要です。'));
    } else {
      box.appendChild(el('p', 'hl-doc-note',
        'この報告書は「' + (STATUS_LABELS[report.status] || report.status) + '」です。'));
    }

    var out = el('div', 'hl-out');
    ['md', 'json'].forEach(function (fmt) {
      var a = el('a', 'hl-btn hl-btn-sm', fmt === 'md' ? 'Markdown' : 'JSON（証跡）');
      a.href = '/api/healing/reports/' + encodeURIComponent(state.reportId) + '/export?format=' + fmt;
      a.target = '_blank';
      a.rel = 'noopener';
      out.appendChild(a);
    });
    var print = el('a', 'hl-btn hl-btn-sm', '印刷 / PDF');
    print.href = '/healing/reports/' + encodeURIComponent(state.reportId) + '/print';
    print.target = '_blank';
    print.rel = 'noopener';
    out.appendChild(print);
    out.appendChild(el('p', 'hl-doc-note', '承認前でも下書きとして出力できます。承認欄は空のままです。'));
    box.appendChild(out);
  }

  function decide(action, note, button) {
    clearError();
    if (button) { button.disabled = true; }
    api('/api/healing/reports/' + encodeURIComponent(state.reportId) + '/decision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: action, note: note || '', actor: '' })
    }).then(function (data) {
      var r = data.report;
      var msg = action === 'approve'
        ? (r.pr_number ? '承認しました。PR #' + r.pr_number + ' を作成しました' : '承認しました')
        : action === 'return' ? '差し戻しました。修正をやり直します' : '却下しました';
      toast(msg);
      setTimeout(function () { window.location.href = '/healing'; }, 2000);
    }).catch(function (e) {
      if (button) { button.disabled = false; }
      showError(e.message);
    });
  }

  function loadDoc() {
    api('/api/healing/reports/' + encodeURIComponent(state.reportId))
      .then(renderDoc)
      .catch(function (e) {
        var doc = document.getElementById('hl-doc');
        if (doc) {
          doc.setAttribute('aria-busy', 'false');
          showState(doc, {
            kind: 'error', title: '報告書を読み込めませんでした', message: e.message,
            next: '一覧に戻って開き直すか、通信を確認してください。',
            actionLabel: '再読み込み', onAction: loadDoc
          }, '報告書を読み込めませんでした。');
        }
        showError(e.message);
      });
  }

  /* ---- 他ファイルへ公開 ---- */
  HL.blockersBox = blockersBox;
  HL.loadDoc = loadDoc;
  HL.section = section;
  HL.toast = toast;
})(window.HealingReports = window.HealingReports || {});
