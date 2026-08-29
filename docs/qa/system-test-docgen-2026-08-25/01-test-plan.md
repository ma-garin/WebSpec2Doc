# テスト計画書 — ドキュメント作成画面 出荷前システムテスト

| 項目 | 内容 |
|---|---|
| 文書ID | STP-DOCGEN-20260825 |
| 版 | 1.0 |
| 被試験体 | WebSpec2Doc「ドキュメント作成」画面（`templates/partials/view-generate.html` と配下 API・crawler core）。作業ツリー @ main（未コミット変更 14 ファイルを含む状態） |
| テストレベル | システムテスト（出荷前診断） |
| 準拠体系 | ISO/IEC/IEEE 29119-3（文書体系）/ ISO/IEC 25010（品質特性）/ ISTQB（severity）/ OWASP ASVS 4.0・Top 10（セキュリティ観点）/ WCAG 2.1 AA（アクセシビリティ）/ Whittaker ツアー（探索的テスト）/ `quality/feature_contracts.yml`（機能契約・failure_modes） |
| 納品先水準 | 国防部門レベル（機密性・完全性・可用性・否認防止・データ外部送信の統制を最重視） |

## 1. 目的

ドキュメント作成画面の全機能・非機能について、出荷可否を第三者検証水準の証跡で判定する。指摘は evidence-only（再現手順と証跡のない指摘は採用しない）。

## 2. 範囲

### 2.1 対象

| 区分 | 対象 |
|---|---|
| 画面 | ウィザード 4 ステップ（①URL 入力・画面発見 ②ログイン設定・記録 ③クロール設定・URL 選択・参考資料 ④実行ビュー）、結果パネル、実行後の結果遷移 |
| API | `/api/discover`, `/api/discover-stream`, `/run`, `/api/cancel`, `/api/live-screenshot`, `/api/reference-docs`, `/api/doc-fusion`, `/api/sample-report`, `/api/result`, `/api/site`, `/api/login/*`, `/api/history*`, `/preview`, `/download*` |
| 契約 | `discover`(critical) / `crawl`(critical) / `login`(critical) / `doc_fusion`(high) / `zero_wait_sample_report`(medium) — failure_modes 計 41 件を全件トレース |
| 永続化 | `output/{host:port}/`（report.json/html/md, screenshots, snapshots, audit.jsonl, auth.json, site.json, reference_docs/, doc_fusion.json）、利用実績ログ |

### 2.2 範囲外

結果閲覧タブ群の詳細機能（テストケース表編集・遷移表・新旧比較）は「出力ファイルの存在と整合」まで。AutoRun 系画面。モバイル/タブレット（PC 専用製品）。本番相当の外部実サイト・実 LLM 接続。

## 3. 製品リスク分析

| リスク | 影響 | 対応トラック |
|---|---|---|
| クロール対象の指定を通じた内部ネットワーク到達（SSRF）・ローカルファイル読取 | 機密性: Critical | T06 |
| ログイン認証情報・セッションの平文保管、ログ出力 | 機密性: Critical | T07 |
| クロール取得データの外部送信（LLM API 等）の統制不能 | 機密性: Critical | T07 |
| 監査証跡（audit.jsonl）の欠落・改ざん可能性 | 否認防止: High | T07, T04 |
| クロール中の破壊操作（削除ボタン等）の実行 | 完全性（対象システム）: Critical | T03 |
| 途中停止・障害時の成果物不整合・復旧不能 | 可用性/信頼性: High | T03, T09 |
| クロール先由来の HTML による本ツール上での XSS | 完全性: High | T06 |
| 誤った成果物（画面漏れ・欠損スクショ）を正常品として納品 | 完全性: High | T04 |
| 発見・実行のタイムアウト・性能劣化で運用に耐えない | 性能: Medium | T08 |
| 操作不能・誤操作誘発（アクセシビリティ・状態表示） | 使用性: Medium | T10 |

## 4. テスト戦略

### 4.1 トラック構成（11 本並列 + 検証 2 本）

| ID | トラック | 25010 主特性 | 主手法 | モック port |
|---|---|---|---|---|
| T01 | 画面発見（discover / SSE / 範囲プリセット / 境界値） | 機能適合性・性能 | 契約ベース・境界値・Intellectual Tour | 9101 |
| T02 | ログイン設定・記録（simple / scrape / submit / record） | 機能適合性・セキュリティ | 契約ベース・状態遷移 | 9102 |
| T03 | クロール実行（selected/auto・並列度・cancel・checkpoint・robots・429・mutation・iframe・shadow） | 機能適合性・信頼性 | 契約ベース・Saboteur Tour | 9103 |
| T04 | 成果物・永続化・履歴・サンプル・再クロール（FedEx Tour） | 機能適合性・信頼性 | データライフサイクル追跡 | 9104 |
| T05 | 参考資料アップロード・doc_fusion | 機能適合性・セキュリティ | 契約ベース・等価分割 | 9105 |
| T06 | セキュリティ（入力系: SSRF / CSRF / パストラバーサル / 引数注入 / XSS） | セキュリティ | OWASP ASVS V5/V12/V13 攻撃入力 | 9106 |
| T07 | セキュリティ（認証情報保管 / データ外部送信 / 監査・否認防止 / テナント越境 / ヘッダ） | セキュリティ | OWASP ASVS V2/V3/V7/V8/V14 | 9107 |
| T08 | 性能効率性（応答時間・並列度スケーリング・SSE 遅延・リソース） | 性能効率性 | 計測（n≥3） | 9108 |
| T09 | 信頼性（同時実行・実行中プロセス停止・出力先異常・破損ファイル・再起動復旧） | 信頼性 | 障害注入（8766 専用インスタンス） | 9109 + app 8766 |
| T10 | 使用性・アクセシビリティ（WCAG 2.1 AA・キーボード・状態表示・エラー文言・ウィザード状態保持） | 使用性 | 実ブラウザ操作・Guidebook/Landmark Tour | 9110 |
| T11 | 保守性・移植性・互換性（静的解析・設定外部化・依存・ログ設計・ブラウザ前提） | 保守性・移植性 | 静的レビュー | 9111 |
| V01 | 検証（T01〜T07 の指摘を反証・再現） | — | 独立再現 | 9112 |
| V02 | 検証（T08〜T11 の指摘を反証 + 設計の契約カバレッジ照合） | — | トレーサビリティ監査 | 9112 |

### 4.2 手法

- 契約ベース: `feature_contracts.yml` の failure_modes 41 件それぞれに最低 1 ケース。
- 境界値: depth 1/10/11, max_pages 1/500/501, parallelism 1/8/9, 参考資料サイズ上限±1。
- 状態遷移: ウィザード 4 ステップ × 戻る/進む/キャンセル/再実行。
- 探索的: Whittaker ツアー（Guidebook / Saboteur / FedEx / Intellectual / Back Alley / All-Nighter 縮小版）。
- 攻撃: OWASP ASVS の該当章に基づく攻撃入力。
- 計測: 性能は n≥3 の中央値、単発値で断定しない。

### 4.3 判定

- 全指摘に ISTQB severity（Critical/High/Medium/Low）と 25010 カテゴリを付与。priority は別軸として付けない。
- evidence（証跡パス・ログ抜粋・スクリーンショット）のない指摘は完了報告書に採用しない。
- 検証トラックが再現できなかった指摘は「未確認」として別掲。

## 5. テスト環境

`02-test-environment.md` を正とする。要点: 本体 `http://127.0.0.1:8765`（認証オフ・ローカル対象許可）、破壊試験専用 `http://127.0.0.1:8766`、モック対象サイト `http://127.0.0.1:9101〜9112, 9199`（`env/mock_site.py`）。

## 6. 体制

| 役割 | 担当 |
|---|---|
| テスト統括・計画・完了判定 | 統括（本セッション） |
| トラック担当（設計・ケース・実行・ログ） | T01〜T11 各 1 名（サブエージェント） |
| 独立検証 | V01, V02（トラック担当とは別） |

## 7. 完了基準・中断基準

| 種別 | 基準 |
|---|---|
| 設計完了 | failure_modes 41 件がケースにトレースされている（V02 が照合） |
| 実行完了 | 全ケースが PASS/FAIL/BLOCKED/未実行 のいずれかで記録され、未実行には理由がある |
| 出荷判定 Go | 検証済み Critical = 0 かつ High = 0 |
| 条件付き Go | Critical = 0、High は改修計画付き |
| No-Go | 検証済み Critical ≥ 1 |
| 中断 | 本体 8765 が応答不能になった場合（再起動後に再開） |

## 8. 成果物

| # | 文書 | パス |
|---|---|---|
| 1 | テスト計画書 | `01-test-plan.md` |
| 2 | テスト環境定義 | `02-test-environment.md`, `env/mock_site.py` |
| 3 | テスト設計仕様書 | `tracks/T*/design.md` |
| 4 | テストケース仕様書 | `tracks/T*/cases.md` |
| 5 | テスト手順（自動化スクリプト） | `tracks/T*/scripts/` |
| 6 | テスト実行ログ・証跡 | `tracks/T*/execution-log.md`, `tracks/T*/evidence/` |
| 7 | インシデントレポート（検証済み） | `06-incident-report.md`（検証結果 `tracks/V*/`） |
| 8 | テスト完了報告書（25010 スコアカード・トレーサビリティ・出荷可否） | `07-test-completion-report.md` |

## 9. スケジュール（予実は完了報告書に記載）

環境準備 → 計画/環境文書 → 11 トラック並列（設計→ケース→実行→ログ） → 検証 2 本 → 統合・完了判定。
