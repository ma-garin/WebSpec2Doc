// AutoRun 実行条件の確定ダイアログ（案C）。
//
// 段階ごとの承認と「要確認」チェックリストを廃止し、実行を押した時点で
// **人が決めるべきことだけ**を2択で問う。推奨は選択済みで出すので、
// そのまま押せば実行できる。違う場合だけ選び直すか、自由入力で指示する。
//
// 「要確認」はシステム側の都合の名前だった。AIが自信の無さを申告しているだけで、
// 人から見れば確認事項ではなく自分が決めるべきことだった（利用者の指摘）。
(function () {
  'use strict';

  var state = {
    domain: '',
    jobId: '',
    decisions: [],
    facts: [],
    answers: {},   // decision_id -> {choice, text}
    busy: false,
    error: '',
  };

  function $(id) { return document.getElementById(id); }

  async function call(path, options) {
    var res = await fetch(path, options);
    var data = await res.json().catch(function () { return {}; });
    if (!res.ok) throw new Error(data.detail || data.error || '操作に失敗しました');
    return data;
  }

  function json(body) {
    return {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    };
  }

  // ---------------------------------------------------------------- 開閉

  async function open(domain, jobId) {
    if (!domain) return;
    state.domain = domain;
    state.jobId = jobId || '';
    state.error = '';
    try {
      var data = await call('/api/autorun/decisions?domain=' + encodeURIComponent(domain));
      state.decisions = data.decisions || [];
      state.facts = data.facts || [];
    } catch (e) {
      state.decisions = [];
      state.facts = [];
      state.error = e && e.message ? e.message : '実行条件を取得できませんでした';
    }
    // 既定は推奨。何も触らずに実行できる状態から始める。
    state.answers = {};
    state.decisions.forEach(function (d) {
      state.answers[d.decision_id] = { choice: d.recommended, text: '' };
    });
    render();
    var host = $('autorun-decisions');
    if (host) host.style.display = '';
  }

  function close() {
    var host = $('autorun-decisions');
    if (host) host.style.display = 'none';
  }

  // ---------------------------------------------------------------- 描画

  function choiceCard(decision, choice) {
    var answer = state.answers[decision.decision_id] || {};
    var selected = answer.choice === choice.key;

    var el = document.createElement('button');
    el.type = 'button';
    el.className = 'ard-choice' + (selected ? ' is-selected' : '');
    el.setAttribute('aria-pressed', selected ? 'true' : 'false');

    var lab = document.createElement('span');
    lab.className = 'ard-choice-label';

    var radio = document.createElement('span');
    radio.className = 'ard-radio';
    radio.setAttribute('aria-hidden', 'true');
    lab.appendChild(radio);

    var text = document.createElement('span');
    text.textContent = choice.label;
    lab.appendChild(text);

    if (choice.key === decision.recommended) {
      var tag = document.createElement('span');
      tag.className = 'ard-tag';
      tag.textContent = '推奨';
      lab.appendChild(tag);
    }
    el.appendChild(lab);

    var detail = document.createElement('span');
    detail.className = 'ard-choice-detail';
    detail.textContent = choice.detail;
    el.appendChild(detail);

    el.addEventListener('click', function () {
      state.answers[decision.decision_id] = {
        choice: choice.key,
        text: (state.answers[decision.decision_id] || {}).text || '',
      };
      state.error = '';
      render();
    });
    return el;
  }

  function decisionBlock(decision) {
    var box = document.createElement('section');
    box.className = 'ard-decision';

    var q = document.createElement('h4');
    q.className = 'ard-question';
    q.textContent = decision.question;
    box.appendChild(q);

    if (decision.context) {
      var ctx = document.createElement('p');
      ctx.className = 'ard-context';
      ctx.textContent = decision.context;
      box.appendChild(ctx);
    }

    var row = document.createElement('div');
    row.className = 'ard-choices';
    (decision.choices || []).forEach(function (c) {
      row.appendChild(choiceCard(decision, c));
    });
    box.appendChild(row);

    // 自由入力は「その選択肢を選んだとき」だけ出す。常時出すと2択が濁る。
    var answer = state.answers[decision.decision_id] || {};
    var chosen = (decision.choices || []).filter(function (c) {
      return c.key === answer.choice;
    })[0];
    if (chosen && chosen.needs_text) {
      var input = document.createElement('input');
      input.type = 'text';
      input.className = 'ard-text';
      input.placeholder = chosen.detail;
      input.value = answer.text || '';
      input.addEventListener('input', function () {
        state.answers[decision.decision_id] = { choice: answer.choice, text: input.value };
      });
      box.appendChild(input);
    }
    return box;
  }

  function render() {
    var body = $('autorun-decisions-body');
    if (!body) return;
    body.replaceChildren();

    if (!state.decisions.length) {
      var none = document.createElement('p');
      none.className = 'ard-context';
      none.textContent = '決めていただく条件はありません。このまま実行できます。';
      body.appendChild(none);
    }

    state.decisions.forEach(function (d) { body.appendChild(decisionBlock(d)); });

    // どちらとも違う場合の指示。2択に収まらない要望をここで受ける。
    var free = document.createElement('section');
    free.className = 'ard-decision';
    var freeQ = document.createElement('h4');
    freeQ.className = 'ard-question';
    freeQ.textContent = 'その他に指示があれば書いてください';
    free.appendChild(freeQ);
    var freeInput = document.createElement('input');
    freeInput.type = 'text';
    freeInput.id = 'autorun-decisions-note';
    freeInput.className = 'ard-text';
    freeInput.placeholder = '例: 決済画面は触らないで';
    free.appendChild(freeInput);
    body.appendChild(free);

    // 決めようがない前提は隠さず、事実として出す（質問にはしない）
    if (state.facts.length) {
      var facts = document.createElement('section');
      facts.className = 'ard-facts';
      var head = document.createElement('div');
      head.className = 'ard-facts-head';
      head.textContent = '選択の余地がない事実';
      facts.appendChild(head);
      state.facts.forEach(function (f) {
        var row = document.createElement('p');
        row.className = 'ard-fact';
        row.textContent = f.title + ' — ' + f.detail;
        facts.appendChild(row);
      });
      body.appendChild(facts);
    }

    // 未確認のまま実行できる以上、実行直前に「何が未確認のまま残るか」を出す。
    // ここで黙ると、成果物を見た人は「全部確認済み」と読む。
    var pending = _pendingReviewCount();
    if (pending > 0) {
      var warn = document.createElement('section');
      warn.className = 'ard-unverified';
      warn.setAttribute('role', 'note');
      var wh = document.createElement('div');
      wh.className = 'ard-facts-head';
      wh.textContent = '未確認のまま実行されます';
      warn.appendChild(wh);
      var wp = document.createElement('p');
      wp.className = 'ard-fact';
      wp.textContent = '要確認 ' + pending + ' 件が未チェックです。'
        + 'このまま実行すると「人の確認を経ていない」と成果物に記録されます。';
      warn.appendChild(wp);
      body.appendChild(warn);
    }

    var err = $('autorun-decisions-error');
    if (err) {
      err.textContent = state.error || '';
      err.style.display = state.error ? '' : 'none';
    }
    var go = $('autorun-decisions-go');
    if (go) go.disabled = state.busy;
  }

  // 要確認の残件数。レビューモジュールが未初期化なら 0 として扱う（警告を出さない）。
  function _pendingReviewCount() {
    var r = window.autorunReview;
    if (!r || typeof r.pendingCount !== 'function') return 0;
    try { return Number(r.pendingCount() || 0); } catch (e) { return 0; }
  }

  // ---------------------------------------------------------------- 確定

  async function submit() {
    if (state.busy) return;
    state.busy = true;
    state.error = '';
    render();
    try {
      var note = $('autorun-decisions-note');
      var payload = {
        domain: state.domain,
        job_id: state.jobId,
        answers: state.answers,
        note: note ? note.value : '',
      };
      await call('/api/autorun/decisions', json(payload));
      close();
      if (window.autorunStages && window.autorunStages.load) {
        await window.autorunStages.load(state.domain);
      }
    } catch (e) {
      state.error = e && e.message ? e.message : '実行条件を確定できませんでした';
    } finally {
      state.busy = false;
      render();
    }
  }

  function boot() {
    var go = $('autorun-decisions-go');
    if (go) go.addEventListener('click', submit);
    var back = $('autorun-decisions-back');
    if (back) back.addEventListener('click', close);
    var scrim = $('autorun-decisions-scrim');
    if (scrim) scrim.addEventListener('click', close);
    document.addEventListener('keydown', function (e) {
      var host = $('autorun-decisions');
      if (e.key === 'Escape' && host && host.style.display !== 'none') close();
    });
  }

  window.autorunDecisions = { open: open, close: close };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
