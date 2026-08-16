/* フィードバックビュー（#view-feedback）。
 *
 * 以前はモーダルだったが、個人設定・ユーザーガイドと表示方法を揃えるため
 * 画面内ビューにした。送信してもビューは閉じない（自分自身が画面のため）。
 * 入力欄を空にして完了メッセージを出し、その場に留まる。
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

  const status = (text, kind) => setViewStatus(statusBox, text, kind);

  /* このビュー自身が画面になったので「今いる画面」は使えない。
     直前のビューは core.js の switchView が持っている。 */
  const originView = () => previousViewLabel();

  function prepare() {
    status('', null);

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

  onViewEnter('feedback', prepare);

  function clearInput() {
    if (messageInput) messageInput.value = '';
    if (counter) counter.textContent = '0';
  }

  messageInput?.addEventListener('input', () => {
    if (counter) counter.textContent = String(messageInput.value.length);
  });

  document.getElementById('feedback-clear-btn')?.addEventListener('click', () => {
    clearInput();
    status('', null);
    messageInput?.focus();
  });

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const checked = form.querySelector('input[name="feedback-category"]:checked');
    const category = checked ? checked.value : '';
    const message = messageInput ? messageInput.value.trim() : '';

    // 送ってから弾かれるより、その場で気づけるほうが速い
    if (!message) {
      status('内容を入力してください。', 'error');
      messageInput?.focus();
      return;
    }

    if (submitBtn) submitBtn.disabled = true;
    status('送信中…', null);
    try {
      await apiJSON('/api/feedback', 'POST', { category, message, view: originView() });
      status('送信しました。ありがとうございます。', 'success');
      // 送信済みの内容が残っていると二重送信を招くので消す
      clearInput();
    } catch (err) {
      status(err.message, 'error');
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  });
})();
