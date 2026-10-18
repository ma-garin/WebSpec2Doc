(() => {
  const host = document.getElementById('dvtS3');
  if (!host) return;
  const R = host.querySelector('[data-dvt3]') || host;
  const q = s => R.querySelector(s), qa = s => [...R.querySelectorAll(s)];
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const TN = {1: '格1 方針', 2: '格2 決まりごと', 3: '格3 仕様', 4: '格4 メモ'};
  const SEV = {high: '重大', mid: '中', low: '軽微'};
  const ICO = {
    ng: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="8" cy="8" r="6.5"/><path d="M5.5 5.5l5 5M10.5 5.5l-5 5"/></svg>',
    wa: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M8 2l6.5 11.5h-13z"/><path d="M8 6.5v3M8 11.5v.2"/></svg>',
    ok: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="8" cy="8" r="6.5"/><path d="M5 8.2l2.2 2.2L11 6"/></svg>'
  };
  const VICO = {
    fail: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/></svg>',
    conditional: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 3l9.5 17h-19z"/><path d="M12 10v4M12 17v.2"/></svg>',
    pass: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="9"/><path d="M8 12.3l3 3 5-6"/></svg>'
  };
  const VTEXT = {
    fail: '重大な課題があります。直すまで合格にできません。',
    conditional: '軽い課題が残っています。内容を確かめて確定してください。',
    pass: '課題は見つかりませんでした。'
  };
  const STCLS = {ng: 'ng', warn: 'wa', ok: 'ok'};
  let sel = null, dir = 'both', filt = 'all', pick = null;

  const S = () => (window.DVT && window.DVT.state) || null;
  const reported = st => st.reports || {};
  const liveFindings = st => (st.findings || []).filter(f => !reported(st)[f.id]);
  const fById = st => { const m = {}; (st.findings || []).forEach(f => { m[f.id] = f; }); return m; };
  const nodes = st => ((st.links && st.links.nodes) || []).slice().sort((a, b) => a.tier - b.tier || String(a.name).localeCompare(String(b.name)));
  const isDone = st => st.step === 'done';
  const isBad = n => n.status !== 'ok';
  const docSev = (st, id) => {
    const o = {high: 3, mid: 2, low: 1}; let m = 0;
    liveFindings(st).forEach(f => { if ((f.doc_id === id || f.related_doc_id === id) && (o[f.severity] || 0) > m) m = o[f.severity]; });
    return m;
  };
  const sevName = m => m === 3 ? '重大' : m === 2 ? '中' : m === 1 ? '軽微' : '';

  function level(st) { return (st.conclusion && st.conclusion.level) || st.auto_level || 'pass'; }

  function drawHead(st) {
    const lv = level(st);
    const v = q('[data-verdict]');
    v.className = 'dvt-s3-verdict ' + lv;
    v.innerHTML = VICO[lv] + '<span>' + esc(st.level_label || lv) + '</span><small>' + esc(VTEXT[lv]) + '</small>';
    const ns = nodes(st), bad = ns.filter(isBad);
    q('[data-n-all]').textContent = ns.length;
    q('[data-n-bad]').textContent = bad.length;
    q('[data-n-major]').textContent = liveFindings(st).filter(f => f.severity === 'high').length;
    const done = isDone(st);
    R.classList.toggle('fixed', done);
    q('[data-act]').innerHTML = done
      ? '<span class="dvt-s3-done"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 8.5l3.2 3.2L13 5"/></svg>確定済み</span>'
      : '<button type="button" class="dvt-s3-btn main" data-open>レポートを確定</button>';
    q('[data-lead]').textContent = done
      ? 'レポートは確定されました。課題のある文書だけが強調されています。文書を押すと、つながりを確かめられます。'
      : '表から文書を選ぶと、その文書が従う先と従う側が見えます。内容を確かめたら、レポートを確定してください。';
    q('[data-redo-wrap]').hidden = false;
  }

  function drawRows(st) {
    const ns = nodes(st), sevMap = {};
    ns.forEach(n => { sevMap[n.id] = docSev(st, n.id); });
    q('[data-rows]').innerHTML = ns.map(n => {
      const bad = isBad(n);
      if (filt === 'bad' && !bad) return '';
      if (filt === 'major' && sevMap[n.id] !== 3) return '';
      const c = STCLS[n.status] || 'ok';
      const label = bad ? ((sevName(sevMap[n.id]) || '要確認') + '：要対応' + (n.issues ? '（' + n.issues + ' 件）' : '')) : '問題なし';
      return '<tr class="r' + (bad ? ' bad' : '') + (n.id === sel ? ' sel' : '') + '" data-id="' + esc(n.id) + '"><td>' + esc(n.name) +
        '</td><td><span class="tier">' + esc(TN[n.tier] || '') + '</span></td><td><span class="st ' + c + '">' + ICO[c] + esc(label) + '</span></td></tr>';
    }).join('') || '<tr><td colspan="3" class="dvt-s3-empty">該当する文書はありません</td></tr>';
  }

  function edgeReason(st, e) {
    const fm = fById(st), parts = [];
    (e.finding_ids || []).forEach(id => {
      const f = fm[id]; if (!f || reported(st)[id]) return;
      parts.push('<b>' + esc(f.rule_label || '') + '（' + esc(SEV[f.severity] || '') + '）</b>' + esc(f.reason || '') +
        (f.quote ? '<span class="dvt-s3-q">「' + esc(f.quote) + '」</span>' : '') +
        (f.fix ? '<span class="dvt-s3-fix">' + esc(f.fix) + '</span>' : ''));
    });
    return parts.join('<hr>');
  }

  function drawMap(st) {
    pick = null;
    const map = q('[data-map]'), why = q('[data-why]');
    const ns = nodes(st), by = {}; ns.forEach(n => { by[n.id] = n; });
    const b = by[sel];
    if (!b) { map.style.cssText = ''; map.innerHTML = '<p class="dvt-s3-none">左の表から文書を選んでください</p>'; q('[data-title]').textContent = '基点の文書'; why.className = 'dvt-s3-why'; why.textContent = '線を押すと、つながりの理由がここに出ます。'; return; }
    q('[data-title]').textContent = b.name + ' を基点に';
    const edges = ((st.links && st.links.edges) || []);
    const isProb = e => e.type !== 'follows' && (e.finding_ids || []).some(id => !reported(st)[id]);
    const up = dir !== 'down' ? edges.filter(e => e.from === b.id && by[e.to]) : [];
    const dn = dir !== 'up' ? edges.filter(e => e.to === b.id && by[e.from]) : [];
    const none = !up.length && !dn.length;
    const H = none ? 100 : Math.max(up.length, dn.length, 1) * 62, W = 560, cw = 170, ch = 48, cx = (W - cw) / 2, cy = none ? 0 : (H - ch) / 2;
    map.style.cssText = 'width:' + W + 'px;height:' + H + 'px';
    let svg = '<svg width="' + W + '" height="' + H + '">', html = '';
    const place = (list, side) => list.forEach((e, k) => {
      const o = by[side === 'L' ? e.to : e.from];
      const y = (H / list.length) * (k + .5) - ch / 2, x = side === 'L' ? 0 : W - cw;
      const x1 = side === 'L' ? x + cw : cx + cw, x2 = side === 'L' ? cx : x;
      const y1 = (side === 'L' ? y : cy) + ch / 2, y2 = (side === 'L' ? cy : y) + ch / 2, m = (x1 + x2) / 2;
      const p = 'M' + x1 + ' ' + y1 + 'C' + m + ' ' + y1 + ' ' + m + ' ' + y2 + ' ' + x2 + ' ' + y2;
      const i = edges.indexOf(e), pb = isProb(e);
      svg += '<path class="ln' + (pb ? ' bad' : '') + '" data-e="' + i + '" d="' + p + '"/><path class="hit" data-e="' + i + '" d="' + p + '"/>';
      html += '<div class="nd' + (isBad(o) ? ' bad' : '') + '" data-id="' + esc(o.id) + '" style="left:' + x + 'px;top:' + y + 'px">' + esc(o.name) + '<small>' + esc(TN[o.tier] || '') + '</small></div>';
    });
    place(up, 'L'); place(dn, 'R'); svg += '</svg>';
    html += '<div class="nd base' + (isBad(b) ? ' bad' : '') + '" style="left:' + cx + 'px;top:' + cy + 'px;cursor:default">' + esc(b.name) + '<small>' + esc(TN[b.tier] || '') + '</small></div>';
    if (up.length) html += '<span class="col-t" style="left:0">上流（従う先）</span>';
    if (dn.length) html += '<span class="col-t" style="left:' + (W - cw) + 'px">下流（従う側）</span>';
    if (none) html += '<p class="dvt-s3-none" style="top:' + (ch + 16) + 'px">この向きにつながる文書はありません</p>';
    map.innerHTML = svg + html;
    why.className = 'dvt-s3-why';
    why.textContent = (up.length + dn.length) ? '線を押すと、つながりの理由がここに出ます。' : 'つながりが無いこと自体は問題ではありません。';
  }

  function render() {
    const st = S(); if (!st || !st.links) return;
    const ns = nodes(st);
    if (!sel || !ns.some(n => n.id === sel)) { const f = ns.find(isBad) || ns[0]; sel = f ? f.id : null; }
    drawHead(st); drawRows(st); drawMap(st);
  }

  q('[data-rows]').addEventListener('click', e => {
    const t = e.target.closest('tr[data-id]'); if (!t) return;
    sel = t.dataset.id; const st = S(); if (st) { drawRows(st); drawMap(st); }
  });
  q('[data-map]').addEventListener('click', e => {
    const st = S(); if (!st) return;
    const n = e.target.closest('.nd:not(.base)');
    if (n) { sel = n.dataset.id; drawRows(st); drawMap(st); return; }
    const h = e.target.closest('.hit'); if (!h) return;
    const ed = st.links.edges[+h.dataset.e]; if (!ed) return;
    const nm = {}; nodes(st).forEach(x => { nm[x.id] = x.name; });
    qa('.ln.pick').forEach(x => x.classList.remove('pick'));
    const ln = q('.ln[data-e="' + h.dataset.e + '"]'); if (ln) ln.classList.add('pick');
    const why = q('[data-why]'), r = ed.type !== 'follows' ? edgeReason(st, ed) : '';
    why.className = 'dvt-s3-why' + (r ? ' bad' : '');
    why.innerHTML = '<b>' + esc(nm[ed.from]) + ' → ' + esc(nm[ed.to]) + '</b>' + (r || '問題はありません。上の格の内容に従って書かれています。');
  });
  q('[data-seg]').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    dir = b.dataset.d; qa('[data-seg] button').forEach(x => x.classList.toggle('on', x === b));
    const st = S(); if (st) drawMap(st);
  });
  qa('.dvt-s3-num').forEach(b => b.addEventListener('click', () => {
    filt = b.dataset.f; qa('.dvt-s3-num').forEach(x => x.classList.toggle('on', x === b));
    const st = S(); if (st) drawRows(st);
  }));

  const mask = q('[data-mask]'), err = q('[data-err]');
  const showErr = m => { err.textContent = m; err.hidden = !m; };
  q('[data-act]').addEventListener('click', e => {
    if (!e.target.closest('[data-open]')) return;
    const st = S(); if (!st) return;
    const live = liveFindings(st), c = {high: 0, mid: 0, low: 0};
    live.forEach(f => { c[f.severity] = (c[f.severity] || 0) + 1; });
    const bad = nodes(st).filter(isBad).length;
    q('[data-sum]').innerHTML = '<li>結論：' + esc(st.level_label || '') + '</li><li>課題のある文書：' + bad + ' 件（重大 ' + c.high + '・中 ' + c.mid + '・軽微 ' + c.low + '）</li><li>文書か検査の結果が変わると、確定は取り消されます</li>';
    showErr(''); mask.classList.add('on'); q('[data-by]').focus();
  });
  q('[data-cancel]').addEventListener('click', () => mask.classList.remove('on'));
  q('[data-ok]').addEventListener('click', async () => {
    const by = q('[data-by]').value.trim();
    if (!by) { showErr('確定する人の名前を入力してください。'); return; }
    const btn = q('[data-ok]'); btn.disabled = true;
    try {
      const r = await window.DVT.api('tier/confirm', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({by, comment: q('[data-comment]').value.trim()})});
      if (r && r.error) throw new Error(r.error);
      mask.classList.remove('on');
      await window.DVT.refresh();
      window.DVT.toast('レポートを確定しました', 'ok');
    } catch (ex) {
      showErr((ex && ex.message) || '確定できませんでした。もう一度お試しください。');
    } finally { btn.disabled = false; }
  });
  q('[data-redo]').addEventListener('click', async () => {
    try {
      const r = await window.DVT.api('tier/reset', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({to: 2})});
      if (r && r.error) throw new Error(r.error);
      await window.DVT.refresh();
      window.DVT.go(2);
    } catch (ex) {
      window.DVT.toast((ex && ex.message) || 'やり直せませんでした。もう一度お試しください。', 'error');
    }
  });

  document.addEventListener('dvt:state', render);
  render();
})();
