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
