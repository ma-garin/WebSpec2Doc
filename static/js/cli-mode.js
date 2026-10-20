// CLI / API の案内ページ。実行はせず、貼り付けられるコマンドを組み立てるだけ。
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const cmdSel = $('cli-cmd');
  const out = $('cli-command');
  if (!cmdSel || !out) return;

  // どの入力欄を使うかはコマンドごとに違う。使わない欄を出したままにすると、
  // 指定したのに効いていないという誤解を生むため隠す。
  const FIELDS = {
    doc:        ['url', 'depth', 'max'],
    autorun:    ['url', 'depth', 'max'],
    test:       ['domain'],
    ci:         ['domain', 'failon'],
    sites:      [],
    show:       ['domain'],
    viewpoints: [],
  };

  function shellQuote(v) {
    // 空白や記号を含む値をそのまま貼り付けても壊れないようにする
    return /^[A-Za-z0-9._:\/-]+$/.test(v) ? v : `'${String(v).replace(/'/g, "'\\''")}'`;
  }

  function build() {
    const cmd = cmdSel.value;
    const use = FIELDS[cmd] || [];
    ['url', 'domain', 'depth', 'max', 'failon'].forEach((k) => {
      const el = $(`cli-${k}-field`);
      if (el) el.classList.toggle('cli-hidden', !use.includes(k));
    });

    const parts = ['python', 'src/cli.py', cmd];
    if (cmd === 'ci') parts.push('gate');
    if (use.includes('url') && $('cli-url').value) parts.push('--url', shellQuote($('cli-url').value));
    if (use.includes('domain') && $('cli-domain').value) parts.push('--domain', shellQuote($('cli-domain').value));
    if (use.includes('depth') && $('cli-depth').value) parts.push('--depth', $('cli-depth').value);
    if (use.includes('max') && $('cli-max').value) {
      // ドキュメント作成側のフラグ名は本体 CLI に合わせる
      parts.push('--max-pages', $('cli-max').value);
    }
    if (use.includes('failon') && $('cli-failon').value) parts.push('--fail-on', $('cli-failon').value);
    if ($('cli-json').checked) parts.push('--json');
    out.textContent = parts.join(' ');
    check(use);
  }

  // 入力の不足は「動かないコマンド」をコピーさせない。注意（ローカル URL・未解析のサイト）はコピーを止めない。
  const KNOWN = Array.prototype.map.call(document.querySelectorAll('#cli-domains option'), (o) => o.value);
  const LOCAL = /^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|0\.0\.0\.0|\[?::1\]?)/i;
  function check(use) {
    const box = $('cli-check');
    const copy = $('cli-copy');
    let error = '';
    let note = '';
    if (use.includes('url')) {
      const v = $('cli-url').value.trim();
      let u = null;
      try { u = new URL(v); } catch (e) { u = null; }
      if (!v) error = '対象 URL を入れてください。URL が無いコマンドは端末で失敗します。';
      else if (!u || (u.protocol !== 'http:' && u.protocol !== 'https:')) error = '対象 URL は http:// か https:// で始めてください。';
      else if (LOCAL.test(u.hostname)) note = 'ローカル・社内の URL は既定で解析しません。対象にするときは端末で先頭に WEBSPEC2DOC_ALLOW_LOCAL=1 を付けて実行してください（この画面では付けません）。';
    }
    if (!error && use.includes('domain')) {
      const d = $('cli-domain').value.trim();
      if (!d) error = '対象サイトを入れてください（例: example.com）。';
      else if (KNOWN.length && KNOWN.indexOf(d) < 0) note = 'このサーバの解析済みサイトにはありません。端末側の出力先にあるかは未確認です。';
    }
    if (copy) {
      copy.disabled = !!error;
      copy.title = error ? 'コマンドが未完成のためコピーできません' : '';
    }
    out.classList.toggle('is-incomplete', !!error);
    if (!box) return;
    box.hidden = !(error || note);
    box.className = 'cli-check' + (error ? ' cli-check--error' : (note ? ' cli-check--note' : ''));
    box.textContent = error ? '× 未完成: ' + error : (note ? '! 注意: ' + note : '');
  }

  ['cli-cmd', 'cli-url', 'cli-domain', 'cli-depth', 'cli-max', 'cli-failon', 'cli-json'].forEach((id) => {
    const el = $(id);
    if (el) el.addEventListener(el.tagName === 'SELECT' || el.type === 'checkbox' ? 'change' : 'input', build);
  });

  function selectCommand() {
    // クリップボードが使えないときは、手でコピーできるよう選択状態にする
    const sel = window.getSelection && window.getSelection();
    if (!sel) return;
    const r = document.createRange();
    r.selectNodeContents(out);
    sel.removeAllRanges();
    sel.addRange(r);
    out.classList.add('is-selected');
  }

  function notify(msg, kind) {
    if (window.WS2D && window.WS2D.toast) window.WS2D.toast(msg, kind);
  }

  $('cli-copy')?.addEventListener('click', () => {
    if ($('cli-copy').disabled) return;
    const text = out.textContent;
    const fail = () => { selectCommand(); notify('コピーできませんでした。手動でコピーしてください', 'warning'); };
    if (!navigator.clipboard || !navigator.clipboard.writeText) { fail(); return; }
    navigator.clipboard.writeText(text).then(() => {
      out.classList.remove('is-selected');
      notify('コピーしました（端末に貼り付けて実行してください）', 'success');
    }).catch(fail);
  });

  build();
})();
