// AutoRun 右パネルの QA アシスタント（LLM チャット）。
//
// 各段階の成果物について相談・修正を依頼するための常設パネル。
// LLM は補助であり、到達できない場合はその旨を正直に表示する。
// AutoRun の実行自体はチャットの可否に依存しない。
(function () {
  'use strict';

  var MAX_HISTORY = 8;
  //: フェーズごとに会話を分ける。文脈が混ざると助言が的外れになる。
  var histories = {};
  var phase = { key: 'intake', label: '受付' };
  var sending = false;

  // フェーズ別の定型チップ。そのフェーズで実際に効く問いだけを出す。
  var PRESETS = {
    intake: ['この範囲で妥当か', '認証が要るサイトの扱い'],
    test_objective: ['この対象に適した目的は', '不要な目的はどれか'],
    test_plan: ['この前提で妥当か', '抜けている前提は', '合否基準の考え方'],
    features: ['粒度は適切か', '分割漏れは'],
    viewpoints: ['漏れている観点は', 'この画面特有のリスク'],
    basic_design: ['この観点に適した技法は', '技法の選択は妥当か'],
    detail_design: ['確認内容は十分か', '異常系の観点'],
    test_cases: ['境界値の具体値は', '期待結果を具体化'],
    playwright_automation: ['未自動化の扱い', 'flaky を避けるには'],
    running: ['この失敗の原因は', 'flaky か本物か'],
  };

  function currentHistory() {
    if (!histories[phase.key]) histories[phase.key] = [];
    return histories[phase.key];
  }

  function $(id) { return document.getElementById(id); }

  function currentContext() {
    return phase.label;
  }

  function syncContextLabel() {
    var label = $('autorun-chat-context');
    if (label) label.textContent = phase.label;
  }

  // フェーズが変わったら、見出し・チップ・会話履歴を切り替える
  function setPhase(next) {
    if (!next || !next.key || next.key === phase.key) return;
    phase = { key: next.key, label: next.label || next.key };
    syncContextLabel();
    renderPresets();
    renderHistory();
  }

  function renderPresets() {
    var host = $('autorun-chat-presets');
    if (!host) return;
    host.replaceChildren();
    (PRESETS[phase.key] || []).forEach(function (text) {
      var chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'autorun-chat-chip';
      chip.textContent = text;
      chip.addEventListener('click', function () { send(text); });
      host.appendChild(chip);
    });
  }

  // このフェーズの会話だけを描き直す
  function renderHistory() {
    var log = $('autorun-chat-log');
    if (!log) return;
    log.replaceChildren();
    var entries = currentHistory();
    if (!entries.length) {
      var empty = document.createElement('p');
      empty.className = 'autorun-chat-lead';
      empty.textContent = 'このフェーズの内容について相談できます。';
      log.appendChild(empty);
      return;
    }
    entries.forEach(function (e) {
      var node = document.createElement('div');
      node.className = 'autorun-chat-msg autorun-chat-msg-' + e.role;
      node.textContent = e.content;
      log.appendChild(node);
    });
    log.scrollTop = log.scrollHeight;
  }

  function appendMessage(role, text) {
    var log = $('autorun-chat-log');
    if (!log) return null;
    var empty = log.querySelector('.autorun-chat-lead');
    if (empty) empty.remove();

    var node = document.createElement('div');
    node.className = 'autorun-chat-msg autorun-chat-msg-' + role;
    node.textContent = text; // LLM/利用者いずれの文字列もテキストとしてのみ扱う
    log.appendChild(node);
    log.scrollTop = log.scrollHeight;
    return node;
  }

  function setStatus(text) {
    var el = $('autorun-chat-status');
    if (el) el.textContent = text || '';
  }

  function setSending(on) {
    sending = on;
    var btn = $('autorun-chat-send');
    var input = $('autorun-chat-input');
    if (btn) { btn.disabled = on; btn.textContent = on ? '送信中…' : '送信'; }
    if (input) input.disabled = on;
    setStatus(on ? '応答を待っています…' : '');
  }

  async function send(text) {
    var message = (text || '').trim();
    if (!message || sending) return;

    var input = $('autorun-chat-input');
    if (input) input.value = '';

    appendMessage('user', message);
    currentHistory().push({ role: 'user', content: message });
    setSending(true);

    try {
      var res = await fetch('/api/llm/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: message,
          context: currentContext(),
          history: currentHistory().slice(-MAX_HISTORY),
        }),
      });
      var data = await res.json().catch(function () { return {}; });

      if (!res.ok) {
        var detail = data.detail ? '\n' + data.detail : '';
        appendMessage('error', (data.error || 'QAアシスタントを利用できませんでした。') + detail);
        return;
      }

      var reply = data.reply || '';
      appendMessage('assistant', reply);
      currentHistory().push({ role: 'assistant', content: reply });
      if (data.model) setStatus(data.model);
    } catch (e) {
      appendMessage('error', 'QAアシスタントへの通信に失敗しました。AutoRun の実行には影響しません。');
    } finally {
      setSending(false);
    }
  }

  function boot() {
    var form = $('autorun-chat-form');
    var input = $('autorun-chat-input');
    if (!form || !input) return;

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      send(input.value);
    });

    // Enter で送信 / Shift+Enter で改行
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        send(input.value);
      }
    });

    syncContextLabel();
    renderPresets();
    renderHistory();
  }

  window.autorunChat = { setPhase: setPhase };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
