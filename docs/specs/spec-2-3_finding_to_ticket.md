# SPEC-2-3 気づきマーク → 再現手順付きバグ票（JSON/CSV エクスポート）

| 項目 | 値 |
|---|---|
| WBS | 2-3（docs/0703-01_plan.md） |
| 優先度 / 見積 | P2 / 1sp |
| 依存 | 2-1（再現手順の生成に SPEC-2-1 の手順変換ロジックを再利用） |
| 背景 | docs/11 §7-2 ①気づき登録・§7-3 実行フェーズ「気づき→バグ票自動起票」 |

## 1. 目的と背景

探索的テスト中にテスターが「バグ疑い」「気になる」と感じた瞬間、現状は別ツールへ手でメモを取り、後から再現手順を思い出して書き起こす必要がある。本タスクで記録ブラウザ上のワンクリックマーク（気づきイベント）を実装し、それまでの操作記録から**再現手順を自動生成したバグ票**を出力する。起票先は特定ツール非依存の**汎用 JSON/CSV**とする（TestRail 連携 `web/services/testrail_exporter.py` は PR #29 で削除済み — 特定ベンダー依存を復活させない）。

**現状の実装状態（実装前に必ず確認すること）:**

- 済: `src/capture/session_recorder.py::_RECORDER_JS` — click/change を `window.__ws2dEvents` バッファに溜め、`poll_once` が回収して JSONL 化（ポーリング方式の理由は同ファイル docstring 参照 — binding コールバック再入の回避）
- 済: `poll_once` は現在の画面状態シグネチャ（`state_signature`）を追跡している（`_last_state_sig`）— 気づき発生時点の画面状態をそのまま転記できる
- 済: `src/generator/csv_reporter.py` — 「特定のテスト管理ツールに依存しない汎用テストケース CSV」の前例（`CSV_ENCODING = "utf-8-sig"`・Excel 互換）
- 済（2-1 完了後）: `src/capture/reverse_generator.py` — action イベント → 手順文字列の変換
- 未: 気づきマーク UI・`kind: "finding"` イベント・バグ票生成・エクスポートの一切

## 2. 受け入れ条件（全て自動テストで検証すること）

- **AC-1**: 記録中のページに気づきマークウィジェット（固定表示ボタン＋任意メモ入力）が注入され、クリックで `kind: "finding"` イベントが JSONL に記録される（Given: 記録セッション中 / When: マークをクリックしメモを入力 / Then: `{kind, note, url, path, state_id}` が追記される）
- **AC-2**: 気づきイベントには発生時点の画面状態（`_last_state_sig` の値。default 含む）が記録される — 独自ハッシュを作らず記録済みシグネチャを転記する（CONVENTIONS §1-3）
- **AC-3**: バグ票の再現手順が「セッション開始（最初の visit）から気づき時点まで」の visit/action イベントから自動生成され、各手順に実測セレクタが含まれる（confidence 1.0・evidence-only）
- **AC-4**: `findings.json` と `findings.csv`（utf-8-sig・Excel でそのまま開ける）が出力され、CSV は 1 気づき = 1 行・再現手順はセル内改行で表現される
- **AC-5**: メモ未入力の気づきも棄却されない（title は「無題の気づき（<path>）」の自動命名。無いことにしない）
- **AC-6**: 気づき機能未使用時の後方互換: finding イベントの無い既存セッション JSONL でエクスポートを実行すると空の findings（0 件）で正常完走し、既存の `--exploration-coverage` 集計は finding イベントが混ざっても結果が変わらない（未知 kind は無視される）
- **AC-7**: 実ブラウザ E2E で「記録開始 → 操作 → マーク → エクスポート → 再現手順にマーク前の操作が載る」ことを検証する

## 3. スコープ外

- 外部バグトラッカー（Jira/Redmine/TestRail 等）への API 起票（汎用 JSON/CSV を人手/別ツールで取り込む前提。PR #29 の方針を踏襲）
- 気づき時点のスクリーンショット自動撮影（ポーリング方式のため撮影タイミングが操作と競合する。Phase 2 で recorder 側の安全な撮影点を設計してから）
- 重要度（severity）の自動判定（推定になるため出さない。CSV には空欄の「重要度」列のみ用意し人間が記入する）
- Web UI での気づき一覧表示（SPEC-2-2 のタブ拡張として別途）

## 4. 基本設計

### 4-1. 変更ファイル一覧

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 変更 | `src/capture/session_recorder.py` | `_RECORDER_JS` に気づきウィジェット追加・`poll_once` で finding イベント回収 |
| 新規 | `src/capture/finding_reporter.py` | finding → FindingTicket 変換・findings.json / findings.csv 出力 |
| 変更 | `src/main.py` | `--export-findings` モード追加（`--exploration-coverage` と同型） |
| 変更 | `tests/test_capture.py` | recorder の finding 回収テスト追記（`_FakeRecorderPage` 拡張） |
| 新規 | `tests/test_finding_reporter.py` | 単体テスト（§6-1） |
| 新規 | `tests/e2e/test_finding_e2e.py` | 実ブラウザ E2E（§6-2） |
| 変更 | `quality/feature_contracts.yml` | 新契約 `finding_ticket` 追加 |

### 4-2. データモデル

```python
# session_recorder.py が JSONL に追記するレコード（既存 3 種に 4 種目を追加）
{"kind": "finding", "note": "<メモ or 空>", "url": ..., "path": ..., "state_id": "<現在シグネチャ>"}

# src/capture/finding_reporter.py（CONVENTIONS §1-1: frozen + tuple）
@dataclass(frozen=True)
class FindingTicket:
    finding_id: str                 # "F001" 連番（セッション横断）
    session: str                    # "session_001.jsonl"
    title: str                      # note 先頭 40 文字 / 空なら "無題の気づき（<path>）"
    note: str
    url: str
    path: str
    state_id: str                   # 気づき時点の画面状態（"default" 含む）
    repro_steps: tuple[str, ...]    # "1. https://… を開く" "2. 「#btn」をクリック" …
    evidence_selector: str          # 直前 action の selector（無ければ空 = 未確認と明示）
    confidence: float = 1.0        # 実測由来固定
```

### 4-3. 処理フロー

```text
記録時（session_recorder 変更）
  _RECORDER_JS: 右下固定の「⚑ 気づき」ボタン（Shadow DOM 不使用・高 z-index）
    クリック → prompt でメモ入力（空可）→ __ws2dEvents.push({type:'finding', note})
  poll_once: type=='finding' → {"kind":"finding", note, url, path, state_id:self._last_state_sig}

エクスポート時（CLI --export-findings）
  load_session_events(output_dir)                       # 既存を共用
  build_finding_tickets(events)
    ├─ セッション単位にグループ化（行順 = 時系列）
    ├─ finding ごとに、そのセッションの先頭〜finding 直前の visit/action を手順化
    │    （手順文字列化は reverse_generator の変換を再利用 — 二重実装禁止）
    └─ FindingTicket 生成（連番はセッション名昇順 → 行順）
  save_findings(tickets, output_dir)
    ├─ findings.json（全フィールド）
    └─ findings.csv（utf-8-sig・§5-2 のヘッダ）
```

## 5. 詳細設計

### 5-1. 関数シグネチャ

```python
# src/capture/finding_reporter.py（新規）
def build_finding_tickets(events: list[dict[str, Any]]) -> list[FindingTicket]:
    """セッションイベントから気づき票を構築する。finding が無ければ空リスト。"""

def save_findings(tickets: list[FindingTicket], output_dir: Path) -> None:
    """findings.json と findings.csv を出力する（0 件でもファイルは生成し件数 0 を明示）。"""

# src/capture/session_recorder.py（変更）
# SessionRecorder.poll_once: raw_events ループで type=='finding' を分岐。
# レコードの state_id は self._last_state_sig を転記（再計算しない — AC-2）。
# _RECORDER_JS のウィジェット注入は既存の再注入機構（add_init_script + evaluate）に乗せる。
```

CSV ヘッダ（`csv_reporter._TESTCASE_HEADER` の流儀に合わせた日本語固定ヘッダ）:

```text
ID, タイトル, 再現手順, URL, 画面状態, 気づきメモ, 根拠セレクタ, セッション, 重要度
```

「重要度」は常に空欄（§3 スコープ外の明示。推定値を書かない）。

### 5-2. エラー処理表

| 事象 | 振る舞い | ユーザー可視 |
|---|---|---|
| ウィジェット注入失敗（CSP 等） | 記録自体は継続（既存 evaluate の例外握り潰しと同じ方針）・警告ログ | ログ「気づきウィジェットを注入できません（記録は継続）」 |
| finding 前に操作が 1 件も無い | repro_steps は URL を開く 1 手順のみ・evidence_selector 空 | 票の手順に「操作記録なし（未確認）」注記 |
| note に改行・カンマ・引用符 | csv モジュールのクォートに委ねる（手書きエスケープ禁止） | Excel で正しく 1 セル表示 |
| セッションが 1 つも無い | エラーログで中断（exploration-coverage と同文言方針） | 「探索セッションがありません」 |

### 5-3. 既存コードとの接続点

- `src/capture/session_recorder.py::_RECORDER_JS` / `poll_once` / `_last_state_sig` — 記録側の唯一の変更点
- `src/capture/coverage.py::load_session_events` — 読み込み共用。`compute_exploration_coverage` は kind 不一致を素通しする実装のため**変更不要**（AC-6 の回帰テストで裏取りする）
- `src/capture/reverse_generator.py`（SPEC-2-1）— action → 手順文字列の変換関数を import して共用
- `src/generator/csv_reporter.py::CSV_ENCODING` — エンコーディング定数を共用
- `src/main.py::_exploration_coverage` — CLI モード追加の型紙

## 6. テスト仕様

### 6-1. 単体テスト（tests/test_capture.py 追記・tests/test_finding_reporter.py）

| テスト名 | 入力 | 期待値 | AC |
|---|---|---|---|
| test_finding_event_recorded_with_state | `_FakeRecorderPage` に finding をバッファ・live_state にモーダル | JSONL レコードに kind=finding・state_id=直前シグネチャ | AC-1, AC-2 |
| test_repro_steps_from_preceding_actions | visit → action×2 → finding | 手順 3 件（URL＋操作 2）・セレクタ含む | AC-3 |
| test_untitled_finding_kept | note="" | title="無題の気づき（/checkout）"・棄却されない | AC-5 |
| test_csv_multiline_and_comma_safe | note に改行とカンマ | csv.reader で読み戻して 1 行 9 列 | AC-4 |
| test_zero_findings_completes | finding 無しイベント列 | tickets==[]・findings.json に 0 件出力 | AC-6 |
| test_coverage_ignores_finding_events | finding 混在イベントで既存集計 | Phase 1 と同一の coverage 結果 | AC-6 |
| test_severity_column_always_empty | 任意の finding | CSV 重要度列が空欄 | §3 |

### 6-2. 実ブラウザ E2E（tests/e2e/test_finding_e2e.py・専用スレッドパターン必須）

`_run_in_thread`（tests/e2e/test_capture_realbrowser_e2e.py）とデモサイト fixture を再利用。標的は `contact.html`（フォーム — CONVENTIONS 罠#5）。ポートは **8901** を環境変数 `WEBSPEC2DOC_E2E_FINDING_PORT` 付きで定義（CONVENTIONS 罠#7。8898=SPEC-3-1・8899=SPEC-2-1 予約済み）。

| テスト名 | 検証 | AC |
|---|---|---|
| test_finding_widget_visible_and_marks | 記録ページにウィジェット表示 → クリックで JSONL に finding | AC-1, AC-7 |
| test_exported_ticket_has_repro_steps | 操作 → マーク → export-findings → 票の手順に直前操作 | AC-3, AC-7 |

### 6-3. 回帰確認

- 既存 `tests/test_capture.py` 全件・`tests/e2e/test_capture_realbrowser_e2e.py` が無変更で PASS（レコーダー変更の影響確認）
- finding を含まない旧セッション JSONL での `--exploration-coverage` / `--reverse-assets`（2-1）が従来どおり動く

## 7. 完了チェックリスト（DoD）

- [ ] AC-1〜7 のテストが全て存在し PASS
- [ ] CONVENTIONS §3 の全ゲート通過（black/ruff/mypy/bandit/pytest/quality_harness）。templates/ static/ は変更しないため verify-ui は対象外（変更した場合は必須に切り替える）
- [ ] feature_contracts.yml に `finding_ticket` 契約（core_files=`src/capture/finding_reporter.py`・`src/capture/session_recorder.py`、failure_modes=`widget_injection_failed`/`no_sessions`/`no_preceding_actions`、required_tests）
- [ ] 実行パス確認: デモサイトで記録 → マーク → `--export-findings` → findings.csv を Excel（または LibreOffice）で開いて再現手順の改行表示まで目視確認
- [ ] 未実行項目があれば「未確認」と報告

## 8. このタスク固有の罠

- **ウィジェットのクリックが操作イベントとして二重記録される**: マークボタン自体への click が `_RECORDER_JS` の click リスナーに拾われ、再現手順に「気づきボタンをクリック」が混入する。ウィジェット要素に専用 id（例 `__ws2d_finding_btn`）を付け、click リスナー側で除外し、その単体テストを書く（罠#9「初期状態ノイズ」と同種の明示的除外）
- prompt() ベースのメモ入力は同期ブロックだが、レコーダーは**ポーリング方式**なので Python 側は影響を受けない（binding 方式に変えたくなっても再入デッドロックの理由で禁止 — session_recorder.py docstring）
- ページ遷移でウィジェットは消える。`add_init_script` 済みなので次ページで自動再注入されるが、SPA（pushState）ではページロードが起きず初回注入のまま生き残る — 両ケースの動作を E2E で確認する
- CSV は `csv.writer` に任せる。`\n` を `\\n` に手置換すると Excel のセル内改行にならない（utf-8-sig と合わせて csv_reporter の前例に従う）
- finding イベントの追加は sessions/*.jsonl の**追加 kind** であり既存 kind のスキーマ変更ではない。coverage.py 側に finding の分岐を「追加しない」こと（未知 kind 素通しが後方互換の担保。集計に混ぜたくなったら SPEC-2-2 側の仕事）
