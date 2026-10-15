# A. 競合調査: AIによる仕様書・設計書・要件のレビュー/品質検査ツール

調査日: 2026-10-15 / WebSearch 11 回 + WebFetch 5 回 = 計 15 回（上限）。
区分: 【実証】=第三者の査読・原データあり / 【主張】=ベンダー資料 / 【未確認】=確認できず。
**精度の公開数値（原データあり）は全製品で見つからなかった。** 引用してはいけない数値は末尾。

## 1. 製品別

### 1-1. バルテス QuintSpect（国内）
- 出典: PR TIMES 2026 https://prtimes.jp/main/html/rd/p/000000416.000030691.html / ITreview https://www.itreview.jp/products/quintspect/profile
- 検出観点【主張】: 5 観点（正確性・理解性・視覚性・深層性・信頼性）で不備箇所を項目ごとに指摘し、優先順位・重要度・期待効果を提示、レーダーチャート化。各観点の定義・評価基準は記載なし【未確認】。複数ドキュメント間の矛盾（不整合）検知あり。
- 準拠規格: 記載なし【未確認】。
- 入力: Excel, PDF。出力: 品質サマリーレポート、レーダーチャート。
- 改版比較【未確認】。指摘管理/履歴: 分析履歴の検索・絞込、分析予約、メール通知（2026-07-06 正式版）。トレーサビリティ: 記載なし。
- 精度数値: なし（プロトタイプ 2025-10 以降 14 社利用、のみ）。
- 料金: 無償お試し/スターター/スタンダード/エンタープライズの 4 プラン、金額非公開。第三者サイトの「5 アカウント 0 円」は未確認。
- AI モデル: 記載なし。生成AIと称する（検索要約）。

### 1-2. QRA QVscribe
- 出典: https://qracorp.com/qvscribe/ （2026 参照）/ https://qracorp.com/?p=539（2.10, 2019）/ NLP4RE論文 https://ceur-ws.org/Vol-2584/NLP4RE-paper3.pdf（2020）
- 検出観点【主張】: 曖昧さ（弱語・受動態・代名詞・継続語）、測定/試験可能性（全称量化・曖昧な時間語・逃げ節・open-ended）、構造（不完全文・imperative 欠落/重複/否定・混在した justification）、一貫性（単位・用語集・類似重複）、要件間の重複・潜在矛盾（Similarity）。Problem Type 単位で ON/OFF、除外接頭辞設定可。
- 準拠: INCOSE（41 ルール版 2019 時点）、EARS 適合判定。ISO 29148 は言及なし。
- 入出力: Word/Excel アドイン、DOORS Next/Polarion/Jama 拡張、Web、REST API。出力 1-5 スコア、ルール名と該当語の指摘、ReqWriter の書き換え提案（採否可）。読み取り専用同期。
- 改版/記録: スナップショットに本文・スコア・設定版・ルールセット・エンジン版を記録、時系列化。「再解析は変更箇所に集中」（詳細なし）。
- 限界（ベンダー自認）: アーキテクチャ/モデル/テスト/コードとの突合は未対応、網羅性（completeness）チェックは対象外。
- 精度: 公開なし。「決定論的スコア」は主張のみ。料金: 非公開（デモ請求/無料トライアル）。AI モデル: 非公開（NLP ルールベースが主、ReqWriter は生成的と推測【未確認】）。

### 1-3. IBM Engineering Requirements Quality Assistant (RQA)
- 出典: https://www.ibm.com/docs/SS3UPN/com.ibm.help.rm.assist.doc/topics/c_rqa_architecture.html / https://requisis.com/en/saas-doors-dng/rqa-saas.html
- 検出【主張】: Watson NLP で曖昧性等を検出。ガイドラインは INCOSE と NASA 準拠、個別一覧は非掲載。EARS は確認できず【未確認】。
- 入力: DOORS Next/DOORS で選択した要件文。出力: 1-100 スコア、問題一覧、改善案。Jazz Reporting Service に集計。Teach Watson でフィードバック→IBM SME レビュー。
- トレーサ/矛盾/改版: 記載なし。精度: なし。料金: 非掲載。
- 注意: IBM ホスト SaaS は終了し REQUISIS（IBM パートナー）が後継提供との第三者記述【主張・未確認】。

### 1-4. Visure Requirements Quality Analyzer
- 出典: https://visuresolutions.com/tool-suite/quality-analyzer （2026 参照）
- 検出【主張】: 「8 品質指標」だが名称非掲載。エンジンは「QVscribe for Visure」ベースの NLP。5 つ星スコアカード、問題語ハイライト、カスタムトリガー語。
- 準拠: INCOSE/29148/EARS は同ページに記載なし【未確認】（安全規格 ISO 26262 等はテンプレート側）。
- 入力: Visure 内の要件文（執筆時解析）。LLM 利用はこのページで未記載（別の AI アシスタント「Vivia」は存在するが関係未確認）。
- 精度: なし（ページ上の導入効果統計はプレースホルダ 0）。料金: 非掲載、14 日トライアル。

### 1-5. Jama Connect Advisor
- 出典: https://www.jamasoftware.com/datasheet/jama-connect-advisor / https://www.jamasoftware.com/blog/2025/03/20/utilize-artificial-intelligence-and-natural-language-processing-to-produce-high-quality-requirements-with-jama-connect-advisor/
- 検出【主張】: 曖昧要件の特定、項目間の欠落リンクの発見、承認済み要件からのテストケース下書き生成（トレースリンク付き）。
- 準拠: INCOSE ルール and/or EARS を選択して採点（ブログ）。データシートは個別ルール非掲載。
- 入力: Jama 内要件、顧客仕様/規制文書 PDF（Jama アイテムへ構造化変換）。出力: 改善提案、トレースリンク提案、テスト下書き。人が採否レビュー。単体/一括採点とレポートあり（ブログ、データシートではスコア記載なし）。
- AI モデル: 非公開。精度: なし。料金: 非掲載（別ページ参照）。

### 1-6. Copilot4DevOps（Modern Requirements, Azure DevOps）
- 出典: https://www.softwareadvice.com.au/software/520634/Copilot4DevOps / G2 レビュー
- 【主張/ユーザー報告】: 作業項目を INVEST・SWOT・MoSCoW で評価、曖昧箇所・欠落の指摘。ISO 29148/INCOSE の言及は見つからず【未確認】。テスト品質にばらつきとのユーザー報告。料金/モデル/精度: 未確認。

### 1-7. SpecLens 系
- 該当製品を検索で特定できず【未確認】。

### 1-8. 国内SIer（NTTデータ・日立・NEC・TIS・SHIFT・富士通）
- 要件/設計書の「レビュー/矛盾検知」製品は検索で確認できず【未確認】（存在しないことの証明ではない）。
- 富士通: 生成AIでレガシーコードから設計書を自動生成する SaaS を提供（作業時間を約30分の1とするが【主張】）。レビューではなく生成。出典 https://dempa-digital.com/?p=711961 (2026-03)
- SHIFT: 「生成AI 360°」（社内浸透支援, 2025-05）等はあるが設計書レビュー製品は確認できず。
- 事例: KINTOテクノロジーズが DB テーブル設計を PR 起点で生成AIレビュー（社内アプリ、製品ではない）。出典 https://codezine.jp/article/detail/21053
- KPMG Japan は要件定義書の作成/レビューは人の判断が強く自動化困難と指摘 https://kpmg.com/jp/ja/insights/2026/04/genai-utilization-01.html

## 2. 比較表（確認できた範囲）

| 製品 | 規格 | 矛盾/重複 | 改版比較 | 指摘管理 | 入力 | 精度公開 |
|---|---|---|---|---|---|---|
| QuintSpect | 不明 | 文書間矛盾 | 不明 | 履歴・通知 | Excel/PDF | なし |
| QVscribe | INCOSE, EARS | 類似・潜在矛盾 | スナップショット | スナップショット時系列 | Word/Excel/RM/API | なし |
| IBM RQA | INCOSE, NASA | 不明 | 不明 | JRS集計 | DOORS | なし |
| Visure QA | 不明 | 不明 | 不明 | スコアカード | Visure内 | なし |
| Jama Advisor | INCOSE, EARS | 欠落リンク検出 | 不明 | 人の採否 | Jama/PDF | なし |
| Copilot4DevOps | なし確認 | 不明 | 不明 | 不明 | ADO | なし |

## 3. 全製品がやっていて必須なもの（確認できた範囲で）
- 要件文単位の曖昧性/弱語/不適切表現の検出と、該当箇所の提示（QuintSpect は観点別だが同系）。
- スコア化または優先度付けによる品質の可視化。
- 人が採否を決める（AI 提案を自動確定しない）。
- 既存の文書/ALM の中で動く入口（Word/Excel/PDF/RM ツール）。

## 4. 誰もやっていない空白（確認できた範囲。存在しない証明ではない）
- 検出精度の公開（原データ・適合率/再現率・誤検知率）。全 6 製品で確認できず。
- Web アプリ実画面・実挙動と仕様書の突合（QVscribe 自身がモデル/テスト/コードとの突合は未対応と記載）。
- 網羅性（completeness）検査（QVscribe は対象外と明記）。
- 指摘ごとの根拠（原文引用・規則 ID）と再現可能な判定記録を、レビュー記録として残す仕組みの公開仕様（QVscribe のスナップショットが近いが仕様突合は不可）。
- 日本語の仕様書/設計書に特化した規格準拠の検査（INCOSE/EARS は英語前提。国内製品は規格非公開）。
- 改版間の差分に絞った再検査の具体仕様（QVscribe は主張のみ、詳細なし）。
- 国内大手SIerの汎用製品としての設計書レビュー（今回の検索では確認できず）。

## 5. 引用してはいけない数値
- 「5 アカウント 0 円」（ITトレンド掲載、公式未確認）
- 富士通「30分の1」（生成側の主張、レビュー精度ではない）
- Visure の導入効果統計（プレースホルダ）
- 「41 ルール」は QVscribe 2019 時点の主張で現行は未確認

## 6. 学術参考（未精読）
- LLM による ISO 29148 品質特性評価 https://arxiv.org/abs/2408.10886v1
- ALICE（矛盾検知, TU Berlin）https://depositonce.tu-berlin.de/items/1d4dc18e-8112-47a2-ab65-d4e81bdac5e1
- Requirements Smells https://arxiv.org/pdf/1611.08847
