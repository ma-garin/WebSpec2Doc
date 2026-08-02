# WS2D-TP-001 テスト計画書（マスターテスト計画）

- 版数: 2.0 / 作成日: 2026-08-02（前版 1.0 / 2026-07-16、46行）
- 準拠: ISO/IEC/IEEE 29119-2:2021（テスト計画のプロセス）、ISO/IEC/IEEE 29119-3（文書様式）、
  ISTQB Foundation Level Syllabus v4.0
- 詳細なテスト戦略・テストレベルのゲート定義・UAT シナリオの正本は `docs/TESTING_STRATEGY.md`。
  本書はその内容を要約しつつ、SIer 標準のテスト計画書として求められる構成要素
  （リスクベース戦略・入口出口基準・体制・スケジュール等）を補強し、MECE に保つ。
- 関連: `docs/TEST_LEVEL_POLICY.md`（製品としての守備範囲宣言）、`docs/DEFINITION_OF_DONE.md`
  （変更種別ごとの完了基準）、`quality/feature_contracts.yml`（機能契約・本計画のリスク母数）。

## 0. 文書概要

本書は WebSpec2Doc の開発チームが自社プロダクトに対して実施するテスト活動全体を計画する
マスターテスト計画書である。対象読者は開発者本人、レビューを行う AI エージェント
（code-reviewer / security-reviewer）、および将来ジョインする開発者・監査者を想定する。

前版（1.0、2026-07-16、46行）は見出しのみで内容が薄く、リスクベースの優先度付け・入口出口基準・
体制・スケジュールを欠いていた。本版では以下を新設・拡充する。

1. `quality/feature_contracts.yml` を実測し直し、機能数が前版が前提としていた 19 件から
   **51 件**に増加している事実を反映する（差分 32 件、約 2.7 倍）。
2. リスクレベル（`risk_level`）の分布を実測し、критical/high に対する重点配分の根拠を明示する。
3. 入口基準・出口基準・中断再開基準を明文化する（前版は出口基準相当のみ記載）。
4. 体制・役割、成果物一覧、リスク登録簿を新設する。

本書と `docs/TESTING_STRATEGY.md` の関係は「本書 = SIer 標準に沿った計画の骨格」
「TESTING_STRATEGY.md = ゲートの技術的詳細と UAT シナリオの正本」であり、
内容を複製せず参照する（MECE・二重管理を避ける）。

## 1. テストの目的とゴール

WebSpec2Doc は「公開 Web サイトを解析し、画面仕様・テスト設計・実行結果を実データから
生成する」ツールである。本テスト計画の目的は、この解析・生成パイプライン自体の品質を
ISO/IEC 25010 の品質特性に沿って担保することにある。

具体的なゴールは次の 5 点とする。

1. **機能適合性**: `quality/feature_contracts.yml` に登録された全 51 機能について、
   各機能が宣言する `required_tests`（happy_path・error_path 等）が、レベルに応じた
   テストで実際に検証されていることをトレーサビリティマトリクス（`WS2D-TM-001`）で示す。
2. **信頼性**: `failure_modes` に列挙された異常系（ログイン壁・タイムアウト・キャンセル・
   部分結果チェックポイント等）が critical/high 機能について網羅的に検証されていること。
3. **使用性**: axe-core によるアクセシビリティ検証とダークモード表示崩れ検証を L3 で実施。
4. **セキュリティ**: 認証・認可・入力処理変更時に L2 で重点検証し、AutoRun セキュリティ
   カーネル（送信ゲートウェイ・非信頼コンテンツ境界）は critical 機能として最優先で扱う。
5. **保守性**: カバレッジ計測とテスト資産のトレーサビリティ維持により、機能追加時の
   デグレードを機械的に検知できる状態を維持する。

これらのゴールは `docs/DEFINITION_OF_DONE.md` の Type A/B/C 完了基準と対応しており、
本計画が定めるテストレベルはすべて DoD のいずれかの MANDATORY/REQUIRED 項目に紐づく。

## 2. テスト対象と範囲

### 2.1 対象（in scope）

| 区分 | 対象 | 根拠 |
|---|---|---|
| ドメイン中核ロジック | `src/` 配下全パッケージ（crawler/analyzer/diff/generator/graph/ingest/llm/capture/registry/mbt/evidence/viewport/ux/apispec/autorun/techniques/wording/archive 等） | `WS2D-UT-001` §1 |
| Web 統合層 | `web/routes/*`（26 モジュール・200 エンドポイント）、`web/services/*`、`web/auth.py`、`web/tenancy.py` | `WS2D-IT-001` §2 |
| UI/フロントエンド | `templates/`、`static/js`、`static/css` | `WS2D-ST-001` §1 |
| 機能契約 | `quality/feature_contracts.yml` 全 51 件（`risk_level`: critical 11 / high 20 / medium 18 / low 2） | 本書 §5 で実測 |
| 受入シナリオ | 実利用者操作を想定した UAT（`WS2D-AT-001`） | ISTQB L4 |

### 2.2 対象外（out of scope、明示的除外）

| 対象外 | 理由 |
|---|---|
| `output/`（生成物ディレクトリ） | 実行結果であり、テスト対象のソースではない |
| `venv/`（依存ライブラリ本体） | サードパーティ資産。脆弱性監査は `make audit` で別途実施 |
| 性能テスト（負荷試験） | `docs/TESTING_STRATEGY.md` §3 が「現状対象外（将来拡張）」と明記 |
| 可用性テスト（障害注入・カオスエンジニアリング） | `WS2D-ST-001` §4 で未実施と確認済み |
| OWASP ZAP 等の専用ツールによる脆弱性スキャン | `WS2D-ST-001` §4 で未実施と確認済み。現状は XSS 回帰テストと L2 の入力検証テストのみ |
| Chromium 以外のブラウザ（Firefox/Safari/Edge） | `docs/TESTING_STRATEGY.md` §4 のツールチェーンが Playwright Chromium 固定 |
| モバイル・タブレット対応 | 製品方針として PC 専用（`docs/DEFINITION_OF_DONE.md` の対象外、開発チーム方針） |
| Ollama 経由 LLM 呼び出しの専用テスト | `WS2D-IT-001` §5: スタブ化の有無が本改訂時点で**未確認** |

### 2.3 製品ポリシーとの関係（重要な区別）

`docs/TEST_LEVEL_POLICY.md` は「WebSpec2Doc という**製品**が、顧客の Web サイトに対して
単体テストを生成しない（受入・システム・API 結合までを担う）」という**成果物としての
守備範囲宣言**である。これは本書が扱う「WebSpec2Doc **自身**の開発チームが自社コード
（`src/`・`web/`）に対して単体テストを書く」こととは階層が異なり、矛盾しない
（`WS2D-UT-001` 冒頭の注記と同じ整理）。本書は後者、すなわち開発チーム自身の QA 活動を計画する。

## 3. テストレベル定義

ISTQB Foundation Level が定める 4 テストレベルを全て実施する。任意レベルの省略は
`docs/TESTING_STRATEGY.md` §2 により禁止されている。

| レベル | 名称 | 目的 | 担当 | 入口基準 | 出口基準 | 実行コマンド |
|---|---|---|---|---|---|---|
| L1 | コンポーネントテスト（単体） | `src/` の関数・クラス単位の正しさを検証 | 実装者 | 対象モジュールの実装完了・型チェック通過 | 全 PASS・カバレッジ寄与確認 | `make test`（L1/L2 共通） |
| L2 | 統合テスト（結合） | route→service→store の HTTP レベル結合を検証 | 実装者 | route/service 実装完了・L1 が green | 全 PASS・主要 API 異常系網羅 | `make test`（L1/L2 共通） |
| L3 | システムテスト（E2E） | 実ブラウザでの UI→API→backend→出力の一気通貫検証 | 実装者（AI レビューエージェント併用） | HTML/JS/CSS 変更を伴うコミット前・L1/L2 green | 全 PASS・console error ゼロ・スクリーンショット証跡保存 | `make verify-ui` |
| L4 | 受入テスト（UAT） | ユーザーストーリー・非機能（使いやすさ）の確認 | プロダクトオーナー（配布先ユーザー含む） | 新機能リリース時・大幅 UI 変更時・L1〜L3 green | 利用者の確認・承認完了 | 手動（`WS2D-AT-001`） |

### 3.1 現在の規模（実測: 2026-08-02、静的カウント）

| 指標 | 値 | 取得コマンド |
|---|---|---|
| 全テストファイル数（L1〜L3 合算） | 213 | `find tests -name "test_*.py" \| wc -l` |
| L3（E2E）テストファイル | 20 | `find tests -name "test_*.py" -path "*/e2e/*" \| wc -l` |
| L1+L2（非 E2E）テストファイル | 193 | 213 − 20 |
| うち L2 寄り（`test_client`/`create_app` 使用） | 42 | `grep -rl "test_client\|create_app" tests/ \| wc -l` |
| うち L1 中核ロジックのみ（概算・重複を許容） | 151 | 193 − 42 |
| テスト関数総数（`def test_` 静的カウント） | 3,026 | `grep -rhE '^\s*def test_' tests/ \| wc -l` |

> 上表は `WS2D-UT-001`／`WS2D-IT-001`／`WS2D-ST-001`（いずれも 2026-08-02 改訂）と同一の
> 実測値であり、本書はこれらと数値を一致させている。動的な PASS/FAIL 件数（`make test`・
> `make verify-ui` の実行結果）は本改訂ではフル実行していない（**未実施**、§8 参照）。
> 参考値として 2026-07-16 時点の `make test`＝1,831 passed、`make verify-ui`＝200 passed/0 skipped
> があるが、当時はファイル数が非 E2E 108・E2E 32 と少なく、現構成（193／20）を反映していない。

## 4. テストタイプ

`docs/TESTING_STRATEGY.md` §3 のテスト種類マトリクスを踏襲し、本計画では実施状況を明記する。

| テストタイプ | L1 | L2 | L3 | L4 | 実施状況 |
|---|---|---|---|---|---|
| 機能テスト | ✓ | ✓ | ✓ | ✓ | 実施（全レベル） |
| 回帰テスト | ✓ | ✓ | ✓（ビジュアル回帰・XSS回帰） | — | 実施（`test_visual_regression_e2e.py`、`test_xss_regression_e2e.py` 等） |
| 探索的テスト | — | — | 一部（`exploration_capture` 機能自体が探索セッション記録を担う） | ✓（L4 は初見・マニュアルなしのジュニアテスト担当者ペルソナで実施） | 一部実施 |
| ユーザビリティ | — | — | 一部（axe-core・レイアウト崩れ検証） | ✓ | 一部実施 |
| セキュリティ | — | ✓（認証・入力処理変更時） | 一部（XSS 回帰のみ） | — | 一部実施。OWASP ZAP 等の専用スキャンは未実施 |
| 性能テスト | — | — | — | — | **対象外**（製品方針、将来拡張） |
| 可用性テスト | — | — | — | — | **未実施** |

探索的テストについて補足する。WebSpec2Doc は `exploration_capture` 機能（risk_level: high）
として「探索セッション記録／カバレッジヒートマップ」を製品機能自体に内包している。
これは開発チームが行う探索的テストの技法とは別に、製品が生成する成果物として
探索セッションを記録・可視化する機能であり、本書 §2.1 の対象に含まれる。

## 5. テスト戦略（リスクベースの優先度付け）

### 5.1 リスク分布の実測

`quality/feature_contracts.yml` を全件読了し、`risk_level` フィールドを集計した
（2026-08-02 実測、51 件全件を目視突合）。

| risk_level | 件数 | 比率 | 対応方針 |
|---|---|---|---|
| critical | 11 | 21.6% | L1〜L4 全レベルで `required_tests` 全項目＋`failure_modes` 全件をカバー対象とする |
| high | 20 | 39.2% | L1〜L3 で `required_tests` 全項目をカバー。L4 は主要シナリオのみ |
| medium | 18 | 35.3% | L1〜L2 で happy_path・error_path・evidence を最低限カバー |
| low | 2 | 3.9% | 回帰防止（parity・静的ガード）中心。個別 E2E は必須としない |
| 合計 | 51 | 100% | — |

前版（1.0）は「全 19 機能」を前提にしていたが、本改訂時点の実測では **51 件**であり、
約 2.7 倍に増加している。これは前版のリスク評価が現状の 32 件（全体の 63%）を
評価対象に含めていなかったことを意味し、本版最大の是正点である。

### 5.2 critical 機能一覧（最優先）

`discover`（URL解析/画面発見）、`crawl`（クロール/レポート生成）、`login`（ログイン/セッション）、
`account_auth`（アプリ利用者認証）、`tenant_membership`（テナント選択と所属管理）、
`tenant_isolation`（テナント分離）、`diff_history`（差分/履歴/再クロール）、
`document_mbt`（文書駆動MBT）、`sso_oidc`（SSO/OIDC）、
`autorun_stage_approval`（AutoRun段階承認パイプライン）、
`autorun_security_kernel`（AutoRunセキュリティカーネル）の 11 件。

これらは「解析の入口（discover/crawl/login）」「認証・テナントの根幹
（account_auth/tenant_membership/tenant_isolation/sso_oidc）」「差分の正しさ（diff_history）」
「AutoRun の中核制御と安全性（document_mbt/autorun_stage_approval/autorun_security_kernel）」の
4 系統に大別され、いずれも欠陥がデータ損失・情報漏洩・全ユーザー影響に直結しうる領域である。

### 5.3 リスクベース配分の実務上の意味

限られた開発リソースの中で、L3（実ブラウザ E2E、コストが高い）のテストケースを
新規追加する際は critical→high→medium の順で優先する。medium/low 機能に E2E を
追加する場合は「他の critical/high 機能の E2E カバレッジが要求水準を満たしていること」を
条件とする。これにより探索コストを機械的に配分する。

## 6. テスト環境

| 項目 | 内容 |
|---|---|
| OS | 開発: macOS（Darwin）。CI: GitHub Actions（`.github/workflows/spec-drift.yml` 等） |
| 言語ランタイム | Python 3.12 / venv |
| Web フレームワーク | Flask（`app.py` 起点） |
| ブラウザ | Chromium（Playwright 1.44.0 経由、pytest-playwright 0.5.0） |
| 解像度 | 1280×800（既定）、1366×768、1920×1080（拡張チェック） |
| DB | SQLite（`instance/auth.db`、テナントごとに `instance/tenants/{slug}/viewpoints.db`） |
| 主要環境変数 | `WEBSPEC2DOC_ALLOW_LOCAL=1`（ローカル/プライベート URL 許可）、`FLASK_TESTING=1`（`webbrowser.open` 抑止）、`WEBSPEC2DOC_AUTH_MODE`、`WEBSPEC2DOC_OIDC_PROVIDER` |
| E2E サーバ起動 | `tests/e2e/conftest.py` が 127.0.0.1:8765 でサーバを自動起動 |
| quarantine 機構 | `tests/e2e/conftest.py` に実装済み（2026-07-16 時点で登録 0 件、本改訂では未再確認） |

本番相当環境（顧客配布環境）は開発環境と同一構成（Python 3.12 + venv + Chromium）を
前提とし、Docker 等のコンテナ化は行わない（開発方針: PC 専用・非コンテナ運用）。

## 7. テストデータ方針

1. **evidence-only 原則**: `.claude/rules/functional-integrity.md` および
   `docs/TEST_LEVEL_POLICY.md` に基づき、観測していない事実を主張しない。テストデータは
   実際にクロール・観測した結果、または明示的にモック化した固定値のみを用いる。
2. **サンプルレポート**: `zero_wait_sample_report` 機能（`demo/sample_report/`）を
   デモ用の固定テストフィクスチャとして使用し、初回起動時のゼロ待ち体験を検証する。
   ただしサンプルは「自分の解析結果」と混同されないことも同時に検証観点とする
   （`failure_modes: sample_mistaken_for_own_analysis`）。
3. **境界値データ**: `field_definition_bva` 機能（`src/analyzer/bva.py`）が生成する
   境界値ケースを、項目定義書＋境界値分析シート（`spec.xlsx`）としてテストデータ生成の
   一部に利用する。
4. **テナント分離データ**: マルチテナントテストでは `output/tenants/{slug}/` 配下に
   テナントごとの隔離データを生成し、cross-tenant アクセス拒否を検証する
   （実データではなくテスト用に作成した複数テナントを使用）。
5. **個人情報**: 実在のユーザー個人情報は使用しない。認証テストはテスト専用アカウント
   （`test_client` 経由で作成する一時ユーザー）を用いる。
6. **URL 安全性**: `src/crawler/url_safety.py` によりテスト対象 URL はローカル/許可リスト内に
   制限し、意図しない外部サイトへのクロールを防止する。

## 8. 入口基準・出口基準・中断再開基準

### 8.1 入口基準（テストサイクル開始条件）

- 対象機能の実装が完了し、`python -m py_compile` 等の構文チェックを通過していること。
- `quality/feature_contracts.yml` に該当機能のエントリが存在し、`status: implemented` であること。
- L1 対象であれば、前段の設計（該当モジュールのインタフェース）が確定していること。

### 8.2 出口基準（テストサイクル完了条件、`docs/TESTING_STRATEGY.md` §5 に準拠）

1. L1+L2: 全テスト PASS、カバレッジ 80% 以上（`make coverage`、閾値は Makefile `--cov-fail-under=80`）。
2. L3（UI 変更時）: E2E 全テスト PASS、スクリーンショット確認済み、console error ゼロ。
3. L4（新機能時）: プロダクトオーナー（ユーザー）による確認・承認完了。
4. CRITICAL/HIGH 相当の未解決指摘事項がゼロであること（`WS2D-DL-001` の Severity 定義に準拠）。

### 8.3 中断・再開基準

| 状況 | 対応 |
|---|---|
| テスト環境（ローカルサーバ・Chromium）が起動不能 | テストサイクルを中断し、環境復旧後に再開。中断中の変更はコミット禁止 |
| L3 実行中に critical 相当の新規欠陥を検出 | 直ちに中断し、`WS2D-DL-001` の起票プロセスに従い記録。修正・再検証後に再開 |
| pre-commit hook が `.ui-verified` 不在でブロック | `make verify-ui` を再実行してから再開（DoD Type B の MANDATORY 項目） |
| 外部依存（OpenAI 等）が到達不能 | L2 はスタブ化されているため影響を受けない設計（`WS2D-IT-001` §5）。L3 で当該機能のみ一時除外し、他機能のテストは継続 |

現状、本改訂の作業自体は「静的集計のみ・`make test`/`make verify-ui` のフル実行なし」という
タスク制約の下で行っており、これは中断ではなく計画時点での**明示的なスコープ限定**である
（§3.1・§11 参照）。

## 9. 成果物一覧

`docs/sdlc/README.md` の文書体系表に基づく、テスト工程（40_test）の成果物一覧。

| 文書ID | 文書 | 本改訂での扱い |
|---|---|---|
| WS2D-TP-001 | テスト計画書（本書） | 全面改訂（46→本版） |
| WS2D-TV-001 | テスト観点表 | 全面改訂 |
| WS2D-UT-001 | 単体テスト仕様兼結果報告書（L1） | 既存（2.0、2026-08-02 拡充済み）。本書から参照 |
| WS2D-IT-001 | 結合テスト仕様兼結果報告書（L2） | 既存（2.0、2026-08-02 拡充済み）。本書から参照 |
| WS2D-ST-001 | システムテスト仕様兼結果報告書（L3） | 既存（2.0、2026-08-02 拡充済み）。本書から参照 |
| WS2D-AT-001 | 受入テスト仕様書（L4） | 全面改訂 |
| WS2D-TM-001 | トレーサビリティマトリクス | 全面改訂（51件対応） |
| WS2D-DL-001 | 不具合管理台帳 | 既存（2.0、2026-08-02 拡充済み）。本書から参照 |
| WS2D-TR-001 | テストサマリレポート | 全面改訂 |

前工程（`10_requirements/`・`20_design/`）・後工程（`50_operation/`・`60_quality/`）の文書は
本書の対象外。詳細は `docs/sdlc/README.md` を参照。

## 10. スケジュールと工数

本プロジェクトはスプリント/チケット単位の工数中央管理を行っていない
（ユーザー方針: TestRail/Jira 等の外部管理ツール不使用）。そのため本書では
時間工数（人日）を見積もらず、**マイルストーン（機能追加・PR 単位）に紐づく実施頻度**として
スケジュールを定義する。

| フェーズ | 実施頻度 | トリガー |
|---|---|---|
| L1/L2 | 毎コミット | pre-commit hook が `make test` を強制実行 |
| L3 | HTML/JS/CSS 変更を含む全コミット前 | pre-commit hook が `.ui-verified` マーカーの有無を検査 |
| L4（受入） | 実装が落ち着いた区切り（マイルストーン）ごと | 開発チームの判断（ユーザー運用方針: 単体・結合は毎回、システム/受入は区切りごと） |
| 全レベル・区切りごとの棚卸し | 機能追加やドキュメント刷新の節目 | 本改訂（2026-08-02）のような全面見直し |

工数を数値化しない代わりに、実施頻度を機械的ゲート（pre-commit hook）に落とし込むことで
「計画されたが実施されない」リスクを構造的に低減している（`docs/DEFINITION_OF_DONE.md` 参照）。

## 11. 体制と役割

| 役割 | 担当 | 責務 |
|---|---|---|
| 実装者 | 開発者本人 | L1/L2 テストコードの作成・実行、L3 テストシナリオの作成 |
| AI レビューエージェント（code-reviewer） | Claude Code エージェント | コード品質・保守性の静的レビュー（`docs/TESTING_STRATEGY.md` §4） |
| AI レビューエージェント（security-reviewer） | Claude Code エージェント | セキュリティ観点の静的レビュー |
| 機械的ゲート | pre-commit hook（`.githooks/pre-commit`） | L1/L2/L3 未実施でのコミットを技術的に阻止 |
| プロダクトオーナー | 開発者本人（配布先では利用者） | L4 受入テストの実施・合否判断・リリース承認 |
| 品質ハーネス | `scripts/quality_harness.py`（L0） | `feature_contracts.yml` の機械的整合性検証 |

体制は少人数（実質 1 名の開発者＋AI エージェント群）であるため、レビューの独立性は
人によるダブルチェックではなく「機械的ゲート（pre-commit hook・quality_harness.py）」と
「AI エージェントによる客観的な静的解析」で代替している。これは体制上のリスクでもあり、
§12 のリスク登録簿にも記載する。

## 12. リスクと対策

| リスク | 発生確率 | 影響度 | 対策 |
|---|---|---|---|
| E2E テストがフラキーになる | 中 | 中 | 再試行2回まで許容・原因調査必須（`docs/TESTING_STRATEGY.md` §6） |
| テストメンテナンスの遅延 | 高 | 高 | 機能追加と同一 PR にテストを必須化 |
| L3 省略の習慣化 | 高 | 高 | pre-commit hook + `.ui-verified` マーカーで機械的に強制 |
| L4（受入）の省略 | 中 | 高 | DoD にチェックリストを設け記録を残す |
| **機能契約の母数不整合が長期間放置される** | 中 | 高 | 本改訂で 19→51 件の乖離を検出。次回以降は改訂のたびに `grep -c feature_id` で母数を再確認する運用に変更 |
| **テスト資産規模の増加にテスト結果報告が追随しない** | 高 | 中 | ファイル数（193/20）と実行結果（1,831 passed 等）の計測日を必ず併記し、乖離があれば明示する運用を本改訂で導入 |
| ドキュメント間の実測値の微小な不一致（例: routes.json 件数） | 中 | 低 | 各文書に取得コマンドを併記し、監査者が独立に再現できる状態を維持する |
| Ollama 経由 LLM 呼び出しのテスト方針が未確定 | 低〜中 | 中 | 次回改訂で `src/llm/provider.py` の分岐実装を直接確認し追記（`WS2D-IT-001` §6 に申し送り済み） |
| 体制の属人化（実質 1 名開発） | 中 | 高 | AI エージェント（code-reviewer/security-reviewer）による機械的な第三者視点の代替 |

## 13. ツール

| カテゴリ | ツール | バージョン | 用途 |
|---|---|---|---|
| テストランナー | pytest | >=8.0 | L1・L2 |
| カバレッジ | pytest-cov | >=5.0 | カバレッジ計測（`make coverage`） |
| E2E / システム | pytest-playwright | 0.5.0 | L3 |
| ブラウザ | Chromium（Playwright） | 1.44.0 | L3 実行エンジン |
| 静的解析 | ruff / mypy | — | `make lint` |
| 機能契約検証 | `scripts/quality_harness.py` | — | L0（機能契約の機械検証） |
| トレーサビリティ生成 | `scripts/generate_traceability_doc.py` | — | `WS2D-TM-001` の機械生成補助 |
| コードレビュー | code-reviewer エージェント | — | 静的品質確認 |
| セキュリティレビュー | security-reviewer エージェント | — | セキュリティ静的検証 |
| Git ゲート | pre-commit hook | — | L1/L2/L3 の自動強制実行 |

## 14. 承認欄

本書は SIer 標準のテスト計画書としての体裁上、承認欄を設けるが、実運用では
`docs/process/functional-integrity-gate.md` が定める機械的ゲート（pre-commit hook・
quality_harness.py・DoD チェックリスト）が実質的な承認機能を担っている。
人による承認は以下の欄に記録する。

| 役割 | 氏名 | 日付 | 承認 |
|---|---|---|---|
| 作成者 | 開発チーム | 2026-08-02 | — |
| レビュー者 | （AI エージェント: code-reviewer / security-reviewer） | — | — |
| 承認者（プロダクトオーナー） | — | — | 未承認 |

上流文書（`WS2D-RD-001` 等）の承認前に本書の内容を実装へ反映することは、
`.claude/rules/absolute-rules.md` A-7 の原則上避けるべきだが、本書はテスト工程の
文書であり、既存の実装済み機能（51件）を後追いで文書化するものであるため、
承認待ちによる手戻りは発生しない（as-built 文書としての性質）。

## 15. 改訂履歴

| 版 | 日付 | 内容 | 作成者 |
|---|---|---|---|
| 1.0 | 2026-07-16 | 初版（46行、テストレベル概要と合格基準のみ） | 開発チーム |
| 2.0 | 2026-08-02 | 全面改訂。テスト対象/対象外の明確化、リスクベーステスト戦略（51機能・risk_level分布の実測反映）、入口/出口/中断再開基準、体制・役割、リスク登録簿、成果物一覧、スケジュール方針を新設。機能母数を19→51に修正 | 開発チーム |
