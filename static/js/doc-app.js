/*
 * ドキュメント作成(app) — モック用 JS。
 * サーバ呼び出しは一切行わない（fetch 禁止）。画面の流れと入力の確認のみを目的とする。
 * 実装時は /api/app-discover（解析）と /api/app-generate（生成）に置き換える想定。
 * ここでは MOCK データと setTimeout による擬似進捗でパネル1〜4を遷移させる。
 */
(function () {
  'use strict';

  var MOCK = {
    android: {
      id: 'com.example.sampleshop',
      name: 'SampleShop',
      screens: [
        { name: 'スプラッシュ', cls: 'SplashActivity', fields: 0 },
        { name: 'ログイン', cls: 'LoginActivity', fields: 2 },
        { name: 'ホーム', cls: 'HomeActivity', fields: 1 },
        { name: '商品一覧', cls: 'ProductListFragment', fields: 1 },
        { name: '商品詳細', cls: 'ProductDetailActivity', fields: 1 },
        { name: 'カート', cls: 'CartActivity', fields: 1 },
        { name: '購入手続き', cls: 'CheckoutActivity', fields: 5 },
        { name: '注文完了', cls: 'OrderCompleteActivity', fields: 0 },
        { name: '設定', cls: 'SettingsActivity', fields: 3 }
      ],
      transitions: 18,
      unreached: ['DebugMenuActivity', 'CouponActivity']
    },
    ios: {
      id: 'com.example.SampleShop',
      name: 'SampleShop',
      screens: [
        { name: 'スプラッシュ', cls: 'SplashViewController', fields: 0 },
        { name: 'ログイン', cls: 'LoginViewController', fields: 2 },
        { name: 'ホーム', cls: 'HomeViewController', fields: 1 },
        { name: '商品一覧', cls: 'ProductListViewController', fields: 1 },
        { name: '商品詳細', cls: 'ProductDetailViewController', fields: 1 },
        { name: 'カート', cls: 'CartViewController', fields: 1 },
        { name: '購入手続き', cls: 'CheckoutViewController', fields: 5 },
        { name: '注文完了', cls: 'OrderCompleteViewController', fields: 0 },
        { name: '設定', cls: 'SettingsViewController', fields: 3 }
      ],
      transitions: 18,
      unreached: ['DebugMenuViewController', 'CouponViewController']
    }
  };

  var DEVICE_APPS = {
    android: [
      { id: 'com.example.sampleshop', name: 'SampleShop' },
      { id: 'com.example.samplebank', name: 'SampleBank' },
      { id: 'com.example.samplenews', name: 'SampleNews' }
    ],
    ios: [
      { id: 'com.example.SampleShop', name: 'SampleShop' },
      { id: 'com.example.SampleBank', name: 'SampleBank' },
      { id: 'com.example.SampleNews', name: 'SampleNews' }
    ]
  };

  var DEVICES = {
    android: ['エミュレータ Pixel 8 (API 34)', '実機 (adb 接続)'],
    ios: ['iPhone 15 シミュレータ (iOS 17.5)', 'iPad (10th) シミュレータ']
  };

  var DISCOVER_LOG_STEPS = [
    'アプリをインストール中',
    '起動・初期画面を取得',
    'マニフェストから Activity 一覧を抽出（静的）',
    '画面を探索中 1/3',
    '画面を探索中 2/3',
    '画面を探索中 3/3',
    '未到達 Activity を照合',
    '完了'
  ];

  var RUN_STAGES = [
    '画面を再取得',
    'フォーム項目を抽出',
    '遷移を確定',
    'テスト条件を組み立て',
    '文書を書き出し'
  ];

  var state = {
    platform: 'android',
    source: 'file',
    fileChosen: false,
    deviceAppId: '',
    discoverTimer: null,
    discoverDone: false,
    selectedScreens: [],
    runTimer: null,
    discoverClock: null,
    runClock: null
  };

  // 端末画面のモック描画。実装では /api/live-screenshot 相当の画像に置き換わる。
  var FIELD_LABELS = {
    'ログイン': ['メールアドレス', 'パスワード'],
    'ホーム': ['検索'],
    '商品一覧': ['絞り込み'],
    '商品詳細': ['数量'],
    'カート': ['クーポンコード'],
    '購入手続き': ['氏名', '郵便番号', '住所', '電話番号', 'カード番号'],
    '設定': ['通知', '言語', 'テーマ']
  };
  var SCREEN_BUTTONS = {
    'ログイン': 'ログイン', '商品詳細': 'カートに入れる', 'カート': '購入手続きへ',
    '購入手続き': '注文を確定', '注文完了': 'ホームへ戻る', '設定': '保存'
  };

  function escHtml(v) {
    return String(v).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function renderPhone(containerId, screen) {
    var el = $(containerId);
    if (!el) return;
    var isIos = state.platform === 'ios';
    var labels = FIELD_LABELS[screen.name] || [];
    var h = '';
    h += '<div class="da-ms-status"><span>' + (isIos ? '9:41' : '12:30') + '</span><span>▲ ▮</span></div>';
    h += '<div class="da-ms-appbar">' + (isIos ? '<span class="da-ms-icon">‹</span>' : '<span class="da-ms-icon">≡</span>') +
      '<span class="da-ms-title">' + escHtml(screen.name) + '</span></div>';
    h += '<div class="da-ms-body">';
    if (screen.name === 'スプラッシュ') {
      h += '<div class="da-ms-logo">' + escHtml(currentMock().name) + '</div>';
    } else if (screen.name === '注文完了') {
      h += '<div class="da-ms-done">✓</div><div class="da-ms-text">ご注文ありがとうございます</div>';
    } else if (screen.name === 'ホーム' || screen.name === '商品一覧') {
      h += '<div class="da-ms-field is-search">' + escHtml(labels[0] || '検索') + '</div>';
      for (var i = 0; i < 4; i++) h += '<div class="da-ms-card"><span class="da-ms-thumb"></span><span class="da-ms-lines"><span></span><span></span></span></div>';
    } else {
      for (var j = 0; j < labels.length; j++) {
        h += '<div class="da-ms-label">' + escHtml(labels[j]) + '</div><div class="da-ms-field"></div>';
      }
    }
    var btn = SCREEN_BUTTONS[screen.name];
    if (btn) h += '<div class="da-ms-btn">' + escHtml(btn) + '</div>';
    h += '</div>';
    h += '<div class="da-ms-nav"><span class="is-on">ホーム</span><span>検索</span><span>カート</span><span>設定</span></div>';
    el.innerHTML = h;
    el.className = 'da-phone-screen' + (isIos ? ' is-ios' : '');
  }

  function formatClock(sec) {
    var m = Math.floor(sec / 60), s = sec % 60;
    return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
  }

  function stopTimers() {
    if (state.discoverTimer) { clearInterval(state.discoverTimer); state.discoverTimer = null; }
    if (state.discoverClock) { clearInterval(state.discoverClock); state.discoverClock = null; }
    if (state.runTimer) { clearInterval(state.runTimer); state.runTimer = null; }
    if (state.runClock) { clearInterval(state.runClock); state.runClock = null; }
  }

  function $(id) {
    return document.getElementById(id);
  }

  function currentMock() {
    return MOCK[state.platform] || MOCK.android;
  }

  function setHidden(el, hidden) {
    if (!el) return;
    if (hidden) {
      el.setAttribute('hidden', 'hidden');
    } else {
      el.removeAttribute('hidden');
    }
  }

  function clearError() {
    var err = $('da-error');
    if (err) {
      err.textContent = '';
      setHidden(err, true);
    }
  }

  function showError(msg) {
    var err = $('da-error');
    if (err) {
      err.textContent = msg;
      setHidden(err, false);
    }
  }

  function populateDeviceSelect() {
    var sel = $('da-device');
    if (!sel) return;
    var list = DEVICES[state.platform] || DEVICES.android;
    sel.innerHTML = '';
    for (var i = 0; i < list.length; i++) {
      var opt = document.createElement('option');
      opt.value = list[i];
      opt.textContent = list[i];
      sel.appendChild(opt);
    }
  }

  function populateDeviceAppSelect() {
    var sel = $('da-device-app');
    if (!sel) return;
    var list = DEVICE_APPS[state.platform] || DEVICE_APPS.android;
    sel.innerHTML = '';
    for (var i = 0; i < list.length; i++) {
      var opt = document.createElement('option');
      opt.value = list[i].id;
      opt.textContent = list[i].name + ' (' + list[i].id + ')';
      sel.appendChild(opt);
    }
    if (list.length > 0) {
      state.deviceAppId = list[0].id;
      if (state.source === 'device') {
        var idInput = $('da-app-id');
        if (idInput) idInput.value = state.deviceAppId;
      }
    }
  }

  function applyPlatform() {
    var fileInput = $('da-file');
    if (fileInput) {
      fileInput.setAttribute('accept', state.platform === 'ios' ? '.app,.zip' : '.apk,.aab');
    }
    populateDeviceSelect();
    var idInput = $('da-app-id');
    if (idInput) {
      idInput.setAttribute('placeholder', currentMock().id);
    }
    if (state.source === 'device') {
      populateDeviceAppSelect();
    }
  }

  function applySource() {
    setHidden($('da-source-file'), state.source !== 'file');
    setHidden($('da-source-device'), state.source !== 'device');
    if (state.source === 'device') {
      populateDeviceAppSelect();
      var idInput = $('da-app-id');
      if (idInput) idInput.value = state.deviceAppId;
    }
  }

  function bindPlatformToggle() {
    var radios = document.getElementsByName('da-platform');
    for (var i = 0; i < radios.length; i++) {
      radios[i].addEventListener('change', function (e) {
        if (e.target && e.target.checked) {
          state.platform = e.target.value;
          applyPlatform();
        }
      });
    }
  }

  function bindSourceToggle() {
    var radios = document.getElementsByName('da-source');
    for (var i = 0; i < radios.length; i++) {
      radios[i].addEventListener('change', function (e) {
        if (e.target && e.target.checked) {
          state.source = e.target.value;
          applySource();
        }
      });
    }
  }

  function bindFileInput() {
    var fileInput = $('da-file');
    if (!fileInput) return;
    fileInput.addEventListener('change', function () {
      var nameSpan = $('da-file-name');
      if (fileInput.files && fileInput.files.length > 0) {
        state.fileChosen = true;
        var fname = fileInput.files[0].name;
        if (nameSpan) nameSpan.textContent = fname;
        var idInput = $('da-app-id');
        if (idInput) idInput.value = currentMock().id;
      } else {
        state.fileChosen = false;
        if (nameSpan) nameSpan.textContent = '';
      }
    });
  }

  function bindDeviceAppSelect() {
    var sel = $('da-device-app');
    if (!sel) return;
    sel.addEventListener('change', function () {
      state.deviceAppId = sel.value;
      var idInput = $('da-app-id');
      if (idInput) idInput.value = sel.value;
    });
  }

  function bindScopeToggle() {
    var radios = document.getElementsByName('da-scope');
    for (var i = 0; i < radios.length; i++) {
      radios[i].addEventListener('change', function (e) {
        if (e.target && e.target.checked) {
          setHidden($('da-scope-custom-fields'), e.target.value !== 'custom');
        }
      });
    }
  }

  function resetDiscoverUI() {
    setHidden($('da-discover-progress'), true);
    setHidden($('da-discover-cancel-btn'), true);
    var btn = $('da-discover-btn');
    if (btn) btn.disabled = false;
    var bar = $('da-discover-bar');
    if (bar) bar.style.width = '0%';
    var log = $('da-discover-log');
    if (log) log.innerHTML = '';
  }

  function startDiscover() {
    clearError();
    var hasFile = state.source === 'file' && state.fileChosen;
    var hasDeviceApp = state.source === 'device' && state.deviceAppId;
    if (!hasFile && !hasDeviceApp) {
      showError('アプリファイルを選択するか、端末のアプリを選択してください。');
      return;
    }
    stopTimers();
    setHidden($('da-p1-summary'), true);
    setHidden($('da-discover-progress'), false);
    // 入力欄が長く、ライブカードは画面下にある。開始した瞬間に見える位置へ寄せる（実物は URL 欄の直下に出る）。
    var card = $('da-discover-progress');
    if (card && card.scrollIntoView) card.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    var btn = $('da-discover-btn');
    if (btn) btn.disabled = true;
    setHidden($('da-discover-cancel-btn'), false);
    setHidden($('da-discover-spinner'), false);
    var log = $('da-discover-log');
    if (log) log.innerHTML = '';
    var bar = $('da-discover-bar');
    if (bar) bar.style.width = '0%';
    setText('da-discover-count', '0画面を発見');
    setText('da-discover-elapsed', '0秒');
    var preview = $('da-discover-preview');
    if (preview) preview.innerHTML = '<div class="da-ms-boot">起動中…</div>';

    // 実物と同じ順: 受付 → 起動 → 静的解析 → 1 画面ずつ探索（ここでプレビューが切り替わる）→ 照合
    var mock = currentMock();
    var plan = [
      { phase: 'アプリをインストールしています…' },
      { phase: '起動して初期画面を取得しています…' },
      { phase: 'マニフェストから Activity 一覧を抽出しています（静的）…' }
    ];
    for (var i = 0; i < mock.screens.length; i++) plan.push({ phase: '画面を探索しています: ' + mock.screens[i].name, screen: mock.screens[i], n: i + 1 });
    plan.push({ phase: '未到達 Activity を照合しています…' });
    plan.push({ phase: '完了', done: true });

    var started = Date.now();
    state.discoverClock = setInterval(function () {
      setText('da-discover-elapsed', Math.round((Date.now() - started) / 1000) + '秒');
    }, 1000);

    var idx = 0;
    state.discoverTimer = setInterval(function () {
      var step = plan[idx];
      setText('da-discover-phase', step.phase);
      if (step.screen) {
        renderPhone('da-discover-preview', step.screen);
        setText('da-discover-caption', 'ライブプレビュー: ' + step.screen.cls);
        setText('da-discover-count', step.n + '画面を発見');
        if (log) {
          var li = document.createElement('li');
          li.className = 'da-feed-row';
          li.innerHTML = '<span class="da-feed-no">' + step.n + '</span><span class="da-feed-name">' + escHtml(step.screen.name) + '</span>' +
            '<code class="da-feed-cls">' + escHtml(step.screen.cls) + '</code><span class="da-feed-meta">入力 ' + step.screen.fields + '</span>';
          log.appendChild(li);
          log.scrollTop = log.scrollHeight;
        }
      }
      idx++;
      if (bar) bar.style.width = Math.round((idx / plan.length) * 100) + '%';
      if (step.done) {
        clearInterval(state.discoverTimer); state.discoverTimer = null;
        clearInterval(state.discoverClock); state.discoverClock = null;
        finishDiscover();
      }
    }, 380);
  }

  function finishDiscover() {
    state.discoverDone = true;
    var btn = $('da-discover-btn');
    if (btn) btn.disabled = false;
    setHidden($('da-discover-cancel-btn'), true);
    setHidden($('da-discover-spinner'), true);
    var mock = currentMock();
    var totalFields = 0;
    for (var i = 0; i < mock.screens.length; i++) {
      totalFields += mock.screens[i].fields;
    }
    setText('da-stat-screens', mock.screens.length);
    setText('da-stat-transitions', mock.transitions);
    setText('da-stat-fields', totalFields);
    setText('da-stat-unreached', mock.unreached.length);
    setHidden($('da-p1-summary'), false);
  }

  function cancelDiscover() {
    stopTimers();
    resetDiscoverUI();
  }

  function setText(id, val) {
    var el = $(id);
    if (el) el.textContent = String(val);
  }

  function bindDiscover() {
    var btn = $('da-discover-btn');
    if (btn) btn.addEventListener('click', startDiscover);
    var cancelBtn = $('da-discover-cancel-btn');
    if (cancelBtn) cancelBtn.addEventListener('click', cancelDiscover);
  }

  function setStep(n) {
    for (var i = 1; i <= 4; i++) {
      var node = $('da-ws-' + i);
      if (node) {
        node.classList.remove('is-active', 'is-done');
        if (i === n) {
          node.classList.add('is-active');
        } else if (i < n) {
          node.classList.add('is-done');
        }
      }
      var panel = $('da-panel-' + i);
      setHidden(panel, i !== n);
    }
    for (var j = 1; j <= 3; j++) {
      var line = $('da-wl-' + j);
      if (line) {
        line.classList.remove('is-done');
        if (n > j) line.classList.add('is-done');
      }
    }
    var panels = document.querySelector('.da-panels');
    if (panels) panels.scrollTop = 0;
  }

  function renderScreenList() {
    var list = $('da-screen-list');
    if (!list) return;
    list.innerHTML = '';
    var mock = currentMock();
    state.selectedScreens = [];
    for (var i = 0; i < mock.screens.length; i++) {
      var s = mock.screens[i];
      state.selectedScreens.push(true);
      var label = document.createElement('label');
      label.className = 'da-screen-row';

      var checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.checked = true;
      checkbox.setAttribute('data-idx', String(i));
      checkbox.addEventListener('change', (function (idx) {
        return function (e) {
          state.selectedScreens[idx] = !!e.target.checked;
          updateSelectedCount();
        };
      })(i));

      var nameSpan = document.createElement('span');
      nameSpan.className = 'da-screen-name';
      nameSpan.textContent = s.name;

      var clsCode = document.createElement('code');
      clsCode.className = 'da-screen-cls';
      clsCode.textContent = s.cls;

      var fieldsSpan = document.createElement('span');
      fieldsSpan.className = 'da-screen-fields';
      fieldsSpan.textContent = '入力 ' + s.fields;

      label.appendChild(checkbox);
      label.appendChild(document.createTextNode(' '));
      label.appendChild(nameSpan);
      label.appendChild(document.createTextNode(' '));
      label.appendChild(clsCode);
      label.appendChild(document.createTextNode(' '));
      label.appendChild(fieldsSpan);
      list.appendChild(label);
    }
    updateSelectedCount();
  }

  function updateSelectedCount() {
    var n = 0;
    for (var i = 0; i < state.selectedScreens.length; i++) {
      if (state.selectedScreens[i]) n++;
    }
    var total = state.selectedScreens.length;
    var span = $('da-selected-count');
    if (span) span.textContent = n + ' / ' + total + ' 画面を選択';
  }

  function setAllScreens(checked) {
    var list = $('da-screen-list');
    if (!list) return;
    var boxes = list.querySelectorAll('input[type=checkbox]');
    for (var i = 0; i < boxes.length; i++) {
      boxes[i].checked = checked;
      var idx = parseInt(boxes[i].getAttribute('data-idx'), 10);
      if (!isNaN(idx)) state.selectedScreens[idx] = checked;
    }
    updateSelectedCount();
  }

  function bindPanel1Next() {
    var btn = $('da-p1-next-btn');
    if (btn) {
      btn.addEventListener('click', function () {
        setStep(2);
        renderScreenList();
      });
    }
  }

  function bindPanel2() {
    var backBtn = $('da-p2-back-btn');
    if (backBtn) backBtn.addEventListener('click', function () { setStep(1); });

    var selectAllBtn = $('da-select-all-btn');
    if (selectAllBtn) selectAllBtn.addEventListener('click', function () { setAllScreens(true); });

    var clearAllBtn = $('da-clear-all-btn');
    if (clearAllBtn) clearAllBtn.addEventListener('click', function () { setAllScreens(false); });
  }

  function resetRunUI() {
    setText('da-exec-title', '生成中…');
    setText('da-exec-elapsed', '00:00');
    setText('da-exec-message', '対象を受け付けて、生成の準備を進めています。');
    setText('da-exec-phase', '準備中');
    setText('da-exec-count', '0 / 0');
    setText('da-exec-eta', '算出中');
    setText('da-exec-unreached', '0件');
    setText('da-exec-saved', '0件');
    var bar = $('da-run-bar');
    if (bar) bar.style.width = '4%';
    var log = $('da-run-log');
    if (log) log.textContent = '';
    for (var i = 0; i < 4; i++) {
      var st = $('da-estep-' + i);
      if (st) { st.classList.remove('is-active', 'is-complete'); if (i === 0) st.classList.add('is-active'); }
    }
    setHidden($('da-run-phone'), true);
    setHidden($('da-run-caption'), true);
    var ph = $('da-run-preview-placeholder');
    if (ph) ph.classList.remove('hidden');
    var running = $('da-exec-running-actions');
    if (running) running.classList.remove('hidden');
    var done = $('da-exec-actions');
    if (done) done.classList.add('hidden');
  }

  function startGenerate() {
    stopTimers();
    setStep(3);
    resetRunUI();
    var mock = currentMock();
    var selected = [];
    for (var i = 0; i < mock.screens.length; i++) if (state.selectedScreens[i]) selected.push(mock.screens[i]);
    var deviceSel = $('da-device');
    var device = deviceSel && deviceSel.value ? deviceSel.value : '';
    var appId = ($('da-app-id') && $('da-app-id').value) || mock.id;
    setText('da-exec-target', appId + (device ? '（' + device + '）' : ''));
    setText('da-exec-count', '0 / ' + selected.length);
    setText('da-exec-unreached', mock.unreached.length + '件');

    // 実物の 4 工程（受付 → 画面取得 → 解析 → 結果整理）に対応させる。画面取得の間だけプレビューが動く。
    var plan = [{ estep: 0, phase: '受付', msg: '対象を受け付けて、生成の準備を進めています。', log: '[受付] ' + appId + ' / ' + (device || '実行先未指定') }];
    for (var j = 0; j < selected.length; j++) {
      plan.push({ estep: 1, phase: '画面取得', msg: '画面を取得しています: ' + selected[j].name, screen: selected[j], n: j + 1,
        log: '[取得] ' + selected[j].name + ' (' + selected[j].cls + ') 入力 ' + selected[j].fields + ' 件' });
    }
    plan.push({ estep: 2, phase: '解析', msg: 'フォーム項目と遷移を解析しています…', log: '[解析] 遷移 ' + mock.transitions + ' 件を確定' });
    plan.push({ estep: 2, phase: '解析', msg: 'テスト条件を組み立てています…', log: '[解析] テスト条件を組み立て（同値分割・境界値・状態遷移）' });
    plan.push({ estep: 3, phase: '結果整理', msg: '文書を書き出しています…', log: '[出力] report.html / transition.mmd / spec.xlsx' });
    plan.push({ estep: 3, phase: '結果整理', msg: '文書を書き出しています…', log: '[出力] 未到達 Activity ' + mock.unreached.length + ' 件を一覧化', done: true });

    var TICK = 600;
    var started = Date.now();
    state.runClock = setInterval(function () {
      setText('da-exec-elapsed', formatClock(Math.round((Date.now() - started) / 1000)));
    }, 1000);

    var log = $('da-run-log');
    var bar = $('da-run-bar');
    var idx = 0;
    state.runTimer = setInterval(function () {
      var step = plan[idx];
      for (var k = 0; k < 4; k++) {
        var st = $('da-estep-' + k);
        if (!st) continue;
        st.classList.remove('is-active', 'is-complete');
        if (k < step.estep) st.classList.add('is-complete');
        if (k === step.estep) st.classList.add('is-active');
      }
      setText('da-exec-phase', step.phase);
      setText('da-exec-message', step.msg);
      if (step.screen) {
        var ph = $('da-run-preview-placeholder');
        if (ph) ph.classList.add('hidden');
        setHidden($('da-run-phone'), false);
        setHidden($('da-run-caption'), false);
        renderPhone('da-run-preview', step.screen);
        setText('da-run-caption', step.screen.name + ' — ' + step.screen.cls);
        setText('da-exec-count', step.n + ' / ' + selected.length);
        setText('da-exec-saved', step.n + '件');
      }
      if (log) { log.textContent += (log.textContent ? '\n' : '') + step.log; log.scrollTop = log.scrollHeight; }
      idx++;
      var remain = Math.ceil(((plan.length - idx) * TICK) / 1000);
      setText('da-exec-eta', remain > 0 ? '約 ' + remain + ' 秒' : '-');
      if (bar) bar.style.width = Math.max(4, Math.round((idx / plan.length) * 100)) + '%';
      if (step.done) {
        clearInterval(state.runTimer); state.runTimer = null;
        clearInterval(state.runClock); state.runClock = null;
        for (var m = 0; m < 4; m++) { var s2 = $('da-estep-' + m); if (s2) { s2.classList.remove('is-active'); s2.classList.add('is-complete'); } }
        setText('da-exec-title', '生成完了');
        setText('da-exec-phase', '完了');
        setText('da-exec-message', '文書を書き出しました。「レポートを見る」で結果を確認できます。');
        var running = $('da-exec-running-actions');
        if (running) running.classList.add('hidden');
        var done = $('da-exec-actions');
        if (done) done.classList.remove('hidden');
      }
    }, TICK);
  }

  function finishGenerate() {
    var mock = currentMock();
    var selectedCount = 0;
    for (var i = 0; i < state.selectedScreens.length; i++) {
      if (state.selectedScreens[i]) selectedCount++;
    }
    var totalFields = 0;
    for (var j = 0; j < mock.screens.length; j++) {
      if (state.selectedScreens[j]) totalFields += mock.screens[j].fields;
    }
    setText('da-result-screens', selectedCount);
    setText('da-result-transitions', mock.transitions);
    setText('da-result-fields', totalFields);
    setText('da-result-unreached', mock.unreached.length);
    setStep(4);
  }

  function cancelGenerate() {
    stopTimers();
    setStep(2);
  }

  function bindPanel3() {
    var cancelBtn = $('da-run-cancel-btn');
    if (cancelBtn) cancelBtn.addEventListener('click', cancelGenerate);
    var newBtn = $('da-exec-new-btn');
    if (newBtn) newBtn.addEventListener('click', cancelGenerate);
    var reportBtn = $('da-exec-report-btn');
    if (reportBtn) reportBtn.addEventListener('click', finishGenerate);
  }

  function bindGenerateBtn() {
    var btn = $('da-generate-btn');
    if (btn) btn.addEventListener('click', startGenerate);
  }

  function resetAll() {
    stopTimers();
    if (state.discoverTimer) {
      clearInterval(state.discoverTimer);
      state.discoverTimer = null;
    }
    if (state.runTimer) {
      clearInterval(state.runTimer);
      state.runTimer = null;
    }
    state.platform = 'android';
    state.source = 'file';
    state.fileChosen = false;
    state.deviceAppId = '';
    state.discoverDone = false;
    state.selectedScreens = [];

    var androidRadio = document.querySelector('input[name=da-platform][value=android]');
    if (androidRadio) androidRadio.checked = true;
    var fileRadio = document.querySelector('input[name=da-source][value=file]');
    if (fileRadio) fileRadio.checked = true;
    var standardScope = document.querySelector('input[name=da-scope][value=standard]');
    if (standardScope) standardScope.checked = true;
    setHidden($('da-scope-custom-fields'), true);

    var fileInput = $('da-file');
    if (fileInput) fileInput.value = '';
    var nameSpan = $('da-file-name');
    if (nameSpan) nameSpan.textContent = '';
    var idInput = $('da-app-id');
    if (idInput) idInput.value = '';

    clearError();
    resetDiscoverUI();
    setHidden($('da-p1-summary'), true);
    resetRunUI();

    applyPlatform();
    applySource();

    setStep(1);
  }

  function bindRestart() {
    var btn = $('da-restart-btn');
    if (btn) btn.addEventListener('click', resetAll);
  }

  function boot() {
    bindPlatformToggle();
    bindSourceToggle();
    bindFileInput();
    bindDeviceAppSelect();
    bindScopeToggle();
    bindDiscover();
    bindPanel1Next();
    bindPanel2();
    bindPanel3();
    bindGenerateBtn();
    bindRestart();

    applyPlatform();
    applySource();
    setHidden($('da-scope-custom-fields'), true);
    setStep(1);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
