// CLI モードの案内ページ。実行はせず、貼り付けられるコマンドを組み立てるだけ。
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
    ['url', 'domain', 'depth', 'max'].forEach((k) => {
      const el = $(`cli-${k}-field`);
      if (el) el.classList.toggle('cli-hidden', !use.includes(k));
    });

    const parts = ['python', 'src/cli.py', cmd];
    if (use.includes('url') && $('cli-url').value) parts.push('--url', shellQuote($('cli-url').value));
    if (use.includes('domain') && $('cli-domain').value) parts.push('--domain', shellQuote($('cli-domain').value));
    if (use.includes('depth') && $('cli-depth').value) parts.push('--depth', $('cli-depth').value);
    if (use.includes('max') && $('cli-max').value) {
      // ドキュメント作成側のフラグ名は本体 CLI に合わせる
      parts.push('--max-pages', $('cli-max').value);
    }
    if ($('cli-json').checked) parts.push('--json');
    out.textContent = parts.join(' ');
  }

  ['cli-cmd', 'cli-url', 'cli-domain', 'cli-depth', 'cli-max', 'cli-json'].forEach((id) => {
    const el = $(id);
    if (el) el.addEventListener(el.tagName === 'SELECT' || el.type === 'checkbox' ? 'change' : 'input', build);
  });

  $('cli-copy')?.addEventListener('click', (e) => {
    const btn = e.currentTarget;
    navigator.clipboard.writeText(out.textContent).then(() => {
      const orig = btn.textContent;
      btn.textContent = 'コピーしました';
      setTimeout(() => { btn.textContent = orig; }, 1500);
    }).catch(() => {
      // クリップボードが使えない環境でも、何が起きたか分かるようにする
      btn.textContent = 'コピーできません（手で選択してください）';
    });
  });

  build();
})();
