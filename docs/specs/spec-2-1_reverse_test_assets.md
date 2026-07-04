# SPEC-2-1 リバース: 記録セッション → テスト資産の逆生成

| 項目 | 値 |
|---|---|
| WBS | 2-1（docs/0703-01_plan.md） |
| 優先度 / 見積 | P1 / 1sp |
| 依存 | なし（キャプチャ Phase 1 = PR #32 実装済みの上に載せる） |
| 背景 | docs/11 §7-2 ②リバース |

## 1. 目的と背景

キャプチャ Phase 1 で、テスターの探索操作は `sessions/session_*.jsonl` に記録され（`--record-session`）、ヒートマップ集計（`--exploration-coverage`）まで動いている。しかし記録は「足跡」として消費されるだけで、テスト資産にならない。本タスクで記録セッションから **テストケース（操作手順＋観察された結果）** と **ビジネスフロー（実演由来 = confidence 1.0）** を逆生成し、Scribe/Tango 等の録画→手順書ツールが持たないギャップ（docs/11 §7-2）を埋める。

**現状の実装状態（実装前に必ず確認すること）:**

- 済: `src/capture/session_recorder.py::SessionRecorder` — JSONL イベント 3 種（`kind: visit / action / state`）。visit は `{url, path}`、action は `{action_type, selector, url, path}`、state は `{state_id, url, path}`。state_id は `crawler/action_explorer.py::state_signature` で計算済み（記録時点で接合キーを持っている）
- 済: `src/capture/coverage.py::load_session_events` — 全セッション読み込み（`record["session"]` にファイル名を付与）
- 済: `src/graph/transition_graph.py::BusinessFlow` と `business_flows_to_dict`（`flow_name / path_id / nodes / screen_types / priority`）— report.json の `meta.business_flows` のスキーマ
- 済: `web/services/qa/advanced_html.py::_pw_candidate` — テストケース候補のスキーマ（`id / title / trace_id / automation_status / steps / expected`）。`web/services/spec_ts_generator.py::generate_spec_ts` がこのスキーマを消費する（SPEC-2-4 のリプレイが転用）
- 未: セッションイベント → テストケース / フローへの変換の一切

## 2. 受け入れ条件（全て自動テストで検証すること）

- **AC-1**: 記録セッションからテストケースが逆生成される（Given: visit → action → state のイベント列 / When: 逆生成 / Then: 操作手順が action の selector を含み、直後の visit/state が「観察された結果」として手順に紐づく）
- **AC-2**: 実演由来のビジネスフローが `business_flows_to_dict` と同一のキー構成＋追加キー `source: "recorded"`・`confidence: 1.0` で生成され、priority は `PRIORITY_HIGH`（"高"）固定
- **AC-3**: 逆生成テストケースが `playwright_candidates.json` 互換スキーマ（`{"domain": ..., "candidates": [...]}`・各要素は `_pw_candidate` と同一キー）で `recorded_candidates.json` に出力され、`generate_spec_ts` がエラーなく .spec.ts を生成できる
- **AC-4**: 画面照合は `normalize_footprint_path`、状態照合は記録済み `state_id`（= `state_signature` 由来）のみを使う。独自ハッシュ・独自正規化を実装しない（CONVENTIONS §1-3）
- **AC-5**: インベントリに無いパスの操作（地図にない足跡）もケース化されるが、`page_id` は空文字・手順に「クロール済みインベントリ未登録（未確認）」の注記が付く（evidence-only: 無いことにしない・推定しない）
- **AC-6**: 既存出力が不変: report.json（report_hash 含む）・exploration_coverage.json・sessions/*.jsonl に一切書き足さない。新規ファイル `recorded_assets.json` / `recorded_candidates.json` のみ追加
- **AC-7**: 実ブラウザ E2E で「記録 → 逆生成 → モーダル操作がケースの観察結果に載る」ことを検証する

## 3. スコープ外

- LLM による手順の自然文リライト（Phase 2。本タスクはルール変換のみ = confidence 1.0 を守る）
- 入力値（input イベントの value）の記録・再現（現行レコーダーは selector のみ記録。value 記録はプライバシー設計を伴うため別タスク）
- リプレイ実行そのもの（SPEC-2-4）・気づきマーク（SPEC-2-3）・UI 表示（SPEC-2-2）
- 複数セッションの 1 ケースへのマージ（セッション = ケースの単位とする）

## 4. 基本設計

### 4-1. 変更ファイル一覧

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 新規 | `src/capture/reverse_generator.py` | イベント列 → RecordedTestCase / 記録フロー変換・保存 |
| 変更 | `src/main.py` | `--reverse-assets` モード追加（`_exploration_coverage` と同型） |
| 新規 | `tests/test_reverse_generator.py` | 単体テスト（§6-1） |
| 新規 | `tests/e2e/test_reverse_assets_e2e.py` | 実ブラウザ E2E（§6-2） |
| 変更 | `quality/feature_contracts.yml` | 新契約 `reverse_assets` 追加 |

### 4-2. データモデル

```python
# src/capture/reverse_generator.py に追加（CONVENTIONS §1-1: frozen + tuple）
@dataclass(frozen=True)
class RecordedStep:
    order: int
    description: str      # 例: "「#submit-btn」をクリック"
    selector: str         # action イベントの selector（evidence 相当・実測）
    url: str
    observed: str = ""    # 直後に観測された結果（"→ /complete へ遷移" / "画面状態 3f2a... が出現"）

@dataclass(frozen=True)
class RecordedTestCase:
    case_id: str                     # "RC001" 連番
    session: str                     # "session_001.jsonl"
    title: str                       # 例: "記録フロー: /checkout → /complete"
    steps: tuple[RecordedStep, ...]
    page_ids: tuple[str, ...]        # 照合できた画面のみ。未照合は含めない（AC-5 は注記で表現）
    confidence: float = 1.0          # 実測由来固定
```

記録フローは dataclass を新設せず、`business_flows_to_dict` 互換 dict（＋`source`/`confidence`/`session`）で持つ（report.json スキーマと二重管理しないため）。

### 4-3. 処理フロー

```text
generate_recorded_assets(report, events)
  ├─ events を record["session"] でセッション単位にグループ化（行順 = 時系列）
  ├─ 各セッション: visit で手順を区切りつつ action → RecordedStep、直後の visit/state → observed
  ├─ 画面照合: normalize_footprint_path(url) と report["screens"] の URL パス突合 → page_ids
  ├─ フロー化: visit した画面列 → classify_pages_for_flows 相当の分類で業務画面通過を判定
  │            → business_flows_to_dict 互換 dict（source="recorded", confidence=1.0, priority="高"）
  └─ 候補化: RecordedTestCase → _pw_candidate 互換 dict（id="RC-0001", automation_status="auto"）
save_recorded_assets(assets, output_dir)
  ├─ recorded_assets.json    … {"test_cases": [...], "flows": [...]}
  └─ recorded_candidates.json … {"domain": ..., "candidates": [...]}（generate_spec_ts が直接消費）
```

## 5. 詳細設計

### 5-1. 関数シグネチャ

```python
# src/capture/reverse_generator.py（新規）
def generate_recorded_assets(
    report: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, Any]:
    """セッションイベントからテストケースと記録フローを逆生成する。
    report は report.json の dict（screens の url / page_id / fingerprint を照合に使う）。"""

def save_recorded_assets(assets: dict[str, Any], output_dir: Path) -> None:
    """recorded_assets.json と recorded_candidates.json を出力する。"""

# src/main.py（変更）: --reverse-assets（--url 必須）。report.json とセッションを読み、
# generate_recorded_assets → save_recorded_assets。_exploration_coverage と同じ
# ガード（report.json 無し / セッション無しは error ログで中断）を踏襲する。
```

- フロー分類は `graph/transition_graph.py::classify_pages_for_flows` の分類結果を再利用する（visit URL 列 → `BUSINESS_SCREEN_LABELS` 通過判定 → `flow_name` 命名は `prioritize_business_flows` と同じ「→」連結）。業務画面を通過しないセッションはフロー化しない（ケース化のみ）
- 候補 dict の `steps` 先頭は `page.goto('<最初の visit URL>')`（`spec_ts_generator._extract_url` が拾える形式）、`expected` は最後の observed、`trace_id` は `RC-<session連番>`

### 5-2. エラー処理表

| 事象 | 振る舞い | ユーザー可視 |
|---|---|---|
| セッション JSONL に不正行 | `load_session_events` が既にスキップ（変更しない） | — |
| action のみで visit が 1 件も無い | ケース化スキップ・警告ログ | ログ「visit イベントの無いセッションをスキップ」 |
| report.json に screens が無い | 全ケース page_ids=() で生成・注記付与（AC-5） | recorded_assets.json の注記 |
| 出力先に書き込み不可 | OSError を伝播（CLI が非 0 終了） | CLI エラーメッセージ |

### 5-3. 既存コードとの接続点

- `src/capture/coverage.py::load_session_events` — イベント読み込みを共用（再実装禁止）
- `src/capture/session_recorder.py::normalize_footprint_path` — 画面照合キー（CONVENTIONS §1-3）
- `src/graph/transition_graph.py` — `BUSINESS_SCREEN_LABELS`・`PRIORITY_HIGH`・`business_flows_to_dict` のスキーマ
- `web/services/spec_ts_generator.py::generate_spec_ts` — 消費側（本タスクでは変更しない。互換性テストのみ）
- `src/main.py::_exploration_coverage` — CLI モード追加の型紙

## 6. テスト仕様

### 6-1. 単体テスト（tests/test_reverse_generator.py）

| テスト名 | 入力 | 期待値 | AC |
|---|---|---|---|
| test_action_becomes_step_with_observed_state | visit → action → state | step.selector = action の selector・observed に state_id | AC-1 |
| test_recorded_flow_has_confidence_one | ログイン画面相当を visit する列 | flow dict に source="recorded"・confidence=1.0・priority="高" | AC-2 |
| test_candidates_schema_matches_pw_candidate | 1 セッション | 各候補が id/title/trace_id/automation_status/steps/expected を持つ | AC-3 |
| test_state_join_uses_recorded_state_id | state イベント | 逆生成側でハッシュ再計算をしない（記録値の素通し） | AC-4 |
| test_unmatched_path_annotated_not_dropped | インベントリ外パスの操作 | ケース化される・page_ids=()・注記「未確認」 | AC-5 |
| test_no_side_effect_on_existing_outputs | save 実行 | report.json / sessions/*.jsonl が変化しない（tmp_path 比較） | AC-6 |
| test_non_business_session_not_flowized | 一般画面のみの visit 列 | flows が空・test_cases は生成される | AC-2 |

イベントのフェイクは dict をそのまま組み立てる（`tests/test_capture.py` のカバレッジテストに倣う）。

### 6-2. 実ブラウザ E2E（tests/e2e/test_reverse_assets_e2e.py・専用スレッドパターン必須）

`tests/e2e/test_capture_realbrowser_e2e.py` の `_run_in_thread` パターンとデモサイト起動 fixture を再利用する。標的は `dashboard.html`（モーダル — CONVENTIONS 罠#5 により login.html は使わない）。ポートは **8899** を環境変数 `WEBSPEC2DOC_E2E_REVERSE_PORT` 付きで定義（CONVENTIONS 罠#7）。

| テスト名 | 検証 | AC |
|---|---|---|
| test_recorded_modal_click_reversed_to_case | 記録（モーダルを開く）→ 逆生成 → ケースの observed にモーダル状態の state_id | AC-1, AC-7 |
| test_recorded_candidates_feed_spec_ts | recorded_candidates.json → generate_spec_ts が .spec.ts を生成 | AC-3 |

### 6-3. 回帰確認

- 既存ユニット全件・既存実ブラウザ E2E が無変更で PASS
- `--record-session` → `--exploration-coverage` の既存フローが従来どおり動く（逆生成はオプトインの別モード）

## 7. 完了チェックリスト（DoD）

- [ ] AC-1〜7 のテストが全て存在し PASS
- [ ] CONVENTIONS §3 の全ゲート通過（black/ruff/mypy/bandit/pytest/quality_harness）
- [ ] feature_contracts.yml に `reverse_assets` 契約（core_files=`src/capture/reverse_generator.py`・failure_modes=`no_sessions`/`no_inventory`/`no_visit_events`・required_tests）
- [ ] 実行パス確認: デモサイトで record-session → reverse-assets を CLI 実行し、recorded_assets.json / recorded_candidates.json を目視確認（UI は本タスク対象外のため CLI 証跡で可）
- [ ] 未実行項目があれば「未確認」と報告

## 8. このタスク固有の罠

- セッション JSONL には**タイムスタンプが無い**（Phase 1 仕様）。順序は行順のみが正。ソート・時刻推定を持ち込まない
- `state` イベントは「シグネチャが変わった瞬間」しか記録されない（`poll_once` の差分検出）。「action の直後の state」は同一 URL 内で次に現れた state を割り当てる近似であり、ポーリング間隔 0.5 秒の粒度を超える精度を仕様に書かない（observed は「観測された結果」であって因果の断定ではない — 文言も「〜が観測された」とする）
- 記録開始直後の `about:blank` は `_record_visit` が既に除外済み（CONVENTIONS 罠#9）。逆生成側で再フィルタしない（二重実装の温床）
- `business_flows_to_dict` 互換 dict に `confidence` を足すのは**記録フロー側のみ**。クロール由来の `meta.business_flows`（report.json）にはキーを足さない（report_hash 互換・CONVENTIONS §2）
- `generate_spec_ts` は steps の `page.goto(...)` 文字列を `_extract_url` で正規表現抽出する。goto 行の書式を変えると URL が拾えず「body 可視のみのテスト」に劣化する — 互換性テスト（6-1/6-2）で担保する
