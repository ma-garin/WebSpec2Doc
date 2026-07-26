// ---- イベントリスナー ----
document.getElementById('autorun-start-btn')?.addEventListener('click', autorunStart);
// 開始できない理由は、押す前に出す（押してから叱らない）。
['autorun-url', 'autorun-target-page-id', 'autorun-selection-criterion'].forEach((id) => {
  const el = document.getElementById(id);
  if (!el) return;
  el.addEventListener('input', autorunSyncStartButton);
  el.addEventListener('change', autorunSyncStartButton);
});
if (typeof autorunSyncStartButton === 'function') autorunSyncStartButton();
document.getElementById('autorun-restart-btn')?.addEventListener('click', autorunReset);
// 旧「テスト実行の設定」モーダル（awaiting_approval の第3関門）は廃止済み。
// バックエンドが当該ステータスを設定しなくなり到達不能となった一方、非表示のまま
// DOM に残って同名セレクタを衝突させていたため、マークアップごと削除した。
// 実行条件の指定は autorun-decisions.js（実行条件の確認ダイアログ）に一本化する。
// ログインモーダル: スキップは「スキップ」ボタンのみ。✕・背景クリックの誤操作でスキップさせない。
document.getElementById('autorun-login-submit')?.addEventListener('click', () => _autorunSubmitLogin(false));
document.getElementById('autorun-login-skip')?.addEventListener('click',   () => _autorunSubmitLogin(true));
document.getElementById('autorun-login-close')?.addEventListener('click',  autorunDismissLoginModal);
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
