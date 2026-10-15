# System 01（ドキュメント作成）現行資産の棚卸し（2026-10-12）

アップデート着手前の現状。画面は認証オフの 8766 で実機確認（Chrome 拡張）、コードは grep と行数で確認。

## 画面（実機確認済み）

| 画面 | URL | 確認した内容 |
|---|---|---|
| ダッシュボード | `/dashboard` | URL 入力→解析開始、集計 4 枚（サイト 25・画面 52・項目 273・差分 2）、サイト一覧（開く／再解析／削除） |
| サイトを追加 / 再解析 | `/generate` | URL 入力、操作の記録（記録用ブラウザ・Recorder/Selenium IDE 取り込み）、解析範囲（1画面／標準／広め／カスタム） |
| 結果 | `/generate#report/<domain>/<tab>` | 8 タブ: 概要／画面と仕様（仕様・ギャラリー・カバレッジ）／テスト設計（画面別・条件マトリクス・技法サマリー・技法詳細・MBT）／テストケース（125 件・グリッド編集・実行）／画面遷移（シーケンス・コミュニケーション・アクティビティ・フローチャート・観点マップ、SVG/PNG/MMD 出力）／テスト実行（PASS 122・FAIL 1）／履歴・差分／現新比較 |
| 実行履歴 | `/run-history` | 61 件・13 サイト。種別・範囲・状態・画面・条件・成果物数 |
| 品質観点 | `/qa-quality` | サイト選択→観点生成、画面リスク（0〜100）と理由、成果物 JSON/HTML |
| 観点管理 | `/viewpoints` | 62 セット・5,500 観点。下書き／公開版／AI 提案／変更履歴、CSV 入出力 |
| 設定 | `/settings/<tab>` | API キー（OpenAI／Ollama）・解析の既定値・通知・外部サービス連携・運用監視・データ管理・監査ログ・テスト設計 |
| 参考 | `/references` | 依拠する標準（29119・ISTQB・25010・25012・WCAG 等）と反映状況 |
| ユーザーガイド | `/user-guide` | 目次 9 項目＋5 ステップ |
| トレーサビリティ | `/traceability/view` | 独立ページ（サイドバーなし）。ドメイン未指定だと空表示 |
| 01·app | `/doc-app` | index.html を app_mode で共用。Android/iOS・パッケージ・エミュレータ選択（モック段階） |

## コード

| 層 | 主なファイル（行数） |
|---|---|
| テンプレート | `templates/index.html`(233)・`partials/view-generate.html`(351)・`view-settings.html`(525)・`view-viewpoints.html`(295)・`result-panel.html`(122) |
| JS | `static/js/history.js`（一覧）・`view-*.js`（結果タブ）・`wizard.js`・`execution.js`・`results.js`・`doc-app-mode.js`・`viewpoint*.js` |
| CSS | `static/app.css`(638)・`app-components.css`(470)・`app-report.css`(641)・`tokens.css` |
| ルート | `web/routes/pages.py`(206)・`crawl.py`(337)・`report.py`(557)・`history.py`(475)・`viewpoints.py`(330)・`record.py`(455)・`settings.py`(231)・`traceability.py` |
| コア | `src/crawler`(4,769)・`src/generator`(6,461。`html_reporter` 1,228・`testcase_table` 842)・`src/analyzer`(1,148)・`src/diff`(2,889)・`src/capture`(2,354)・`src/ingest`(2,054)・`src/llm`(1,694)・`src/mbt`(1,671) |
| サービス | `web/services/site_report.py`・`run_store.py`・`export_xlsx.py`・`app_mock.py`・`screen_test_design.py` |
| 仕様 | `docs/design/specs/spec-1-1`〜`1-5`、`quality/feature_contracts.yml`（doc-fusion・doc-app） |

## 確認中に見つけた事象

| # | 事象 | 判定 |
|---|---|---|
| 1 | ダッシュボードの「開く」を拡張のクリックで押しても遷移しない | **アプリの欠陥ではない**。タブが `visibilityState=hidden` で、拡張のクリックはサイドバー含め全要素に届いていなかった。`element.click()` では `/generate#report/demomart/overview` へ正常遷移 |
| 2 | demomart のヘッダは「差分あり」だが、履歴・差分は「前回から変更はありません」、現新比較は 7/7 変更なし | 未検証。差分バッジの比較対象が別の 2 点の可能性。表示の不整合として要確認 |
| 3 | `/doc-app` にも Web 専用の「操作を記録して作る」「サンプル URL（example.com）」が出る | app モードで隠し漏れの可能性（未検証） |
| 4 | トレーサビリティは `/traceability/view` の独立ページで、他画面の骨格（サイドバー）と異なる | 設計どおりかは未確認 |

## 未確認
- 解析の実行（新規 URL→完了）・中止・失敗時の表示は動かしていない（外部アクセスと時間がかかるため）
- エクスポート（xlsx・zip）の中身
