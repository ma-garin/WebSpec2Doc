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
