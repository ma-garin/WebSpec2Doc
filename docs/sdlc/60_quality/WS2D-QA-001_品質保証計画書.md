# WS2D-QA-001 品質保証計画書

- 文書ID: WS2D-QA-001
- 版数: 2.0 / 作成日: 2026-08-02 / 準拠: IEEE 730（SQA）、ISO/IEC 25010（品質特性モデル）、ISTQB Foundation Level
- 正本参照: 完了定義 `docs/DEFINITION_OF_DONE.md`、機能整合性ゲート `docs/process/functional-integrity-gate.md`、機能契約 `quality/feature_contracts.yml`。本書はこれらを統合し、ISO/IEC 25010の8品質特性ごとの評価とゲート実装の詳細を追加した統合ビューである。

## 1. 品質方針と目標

WebSpec2Doc の品質保証は以下の3つの方針で運営する。

1. **機能整合性を最優先する。** 「UIがある」「ボタンがある」「テストが通った」だけでは完了と扱わない。実行パス（UI→API→backend route→service/core→出力→永続化→エラー処理→利用者可視の証跡）を実際に検証する（`.claude/rules/functional-integrity.md`）。
2. **狩野モデル×VDD（Value-Driven Development）。** 当たり前品質（品質ゲートの正常化・死んだUIの排除）の回復を最優先とし、その上で外部品質・魅力的品質へ投資する。優先順位を逆にしない。
3. **evidence-only 原則を品質保証にも適用する。** 「動くはず」という推測を完了根拠にしない。実行した証跡（テストログ・スクリーンショット・quality_harness.pyの出力）を必ず残す。

品質目標（2026-08-02時点）: L0〜L3の全ゲートgreen維持、カバレッジ80%以上の維持、critical/highリスク機能の異常系テスト100%網羅（`required_tests`充足）。単独開発体制であっても、これらのゲートを「後で確認する」対象にせず、コミット単位で維持することを方針とする。

## 2. 品質特性ごとの目標と測定方法（ISO/IEC 25010）

ISO/IEC 25010 が定める8つの品質特性それぞれについて、本プロダクトでの目標・測定方法・実測値（測定していないものは「未測定」と明記）を示す。

| # | 品質特性 | 目標 | 測定方法 | 実測・現状 |
|---|---|---|---|---|
| 1 | 機能適合性 (Functional Suitability) | 契約化された全機能が実行パスを持ち、異常系を含め検証済み | `scripts/quality_harness.py`（L0ゲート） | PASS。`quality/feature_contracts.yml` には51件のfeature_idが登録されている（2026-08-02実カウント。`docs/sdlc/README.md`記載の「validated_features=19」は2026-07-16時点の値であり、その後の機能追加で乖離しているため要再測定） |
| 2 | 性能効率性 (Performance Efficiency) | クロール・生成処理が実用的な時間で完了する | 個別施策単位のBefore/After計測（コミットログ） | 部分測定。実績: 「最初の解析を短くする（無反応1.8秒→0.14秒、実時間-37%）」という個別コミットの効果測定はあるが、**継続的な性能SLA・回帰検知の仕組みは未整備（未測定）**。対象サイト側の性能はCore Web Vitals（LCP/CLS/TTFB）を計測する機能（`performance_probe.py`）を持つが、これは自プロダクトの性能ではなく対象サイトの計測結果である |
| 3 | 互換性 (Compatibility) | 対応OS・ブラウザでの動作保証 | `src/doctor.py` の環境診断、CI実行環境 | Python 3.11〜3.12のみ対応（playwright 1.44.0のwheel制約）。ブラウザはChromium固定（Firefox/WebKit対応は`spec-6-2`でスコープ外と明記）。CI（`.github/workflows/ci.yml`）はubuntu-22.04固定。macOS/Linux両対応のシェル分岐（`gdate`/`date`, `gtimeout`/`timeout`）は`.githooks/pre-commit`で確認。**Windows対応は未測定** |
| 4 | 使用性 (Usability) | 利用者がエラーなく主要フローを完了できる | DoD Type B（ブラウザ目視確認、1920×1080/1366×768） | 対象サイトへのUX自動レビュー機能（axe-core＋ニールセン10原則ヒューリスティック）は存在するが、これは**プロダクト自身のUIには適用されていない**（対象範囲外）。自プロダクトのUIはDoD Type Bの人間による目視確認に依存しており、定量的なユーザビリティスコアは**未測定** |
| 5 | 信頼性 (Reliability) | テストgreen維持、既知の不安定要因の管理 | `make test`, `make verify-ui` | L1/L2: 1,831 passed（2026-07-16時点）。L3 E2E: 200 passed / 0 skipped。カバレッジ84.30%（閾値80%）。既知の環境依存flakyテストの存在は開発運用メモに記録があるが、**件数・具体的テスト名の一覧は本書執筆時点で未確認** |
| 6 | セキュリティ (Security) | 既知の脆弱性クラスからの防御 | `make security`（bandit -ll・pip-audit） | Medium以上ゼロを目標値として運用。SSRF対策（`url_safety.py`, `egress_gateway.py`）・prompt injection対策（`untrusted_content.py`）・secrets scan（`scan_for_secrets`）を実装済み。**脆弱性0件を継続的に記録した時系列データは未測定**（`make security`は実行時点のみの静的なスナップショット） |
| 7 | 保守性 (Maintainability) | 層分離・小さい関数・モジュール登録の徹底 | `docs/sdlc/_asbuilt/modules.json` 実測、`quality_harness.py`の未登録モジュール検知 | 237モジュール実測。関数長 中央値12行・p90 44行・最大228行（詳細は`WS2D-CS-001`§5）。フォーマルな保守性指標（循環的複雑度等）は**未測定** |
| 8 | 移植性 (Portability) | 環境構築の再現性 | `make setup`, `src/doctor.py` | venv・Chromium runtime双方を`.runtime/ms-playwright`固定で再現。Docker化は方針として不採用（社内運用メモ）。**コンテナ環境での動作は未測定** |

上表のうち性能効率性・使用性（自プロダクト）・信頼性の一部・セキュリティの時系列・保守性の複雑度・移植性のコンテナ対応は明確に「未測定」である。これを隠さず本書に記録することが、次回の品質保証活動の優先順位付けの材料になる。

## 3. 品質ゲート一覧

`scripts/quality_harness.py`・`.githooks/pre-commit`・`Makefile` の実際の中身を確認した結果、以下のゲートが存在する。「強制」列は、そのゲートが**機械的に強制**されるか（スキップ不可）、**手動実行が前提**か（実行を忘れても誰も止めない）を区別する。

| ゲート層 | 内容 | コマンド | いつ実行されるか | 強制 |
|---|---|---|---|---|
| L0 | 機能契約の機械検証（未登録モジュール検知・UI-only禁止・シンボル実在確認・異常系必須） | `python scripts/quality_harness.py` | 手動（完了前にCLAUDE.mdが実行を指示） | 手動実行が前提。pre-commitには組み込まれていない |
| L1/L2 | 単体・結合テスト | `make test` | pre-commit hookで**全コミット時に自動実行** | 機械強制（PY_CHANGED または UI_CHANGED 時） |
| L3 | 実ブラウザE2E | `make verify-ui` | UIファイル（.html/.js/.css）変更時のみ、pre-commitが`.ui-verified`マーカーの存在とハッシュ一致を要求 | 機械強制（UI変更時のみ。マーカー有効期限2時間） |
| カバレッジ | ≥80% | `make coverage` | 手動 | 手動実行が前提 |
| 静的解析 | ruff・mypy・独自スクリプト2本 | `make lint` | 手動 | **pre-commitに含まれない**（既知のギャップ、下記参照） |
| フォーマット | black | `black .` | 手動 | **pre-commitに含まれない** |
| セキュリティ | bandit（Medium以上ゼロ）・pip-audit | `make security` | 手動 | **pre-commitに含まれない** |
| 構文チェック | `py_compile` | pre-commit内 | 全コミット時 | 機械強制 |
| verify-all | quality-harness + test + verify-ui の合成 | `make verify-all` | 手動（コミット直前1回を推奨） | 手動実行が前提 |

**重要な発見（本書改訂で明らかになったギャップ）**: `docs/specs/CONVENTIONS.md` §3が定める品質ゲート順序（black→ruff→mypy→bandit→pytest→quality_harness→verify-ui）は「開発者が手動で通すべき順序」であり、pre-commit hookが機械的に強制するのは「構文チェック」「pytest L1/L2」「UI変更時のハッシュ照合」の3点のみである。black・ruff・mypy・banditの未実行は、コミット自体をブロックしない。CIでの強制の有無は `.github/workflows/ci.yml` の詳細な中身を本書執筆時点で読み込んでおらず、**未確認**。これは重要な監査対象であり、CI設定ファイルの内容確認を次回の品質保証活動の課題とする。

## 4. Definition of Done（完了の定義）

`docs/DEFINITION_OF_DONE.md`（バージョン1.0.0、IEEE 730-2014・ISTQB Foundation Level準拠）を統合する。

**原則**: pytestが全テストPASSであることは「完了」ではない。それは「コードが壊れていない」というL1/L2レベルの確認にすぎない。L3（システムテスト：ブラウザ確認）とL4（受け入れテスト：ユーザー確認）が完了して初めて「完了」である。

変更タイプ別のDoD:

**Type A（バックエンド変更、`src/**/*.py`, `web/**/*.py`, `app.py`）**
- MANDATORY: `make test`全PASS＋カバレッジ80%以上、構文エラーなし、pre-commit PASS。
- REQUIRED: code-reviewerエージェント実行でHIGH以上の指摘なし、変更理由・影響範囲をコミットメッセージに記載。

**Type B（フロントエンド変更、`static/**/*.js`, `static/**/*.css`, `templates/**/*.html`）★最重要**
- MANDATORY: `make test`全PASS、`make verify-ui`でE2E全PASS（`.ui-verified`マーカー生成）、マーカーがstagedファイルより新しいタイムスタンプを持つこと。
- REQUIRED（省略禁止）: ブラウザで実際に変更機能を操作して確認（1920×1080）、1366×768でレイアウト崩れ確認、変更した全ユーザーフローを最初から最後まで通して確認、ブラウザコンソールにエラーなし、ユーザーストーリー（受け入れ基準）充足確認、スクリーンショットを`tests/e2e/screenshots/`に保存。
- PROHIBITED: pytest PASSのみでの完了判断、ブラウザ確認なしのコミット・プッシュ、E2Eスキップでの UI 変更コミット、「動くはず」という推測での完了宣言。

**Type C（ドキュメント変更、`docs/**/*.md`, `README.md`, `CLAUDE.md`, `AGENTS.md`）**
- Markdown構文チェック、内部リンク（相対パス）の有効性確認、古い情報を更新した場合は関連ドキュメントも合わせて更新。

**機械的ゲート（pre-commit hook）**: git commit実行時、HTML/JS/CSS変更の有無で分岐する。変更なしなら通常のpytestチェックのみ。変更ありなら`.ui-verified`の存在・新旧・ハッシュ一致を確認し、いずれか不備があればBLOCKED（「make verify-uiを実行してください」）。

**違反時の対応**: DoD未達のままコミット・プッシュが判明した場合、(1)即座にインシデントとして記録（`docs/INCIDENT_POSTMORTEM.md`形式）、(2)問題のあるコミットを特定し影響評価、(3)修正実施しDoDを完全に満たしてから再プッシュ、(4)再発防止措置を`docs/TESTING_STRATEGY.md`へ反映、の4段階で対応する。

## 5. Functional Integrity Gate の説明

`docs/process/functional-integrity-gate.md` を統合する。このゲートは、「画面がある」「ボタンがある」「テストが通った」だけで完了扱いすることを禁止するための開発プロセスルールであり、Claude / Codex / 人間レビュー共通のルールである。

過去の問題事例（本ゲート新設の背景）: UX評価・ペルソナ評価・戦略レビュー・コードレビューを実施したにもかかわらず、解析速度・ログイン必須画面・途中停止・robots制限・途中結果保存などの根幹機能が評価対象から漏れた実績がある。

**完了判定の必須実行パス**:

```text
UI → API → backend route → service/core → output → persistence → error handling → user-visible evidence
```

**不十分な完了根拠**（これだけでは完了扱いしない）: UIが存在する／ボタンが存在する／テストが通る／ペルソナ評価をした／戦略レビューをした／画面が見やすい／コードがきれい／それっぽい説明ができる。

**必須確認観点**（critical/high risk機能で最低限確認する）: happy path／failure path／timeout／cancellation／auth・login wall／robots・access restriction／partial result・recovery／logs or evidence／user-visible status or error。

**未確認ルール**: 未確認の項目は必ず「未確認」と書く。未確認の項目を「完了」「検証済み」「問題なし」と表現してはいけない。本書自体もこのルールに従い、§2・§3で複数の項目を「未測定」「未確認」と明記した。

**RCAルール**: 開発プロセスの失敗が起きた場合、場当たり的な反省は禁止。5 Whys／Fishbone／FMEA／CAPA／DoD updateのいずれかの枠組みを明示して分析する（詳細は本書§9）。

**禁止事項**: コードを読まずにレビュー済みと言う／実行パスを追わずに価値評価だけで完了扱いする／UIだけ存在する未接続機能を残す／エラーを利用者に見せずに失敗する／証跡なしに検証済みと報告する。

## 6. レビュー体制と観点

- 開発体制は現時点で単独開発者（`git log`のコミッター表記は`ma-garin`のみを確認）。相互レビュー（複数人でのpeer review）体制の詳細は**未確認**。
- コードレビューは`code-reviewer`エージェント（AIエージェント）の実行をMANDATORY相当として運用し、HIGH以上の指摘なしを基準とする（`docs/DEFINITION_OF_DONE.md` Type A）。
- レビュー観点は本書§2〜5の各ゲート・DoD項目に加え、`WS2D-CS-001`§18のレビュー観点チェックリストを併用する。
- 最終承認（人間による目視確認）はDoD Type Bで必須とし、省略できない（PROHIBITED項目に明記）。
- 開発体制が単独である現状は、相互チェックの欠如というリスクを内包する。AIエージェントレビュー＋人間の自己レビューという二段構えで代替しているが、これは「複数人レビュー」と同等の効果を持つとは限らない点を正直に記録する。

## 7. 静的解析・動的解析の方針

- **静的解析**: ruff（`E,F,W,I,UP,B`）・mypy（py3.12、`warn_unused_ignores`等）・bandit（`-ll`＝Medium以上）を`pyproject.toml`で設定。実行は`make lint`／`make security`。
- **動的解析**: pytest（単体・結合、`tests/`）とPlaywright実ブラウザE2E（`tests/e2e/`）。テストピラミッドは「単体（フェイク注入・高速）→結合（実ファイルI/O・tmp_path）→実ブラウザE2E（専用スレッド・デモサイト標的）」の3層。
- フェイクの前例: `_FakeRecorderPage`（`tests/test_capture.py`）、`_FakeClock`・`_WaitProbePage`（`tests/test_real_site_resilience.py`）。新規フェイクはこれらのパターンに倣う。
- 環境依存テストの罠（`docs/specs/CONVENTIONS.md`既知の罠3）: CIのunitジョブはvenvなし・ブラウザ未導入。「この環境なら全PASS」型のテストはCIで落ちる。環境不変の性質（例:「FAIL項目には必ずfixが付く」）を検証する設計にする。

## 8. テスト戦略の概要

詳細は `WS2D-TP-001`（テスト計画書、`docs/sdlc/40_test/WS2D-TP-001_テスト計画書.md`）および `docs/TESTING_STRATEGY.md` を参照。本書では概要のみ示す。

- L1/L2（単体・結合）: `tests/`配下、非E2Eテストファイル108本（`docs/sdlc/README.md`実測サマリ2026-07-16時点）。
- L3（システム・E2E）: `tests/e2e/`配下、E2Eテストファイル32本。デモサイト標的は`contact.html`（フォーム）・`dashboard.html`（モーダル/タブ/アコーディオン）・`spa.html`・`checkout.html`。`login.html`はログインウォール検出でE2E標的から除外する（既知の罠5）。
- テスト関数総数1,985（`grep -rhE '^\s*def test_' tests/ | wc -l`実測）。
- E2E実行時の既知の罠（CONVENTIONS §4）: pytest-playwrightのセッションfixtureがメインスレッドのasyncioループを保持するため、実ブラウザ処理は専用スレッドで実行する（`_run_in_thread`パターン）。ポート衝突回避（8765=GUI・8766=demo・8894/8896=既存e2e）。

## 9. 不具合の予防と再発防止プロセス

- 不具合は `WS2D-DL-001`（不具合管理台帳、`docs/sdlc/40_test/WS2D-DL-001_不具合管理台帳.md`）に起票→原因分類→対策→検証→クローズの手順で管理する。
- **開発プロセス失敗時は必ず名前付きRCAフレームワークを使う**（`.claude/rules/functional-integrity.md`）。使用可能な枠組み: 5 Whys／Fishbone（特性要因図）／FMEA（故障モード影響解析）／CAPA（是正・予防処置）／DoD update（完了定義の更新そのものを是正処置とする）。**場当たり的な反省（フレームワーク名を伴わない自由記述の反省）は禁止**。
- 実例として本書§3で発見した「pre-commitがblack/ruff/mypy/banditを強制していない」というギャップは、CAPA的に扱う場合: 是正処置（本書での明記・開発者への周知）と予防処置（pre-commitへの追加を検討する、またはCI側での強制を確認する）の両方を検討する対象とする。
- レトロ（振り返り）の学びは`retro`スキル経由でlessonsとして蓄積する運用（ユーザー側の運用メモ）。

## 10. メトリクスと監視

品質メトリクスは何を測り、どう使うかを明確にする。

| メトリクス | 何を測るか | どう使うか | 実測（2026-07-16、`docs/sdlc/README.md`） |
|---|---|---|---|
| 機能契約検証 | feature_contracts.ymlの整合性 | L0ゲートのPASS/FAIL判定 | validated_features=19（注: 2026-08-02時点のfeature_contracts.yml実物は51件のfeature_idを含み、この数値は要再測定。§2参照） |
| L1/L2テスト | 単体・結合の合否 | コミットのブロック判定 | 1,831 passed |
| L3 E2E | 実ブラウザ動作 | UI変更のリリース可否判定 | 200 passed / 0 skipped |
| カバレッジ | テストが到達したコード行の割合 | 80%を下回ると`make coverage`が失敗 | 84.30% |
| Blueprint/エンドポイント数 | APIの規模 | 変更影響範囲の把握 | 17 Blueprint / 121エンドポイント |
| テスト関数総数 | テスト資産の規模 | テスト負債の把握 | 1,985 |
| トレーサビリティGAP | 要件⇔テストの対応漏れ | `WS2D-TM-001`（機械生成）で0を維持 | 0 |
| quarantine（隔離テスト） | flaky等で一時隔離したテスト数 | 隔離の常態化を防ぐ監視 | 0 |

可観測性機能（`web/services/metrics.py`、`/metrics` Prometheusエンドポイント）は対象サイトのクロール・通知・ジョブキューの実行時メトリクスを提供するが、これは**プロダクト自身の品質メトリクスではなく運用監視機能**である点に注意する（混同しないこと）。

## 11. 品質記録の管理

- テスト仕様兼結果報告書（`WS2D-UT-001`単体・`WS2D-IT-001`結合・`WS2D-ST-001`システム・`WS2D-AT-001`受入）を`docs/sdlc/40_test/`配下で管理する。
- トレーサビリティマトリクス（`WS2D-TM-001`）は`scripts/generate_traceability_doc.py --write`で機械生成する。手動更新しない。
- 2026-07-26に実施された全体テスト証跡パック（`docs/sdlc/40_test/zero-base-20260726/`、01_unit〜05_traceabilityのHTML＋index＋manifest.json）が存在することを確認した。これは特定時点でのゼロベース評価の記録であり、継続的な品質記録の一形態として位置づける。
- 品質ハーネス（`scripts/quality_harness.py`）の実行結果（PASS/FAIL＋エラー一覧）はコマンド実行のたびの標準出力であり、恒久的な記録として別途保存する仕組みは**本書執筆時点で確認できず未確認**。

## 12. 継続的改善

- ADR（Architecture Decision Record、`docs/adr/0001`〜）でアーキテクチャ判断を記録する。
- レトロの学びは`retro`スキル経由で蓄積する（プロセス改善知見、実装詳細とは別に管理）。
- 依存更新戦略（`docs/specs/spec-6-2_dependency_update_strategy.md`）のような「意図的に技術的負債を先送りし、判断基準を明文化する」アプローチは、品質保証における継続的改善の一形態として位置づける（playwright 1.44.0固定の判断基準表・四半期レビューサイクル）。
- 本書自体が「実測に基づく統合ビュー」であることの帰結として、次回改訂時は§2の「未測定」項目を優先的に埋めることを推奨する。

## 13. 妥当性確認と検証（Verification & Validation）

IEEE/ISO用語における「検証（Verification）」と「妥当性確認（Validation）」を区別して運用する。

- **検証（Verification）**: 「正しく作っているか（building the product right）」の確認。本書のL0〜L3ゲート（quality_harness・pytest・E2E）はすべて検証活動である。
- **妥当性確認（Validation）**: 「正しいものを作っているか（building the right product）」の確認。DoD Type BのREQUIRED項目（ユーザーストーリー・受け入れ基準の充足確認、ブラウザでの実際の操作確認）が妥当性確認に相当する。
- 本プロダクトの評価では「検証は自動化ゲートで機械的に、妥当性確認は人間の目視確認で」という役割分担を取っている。どちらか一方だけでは「完了」と扱わない（Functional Integrity Gateの原則と同一）。
- **リスクベーステスト**: `quality/feature_contracts.yml`の`risk_level`（critical/high/medium/low）に応じてテストの厚みを変える。critical/highは`failure_modes`と`required_tests`が必須であり、`scripts/quality_harness.py`の`RISK_LEVELS_REQUIRING_FAILURE_TESTS = {"critical", "high"}`が機械検証する。medium/lowはこの必須化ルールの対象外であり、テストの手厚さは実装者の判断に委ねられる。

## 14. テストの質を測るテスト（自己検証）

一般的なテスト戦略は「テストが通ったこと」までしか確認しないが、本プロダクトは「そのテストが本当に欠陥を検出できるか」まで確認する仕組みを持つ。

- AutoRunで生成したテストに対し、ミューテーションテスト（意図的にコードへ欠陥を注入し、テストがそれを検出するかを確認する手法）を実行する（`web/services/mutation_verifier.py: run_self_check`）。
- 出力は「自己検証スコア」と「弱いテストの一覧」であり、`mutation_verification.json`として永続化される（`output/{domain}/qa_process/mutation_check/`）。
- この仕組みは「テストカバレッジが高い＝品質が高い」という誤った等式を避けるための補助線であり、§10のカバレッジ数値と併読することを推奨する。
- 適用できない場合は`self_check_not_applicable`として明示し、無理に数値を作らない（evidence-only原則の適用例）。

## 15. 品質に関するAIエージェント運用ルール

- LLMを用いる経路（観点生成・UXレビュー・QAチャット等）は、実測（confidence 1.0）とLLM由来（confidence 0.9以下）を必ず区別して出力する（`src/llm/prompt_guard.py`のQA_PRINCIPLES）。
- LLM出力の幻覚（実在しないセレクタ・引用の捏造）はフィルタで除去する（`filter_hallucinated_findings`, `src/ingest/llm_extractor.py`のquote突合）。品質保証の観点からは、LLM経路の追加はこのフィルタ実装とセットで行うことをゲートとする。
- 開発作業そのものにAIエージェント（Claude・Codex）を用いる場合も、本書§4のDoD・§5のFunctional Integrity Gateは同一の基準で適用する。「AIが実装した」ことは検証省略の理由にならない。
- AIエージェントによるレビュー・評価（`code-reviewer`等）は、コードを実際に読み、実行パスを追った上での指摘であることを前提とする。「それっぽい説明」だけの指摘はFunctional Integrity Gateの禁止事項に該当する。

## 16. 品質コストと投資判断

- 狩野モデル×VDDの方針（§1）に基づき、品質投資の優先順位は「当たり前品質の回復（ゲートの正常化）」→「一元的品質（機能の正確性）」→「魅力的品質（UX・付加価値機能）」の順とする。
- 現状（2026-08-02）、pre-commitがblack/ruff/mypy/banditを強制していないというギャップ（§3）は「当たり前品質」レベルの課題であり、新規の魅力的品質投資（新機能追加）より優先度が高いと位置づける。
- ROIダッシュボード（`usage_roi`機能）は利用実績からの削減工数推定であり、品質保証活動そのものの投資対効果を測る指標ではない点に注意する（混同しないこと、§10参照）。

## 17. サプライチェーンとサードパーティ資産の品質

- サードパーティ資産（axe-core, driver.js, mermaid.min.js）はCDN取得せず同梱する方針（オフライン完結）。ライセンスは`ASSET.md`に記録し、`WS2D-LI-001`（OSSライセンス一覧）で一元管理する。
- 依存パッケージの脆弱性は`make security`（pip-audit）・`make audit`で定期監査する。CI上での自動実行有無は本書執筆時点で個別ジョブの中身を確認しておらず未確認（§3同様のギャップ）。
- LLMプロバイダ（OpenAI / Ollama）は`src/llm/openai_client.py`が両対応しており、OpenAI APIキー未設定でもルールベースへのフォールバックで機能が完走する設計（`RulesProvider`）。品質保証上は「外部サービス不可用時にも主要機能が動作すること」を非機能要件として扱う。

## 18. 非機能要件の品質保証における扱い

- 非機能要件（NFR）は`WS2D-NF-001`（非機能要件定義書、`docs/sdlc/10_requirements/WS2D-NF-001_非機能要件定義書.md`）を正本とする。本書はそれを品質ゲートの観点から補完する位置づけである。
- AutoRunの`autorun_nonfunctional_judge`機能（`web/services/nonfunctional_judge.py`）は、既存の観測データ（性能・アクセシビリティ計測結果等）を基準線と比較し合否を判定する。
- 初回実行時は比較対象となる基準線が無いため`no_baseline_first_run`として明示し、未観測領域は`observation_coverage.json`で「我々は全体を見たか」を可視化する（`web/services/observation_coverage.py`）。
- 非機能要件の品質保証は「判定した」ことと「観測できていない」ことを明確に分離する設計であり、evidence-only原則が非機能領域にも一貫して適用されている例である。
- ログイン必須画面のように非機能判定自体が観測できない領域は`login_wall_unobserved`として明示し、判定不能を「合格」に読み替えない。

## 19. 品質保証活動のロール別責任分担

現状の単独開発体制（§6参照）における役割の分担を明示する。体制拡大時の分担設計の出発点として使う。

| ロール | 責任範囲 | 実施者 | 備考 |
|---|---|---|---|
| 実装 | コーディング規約準拠・単体テスト作成 | 開発者本人（AIエージェント併用） | `WS2D-CS-001`準拠 |
| コードレビュー | HIGH以上の指摘検出 | `code-reviewer`エージェント | 人間の最終確認と併用 |
| 品質ゲート実行 | `make lint`/`make test`/`make verify-ui`等の実行 | 開発者本人（コミット前） | pre-commitが一部を機械強制 |
| L0ハーネス実行 | `quality_harness.py`の実行と結果確認 | 開発者本人（手動） | pre-commit対象外 |
| 最終承認 | DoD充足の確認、マージ判断 | 開発者本人 | ブラウザ目視確認を含む |
| インシデント対応 | RCA実施・再発防止策の反映 | 開発者本人 | `WS2D-DL-001`へ記録 |

体制拡大時は、コードレビューと最終承認を別人格に分離することを推奨する。現状は同一人物が兼務しており、相互チェックの効果は限定的である点を正直に記録する。

## 20. 品質保証計画書と他文書の関係

| 文書 | 役割 | 本書との関係 |
|---|---|---|
| `docs/DEFINITION_OF_DONE.md` | 完了の定義（一次情報源） | §4はこの文書の統合ビュー |
| `docs/process/functional-integrity-gate.md` | 機能整合性ゲート（一次情報源） | §5はこの文書の統合ビュー |
| `quality/feature_contracts.yml` | 機能契約データ（一次情報源） | §2・§3・§10が参照するL0ゲートの入力 |
| `WS2D-CS-001`（コーディング規約） | 実装規約 | §3のゲートが要求する静的解析の詳細を定義 |
| `WS2D-RL-001`（リリース手順書） | リリースプロセス | §3のゲートをリリース前チェックリストとして再利用 |
| `WS2D-NF-001`（非機能要件定義書） | 非機能要件の一次情報源 | §18が参照 |

本書は「統合ビュー」であるため、詳細を追う場合は上表の一次情報源に立ち返ること。本書の記載と一次情報源が食い違う場合は一次情報源を優先する。

## 21. 品質保証活動の運用サイクル

- 依存更新の四半期レビュー（`docs/specs/spec-6-2_dependency_update_strategy.md`の更新判断基準表）に合わせ、品質保証活動も四半期単位で棚卸しすることを推奨する。
- 棚卸し対象: §2の「未測定」項目の解消状況、§10のメトリクス推移、quarantineテストの有無、`feature_contracts.yml`の`feature_id`数と実装済み機能数の整合。
- レトロ（`retro`スキル）の実施タイミングと合わせることで、プロセス改善（§12継続的改善）と品質保証の棚卸しを同時に行い、往復コストを下げる。
- 棚卸しの結果、本書の版数を更新する場合は改訂履歴に理由を明記する（本書自身がその実例である）。

## 22. 用語の補足（本書固有の言い回し）

| 用語 | 本書での意味 |
|---|---|
| green | 該当ゲート（テスト・E2E等）が全てPASSしている状態 |
| フルゲート | `make lint`＋`make security`＋`make test`＋`make verify-ui`＋`quality_harness.py`＋`make coverage`の全項目 |
| MANDATORY項目 | pre-commitが機械強制する項目（構文・pytest・UI変更時のハッシュ照合） |
| REQUIRED項目 | 人間が確認する項目（ブラウザ目視確認等）。省略禁止だが機械強制はされない |
| 未測定 | 測定の仕組み自体が存在しない、または実施していないことを示すラベル（§2で多用） |

## 改訂履歴

| 版 | 日付 | 内容 | 作成者 |
|---|---|---|---|
| 1.0 | 2026-07-16 | 新規作成 | 開発チーム |
| 2.0 | 2026-08-02 | 全面改訂。ISO/IEC 25010の8品質特性別評価（未測定項目の明記含む）、品質ゲートの強制範囲の実態確認（pre-commitの実強制範囲とのギャップを明記）、Functional Integrity Gate全文統合、RCAプロセスの明確化、V&V区別・自己検証（ミューテーションテスト）・AIエージェント運用ルール・品質投資判断・サプライチェーン品質・非機能要件の扱い・ロール別責任分担・関連文書との関係・運用サイクル・用語補足を追加し、250行以上に拡充 | 開発チーム |
