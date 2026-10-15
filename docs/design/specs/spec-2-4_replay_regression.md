# SPEC-2-4 リプレイ: 記録フローの回帰化・ドリフト影響提案・セレクタ修復候補

| 項目 | 値 |
|---|---|
| WBS | 2-4 |
| 優先度 / 見積 | P2 / 2sp |
| 依存 | 2-1（recorded_candidates.json / recorded_assets.json が入力） |
| 背景 | docs/11 §7-2 ④リプレイ・§7-3 保守フェーズ「ドリフト×記録フローの影響提案」 |

## 1. 目的と背景

SPEC-2-1 で記録セッションはテスト資産（`recorded_candidates.json` = playwright_candidates 互換）になったが、まだ「再実行」できない。本タスクで (a) 記録フローを AutoRun 基盤（`generate_spec_ts` → `run_playwright`）で再実行可能にし = 実利用由来のリグレッションスイート、(b) ドリフト検出と連結して「差分が出た画面を通過する記録フロー」を先に再実行すべきフローとして提案し、(c) リプレイ失敗時に evidence 由来のセレクタ修復**候補**を提示する（自動書き換えはしない — evidence-only）。

**現状の実装状態（実装前に必ず確認すること）:**

- 済: `web/services/spec_ts_generator.py::generate_spec_ts` — candidates JSON → .spec.ts。`<basename>.meta.json`（test_id/page_id/fingerprint/url）を併産。`_sort_locators_by_reliability` / `_build_resilient_locator` がロケータ優先順位付けを実装済み
- 済: `web/services/playwright_executor.py::run_playwright(spec_path, output_dir, per_test_timeout_sec, timeout_sec, add_log)` — ローカル @playwright/test CLI 実行・結果 dict（ok/passed/failed/tests[].error 等）・npx 不在時は `unavailable` 結果でフォールバック
- 済: `web/services/auto_run_job.py::AutoRunJob` — ジョブ状態・ログ（add_log）・cancel の器
- 済: `src/diff/impact_analyzer.py::analyze_impact` / `format_impact_report` — 差分→影響テスト特定（fingerprint 優先・URL フォールバック）。呼び出し起点は `src/main.py::_compute_impact_report`
- 済（2-1 完了後）: `output/{domain}/recorded_candidates.json`（`{"domain", "candidates"}`）と `recorded_assets.json` の flows（`business_flows_to_dict` 互換＋`source: "recorded"`）。未: リプレイ実行経路・記録フローへの影響分析・セレクタ修復候補の一切

## 2. 受け入れ条件（全て自動テストで検証すること）

- **AC-1**: リプレイ実行で `recorded_candidates.json` から .spec.ts が生成され `run_playwright` で実行、`qa_process/replay_report.json` に結果（passed/failed/tests）が保存される（Given: 2-1 の成果物あり / When: リプレイ実行 / Then: レポートと Playwright HTML が出力される）
- **AC-2**: Node.js/npx が無い環境ではリプレイが `unavailable: true` の結果で完走し、理由がユーザーに表示される（playwright_executor の既存フォールバックを素通しする — 例外で死なない）
- **AC-3**: ドリフト検出時、差分ページを通過する記録フローが「先に再実行すべきフロー」として impact レポートに載る（照合は fingerprint 優先・無ければ正規化 URL パス。独自ハッシュ禁止 — CONVENTIONS §1-3）
- **AC-4**: 記録フローが無い場合、impact レポートは従来と同一スキーマ（`recorded_flow_rerun` キーが**存在しない** — オプトイン。report_hash・スナップショット互換を壊さない）
- **AC-5**: リプレイ失敗テストに対し、report.json の該当画面（meta.json の page_id/fingerprint で特定）の evidence セレクタ群から修復候補が `_sort_locators_by_reliability` の優先順で提示される。候補は**提案のみ**で spec や記録 JSONL を書き換えない
- **AC-6**: 該当画面が report.json に見つからない失敗テストは修復候補 `[]`＋「候補なし（未確認）」注記になる（実在しないセレクタを発明しない — 幻覚フィルタと同じ原則）
- **AC-7**: 実ブラウザ E2E（またはそれが不可能な CI では unavailable 経路のフォールバックテスト）で AC-1 の実行パスを検証する

## 3. スコープ外

- 修復候補の自動適用・自己修復リトライ（人間の承認なしに spec を書き換えない）
- 夜間スケジュール実行（`web/services/scheduler.py` への組み込みは WBS 4-4 CI 監視と合わせて別タスク）
- 入力値の再現（2-1 §3 と同じ制約 — レコーダーが value を記録しないため、リプレイの検証は遷移・表示の到達性が主）
- Web UI の専用画面新設（既存「テスト実行」タブへの最小追加のみ。全面的な UI は SBTM 運営画面と合わせて後続）

## 4. 基本設計

### 4-1. 変更ファイル一覧

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 新規 | `web/services/replay_runner.py` | リプレイ実行のオーケストレーション・修復候補生成 |
| 新規 | `web/routes/replay.py` | `POST /api/replay/<domain>`・`GET /api/replay/<domain>/status`（Blueprint 登録は既存 bp 登録列に追加） |
| 変更 | `src/diff/impact_analyzer.py` | `analyze_recorded_flow_impact` 追加・`format_impact_report` にオプトイン引数追加 |
| 変更 | `src/main.py` | `_compute_impact_report` で recorded_assets.json の flows を接続 |
| 変更 | `templates/partials/view-generate.html`・`static/js/view-test-runs.js` | 「テスト実行」タブにリプレイ開始ボタンと結果表示を追加 |
| 新規 | `tests/test_replay_runner.py`・`tests/test_impact_recorded_flows.py` | 単体テスト（§6-1） |
| 新規 | `tests/e2e/test_replay_e2e.py` | E2E（§6-2） |
| 変更 | `quality/feature_contracts.yml` | 新契約 `replay_regression` 追加 |

### 4-2. データモデル

```python
# qa_process/replay_report.json（run_playwright の結果 dict に追記して保存）
{
  "ok": bool, "passed": int, "failed": int, "tests": [...],   # playwright_executor そのまま
  "spec_path": "qa_process/replay.spec.ts",
  "repair_candidates": [                                       # 失敗テストがある時のみ
    {"test_id": "RC-0001", "page_id": "P003",
     "failed_error": "<tests[].error の先頭 400 文字>",
     "candidates": ["[data-testid=submit]", "[name='email']", "#send"],  # 優先順
     "note": ""}   # 画面未特定時: "候補なし（report.json に該当画面が見つからず未確認）"
  ]
}
# format_impact_report の戻り dict（オプトイン追加キー）
"recorded_flow_rerun": [
  {"flow_name": "ログイン→決済", "path_id": "RF001", "session": "session_001.jsonl",
   "reason": "差分画面 https://…/checkout を通過", "priority": "高"}
]
```

### 4-3. 処理フロー

```text
POST /api/replay/<domain>
  ├─ _valid_domain 検証（web/validation.py の既存関数）→ AutoRunJob 生成・別スレッド実行
  └─ replay_runner.run_replay(domain, output_dir, add_log=job.add_log)
       ├─ recorded_candidates.json 読込（無ければ error 結果で終了）
       ├─ generate_spec_ts(domain, candidates_path, qa_process/replay.spec.ts,
       │                    filter_mode="all", report_path=report.json)   # meta.json 併産
       ├─ run_playwright(spec_path, qa_process/, per_test_timeout_sec=30, add_log=add_log)
       ├─ 失敗テスト × replay.meta.json × report.json → propose_selector_repairs
       └─ replay_report.json 保存 → job.outputs / test_results へ反映

ドリフト連結（src/main.py::_compute_impact_report 変更）
  ├─ recorded_assets.json が存在すれば flows を読込
  ├─ analyze_recorded_flow_impact(diff, flows, url_fingerprints)
  └─ format_impact_report(impacted, recorded_flow_impacts=...)  # None なら従来出力
```

## 5. 詳細設計

### 5-1. 関数シグネチャ

```python
# web/services/replay_runner.py（新規）
def run_replay(
    domain: str,
    output_dir: Path,
    per_test_timeout_sec: int = 30,
    add_log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """recorded_candidates.json をリプレイ実行し replay_report.json を出力して返す。"""

def propose_selector_repairs(
    failed_tests: list[dict[str, Any]],
    test_metadata: list[dict[str, Any]],   # replay.meta.json の tests
    report: dict[str, Any],                # report.json
) -> list[dict[str, Any]]:
    """失敗テストの画面を page_id/fingerprint で特定し、該当画面のフォームフィールド
    evidence（selector）・buttons から修復候補を _sort_locators_by_reliability 順で返す。"""

# src/diff/impact_analyzer.py（追加・変更）
def analyze_recorded_flow_impact(
    diff_result: DiffResult,
    recorded_flows: list[dict],            # recorded_assets.json の flows
    url_fingerprints: dict[str, str] | None = None,
) -> list[dict]:
    """差分ページ（added/removed/field_changes/attribute_diffs の page_url）を通過する
    記録フローを特定する。fingerprint 一致優先・無ければ normalize_footprint_path で照合。"""

def format_impact_report(
    impacted_tests: list[ImpactedTest],
    recorded_flow_impacts: list[dict] | None = None,   # 既定 None = 従来と同一出力
) -> dict: ...
```

- src → web の import は禁止（CONVENTIONS §1-1）。`_sort_locators_by_reliability` は web 層にあるため `propose_selector_repairs` も web 層（replay_runner）に置き、impact_analyzer（src/diff）はフロー特定のみを担う。正規化パス照合は `capture.session_recorder.normalize_footprint_path` を共用する（独自正規化禁止）

### 5-2. エラー処理表

| 事象 | 振る舞い | ユーザー可視 |
|---|---|---|
| recorded_candidates.json 無し | `{"ok": false, "error": "記録資産がありません（先に --reverse-assets を実行）"}` | UI にエラーメッセージとガイド表示 |
| npx / @playwright/test 無し | playwright_executor の `unavailable` 結果を素通し | 「Node.js をインストールしてください」（既存文言） |
| 実行タイムアウト | `_SUBPROCESS_MAX_SEC` 超過 → executor の `_error_result` を素通し | タイムアウト文言＋対処（既存） |
| リプレイのキャンセル | AutoRunJob.cancel（proc terminate）を流用 | status=cancelled |
| 失敗テストの画面が report.json に無い | 候補 []＋注記（AC-6） | replay_report.json / UI に「候補なし（未確認）」 |
| recorded_assets.json 破損 | 警告ログ・impact は従来出力（recorded_flow_rerun 無し） | ログ「記録フローの読込に失敗（影響提案を省略）」 |

### 5-3. 既存コードとの接続点

- `web/services/spec_ts_generator.py::generate_spec_ts` / `metadata_file_path`・`web/services/playwright_executor.py::run_playwright` — いずれも変更しない（消費のみ。結果 dict の `tests[].error` を修復候補入力に使う）
- `web/services/auto_run_job.py::AutoRunJob` — ジョブ器を流用（status 列挙は既存値で足りる: running_tests/complete/failed/cancelled）
- `web/routes/report.py::api_result` — `files` に `replay_report` を追加（`path_of("qa_process/replay_report.json")` 方式）
- `src/main.py::_compute_impact_report`（596 行付近）— recorded_assets.json 接続の唯一の src 側変更点
- `src/generator/html_reporter.py::_impact_section` — `recorded_flow_rerun` があれば「先に再実行すべき記録フロー」表を追記（キー不在なら従来表示）

## 6. テスト仕様

### 6-1. 単体テスト（tests/test_replay_runner.py・tests/test_impact_recorded_flows.py）

| テスト名 | 入力 | 期待値 | AC |
|---|---|---|---|
| test_replay_missing_candidates_error | 空ディレクトリ | ok=false・ガイド文言・例外なし | AC-1 |
| test_replay_unavailable_passthrough | run_playwright をフェイクで unavailable に | replay_report.json に unavailable=true | AC-2 |
| test_flow_impact_by_fingerprint | 差分ページ fp = flow 通過画面 fp | recorded_flow_rerun に該当フロー・reason に差分画面 | AC-3 |
| test_flow_impact_url_fallback | fp 無し・パス一致のみ | 正規化パスで照合される | AC-3 |
| test_impact_report_schema_unchanged_without_flows | recorded_flow_impacts=None | 従来キーのみ（スナップショット比較） | AC-4 |
| test_repair_candidates_sorted_by_reliability | 失敗テスト＋evidence セレクタ 3 種 | data-testid → name → id の優先順 | AC-5 |
| test_repair_no_screen_found | meta に無い page_id | candidates=[]・note に「未確認」 | AC-6 |
| test_repair_does_not_mutate_inputs | 修復候補生成 | spec.ts・sessions/*.jsonl・candidates が不変 | AC-5 |

フェイク: `run_playwright` はモジュール関数のため monkeypatch で注入（`_FakeClock` 等の既存フェイク流儀に倣い、戻り dict を固定注入）。

### 6-2. E2E（tests/e2e/test_replay_e2e.py）

デモサイト標的は `checkout.html`（CONVENTIONS 罠#5）。ポートは **8902** を環境変数 `WEBSPEC2DOC_E2E_REPLAY_PORT` 付きで定義（罠#7。8898/8899/8901 は SPEC-3-1/2-1/2-3 予約済み）。記録→逆生成部分は実ブラウザのため**専用スレッドパターン必須**（`_run_in_thread`）。リプレイ実行は subprocess（@playwright/test）のため asyncio 制約を受けない。

| テスト名 | 検証 | AC |
|---|---|---|
| test_record_reverse_replay_roundtrip | 記録 → reverse-assets → run_replay → replay_report.json の passed ≥ 1 | AC-1, AC-7 |
| test_replay_without_node_env | npx を PATH から外した環境変数で実行 → unavailable 経路 | AC-2, AC-7 |

CI の unit ジョブは Node/ブラウザ未導入（CONVENTIONS 罠#3）のため、roundtrip は tests/e2e/ 配下のみに置き、unit 側には unavailable 経路と環境不変の性質テストだけを置く。

### 6-3. 回帰確認

- 既存 AutoRun E2E（tests/e2e/test_autorun_modal_e2e.py）・`_compute_impact_report` 経由の既存 impact テストが無変更で PASS
- recorded_assets.json が無い環境での再クロール＋差分検出が従来と同一の impact_report を出す（AC-4）

## 7. 完了チェックリスト（DoD）

- [ ] AC-1〜7 のテストが全て存在し PASS
- [ ] CONVENTIONS §3 の全ゲート通過（black/ruff/mypy/bandit/pytest/quality_harness）
- [ ] **UI 変更（view-generate.html / view-test-runs.js）があるため `make verify-ui` PASS 必須**
- [ ] feature_contracts.yml に `replay_regression` 契約（core_files=`web/services/replay_runner.py`・`src/diff/impact_analyzer.py`、route_files=`web/routes/replay.py`、failure_modes=`no_recorded_assets`/`node_unavailable`/`timeout`/`cancel`/`screen_not_found`、required_tests に cancel_path 含む）
- [ ] 実行パス確認: UI のリプレイボタン → API → replay_runner → .spec.ts 実行 → replay_report.json → UI 結果表示、およびドリフト時の「先に再実行すべきフロー」表示まで実際に動かして目視確認。動かせない項目（例: Node 無し環境の実機）は「未確認」と明記
- [ ] 未実行項目があれば「未確認」と報告

## 8. このタスク固有の罠

- **リプレイの「PASS」は到達性の確認であって業務結果の一致検証ではない**。レコーダーが入力値と期待値を記録しない以上、生成 spec のアサーションは URL 到達＋要素可視が上限。「実利用由来リグレッション」の売り文句をレポート文言で誇張しない（「記録フローの再走行に成功」と書く）
- `generate_spec_ts` は candidates の steps コメント化＋`page.goto` 抽出という**緩い変換**。リプレイで click を実際に発行させたい場合でも spec_ts_generator の生成規則を分岐させず、candidates 側（2-1 の出力）の steps 書式で制御する — 生成器の二又化は AutoRun 本体の回帰リスク
- `run_playwright` は `output/.playwright_env` の共有 node_modules を使う。E2E で並走する AutoRun テストと npm install が競合し得るため、リプレイ E2E は事前セットアップ済み前提（`_pw_test_available` を確認してから実行、無ければ skip 理由を明示）
- impact_analyzer への引数追加は**キーワード引数・既定 None**。`src/main.py` 以外にテストからの直接呼び出しが多数あるため、位置引数で足すと既存テストが静かに壊れる
- `qa_process/` 配下は AutoRun の成果物ディレクトリ。`autorun.spec.ts` / `playwright_report.json` を**上書きしない**ファイル名（`replay.spec.ts` / `replay_report.json`）を厳守する（api_result がファイル名で拾っているため衝突すると「テスト実行」タブの表示が入れ替わる）
