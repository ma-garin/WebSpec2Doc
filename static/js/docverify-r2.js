/* ドキュメント検証 R2: AI の説明（送信前確認・採否・質問票へ送る）、設定画面の送信先と監査ログ。
   契約: docs/sdlc/20_design/WS2D-DD-006_詳細設計書_System06_R2.md 6 章。window.DV の公開物だけを使う。 */
(function () {
  'use strict';
  const DV = window.DV;
  if (!DV) return;
  const esc = DV.esc;
  const R2 = '/api/docverify/r2';
  const base = (fid) => `${R2}/inspections/${encodeURIComponent(DV.state.review.id)}/findings/${encodeURIComponent(fid)}/ai`;
  const post = (path, body) => DV.api(path, { method: 'POST', json: body || {} });
  const findingOf = (fid) => ((DV.state.review && DV.state.review.findings) || []).find((f) => f.id === fid);
  const closeModal = () => { const b = document.querySelector('#dv-modal [data-modal="cancel"]'); if (b) b.click(); };

  /* 指摘のカード・表の行に「AI の説明を見る」を足す（SCR-06-05） */
  function decorate() {
    document.querySelectorAll('[data-fa="ask"][data-fid]').forEach((b) => {
      const act = b.parentElement;
      if (!act || act.querySelector('[data-r2="explain"]')) return;
      act.insertAdjacentHTML('beforeend', `<button type="button" class="b" data-r2="explain" data-fid="${esc(b.dataset.fid)}">AI の説明を見る</button>`);
    });
    document.querySelectorAll('tr[data-fid]').forEach((tr) => {
      const td = tr.lastElementChild;
      if (!td || tr.querySelector('[data-r2="explain"]')) return;
      td.insertAdjacentHTML('beforeend', ` <button type="button" class="b" data-r2="explain" data-fid="${esc(tr.dataset.fid)}">AI の説明を見る</button>`);
    });
  }

  function highlight(text, spans) {
    let out = '', at = 0;
    (spans || []).forEach((s) => { out += esc(text.slice(at, s.start)) + `<mark>${esc(text.slice(s.start, s.end))}</mark>`; at = s.end; });
    return out + esc(text.slice(at));
  }

  function previewHtml(p, words, wobble) {
    const d = p.destination;
    const row = (k, v) => `<tr><th scope="row">${esc(k)}</th><td>${esc(v)}</td></tr>`;
    return `<table class="dv-r2-dest">${row('送信先', d.name + (d.model ? `（${d.model}）` : ''))}${row('所在', d.location)}`
      + `${row('学習利用', d.training)}${row('保持期間', d.retention)}${row('出典', `${d.source}（取得日 ${d.retrieved}）`)}`
      + `${row('送信回数', `${p.sends} 回`)}</table>`
      + `<p class="mut">実際に送る文（伏せ字の部分を強調しています）</p><pre class="dv-r2-text" style="white-space:pre-wrap">${highlight(p.masked.text, p.masked.spans)}</pre>`
      + `<label>ほかに伏せる語（読点で区切る）<input type="text" id="dv-r2-words" value="${esc(words.join('、'))}"></label>`
      + `<label><input type="checkbox" id="dv-r2-wobble"${wobble ? ' checked' : ''}> 解釈の揺れも調べる（追加で 3 回送ります）</label>`
      + '<p><button type="button" class="b" id="dv-r2-remask">伏せ字と送信回数を反映</button></p>'
      + `<p class="mut">「送る」を押すまで送信しません。最長 ${esc(p.timeout_sec)} 秒で打ち切ります。</p>`;
  }

  async function confirmSend(fid, words, wobble) {
    const p = await post(`${base(fid)}/preview`, { extra_words: words, with_wobble: wobble });
    let again = null;
    const shown = DV.modal({ title: 'AI へ送る前の確認', html: previewHtml(p, words, wobble), ok: '送る', cancel: '取りやめる' });
    const re = document.getElementById('dv-r2-remask');
    if (re) re.onclick = () => {
      const w = document.getElementById('dv-r2-words').value.split(/[、,]/).map((x) => x.trim()).filter(Boolean);
      again = [w, document.getElementById('dv-r2-wobble').checked];
      closeModal();
    };
    const ok = await shown;
    if (!ok) post(`${R2}/ai/cancel`, { consent_token: p.consent_token }).catch(() => {});
    if (again) return confirmSend(fid, again[0], again[1]);
    return ok ? p.consent_token : null;
  }

  async function send(fid, token) {
    let done = false;
    const waiting = DV.modal({ title: 'AI の説明を作っています', html: '<p>最長 60 秒かかります。取りやめても規則の指摘はそのまま使えます。</p>', cancel: '取りやめる' });
    waiting.then(() => { if (!done) post(`${R2}/ai/cancel`, { consent_token: token }).catch(() => {}); });
    try {
      const data = await post(`${base(fid)}/explain`, { consent_token: token });
      DV.setReview(data);
      return data.ai;
    } catch (e) {
      return null;  // 利用者向けの文は DV.api が帯に出している（FR-06-115）
    } finally {
      done = true;
      closeModal();
      await waiting;
    }
  }

  function resultHtml(ai) {
    const qs = (ai.open_questions || []).map((q, i) => `<li><label><input type="checkbox" data-r2q="${i}"${(ai.sent_questions || []).includes(i) ? ' disabled' : ''}> ${esc(q)}</label></li>`).join('');
    const wob = ai.wobble && ai.wobble.split ? '<p><span class="dv-chip">解釈が分かれます</span></p>' : '';
    const state = ai.adopted === true ? '採用済み' : ai.adopted === false ? '不採用' : '未判断';
    return `<p><span class="dv-chip">AI の提案</span> <span class="mut">${esc(ai.provider)} / ${esc(ai.model)}・${esc(state)}</span></p>${wob}`
      + `<h3>理由</h3><p>${esc(ai.explanation)}</p><h3>書き換え案</h3><p>${esc(ai.rewrite)}</p>`
      + '<p class="mut">採用しても元の文書は変わりません。案は指摘の対応結果に記録されます。</p>'
      + (qs ? `<h3>決まっていない事項</h3><ul>${qs}</ul><p><button type="button" class="b" id="dv-r2-q">選んだ事項を質問票へ送る</button></p>` : '')
      + '<p><button type="button" class="b" id="dv-r2-reject">不採用にする</button></p>';
  }

  async function showResult(fid, ai) {
    let act = null;
    const shown = DV.modal({ title: 'AI の提案', html: resultHtml(ai), ok: '採用する', cancel: '閉じる' });
    const rej = document.getElementById('dv-r2-reject');
    if (rej) rej.onclick = () => { act = 'reject'; closeModal(); };
    const q = document.getElementById('dv-r2-q');
    if (q) q.onclick = () => {
      act = [...document.querySelectorAll('[data-r2q]:checked')].map((x) => +x.dataset.r2q);
      closeModal();
    };
    const ok = await shown;
    try {
      if (ok || act === 'reject') {
        DV.setReview(await post(`${base(fid)}/decision`, { decision: ok ? 'adopt' : 'reject' }));
        DV.toast(ok ? 'AI 提案を採用しました。' : 'AI 提案を不採用にしました。');
      } else if (Array.isArray(act)) {
        if (!act.length) { DV.toast('質問票に送る事項を選んでください。'); return; }
        DV.setReview(await post(`${base(fid)}/questions`, { indexes: act }));
        DV.toast('質問票に送りました。');
      } else return;
      if (DV.current) DV.show(DV.current);
    } catch (e) { /* 帯に出ている */ }
  }

  async function explain(fid) {
    const f = findingOf(fid);
    if (f && f.ai) return showResult(fid, f.ai);
    try {
      const token = await confirmSend(fid, [], false);
      if (!token) return;
      const ai = await send(fid, token);
      if (ai) await showResult(fid, ai);
    } catch (e) { /* 「使わない」設定などは帯に出ている */ }
  }

  document.addEventListener('click', (e) => {
    const b = e.target.closest && e.target.closest('[data-r2="explain"]');
    if (!b || !DV.state.review) return;
    e.preventDefault();
    DV.busy(b, () => explain(b.dataset.fid));
  });
  new MutationObserver(() => decorate()).observe(document.body, { childList: true, subtree: true });

  /* 設定画面: 送信先（SCR-06-09）と監査ログ（SCR-06-12） */
  function settingsHtml(s) {
    const opt = [['none', '使わない'], ['openai', 'OpenAI'], ['ollama', 'Ollama（社内）']].map(([k, v]) =>
      `<label><input type="radio" name="dv-r2-dest" value="${k}"${s.settings.destination === k ? ' checked' : ''}${s.can_edit ? '' : ' disabled'}> ${esc(v)}</label>`).join(' ');
    const d = s.destination;
    return `<h3 class="dvg-h3">AI の送信先</h3><p>${opt}</p>`
      + `<p><label>Ollama の接続先 <input type="text" id="dv-r2-url" value="${esc(s.settings.ollama_url)}"${s.can_edit ? '' : ' disabled'}></label> `
      + `<label>モデル名 <input type="text" id="dv-r2-model" value="${esc(s.settings.ollama_model)}"${s.can_edit ? '' : ' disabled'}></label></p>`
      + `<ul class="dvg-list"><li>所在: ${esc(d.location)}</li><li>学習利用: ${esc(d.training)}</li><li>保持: ${esc(d.retention)}</li>`
      + `<li class="mut">出典: ${esc(d.source)}（取得日 ${esc(d.retrieved)}）</li></ul>`
      + (s.can_edit ? '<p><button type="button" class="b p" id="dv-r2-save">送信先を保存</button></p>' : '<p class="mut">送信先を変えられるのはテナント管理者です。</p>');
  }

  function auditHtml(data) {
    const users = (data.users || []).map((u) => `<option>${esc(u)}</option>`).join('');
    const acts = Object.entries(data.actions || {}).map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join('');
    return '<h3 class="dvg-h3">監査ログ</h3><p><label>開始 <input type="date" id="dv-r2-since"></label> <label>終了 <input type="date" id="dv-r2-until"></label> '
      + `<label>利用者 <select id="dv-r2-user"><option value="">すべて</option>${users}</select></label> `
      + `<label>操作 <select id="dv-r2-act"><option value="">すべて</option>${acts}</select></label> `
      + '<button type="button" class="b" id="dv-r2-filter">絞り込む</button> <button type="button" class="b" id="dv-r2-csv">CSV で出す</button></p><div id="dv-r2-rows"></div>';
  }

  function rowsHtml(rows) {
    if (!rows.length) return '<p class="mut">条件に合う記録はありません。</p>';
    return '<table class="dv-r2-audit"><thead><tr><th>日時</th><th>利用者</th><th>操作</th><th>対象</th><th>内容</th></tr></thead><tbody>'
      + rows.map((r) => `<tr><td>${esc(r.at)}</td><td>${esc(r.user)}</td><td>${esc(r.action_label)}</td><td>${esc(r.target)}</td><td>${esc(r.summary)}</td></tr>`).join('')
      + '</tbody></table>';
  }

  function query() {
    const v = (id) => (document.getElementById(id) || {}).value || '';
    const q = new URLSearchParams({ since: v('dv-r2-since'), until: v('dv-r2-until'), user: v('dv-r2-user'), action: v('dv-r2-act') });
    return q.toString();
  }

  async function loadAudit(box) {
    try {
      const data = await DV.api(`${R2}/audit`);
      box.innerHTML = auditHtml(data);
      document.getElementById('dv-r2-rows').innerHTML = rowsHtml(data.rows || []);
      document.getElementById('dv-r2-filter').onclick = (e) => DV.busy(e.target, async () => {
        const d = await DV.api(`${R2}/audit?${query()}`);
        document.getElementById('dv-r2-rows').innerHTML = rowsHtml(d.rows || []);
      });
      document.getElementById('dv-r2-csv').onclick = (e) => DV.busy(e.target, () => DV.download(`${R2}/audit.csv?${query()}`, 'audit.csv'));
    } catch (e) {
      DV.banner('');
      box.innerHTML = `<h3 class="dvg-h3">監査ログ</h3><p class="mut">${esc((e.data && e.data.error) || '監査ログを読めませんでした。再読み込みしてください。')}</p>`;
    }
  }

  async function renderSettings() {
    const host = document.getElementById('dvgSettings');
    if (!host) return;
    let box = document.getElementById('dv-r2-settings');
    if (!box) { host.insertAdjacentHTML('afterend', '<section id="dv-r2-settings"><div id="dv-r2-llm"></div><div id="dv-r2-audit"></div></section>'); box = document.getElementById('dv-r2-settings'); }
    const llm = document.getElementById('dv-r2-llm');
    try {
      const s = await DV.api(`${R2}/llm-settings`);
      llm.innerHTML = settingsHtml(s);
      const save = document.getElementById('dv-r2-save');
      if (save) save.onclick = () => DV.busy(save, async () => {
        const dest = (document.querySelector('[name="dv-r2-dest"]:checked') || {}).value || 'none';
        await post(`${R2}/llm-settings`, { destination: dest, ollama_url: document.getElementById('dv-r2-url').value, ollama_model: document.getElementById('dv-r2-model').value });
        DV.toast('送信先を保存しました。');
        renderSettings();
      }).catch(() => {});
    } catch (e) { llm.innerHTML = '<p class="mut">送信先の設定を読めませんでした。再読み込みしてください。</p>'; }
    loadAudit(document.getElementById('dv-r2-audit'));
  }

  DV.on('settings', renderSettings);
  DV.r2 = { decorate, explain, renderSettings };
})();
