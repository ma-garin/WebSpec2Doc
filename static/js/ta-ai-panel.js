// ---- テスト活動支援 / AIと相談パネル ----
// 右下の浮遊ボタンから、既存画面に「重ねて」開くチャット。画面本体のレイアウトは動かさない。
//
// 設計上の約束:
//  1. AI は画面を勝手に書き換えない。提案を出し、人がボタンを押して初めて反映する。
//  2. 反映できる操作は工程ごとに registerAction() で登録する。共通の reply() に
//     工程別の分岐を足していくと、工程が増えるたびに分岐が肥大するため。
(function () {
  'use strict';

  const MAX_HISTORY = 12;   // 送信する会話履歴の上限（トークンと応答時間の抑制）

  // 工程ごとの質問候補。何を聞けばよいか分からない状態で放置しない。
  const SUGGESTIONS = {
    'test-plan': ['リスクの抜けを点検して', '終了基準は妥当？', '工数見積の根拠を説明して'],
    'test-analysis': ['条件の抜け漏れを観点と突き合わせて点検して', '未対応の要求への条件案を出して', '因子に追加すべき水準は？'],
    'test-strategy': ['デシジョンテーブルの簡約はできる？', 'ペアワイズの組合せ数を減らしたい', '追加すべき状態遷移は？'],
    'test-design': ['自動化不可のケースだけ抽出して', 'このケースの期待結果を具体化して', 'テストデータの作り方を提案して'],
    'test-implementation': ['Page Object の構成を提案して', '生成コードのレビュー観点は？', 'flaky になりにくい待ち方は？'],
    'test-execution': ['失敗の共通原因を分析して', 'flaky 疑いは隔離すべき？', '実行時間を短縮したい'],
    'manual-execution': ['残りの実施順を提案して', 'ブロック時の扱いを教えて', '証跡はどこまで必要？'],
    'defect-analysis': ['混入工程の偏りの理由は？', 'Why 1 の下書きを作って', '再テストの優先順位は？'],
    'code-fix': ['この差分の回帰リスクは？', '影響範囲のケース選定は妥当？', 'コミットメッセージ案を出して'],
    'test-completion': ['未達の基準を満たす最短の道筋は？', '完了レポートに何を書くべき？', '教訓の書き方を教えて'],
    'test-activity': ['今どの工程から始めるべき？', '対応中の不具合の傾向を教えて', 'この画面の使い方を教えて'],
    'integrations': ['GitHub 連携で何ができる？', '開発標準はどう使われる？', 'トークンの安全な管理方法は？'],
  };

  // 工程 → 反映アクションの登録簿。各工程の JS が自分の反映操作を足す。
  const ACTIONS = {};
  function registerAction(view, action) {
    if (!ACTIONS[view]) ACTIONS[view] = [];
    ACTIONS[view] = ACTIONS[view].concat([action]);
  }

  let _panel = null;
  let _history = [];
  let _view = '';

  function labelOf(view) {
    const item = document.querySelector(`.app-nav-item[data-view="${view}"] .nav-label`);
    return item ? item.textContent.trim() : 'テスト活動支援';
  }

  function currentDomain() {
    // 画面が対象ドメインを持っていれば文脈として渡す（無ければ渡さない。推測しない）
    const sel = document.querySelector('#ta-design-domain, #ta-exec-suite, #ta-analysis-doc-select');
    return sel && sel.value ? sel.value : '';
  }

  function addMessage(role, text) {
    const body = _panel.querySelector('.ta2-ai-body');
    const el = document.createElement('div');
    el.className = 'ta2-msg ta2-msg-' + role;
    el.textContent = text;
    body.appendChild(el);
    body.scrollTop = body.scrollHeight;
    return el;
  }

  function addActionButton(label, onClick) {
    const body = _panel.querySelector('.ta2-ai-body');
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'ta2-msg-act';
    btn.textContent = label;
    btn.addEventListener('click', () => {
      btn.disabled = true;
      onClick();
    });
    body.appendChild(btn);
    body.scrollTop = body.scrollHeight;
  }

  // 回答のあとに「次の工程へ」と、その工程が登録した反映アクションを出す
  function offerActions() {
    (ACTIONS[_view] || []).forEach((a) => addActionButton(a.label, a.run));
    const proc = window.TA_PROCESS || [];
    const i = proc.findIndex((s) => s.view === _view);
    if (i >= 0 && i < proc.length - 1) {
      const next = proc[i + 1];
      addActionButton('→ ' + next.label + 'へ進む', () => {
        if (typeof switchView === 'function') switchView(next.view);
        close();
      });
    }
  }

  async function send(text) {
    if (!text) return;
    addMessage('me', text);
    _history = _history.concat([{ role: 'user', content: text }]).slice(-MAX_HISTORY);
    const pending = addMessage('ai', '考えています…');
    try {
      const res = await fetch('/api/llm/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          context: labelOf(_view),
          domain: currentDomain(),
          history: _history.slice(0, -1),
        }),
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || 'AIの呼び出しに失敗しました');
      pending.textContent = data.reply || '(応答が空でした)';
      _history = _history.concat([{ role: 'assistant', content: data.reply || '' }]).slice(-MAX_HISTORY);
      offerActions();
    } catch (e) {
      // 失敗を黙らせない。何が起きたかをその場に残す
      pending.textContent = 'エラー: ' + String(e && e.message ? e.message : e);
    }
  }

  function build() {
    const panel = document.createElement('aside');
    panel.className = 'ta2-ai-panel';
    panel.setAttribute('aria-label', 'AIと相談');
    panel.innerHTML =
      '<div class="ta2-ai-head">'
      + '<span class="ta2-ai-title">✦ AIと相談</span>'
      + '<span class="ta2-ai-ctx"></span>'
      + '<button type="button" class="ta2-ai-close" aria-label="閉じる">✕</button>'
      + '</div>'
      + '<div class="ta2-ai-body"></div>'
      + '<form class="ta2-ai-foot">'
      + '<input type="text" placeholder="メッセージを入力…" aria-label="AIへの相談内容">'
      + '<button type="submit" aria-label="送信">↑</button>'
      + '</form>';
    panel.querySelector('.ta2-ai-close').addEventListener('click', close);
    panel.querySelector('.ta2-ai-foot').addEventListener('submit', (e) => {
      e.preventDefault();
      const input = panel.querySelector('.ta2-ai-foot input');
      const v = input.value.trim();
      input.value = '';
      send(v);
    });
    return panel;
  }

  function activeView() {
    const el = document.querySelector('.view.is-active');
    return el ? el.id.replace(/^view-/, '') : 'test-activity';
  }

  function open() {
    if (_panel) return;
    _view = activeView();
    _history = [];
    _panel = build();
    document.body.appendChild(_panel);
    _panel.querySelector('.ta2-ai-ctx').textContent = labelOf(_view);
    addMessage('ai', labelOf(_view) + 'を表示中です。この画面の内容を踏まえて相談できます。');
    const body = _panel.querySelector('.ta2-ai-body');
    const lab = document.createElement('div');
    lab.className = 'ta2-sugg-label';
    lab.textContent = '質問の候補';
    body.appendChild(lab);
    (SUGGESTIONS[_view] || SUGGESTIONS['test-activity']).forEach((q) => {
      const s = document.createElement('button');
      s.type = 'button';
      s.className = 'ta2-sugg';
      s.textContent = q;
      s.addEventListener('click', () => send(q));
      body.appendChild(s);
    });
    const fab = document.getElementById('ta2-ai-fab');
    if (fab) fab.hidden = true;
    _panel.querySelector('.ta2-ai-foot input').focus();
  }

  function close() {
    if (_panel) _panel.remove();
    _panel = null;
    const fab = document.getElementById('ta2-ai-fab');
    if (fab) fab.hidden = false;
  }

  function init() {
    if (document.getElementById('ta2-ai-fab')) return;
    const fab = document.createElement('button');
    fab.type = 'button';
    fab.id = 'ta2-ai-fab';
    fab.className = 'ta2-ai-fab';
    fab.innerHTML = '<span aria-hidden="true">💬</span>AIと相談';
    fab.addEventListener('click', open);
    document.body.appendChild(fab);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && _panel) close(); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.taAiPanel = { registerAction, open, close };
})();
