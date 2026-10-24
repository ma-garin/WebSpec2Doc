/* System 06 画面枠の補助（監査 D-07・D-15）。表示の補助だけで、保存の処理は各画面の JS が持つ */
(function () {
  'use strict';
  function enhance(inp) {
    if (inp.dataset.dvFile) return;
    inp.dataset.dvFile = '1';
    const lab = inp.closest('label');
    const cap = lab && lab.querySelector('span');
    const word = cap && cap.textContent.trim();
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'p1-btn dv-file-btn';
    btn.textContent = word ? word + 'を選ぶ' : 'ファイルを選ぶ';
    const name = document.createElement('span');
    name.className = 'dv-file-name';
    name.textContent = '未選択';
    btn.addEventListener('click', (e) => { e.preventDefault(); e.stopPropagation(); inp.click(); });
    const show = () => { name.textContent = inp.files && inp.files[0] ? inp.files[0].name : '未選択'; };
    inp.addEventListener('change', show);
    if (inp.form) inp.form.addEventListener('reset', () => setTimeout(show, 0));
    inp.classList.add('dv-file-native');
    inp.tabIndex = -1;
    inp.after(btn, name);
    if (cap && word) cap.hidden = true;
  }
  function init() {
    document.querySelectorAll('.app-content input[type=file]').forEach(enhance);
    document.addEventListener('click', (e) => {
      if (!e.target.closest('[data-view="plan"] [data-act="save"]')) return;
      const other = document.getElementById('dvR4PlanSave');
      if (other) setTimeout(() => other.click(), 0);
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
