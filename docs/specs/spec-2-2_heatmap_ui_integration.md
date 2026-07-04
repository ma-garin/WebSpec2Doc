# SPEC-2-2 ヒートマップの UI 統合とチャーター自動提案

| 項目 | 値 |
|---|---|
| WBS | 2-2（docs/0703-01_plan.md） |
| 優先度 / 見積 | P1 / 1sp |
| 依存 | なし（キャプチャ Phase 1 実装済み。SPEC-2-1 とは独立） |
| 背景 | docs/11 §7-2 ③ヒートマップ・SBTM チャーター提案 |

## 1. 目的と背景

Phase 1 で `exploration_heatmap.html` は生成されるが、単体ファイルとして孤立している。report.html（配布用の自己完結文書）と Web UI の結果画面（`static/js/results.js` の 6 タブ構成）のどちらからも辿れず、「テストの進み具合と穴が、この地図で毎日見えます」（docs/11 §7-5）というデモの締めが成立しない。本タスクでヒートマップを両方に統合し、さらに「未探索 × ビジネスフロー優先度・高」の画面を次の探索チャーターとして自動提案する。

**現状の実装状態（実装前に必ず確認すること）:**

- 済: `src/capture/coverage.py::compute_exploration_coverage` / `save_exploration_coverage` — `exploration_coverage.json`（`summary / screens / unmatched_footprints`）と `exploration_heatmap.html` を出力
- 済: `src/generator/heatmap_reporter.py::generate_heatmap_html`（`HEATMAP_FILE_NAME = "exploration_heatmap.html"`・自己完結・ライト/ダーク検証済みパレット）
- 済: report.json の `meta.business_flows`（`prioritize_business_flows` 由来・priority "高"）— チャーター提案の優先度ソース
- 済: Web UI タブ基盤 — `static/js/results.js` の `TAB_DEFS`（panel / render / subs のレジストリ）、`templates/partials/view-generate.html` の `.result-tabs` ボタン列と `rp-*` パネル、`web/routes/report.py::api_result` の `files` dict（`path_of` で成果物パスを返す）
- 済: report.html はサイドバー型（`src/generator/html_reporter.py::_section` / `_sidebar`。`_coverage_section` / `_impact_section` がオプトイン表示の前例）
- 未: report.html への探索カバレッジセクション、Web UI の探索カバレッジタブ、チャーター提案の一切

## 2. 受け入れ条件（全て自動テストで検証すること）

- **AC-1**: `exploration_coverage.json` が存在する状態でクロール（または `--exploration-coverage` 再集計）すると、report.html のサイドバーに「探索カバレッジ」項目とセクションが載る（Given: カバレッジ集計済み / When: report.html 生成 / Then: 画面カバレッジ率・未探索画面一覧・チャーター提案が表示される）
- **AC-2**: カバレッジ未集計時は report.html にセクションもサイドバー項目も現れず、既存出力とバイト同一性を保つ（オプトイン — CONVENTIONS §2）
- **AC-3**: Web UI 結果画面に「探索カバレッジ」タブが追加され、`/api/result` が `files.exploration_heatmap` / `files.exploration_json` を返し、タブ内にヒートマップ（iframe）とチャーター提案リストが表示される
- **AC-4**: チャーター提案は「explored=false かつ business_flows（priority 高）の nodes に含まれる画面」を最優先に列挙し、各提案に根拠（該当 flow_name と path_id）を付ける（evidence-only）
- **AC-5**: business_flows が無い・セッションが無い場合、提案は空配列で完走する（エラー・推定提案を出さない）。カバレッジファイルが無いドメインでは Web UI タブが「未集計」の空状態表示になる
- **AC-6**: `exploration_coverage.json` への `charters` キー追加はオプトイン（business_flows を渡した時のみ付与）。既存キー（summary/screens/unmatched_footprints）のスキーマは不変
- **AC-7**: UI E2E（make verify-ui・GUI ポート 8765）でタブ切替・ヒートマップ表示・提案表示・空状態を検証する

## 3. スコープ外

- 状態（モーダル・タブ）単位のセル塗り分けの高度化（Phase 1 の `states` 集計表示を流用）
- 消化バーンダウン（WBS 5-2）・チーム集約ヒートマップ（docs/11 §7-4）
- Web UI からの記録セッション起動（記録は CLI のまま。UI は閲覧と提案のみ）
- チャーターの担当者割当・SBTM セッション管理

## 4. 基本設計

### 4-1. 変更ファイル一覧

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 変更 | `src/capture/coverage.py` | `propose_charters` 追加・`compute_exploration_coverage` に business_flows 引数（既定 None）追加 |
| 変更 | `src/generator/heatmap_reporter.py` | チャーター提案セクションの描画追加（`charters` キー存在時のみ） |
| 変更 | `src/generator/html_reporter.py` | `_exploration_section` 追加・`generate_html_report` に `exploration_coverage` 引数（既定 None）追加・`_sidebar` に項目追加 |
| 変更 | `src/main.py` | `_run_crawl` / `_exploration_coverage` で既存カバレッジ・business_flows を接続 |
| 変更 | `web/routes/report.py` | `api_result` の `files` に `exploration_heatmap` / `exploration_json` 追加 |
| 変更 | `templates/partials/view-generate.html` | タブボタン `data-tab="coverage"` とパネル `rp-coverage` 追加 |
| 変更 | `static/js/results.js` | `TAB_DEFS` に `coverage` エントリ追加 |
| 新規 | `static/js/view-coverage.js` | `renderCoverage`（ヒートマップ iframe＋提案リスト＋空状態） |
| 変更 | `templates/index.html` | view-coverage.js の script 読み込み追加 |
| 新規 | `tests/test_charter_proposal.py` ほか | 単体テスト（§6-1） |
| 新規 | `tests/e2e/test_coverage_tab_e2e.py` | UI E2E（§6-2・verify-ui 対象） |
| 変更 | `quality/feature_contracts.yml` | `exploration_capture` 契約に ui_files / route_files を追記 |

### 4-2. データモデル

チャーター提案は dict のみ（`exploration_coverage.json` に載せる JSON がスキーマの正）:

```python
# exploration_coverage.json に追加されるオプトインキー
"charters": [
  {
    "page_id": "P003",
    "url": "https://…/checkout",
    "title": "チェックアウト",
    "reason": "未探索 × ビジネスフロー通過画面",
    "flows": [{"flow_name": "ログイン→決済", "path_id": "TP012"}],  # 根拠
    "priority": "高"          # flow 通過時のみ。それ以外の未探索は "中"
  }
]
```

### 4-3. 処理フロー

```text
CLI --exploration-coverage（既存モード・変更）
  ├─ report.json 読込 → meta.business_flows を取り出す
  ├─ compute_exploration_coverage(report, events, business_flows=flows)
  │    └─ flows が非 None なら coverage["charters"] = propose_charters(...)
  └─ save_exploration_coverage(coverage, output_dir)   # 既存（heatmap 側が charters を描画）

report.html 生成（_run_crawl 内・変更）
  └─ output_dir/exploration_coverage.json が存在すれば読み込み
     → generate_html_report(..., exploration_coverage=coverage)  # None なら従来と同一出力

Web UI
  └─ /api/result → files.exploration_heatmap（/preview?path=… で iframe 表示）
     files.exploration_json（renderCoverage が fetch して提案リストを描画）
```

## 5. 詳細設計

### 5-1. 関数シグネチャ

```python
# src/capture/coverage.py（追加・変更）
def propose_charters(
    coverage: dict[str, Any], business_flows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """未探索画面とビジネスフロー（priority 高）通過画面の積集合からチャーター案を返す。
    照合キー: flow の nodes（URL）を normalize_footprint_path で正規化し、
    coverage["screens"] の url 正規化パスと突合する（独自ハッシュ禁止 — CONVENTIONS §1-3）。
    並び順: フロー通過の未探索 → その他未探索（page_id 昇順）。"""

def compute_exploration_coverage(
    report: dict[str, Any],
    events: list[dict[str, Any]],
    business_flows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """既存処理は不変。business_flows 指定時のみ戻り値に "charters" を追加する。"""

# src/generator/html_reporter.py（追加）
def _exploration_section(exploration_coverage: dict | None) -> str:
    """None または空なら空文字を返す（_impact_section と同型のオプトイン）。
    サマリータイル（カバレッジ率）・未探索画面表・チャーター提案表を _section で包む。"""
```

```javascript
// static/js/results.js の TAB_DEFS に追加（レジストリ方式を崩さない）
coverage: { panel: 'rp-coverage', render: 'renderCoverage' },
// static/js/view-coverage.js（新規）: renderCoverage は resultHero へ描画するだけ
// （パネル永続化の仕組みは results.js 側が持つ — 既存 view-*.js と同じ流儀）
```

### 5-2. エラー処理表

| 事象 | 振る舞い | ユーザー可視 |
|---|---|---|
| exploration_coverage.json が破損 JSON | 警告ログ・report.html は従来出力へフォールバック | ログ「探索カバレッジの読込に失敗（セクション省略）」 |
| business_flows のキー欠落（nodes 無し等） | その flow をスキップして続行 | — |
| Web UI: カバレッジファイル無し | files キーは空文字・タブは空状態表示 | 「探索セッション未集計。CLI の --record-session → --exploration-coverage を実行してください」 |
| /preview の path 検証 | 既存 `_safe_output_path` に委譲（新規検証を書かない） | 404 |

### 5-3. 既存コードとの接続点

- `web/routes/report.py::api_result` の `path_of` — `exploration_heatmap.html` / `exploration_coverage.json` を同方式で追加
- `static/js/results.js::TAB_DEFS` と `_switchPanels` — タブ追加はレジストリ 1 行＋テンプレート（ディープリンク `#report/<domain>/coverage` は既存機構で自動対応）
- `src/generator/html_reporter.py::_sidebar(pages, has_coverage, has_impact)` — 引数 `has_exploration` を追加（既定 False = 既存呼び出し互換）
- `src/main.py::_exploration_coverage` — business_flows の受け渡しと report.html 再生成はここが起点

## 6. テスト仕様

### 6-1. 単体テスト（tests/test_charter_proposal.py・tests/test_html_reporter.py 追記）

| テスト名 | 入力 | 期待値 | AC |
|---|---|---|---|
| test_charter_unexplored_flow_screen_first | 未探索×flow 通過 1 件＋未探索のみ 1 件 | 前者が先頭・priority "高"・flows に根拠 | AC-4 |
| test_charter_empty_without_flows | business_flows=None | "charters" キー自体が無い | AC-5, AC-6 |
| test_charter_all_explored | 全画面 explored=true | charters == [] | AC-5 |
| test_coverage_json_schema_unchanged | flows なし集計 | 既存 3 キーのみ（スナップショット比較） | AC-6 |
| test_report_html_without_coverage_identical | exploration_coverage=None | 従来出力と同一文字列 | AC-2 |
| test_report_html_with_coverage_has_section | 集計済み dict | 「探索カバレッジ」セクション＋サイドバー項目 | AC-1 |
| test_api_result_returns_heatmap_paths | fixture ドメインにファイル配置 | files.exploration_heatmap が実パス | AC-3 |

### 6-2. UI E2E（tests/e2e/test_coverage_tab_e2e.py・make verify-ui）

`tests/e2e/test_report_tabs_e2e.py` の fixture 方式（`output/<fixture-domain>/` に report.json 等を直接配置・GUI は既存ポート **8765**）に倣う。実ブラウザ再記録は不要 — 固定の exploration_coverage.json を fixture として置く。

| テスト名 | 検証 | AC |
|---|---|---|
| test_coverage_tab_renders_heatmap | タブ切替 → iframe にヒートマップ・提案リスト表示 | AC-3, AC-7 |
| test_coverage_tab_charter_reason_visible | 提案行に flow_name（根拠）が表示される | AC-4 |
| test_coverage_tab_empty_state | カバレッジ無しドメイン → 空状態文言 | AC-5 |
| test_coverage_deeplink | `#report/<domain>/coverage` 直リンクでタブ選択 | AC-3 |

### 6-3. 回帰確認

- `tests/e2e/test_report_tabs_e2e.py`（既存 6 タブ・ディープリンク互換）が無変更で PASS
- report.json の report_hash が不変（本タスクは report.json に触らない）
- 既存 `exploration_heatmap.html` 単体生成（Phase 1 経路）が従来どおり動く

## 7. 完了チェックリスト（DoD）

- [ ] AC-1〜7 のテストが全て存在し PASS
- [ ] CONVENTIONS §3 の全ゲート通過（black/ruff/mypy/bandit/pytest/quality_harness）
- [ ] **UI 変更（templates/ static/ の変更）のため `make verify-ui` の PASS が必須**（CONVENTIONS §3・飛ばした場合は完了と言わない）
- [ ] feature_contracts.yml の `exploration_capture` に ui_files（view-generate.html / results.js / view-coverage.js）・route_files（web/routes/report.py）を追記
- [ ] 実行パス確認: デモサイトで record → coverage → Web UI タブ表示 → チャーター提案の根拠リンクまで目視確認（UI→API→core→出力→永続化→エラー処理→ユーザー可視証跡）
- [ ] 未実行項目があれば「未確認」と報告

## 8. このタスク固有の罠

- `generate_html_report` の引数追加は**既定値 None 必須**。呼び出し側は `src/main.py` に複数箇所ある（686/769/806 行付近のラッパー群）— 1 箇所でも漏れると TypeError ではなく「セクションが出ない」形で静かに失敗する。AC-1 の統合テストで検知する
- Web UI のタブは `results.js` の `TAB_DEFS` **と** `view-generate.html` のボタン/パネルの**両方**を足す。片方だけだと `_switchPanels` が 'overview' へフォールバックし、E2E が「タブはあるのに中身が overview」で落ちる
- ヒートマップ iframe は `/preview?path=…` 経由で表示する。`file://` 直参照や新規静的配信ルートを作らない（`_safe_output_path` のパス検証を迂回しない — bandit/SSRF 対策の前例）
- チャーターの画面照合は URL 正規化パス（`normalize_footprint_path`）。flow の nodes には状態ノード（`#state=` 付き — `transition_graph.STATE_NODE_SEPARATOR`）が混ざり得るため、照合前に分離すること
- ダークモード: heatmap_reporter は `prefers-color-scheme` で両モード検証済みパレットを使っている。提案セクションの追加色は既存の `--warn` / `--ok` 変数を使い、新規カラーコードを持ち込まない
