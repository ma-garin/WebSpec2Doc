# バッチ／データ／DB／API テスト OSS と LLM テスト生成 OSS 調査（2026-10-15 時点）

## 要約（10 行）
1. 推奨の核は「pytest を実行器、Python 製ライブラリを部品」。DB は Testcontainers-python（Docker 要）か pytest-postgresql（Docker 不要・PostgreSQL のみ・LGPL）、データ検証は Pandera（MIT）＋ SQL 直書きの期待値比較、API は Schemathesis（MIT・OpenAPI 前提）と Tavern／Hurl。
2. 「DB 前後比較・期待値テーブル」を担う汎用 Python OSS は見つからず（DBUnit 相当は Java）。ここは自前実装（before/after スナップショット差分＋期待値 CSV）が必要。本システムの差別化領域。
3. 生成コードのターゲットは第一候補 Python+pytest（生成→実行→修復ループを CoverUp 型で回せる）。第二候補は Hurl（API 状態ポーリング・宣言的でレビューしやすい）と SQL（pgTAP/utPLSQL/tSQLt は DB 種別が合うときのみ）。顧客が Java 製バッチなら JUnit＋Spring Batch Test／Karate／REST Assured を追加ターゲットにする。
4. ライセンス注意: Soda Core v4 は Elastic License 2.0（SaaS として機能提供は禁止条項あり）、SDV は BUSL-1.1、Liquibase 5.x は FSL、AGPL の Qodo Cover は組み込み不可。商用製品へ同梱するなら GE（Apache-2.0）・Pandera（MIT）・Testcontainers（Apache-2.0/MIT）が安全。
5. data-diff は 2024-05 に公式アーカイブ。後継 fork は reladiff（MIT・最終リリース 2025-03）。クロス DB 比較の参考・限定利用に留める。
6. LLM テスト生成 OSS は研究由来が中心で、バッチ／DB／データ検証向けのものは確認できず。CoverUp（Python・Apache-2.0）と Pynguin（MIT）が実用寄り。TestPilot はアーカイブ、Qodo Cover は保守終了、Meta TestGen-LLM は非公開。いずれも「ユニットテスト（コード単位）」向けで、IT/ST のジョブ・データ前後比較には直接使えない＝「参考にするだけ」。
7. 流用すべき設計思想は「LLM が生成 → 実行 → カバレッジ／ミューテーションで採否判定 → 失敗ログを渡して再生成」の検証ループ（CoverUp・TestGen-LLM・ACH 系）。
8. JP1/A-AUTO 等のジョブネットと連携する公開 OSS 事例は未発見。ジョブ起動・状態取得を CLI/API アダプタで抽象化し、本システムは黒箱として DB・ファイル・ログの前後を検証する設計が妥当。

---

## 0. 調査方法と制約
- WebSearch 13 回、WebFetch 3 回（上限内）。加えて PyPI の JSON API・GitHub API・raw README を curl で取得し、版・ライセンス・最終 push を機械的に確認した（これは WebSearch/WebFetch の回数に含めていない。含めるべきとの解釈なら上限超過の可能性あり）。GitHub API は途中でレート制限に到達し、一部リポジトリは取得できていない。
- 成熟度欄の「スター数」「最終リリース」は参考値。PyPI の最新版は 2026-10-15 取得時点。
- 「記憶ベース」と書いた箇所は今回の調査で一次資料を確認していない（未確認扱い）。

---

## 1. データ検証

### Great Expectations（GX Core）
- ライセンス: Apache-2.0（PyPI・GitHub）／言語: Python／対象: DataFrame・SQL テーブル
- 成熟度（参考）: PyPI 1.24.0（2026-10-07）、約 11.9k stars。GX Cloud は別の商用製品
- できること: Expectation（データへのアサーション）、Validation Definition、Data Docs（検証結果 HTML）、プロファイリング。DB 前後比較・スナップショットは標準機能ではない（件数・列統計・値集合などの宣言的検証向け）
- 組み込み方: **ライブラリとして使う**（Python から実行し結果 JSON を証跡に取り込む）。または生成コードのターゲット（Expectation を LLM が生成）
- 制約: 概念が重く API の変更が多い（0.x→1.x の破壊的変更。記憶ベース）。行単位の期待値表との完全一致比較は不得手
- 出典: https://github.com/great-expectations/great_expectations（README・2026）、https://pypi.org/project/great-expectations/

### Soda Core
- ライセンス: **v4 は Elastic License 2.0**（リポジトリ main の LICENSE を確認。PyPI の soda-core 4.27.0 は "Proprietary" 表記）。v3 系（soda-core-postgres 3.5.6、2025-09）のライセンスは今回未確認
- 言語: Python／対象: PostgreSQL・Snowflake・BigQuery・Databricks・DuckDB 等
- 成熟度（参考）: PyPI soda-core 4.27.0（2026-10-13）、約 2.4k stars
- できること: YAML のデータコントラクト、50 超の組込チェック、スキーマ検証。Soda Cloud と連携
- 組み込み方: **参考にするだけ**（コントラクトの YAML 設計は有用）。同梱する場合は ELv2 の「第三者にホスト型／マネージドサービスとして主要機能を提供してはならない」条項と、ライセンスキー機能の回避禁止条項に抵触しないか法務確認が必要
- 制約: 本システムが SaaS 提供なら ELv2 が障害になり得る
- 出典: https://github.com/sodadata/soda-core（LICENSE・README、2026）

### Deequ / PyDeequ
- ライセンス: Apache-2.0／言語: Scala（Spark 上）、PyDeequ は Python ラッパー／対象: Spark DataFrame
- 成熟度（参考）: PyDeequ 1.7.0（2026-09-14）、Deequ 約 3.6k stars。PyDeequ 1.7.0+ は Deequ 2.0.21（Spark 3.5）/2.0.18（Spark 4.1）に追従、Spark 3.1–3.4 は 1.6.0 まで
- できること: 制約検証、メトリクス計算、異常検知、制約提案
- 組み込み方: **対象顧客が Spark 基盤のときだけ**ライブラリとして使う。一般的な RDB バッチの IT/ST には過剰（JVM と Spark が必要）
- 出典: https://github.com/awslabs/python-deequ（README・2026）

### Pandera
- ライセンス: MIT／言語: Python／対象: pandas・polars・PySpark 等の DataFrame
- 成熟度（参考）: 0.34.1（2026-10-06）、約 4.5k stars
- できること: DataFrameSchema／型付きモデルによる列型・値域・行間チェック。Hypothesis ベースのテストデータ生成機能（strategies）は記憶ベース（今回未確認）
- 組み込み方: **ライブラリとして使う**。テーブル内容を DataFrame に取り込み、期待スキーマで検証する軽量層に最適
- 制約: 前後の差分比較・参照整合の複数テーブル検証は自前で書く必要
- 出典: https://github.com/unionai-oss/pandera（README・2026）

### dbt tests（dbt-core）
- ライセンス: Apache-2.0／言語: Python（SQL モデルを対象）／成熟度（参考）: dbt-core 1.12.6（2026-10-14）
- できること: data tests（not_null・unique 等、構築後データを検証）、**unit tests（1.8〜。given で入力モック、expect で期待行を YAML 定義）**。SQL モデルのみ対象。マテビュー・再帰 SQL・introspective クエリは unit test 非対応
- 組み込み方: 顧客が dbt を使うなら**生成コードのターゲット**（given/expect YAML を LLM が生成。構造が単純で機械検証しやすい）。dbt を使わない顧客には不向き
- 出典: https://docs.getdbt.com/reference/resource-properties/unit-tests（公式 docs・検索結果の要約を確認）

### data-diff（Datafold）／reladiff
- data-diff: MIT。**2024-05-17 に Datafold がサポート終了、リポジトリはアーカイブ**。最終版 0.11.2。商用 Datafold Cloud への誘導あり
- reladiff（fork）: MIT 表記（README・PyPI。GitHub の SPDX は NOASSERTION）。PyPI 0.6.0（2025-03-04）、GitHub 最終 push 2025-08-18、約 545 stars。主要 DB 十数種をサポート
- できること: テーブル／DB 間の行差分（ハッシュによる効率的比較）
- 組み込み方: クロス DB の件数・行比較の**参考／限定的ライブラリ利用**。保守体制が小さいので依存は薄く。比較ロジックは自前実装も選択肢
- 出典: https://www.datafold.com/blog/sunsetting-open-source-data-diff（2024）、https://github.com/erezsh/reladiff（README）

### Elementary
- ライセンス: Apache-2.0／言語: Python（CLI）＋ dbt パッケージ／成熟度（参考）: 0.26.1（2026-10-11）、約 2.4k stars
- できること: dbt のテスト結果・メタデータからデータ可観測性レポート。異常検知は dbt パッケージ側。Elementary Cloud は商用
- 組み込み方: **参考にするだけ**（dbt 前提。本システムの IT/ST 用途とは主眼が違う＝運用監視）
- 出典: https://github.com/elementary-data/elementary（README・2026）

---

## 2. DB テスト

### Testcontainers（python / java / go）
- ライセンス: python Apache-2.0、java MIT、go MIT／成熟度（参考）: testcontainers-python 4.15.0（2026-07-24）、java 約 8.8k stars
- できること: テスト内で使い捨ての DB コンテナ（PostgreSQL 等）を起動・破棄。テスト間の分離が容易
- 組み込み方: **ライブラリとして使う**（生成テストの fixture）
- 制約: **Docker 互換ランタイムが必須**。本プロジェクトの方針メモ（Docker 禁止・有償のみ）と衝突する可能性があり、Podman 等の代替運用可否は今回未確認。Oracle 等の商用 DB イメージはライセンス・サイズの問題（記憶ベース）
- 出典: https://github.com/testcontainers/testcontainers-python（README・2026）、https://simple-repository.app.cern.ch/project/testcontainers

### pytest-postgresql
- ライセンス: LGPL-3.0-or-later（PyPI）／言語: Python／成熟度（参考）: 9.1.1（2026-10-04）
- できること: ローカルにインストール済みの PostgreSQL バイナリで一時インスタンス／テンプレート DB を起動する pytest fixture。**Docker 不要**
- 組み込み方: **ライブラリとして使う**（PostgreSQL 限定）。LGPL は動的リンク／テスト依存なら通常問題になりにくいが、同梱配布するなら法務確認
- 出典: https://pypi.org/project/pytest-postgresql/

### DBUnit
- ライセンス・最新版は今回未確認（GitHub API で dbunit/dbunit が 404）。記憶ベース: Java／JUnit 拡張／LGPL／XML・CSV・Excel のデータセットで DB を投入し、実テーブルと期待データセットを比較
- 組み込み方: **考え方を参考にする**（期待データセット＋前後比較）。Java 顧客の生成ターゲットとしては有力
- 出典: 未確認

### pgTAP
- ライセンス: PostgreSQL ライセンス系の許諾文言（README。SPDX は未確認）／言語: PL/pgSQL／成熟度（参考）: 1.3.5、約 1.2k stars、2026-09 push
- できること: TAP 出力のアサーション関数（`results_eq`・`has_table` など）、xUnit 風のテスト関数
- 組み込み方: **生成コードのターゲット**（顧客が PostgreSQL で、DB 内ロジック・制約を直接検証したいとき）
- 出典: https://github.com/theory/pgtap（README・2026）

### utPLSQL
- ライセンス: Apache-2.0／言語: PL/SQL（Oracle 対象）／成熟度（参考）: 約 625 stars、2026-10-12 push
- できること: PL/SQL パッケージのユニットテスト、モック、カバレッジ、JUnit 形式出力（記憶ベース）
- 組み込み方: Oracle 顧客向けの**生成ターゲット**。国内の基幹バッチは Oracle が多いので候補（国内シェアは未検証）
- 出典: https://github.com/utPLSQL/utPLSQL

### tSQLt
- 公式リポジトリは tsqlt-org/tSQLt（旧 tSQLt/tSQLt は移転案内）。ライセンスは GitHub API 上 None（記憶ベースで Apache-2.0、未確認）／言語: T-SQL（SQL Server 対象）
- できること: T-SQL で書くユニットテスト、テーブルの偽装（FakeTable）、期待・実績テーブル比較（AssertEqualsTable）は記憶ベース
- 組み込み方: SQL Server 顧客向けの**生成ターゲット**
- 出典: https://github.com/tsqlt-org/tSQLt（README）

### Flyway／Liquibase（スキーマ管理）
- Flyway: GitHub 上 Apache-2.0（Community）、約 10k stars、2026-10 push。Redgate の有償エディションあり
- Liquibase: **5.0 から Community は FSL（Functional Source License、2 年後に Apache-2.0 へ移行）**。ソース公開だが OSI 的な OSS ではないとの指摘あり（第三者ブログ）
- 組み込み方: テスト用 DB に本番と同じスキーマを適用するための**前提ツール**。顧客資産の読み取り対象（マイグレーション SQL）として扱う。本システムが同梱するなら Flyway Community が無難
- 出典: https://www.liquibase.com/blog/liquibase-community-for-the-future-fsl（2025）、https://github.com/flyway/flyway

---

## 3. バッチ基盤のテスト支援

### Spring Batch Test
- ライセンス: Apache-2.0／言語: Java／成熟度（参考）: 約 3k stars、2026-10 push
- できること: `@SpringBatchTest` で `JobLauncherTestUtils`・`JobRepositoryTestUtils` を注入。ジョブ全体 `launchJob()`・ステップ単体 `launchStep()` を実行し、`JobExecution` の終了状態を検証。公式 docs の例は、DB テーブル投入→ジョブ起動→出力ファイル検証。
- 組み込み方: 顧客が Spring Batch なら Java／JUnit の**生成ターゲット**。それ以外の言語のバッチには使えない
- 出典: https://docs.spring.io/spring-batch/reference/5.2/testing.html

### JBatch（JSR-352）
- 今回は一次資料を確認していない（未確認）。記憶ベースでは実装（Spring Batch・WebSphere・Open Liberty 等）依存でテスト支援は実装側の機能。

### Airflow のテスト機構
- Apache-2.0／Python／3.3.2（2026-09-17）。公式 docs（3.3.2 版）: DagBag import テスト（`dagbag.import_errors` が空、`dag.task_dict`・`downstream_task_ids` の構造検証）、オペレータは `op.execute(context)`・`render_template_fields()` で単体テスト、`dag.test()` は全体実行（メタデータ DB が必要）、変数・接続は環境変数 `AIRFLOW_VAR_*`・`AIRFLOW_CONN_*` でモック。Airflow 3.2 で `TaskInstance.run()` 等が削除
- 組み込み方: 顧客が Airflow なら**Python の生成ターゲット**（pytest）。本システムが Python なので親和性が最も高い
- 出典: https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html

### Dagster のテスト機構
- Apache-2.0／Python／1.13.26（2026-10-09）。公式 docs: アセット・オペを直接関数として呼び、`build_asset_context()`、`unittest.mock.Mock(spec=...)` でリソースを差し替え、複数アセットは `job.execute_in_process()`。asset checks は実行時のデータ品質検証の位置づけで、単体テスト手段ではない
- 出典: https://dagster.io/docs/guides/test/unit-testing-assets-and-ops

### JP1/AJS3・A-AUTO 等のジョブネットとの連携
- OSS のテスト連携事例は今回の検索で見つからず（未確認）。見つかったのは日立の公式マニュアル（時刻変更の注意）のみ: システム日時を戻すとイベント検索やファイル更新検出に影響し、ジョブが異常終了する場合がある。時刻を戻す手順ではサービス停止が前提で、即時起動すると次回起動時刻が過去になる
- 含意: 日付・時刻依存のバッチテストでは、OS 時刻の変更は他ジョブへ副作用がある。**実行日／基準日をパラメータで渡す設計、または時刻を固定できるテスト専用環境**が要件になる。ジョブ起動・状態取得のコマンド／API の具体は記憶ベースのため要確認
- 出典: https://itpfdoc.hitachi.co.jp/manuals/3021/30213D2530e/AJSJ0106.HTM（日立 JP1 マニュアル）

---

## 4. API テスト

| 名称 | ライセンス／言語 | 成熟度（参考） | できること | 組み込み方 | 制約・弱み |
|---|---|---|---|---|---|
| Schemathesis | MIT／Python | PyPI 4.31.1（2026-10-14）、約 3.7k stars | OpenAPI／GraphQL からプロパティベース（Hypothesis）でケース生成、5xx・スキーマ不一致を検出。pytest 連携 | **ライブラリ／CLI として使う**（仕様書があるとき） | 仕様と実装が一致していることが前提。業務ロジックの期待値は書けない。なお検索で出た「v4.22.4（2026-07）」は集約サイトの古い値で、PyPI を正とした |
| Hurl | Apache-2.0／Rust | 約 19.3k stars、2026-10 push | テキスト形式でリクエスト連鎖、`[Captures]`・`[Asserts]`（JSONPath・XPath）、リトライ、JUnit/TAP/HTML レポート | **生成コードのターゲット**（バッチ状態の完了待ちポーリングが書きやすい） | ファイル分割や DB 検証は不可。バイナリ配布 |
| Tavern | MIT／Python | 3.7.0（2026-09-25）、約 1.2k stars | YAML で REST・MQTT・gRPC を pytest プラグインとしてテスト | **生成ターゲット／ライブラリ**。Python 製システムと親和 | YAML の表現力は限定的 |
| Karate | MIT／Java | 約 9k stars、2026-10 push | API・モック・性能・UI を 1 つの DSL で（README の説明）。DB 直接検証は Java 連携で可能（記憶ベース） | Java 顧客向けの**生成ターゲット** | JVM が必要 |
| REST Assured | Apache-2.0／Java | 約 7.1k stars、2026-10 push | Java の流暢な API による REST 検証 | Java 顧客向け生成ターゲット | コードベースが Java に固定 |
| Pact（pact-python） | MIT／Python | 4.0.0（2026-10-15）、約 685 stars | 消費者駆動契約テスト（consumer／provider 検証） | 複数システム間の IT で**参考／ライブラリ** | 契約を書く消費者側の協力が前提。バッチ連携には不向き |
| Dredd | MIT／JavaScript | **アーカイブ（2024-05-11）** | API Blueprint／OpenAPI 検証 | 採用しない | メンテナンス終了 |
| Step CI | MPL-2.0／TypeScript | 約 1.9k stars、**最終 push 2024-08-03**（活動低下） | YAML で API 検証、言語非依存 | 採用しない（Hurl／Tavern で代替可能） | 有償サポートプラン告知あり。活動が止まっている |
| Keploy | Apache-2.0／Go | 約 18.6k stars、2026-10 push | eBPF で API 呼出・DB クエリを記録し、テストとモックとして再生 | 本番／検証環境のトラフィック記録型の**参考**。Linux／eBPF 前提 | 新規ケースの網羅設計には使えない。PyPI の keploy（2.0.0a39・2024）は別物で無関係 |
| EvoMaster | LGPL-3.0／Kotlin | PyPI 6.2.0（2026-09-15）、約 800 stars | REST・GraphQL・RPC を探索的に fuzz し、Python／JS／JUnit 形式の回帰テストを出力。ブラックボックスモードあり | **生成コードのターゲットかつ参考**（進化的探索による非 LLM の生成。AI 駆動を謳うが LLM 利用の有無は未確認） | リポジトリは WebFuzzing/EvoMaster に移動。LGPL。Docker 実行が主導線 |

- 出典: https://github.com/schemathesis/schemathesis、https://github.com/Orange-OpenSource/hurl、https://github.com/taverntesting/tavern、https://github.com/karatelabs/karate、https://github.com/pact-foundation/pact-python、https://github.com/keploy/keploy、https://github.com/stepci/stepci、https://github.com/EMResearch/EvoMaster（各 README・2026）。Dredd のアーカイブは GitHub メタデータ（2026-10-15 取得）。

---

## 5. LLM によるテスト生成

| 名称 | ライセンス／言語／対象 | 成熟度（参考） | 方式 | 本システムでの位置づけ | 制約・弱み |
|---|---|---|---|---|---|
| CoverUp | Apache-2.0／Python／pytest | PyPI 0.6.3（2025-07-31）、約 115 stars、FSE 2025 | SlipCover でカバレッジ計測 → 未カバー箇所を LLM に渡して生成 → 実行・カバレッジ増を確認 → 再プロンプト。OpenAI・Anthropic・Bedrock 対応 | **参考（設計ループの手本）**。Python 製の対象コードのユニットテスト向け | バッチの外部入出力・DB 状態比較は対象外。論文では CodaMosa 比で中央値カバレッジが高いと主張（数値は第 6 節の注意参照） |
| CodaMosa | MIT／Python（Pynguin 上） | ICSE 2023。README が「Pynguin のほうが保守されている」と明記 | 探索型生成が停滞したとき LLM（Codex API）で補う | 参考のみ | OpenAI Codex 前提で古い |
| Pynguin | MIT／Python | 0.47.0（2026-09-16）、約 1.4k stars | 探索型（非 LLM）。LLM 補助機能の有無は未確認 | 参考。Python コードのユニットテスト自動生成のベースライン | ユニットテスト専用 |
| TestPilot | MIT／JS・TS（npm パッケージ） | **アーカイブ（2025-02-03）**、後継は neu-se/testpilot2（未確認） | 関数のシグネチャ・本体・ドキュメントの使用例をプロンプトに入れ、失敗したら再プロンプト | 参考のみ | 研究プロトタイプ。README が日常利用は Copilot Chat を推奨 |
| ChatUniTest | MIT（core）／Java／Maven プラグイン | core 約 44 stars、2026-03 push | 生成 → 検証 → 修復の枠組み（Java のユニットテスト） | Java 顧客向けの参考。ターゲットとしては JUnit | 小規模プロジェクト。Java 限定 |
| HITS | 論文（arXiv 2408.11324）。公開リポジトリは今回未確認 | — | 複雑なメソッドをスライスに分割して LLM が各スライスのテストを生成 | 参考（スライス分割の発想） | 実装の入手可否が未確認 |
| Meta TestGen-LLM | **非公開**（論文 FSE 2024 Industry）。Qodo のブログが「Meta はコードを公開していない」と記載 | — | 既存テストを LLM で改善し、ビルド・実行・カバレッジ増の関門を通ったものだけ採用 | 参考のみ。「関門による採否判定」を設計に取り込む | 実装は入手不可 |
| Qodo Cover（旧 cover-agent） | **AGPL-3.0**／Python | **2025-06-15 に保守終了**と README に明記、約 5.7k stars | TestGen-LLM の OSS 実装。Cobertura XML のカバレッジを入力に生成 | 採用しない（AGPL と保守終了） | 同上 |
| TestSpark | MIT／Kotlin（IntelliJ プラグイン） | 約 90 stars、2026-07 push | IDE 内で複数の LLM を使ってユニットテスト生成 | 参考のみ | IDE 利用が前提 |
| TestForge（Luz7818） | MIT／Python | 小規模個人プロジェクト（実績・活動は未検証） | ミューテーションテストで「バグを検出できるテスト」だけを採用。Meta の ACH（FSE 2025）の再実装を自称 | 参考（品質関門の設計） | 信頼性未検証 |
| unit-test-agent（comain）、testgen-agent（u7465990）、agentic-unit-testing | 未確認 | 個人・学生規模とみられる | JaCoCo／PIT／coverage.py／mutmut で採否判定する LLM エージェント | 採用しない（参考の域を出ない） | 活動・品質未検証 |

- 補助 OSS（採否関門に使える）: mutmut（BSD-3-Clause、3.8.0、2026-09）、Cosmic Ray（MIT、8.7.0）、Hypothesis（MPL-2.0、6.169.3）、Faker（MIT、40.43.0）
- 避ける: **SDV（合成データ）は BUSL-1.1**（PyPI 表記）。商用製品への組み込みは制限があり得る
- ベンチマーク: TestGenEval（arXiv 2410.00752、Python の実プロジェクト）、SWT-Bench（NeurIPS 2024、arXiv 2406.12952、バグ再現テスト）。本システムの生成品質評価の枠組みの参考
- DB・SQL 向け LLM 研究（コード公開は未確認）: Google の SQL テストデータ生成（arXiv 2504.17203）、ShQveL（arXiv 2505.02012）、MIST（arXiv 2603.21530、2026-03）
- 出典: https://github.com/plasma-umass/coverup、https://arxiv.org/html/2403.16218v4、https://github.com/microsoft/codamosa、https://github.com/githubnext/testpilot、https://github.com/ZJU-ACES-ISE/chatunitest-core、https://arxiv.org/html/2408.11324v1、https://arxiv.org/pdf/2402.09171、https://www.qodo.ai/blog/we-created-the-first-open-source-implementation-of-metas-testgen-llm、https://github.com/qodo-ai/qodo-cover、https://github.com/JetBrains-Research/TestSpark、https://github.com/Luz7818/testforge

---

## 6. 本システムへの組み込み方（推奨と根拠）

### 推奨構成（Python／Flask 製システム向け）
| 層 | 採用 | 根拠 |
|---|---|---|
| 実行器 | pytest | Tavern・Schemathesis・pytest-postgresql・Pandera・Airflow／Dagster のテストがすべて乗る。JUnit XML でレポート化できる |
| DB 準備 | Testcontainers-python または pytest-postgresql | Docker 可否で選択。どちらも fixture 化できる |
| 前後比較・期待値テーブル | **自前実装**（スナップショット差分、期待 CSV、許容差・除外列・非決定値のマスク） | 該当する Python OSS が見つからず。Pandera／GE は補助（型・値域の検証） |
| データ品質 | Pandera（軽量）／GE（宣言的ルールを証跡化したいとき） | ライセンスが Apache-2.0・MIT で同梱しやすい |
| API | Schemathesis（仕様あり）＋ Tavern または Hurl（業務シナリオ） | Python から呼びやすい。Hurl は非同期バッチの完了待ちポーリングが自然に書ける |
| 生成の品質関門 | 実行成功、カバレッジ、ミューテーション（mutmut）、仕様トレース | CoverUp・TestGen-LLM の共通パターン |

### 生成コードのターゲット言語候補
1. **Python＋pytest**（第一候補）。LLM が最も得意で、生成→実行→修復ループを本システム内で完結できる
2. **Hurl**（API・状態ポーリング向け）と **SQL**（pgTAP／utPLSQL／tSQLt、DB 種別が一致する場合）。宣言的で人間のレビューが容易
3. **Java＋JUnit（Spring Batch Test／Karate／REST Assured／DBUnit 考え方）**。顧客のバッチが Java／Spring Batch の場合のみ。国内の顧客分布は未検証
4. **YAML（dbt unit tests／Soda／GE）**。顧客がそのツールを導入済みの場合のみ

### 使う／参考にする／採らない
- ライブラリとして使う: pytest、Testcontainers-python／pytest-postgresql、Pandera、Schemathesis、Tavern、Hypothesis、Faker、mutmut
- 生成ターゲット: Python、Hurl、pgTAP／utPLSQL／tSQLt、JUnit 系、dbt unit tests
- 参考にするだけ: Great Expectations（Data Docs・Expectation 設計）、Soda（コントラクト YAML）、CoverUp／TestGen-LLM／HITS（検証ループ）、DBUnit・reladiff（前後比較）、EvoMaster・Keploy
- 採らない: Dredd（アーカイブ）、Step CI（停止）、Qodo Cover（AGPL・保守終了）、SDV（BUSL）、TestPilot（アーカイブ）

### 要件定義への含意
- ジョブ起動・状態取得は**アダプタ層**で抽象化する（シェル／JP1 コマンド／Airflow REST／Spring Batch の起動）。本システム自体はジョブ基盤に依存しない
- 日付・基準日の制御（OS 時刻を変えられない前提）、冪等性、再実行、部分失敗時のリカバリ観点を、テスト観点の標準項目に入れる
- 期待値は LLM の推測ではなく仕様書・設計書の根拠に紐づける（A-5。根拠なき期待値は PASS に数えない）
- 生成テストは必ず実行して採否判定する（カバレッジやアサーション数だけで合格にしない）。LLM 生成テストの「カバレッジ・ミューテーションスコアと有効性の相関」を検証する 2026 年の再現研究が存在する（arXiv 2607.22880、未精読）

---

## 引用してはいけない数値
- スター数・ダウンロード数全般（参考値。意思決定の根拠にしない）
- CoverUp 論文の「CodaMosa 比で中央値カバレッジ 80% 対 47%」「81% 対 62%」は版により異なる（検索結果の要約。原文未精読）。引用するなら論文版を明記して原文を確認すること
- ChatUniTest の「EvoSuite の分岐カバレッジ 86.59% → 90.6%」（論文要約経由。条件・データセット未確認）
- Meta の「改善クラス 11.5%、提案の 73% が採用」（Qodo ブログ・要約経由。原論文 arXiv 2402.09171 で未確認）
- 集約サイトの Schemathesis 版（v4.22.4）。PyPI の 4.31.1 が正
- 一部の「awesome AI agents 2026」系リストの記述（裏取りなし）

## 未確認事項
- Soda Core v3 系のライセンス、v4 の ELv2 が自社 SaaS に抵触するかの法務判断
- DBUnit の現行版・ライセンス・リポジトリ位置、tSQLt のライセンス、pgTAP の SPDX 表記、utPLSQL の機能詳細（記憶ベースの記述を含む）
- Pandera の Hypothesis 連携の現状、GX の 0.x→1.x 破壊的変更の詳細
- JBatch（JSR-352）のテスト支援、JP1/AJS3・A-AUTO のコマンド／API とテスト連携の公開事例（日立マニュアルの時刻変更注意点のみ確認）
- Testcontainers の Docker 代替ランタイム（Podman 等）での動作と、プロジェクト方針（Docker 禁止）との整合
- HITS・Keploy の LLM 利用有無、EvoMaster が LLM を使う範囲、TestPilot 後継 testpilot2 の状態、小規模 LLM テスト生成リポジトリ（TestForge 等）の品質
- 2025〜2026 のバッチ／DB／データ検証に特化した LLM テスト生成 OSS は本調査では見つからなかった（「存在しない」の証明ではない。検索 13 回の範囲）
- GitHub API のレート制限で取得できなかったリポジトリ（ChatUniTest Maven プラグイン、HITS 等）の最終 push・ライセンス
