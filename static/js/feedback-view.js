/* フィードバックビュー（#view-feedback）。
 *
 * 以前はモーダルだったが、個人設定・ユーザーガイドと表示方法を揃えるため
 * 画面内ビューにした。送信してもビューは閉じない（自分自身が画面のため）。
 * 入力欄を空にして完了メッセージを出し、その場に留まる。
 *
 * core.js の switchView('feedback') から prepareFeedbackView() が呼ばれる。
 */
(function () {
  'use strict';

  const view = document.getElementById('view-feedback');
  const form = document.getElementById('feedback-form');
  if (!view || !form) return;

  const messageInput = document.getElementById('feedback-message');
  const counter = document.getElementById('feedback-count');
  const statusBox = document.getElementById('feedback-status');
  const submitBtn = document.getElementById('feedback-submit-btn');

  function setStatus(text, kind) {
    if (!statusBox) return;
    statusBox.textContent = text || '';
    statusBox.hidden = !text;
    statusBox.classList.toggle('is-error', kind === 'error');
    statusBox.classList.toggle('is-success', kind === 'success');
  }

  /* このビュー自身が画面になったので「今いる画面」は使えない。
     ユーザーメニューが遷移前に控えた画面名を使い、無ければ空で送る。 */
  function originView() {
    return window.__feedbackOriginView || '';
  }

  function prepare() {
    setStatus('', null);

    const userName = document.querySelector('.usermenu-name');
    const userMail = document.querySelector('.usermenu-mail');
    const metaUser = document.getElementById('feedback-meta-user');
    const metaView = document.getElementById('feedback-meta-view');
    if (metaUser) {
      const name = userName ? userName.textContent.trim() : '';
      const mail = userMail ? userMail.textContent.trim() : '';
      metaUser.textContent = mail && mail !== name ? `${name}（${mail}）` : name || '-';
    }
    if (metaView) metaView.textContent = originView() || '-';
    if (messageInput) messageInput.focus();
  }

  window.prepareFeedbackView = prepare;

  function clearInput() {
    if (messageInput) messageInput.value = '';
    if (counter) counter.textContent = '0';
  }

  messageInput?.addEventListener('input', () => {
    if (counter) counter.textContent = String(messageInput.value.length);
  });

  document.getElementById('feedback-clear-btn')?.addEventListener('click', () => {
    clearInput();
    setStatus('', null);
    messageInput?.focus();
  });

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const checked = form.querySelector('input[name="feedback-category"]:checked');
    const category = checked ? checked.value : '';
    const message = messageInput ? messageInput.value.trim() : '';

    // 送ってから弾かれるより、その場で気づけるほうが速い
    if (!message) {
      setStatus('内容を入力してください。', 'error');
      messageInput?.focus();
      return;
    }

    if (submitBtn) submitBtn.disabled = true;
    setStatus('送信中…', null);
    try {
      const response = await fetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category, message, view: originView() })
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setStatus(data.error || '送信に失敗しました。', 'error');
        return;
      }
      setStatus('送信しました。ありがとうございます。', 'success');
      // 送信済みの内容が残っていると二重送信を招くので消す
      clearInput();
    } catch (err) {
      setStatus('通信に失敗しました。接続を確認してもう一度お試しください。', 'error');
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  });
})();
