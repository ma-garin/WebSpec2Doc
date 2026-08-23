// ---- 無反応ボタンの解消（全画面共通） ----
// 受け手の無いボタンが押下時に沈黙する問題への対処。
// 本来の機能が実装されるまでの間も、利用者に必ず状態を返す。
// 機能実装時は、この表から当該 id を削除すれば個別ハンドラが優先される。
(function () {
  const UNIMPLEMENTED = new Set(["hero-sample-btn", "onboarding-demo-btn", "sample-url-btn", "ta-analysis-trace-check", "ta-completion-lesson-add", "ta-completion-report", "ta-defect-analyze", "ta-defect-rca-save", "ta-defect-rca-suggest", "ta-defect-reload", "ta-defect-sync", "ta-design-export", "ta-design-generate", "ta-detail-condition-add", "ta-detail-expand", "ta-detail-reset", "ta-exec-export", "ta-exec-log-clear", "ta-exec-schedule", "ta-exec-stop", "ta-fix-generate", "ta-fix-impact-run", "ta-fix-open-defect", "ta-fix-pr", "ta-fix-reload", "ta-impl-generate", "ta-impl-import", "ta-impl-pr", "ta-impl-reload", "ta-impl-select-all", "ta-int-code-connect", "ta-int-docs-connect", "ta-int-github-connect", "ta-int-github-save", "ta-int-standard-connect", "ta-int-standard-upload", "ta-int-test-all", "ta-pipeline-reload", "ta-plan-estimate-recalc", "ta-plan-generate", "ta-plan-save", "ta-recent-reload", "ta-start-btn"]);

  function _notice(message, isError) {
    let box = document.getElementById('app-global-notice');
    if (!box) {
      box = document.createElement('div');
      box.id = 'app-global-notice';
      box.className = 'app-global-notice';
      box.setAttribute('role', 'status');
      box.setAttribute('aria-live', 'polite');
      document.body.appendChild(box);
    }
    box.textContent = message;
    box.classList.toggle('is-error', Boolean(isError));
    box.classList.add('is-visible');
    window.clearTimeout(_notice._timer);
    _notice._timer = window.setTimeout(() => box.classList.remove('is-visible'), 4000);
  }

  // 他のハンドラが先に処理した場合に備え、バブリング後（最後）に評価する。
  document.addEventListener('click', (ev) => {
    const btn = ev.target && ev.target.closest ? ev.target.closest('button[id]') : null;
    if (!btn || !UNIMPLEMENTED.has(btn.id)) return;
    if (ev.defaultPrevented) return;
    const label = (btn.textContent || '').trim() || btn.id;
    _notice('「' + label + '」はまだ実装されていません。', true);
  });

  window.appNotice = _notice;
})();
