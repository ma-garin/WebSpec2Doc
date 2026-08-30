/* ============================================================================
 * TA2 / ws-resync.js — テストケース表の変更をテストに取り込む（B5）
 *
 * 「表を取り込む」を押すと POST /api/ta2/tests/resync が走り、
 *   追加（表にあってテストに無い） / 名前更新 / 表に無いもの（orphan）
 * の件数を toast で返す。既存テストの手順・実行履歴は書き換えない。
 *
 * ルートの存在確認はしない。以前は HEAD で叩いていたが、ルートは POST 専用のため
 * 全ページ読み込みで 405 のコンソールエラーを撒いていた（検証ループ1 B-3）。
 * ボタンは常に出し、失敗はサーバが返したメッセージを toast で見せる。
 * ========================================================================== */
(function () {
  'use strict';
  var T = window.TA2;
  if (!T) return;
  var $ = T.$;
  var URL_RESYNC = '/api/ta2/tests/resync';

  function makeButton(id) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'btn';
    b.id = id;
    b.textContent = '表を取り込む';
    b.title = 'テストケース表の追加・名前の変更をテスト一覧に反映します（手順と実行履歴は保持します）';
    b.addEventListener('click', function () { run(b); });
    return b;
  }

  function summary(r) {
    var added = (r.added || []).length;
    var renamed = (r.renamed || []).length;
    var orphaned = (r.orphaned || []).length;
    return '追加 ' + added + ' / 名前更新 ' + renamed + ' / 表に無いもの ' + orphaned;
  }

  function run(btn) {
    var domain = T.state && T.state.domain;
    if (!domain) { T.toast('対象サイトが選ばれていません', 'ng'); return; }
    var all = document.querySelectorAll('.resync-btn');
    var i;
    for (i = 0; i < all.length; i++) { all[i].disabled = true; }
    T.api.post(URL_RESYNC, { domain: domain }).then(
      function (res) {
        T.toast(summary(res), 'ok');
        return T.loadTests().then(function () { T.render(); });
      },
      function (e) { T.toast((e && e.message) || '取り込みに失敗しました', 'ng'); }
    ).then(function () {
      for (var j = 0; j < all.length; j++) { all[j].disabled = false; }
    });
  }

  function mount() {
    var listFoot = $('#list-f-tests');
    if (listFoot && !$('#resync-btn')) {
      var b1 = makeButton('resync-btn');
      b1.className = 'btn resync-btn';
      listFoot.appendChild(b1);
    }
    var specHead = document.querySelector('#p-spec .ph');
    if (specHead && !$('#resync-btn-spec')) {
      var b2 = makeButton('resync-btn-spec');
      b2.className = 'btn resync-btn';
      var before = specHead.querySelector('.pop-wrap');
      if (before) specHead.insertBefore(b2, before);
      else specHead.appendChild(b2);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  } else {
    mount();
  }
})();
