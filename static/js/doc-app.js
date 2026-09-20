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
    runTimer: null
  };

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

    setHidden($('da-discover-progress'), false);
    var btn = $('da-discover-btn');
    if (btn) btn.disabled = true;
    setHidden($('da-discover-cancel-btn'), false);
    var log = $('da-discover-log');
    if (log) log.innerHTML = '';
    var bar = $('da-discover-bar');
    if (bar) bar.style.width = '0%';

    var idx = 0;
    var total = DISCOVER_LOG_STEPS.length;
    state.discoverTimer = setInterval(function () {
      if (idx >= total) {
        clearInterval(state.discoverTimer);
        state.discoverTimer = null;
        finishDiscover();
        return;
      }
      if (log) {
        var li = document.createElement('li');
        li.textContent = DISCOVER_LOG_STEPS[idx];
        log.appendChild(li);
      }
      idx++;
      if (bar) bar.style.width = Math.round((idx / total) * 100) + '%';
    }, 350);
  }

  function finishDiscover() {
    state.discoverDone = true;
    var btn = $('da-discover-btn');
    if (btn) btn.disabled = false;
    setHidden($('da-discover-cancel-btn'), true);
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
    if (state.discoverTimer) {
      clearInterval(state.discoverTimer);
      state.discoverTimer = null;
    }
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
    setText('da-run-stage', '');
    var bar = $('da-run-bar');
    if (bar) bar.style.width = '0%';
    var log = $('da-run-log');
    if (log) log.innerHTML = '';
  }

  function startGenerate() {
    setStep(3);
    resetRunUI();
    var idx = 0;
    var total = RUN_STAGES.length;
    var log = $('da-run-log');
    var bar = $('da-run-bar');
    state.runTimer = setInterval(function () {
      if (idx >= total) {
        clearInterval(state.runTimer);
        state.runTimer = null;
        finishGenerate();
        return;
      }
      setText('da-run-stage', RUN_STAGES[idx]);
      if (log) {
        var li = document.createElement('li');
        li.textContent = RUN_STAGES[idx];
        log.appendChild(li);
      }
      idx++;
      if (bar) bar.style.width = Math.round((idx / total) * 100) + '%';
    }, 700);
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
    if (state.runTimer) {
      clearInterval(state.runTimer);
      state.runTimer = null;
    }
    setStep(2);
  }

  function bindPanel3() {
    var cancelBtn = $('da-run-cancel-btn');
    if (cancelBtn) cancelBtn.addEventListener('click', cancelGenerate);
  }

  function bindGenerateBtn() {
    var btn = $('da-generate-btn');
    if (btn) btn.addEventListener('click', startGenerate);
  }

  function resetAll() {
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
