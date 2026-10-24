# S06 対検査レビュー UI 完了記録（W1・2026-10-24）

## 通した経路（ポート 8768・認証オフ・Chrome ヘッドレス）
- /docverify#pair → GET /api/docverify/v1-a-order-payment/pair/findings・/docs・/trail（W2 実装の実 API）→ 12 件のカード・両文書・判定帯を表示
- カード選択 → 両文書の quote に強調 2 件（mark.hl）・該当章へスクロール
- 「要確認」押下 → POST /findings/V1-A-01/decide（実 API）→ 再取得で状態・判定帯・証跡（18 件）更新。保存先は W2 の data/docverify/v1-a-order-payment/pair/（UI 通し確認の記録が 1 件残る）
- 承認ボタン: gate.overall.pass=false のため無効を確認
- エラー時の文言: API の error.message を表示。無いときは 通信断/403/404/409/5xx ごとに次の行動 1 行付きの日本語

## 状態と幅（横スクロール 0 = documentElement と section の scrollWidth 差 0、はみ出し要素 0）
["normal", 1366, {"state": "normal", "hidden": false, "docX": 0, "secX": 0, "bodyY": 0, "bottom": 756, "vh": 768, "cards": 12, "over": 0, "msg": "|"}]
["selected", 1366, {"state": "normal", "hidden": false, "docX": 0, "secX": 0, "bodyY": 0, "bottom": 756, "vh": 768, "cards": 12, "over": 0, "msg": "|", "marks": 2}]
["normal", 1920, {"state": "normal", "hidden": false, "docX": 0, "secX": 0, "bodyY": 0, "bottom": 1068, "vh": 1080, "cards": 12, "over": 0, "msg": "|"}]
["selected", 1920, {"state": "normal", "hidden": false, "docX": 0, "secX": 0, "bodyY": 0, "bottom": 1068, "vh": 1080, "cards": 12, "over": 0, "msg": "|", "marks": 2}]
["normal", 1024, {"state": "normal", "hidden": false, "docX": 0, "secX": 0, "bodyY": 0, "bottom": 648, "vh": 660, "cards": 12, "over": 0, "msg": "|"}]
["selected", 1024, {"state": "normal", "hidden": false, "docX": 0, "secX": 0, "bodyY": 0, "bottom": 648, "vh": 660, "cards": 12, "over": 0, "msg": "|", "marks": 2}]
["loading", 1366, {"state": "loading", "hidden": false, "docX": 0, "secX": 0, "bodyY": 0, "bottom": 756, "vh": 768, "cards": 0, "over": 0, "msg": "対検査の内容を読み込んでいます。|"}]
["error", 1024, {"state": "error", "hidden": false, "docX": 0, "secX": 0, "bodyY": 0, "bottom": 648, "vh": 660, "cards": 0, "over": 0, "msg": "指摘を読み込めませんでした。少し待ってから再読み込みしてください。|"}]
["empty", 1366, {"state": "empty", "hidden": false, "docX": 0, "secX": 0, "bodyY": 0, "bottom": 756, "vh": 768, "cards": 0, "over": 0, "msg": "|"}]
["conflict", 1366, {"state": "conflict", "hidden": false, "docX": 0, "secX": 0, "bodyY": 0, "bottom": 756, "vh": 768, "cards": 12, "over": 0, "msg": "ほかの人が先に更新しました。最新を読み込んでから操作してください。|ほかの人が先に更新しました。最新
["unsaved", 1366, {"state": "unsaved", "hidden": false, "docX": 0, "secX": 0, "bodyY": 0, "bottom": 756, "vh": 768, "cards": 12, "over": 0, "msg": "保存できませんでした。通信を確かめてから「もう一度保存」を押してください。|保存できませんでした。通信を
["real-decide", 1366, {"state": "normal", "hidden": false, "docX": 0, "secX": 0, "bodyY": 0, "bottom": 756, "vh": 768, "cards": 12, "over": 0, "msg": "|", "trail": 19, "first": "\n      重大矛盾\n        

- 読込中・失敗・0 件・競合・未保存は page.route で API 応答を差し替えて発生させた（画面側の手動切替は無い）
- 撮影: /private/tmp/claude-501/-Users-fujimagariyuki-dev-active-webspec2doc/453414cb-bd3f-477e-9dd9-f5147cdd8a4a/scratchpad/pair-1366.png ほか pair-*.png

## 未検証
- 承認の成功（全体合格のデータが無い）・同一人物/認証オフの 403 文言の実表示
- 取消（revoke）の実 API 応答
- サイドバー「レビュー一覧」の行クリックからの遷移（inspections に v1-a-order-payment が無く、検査では inspections API を差し替えて #pair 直指定で開いた）
- 1024×660 では上部の画面見出しカードが高く、本体の高さが 300px 前後になる（判定帯は収まるが文書欄が狭い）
- pytest / make verify-ui / check_clipping.py は未実行

## 要判断
- 「未保存」の定義: 書込の通信断・5xx（再送可）とした。入力途中の未送信は状態にしていない
- 一覧から開いたとき pair を出すため、openReview(id,'read') を #read 直指定以外は pair に読み替えた（docverify-global.js は所有外のため）
- 1024 幅の見出しカードの高さは共通側（ページ頭）の問題。縮めるなら変更要求が要る

## 変更要求
なし
