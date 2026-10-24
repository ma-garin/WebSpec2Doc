# C0 共通シェル・ナビ・トークン 設計（2026-10-24）

## 変える点
- static/css/tokens.css 新設: 文字 11/13/14/16/18/22/28（--fs-*）・余白 8/12/16/24/32（--sp-*）・状態色 3 値（--state-ok/ng/hold と -bg/-tx/-border）・役割色（--ui-*）・右パネル寸法。ta2.css（--bg/--sf/--line/--tx/--ac/--ok/--ng/--wa/--sans/--mono）・static/tokens.css と名前は重ならない。layouts/system.html で static/tokens.css の直後に読む。
- layouts/system.html にスロット: `content_state`（本文 data-state）・`right_panel`＋`right_panel_label`（右パネル）・`verdict_band`（下部判定帯）。右パネル・判定帯は block を書いた System だけに出る（書かない System の DOM は不変）。
- 上部バー: URL の ?case=&tv= を表示。無ければ「案件未選択」。
- 右パネルの開閉・保持（System ごとに localStorage）を c-hybrid.js に追加。右パネルがある画面だけ layout が c-hybrid.js を読む（二重読込でも二重に結ばない）。
- システム切替: 「システム」「切替」をすべての殻変種で nowrap・keep-all。名前は 2 行で省略。
- docverify-sidebar の設定アイコンを proposal-1 と同じ形に。項目・順序・クラスは固定のまま。
- components.css 末尾に追加のみ: 状態バナー `.ui-state-banner--{loading,empty,no-match,error,forbidden,dirty,conflict,restored}`、`.ui-state-only--*`・`.ui-state-hide-*`・`.ui-skeleton-line`、部品 `.finding-card`・`.verdict-band`・`.evidence-row`・`.step-bar`。

## 変えない点
- 既存クラスの削除・改名なし。components.css の既存行は無変更。サイドバーの殻・折りたたみ・foot。

## System 側の使い方
```
{% block content_state %}loading{% endblock %}
{% block right_panel_label %}証跡{% endblock %}
{% block right_panel %}<div class="evidence-row">…</div>{% endblock %}
{% block verdict_band %}<div class="verdict-band__row">…全体…</div><div class="verdict-band__row">…今回の変更分…</div>{% endblock %}
```
実行時の状態切替は `#app-content` の data-state を書き換える。
