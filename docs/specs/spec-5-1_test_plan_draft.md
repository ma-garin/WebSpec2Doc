# SPEC-5-1 テスト計画ドラフト生成（インベントリ×ROI 係数→工数見積・スコープ表）

| 項目 | 値 |
|---|---|
| WBS | 5-1 |
| 優先度 / 見積 | P3 / 1sp |
| 依存 | なし |
| 背景 | docs/11 §7-3「計画」フェーズ（現状: 対象外 → インベントリ＋ROI 係数から計画ドラフト生成） |

## 1. 目的と背景

現状、プロジェクトライフサイクルの「計画」フェーズは本製品の対象外（docs/11 §7-3）。クロール済みインベントリ（report.json）には画面一覧・テスト条件・ビジネスフロー優先度が揃っており、ROI 係数（1 件あたりの手作業想定分数）も実装済みだが、両者を「これからのテスト計画」へ変換する機能がない。画面数×優先度→工数見積・スコープ表を Markdown / Excel で出力し、テストマネージャの計画初稿を自動生成する。

**現状の実装状態（実装前に必ず確認すること）:**

- 済: ROI 係数モデル `web/services/usage_tracker.py::SavingCoefficients`（minutes_per_screen=45.0 / minutes_per_condition=10.0 / minutes_per_diff=30.0、環境変数 `WEBSPEC2DOC_MIN_PER_SCREEN` 等で上書き可）— ただし**事後の削減実績集計**にのみ使用
- 済: 画面優先度のルール分類 `src/llm/screen_classifier.py::classify_screen_by_rules(title, headings, form_fields)` → `ScreenClassification.test_priority`（critical/high/medium/low）。オフライン完走（RulesProvider 前提）
- 済: ビジネスフロー優先度 `src/graph/transition_graph.py::prioritize_business_flows` → report.json の `meta.business_flows[]`（flow_name・nodes・priority="高"）
- 済: Excel 出力の前例 `src/main.py::_save_excel_output`（openpyxl・spec.xlsx）、CLI 後処理モードの前例 `src/main.py::_exploration_coverage`（report.json 必須チェック）
- 未: 計画生成ロジック・出力（test_plan.md / test_plan.xlsx）・CLI フラグ

## 2. 受け入れ条件（全て自動テストで検証すること）

- **AC-1**: report.json からスコープ表が生成される（Given: クロール済み report.json / When: `--test-plan` 実行 / Then: `test_plan.md` と `test_plan.xlsx` が出力され、canonical 画面ごとに 画面ID・タイトル・URL・画面種別・優先度・テスト条件数・見積分数 の行がある）
- **AC-2**: 見積には計算根拠（使用した係数値・重み・件数）と免責文言「係数に基づく推定値であり実測ではない」が明記される（usage_tracker の disclaimer と同趣旨。evidence-only 原則）
- **AC-3**: `meta.business_flows[].nodes` に URL が含まれる画面は優先度が high 未満なら high へ引き上げられ、根拠として flow_name が priority_source に付記される
- **AC-4**: 係数と優先度重みは環境変数で上書きできる（既存 `WEBSPEC2DOC_MIN_PER_SCREEN` / `WEBSPEC2DOC_MIN_PER_CONDITION` と、新設 `WEBSPEC2DOC_PLAN_WEIGHT_{CRITICAL,HIGH,MEDIUM,LOW}`。不正値は既定値へフォールバックし警告ログ）
- **AC-5**: report.json 不在時は `_exploration_coverage` と同様に logger.error で案内して終了する（例外で落ちない）
- **AC-6**: 既存出力が変化しない（report.json のスキーマ・report_hash に触れない。新規ファイル追加のみ）
- **AC-7**: src 側の係数既定値が `web/services/usage_tracker.py` の既定値と一致することを検証するパリティテストがある（層分離のため定義が 2 箇所になる — §8 参照）

## 3. スコープ外

- Web UI 統合（計画画面・ダウンロードボタン。WBS 1-5/3-5 の UI 統合と合わせて後続）
- 人員割当・日程（ガントチャート）・実測工数によるフィードバック補正
- テストケース明細の再掲（既存の 29119-4 遷移テスト・テスト条件出力と重複させない — 計画は件数と見積のみ）
- diff 係数（minutes_per_diff）の計画反映（回帰計画は将来。今回は新規テスト計画のみ）

## 4. 基本設計

### 4-1. 変更ファイル一覧

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 新規 | `src/generator/test_plan_generator.py` | 係数・計画モデル・md/xlsx 出力 |
| 変更 | `src/main.py` | `--test-plan` フラグと `_generate_test_plan()`（`_exploration_coverage` に倣う） |
| 新規 | `tests/test_test_plan_generator.py` | 単体・結合テスト（§6） |
| 変更 | `quality/feature_contracts.yml` | 新契約 `test_plan`（core_files・failure_modes・required_tests。ui_files/route_files は空配列） |

### 4-2. データモデル

```python
# src/generator/test_plan_generator.py
@dataclass(frozen=True)
class PlanCoefficients:
    """見積係数。既定値は usage_tracker と同値（パリティテストで担保）。"""

    minutes_per_screen: float = 45.0
    minutes_per_condition: float = 10.0
    weight_critical: float = 1.5
    weight_high: float = 1.2
    weight_medium: float = 1.0
    weight_low: float = 0.5

@dataclass(frozen=True)
class PlanRow:
    page_id: str
    title: str
    url: str
    screen_type: str
    test_priority: str          # critical/high/medium/low
    priority_source: str        # "画面分類" / "ビジネスフロー: ログイン→決済"
    condition_count: int
    estimated_minutes: float

@dataclass(frozen=True)
class TestPlan:
    rows: tuple[PlanRow, ...]
    total_minutes: float
    total_hours: float          # round(total_minutes / 60.0, 1)
    coefficients: PlanCoefficients
    disclaimer: str
```

### 4-3. 処理フロー

```text
_generate_test_plan(args)
  ├─ report.json 読み込み（JSON_REPORT_FILE_NAME・不在なら logger.error）
  ├─ canonical 画面抽出（s.get("is_canonical", True) — usage_tracker と同じ既定 True）
  ├─ 画面ごと: classify_screen_by_rules(title, tuple(headings), field_names)
  ├─ meta.business_flows の nodes と URL 照合 → 優先度引き上げ（AC-3）
  ├─ 見積 = weight(priority) × minutes_per_screen + condition_count × minutes_per_condition
  └─ save_test_plan(plan, output_dir) → test_plan.md / test_plan.xlsx
```

## 5. 詳細設計

### 5-1. 関数シグネチャ

```python
def load_plan_coefficients() -> PlanCoefficients:
    """環境変数を反映した係数を返す。既存 env 名（WEBSPEC2DOC_MIN_PER_SCREEN /
    WEBSPEC2DOC_MIN_PER_CONDITION）を尊重し、重みは WEBSPEC2DOC_PLAN_WEIGHT_* で上書き。"""

def compute_test_plan(report: dict, coefficients: PlanCoefficients) -> TestPlan:
    """report.json の dict から計画を組み立てる純関数（I/O なし・テスト容易）。"""

def save_test_plan(plan: TestPlan, output_dir: Path) -> None:
    """test_plan.md と test_plan.xlsx を出力する。xlsx 失敗時は md のみ出力し警告（§5-3）。"""
```

- テスト条件数は usage_tracker の集計式と同じ経路で数える: `screens[].forms[].fields[].test_conditions` の合計
- xlsx はシート 2 枚: 「スコープ表」（PlanRow 全列）・「見積サマリ」（優先度別小計・総計・係数・免責）。書式は `src/main.py::_save_excel_output` に倣う
- md は表 + サマリ + 免責。ソートは優先度（critical→low）→ 見積分数の降順

### 5-2. エラー処理表

| 事象 | 振る舞い | ユーザー可視 |
|---|---|---|
| report.json 不在 | logger.error で終了（`--exploration-coverage` と同文体） | 「先に `--format json` でクロールしてください」 |
| report.json 破損（JSONDecodeError） | logger.error で終了 | 「report.json を読み込めません」 |
| screens が空 | 0 行の計画＋注記を出力（失敗にしない） | md に「対象画面 0 件」 |
| xlsx 書き込み失敗（OSError） | md のみ出力し警告ログ | 「Excel 出力に失敗（md は出力済み）」 |
| 環境変数の不正値 | 既定値フォールバック＋警告（usage_tracker `_env_float` と同挙動） | 警告ログ |

### 5-3. 既存コードとの接続点

- `src/main.py`: `parser.add_argument("--test-plan", action="store_true", ...)`、分岐は `_exploration_coverage` の隣。`JSON_REPORT_FILE_NAME`・`_domain_name` を再利用
- `src/llm/screen_classifier.py::classify_screen_by_rules` — headings は **tuple** 引数（report.json の list を変換して渡す）
- `web/services/usage_tracker.py` — **import しない**（層分離。§8 罠 1）。既定値の一致はテストで担保（AC-7）
- business_flows は **`meta.business_flows`** 配下（トップレベルキーではない — docs/demo/sample_output/report.json で確認済み）。キー不在（古い report）はスキップして分類優先度のみで続行

## 6. テスト仕様

### 6-1. 単体テスト（tests/test_test_plan_generator.py）

| テスト名 | 入力 | 期待値 | AC |
|---|---|---|---|
| test_plan_rows_from_canonical_screens | screens 3 件（1 件 is_canonical=False） | rows 2 件・列が揃う | AC-1 |
| test_estimate_formula_and_disclaimer | 条件数 4・priority=high | 45×1.2 + 4×10 = 94.0 分・免責文字列を含む | AC-2 |
| test_business_flow_raises_priority | meta.business_flows の nodes に該当 URL（分類は medium） | test_priority=high・priority_source に flow_name | AC-3 |
| test_env_override_and_invalid_fallback | WEBSPEC2DOC_PLAN_WEIGHT_HIGH="2.0" / "abc" | 2.0 反映 / 既定値＋警告 | AC-4 |
| test_missing_business_flows_key | meta に business_flows なし | 例外なく分類優先度のみで生成 | AC-3 |
| test_empty_screens_plan | screens=[] | rows=()・total 0・md に注記 | 5-2 |
| test_coefficients_parity_with_usage_tracker | 両モジュールの既定値 | minutes_per_screen / minutes_per_condition が一致 | AC-7 |

### 6-2. 結合テスト（実ファイル I/O・tmp_path）

| テスト名 | 検証 | AC |
|---|---|---|
| test_save_outputs_md_and_xlsx | tmp_path に report.json → save → md 内容と load_workbook でシート 2 枚・行数検証 | AC-1 |
| test_missing_report_logs_error | report.json なしで CLI 分岐関数 → logger.error・例外なし | AC-5 |
| test_xlsx_failure_still_writes_md | 書込不能ディレクトリを注入 | md 出力＋警告 | 5-2 |

### 6-3. 回帰確認

- 既存ユニット全件（1,222 件）が無変更で PASS。report.json を読み取り専用で扱い、report_hash に影響しないこと（AC-6）

## 7. 完了チェックリスト（DoD）

- [ ] AC-1〜7 のテストが全て存在し PASS
- [ ] CONVENTIONS §3 の全ゲート通過（black/ruff/mypy/bandit/pytest/quality_harness）
- [ ] feature_contracts.yml に `test_plan` 契約追加
- [ ] 実行パス確認: `make demo` の DemoMart をクロール後、CLI `--test-plan` で test_plan.md / test_plan.xlsx が生成され、決済画面（checkout）が優先度 high 以上・ビジネスフロー根拠付きで載ることを目視確認

## 8. このタスク固有の罠

- **層分離**: 係数の「正」は web/services/usage_tracker.py にあるが、src/generator から web を import してはならない（CONVENTIONS §1-1: 依存方向は上→下のみ）。既定値の二重定義はパリティテスト（AC-7）で乖離を検知する。テストは両層を import してよい
- `classify_screen_by_rules` の headings 引数は tuple 型。report.json の list をそのまま渡すと mypy で落ちる
- business_flows の nodes は **URL 文字列**（page_id ではない）。画面との照合は URL 完全一致で行い、末尾スラッシュ差異が出たら `ingest/matcher.py::_normalize_path` と同様の正規化を検討する（仕様外判断として報告）
- `screen_count` の数え方は usage_tracker（is_canonical 既定 True）と揃える。全 screens を数えると変種画面で見積が水増しされる
- 優先度重み（1.5/1.2/1.0/0.5）は本仕様で新設する**推定係数**。根拠のない断定をせず、出力に必ず係数値と免責を併記する（evidence-only）
