# SPEC-5-3 オンボーディングパック（仕様書＋記録フロー＋用語集の単一 HTML）

| 項目 | 値 |
|---|---|
| WBS | 5-3 |
| 優先度 / 見積 | P3 / 1sp |
| 依存 | 2-4（リプレイ）— 未着手のため「フロー再生」は手順書形式の静的表示に留め、自動再生連携は 2-4 側で行う |
| 背景 | docs/11 §7-3「引き継ぎ」フェーズ（仕様書＋記録済みフロー再生 = 新規参画者のドメイン知識教材） |

## 1. 目的と背景

プロジェクトライフサイクルの「引き継ぎ」フェーズは現状対象外（docs/11 §7-3）。新規参画者向け教材の前例は docs/demo/DEMO_SCRIPT.md（人手で書いたデモ台本）しかない。一方、教材の素材は既に自動生成されている: report.json（画面カタログ・evidence 付き）、sessions/*.jsonl（実操作の足跡）、doc_fusion.json（page_id ↔ 文書上の正式名称）。これらを**外部リソース参照なしの単一 HTML**（onboarding_pack.html）に束ね、「これ 1 ファイル渡せば新規参画者が画面・業務フロー・用語をたどれる」状態を作る。

**現状の実装状態（実装前に必ず確認すること）:**

- 済: 画面インベントリ report.json（screens[].page_id/title/url/headings/forms/page_states/transitions/is_canonical、`src/generator/json_reporter.py`）
- 済: 操作記録 sessions/session_NNN.jsonl（kind=visit/action/state・selector・url・path、`src/capture/session_recorder.py`。読み込みは `capture/coverage.py::load_session_events` が session ファイル名付きで返す）
- 済: 用語対応 doc_fusion.json（`src/generator/fusion_reporter.py::FUSION_JSON_NAME = "doc_fusion.json"`、screen_matches[].page_id/page_title/official_name/method/score）
- 済: 自己完結単一 HTML の前例 `src/generator/heatmap_reporter.py`（html.escape・検証済みパレット・外部リソースなし）
- 済: スクリーンショット `output/{domain}/screenshots/{page_id}.png`（命名規約は `src/diff/screenshot_diff.py::compare_snapshot_screenshots` が前提とする page_id.png）
- 未: 束ねる generator・記録フローの手順書レンダリング・用語集レンダリング・CLI

## 2. 受け入れ条件（全て自動テストで検証すること）

- **AC-1**: `--onboarding-pack` で `onboarding_pack.html` が出力される（Given: クロール済み report.json / When: CLI 実行 / Then: 目次と 4 章 — ①サイト概要 ②画面カタログ ③記録フロー ④用語集 — を含む単一 HTML）
- **AC-2**: 画面カタログは canonical 画面のみを対象とし、doc_fusion の official_name があれば「正式名称（文書由来）」として実測タイトルに併記、URL・フォーム項目（名前・型・必須）・画面状態（page_states の kind）を根拠（セレクタ）付きで一覧する
- **AC-3**: sessions がある場合、セッションごとに visit/action/state を時系列のステップ（番号・操作種別・selector・URL）として手順書形式でレンダリングする。sessions が無い場合は「記録セッションなし（--record-session で追加できます）」と明示する
- **AC-4**: doc_fusion.json がある場合、screen_matches を用語集（page_id・実測タイトル・正式名称・対応根拠 URL一致/名称類似）として表示する。無い場合は「用語集: 参考文書が取り込まれていないため未確認」と明示する（evidence-only: 無いものを無いと書く）
- **AC-5**: 生成 HTML は外部リソース参照ゼロ（`http(s)://` を指す src/href/CSS url() を含まない）。スクリーンショットは data URI（base64）で埋め込み、サイズ上限（既定 300KB・`WEBSPEC2DOC_ONBOARDING_IMG_LIMIT_KB`）超過や欠損は「スクリーンショット未埋め込み（サイズ超過/未取得）」と注記する
- **AC-6**: ユーザー由来文字列（タイトル・見出し・selector 等）は全て html.escape され、既存出力（report.json スキーマ・report_hash・他の生成物）は不変（新規ファイル追加のみ）

## 3. スコープ外

- 記録フローの自動再生・リプレイ実行（WBS 2-4。本パックは静的な手順書表示まで）
- 動画・GIF 化、PDF 変換、多言語対応
- Web UI からの生成ボタン・ダウンロード統合（WBS 1-5/3-5 の UI 統合と合わせて後続）
- 用語の LLM 意味抽出（WBS 1-1。今回の用語集は doc_fusion の突合結果のみ = 根拠のある対応だけを載せる）

## 4. 基本設計

### 4-1. 変更ファイル一覧

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 新規 | `src/generator/onboarding_reporter.py` | `ONBOARDING_FILE_NAME = "onboarding_pack.html"`・4 章レンダリング・data URI 埋め込み |
| 変更 | `src/main.py` | `--onboarding-pack` フラグと `_generate_onboarding_pack()`（`_exploration_coverage` に倣い report.json 必須チェック） |
| 新規 | `tests/test_onboarding_reporter.py` | 単体・結合テスト（§6） |
| 変更 | `quality/feature_contracts.yml` | 新契約 `onboarding_pack`（core_files・failure_modes・required_tests。ui_files/route_files は空配列） |

### 4-2. データモデル

新規の層間データ型は追加しない（既存 dict をそのまま受ける純関数構成）。入力は report: dict / sessions: dict[str, list[dict]]（ファイル名→イベント列）/ fusion: dict | None / screenshots_dir: Path | None の 4 つ。

### 4-3. 処理フロー

```text
_generate_onboarding_pack(args)
  ├─ report.json 読み込み（不在なら logger.error — JSON_REPORT_FILE_NAME）
  ├─ load_session_events(output_dir) → session 名でグループ化（無ければ空 = AC-3 の注記）
  ├─ doc_fusion.json があれば読み込み（無ければ None = AC-4 の注記）
  ├─ generate_onboarding_html(report, sessions, fusion, screenshots_dir)
  │    ①概要（meta: target_url/crawled_at/screen_count・遷移カバレッジ要約）
  │    ②画面カタログ（canonical 画面×official_name×フォーム×状態×スクショ data URI）
  │    ③記録フロー（セッション別ステップ表）
  │    ④用語集（screen_matches or 未確認注記）
  └─ output_dir/onboarding_pack.html へ書き出し
```

## 5. 詳細設計

### 5-1. 関数シグネチャ

```python
# src/generator/onboarding_reporter.py
def generate_onboarding_html(
    report: dict[str, Any],
    sessions: dict[str, list[dict[str, Any]]],
    fusion: dict[str, Any] | None,
    screenshots_dir: Path | None,
) -> str:
    """オンボーディングパックの自己完結 HTML を返す（I/O はスクショ読み込みのみ）。"""

def _embed_screenshot(screenshots_dir: Path | None, page_id: str, limit_kb: int) -> str:
    """screenshots/{page_id}.png を data URI にする。欠損・超過は注記文字列を返す。"""

def _render_flow_steps(session_name: str, events: list[dict[str, Any]]) -> str:
    """visit=「画面へ移動」/ action=「クリック・入力（selector）」/ state=「画面状態の変化」
    としてステップ表を生成。ts があれば時刻列を表示（SPEC-5-2 導入後は自動で載る）。"""
```

- official_name の対応付けは fusion["screen_matches"] から `page_id → official_name` の辞書を作って引く（`ingest/matcher.py::FusionResult.official_names` と同じ対応）
- スタイルは heatmap_reporter に倣いインライン CSS のみ。配色は同モジュールの検証済みパレット定数を import して流用する
- 教材としての読み順は docs/demo/DEMO_SCRIPT.md の構成（概要→画面の見どころ→フロー）を参考に、各章冒頭へ 1〜2 行の「この章の読み方」を置く

### 5-2. エラー処理表

| 事象 | 振る舞い | ユーザー可視 |
|---|---|---|
| report.json 不在 | logger.error で終了（`_exploration_coverage` と同文体） | 「先に `--format json` でクロールしてください」 |
| sessions/ 不在・0 件 | 生成は継続 | ③章に「記録セッションなし」注記 |
| doc_fusion.json 不在・破損 | 生成は継続（破損は警告ログ） | ④章に「参考文書なしのため未確認」注記 |
| スクショ欠損・読込失敗・上限超過 | 生成は継続 | 該当画面に「未埋め込み」注記（理由付き） |
| HTML 書き込み失敗（OSError） | logger.error | 「出力に失敗しました: パス」 |

### 5-3. 既存コードとの接続点

- `src/main.py`: `JSON_REPORT_FILE_NAME`・`_domain_name` を再利用。分岐は `_exploration_coverage` の隣
- `src/capture/coverage.py::load_session_events` — セッション読込を**再実装しない**（record["session"] 付与済み）
- `src/generator/fusion_reporter.py::FUSION_JSON_NAME` — ファイル名定数を共用
- `src/generator/heatmap_reporter.py` — パレット定数・html.escape の使い方の前例

## 6. テスト仕様

### 6-1. 単体テスト（tests/test_onboarding_reporter.py）

| テスト名 | 入力 | 期待値 | AC |
|---|---|---|---|
| test_pack_has_four_sections | report＋sessions＋fusion フル素材 | 目次と 4 章見出しを含む | AC-1 |
| test_catalog_canonical_only_with_official_name | canonical/非 canonical 混在＋fusion | 非 canonical 不掲載・正式名称併記 | AC-2 |
| test_flow_steps_in_event_order | visit→action→state の 3 イベント | ステップ番号順・selector 表示 | AC-3 |
| test_no_sessions_note | sessions={} | 「記録セッションなし」注記 | AC-3 |
| test_no_fusion_glossary_unverified | fusion=None | 「未確認」注記・用語表なし | AC-4 |
| test_no_external_resources | フル素材 | `https?://` を指す src/href/url() が 0 件（正規表現検証） | AC-5 |
| test_screenshot_limit_and_missing | 上限超過 PNG / 欠損（tmp_path） | data URI なし＋理由付き注記 | AC-5 |
| test_html_escapes_user_strings | タイトルに `<script>` を含む report | エスケープ済み・生タグなし | AC-6 |

### 6-2. 結合テスト（実ファイル I/O・tmp_path）

| テスト名 | 検証 | AC |
|---|---|---|
| test_cli_generates_pack_from_files | tmp_path に report.json/sessions/doc_fusion.json/screenshots を配置 → CLI 分岐関数 → onboarding_pack.html 生成・data URI 埋め込み | AC-1, AC-5 |
| test_cli_report_only_minimum_pack | report.json のみ | 生成成功・③④に注記 | AC-3, AC-4 |
| test_missing_report_logs_error | report.json なし | logger.error・例外なし | 5-2 |

実ブラウザ E2E は不要（生成済みファイルのみで完結）。デモ検証は DoD の実行パス確認で行う。

### 6-3. 回帰確認

- 既存ユニット全件（1,222 件）PASS・既存生成物（report.json/report.html/spec.xlsx 等）に差分なし（AC-6）

## 7. 完了チェックリスト（DoD）

- [ ] AC-1〜6 のテストが全て存在し PASS
- [ ] CONVENTIONS §3 の全ゲート通過（black/ruff/mypy/bandit/pytest/quality_harness）
- [ ] feature_contracts.yml に `onboarding_pack` 契約追加
- [ ] 実行パス確認: DemoMart をクロール＋`--record-session` 1 回＋参考文書 1 枚取り込みの上で `--onboarding-pack` を実行し、生成 HTML をブラウザで開いて 4 章・スクショ埋め込み・checkout 画面の正式名称併記を目視確認（ネットワーク遮断状態でも表示が崩れないこと）

## 8. このタスク固有の罠

- **data URI の肥大化**: 全画面のスクショを無制限に埋め込むと HTML が数十 MB になり「1 ファイル教材」の利点が死ぬ。上限は必ず入れ、超過は隠さず「未埋め込み（サイズ超過）」と書く（evidence-only — 黙って落とさない）
- doc_fusion.json の screen_matches キーは `page_id / page_title / official_name / method / score`（fusion_reporter.fusion_to_dict の出力）。`FusionResult.official_names`（dict）とは形が違う — JSON 側を読むこと
- セッションイベントの `ts` は SPEC-5-2 で導入予定。**本仕様は ts が有っても無くても動く**こと（有れば時刻列表示・無ければ列ごと省略）。ts 前提の実装にすると導入順序に依存して壊れる
- `Path.glob` は sessions/ ディレクトリ不在でも空を返すが、`load_session_events` 経由で読むこと（独自実装すると record["session"] 付与や破損行スキップの挙動が乖離する）
- スクショ命名は `screenshots/{page_id}.png` 前提だが、状態スクショ等の別名ファイルが混在する。**page_id 完全一致のみ**埋め込み、当て推量のファジーマッチをしない
- bandit: base64 埋め込み自体は問題ないが、HTML 生成で `format`/f-string に未エスケープ値を混ぜない（全て html.escape 経由のヘルパーに寄せる）
