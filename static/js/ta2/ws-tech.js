/* ---------------------------------------------------------------------------
 * 分析・設計 ＞ 技法
 *
 * ISO/IEC/IEEE 29119-4:2021 が定める仕様ベース技法のうち、画面の解析結果から
 * 導けるものを、技法ごとに何が出たかで見せる。適用できない技法も理由つきで
 * 並べる（黙って省くと「検討していない」のか「対象が無い」のか分からない）。
 * ------------------------------------------------------------------------- */
(function () {
  'use strict';
  var T = window.TA2;
  if (!T) return;
  var S = T.state, $ = T.$, esc = T.esc;

  /* 技法の表示名と、根拠となる規格の節。節番号は ISO/IEC/IEEE 29119-4:2021。
     カバレッジ計算式は有償部のため引用せず、節番号の参照に留める。 */
  var TECH = {
    classification_tree: ['分類ツリー法', 'ISO/IEC/IEEE 29119-4 5.2.2'],
    decision_table:      ['デシジョンテーブル', 'ISO/IEC/IEEE 29119-4 5.2.6'],
    cause_effect:        ['原因結果グラフ', 'ISO/IEC/IEEE 29119-4 5.2.7'],
    pairwise:            ['組合せ（ペアワイズ）', 'ISO/IEC/IEEE 29119-4 5.2.5'],
    orthogonal_array:    ['直交表', 'ISO/IEC/IEEE 29119-4 5.2.5'],
    domain_analysis:     ['ドメイン分析', 'Beizer / Binder・ISTQB CTAL-TA'],
    error_guessing:      ['エラー推測', 'ISO/IEC/IEEE 29119-4 5.4・ODC / OWASP WSTG']
  };
  var ORDER = ['classification_tree', 'decision_table', 'cause_effect', 'pairwise',
               'orthogonal_array', 'domain_analysis', 'error_guessing'];

  var cache = {};   // domain -> screens[]

  function load(domain) {
    if (cache[domain]) return Promise.resolve(cache[domain]);
    return T.api.get('/api/ta2/techniques?domain=' + encodeURIComponent(domain))
      .then(function (r) { cache[domain] = (r && r.screens) || []; return cache[domain]; });
  }

  function num(v) { return Number(v || 0).toLocaleString('ja-JP'); }

  function countOf(res, key) {
    var c = res.technique_case_counts || {};
    var name = (TECH[key] || [])[0];
    // 集計名と技法キーの対応は生成側が持つ。無ければ個別に数える。
    if (name && c[name] != null) return c[name];
    var v = res[key] || {};
    if (v.case_count != null) return v.case_count;
    if (Array.isArray(v.rules)) return v.rules.length;
    if (Array.isArray(v.cases)) return v.cases.length;
    if (Array.isArray(v.rows)) return v.rows.length;
    return 0;
  }

  function sample(res, key) {
    var v = res[key] || {};
    if (key === 'error_guessing') {
      return (v.guesses || []).slice(0, 3).map(function (g) {
        return (g.title || '') + '：' + (g.expected || '');
      });
    }
    if (key === 'cause_effect') {
      return (v.rules || []).slice(0, 3).map(function (r) {
        var n = Object.keys(r.conditions || {}).length;
        return (r.rule || r.effect || '') + '：条件 ' + n + ' 件 → '
          + (r.expected || r.action || (r.expected_valid ? '受理される' : '拒否される'));
      });
    }
    if (key === 'domain_analysis') {
      return (v.cases || []).slice(0, 3).map(function (c) {
        return (c.field || '') + '：' + (c.boundary || '') + ' の ' + (c.point || '') + ' 点 → '
          + (c.expected || '');
      });
    }
    if (key === 'decision_table') {
      return (v.rules || []).slice(0, 3).map(function (r) {
        return (r.rule || '') + '：' + (r.action || r.effect || '');
      });
    }
    if (key === 'classification_tree') {
      var branches = ((v.tree || {}).branches) || [];
      var out = [];
      branches.forEach(function (br) {
        (br.classifications || []).forEach(function (cl) {
          if (out.length < 3) {
            out.push((cl.name || cl.label || cl.field || '') + '（'
              + ((cl.classes || []).length) + ' クラス）');
          }
        });
      });
      return out;
    }
    return [];
  }

  function cardHtml(res, key) {
    var meta = TECH[key] || [key, ''];
    var v = res[key] || {};
    var ok = v.applicable !== false;
    var n = ok ? countOf(res, key) : 0;
    var body;
    if (!ok) {
      body = '<p class="tech-na">この画面には適用できません'
        + (v.reason ? '：' + esc(v.reason) : '') + '</p>';
    } else {
      var lines = sample(res, key).filter(Boolean);
      body = '<p class="tech-n"><b>' + num(n) + '</b> 件</p>'
        + (v.coverage ? '<p class="tech-cov">' + esc(v.coverage) + '</p>' : '')
        + (lines.length
            ? '<ul class="cond">' + lines.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>'
            : '<p class="tech-na">導出できた項目はありません</p>');
    }
    return '<div class="card tech-card' + (ok ? '' : ' is-na') + '">'
      + '<h3>' + esc(meta[0]) + '</h3>'
      + '<div class="sub">' + esc(meta[1]) + '</div>'
      + body + '</div>';
  }

  function render(pid) {
    var host = $('#spec-tech');
    if (!host) return;
    var domain = S.domain;
    if (!domain) { host.innerHTML = ''; return; }
    host.innerHTML = '<div class="card"><h3>読み込んでいます…</h3></div>';
    load(domain).then(function (screens) {
      var res = null;
      screens.forEach(function (x) { if (String(x.page_id) === String(pid)) res = x; });
      if (!res) {
        host.innerHTML = '<div class="card"><h3>この画面の技法適用結果はありません</h3>'
          + '<div class="sub">解析結果に含まれていない画面です。</div></div>';
        return;
      }
      host.innerHTML = '<div class="tech-head">'
        + '<b>' + esc(res.title || res.page_id) + '</b>'
        + '<span>この画面から導いたテスト設計の内訳です。件数はケース数で、'
        + '同じケースが複数の技法から導かれることがあります。</span></div>'
        + '<div class="tech-grid">'
        + ORDER.map(function (k) { return cardHtml(res, k); }).join('')
        + '</div>';
    }, function (e) {
      host.innerHTML = '<div class="card"><h3>読み込めませんでした</h3>'
        + '<div class="sub">' + esc((e && e.message) || '') + '</div></div>';
    });
  }

  T.techRender = render;      // ws-spec.js から呼ぶ
})();
