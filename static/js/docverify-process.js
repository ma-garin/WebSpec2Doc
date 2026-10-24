/* ドキュメント検証 R4: 種別・役割・工程・工数と指標・プリセット・判定と記録（WS2D-DD-006 R4 7 章）。
 * templates/docverify/_process.html の部品を各画面へ差し込む。更新は必ず rev を送り、409 は再読み込みを促す。 */
(() => {
  'use strict';
  if (!window.DV) return;
  const DV = window.DV;
  const P = '/api/docverify/r4';
  const $ = (s) => document.querySelector(s);
  const esc = DV.esc;
  let meta = null;
  let st = null;
  let presetList = [];
  let people = [];

  const iid = () => (DV.state.review && DV.state.review.id) || '';

  function mount(view) {
    const part = document.getElementById(`dvR4-${view}`);
    const host = document.querySelector(`.dv-view[data-view="${view}"]`);
    if (part && host && part.parentElement !== host) host.appendChild(part);
  }

  async function ensureMeta() {
    if (!meta) meta = await DV.api(`${P}/meta`);
    return meta;
  }

  async function load() {
    await ensureMeta();
    st = await DV.api(`${P}/inspections/${encodeURIComponent(iid())}`);
    people = (st.participants || []).map((p) => ({ ...p }));
    return st;
  }

  async function send(path, method, json) {
    try {
      st = await DV.api(`${P}/inspections/${encodeURIComponent(iid())}${path}`, { method, json: { ...json, rev: st.rev } });
      people = (st.participants || []).map((p) => ({ ...p }));
      return st;
    } catch (e) {
      if (e.status === 409 && e.data && e.data.code === 'conflict') await load();
      throw e;
    }
  }

  const options = (list, cur) => list.map((o) => `<option value="${esc(o.id)}"${o.id === cur ? ' selected' : ''}>${esc(o.label)}</option>`).join('');

  function renderPeople() {
    const roles = meta.roles;
    const rows = people.map((p, i) => `<tr><td><input type="text" data-i="${i}" data-k="name" value="${esc(p.name)}" aria-label="参加者の名前"></td>`
      + `<td><select data-i="${i}" data-k="role" aria-label="役割">${options(roles, p.role)}</select></td>`
      + `<td><button type="button" class="btn-outline-sm" data-del="${i}">外す</button></td></tr>`).join('');
    $('#dvR4People').innerHTML = `<thead><tr><th>名前</th><th>役割</th><th></th></tr></thead><tbody>${rows || '<tr><td colspan="3">参加者が登録されていません。参加者を追加してください。</td></tr>'}</tbody>`;
  }

  function renderPlanFields() {
    const t = st.type;
    $('#dvR4Legacy').hidden = !t.legacy;
    $('#dvR4Legacy').textContent = t.hint || '';
    $('#dvR4Type').innerHTML = `<option value="">選んでください</option>${options(meta.types, t.type)}`;
    $('#dvR4Required').textContent = t.legacy ? '' : `必須の役割: ${t.required.map((r) => (meta.roles.find((x) => x.id === r) || {}).label).join('・')}`;
    $('#dvR4Independent').checked = !!st.r4.independent;
    $('#dvR4ExitVerified').checked = !!st.exit_options.require_all_verified;
    $('#dvR4ExitDone').checked = !!st.exit_options.require_all_individual_done;
    $('#dvR4Preset').innerHTML = presetList.map((p) => `<option value="${esc(p.id)}"${p.id === st.r4.preset_id ? ' selected' : ''}>${esc(p.name)}${p.builtin ? '（既定）' : ''}</option>`).join('');
    renderPeople();
  }

  function renderFlow() {
    const errs = st.entry_errors || [];
    $('#dvR4Entry').innerHTML = errs.map((e) => `<li>${esc(e)}</li>`).join('');
    $('#dvR4Advance').disabled = !st.next_phase || errs.length > 0;
    const label = Object.fromEntries(DV.PHASES);
    const rows = (st.phase_log || []).map((e) => `<tr><td>${esc(label[e.phase] || e.phase)}</td><td>${esc(e.started_at)}</td><td>${esc(e.ended_at || '進行中')}</td><td>${esc(e.started_by || '—')}</td></tr>`).join('');
    $('#dvR4Log').innerHTML = `<thead><tr><th>工程</th><th>開始</th><th>終了</th><th>担当</th></tr></thead><tbody>${rows || '<tr><td colspan="4">工程の記録はまだありません。</td></tr>'}</tbody>`;
  }

  function renderEffort() {
    const prep = st.effort.prep || {};
    $('#dvR4Prep').innerHTML = people.map((p) => `<label>${esc(p.name)} の準備時間（分）<input type="number" min="0" step="1" data-prep="${esc(p.name)}" value="${esc(prep[p.name] ?? '')}"></label>`).join('')
      || '<p class="dv-r4-muted">参加者を登録すると準備時間を入れられます。</p>';
    $('#dvR4Meeting').value = st.effort.meeting_minutes || '';
    $('#dvR4Pages').value = st.r4.pages || '';
    $('#dvR4Kind').value = st.r4.doc_kind || '';
    const m = st.indicators;
    const val = (v, unit) => (v === null || v === undefined ? '—' : `${v} ${unit}`);
    let html = `<dl class="dv-r4-dl"><dt>工数の合計</dt><dd>${esc(st.effort.total_minutes)} 分</dd>`
      + `<dt>指摘密度</dt><dd>${esc(val(m.density, '件/頁'))}</dd><dt>検査速度</dt><dd>${esc(val(m.speed, '頁/時'))}</dd>`
      + `<dt>頁あたり工数</dt><dd>${esc(val(m.effort_per_page, '人時/頁'))}</dd>`
      + `<dt>重大度別（採用）</dt><dd>重大 ${esc(m.by_severity.critical)}・主要 ${esc(m.by_severity.major)}・軽微 ${esc(m.by_severity.minor)}</dd>`
      + `<dt>修正完了率</dt><dd>${m.fix_rate === null ? '—' : esc(Math.round(m.fix_rate * 100)) + ' %'}</dd></dl>`;
    html += (m.messages || []).map((t) => `<p class="dv-r4-muted">${esc(t)}</p>`).join('');
    const ref = m.reference;
    if (ref) {
      html += `<p class="${ref.attention ? 'dv-r4-warn' : 'dv-r4-muted'}">${esc(ref.label)}の参考範囲 ${esc(ref.low)}〜${esc(ref.high)} 件/頁`
        + `${ref.median === null ? '' : `（中央 ${esc(ref.median)}）`}: ${esc(ref.note)}</p>`
        + `<p class="dv-r4-muted">出典: ${esc(ref.source)}。${esc(ref.limit)}</p>`;
    }
    $('#dvR4Metrics').innerHTML = html;
  }

  async function showPlan() {
    mount('plan');
    if (!iid()) return;
    const [, pl] = await Promise.all([load(), DV.api(`${P}/presets`)]);
    presetList = pl.presets || [];
    renderPlanFields();
    renderFlow();
    renderEffort();
  }

  function showTriage() {
    mount('triage');
    if (!iid()) return Promise.resolve();
    return load().then(() => {
      const kinds = [{ id: '', label: '未選択' }, ...meta.kinds];
      $('#dvR4Hidden').hidden = !(st.r4.independent && st.phase === 'individual');
      const rows = (st.findings || []).map((f) => `<tr><td>${esc(f.id)}</td><td>${esc(f.message)}</td>`
        + `<td><select data-kind="${esc(f.id)}" aria-label="指摘 ${esc(f.id)} の種別">${options(kinds, f.kind || '')}</select></td></tr>`).join('');
      $('#dvR4Kinds').innerHTML = `<thead><tr><th>No.</th><th>指摘</th><th>種別</th></tr></thead><tbody>${rows || '<tr><td colspan="3">指摘はまだありません。</td></tr>'}</tbody>`;
    });
  }

  function showQuestions() { mount('questions'); }

  async function showGate() {
    mount('gate');
    if (!iid()) return;
    await load();
    const ap = st.approval;
    $('#dvR4Stale').hidden = !ap.stale;
    $('#dvR4Stale').textContent = ap.message || '';
    // 判定の記録は承認者だけ（サーバの権限表の approve と同じ判定）。押して 403 になる導線を作らない
    const canApprove = !DV.state.can || DV.state.can.approve !== false;
    const vs = $('#dvR4VerdictSave');
    vs.disabled = !canApprove;
    vs.title = canApprove ? '' : '判定を記録できるのは承認者です。議長（またはテナント管理者）に承認者として参加者へ追加してもらってください。';
    $('#dvR4Verdict').innerHTML = `<option value="">選んでください</option>${options(meta.verdicts, ap.verdict || '')}`;
    $('#dvR4Unchecked').innerHTML = (st.unchecked || []).map((i) => `<li>${esc(i.text)}</li>`).join('') || '<li>未確認の項目はありません。</li>';
    $('#dvR4Record').innerHTML = `<tbody>${(st.record || []).map((r) => `<tr><th scope="row">${esc(r[0])}</th><td>${esc(r[1])}</td></tr>`).join('')}</tbody>`;
    $('#dvR4Standards').innerHTML = meta.standards.map((s) => `<li>${esc(s.name)}（${esc(s.version)}）: ${esc(s.scope)}</li>`).join('');
    $('#dvR4StandardsNote').textContent = meta.standards_note;
  }

  const guard = (fn) => async (ev) => {
    try { await fn(ev); } catch (e) { /* 文は DV.api が帯に出している */ }
  };

  function bindPlan() {
    $('#dvR4AddPerson').addEventListener('click', () => { people = [...people, { name: '', role: 'reviewer', done: false }]; renderPeople(); });
    $('#dvR4People').addEventListener('input', (e) => {
      const i = Number(e.target.dataset.i);
      if (Number.isNaN(i)) return;
      people = people.map((p, n) => (n === i ? { ...p, [e.target.dataset.k]: e.target.value } : p));
    });
    $('#dvR4People').addEventListener('click', (e) => {
      if (e.target.dataset.del === undefined) return;
      const i = Number(e.target.dataset.del);
      people = people.filter((_, n) => n !== i);
      renderPeople();
    });
    $('#dvR4PlanSave').addEventListener('click', guard(async () => {
      await send('/plan', 'PUT', {
        review_type: $('#dvR4Type').value, participants: people, independent: $('#dvR4Independent').checked,
        exit_options: { require_all_verified: $('#dvR4ExitVerified').checked, require_all_individual_done: $('#dvR4ExitDone').checked },
      });
      DV.toast('計画を保存しました。');
      await showPlan();
    }));
    $('#dvR4Advance').addEventListener('click', guard(async () => { await send('/advance', 'POST', {}); DV.toast('次の工程へ進めました。'); await showPlan(); }));
    $('#dvR4EffortSave').addEventListener('click', guard(async () => {
      const prep = {};
      document.querySelectorAll('#dvR4Prep [data-prep]').forEach((el) => { if (el.value !== '') prep[el.dataset.prep] = Number(el.value); });
      const pages = $('#dvR4Pages').value;
      await send('/effort', 'PUT', { prep, meeting_minutes: Number($('#dvR4Meeting').value || 0), pages: pages ? Number(pages) : null, doc_kind: $('#dvR4Kind').value || null });
      DV.toast('工数を保存しました。');
      renderEffort();
    }));
    bindPresets();
  }

  function bindPresets() {
    $('#dvR4PresetUse').addEventListener('click', guard(async () => { await send('/preset', 'POST', { preset_id: $('#dvR4Preset').value }); DV.toast('観点プリセットを読み込みました。'); await showPlan(); }));
    $('#dvR4PresetCopy').addEventListener('click', guard(async () => {
      await DV.api(`${P}/presets/${encodeURIComponent($('#dvR4Preset').value)}/copy`, { method: 'POST', json: {} });
      DV.toast('プリセットを複製しました。');
      await showPlan();
    }));
    $('#dvR4PresetDelete').addEventListener('click', guard(async () => {
      await DV.api(`${P}/presets/${encodeURIComponent($('#dvR4Preset').value)}`, { method: 'DELETE' });
      DV.toast('プリセットを削除しました。');
      await showPlan();
    }));
  }

  function bindOthers() {
    $('#dvR4Kinds').addEventListener('change', guard(async (e) => {
      const fid = e.target.dataset.kind;
      if (!fid || !e.target.value) return;
      await send(`/findings/${encodeURIComponent(fid)}/kind`, 'POST', { kind: e.target.value });
      DV.toast('指摘の種別を記録しました。');
    }));
    $('#dvR4AnsImport').addEventListener('click', guard(async () => {
      const file = $('#dvR4AnsFile').files[0];
      if (!file) { DV.banner('回答を書き込んだ質問票（CSV か Excel）を選んでください。'); return; }
      await load();
      const form = new FormData();
      form.append('file', file);
      form.append('rev', String(st.rev));
      const res = await DV.api(`${P}/inspections/${encodeURIComponent(iid())}/answers`, { method: 'POST', form });
      $('#dvR4AnsResult').textContent = `${res.applied} 件の回答を反映しました。${res.message ? ` ${res.message}` : ''}`;
    }));
    $('#dvR4VerdictSave').addEventListener('click', guard(async () => {
      await send('/verdict', 'POST', { verdict: $('#dvR4Verdict').value, approver: $('#dvR4Approver').value, decided_at: $('#dvR4Decided').value });
      DV.toast('判定を記録しました。');
      await showGate();
    }));
    $('#dvR4RecordXlsx').addEventListener('click', guard(() => DV.download(`${P}/inspections/${encodeURIComponent(iid())}/record.xlsx`, `review-record-${iid()}.xlsx`)));
    $('#dvR4AuditVerify').addEventListener('click', guard(async () => {
      const r = await DV.api(`${P}/audit/verify`);
      $('#dvR4AuditResult').textContent = r.message;
    }));
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (!$('#dvR4Parts')) return;
    bindPlan();
    bindOthers();
    DV.on('plan', guard(showPlan));
    DV.on('triage', guard(showTriage));
    DV.on('questions', showQuestions);
    // 判定と記録は対検査の Gate API に一本化した（docverify-cases.js・S06 r2）。旧来の独自判定は描かない
  });
})();
