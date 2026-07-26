// AutoRun 要確認チェックリスト。
//
// AutoRun は既定で自律的に成果物を作る。人は全項目を承認するのではなく、
// **AI 由来（LLM 提案・前提）または高リスク**の項目だけをこのリストで確認する。
// 実測 × 低〜中リスクの項目は「自動承認」に畳み込み、必要なときだけ開く。
(function () {
  'use strict';

  var state = { domain: '', entries: [], counts: null, busy: false, showAuto: false };

  function $(id) { return document.getElementById(id); }
  function root() { return $('autorun-review'); }

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

  function reviewEntries() {
    return state.entries.filter(function (e) { return e.needs_review; });
  }

  function autoEntries() {
    return state.entries.filter(function (e) { return !e.needs_review; });
  }

  // ---------------------------------------------------------------- 部品

  function badge(cls, text, title) {
    var b = document.createElement('span');
    b.className = 'arv-badge ' + cls;
    b.textContent = text;
    if (title) b.title = title;
    return b;
  }

  function button(text, onClick, cls) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = cls || 'btn-outline-sm';
    b.textContent = text;
    b.addEventListener('click', onClick);
    return b;
  }

  // 進捗。「あと何件見ればよいか」を最初に示す。
  function renderProgress() {
    var counts = state.counts || { review: 0, review_done: 0, auto: 0 };
    var wrap = document.createElement('div');
    wrap.className = 'arv-progress';

    var head = document.createElement('div');
    head.className = 'arv-progress-head';

    var label = document.createElement('span');
    label.className = 'arv-progress-label';
    label.textContent = counts.review
      ? '要確認 ' + counts.review_done + ' / ' + counts.review + ' 件'
      : '要確認はありません';
    head.appendChild(label);

    var note = document.createElement('span');
    note.className = 'arv-progress-note';
    note.textContent = '実測・低リスクの ' + counts.auto + ' 件は自動承認';
    head.appendChild(note);
    wrap.appendChild(head);

    var bar = document.createElement('div');
    bar.className = 'arv-bar';
    bar.setAttribute('role', 'progressbar');
    bar.setAttribute('aria-valuemin', '0');
    bar.setAttribute('aria-valuemax', String(counts.review || 0));
    bar.setAttribute('aria-valuenow', String(counts.review_done || 0));
    var fill = document.createElement('i');
    var pct = counts.review ? Math.round((counts.review_done / counts.review) * 100) : 100;
    fill.style.width = pct + '%';
    bar.appendChild(fill);
    wrap.appendChild(bar);
    return wrap;
  }

  // チェックリストの1行。チェック＝承認。根拠は「なぜ人が見るのか」を必ず添える。
  function row(entry) {
    var el = document.createElement('div');
    el.className = 'arv-row is-' + entry.confidence + (entry.approved ? ' is-approved' : '');

    var box = document.createElement('input');
    box.type = 'checkbox';
    box.className = 'arv-check';
    box.checked = !!entry.approved;
    box.disabled = state.busy;
    box.setAttribute(
      'aria-label',
      entry.title + ' を承認'
    );
    box.addEventListener('change', function () {
      setApproval(entry, box.checked);
    });
    el.appendChild(box);

    var body = document.createElement('div');
    body.className = 'arv-body';

    var head = document.createElement('div');
    head.className = 'arv-row-head';
    var title = document.createElement('span');
    title.className = 'arv-title';
    title.textContent = entry.title;
    head.appendChild(title);
    head.appendChild(badge('is-' + entry.confidence, entry.confidence_label));
    if (entry.risk === 'high') head.appendChild(badge('is-risk', '高リスク'));
    var stage = document.createElement('span');
    stage.className = 'arv-stage';
    stage.textContent = entry.stage_name;
    head.appendChild(stage);
    body.appendChild(head);

    if (entry.detail) {
      var detail = document.createElement('p');
      detail.className = 'arv-detail';
      detail.textContent = entry.detail;
      body.appendChild(detail);
    }

    var reason = document.createElement('p');
    reason.className = 'arv-reason is-' + entry.confidence;
    reason.textContent = entry.reason;
    body.appendChild(reason);
    el.appendChild(body);

    var actions = document.createElement('div');
    actions.className = 'arv-actions';
    actions.appendChild(
      button('アシスタントに相談', function () { askAssistant(entry); }, 'btn-outline-sm')
    );
    el.appendChild(actions);
    return el;
  }

  function askAssistant(entry) {
    // アシスタントは常駐しないので、相談対象を渡して開く
    if (window.autorunChat && window.autorunChat.open) {
      window.autorunChat.open({ title: entry.title, detail: entry.detail });
    }
    var input = $('autorun-chat-input');
    if (!input) return;
    input.value =
      '次の項目を確認したい。根拠が十分か、他に見るべき観点があるか教えてください:\n'
      + entry.title + '\n' + entry.detail;
    input.focus();
  }

  function message(text) {
    var p = document.createElement('p');
    p.className = 'arv-empty';
    p.textContent = text;
    return p;
  }

  // 自動承認ぶんは既定で畳む。「勝手に通した」を隠さないため件数と開閉は常に出す。
  function renderAuto() {
    var items = autoEntries();
    var wrap = document.createElement('section');
    wrap.className = 'arv-auto';
    if (!items.length) return wrap;

    var head = document.createElement('button');
    head.type = 'button';
    head.className = 'arv-auto-head';
    head.setAttribute('aria-expanded', state.showAuto ? 'true' : 'false');
    head.textContent =
      (state.showAuto ? '▾ ' : '▸ ') + '自動承認された ' + items.length + ' 件（実測・低リスク）';
    head.addEventListener('click', function () {
      state.showAuto = !state.showAuto;
      render();
    });
    wrap.appendChild(head);

    if (state.showAuto) {
      var list = document.createElement('div');
      list.className = 'arv-auto-list';
      items.forEach(function (entry) {
        var line = document.createElement('div');
        line.className = 'arv-auto-row';
        var t = document.createElement('span');
        t.className = 'arv-auto-title';
        t.textContent = entry.title;
        line.appendChild(t);
        line.appendChild(badge('is-' + entry.confidence, entry.confidence_label));
        var st = document.createElement('span');
        st.className = 'arv-auto-stage';
        st.textContent = entry.stage_name;
        line.appendChild(st);
        list.appendChild(line);
      });
      wrap.appendChild(list);
    }
    return wrap;
  }

  // ---------------------------------------------------------------- 描画

  function render() {
    var host = root();
    if (!host) return;
    host.replaceChildren();
    if (!state.entries.length) {
      host.style.display = 'none';
      return;
    }
    host.style.display = '';

    var head = document.createElement('header');
    head.className = 'arv-head';
    var kicker = document.createElement('div');
    kicker.className = 'section-kicker';
    kicker.textContent = '要確認';
    head.appendChild(kicker);
    var lead = document.createElement('p');
    lead.className = 'arv-lead';
    lead.textContent =
      'AI が作った下書きのうち、根拠が弱い項目と影響の大きい項目だけを確認します。'
      + 'チェックすると承認され、確定版に含まれます。';
    head.appendChild(lead);
    host.appendChild(head);

    host.appendChild(renderProgress());

    var items = reviewEntries();
    if (!items.length) {
      host.appendChild(message('人が確認すべき項目はありません。すべて実測に基づいています。'));
    } else {
      var list = document.createElement('div');
      list.className = 'arv-list';
      items.forEach(function (entry) { list.appendChild(row(entry)); });
      host.appendChild(list);
    }

    host.appendChild(renderAuto());
    host.appendChild(renderFooter());
  }

  function renderFooter() {
    var counts = state.counts || { review_pending: 0 };
    var bar = document.createElement('div');
    bar.className = 'arv-foot';

    var note = document.createElement('span');
    note.className = 'arv-foot-note';
    note.textContent = counts.review_pending
      ? '未確認が ' + counts.review_pending + ' 件あります。すべて確認すると確定できます。'
      : 'すべて確認済みです。確定できます。';
    bar.appendChild(note);

    var confirm = button('確定する', signOff, 'btn-primary');
    confirm.disabled = state.busy || !!counts.review_pending;
    bar.appendChild(confirm);
    return bar;
  }

  function renderError(messageText) {
    var host = root();
    if (!host) return;
    var err = document.createElement('div');
    err.className = 'arv-error';
    err.setAttribute('role', 'alert');
    err.textContent = messageText;
    host.appendChild(err);
    // 一覧が長いと失敗理由が画面外に出る。見える位置まで運ぶ。
    if (err.scrollIntoView) err.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }

  // ---------------------------------------------------------------- 操作

  async function withBusy(fn) {
    if (state.busy) return;
    state.busy = true;
    render();
    try {
      await fn();
    } catch (e) {
      renderError(e && e.message ? e.message : '操作に失敗しました');
      return;
    } finally {
      state.busy = false;
    }
    render();
  }

  function setApproval(entry, approved) {
    return withBusy(async function () {
      await call('/api/autorun/stages/item', json({
        domain: state.domain,
        stage_id: entry.stage_id,
        item_id: entry.item_id,
        approved: approved,
      }));
      await refresh();
    });
  }

  function signOff() {
    return withBusy(async function () {
      // 「確定する」は、対象になっている段階そのものを承認する。
      // 以前はここで表示を更新するだけで承認 API を呼んでおらず、項目は承認済み
      // なのに段階は未承認のまま残っていた。その結果、後段の
      // 「承認を確定して実行する」が 409（未承認の段階があります）で弾かれ、
      // 利用者からは「押しても何も起きない」状態になっていた（実測で発覚）。
      var seen = {};
      var stageIds = [];
      state.entries.forEach(function (e) {
        if (e.stage_id && !seen[e.stage_id]) { seen[e.stage_id] = true; stageIds.push(e.stage_id); }
      });

      var failed = [];
      for (var i = 0; i < stageIds.length; i++) {
        try {
          await call('/api/autorun/stages/approve', json({
            domain: state.domain,
            stage_id: stageIds[i],
          }));
        } catch (e) {
          // 承認できない段階（項目未承認など）は握り潰さず、理由を残す
          failed.push(stageIds[i] + '（' + (e && e.message ? e.message : '失敗') + '）');
        }
      }

      // 段階の状態はサーバが正。承認後は必ず読み直し、画面と乖離させない。
      if (window.autorunStages && window.autorunStages.load) {
        await window.autorunStages.load(state.domain);
      } else if (window.autorunStages && window.autorunStages.render) {
        window.autorunStages.render();
      }

      if (failed.length) {
        throw new Error('承認できなかった段階があります: ' + failed.join(' / '));
      }
      var counts = state.counts || {};
      renderConfirmed(counts);
    });
  }

  function renderConfirmed(counts) {
    var host = root();
    if (!host) return;
    var box = document.createElement('div');
    box.className = 'arv-confirmed';
    box.textContent =
      '確定しました。確認 ' + (counts.review || 0) + ' 件 / 自動承認 '
      + (counts.auto || 0) + ' 件。記録はアクティビティログに残ります。';
    host.appendChild(box);
  }

  async function refresh() {
    var data = await call('/api/autorun/review-queue?domain=' + encodeURIComponent(state.domain));
    state.entries = data.entries || [];
    state.counts = data.counts || null;
  }

  async function load(domain) {
    if (!domain) return;
    state.domain = domain;
    try {
      await refresh();
      // 初回は自動承認の対象をまとめて通し、人が見る対象だけを残す
      var counts = state.counts || {};
      if (counts.auto && counts.approved < counts.auto) {
        var res = await call('/api/autorun/review-queue/auto-approve', json({ domain: domain }));
        state.entries = res.entries || state.entries;
        state.counts = res.counts || state.counts;
      }
      render();
    } catch (e) {
      state.entries = [];
      state.counts = null;
      render();
    }
  }

  window.autorunReview = {
    load: load,
    render: render,
    hide: function () {
      var host = root();
      if (host) host.style.display = 'none';
    },
  };
})();
