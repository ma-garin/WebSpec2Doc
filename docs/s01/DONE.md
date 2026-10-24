# System 01 — 完了記録（波 B）

## 通した経路（実データ: demo/site を複製した静的サイトを python -m http.server 8781 で配信）
- クロール 1 回目 → src/main.py --domain-name demo-shop → output/demo-shop/snapshots/20261024-174456.json・report.json・audit.jsonl
- サイトを変更（contact.html に電話番号欄を追加・products.html の画面名を変更）→ 2 回目 --compare → snapshots/20261024-174517.json・drift_summary.json
- /dashboard → showResults('demo-shop') → GET /api/s01/versions → web/services/s01_versions.py build_site_versions → 判定帯
  - 全体: 判定不能（login.html はログインが必要で未確認）／今回の変更分: 未判定（入力項目の追加: phone、画面名の変更: DemoMart - 商品一覧 → 商品一覧（新））
  - 失敗行: 「ログインが必要な画面のため、中身を取得できませんでした。次の行動: ログイン情報を登録してから再解析してください。」
- 失敗例: 存在しない URL（nothing.html）を broken-site としてクロール → 応答 404 の画面を未確認に数え、全体＝判定不能＋「画面がエラー（404）を返したため…」
- API 404: /api/s01/versions?domain=nosuch.example → 404「このサイトはまだ解析されていません。URL を入れて解析してください。」
- 保存先: 読み取りのみ（判定帯は何も保存しない）

## 確認した状態と幅（ヘッドレス Chrome・Playwright）
- 1366×768・1920×1080・1024×660 × {通常 demo-shop, 通常 broken-site, 読込中, 失敗} の 12 通りで、文書の横はみ出し 0・判定帯の横はみ出し 0
- 撮影: scratchpad の s01-<対象>-<幅>.png（1024 の demo-shop を目視確認）

## 未検証
- robots で除外された画面の表示（demo の admin.html はリンクされておらず、crawl_started に除外 URL が載らなかった。文言の対応表のみ実装）
- 解析画面 0 件（report.json も版も無い）の「0件」状態の実画面（コードの分岐のみ。CLI はエラーページも 1 画面として保存したため再現できず）
- 権限不足（共通 403）での表示、認証あり（AUTH_MODE=off で確認）
- 追加した表示ロジックの単体テスト（pytest は禁止のため未作成・未実行）
- /sites/<domain>/<ws>（workspace.html は S02 所有）への判定帯の表示
- 生成物本文（screens.md・report.html）の中に区分を埋め込むこと（判定帯の区分表で示すに留めた）

## 変更要求
- CR-01-1（docs/change-requests/S01-1.md）: /doc-app 入口をシステム選択の主導線から外す
