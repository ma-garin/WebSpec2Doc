// 初回オンボーディング（driver.js は static/vendor に固定版を同梱）。
(function () {
  'use strict';

  const TOUR_KEY = 'webspec2doc.onboarding.tour-completed';
  const REPORT_KEY = 'webspec2doc.onboarding.report-viewed';
  const DEMO_URL = 'http://127.0.0.1:8766/';
  let onboardingState = { checklist: {} };
  let activeTour = null;
  let tourFinishing = false;

  function setChecklistVisible(visible) {
    const checklist = document.getElementById('onboarding-checklist');
    if (checklist) checklist.hidden = !visible;
  }

  function readLocal(key) {
    try { return localStorage.getItem(key) === '1'; } catch (e) { return false; }
  }

  function writeLocal(key) {
    try { localStorage.setItem(key, '1'); } catch (e) { /* private modeなどでは保存しない */ }
  }

  function renderChecklist() {
    const checklist = onboardingState.checklist || {};
    const states = {
      site_registered: Boolean(checklist.site_registered),
      first_crawl: Boolean(checklist.first_crawl),
      report_viewed: Boolean(checklist.report_available && readLocal(REPORT_KEY)),
    };
    Object.entries(states).forEach(([name, complete]) => {
      const row = document.querySelector(`[data-onboarding-state="${name}"]`);
      if (!row) return;
      row.classList.toggle('is-complete', complete);
      const marker = row.querySelector('.onboarding-check');
      if (marker) marker.textContent = complete ? '✓' : String(Object.keys(states).indexOf(name) + 1);
      row.setAttribute('aria-label', `${row.querySelector('strong')?.textContent || name}: ${complete ? '完了' : '未完了'}`);
    });
  }

  async function loadOnboarding() {
    try {
      const response = await fetch('/api/onboarding', { headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      onboardingState = await response.json();
    } catch (e) {
      onboardingState = { storage: 'client', tour_completed: null, checklist: {} };
    }
    renderChecklist();
    return onboardingState;
  }

  async function persistTourCompletion() {
    writeLocal(TOUR_KEY);
    try {
      await fetch('/api/onboarding/complete', {
        method: 'POST',
        headers: { Accept: 'application/json' },
      });
    } catch (e) { /* 認証なし・一時的な通信断では端末側の完了状態を使う */ }
  }

  function finishTour() {
    if (tourFinishing) return;
    tourFinishing = true;
    setChecklistVisible(false);
    void persistTourCompletion();
  }

  function addSkipButton(popover, opts) {
    popover.closeButton.setAttribute('aria-label', '操作ツアーをスキップ');
    popover.closeButton.setAttribute('title', 'スキップ');
    if (popover.footerButtons.querySelector('.wsd-tour-skip')) return;
    const skip = document.createElement('button');
    skip.type = 'button';
    skip.className = 'wsd-tour-skip';
    skip.textContent = 'スキップ';
    skip.addEventListener('click', () => {
      finishTour();
      opts.driver.destroy();
    });
    popover.footerButtons.prepend(skip);
  }

  function startTour() {
    const driverFactory = window.driver && window.driver.js && window.driver.js.driver;
    if (!driverFactory) {
      if (typeof showToast === 'function') showToast('操作ツアーを読み込めませんでした', 'error');
      return;
    }
    if (activeTour && activeTour.isActive()) activeTour.destroy();
    tourFinishing = false;
    if (typeof switchView === 'function') switchView('dashboard');
    setChecklistVisible(true);

    activeTour = driverFactory({
      animate: true,
      allowClose: true,
      allowKeyboardControl: true,
      overlayClickBehavior: 'close',
      popoverClass: 'wsd-onboarding-popover',
      showProgress: true,
      progressText: '{{current}} / {{total}}',
      nextBtnText: '次へ',
      prevBtnText: '戻る',
      doneBtnText: '始める',
      onPopoverRender: addSkipButton,
      onDestroyed: finishTour,
      steps: [
        {
          element: '#hero-url',
          popover: {
            title: '1. 対象サイトを入力',
            description: '解析するWebサイトのURLを入力します。まずは同梱デモサイトでも試せます。',
            side: 'bottom',
            align: 'start',
          },
        },
        {
          element: '#hero-start-btn',
          popover: {
            title: '2. 解析を開始',
            description: '画面を収集し、仕様書・テスト設計・技術ヘルス・アクセシビリティ監査を生成します。',
            side: 'bottom',
            align: 'end',
          },
        },
        {
          element: '#onboarding-checklist',
          popover: {
            title: '3. 最初の成功まで確認',
            description: 'サイト登録、初回クロール、レポート確認の進み具合をここで追跡できます。',
            side: 'top',
            align: 'center',
          },
        },
        {
          element: '#nav-run-history-btn',
          popover: {
            title: '4. 継続運用へ',
            description: '実行履歴から結果を確認できます。設定の「運用監視」では定期実行と通知も設定できます。',
            side: 'right',
            align: 'center',
          },
        },
      ],
    });
    window.setTimeout(() => activeTour.drive(), 80);
  }

  function useDemoSite() {
    if (typeof switchView === 'function') switchView('dashboard');
    const input = document.getElementById('hero-url');
    if (input) {
      input.value = DEMO_URL;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.focus();
    }
    if (typeof showToast === 'function') {
      showToast('デモURLを入力しました。未起動の場合はターミナルで make demo を実行してください。', 'success');
    }
  }

  document.addEventListener('click', (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (target?.closest('[data-onboarding-demo]')) useDemoSite();
    if (target?.closest('.hist-open, #popup-view-report-btn')) {
      document.dispatchEvent(new CustomEvent('webspec2doc:report-viewed'));
    }
  });

  document.addEventListener('webspec2doc:report-viewed', () => {
    writeLocal(REPORT_KEY);
    onboardingState.checklist = {
      ...(onboardingState.checklist || {}),
      site_registered: true,
      first_crawl: true,
      report_available: true,
    };
    renderChecklist();
  });

  document.getElementById('restart-tour')?.addEventListener('click', startTour);

  void loadOnboarding().then((state) => {
    const completed = state.storage === 'server' ? Boolean(state.tour_completed) : readLocal(TOUR_KEY);
    if (state.auto_start !== false && !completed) startTour();
  });
})();
