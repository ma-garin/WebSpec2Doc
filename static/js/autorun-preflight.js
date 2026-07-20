// AutoRun 着手前プレフライト。
//
// URL を入力した時点で「浅い探索」を走らせ、開始を押す前に
// 到達可否 / ログイン要否の気配 / 発見画面数の概算 を提示する。
//
// 重要な前提:
// - これは **参考値** であり、本実行の観測結果ではない。claim_scope を汚さない。
// - 発見 0 件は「サイトが壊れている」ことを意味しない。到達できなかった事実のみを述べる。
// - 開始を妨げない。プレフライトが失敗しても本実行は可能。
(function () {
  'use strict';

  var PREFLIGHT_DEPTH = '1';
  var PREFLIGHT_MAX_PAGES = '8';
  var DEBOUNCE_MS = 600;
  var SAMPLE_SHOWN = 3;

  var timer = null;
  var reader = null;
  var runId = '';
  var seq = 0; // 応答の取り違え防止（古い応答を捨てる）

  function el() {
    return document.getElementById('autorun-preflight');
  }

  // 本文は自前の静的HTMLのみ。対象サイト由来の文字列（画面タイトル等）は
  // innerHTML に載せず、必ず textContent で差し込む（XSS 防止）。
  function render(html, state, untrustedItems) {
    var box = el();
    if (!box) return;
    box.innerHTML = html;
    box.className = 'autorun-preflight' + (state ? ' is-' + state : '');
    if (untrustedItems && untrustedItems.length) {
      var list = document.createElement('ul');
      list.className = 'autorun-preflight-list';
      untrustedItems.forEach(function (text) {
        var li = document.createElement('li');
        li.textContent = text; // 対象サイト由来 — テキストとしてのみ扱う
        list.appendChild(li);
      });
      var anchor = box.querySelector('[data-preflight-list]');
      if (anchor) anchor.replaceWith(list);
      else box.appendChild(list);
    }
    box.hidden = false;
  }

  function hide() {
    var box = el();
    if (!box) return;
    box.hidden = true;
    box.innerHTML = '';
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  async function cancelInFlight() {
    if (timer) { clearTimeout(timer); timer = null; }
    if (reader) {
      try { await reader.cancel(); } catch (e) { /* 既に閉じている */ }
      reader = null;
    }
    if (runId) {
      var id = runId;
      runId = '';
      try {
        await fetch('/api/cancel', { method: 'POST', body: new URLSearchParams({ run_id: id }) });
      } catch (e) { /* 中断できなくても実害はない */ }
    }
  }

  function looksLikeUrl(value) {
    if (!/^https?:\/\//i.test(value)) return false;
    try { return !!new URL(value).hostname; } catch (e) { return false; }
  }

  function looksLikeLoginWall(pages, url) {
    if (pages.length > 0) return false;
    return /login|signin|sign-in|auth|account/i.test(url);
  }

  function summarize(pages, url, truncated) {
    if (pages.length === 0) {
      if (looksLikeLoginWall(pages, url)) {
        return {
          state: 'warn',
          html:
            '<strong>ログインが必要な可能性があります。</strong>' +
            '画面を検出できませんでした。認証が要る場合は「詳細オプション」で設定してください。' +
            '<small>この結果は浅い事前確認によるものです。開始は可能です。</small>',
        };
      }
      return {
        state: 'warn',
        html:
          '<strong>画面を検出できませんでした。</strong>' +
          'URL の誤りか、ログインや robots.txt による制限が考えられます。' +
          '<small>「検出できなかった」という事実のみで、サイトの不具合を意味しません。開始は可能です。</small>',
      };
    }

    var sample = pages.slice(0, SAMPLE_SHOWN).map(function (p) {
      return String(p.title || p.url || '');
    });

    var count = truncated ? pages.length + '画面以上' : pages.length + '画面';
    return {
      state: 'ok',
      items: sample,
      html:
        '<strong>到達できました。' + count + 'を確認。</strong>' +
        '<div data-preflight-list></div>' +
        '<small>浅い事前確認（深さ ' + PREFLIGHT_DEPTH + ' / 最大 ' + PREFLIGHT_MAX_PAGES +
        '画面）の参考値です。本実行の対象範囲とは異なります。</small>',
    };
  }

  async function runPreflight(url) {
    var mySeq = ++seq;
    render('<span class="autorun-preflight-spin"></span>到達できるか確認しています…', 'busy');

    var pages = [];
    try {
      var body = new URLSearchParams({
        url: url,
        depth: PREFLIGHT_DEPTH,
        max_pages: PREFLIGHT_MAX_PAGES,
      });
      var res = await fetch('/api/discover-stream', { method: 'POST', body: body });
      if (!res.ok || !res.body) throw new Error('事前確認を実行できませんでした');

      reader = res.body.getReader();
      var decoder = new TextDecoder();
      var buf = '';
      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;
        if (mySeq !== seq) return; // 新しい入力に追い越された
        buf += decoder.decode(chunk.value, { stream: true });
        var parts = buf.split('\n\n');
        buf = parts.pop() || '';
        for (var i = 0; i < parts.length; i++) {
          var line = parts[i].replace(/^data:\s?/, '').trim();
          if (!line) continue;
          var obj;
          try { obj = JSON.parse(line); } catch (e) { continue; }
          if (obj.run_id) {
            runId = obj.run_id;
          } else if (obj.page) {
            pages.push(obj.page);
          } else if (obj.error) {
            throw new Error(obj.error);
          }
        }
      }
      if (mySeq !== seq) return;
      var truncated = pages.length >= Number(PREFLIGHT_MAX_PAGES);
      var out = summarize(pages, url, truncated);
      render(out.html, out.state, out.items);
    } catch (e) {
      if (mySeq !== seq) return;
      render(
        '<strong>事前確認できませんでした。</strong>' + esc(e && e.message ? e.message : '') +
        '<small>事前確認の失敗であり、対象サイトの不具合を意味しません。開始は可能です。</small>',
        'warn'
      );
    } finally {
      reader = null;
      runId = '';
    }
  }

  function boot() {
    var input = document.getElementById('autorun-url');
    var button = document.getElementById('autorun-preflight-btn');
    if (!input || !button) return;

    // URL を打っただけでは対象サイトへアクセスしない。明示操作でのみ実行する。
    button.addEventListener('click', function () {
      var url = (input.value || '').trim();
      cancelInFlight();
      seq++;
      if (!url) {
        render('<strong>URL を入力してください。</strong>', 'warn');
        return;
      }
      if (!looksLikeUrl(url)) {
        render('<strong>URL の形式が正しくありません。</strong>http:// または https:// で始まる URL を入力してください。', 'warn');
        return;
      }
      runPreflight(url);
    });

    // URL を書き換えたら、前の確認結果は当てにならないので取り下げる
    input.addEventListener('input', function () {
      cancelInFlight();
      seq++;
      hide();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
