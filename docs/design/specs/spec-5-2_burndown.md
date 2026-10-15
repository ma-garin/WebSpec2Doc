# SPEC-5-2 進捗バーンダウン（探索カバレッジの時系列推移表示）

| 項目 | 値 |
|---|---|
| WBS | 5-2 |
| 優先度 / 見積 | P3 / 0.5sp |
| 依存 | 2-2（ヒートマップ UI 統合）— 未着手のため本仕様は独立 HTML で成立させ、report.html タブ統合は 2-2 側で行う |
| 背景 | docs/11 §7-3「報告」フェーズ（消化バーンダウン: 分母に対する進捗） |

## 1. 目的と背景

探索カバレッジ（`src/capture/coverage.py`）は「現時点の消化率」しか出せず、日々の進捗（残りの未探索がどう減っているか）が見えない。分母 = クロール済みインベントリの画面数＋状態数、分子 = 探索セッションの足跡、という既存の集計を**セッション日時ベースの時系列**に展開し、バーンダウン（未探索残数の推移）として出力する。

**現状の実装状態（実装前に必ず確認すること）:**

- 済: セッション記録 `src/capture/session_recorder.py::SessionRecorder` — JSONL（`sessions/session_NNN.jsonl`・連番は `_next_session_path`）へ visit/action/state を追記。**ただしイベントに時刻フィールドがない**（kind/url/path/selector/state_id のみ）— 日時ベースの推移が現状出せない根本原因
- 済: 集計 `src/capture/coverage.py::compute_exploration_coverage(report, events)` — summary に total_screens / explored_screens / total_states / touched_states / coverage_ratio。`load_session_events` は各レコードに `record["session"] = ファイル名` を付与済み（セッション別分割に利用可能）
- 済: 出力 `save_exploration_coverage` → exploration_coverage.json + exploration_heatmap.html（`generator/heatmap_reporter.py`・自己完結 HTML・検証済みパレット）
- 済: CLI `src/main.py::_exploration_coverage`（report.json とセッションの存在チェック）
- 未: イベントへの時刻付与、セッション単位の累積系列、バーンダウン出力

## 2. 受け入れ条件（全て自動テストで検証すること）

- **AC-1**: SessionRecorder が全イベントに `ts`（UTC ISO8601）を付与する（Given: FakeClock を注入した SessionRecorder / When: poll_once・_record_visit / Then: 記録 dict に注入時刻の `ts` が入る）
- **AC-2**: `--exploration-coverage` 実行で既存出力に加え `exploration_burndown.json` と `exploration_burndown.html` が出力される（Given: report.json とセッション 2 件以上 / When: CLI 実行 / Then: セッション日時昇順の累積系列 — 各点に at・explored_screens・touched_states・remaining_screens・remaining_states・coverage_ratio）
- **AC-3**: `ts` の無い旧形式セッションはファイル更新時刻（mtime）で代替し、その点に `estimated: true` と注記「日時はファイル更新時刻からの推定」が付く（evidence-only: 推定を推定と明示）
- **AC-4**: 累積系列の explored_screens / touched_states は単調非減少、remaining は単調非増加である
- **AC-5**: セッション 0 件は既存のエラー動作（logger.error）のまま、1 件なら 1 点の系列として HTML が壊れず描画される
- **AC-6**: 既存出力のスキーマが不変（exploration_coverage.json / exploration_heatmap.html / report.json は byte 同等の集計結果。`ts` 追加はセッション JSONL への追加キーであり、coverage 集計は `ts` を参照しない）

## 3. スコープ外

- report.html / Web UI へのタブ統合（WBS 2-2）、ステークホルダー向け日次サマリ・通知（docs/11 §7-3 報告行の残項目）
- 複数テスターのチーム集約・個人別チャーター配分（docs/11 §7-4）
- 記録中のリアルタイム更新（バーンダウンは集計コマンド実行時に再計算）
- 旧セッションファイルへの ts 遡及付与（mtime 推定で表示のみ）

## 4. 基本設計

### 4-1. 変更ファイル一覧

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 変更 | `src/capture/session_recorder.py` | clock 注入フィールド追加・`_append` で `ts` 付与 |
| 新規 | `src/capture/burndown.py` | セッション別分割・時刻決定・累積系列計算 |
| 新規 | `src/generator/burndown_reporter.py` | 自己完結 HTML（SVG 折れ線）生成。`BURNDOWN_FILE_NAME = "exploration_burndown.html"` |
| 変更 | `src/main.py` | `_exploration_coverage` の末尾でバーンダウンも出力 |
| 変更 | `tests/test_capture.py` ほか | 単体テスト追加（§6） |
| 変更 | `quality/feature_contracts.yml` | `exploration_capture` 契約の core_files/outputs に burndown を追記 |

### 4-2. データモデル

```python
# src/capture/burndown.py
@dataclass(frozen=True)
class BurndownPoint:
    session: str              # "session_001.jsonl"
    at: str                   # ISO8601（セッション先頭イベントの ts、無ければ mtime）
    estimated: bool           # True = mtime からの推定日時
    explored_screens: int
    touched_states: int
    remaining_screens: int    # total_screens - explored_screens
    remaining_states: int     # total_states - touched_states
    coverage_ratio: float
```

### 4-3. 処理フロー

```text
compute_exploration_burndown(report, events, sessions_dir)
  ├─ events を record["session"] でセッション別に分割（load_session_events が付与済み）
  ├─ セッション代表時刻 = 先頭イベントの ts / 無ければ session ファイルの mtime（estimated=True）
  ├─ 代表時刻の昇順にセッションを並べる
  ├─ 先頭〜k 番目の累積イベントで compute_exploration_coverage を再利用 → k 点目
  └─ BurndownPoint 列 → exploration_burndown.json / exploration_burndown.html
```

## 5. 詳細設計

### 5-1. 関数シグネチャ

```python
# session_recorder.py（変更）— frozen でない dataclass のため field 追加可
@dataclass
class SessionRecorder:
    ...
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    # _append(record) の先頭で record.setdefault("ts", self.clock().isoformat(timespec="seconds"))

# burndown.py
def compute_exploration_burndown(
    report: dict[str, Any], events: list[dict[str, Any]], sessions_dir: Path
) -> dict[str, Any]:
    """セッション日時昇順の累積カバレッジ系列を返す（点列＋分母サマリ）。"""

def _session_timestamp(
    session_events: list[dict[str, Any]], session_path: Path
) -> tuple[str, bool]:
    """(ISO8601, estimated) を返す。ts があれば先頭 ts、無ければ mtime。"""

# generator/burndown_reporter.py
def generate_burndown_html(burndown: dict[str, Any]) -> str:
    """自己完結の SVG 折れ線 HTML（残数 2 系列: 画面・状態）。外部リソース参照なし。"""
```

- 累積再計算は既存 `compute_exploration_coverage` を k 回呼ぶ素朴実装で足りる（セッション数は高々数十・イベントは数千のオーダー。独自の増分集計を実装しない）
- HTML の配色は `generator/heatmap_reporter.py` の検証済みパレット定数（`_LIGHT_RAMP`/`_DARK_RAMP`）を import して流用する（同層 generator 内なので層分離違反にならない）。estimated な点は破線マーカー＋「推定」ラベルを併記し、色だけに意味を持たせない

### 5-2. エラー処理表

| 事象 | 振る舞い | ユーザー可視 |
|---|---|---|
| sessions/ 不在・セッション 0 件 | 既存 `_exploration_coverage` のエラーのまま（バーンダウンに到達しない） | 「先に --record-session で操作を記録してください」 |
| JSONL 行破損 | `load_session_events` の既存挙動（行スキップ）を踏襲 | なし（既存どおり） |
| ts のパース不能（不正文字列） | mtime 代替＋警告ログ・estimated=True | 系列点に「推定」表示 |
| セッション全イベントが未照合（unmatched のみ） | 0 進捗の点として系列に含める（欠落させない） | 残数が減らない点として可視 |

### 5-3. 既存コードとの接続点

- `src/capture/coverage.py::load_session_events` / `compute_exploration_coverage` — **変更しない**（AC-6）。`SESSIONS_DIR_NAME` を共用
- `src/main.py::_exploration_coverage` — `save_exploration_coverage` 呼び出しの直後に burndown 計算・保存を追加し、ログに出力ファイル名を出す
- `state_signature` / `normalize_footprint_path` — 触らない（CONVENTIONS §1-3）

## 6. テスト仕様

### 6-1. 単体テスト（tests/test_capture.py・新規 tests/test_burndown.py）

| テスト名 | 入力 | 期待値 | AC |
|---|---|---|---|
| test_recorder_appends_timestamp | FakeClock 注入の SessionRecorder（`_FakeRecorderPage` 再利用） | 全レコードに注入時刻の ts | AC-1 |
| test_burndown_orders_sessions_by_ts | ts が逆順の 2 セッション | 系列が時刻昇順に並ぶ | AC-2 |
| test_burndown_mtime_fallback_marked_estimated | ts なし JSONL（tmp_path 実ファイル） | at=mtime 由来・estimated=True・注記 | AC-3 |
| test_burndown_monotonic | 3 セッション累積 | explored/touched 非減少・remaining 非増加 | AC-4 |
| test_single_session_single_point | セッション 1 件 | 点 1 個・HTML 生成が例外なし | AC-5 |
| test_coverage_result_ignores_ts | ts 付きイベントで compute_exploration_coverage | ts なしと同一の集計結果 | AC-6 |
| test_invalid_ts_falls_back | ts="broken" | mtime 代替＋estimated=True | 5-2 |

時刻は FakeClock 注入（`tests/test_real_site_resilience.py::_FakeClock` の前例に倣う。実時刻依存テスト禁止 — CONVENTIONS §4-3）。

### 6-2. 結合テスト（実ファイル I/O・tmp_path）

| テスト名 | 検証 | AC |
|---|---|---|
| test_cli_outputs_burndown_files | report.json＋sessions 2 件を tmp_path に配置 → CLI 分岐関数 → json/html 生成・系列 2 点 | AC-2 |
| test_html_self_contained | 生成 HTML に外部 URL の src/href が無い・SVG を含む | 5-1 |

実ブラウザ E2E は不要（記録済み JSONL とレポートのみで完結）。既存のキャプチャ実ブラウザ E2E（tests/e2e/test_capture_realbrowser_e2e.py）が無変更で PASS することを回帰とする。

### 6-3. 回帰確認

- 既存ユニット全件（1,222 件）PASS。特に tests/test_capture.py の記録内容検証が ts 追加で壊れないこと（§8 罠 2）
- exploration_coverage.json / exploration_heatmap.html の出力が ts 導入前後で同一（AC-6）

## 7. 完了チェックリスト（DoD）

- [ ] AC-1〜6 のテストが全て存在し PASS
- [ ] CONVENTIONS §3 の全ゲート通過（black/ruff/mypy/bandit/pytest/quality_harness）
- [ ] feature_contracts.yml の `exploration_capture` 契約更新
- [ ] 実行パス確認: DemoMart で `--record-session` を 2 回（日を分けられない場合は時刻差で）→ `--exploration-coverage` → exploration_burndown.html で残数が減る折れ線を目視確認

## 8. このタスク固有の罠

- **SessionRecorder は frozen でない dataclass**。clock フィールドは `field(default=...)` に **callable そのもの**を入れる（`default_factory` にすると「datetime を返す関数」ではなく「関数を返す関数」が要る形になり混乱しやすい）。`lambda: datetime.now(UTC)` を default にし、テストでは FakeClock を渡す
- 既存 tests/test_capture.py が記録 dict を**完全一致**で検証している場合、ts 追加で落ちる。テスト側は「期待キーの部分集合比較」へ直してよいが、**ts 以外のキー・値が変わらないこと**の検証は残す
- mtime は git clone・ファイルコピー・rsync で書き換わる。「推定」表示（estimated=True）を UI 文言から絶対に落とさない（evidence-only 原則 — 根拠のない日時を事実として出さない）
- 系列の分母（total_screens/total_states）は**最新の report.json** に対するもの。再クロールで分母が変わると過去点の remaining も再計算される（系列はスナップショットではなく「現インベントリに対する消化史」）。この意味を HTML の注記に明記する
- 記録開始直後の about:blank 除外（CONVENTIONS §4-9）は `_record_visit` 実装済み。burndown 側で再実装しない
