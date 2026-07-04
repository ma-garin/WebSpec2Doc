# 実装規約と既知の罠（全仕様書共通・実装前に必読）

本書は docs/specs/ 配下の全実装仕様書に共通する制約である。**実装エージェント（人間・AI を問わず）は、着手前に本書と対象仕様書・CLAUDE.md・.claude/rules/functional-integrity.md を読むこと。** 本書に反する実装は仕様書に合致していてもリジェクトされる。

## 1. アーキテクチャの掟

### 1-1. 層分離（依存方向は上→下のみ）

```text
web/ (routes → services)          … Flask UI・API。src の関数を呼ぶ
src/main.py                        … CLI エントリポイント
src/{crawler, ingest, capture}     … 入力層（実測・文書・操作記録）
src/{analyzer, graph, diff, llm}   … 解析層
src/generator                      … 出力層（md/html/excel/json/pdf）
```

- 下の層から上の層を import しない（例: crawler から generator を呼ばない）
- 層をまたぐデータは frozen dataclass（`@dataclass(frozen=True)`・コレクションは `tuple`）で受け渡す
- LLM 呼び出しは必ず `src/llm/provider.py` の LLMProvider Protocol 経由。**OpenAI キーが無い環境でも RulesProvider フォールバックで完走する**こと（デモ・CI の前提）

### 1-2. evidence-only 原則（このプロダクトの魂）

- 出力されるすべての事実に根拠を付ける: 実測由来 = `SourceEvidence`（selector・bbox・screenshot_path）で confidence **1.0 固定**、LLM 由来 = confidence **0.9 以下**、文書由来 = `DocumentEvidence`（file・location・quote）
- **根拠のない推定値を出力しない。読めなかったものは「未確認」と明示する**（例: closed shadow root は「検出したが読めない」と記録）
- LLM 出力には幻覚フィルタを必須とする: 実在しないセレクタ・要素を参照する出力は破棄

### 1-3. 状態の接合キー

画面状態の識別は `src/crawler/action_explorer.py` の **`state_signature(parts)` を必ず共用**する（クロール時の PageState.state_id と操作記録の突合キー）。独自ハッシュを実装してはならない。画面の照合は正規化 URL パス（`capture/session_recorder.py` の `normalize_footprint_path`）、画面同定は fingerprint v2（`analyzer/canonicalizer.py`）。

## 2. コーディング規約

- Python 3.11〜3.12（playwright 1.44 の制約。3.13 は不可）。`from __future__ import annotations` を全ファイル先頭に
- 型ヒント必須（mypy strict 相当で通ること）。コメント・docstring・エラーメッセージ・ログは**日本語**
- 環境変数は `WEBSPEC2DOC_` プレフィックス。既定値は安全側（例: ローカル URL 拒否・mutation 遮断）
- report.json 等の既存出力スキーマへの追加は**オプトイン**にする: 機能未使用時にキーを追加しない（report_hash・スナップショット互換を壊さない。前例: `official_name` は突合時のみ付与）
- 新機能は `quality/feature_contracts.yml` に契約を追加（`core_files`・`failure_modes`・`required_tests` 必須。ui_files/route_files は該当なしなら空配列可）

## 3. 品質ゲート（この順で全部通す — 1つでも飛ばすと CI で落ちる）

```bash
venv/bin/python -m black <変更ファイル...>        # ruff だけでは不足。CI に black --check がある
venv/bin/python -m ruff check --fix <変更ファイル...>
venv/bin/python -m mypy <変更した src 配下...>
venv/bin/python -m bandit -r src web app.py -ll -q  # Medium 以上ゼロ
venv/bin/python -m pytest tests/ -q --ignore=tests/e2e
venv/bin/python scripts/quality_harness.py
# templates/ static/ の *.html/js/css を変更した場合のみ:
make verify-ui
```

コミットは機能単位・日本語メッセージ。pre-commit フックが pytest を強制する。

## 4. 既知の罠（すべて実際に CI を落とした実績のある罠）

| # | 罠 | 正しいやり方 |
|---|---|---|
| 1 | **bandit と ruff の抑制コメントは別物**。`# noqa: S314` は bandit に効かない | 抑制するなら `# nosec BXXX  # noqa: SXXX` を併記。ただし原則は抑制でなく正攻法（XML→defusedxml、0.0.0.0→環境変数ゲート） |
| 2 | **pytest-playwright のセッション fixture がメインスレッドの asyncio ループを保持**し、e2e で `sync_playwright()` を直接呼ぶと `Sync API inside the asyncio loop` で死ぬ（ローカル単独実行では再現しない） | 実ブラウザ処理は専用スレッドで実行。`tests/e2e/test_capture_realbrowser_e2e.py` の `_run_in_thread` パターンを再利用 |
| 3 | **環境依存テスト**: CI の unit ジョブは venv なし・ブラウザ未導入。「この環境なら全 PASS」型のテストは CI で落ちる | 環境不変の性質を検証する（例:「FAIL 項目には必ず fix が付く」）。時刻依存は FakeClock 注入（`tests/test_real_site_resilience.py` 参照） |
| 4 | black 未適用のまま push（ruff は通る） | ゲート手順（§3）を省略しない |
| 5 | デモサイトの `login.html` を E2E 標的にするとログインウォール検出でスキップされ、テストが空振りする | E2E 標的は `contact.html`（フォーム）・`dashboard.html`（モーダル/タブ/アコーディオン）・`spa.html`・`checkout.html` を使う |
| 6 | ローカル URL は SSRF 保護で既定拒否 | テスト・デモでは `WEBSPEC2DOC_ALLOW_LOCAL=1` を設定（e2e は fixture 内で設定済み） |
| 7 | ポート衝突: 8765=GUI、8766=demo、8894/8896=既存 e2e | 新規 e2e は未使用ポートを環境変数付きで定義する |
| 8 | Playwright の Chromium はリポジトリ配下 `.runtime/ms-playwright` 固定（PR #30） | `playwright install` を直接叩かない。`make setup-runtime` / `scripts/manage_playwright_runtime.py` を使う |
| 9 | 記録開始直後の `about:blank` が足跡に混入する類の「初期状態ノイズ」 | 境界イベント（about:/chrome-error:）は明示的に除外し、その単体テストを書く |
| 10 | frozen dataclass に dict フィールドを持たせるとハッシュ不能 | 原則 tuple。dict が必要なら `field(default_factory=dict)` で hash 非依存の用途に限定 |

## 5. テストの掟

- 新規ロジックには**同一コミットで**単体テストを付ける（tests/test_*.py、日本語 docstring でテスト意図を書く）
- テストピラミッド: 単体（フェイク注入・高速）→ 結合（実ファイル I/O・tmp_path）→ 実ブラウザ E2E（tests/e2e/・デモサイト標的・専用スレッド）
- フェイクの前例: `_FakeRecorderPage`（tests/test_capture.py）、`_FakeClock`（tests/test_real_site_resilience.py）、`_WaitProbePage`（同）。新規フェイクはこれらに倣う
- 完了宣言の前に §3 のゲートを全部通し、**実行パス（UI→API→core→出力→永続化→エラー処理→ユーザー可視証跡）を実際に動かす**（.claude/rules/functional-integrity.md）。実行できない項目は「未確認」と報告する

## 6. 仕様書の読み方

各仕様書（SPEC-X-Y）は次の構成をとる。**§2 受け入れ条件がそのまま合格判定**であり、§6 のテスト仕様は受け入れ条件と 1 対 1 以上で対応する。仕様書に無い設計判断が必要になった場合は、本書 §1〜2 の制約内で最小の選択を行い、実装報告に「仕様外判断」として明記すること。
