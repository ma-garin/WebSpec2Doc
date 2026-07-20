// AutoRun 右パネルの QA アシスタント（LLM チャット）。
//
// 各段階の成果物について相談・修正を依頼するための常設パネル。
// LLM は補助であり、到達できない場合はその旨を正直に表示する。
// AutoRun の実行自体はチャットの可否に依存しない。
(function () {
  'use strict';

  var MAX_HISTORY = 8;
  var history = [];
  var sending = false;

  function $(id) { return document.getElementById(id); }

  function currentContext() {
    // 実行中はコックピットの表示中フェーズを、待機中は「受付」を文脈として渡す
    var steps = $('autorun-steps');
    if (steps && steps.style.display !== 'none') {
      var phase = $('autorun-phase-label');
      var text = phase && phase.textContent ? phase.textContent.trim() : '';
      return text || '実行中';
    }
    return '受付';
  }

  function syncContextLabel() {
    var label = $('autorun-chat-context');
    if (label) label.textContent = currentContext();
  }

  function appendMessage(role, text) {
    var log = $('autorun-chat-log');
    if (!log) return null;
    var empty = $('autorun-chat-empty');
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
    history.push({ role: 'user', content: message });
    setSending(true);

    try {
      var res = await fetch('/api/llm/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: message,
          context: currentContext(),
          history: history.slice(-MAX_HISTORY),
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
      history.push({ role: 'assistant', content: reply });
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

    // 定型の相談チップ
    document.querySelectorAll('[data-chat-preset]').forEach(function (chip) {
      chip.addEventListener('click', function () {
        send(chip.getAttribute('data-chat-preset'));
      });
    });

    syncContextLabel();
    // 実行フェーズの変化に合わせて文脈表示を更新する
    var phase = $('autorun-phase-label');
    if (phase && window.MutationObserver) {
      new MutationObserver(syncContextLabel).observe(phase, {
        childList: true,
        characterData: true,
        subtree: true,
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
