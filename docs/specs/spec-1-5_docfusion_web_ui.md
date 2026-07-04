# SPEC-1-5 Doc Fusion の Web UI 統合（参考文書アップロードとギャップ表示）

| 項目 | 値 |
|---|---|
| WBS | 1-5（docs/0703-01_plan.md） |
| 優先度 / 見積 | P1 / 1sp |
| 依存 | なし（Phase 1 = CLI の `--reference-doc` は実装済み。SPEC-1-1〜1-4 と独立に価値が出る） |
| 背景 | docs/11 §6-4 実装スケッチ「web/ 文書アップロード UI」 |

## 1. 目的と背景

Doc Fusion は現在 **CLI 専用**（`src/main.py --reference-doc`）で、Web UI からは参考文書を渡す手段が無く、突合結果（doc_fusion.json/md）も画面に表示されない。非エンジニアの主要動線である 4 ステップウィザード（`templates/partials/view-generate.html`）に「参考文書」アップロード欄を追加し、レポート画面にギャップ 3 分類（文書のみ／実測のみ／矛盾）の表示タブを設ける。

**現状の実装状態（実装前に必ず確認すること）:**

- 済: `web/routes/crawl.py::run` — `/run` が form-urlencoded を受け `src/main.py` をサブプロセス起動（`--auth` の付与が引数追加の前例）
- 済: `static/js/execution.js`（100 行付近） — `#form` submit で URLSearchParams を組み立て `/run` へ POST
- 済: ファイルアップロードの前例 — `web/routes/viewpoints.py::api_import_viewpoint_set`（`request.files.get("file")`）
- 済: パス検証の前例 — `web/validation.py::_safe_auth_path`（プロジェクト配下のみ許可）・`_valid_domain`
- 済: `src/ingest/loader.py::SUPPORTED_SUFFIXES`・旧形式（.xls/.doc/.ppt）の変換案内メッセージ
- 未: アップロード API・`/run` への `--reference-doc` 連携・doc_fusion.json の取得 API・ギャップ表示タブ

## 2. 受け入れ条件（全て自動テストで検証すること）

- **AC-1**: ステップ2（条件設定）で参考文書を選択→アップロードするとファイル名一覧が表示され、削除もできる（Given: 条件設定画面 / When: xlsx を選択 / Then: 一覧に表示・hidden 値に保存パスが入る）
- **AC-2**: 未対応拡張子（.exe 等）は API が 400 とエラーメッセージ（対応形式の列挙）を返し、UI に赤字表示される。旧形式（.xls）は loader と同文の変換案内で拒否される
- **AC-3**: アップロード済みで「解析開始」すると `/run` のサブプロセス cmd に `--reference-doc <保存パス>` が付与され、完走後に `output/{domain}/doc_fusion.json` が存在する
- **AC-4**: レポート画面に「文書突合」タブが**doc_fusion.json 存在時のみ**現れ、サマリ（画面対応/文書のみ/実測のみ/矛盾の件数）とギャップ表（分類・画面・項目・内容・文書の出所・実測セレクタ）が表示される
- **AC-5**: 参考文書なしのクロールでは UI・タブ・API とも従来通り（タブ非表示・`/api/doc-fusion` は 404・report.json スキーマ不変）
- **AC-6**: `reference_docs` パラメータに OUTPUT_DIR 外・別ドメイン配下・`../` を含むパスを渡すと `/run` はそれを無視する（パストラバーサル防止）
- **AC-7**: UI E2E（`tests/e2e/` = make verify-ui 配下）が「アップロード→実行→文書突合タブ表示」のフローを検証する

## 3. スコープ外

- LLM 抽出の ON/OFF トグルとルール・要件の UI 表示（SPEC-1-1〜1-3 の成果物の描画は本タスクではギャップ表のみ。documented_rules 等はタブ内に JSON があれば件数表示に留める）
- refreshed_spec.md のプレビュー・ダウンロード導線（SPEC-1-4 完了後の追加タスク）
- アップロード文書の永続管理 UI（一覧・削除画面）。保存先は `output/{domain}/reference_docs/` に置き、再クロール時の再利用は同パス指定で足りる
- 文書内容のサーバ側ウイルススキャン

## 4. 基本設計

### 4-1. 変更ファイル一覧

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 変更 | `web/routes/crawl.py` | `/api/reference-docs`（POST・multipart）追加・`/run` に `reference_docs` パラメータ処理と `--reference-doc` 付与・`/api/doc-fusion`（GET）追加 |
| 変更 | `web/validation.py` | `_safe_reference_doc_paths(raw, domain)` 追加（§5-1） |
| 変更 | `templates/partials/view-generate.html` | ステップ2 のオプション行に「参考文書（任意）」欄・結果タブ列に「文書突合」タブとパネル追加 |
| 変更 | `static/js/wizard.js` | アップロード UI（選択→POST→一覧描画→削除） |
| 変更 | `static/js/execution.js` | `/run` の body に `reference_docs` を追加 |
| 変更 | `static/js/results.js` | doc_fusion.json 取得とタブ表示切替（存在時のみ） |
| 新規 | `static/js/doc-fusion.js` | ギャップ表・サマリの描画（`view-utils.js` のエスケープ関数を利用） |
| 新規 | `tests/e2e/test_doc_fusion_ui_e2e.py` | UI E2E（§6-2） |
| 変更 | `tests/test_web_routes*.py` 相当 | ルート単体テスト追加（§6-1） |
| 変更 | `quality/feature_contracts.yml` | doc_fusion 契約の ui_files / route_files を空配列から更新 |

### 4-2. データモデル（API 契約）

```python
# POST /api/reference-docs  (multipart: domain, files[])
# 200: {"ok": true, "saved": [{"name": "画面一覧.xlsx", "path": "output/example.com/reference_docs/画面一覧.xlsx"}]}
# 400: {"ok": false, "error": "未対応の文書形式です: ...（対応形式: .xlsx, .xlsm, ...)"}
_MAX_REFERENCE_DOC_BYTES = 20 * 1024 * 1024  # 20MB/ファイル
_REFERENCE_DIR_NAME = "reference_docs"

# GET /api/doc-fusion?domain=example.com
# 200: doc_fusion.json の中身をそのまま返す（fusion_to_dict のスキーマ）
# 404: {"error": "doc_fusion.json not found"}
```

### 4-3. 処理フロー

```text
[ステップ2] ファイル選択 → POST /api/reference-docs
  → 拡張子 allowlist（loader.SUPPORTED_SUFFIXES）・旧形式拒否・サイズ検証
  → output/{domain}/reference_docs/ に保存（ファイル名は sanitize）→ 保存パス返却
[解析開始] execution.js が body に reference_docs=<パス,カンマ区切り> を追加
  → /run: _safe_reference_doc_paths で検証 → cmd += ["--reference-doc", path] × N
[完了] results.js が GET /api/doc-fusion → 200 なら「文書突合」タブ表示
  → doc-fusion.js がサマリ＋ギャップ表を描画（kind_labels は fusion_reporter と同語彙）
```

## 5. 詳細設計

### 5-1. 関数シグネチャ

```python
# web/validation.py
def _safe_reference_doc_paths(raw: str, domain: str) -> list[str]:
    """カンマ区切りパスを検証する。resolve 後に
    OUTPUT_DIR/{domain}/reference_docs/ 配下の実在ファイルのみ通す
    （_safe_auth_path と同じ resolve→parents 判定）。不正パスは黙って除外し警告ログ。"""

# web/routes/crawl.py
@bp.post("/api/reference-docs")
def upload_reference_docs() -> tuple[dict, int] | dict:
    """multipart 受信。domain は _valid_domain で検証。ファイル名は
    Path(name).name に縮めたうえ拡張子を SUPPORTED_SUFFIXES で検証。
    旧形式（.xls/.doc/.ppt）は loader と同文の案内で 400。"""

@bp.get("/api/doc-fusion")
def api_doc_fusion() -> tuple[dict, int] | Response:
    """output/{domain}/doc_fusion.json を返す。無ければ 404。
    domain 検証は live_screenshot と同じ _valid_domain。"""
```

```html
<!-- view-generate.html ステップ2（compare チェックボックスの行の下）-->
<div class="field" id="reference-doc-block" style="margin-top:10px">
  <label for="reference-doc-input">参考文書（任意 — 既存の画面一覧・項目定義書など）</label>
  <input type="file" id="reference-doc-input" multiple
         accept=".xlsx,.xlsm,.docx,.pptx,.pdf,.md,.txt,.yaml,.yml,.json" />
  <ul id="reference-doc-list"></ul>
  <div id="reference-doc-status" class="input-field-message"></div>
</div>
<!-- 結果タブ（result-tabs の history の前・初期 hidden）-->
<button type="button" role="tab" aria-selected="false" class="result-tab" data-tab="doc-fusion"
        aria-controls="rp-doc-fusion" id="tab-doc-fusion" hidden>文書突合<span class="tab-count" id="tab-count-doc-fusion"></span></button>
<div class="result-tab-panel rp-simple" id="rp-doc-fusion" role="tabpanel" tabindex="0" aria-label="文書突合" hidden></div>
```

### 5-2. エラー処理表

| 事象 | 振る舞い | ユーザー可視 |
|---|---|---|
| 未対応拡張子・サイズ超過 | 400・保存しない | `#reference-doc-status` に赤字（対応形式・上限を明記） |
| 旧形式 .xls/.doc/.ppt | 400 | 「xlsx 形式に変換してから指定してください」（loader と同文） |
| アップロード成功後にクロール失敗 | 保存ファイルは残す（再実行で再利用可） | 既存のエラー表示（exec-error）のみ |
| 突合自体の失敗（文書が壊れている等） | CLI 側で警告に留め完走（`_run_doc_fusion` の既存挙動） | 実行ログに警告文が流れ、タブは非表示（404） |
| /api/doc-fusion の JSON 破損 | 500 + error JSON | タブ非表示・console.warn |
| 不正 reference_docs パス | 除外して通常クロール続行 | 実行ログに「参考文書パスを無視しました」 |

### 5-3. 既存コードとの接続点

- `web/routes/crawl.py::run` — cmd 組み立て（`--auth` 追加の直後に `--reference-doc` を追加）・`_valid_domain`/`OUTPUT_DIR` は web/config・web/validation の既存 import
- `static/js/execution.js:109` 付近 — URLSearchParams への `reference_docs` 追加（hidden input または wizard.js が保持する配列から）
- `static/js/results.js` — SUMMARY 受信後のタブ初期化処理に doc-fusion 判定を追加（`fetch('/api/doc-fusion?domain=...')`）
- `templates/partials/view-generate.html:118` 付近（上級設定 details の隣）と `:244` 付近（result-tabs）
- `src/ingest/loader.py::SUPPORTED_SUFFIXES` — 拡張子 allowlist の単一ソース（web 側に別リストを書かない。web→src の import は許容方向）
- `src/generator/fusion_reporter.py::fusion_to_dict` — 表示するキー（meta / screen_matches / doc_only_screens / crawl_only_page_ids / field_gaps）と kind_labels の語彙

## 6. テスト仕様

### 6-1. 単体テスト（Flask test client・tests/test_web_docfusion_routes.py 新規）

| テスト名 | 入力 | 期待値 | AC |
|---|---|---|---|
| test_upload_saves_supported_file | xlsx を multipart POST | 200・reference_docs/ に保存・パス返却 | AC-1 |
| test_upload_rejects_unknown_suffix | .exe | 400・error に対応形式列挙・未保存 | AC-2 |
| test_upload_rejects_legacy_xls | .xls | 400・「変換してから」案内 | AC-2 |
| test_run_appends_reference_doc_args | reference_docs 付き /run（subprocess をモック） | cmd に --reference-doc とパス | AC-3 |
| test_run_ignores_traversal_path | `../../etc/passwd`・他ドメイン配下 | cmd に付与されない | AC-6 |
| test_doc_fusion_api_404_when_missing | doc_fusion.json なし | 404 | AC-5 |
| test_doc_fusion_api_returns_json | フィクスチャ JSON 配置 | 200・meta.field_gaps 等が透過 | AC-4 |
| test_upload_size_limit | 20MB 超のダミー | 400・未保存 | 5-2 |

### 6-2. UI E2E（tests/e2e/test_doc_fusion_ui_e2e.py — make verify-ui 配下・base-url 8765）

| テスト名 | 検証 | AC |
|---|---|---|
| test_reference_doc_upload_flow | ステップ2 でファイル選択→一覧表示→削除 | AC-1 |
| test_gap_tab_visible_after_fusion | doc_fusion.json をフィクスチャ配置した domain のレポートで「文書突合」タブが現れ、ギャップ表に 3 分類が描画される | AC-4 |
| test_no_docs_no_tab | doc_fusion.json の無い domain でタブ非表示 | AC-5 |

クロール実行込みの通し（アップロード→実行→タブ）はデモサイト `contact.html` ＋ md 参考文書で 1 本（CONVENTIONS §4-5: login.html を標的にしない）。デモサーバのポートは既存 UI E2E の流儀（8765 の GUI に対する fixture）に従い、新規に必要なら未使用ポートを環境変数付きで定義する（§4-7）。

### 6-3. 回帰確認

- 既存 UI E2E 64 件が無変更で PASS（タブ追加が既存タブの data-tab 切替を壊さないこと — results.js のタブ列挙がハードコードなら要修正箇所として洗い出す）
- 参考文書なしクロールの report.json・SUMMARY 行のスキーマ不変（AC-5）

## 7. 完了チェックリスト（DoD）

- [ ] AC-1〜7 のテストが全て存在し PASS
- [ ] CONVENTIONS §3 の全ゲート通過（black/ruff/mypy/bandit/pytest/quality_harness）
- [ ] **templates/ static/ を変更するため `make verify-ui` の通過が必須**（.ui-verified マーカー生成まで。省略した完了宣言はリジェクト）
- [ ] feature_contracts.yml の doc_fusion に ui_files（view-generate.html・wizard.js・doc-fusion.js 等）・route_files（web/routes/crawl.py）を記載
- [ ] 実行パス確認: ブラウザで アップロード→解析開始→実行ログに --reference-doc→文書突合タブのギャップ表→output/{domain}/reference_docs/ と doc_fusion.json の実在、まで通しで目視確認（UI→API→core→出力→永続化→ユーザー可視証跡）

## 8. このタスク固有の罠

- **`/run` は form-urlencoded のストリーミング応答**であり multipart にできない（応答を読みながらの実行ログ表示が壊れる）。アップロードは必ず**別 API に分離**し、`/run` へはパスだけ渡す 2 段構成にする
- 保存ファイル名に日本語が来る（「画面一覧.xlsx」）。`werkzeug.utils.secure_filename` は**非 ASCII を全部落として空文字にする**ため使わない。`Path(name).name` で directory 部を剥がし、拡張子 allowlist＋保存先ディレクトリ固定で安全性を担保する（前例: `_safe_auth_path` の resolve→parents 判定）
- doc_fusion.json の `field_gaps[].detail` や quote は**ユーザー文書由来の任意文字列**。innerHTML に直挿しすると XSS になる。描画は textContent か既存のエスケープユーティリティ（view-utils.js）経由に限定する
- 結果タブは `result-tabs` の `data-tab` 規約で切り替わる。**タブボタンだけ追加してパネル id（`rp-doc-fusion`）や aria-controls を欠くと、既存タブ切替 JS が例外で全タブ死する**。既存タブ（runs 等）の属性一式を完全に揃えて複製する
- bandit がアップロード処理の `open`/パス結合を指摘しやすい。抑制コメントに逃げず、保存先を `OUTPUT_DIR/{domain}/reference_docs` に resolve 固定してから書き込む正攻法で通す（CONVENTIONS §4-1）
- UI E2E は pytest-playwright（同期 API）。実ブラウザの専用スレッドパターンが必要なのは `sync_playwright()` 直呼びの場合のみで、既存 `tests/e2e/test_ui_smoke_e2e.py` の流儀（page fixture）に合わせれば不要。**新規に sync_playwright を直接呼ばない**（§4-2 の罠）
