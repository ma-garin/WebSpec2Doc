(() => {
  const host = document.getElementById('dvtS3');
  if (!host) return;
  const R = host.querySelector('[data-dvt3]') || host;
  const q = s => R.querySelector(s), qa = s => [...R.querySelectorAll(s)];
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const TN = {1: '格1 方針', 2: '格2 決まりごと', 3: '格3 仕様', 4: '格4 メモ'};
  const SEV = {high: '重大', mid: '注意', low: '軽微'};
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
  const badSet = st => { const m = {}; (st.findings || []).forEach(f => { m[f.doc_id] = true; }); return m; };
  const isBad = (st, n) => !!badSet(st)[n.id];
  const liveCount = (st, id) => liveFindings(st).filter(f => f.doc_id === id).length;
  const fmtAt = v => {
    if (!v) return '';
    const d = new Date(v); if (isNaN(d.getTime())) return String(v);
    const z = n => String(n).padStart(2, '0');
    return d.getFullYear() + '/' + z(d.getMonth() + 1) + '/' + z(d.getDate()) + ' ' + z(d.getHours()) + ':' + z(d.getMinutes());
  };
  const docSev = (st, id) => {
    const o = {high: 3, mid: 2, low: 1}; let m = 0;
    liveFindings(st).forEach(f => { if (f.doc_id === id && (o[f.severity] || 0) > m) m = o[f.severity]; });
    return m;
  };
  const sevName = m => m === 3 ? '重大' : m === 2 ? '注意' : m === 1 ? '軽微' : '';

  function level(st) { return (st.conclusion && st.conclusion.level) || st.auto_level || 'pass'; }

  function drawHead(st) {
    const lv = level(st);
    const v = q('[data-verdict]');
    v.className = 'dvt-s3-verdict ' + lv;
    v.innerHTML = VICO[lv] + '<span>' + esc(st.level_label || lv) + '</span><small>' + esc(VTEXT[lv]) + '</small>';
    const ns = nodes(st), bad = ns.filter(n => isBad(st, n));
    q('[data-n-all]').textContent = ns.length;
    q('[data-n-bad]').textContent = bad.length;
    q('[data-n-major]').textContent = liveFindings(st).filter(f => f.severity === 'high').length;
    const done = isDone(st);
    R.classList.toggle('fixed', done);
    q('[data-act]').innerHTML = done
      ? '<span class="dvt-s3-done"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 8.5l3.2 3.2L13 5"/></svg>確定済み</span>'
      : '<button type="button" class="dvt-s3-btn main" data-open>レポートを確定</button>';
    const cc = q('[data-concl]'), cn = st.conclusion || {};
    if (cc) {
      cc.hidden = !done;
      cc.innerHTML = done ? '<span><b>確定した人</b>' + esc(cn.confirmed_by || '（未記入）') + '</span><span><b>確定した日時</b>' + esc(fmtAt(cn.confirmed_at) || '（不明）') + '</span><span class="cm"><b>コメント</b>' + esc(cn.comment || 'なし') + '</span>' : '';
    }
    q('[data-lead]').textContent = done
      ? 'レポートは確定されました。課題のある文書だけが強調されています。文書を押すと、つながりを確かめられます。'
      : '表から文書を選ぶと、その文書が従う先と従う側が見えます。内容を確かめたら、レポートを確定してください。';
    q('[data-redo-wrap]').hidden = false;
  }

  function drawRows(st) {
    const ns = nodes(st), sevMap = {};
    ns.forEach(n => { sevMap[n.id] = docSev(st, n.id); });
    const bs = badSet(st);
    q('[data-rows]').innerHTML = ns.map(n => {
      const bad = !!bs[n.id];
      if (filt === 'bad' && !bad) return '';
      if (filt === 'major' && sevMap[n.id] !== 3) return '';
      const c = STCLS[n.status] || 'ok';
      const label = bad ? ((sevName(sevMap[n.id]) || '要確認') + '：要対応' + (liveCount(st, n.id) ? '（' + liveCount(st, n.id) + ' 件）' : '')) : '問題なし';
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
    if (!parts.length && e.reason) parts.push(esc(e.reason));
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
    const bs = badSet(st);
    const isProb = e => e.type !== 'follows' && (e.finding_ids || []).some(id => !reported(st)[id]);
    const group = (list, key) => {
      const g = [], idx = {};
      list.forEach(e => {
        const o = by[e[key]], i = edges.indexOf(e);
        if (idx[o.id] == null) { idx[o.id] = g.length; g.push({o, ids: []}); }
        g[idx[o.id]].ids.push(i);
      });
      return g;
    };
    const up = dir !== 'down' ? group(edges.filter(e => e.from === b.id && by[e.to]), 'to') : [];
    const dn = dir !== 'up' ? group(edges.filter(e => e.to === b.id && by[e.from]), 'from') : [];
    const none = !up.length && !dn.length;
    const avail = (map.parentElement || host).clientWidth || 560;
    const W = Math.max(320, Math.min(560, avail - 36)), cw = Math.max(110, Math.min(170, Math.floor((W - 60) / 2))), ch = 48;
    const H = none ? 100 : Math.max(up.length, dn.length, 1) * 62, cx = (W - cw) / 2, cy = none ? 0 : (H - ch) / 2;
    map.style.cssText = 'width:' + W + 'px;height:' + H + 'px';
    let svg = '<svg width="' + W + '" height="' + H + '">', html = '';
    const nodeHtml = (o, cls, st2) => '<div class="' + cls + '" ' + (st2.id ? 'data-id="' + esc(o.id) + '" ' : '') + 'title="' + esc(o.name) + '" style="' + st2.css + '"><span class="nm">' + esc(o.name) + '</span><small>' + esc(TN[o.tier] || '') + '</small></div>';
    const place = (list, side) => list.forEach((g, k) => {
      const o = g.o;
      const y = (H / list.length) * (k + .5) - ch / 2, x = side === 'L' ? 0 : W - cw;
      const x1 = side === 'L' ? x + cw : cx + cw, x2 = side === 'L' ? cx : x;
      const y1 = (side === 'L' ? y : cy) + ch / 2, y2 = (side === 'L' ? cy : y) + ch / 2, m = (x1 + x2) / 2;
      const p = 'M' + x1 + ' ' + y1 + 'C' + m + ' ' + y1 + ' ' + m + ' ' + y2 + ' ' + x2 + ' ' + y2;
      const pb = g.ids.some(i => isProb(edges[i])), ds = g.ids.join(',');
      svg += '<path class="ln' + (pb ? ' bad' : '') + '" data-e="' + ds + '" d="' + p + '"/><path class="hit" data-e="' + ds + '" d="' + p + '"/>';
      html += nodeHtml(o, 'nd' + (bs[o.id] ? ' bad' : ''), {id: 1, css: 'left:' + x + 'px;top:' + y + 'px;width:' + cw + 'px'});
    });
    place(up, 'L'); place(dn, 'R'); svg += '</svg>';
    html += nodeHtml(b, 'nd base' + (bs[b.id] ? ' bad' : ''), {id: 0, css: 'left:' + cx + 'px;top:' + cy + 'px;width:' + cw + 'px;cursor:default'});
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
    if (!e.target.closest('svg')) return;
    const box = q('[data-map]').getBoundingClientRect(), px = e.clientX - box.left, py = e.clientY - box.top;
    let best = null, bd = 14;
    qa('.ln').forEach(path => {
      const len = path.getTotalLength();
      for (let t = 0; t <= len; t += 4) {
        const pt = path.getPointAtLength(t), d = Math.hypot(pt.x - px, pt.y - py);
        if (d < bd) { bd = d; best = path; }
      }
    });
    if (!best) return;
    const ids = best.dataset.e.split(',').map(Number), eds = ids.map(i => st.links.edges[i]).filter(Boolean);
    if (!eds.length) return;
    const nm = {}; nodes(st).forEach(x => { nm[x.id] = x.name; });
    qa('.ln.pick').forEach(x => x.classList.remove('pick'));
    best.classList.add('pick');
    const why = q('[data-why]');
    const rs = eds.map(ed => ed.type !== 'follows' ? edgeReason(st, ed) : '').filter(Boolean);
    const r = rs.join('<hr>');
    why.className = 'dvt-s3-why' + (r ? ' bad' : '');
    why.innerHTML = '<b>' + esc(nm[eds[0].to]) + ' → ' + esc(nm[eds[0].from]) + '</b>' + (r || '問題はありません。上の格の内容に従って書かれています。');
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

  const mask = q('[data-mask]'), err = q('[data-err]'), byIn = q('[data-by]');
  let opener = null;
  const showErr = m => {
    err.textContent = m; err.hidden = !m;
    byIn.classList.toggle('inv', !!m);
    if (m) { byIn.setAttribute('aria-invalid', 'true'); byIn.setAttribute('aria-describedby', 'dvt3Err'); }
    else { byIn.removeAttribute('aria-invalid'); byIn.removeAttribute('aria-describedby'); }
  };
  const closeDlg = () => { mask.classList.remove('on'); if (opener && opener.isConnected) opener.focus(); opener = null; };
  q('[data-act]').addEventListener('click', e => {
    const ob = e.target.closest('[data-open]'); if (!ob) return;
    const st = S(); if (!st) return;
    const live = liveFindings(st), c = {high: 0, mid: 0, low: 0};
    live.forEach(f => { c[f.severity] = (c[f.severity] || 0) + 1; });
    const bad = nodes(st).filter(n => isBad(st, n)).length;
    q('[data-sum]').innerHTML = '<li>結論：' + esc(st.level_label || '') + '</li><li>課題のある文書：' + bad + ' 件（重大 ' + c.high + '・注意 ' + c.mid + '・軽微 ' + c.low + '）</li><li>文書か検査の結果が変わると、確定は取り消されます</li>';
    opener = ob; showErr(''); mask.classList.add('on'); byIn.focus();
  });
  q('[data-cancel]').addEventListener('click', closeDlg);
  mask.addEventListener('mousedown', e => { if (e.target === mask) closeDlg(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && mask.classList.contains('on')) { e.preventDefault(); closeDlg(); } });
  byIn.addEventListener('input', () => { if (!err.hidden) showErr(''); });
  q('[data-ok]').addEventListener('click', async () => {
    const by = byIn.value.trim();
    if (!by) { showErr('確定する人の名前を入力してください。'); byIn.focus(); return; }
    const btn = q('[data-ok]'); btn.disabled = true;
    try {
      const r = await window.DVT.api('tier/confirm', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({by, comment: q('[data-comment]').value.trim()})});
      if (r && r.error) throw new Error(r.error);
      closeDlg();
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
