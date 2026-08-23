// ---- テスト活動支援 / 分析ビュー ----
// System 01（ドキュメント作成）の解析データを読み取り専用で共用する。
// 経路: /api/history（サイト一覧）→ /api/result?domain（report.json のパス）
//       → /preview?path=（screens[] と transitions）。書き込みは行わない。
(function () {
  // escHtml（core.js）不在時も素通しにしない。読込順が変わっても外部サイト由来の
  // title/url が未エスケープで innerHTML に入らないよう、自前の置換を持つ。
  const esc = (v) => (typeof escHtml === 'function'
    ? escHtml(String(v))
    : String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));
  let _domainsLoaded = false;

  function _select() { return document.getElementById('ta-analysis-doc-select'); }
  function _tbody() { return document.getElementById('ta-condition-body'); }

  function _showEmpty(message) {
    const tbody = _tbody();
    if (tbody) tbody.innerHTML = `<tr><td colspan="6"><div class="empty">${esc(message)}</div></td></tr>`;
  }

  async function loadDomains() {
    const sel = _select();
    if (!sel) return;
    try {
      const res = await fetch('/api/history');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'サイト一覧を取得できませんでした');
      const items = data.items || [];
      const current = sel.value;
      sel.innerHTML = '<option value="">解析済みサイトを選択</option>'
        + items.map(it => `<option value="${esc(it.domain)}">${esc(it.domain)}（${Number(it.screens) || 0} 画面）</option>`).join('');
      if (current && items.some(it => it.domain === current)) sel.value = current;
      _domainsLoaded = true;
    } catch (e) {
      _showEmpty('サイト一覧の読み込みに失敗しました: ' + e.message);
    }
  }

  async function loadConditions(domain) {
    const tbody = _tbody();
    if (!tbody) return;
    if (!domain) { _showEmpty('まだデータがありません'); return; }
    tbody.innerHTML = '<tr><td colspan="6">読み込んでいます…</td></tr>';
    try {
      const res = await fetch('/api/result?domain=' + encodeURIComponent(domain));
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || '解析結果を取得できませんでした');
      const jsonPath = data.files && data.files.json;
      if (!jsonPath) { _showEmpty('このサイトには解析データ（report.json）がありません'); return; }
      const repRes = await fetch('/preview?path=' + encodeURIComponent(jsonPath));
      if (!repRes.ok) throw new Error('report.json を読み込めませんでした（HTTP ' + repRes.status + '）');
      const report = await repRes.json();
      const screens = report.screens || [];
      if (!screens.length) { _showEmpty('このサイトには画面データがありません'); return; }
      _renderConditions(screens, domain);
    } catch (e) {
      _showEmpty('読み込みに失敗しました: ' + e.message);
    }
  }

  // 画面 1 件をテスト条件の種 1 行にする。
  //   条件ID = 画面ID ／ 由来 = 画面名と URL ／ 分類 = 画面 ／ 観点 = 遷移先の数。
  // 優先度は流入遷移数から導出する（流入が多い画面ほど壊れたときの影響が広い）。
  function _renderConditions(screens, domain) {
    const tbody = _tbody();
    if (!tbody) return;
    // 行データを先に配列として組み立て、表の描画と設計ビューへの引き継ぎ保存の
    // 両方に同じデータを使う（描画とデータ構築の二重化を避ける）。
    const items = screens.map(sc => {
      const title = sc.title || sc.url || '(無題)';
      const toCount = ((sc.transitions && sc.transitions.to) || []).length;
      const fromCount = ((sc.transitions && sc.transitions.from) || []).length;
      return {
        id: sc.page_id || sc.state_id || '',
        title,
        url: sc.url || '',
        condition: `画面「${title}」が表示され、定義された遷移先へ移動できること`,
        category: '画面',
        priority: fromCount >= 3 ? '高' : (fromCount >= 1 ? '中' : '低'),
        note: `遷移先 ${toCount} 件 ／ 流入 ${fromCount} 件`,
      };
    });
    tbody.innerHTML = items.map(it => `<tr>
        <td>${esc(it.id)}</td>
        <td>${esc(it.title)}<div class="muted-copy">${esc(it.url)}</div></td>
        <td>${esc(it.condition)}</td>
        <td>${esc(it.category)}</td>
        <td>${esc(it.priority)}</td>
        <td>${esc(it.note)}</td>
      </tr>`).join('');
    _saveConditions(domain, items);
  }

  // 設計ビューへの引き継ぎ保存。契約: キー ta.conditions.v1 /
  // 値 {"domain": 抽出元ドメイン, "items": [{id,title,url,condition,category,priority,note}]}。
  // ストレージ不可（プライベートモード等）でも分析表示自体は成立させる。
  function _saveConditions(domain, items) {
    try {
      sessionStorage.setItem('ta.conditions.v1', JSON.stringify({ domain, items }));
    } catch (_) { /* 保存失敗は無視。分析表示を止めない */ }
  }

  function _reload() {
    loadDomains();
    const sel = _select();
    if (sel && sel.value) loadConditions(sel.value);
  }

  document.getElementById('ta-analysis-doc-select')?.addEventListener('change', (e) => {
    loadConditions(e.target.value);
  });
  document.getElementById('ta-analysis-reload')?.addEventListener('click', _reload);

  // 画面切替時の初期化。core.js の VIEW_INIT 表へビュー側から登録する（core.js は編集しない）。
  if (typeof onViewEnter === 'function') {
    onViewEnter('test-analysis', () => { if (!_domainsLoaded) loadDomains(); });
  } else {
    loadDomains();
  }
})();


// ---- テスト活動支援 / 分析ビュー: 仕様書ファイルのアップロード ----
// 既存の POST /api/reference-docs（output/{domain}/reference_docs/ へ保存）へ配線する。
// 受け入れ拡張子と上限サイズはサーバ側 allowlist が正で、ここでは事前選別のみ行う。
(function () {
  const UPLOAD_BUCKET = 'uploads';

  function _el(id) { return document.getElementById(id); }

  function _setState(message, isError) {
    const box = _el('ta-analysis-doc-upload-state');
    if (!box) return;
    box.hidden = false;
    box.textContent = message;
    box.classList.toggle('is-error', Boolean(isError));
  }

  function _markDocConnected(count) {
    const item = document.querySelector('#ta-analysis-source-state .ta-source-item');
    const badge = item ? item.querySelector('.badge') : null;
    if (!badge) return;
    badge.textContent = count + ' 件';
    badge.classList.remove('badge-muted');
  }

  async function _upload() {
    const input = _el('ta-analysis-doc-files');
    const files = input && input.files ? Array.from(input.files) : [];
    if (!files.length) {
      _setState('ファイルを選択してください。', true);
      return;
    }
    // 解析済みサイトに依存せず単独で使えるよう、アップロード専用の保存先へ固定する。
    // DOMAIN_RE（^[A-Za-z0-9._:\[\]-]{1,253}$）を満たす値であること。
    const domain = UPLOAD_BUCKET;
    const form = new FormData();
    form.append('domain', domain);
    files.forEach((file) => form.append('files', file));
    _setState(files.length + ' 件をアップロードしています…');
    try {
      const res = await fetch('/api/reference-docs', { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || 'アップロードに失敗しました');
      const saved = data.saved || [];
      _setState(saved.length + ' 件をアップロードしました: ' + saved.map((s) => s.name).join('、'));
      _markDocConnected(saved.length);
    } catch (e) {
      _setState('アップロードに失敗しました: ' + e.message, true);
    }
  }

  // 読込順に依存しないよう委譲で束ねる。
  document.addEventListener('click', (ev) => {
    const target = ev.target;
    if (target && target.id === 'ta-analysis-doc-upload') _upload();
  });
})();


// ---- テスト活動支援 / 分析ビュー: 「テスト条件を抽出」ボタン ----
// 押下しても無反応だった不具合の解消。成功・失敗・未生成のいずれでも必ず状態を表示する。
(function () {
  const UPLOAD_BUCKET = 'uploads';

  const esc = (v) => (typeof escHtml === 'function'
    ? escHtml(String(v))
    : String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));

  function _setState(message, isError) {
    const box = document.getElementById('ta-analysis-doc-upload-state');
    if (!box) return;
    box.hidden = false;
    box.textContent = message;
    box.classList.toggle('is-error', Boolean(isError));
  }

  function _tbody() { return document.getElementById('ta-condition-body'); }

  function _showRowMessage(message) {
    const tbody = _tbody();
    if (tbody) tbody.innerHTML = `<tr><td colspan="6"><div class="empty">${esc(message)}</div></td></tr>`;
  }

  function _render(items) {
    const tbody = _tbody();
    if (!tbody) return;
    tbody.innerHTML = items.map((it, i) => `<tr>
      <td>${esc(it.id || 'TC-' + String(i + 1).padStart(3, '0'))}</td>
      <td>${esc(it.source || it.origin || '-')}</td>
      <td>${esc(it.condition || it.title || '-')}</td>
      <td>${esc(it.category || '-')}</td>
      <td>${esc(it.priority || '-')}</td>
      <td>${esc(it.note || '-')}</td>
    </tr>`).join('');
  }

  async function _extract() {
    const btn = document.getElementById('ta-analysis-run');
    if (btn) btn.disabled = true;
    _setState('アップロード済み文書からテスト条件を抽出しています…');
    _showRowMessage('抽出しています…');
    try {
      const res = await fetch('/api/doc-fusion?domain=' + encodeURIComponent(UPLOAD_BUCKET));
      if (res.status === 404) {
        _setState('アップロードした文書の解析結果がまだ生成されていません。先にドキュメントをアップロードしてください。', true);
        _showRowMessage('解析結果がありません（doc_fusion.json 未生成）');
        return;
      }
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || '抽出に失敗しました');
      const items = data.items || data.conditions || data.requirements || [];
      if (!items.length) {
        _setState('解析結果に条件として取り出せる項目がありませんでした。', true);
        _showRowMessage('抽出できる項目がありませんでした');
        return;
      }
      _render(items);
      _setState(items.length + ' 件のテスト条件を抽出しました。');
    } catch (e) {
      _setState('抽出に失敗しました: ' + e.message, true);
      _showRowMessage('抽出に失敗しました: ' + e.message);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  document.addEventListener('click', (ev) => {
    if (ev.target && ev.target.id === 'ta-analysis-run') _extract();
  });
})();
