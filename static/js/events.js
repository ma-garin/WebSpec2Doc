// ---- イベントリスナー ----
document.getElementById('autorun-start-btn')?.addEventListener('click', autorunStart);
document.getElementById('autorun-approve-btn')?.addEventListener('click', autorunApprove);
document.getElementById('autorun-cancel-btn')?.addEventListener('click', autorunCancel);
document.getElementById('autorun-restart-btn')?.addEventListener('click', autorunReset);
document.getElementById('autorun-login-submit')?.addEventListener('click', () => _autorunSubmitLogin(false));
document.getElementById('autorun-login-skip')?.addEventListener('click',   () => _autorunSubmitLogin(true));
document.getElementById('autorun-login-close')?.addEventListener('click',  () => _autorunSubmitLogin(true));
document.getElementById('autorun-login-overlay')?.addEventListener('click',() => _autorunSubmitLogin(true));
document.getElementById('autorun-login-password')?.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') _autorunSubmitLogin(false);
});
// プレビュータブ切り替え
document.querySelectorAll('.autorun-preview-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    const tab = btn.dataset.ptab;
    document.querySelectorAll('.autorun-preview-tab').forEach(b => b.classList.remove('is-active'));
    btn.classList.add('is-active');
    document.getElementById('autorun-ptab-cases').style.display  = (tab === 'cases')  ? '' : 'none';
    document.getElementById('autorun-ptab-script').style.display = (tab === 'script') ? '' : 'none';
  });
});
