# WS2D-CS-001 コーディング規約

- 文書ID: WS2D-CS-001
- 版数: 2.0 / 作成日: 2026-08-02
- 実体は `pyproject.toml`（black・ruff・mypy・pytest 設定）＋ `docs/specs/CONVENTIONS.md`（実装規約・既知の罠10件）＋ `.claude/rules/`（AIエージェント向け共通規約）。本書はこれらを統合し、`docs/sdlc/_asbuilt/modules.json`（実装237モジュールの実測）を根拠に具体的な数値基準を追加した統合ビューである。

## 1. 目的と適用範囲

本書は WebSpec2Doc のソースコード（`src/`, `web/`, `app.py`, `scripts/`, `tests/`）およびフロントエンド資産（`static/`, `templates/`）に適用するコーディング規約を定める。目的は次の3点。

1. 実装者（人間・AIエージェントを問わず）が、レビュー前に自分のコードを規約に照らして自己点検できるようにする。
2. `make lint` / pre-commit hook で機械的に強制される項目と、人間のレビューで確認する項目を明確に分離する。
3. 「規約は800行以内と書いてあるが実態は1700行のファイルがある」といった規約と実態の乖離を隠さず記録し、次の改訂の材料にする。

適用範囲外: `docs/sdlc/_asbuilt/` 配下の自動生成JSON、`static/vendor/` 配下のサードパーティ資産（driver.js・mermaid、いずれも `ASSET.md` にライセンス記録済み）。これらは本規約の対象としない。

新規にコードを書く・既存コードを変更するすべての作業（人間・Claude・Codex等のAIエージェントを問わず）が本書の適用対象であり、`docs/specs/CONVENTIONS.md` と矛盾する場合は CONVENTIONS.md を優先する（本書はその要約・統合ビューであり、一次情報源ではない）。

## 2. Python コーディング規約（PEP 8 準拠）

### 2-1. 基本方針

- Python 3.11〜3.12 のみを対象とする（`docs/specs/CONVENTIONS.md` §2）。3.13 非対応の理由は playwright 1.44.0 の wheel 制約であり、`src/doctor.py` の `PLAYWRIGHT_PYTHON_SUPPORT` 対応表で機械検証する。3.13対応の判断基準は `docs/specs/spec-6-2_dependency_update_strategy.md` を参照。
- PEP 8 に準拠し、行長は black（line-length=100）に委ねる。ruff 側は `E501`（行長超過）を意図的に ignore 設定にしている（`pyproject.toml`）——二重に指摘される状態を避けるため、権威を black 側に一本化している。
- コメント・docstring・エラーメッセージ・ログ出力はすべて日本語で書く（`docs/specs/CONVENTIONS.md` §2 で明記された既存方針）。変数名・関数名等の識別子は英語（PEP 8 準拠のsnake_case/PascalCase）。

### 2-2. 命名規則（種別ごと）

実際のコードベースから収集した実例に基づく命名規則を以下に示す。

| 種別 | 規則 | 実例 | 出典 |
|---|---|---|---|
| モジュール／パッケージ | 全小文字・アンダースコア区切り（snake_case）。短く具体的な名詞 | `page_crawler.py`, `auth_store.py`, `viewpoint_store.py` | `src/crawler/`, `web/services/` |
| クラス | PascalCase（CapWords） | `BoundaryCase`, `CanonicalInfo`, `AnalyzedPage`, `SessionRecorder`, `AuthError` | `src/analyzer/bva.py`, `src/capture/session_recorder.py` |
| 関数・メソッド | snake_case、動詞始まりが基本 | `derive_boundary_cases`, `crawl_site`, `build_state_table`, `resolve_session` | `src/analyzer/bva.py`, `src/crawler/page_crawler.py` |
| 変数 | snake_case | `auth_path`, `login_url`, `current_url` | `web/routes/login.py` |
| 定数（モジュールレベル） | UPPER_SNAKE_CASE | `SCRAPE_TIMEOUT_SEC`, `SUBMIT_TIMEOUT_SEC`, `ROLE_ADMIN`, `ROLE_MEMBER`, `PLAYWRIGHT_PYTHON_SUPPORT` | `web/routes/login.py`, `web/services/auth_store.py`, `src/doctor.py` |
| プライベート関数・変数 | 単一の先頭アンダースコア `_name` | `_out()`, `_valid_domain()`, `_rel()`, `_require_path()`, `_validate_feature()` | `web/routes/login.py`, `scripts/quality_harness.py` |
| Blueprint（Flask） | 変数名 `bp`、モジュール名と対応する文字列 | `bp = Blueprint("account", __name__)` | `web/routes/account.py` |
| テスト用フェイク | アンダースコア始まり＋名詞 | `_FakeRecorderPage`, `_FakeClock`, `_WaitProbePage` | `tests/test_capture.py`, `tests/test_real_site_resilience.py` |

二重アンダースコア（name mangling、`__name`）の使用は本コードベースでは積極採用されていない。プライベート性の表現は単一アンダースコアで統一する。

### 2-3. PEP 8 からの逸脱点

- 行長: PEP 8 既定の79字ではなく100字（black設定）。
- import順序の強制はツール任せ（ruffの `I`（isort相当）ルール選択）であり、手動での並べ替えは不要。

## 3. 型ヒントの方針

- 全 Python ファイルの先頭に `from __future__ import annotations` を置く。実例: `web/routes/account.py`, `web/routes/login.py`, `src/ci_drift.py`, `scripts/quality_harness.py` はすべてこの1行がファイル冒頭（docstring直後）にある。
- 型ヒントは必須。`docs/specs/CONVENTIONS.md` §2 は「型ヒント必須（mypy strict 相当で通ること）」と明記している。mypy 設定（`pyproject.toml`）は `warn_unused_ignores=true`・`warn_redundant_casts=true`・`no_implicit_optional=true` を有効化しており、曖昧な型抑制を許さない。
- 戻り値注釈は原則すべての関数（public・private問わず）に付与する。実測サンプルでは `def _out() -> Path`、`def check_python_version(...) -> CheckResult`、`def count(name: str) -> int` のように、1行の小さなヘルパー関数にも戻り値注釈が付いている。戻り値が無い場合も `-> None` を明示する。
- `ignore_missing_imports=true` は networkx / openpyxl / playwright のスタブ未提供に対する現実的な妥協であり、「型を書かなくてよい」という意味ではない。スタブが無いサードパーティ呼び出し箇所こそ、呼び出し側の型を厳密に書く。
- Union型は `X | Y` 記法（PEP 604、`from __future__ import annotations` により3.11でも文字列注釈として解決可能）を使う。実例: `web/routes/account.py` の `BaseResponse | str`。

## 4. docstring 規約

- **日本語で書く。** これは例外のないプロジェクト全体の方針である（`docs/specs/CONVENTIONS.md` §2）。
- 形式は Google/NumPy 形式のような `Args:`/`Returns:` セクション構造を厳密には強制していない。実態は「1行の要約」＋（必要なら）空行を挟んで「設計背景・理由・引用文献」を続ける自由記述形式が主流。実例: `src/mbt/pairwise.py` は要約1行の後に「方針:」の箇条書きで設計判断を説明し、`src/techniques/combinatorial.py` は一次出典（Cohen et al. 1997、Kuhn et al. 2004、NIST SP 800-142 等）を著者・年・タイトル付きで明記している。
- **「主張境界」の明記慣行**: 本プロダクトはevidence-only原則（後述§12）を持つため、多くのモジュールdocstringに「主張境界:」という定型見出しで、そのモジュールが**主張しないこと**を明示する慣行がある。実例: `src/apispec/__init__.py`「クロール中に発火した呼び出しのみ。APIの網羅は主張しない」、`src/diff/severity.py`「変更が安全か危険かの判断ではない」、`src/viewport/__init__.py`「未選択の画面幅や実機固有の挙動については何も言わない」。新規モジュールも、判定・分類・スコアリングを行う場合はこの慣行に倣うこと。
- 必須範囲: 新規モジュールは module docstring を必須とする。実測では `src/main.py`, `src/llm/provider.py`, `src/analyzer/canonicalizer.py`, `src/diff/differ.py` 等、旧来のモジュールに docstring 欠如が残っている（`(no module docstring)` を実際に確認したもの）。これは是正対象であり、新規追加分での欠如は許容しない。
- 関数・メソッドのdocstringは、複雑な設計判断を伴う場合（既知の罠の回避、他モジュールとの責務分担、evidence-onlyの適用方法）は必須。単純な1行ヘルパーは省略可。

## 5. ファイル・関数の大きさの上限（実測ベース）

`docs/sdlc/_asbuilt/modules.json`（237モジュール: src 147 / web 90）と関数単位のAST解析（2026-08-02実測、2,360関数）による実態は次のとおり。

| 指標 | 実測値 |
|---|---|
| ファイル行数 最大 | 1,724行（`web/routes/auto_run.py`） |
| ファイル行数 上位3 | `web/routes/auto_run.py`(1724) / `src/main.py`(1581) / `src/crawler/page_crawler.py`(1491) |
| 800行超のファイル数 | 6件以上（実測上位25件中で確認） |
| 関数の長さ 中央値 | 12行 |
| 関数の長さ 平均 | 19.4行 |
| 関数の長さ p90 | 44行 |
| 関数の長さ 最大 | 228行（`src/main.py: _run_crawl`） |

旧版規約（v1.0）は「1ファイル800行以内・関数50行以内」を目安としていたが、実態は最大ファイルが目安の2倍超、最長関数も228行と目安を大きく超える。これは中央値・p90（44行）が示すとおり大多数の関数は目安内に収まっている一方、CLI引数パーサ（`parse_args`, `build_parser`）やオーケストレータ関数（`_run_crawl`, `crawl_site_parallel`, `run_playwright`）に長い関数が集中していることを意味する。

本書が定める基準（v2.0、実態を踏まえて改訂）:

- **新規関数は 50 行以内を目標**とする（p90=44行が実態として裏付ける妥当な目安）。
- 100行を超える場合は、責務分割（ヘルパー関数への抽出）を検討したうえで、分割しない理由（一体的なフロー制御・可読性への配慮等）をレビューコメントに残す。
- 200行を超える関数の新規追加は原則禁止。既存の超過分（`_run_crawl`, `parse_args`, `build_state_table` 等）は「新規に触る際に段階的に縮小する」対象として扱い、無関係な変更のついでに一括リファクタリングしない。
- ファイルは「多数小ファイル > 少数巨大ファイル」の原則を維持し、新規ファイルは800行を上限の目安とする。既存の超過ファイル（`auto_run.py` 等）は機能追加のたびにさらに肥大化させず、責務の分割（例: 既存の `web/services/qa/` のような下位パッケージ化）を優先的に検討する。

## 6. import 順序

- 標準ライブラリ → サードパーティ → ローカル（自プロジェクト）の順。ruff の `I`（isort相当ルール）を `select` に含めており（`pyproject.toml`: `select = ["E", "F", "W", "I", "UP", "B"]`）、`make lint`（`ruff check --fix`）実行で自動整列される。手動での並べ替え作業は不要かつ非推奨（ツールと結果が食い違う編集をしない）。
- `from __future__ import annotations` は import 群の最初（モジュールdocstringの直後）に単独で置く。
- ruff の他ルールカテゴリの意味: `UP`（pyupgrade、古い書き方を新しい構文へ）・`B`（bugbear、バグを誘発しやすいパターン検出）・`E`/`F`/`W`（pycodestyle・pyflakes基本チェック）。これらも `make lint` で自動修正・検出される。
- `pyproject.toml` の `[tool.pytest.ini_options]` は `pythonpath = ["."]` を設定しており、テストコードは常にリポジトリルートを基準にimportする（`from src...`, `from web...` 形式）。相対import（`from .. import`）はテストコードでは使わない。
- 循環importを避けるための層間import制約は本書 §11「層分離」を参照。

## 7. 例外処理の規約

- 境界（ユーザー入力・API応答・ファイルI/O）では必ず検証し、フェイルファストで失敗する。`docs/specs/CONVENTIONS.md` の既知の罠にも「環境依存テスト」等、失敗を握りつぶさず可視化する設計が繰り返し要求されている。
- **エラーを黙殺しない。** 実例: `scripts/quality_harness.py` の `_read_contracts()` は `json.JSONDecodeError` を捕捉し、`AssertionError` に変換して原因を明示するメッセージへ再送出する。`web/routes/login.py` の `api_login_simple` は `subprocess.TimeoutExpired` と `json.JSONDecodeError` の両方を個別に捕捉し、利用者向けの日本語メッセージ＋適切なHTTPステータス（504・500）を返す。
- 例外を握りつぶす（`except Exception: pass`）ような実装は禁止。フォールバック処理を行う場合でも、`src/llm/activity_log.py` のようにフォールバックの発生自体を記録する（「記録の失敗はLLM呼び出し自体を妨げないbest-effort」）。
- UI/APIでは利用者向けの日本語メッセージ、サーバ側ログには文脈付きの詳細情報を出す、という二層構成を徹底する。
- `failure_modes` は `quality/feature_contracts.yml` の各機能契約に列挙されており、critical/highリスクの機能では想定される失敗モードごとにテストが要求される（`required_tests` に `error_path` 等が必須）。新規の例外パスは、対応する機能のfailure_modesに追記するかを検討する。

## 8. イミュータブル方針

- **既存オブジェクトを破壊せず、新しいオブジェクトを返す。** `docs/specs/CONVENTIONS.md` §1-1: 「層をまたぐデータは frozen dataclass（`@dataclass(frozen=True)`・コレクションは `tuple`）で受け渡す」。`src/autorun/stages.py` のdocstringにも設計方針として明記: 「不変データ。更新は必ず新しいオブジェクトを返す。」
- 採用実績（`frozen=True` / `NamedTuple` / `@dataclass` の使用を実際に確認したファイル、2026-08-02 grep実測）: `src/doctor.py`, `src/capture/session_recorder.py`, `src/capture/finding_reporter.py`, `src/capture/burndown.py`, `src/llm/industry_template.py`, `src/wording/consistency.py`, `src/capture/reverse_generator.py`, `src/llm/viewpoint_generator.py`, `src/llm/screen_classifier.py`, `src/llm/openai_client.py`, `src/viewport/profiles.py`, `src/archive/full_archive.py`, `src/autorun/qf_schema.py`, `src/autorun/techniques.py`, `src/autorun/stages.py` 他、計22ファイル以上で確認。全体（237モジュール）への普及率としては部分採用の段階であり、「全面適用済み」ではない点は正直に記録する。
- **既知の罠**（`docs/specs/CONVENTIONS.md` §4 罠10）: frozen dataclass に `dict` フィールドを持たせるとハッシュ不能になる。原則 `tuple` を使い、`dict` がどうしても必要な場合は `field(default_factory=dict)` を使い、hash に依存しない用途に限定する。
- ミューテーションパターンの代替として `.with_xxx()` スタイルの更新メソッドを使う（新しいインスタンスを返す）。既存オブジェクトのフィールドを直接書き換えるコードは新規追加しない。

## 9. ログ出力規約

- 日本語で書く（コメント・エラーメッセージと同一方針）。
- LLM呼び出しは必ずアクティビティログを残す（`src/llm/activity_log.py`）。記録項目は「目的・接続先・モデル・結果・所要時間・プロンプト長」のみで、**プロンプト本文そのものは保存しない**（情報漏洩・秘密混入を避けるため）。ログ記録自体の失敗はLLM呼び出しの成功を妨げないbest-effort設計とする。
- 管理操作の監査ログ（`web/services/admin_audit.py`）は「秘密値なしのJSONLへ追記・検索する」設計。ログに秘密情報（パスワード・トークン等）を書き込まないことは、本書§10のセキュリティ規約と直結する。
- pre-commit hook（`.githooks/pre-commit`）のログ出力は色分け関数（`log_info`/`log_ok`/`log_warn`/`log_fail`/`log_blocked`）で統一されており、シェルスクリプトのログ出力もこのパターンに倣う。
- 構造化ログ（JSON形式）は `web/services/metrics.py` 等の可観測性機能（`/metrics` Prometheus形式エンドポイント）で採用されている。将来的にログの機械集計が必要な箇所は、自由文字列ログではなくJSONL形式を優先する。

## 10. セキュリティ規約

- **秘密情報のハードコード禁止。** パスワードはメモリ内のみで保持し、送信後に変数を破棄する（`src/crawler/auto_login.py` のdocstring方針）。認証情報のFlask↔サブプロセス間受け渡しはコマンドライン引数を使わずstdin経由にする（`web/routes/login.py: api_login_simple` のコメント: 「認証情報はstdin経由でサブプロセスに渡し、コマンドライン引数・ログに残さない」）。
- **入力検証**: すべてのルートハンドラで境界検証を行う（例: `_valid_domain()` によるドメイン名検証、`web/routes/login.py`）。ドメイン名・URLはパストラバーサル文字（`/`, `\`, `..`）を拒否する。
- **SQLパラメータ化**: `web/services/auth_store.py`（SQLite、1,322行）は認証・テナント管理の中核ストアであり、パラメータ化されたクエリを用いる（生SQL文字列へのユーザー入力の直接埋め込みを禁止）。
- **SSRF対策**: ローカルURL（127.0.0.1等）は既定で拒否する（`src/crawler/url_safety.py`）。テスト・デモ時のみ `WEBSPEC2DOC_ALLOW_LOCAL=1` で明示的に許可する。AutoRunの全外向き通信は送信ゲートウェイ（`web/services/egress_gateway.py: assert_target_allowed`）を唯一の出口とし、DNSリバインディング・自己オリジンへの誘導を拒否する。
- **非信頼コンテンツ境界**: クロール対象サイト由来のデータ（`<title>`・placeholder等）は全て汚染済みとして扱う（`web/services/untrusted_content.py`）。LLMへの埋め込みはプロンプトインジェクション対策込みの区切り（`src/llm/prompt_guard.py: untrusted_block`）を必ず使う。
- **XSS対策**: フロントエンドのDOM生成で文字列連結を行う場合は必ず `escHtml`（`core.js`）でエスケープする。
- **XML攻撃対策**: Office文書（.docx/.pptx）の読み込みは `defusedxml` を使う（`src/ingest/office_reader.py`）。標準の `xml` モジュールを直接使わない。
- **静的セキュリティ解析**: `make security`（bandit `-ll`＝Medium以上ゼロ必須、pip-audit）。bandit抑制コメント（`# nosec`）とruff抑制コメント（`# noqa`）は別物であり、抑制する場合は両方を併記する必要がある（`docs/specs/CONVENTIONS.md` §4 罠1）。原則は抑制ではなく正攻法（例: XML→defusedxml、0.0.0.0→環境変数ゲート）。

## 11. 層分離とアーキテクチャの掟

`docs/specs/CONVENTIONS.md` §1-1 が定める依存方向:

```text
web/ (routes → services)          … Flask UI・API。src の関数を呼ぶ
src/main.py                        … CLI エントリポイント
src/{crawler, ingest, capture}     … 入力層（実測・文書・操作記録）
src/{analyzer, graph, diff, llm}   … 解析層
src/generator                      … 出力層（md/html/excel/json/pdf）
```

- 下の層から上の層をimportしない（例: `crawler` から `generator` を呼ばない）。実例として `src/capture/finding_reporter.py` は CSVエンコーディングの値だけを `generator.csv_reporter` から複製し、importはしていない（層違反の回避を意図的に選択した「仕様外判断」としてdocstringに明記）。
- `web/routes/*` は入力検証と委譲のみを行う「薄いルート」とし、ロジックは `web/services/` または `src/` に置く。
- ドメイン中核（`src/`）はFlask非依存を維持する。
- `web` → `src` の一方向依存のみ許可。逆方向（`src` が `web` をimport）は禁止。実例: `src/ingest/req_tracer.py` のdocstringに明記「`web` 側からこのモジュールをimportしてはならない（web → src の一方向依存のみ）」。

## 12. evidence-only 原則（このプロダクトの魂）

- 出力されるすべての事実に根拠を付ける。実測由来のデータは `SourceEvidence`（selector・bbox・screenshot_path）で confidence **1.0固定**、LLM由来は confidence **0.9以下**、文書由来は `DocumentEvidence`（file・location・quote）で表現する。
- **根拠のない推定値を出力しない。読めなかったものは「未確認」と明示する**（例: closed shadow rootは「検出したが読めない」と記録する）。
- LLM出力には幻覚フィルタを必須とする。実在しないセレクタ・要素を参照する出力は破棄する（`src/ingest/llm_extractor.py` の quote 突合、`filter_hallucinated_findings` 等）。
- 本書の他章（docstring規約の「主張境界」、セキュリティ規約の「非信頼コンテンツ境界」）もこの原則から派生している。新規機能を実装する際は、「この機能が主張してよいこと／主張してはいけないこと」を実装前に自問すること。

## 13. JavaScript / CSS の規約

`static/` 配下の実態（2026-08-02確認）に基づく。

- **素のJavaScript（フレームワークなし）。** ビルドステップ・バンドラを使わない。`static/js/` 配下に機能単位でファイルを分割する（例: `autorun-chat.js`, `history.js`, `view-testcase-grid.js`）。IIFEパターン（`(function () { 'use strict'; ... })()`）でグローバル汚染を避ける。
- 命名: 関数はcamelCase（`currentHistory()`, `syncContextLabel()`, `setPhase()`）、定数はUPPER_SNAKE_CASE（`MAX_HISTORY`, `PRESETS`）。コメントは日本語。
- **ESLint / Prettier 等のJS/CSS向け静的解析ツールは未導入**（`.eslintrc*`, `.prettierrc*`, `package.json` を2026-08-02時点でリポジトリ直下に検索したが存在しない）。JS/CSSの品質担保は現状レビューとE2Eテストに依存しており、機械的な静的解析は無い。これは既知のギャップとして記録し、導入するかは別途判断する。
- CSS変数によるデザイントークン一元管理（`static/tokens.css`）。色は生のhex値を直書きせず、トークン参照（`var(--color-primary)` 等）を使う。ダークモード追従のため。例外はエクスポート下地の白のみ。
- 共通UI部品を再利用する: `ui-states.js`（状態表示）、`core.js`（toast/dialog、`escHtml`）、`table-utils.js`（テーブル共通処理）。同じUIパターンを個別ファイルで再実装しない。
- `static/vendor/` はサードパーティ資産専用（driver.js, mermaid）。ライセンスは `ASSET.md` に記録し、CDN取得は行わない（オフライン完結の方針、`src/ux/axe_runner.py` の axe-core 同梱も同じ方針）。

## 14. HTML / Jinja2 テンプレートの規約

- `templates/` 配下、`templates/partials/` で画面単位に分割する（例: `view-generate.html`, `view-settings.html`, `view-auto-run.html`）。1ファイル1画面（またはタブ）を基本とする。
- Jinja2の既定の自動エスケープに依存する。テンプレート内で `|safe` フィルタを使う場合は、その文字列が信頼できる出所（自プロダクト生成物）であることを確認する。
- DOM生成をJavaScript側で行う場合（`innerHTML` への文字列連結等）は、§13で述べた `escHtml`（`core.js`）を必ず通す。
- E2Eテストのセレクタ安定性のため、既存の `id` / `class` / `data-*` 属性は理由なく変更しない（変更するとE2Eテストの broken selector を誘発する）。

## 15. Git コミットメッセージ規約

`type: description` 形式（日本語のdescription）。実際の `git log`（2026-08-02、直近40件）から確認した実例:

| コミットメッセージ | 種別 |
|---|---|
| `fix: ログイン後の遷移を「ユーザー選択→テナント選択→システム選択」にする` | fix |
| `feat: 初期管理者を admin / password で自動作成する` | feat |
| `feat: マルチテナント（ログイン→テナント選択→システム選択）` | feat |
| `refactor: 並列discoverの後始末とブラウザ共有が不可な理由の記録` | refactor |
| `perf: 最初の解析を短くする（無反応 1.8秒→0.14秒、実時間 -37%）` | perf |
| `chore: 生成に置き換わった業種テンプレート3本を削除する` | chore |
| `fix: CSV取込が根拠を捏造していたのを直す` | fix |
| `refactor: 観点の役割を1箇所で決め、検証の規律を記録する` | refactor |

観察できる方針:

- 「何を」だけでなく「なぜ」を書く（例: `refactor: 並列discoverの後始末と*ブラウザ共有が不可な理由の記録*`）。
- 定量的な効果がある場合は数値を入れる（`perf` の例: 「無反応 1.8秒→0.14秒、実時間 -37%」）。実測なしの「速くなった」という主観的表現は避ける。
- 使用が確認された type: `feat` / `fix` / `refactor` / `chore` / `perf`。`docs` / `test` / `ci` は親ルール（`~/.claude/rules/common/git-workflow.md`）で定義されているが、直近40件のログでは出現しなかった（未確認＝使用実績なしであり、禁止ではない）。
- マージコミット（`Merge pull request #NNN from ma-garin/<branch>`）はPRベースの運用を示す。

## 16. ブランチ運用

- ブランチ命名は `<type>/<説明>` 形式。実例（PR履歴より）: `feat/multi-tenant-auth`, `fix/login-flow-order`, `refactor/tenant-auth-cleanup`, `chore/remove-design-docs`, `feat/initial-admin-credentials`, `feat/run-history-drop-tabs`。
- 変更はフェーズ／機能ブランチで実施し、`--no-ff`（マージコミットを必ず作る）で `main` へマージする。これは `git revert -m 1` によるロールバックを可能にするための意図的な選択であり、詳細は `WS2D-RL-001`（リリース手順書）§ロールバックを参照。
- PRベースでの運用（`Merge pull request #158` 等、連番のPR番号が確認できる＝158件以上のPRが作成・マージされた実績）。
- `main` 以外の長期生存ブランチ（`develop`・`release/*` 等）は存在しない。トランクベースに近い、機能ブランチ→即mainマージの単純な運用である。
- mainブランチは保護設定なし（ユーザー運用メモとして把握しているが、GitHub側の設定確認はリポジトリ管理者権限が必要であり本書執筆時点でのAPI確認は行っていない＝未確認）。

## 17. 静的解析の実行方法と CI での強制

`make lint`（`Makefile`）の中身:

```bash
venv/bin/ruff check src/ web/ app.py --fix
venv/bin/mypy src/ web/ app.py --ignore-missing-imports
python scripts/check_e2e_conventions.py
python scripts/check_fetch_error_handling.py --fail-on-missing
```

すなわち `make lint` は ruff・mypy に加え、E2Eテストの規約チェック（`check_e2e_conventions.py`）と fetch のエラー処理チェック（`check_fetch_error_handling.py`、P0-3対応）という2本の独自スクリプトも実行する。black は `make lint` には含まれておらず、`docs/specs/CONVENTIONS.md` §3 の品質ゲート手順で個別に `venv/bin/python -m black <変更ファイル>` を実行する必要がある（**既知の罠4**: 「black未適用のままpush（ruffは通る）」）。

**pre-commit hookが機械的に強制する範囲**（`.githooks/pre-commit`、実際のスクリプト内容を確認）は次の3点のみである。

1. Python構文チェック（`py_compile`）。
2. `make test` 相当のpytest L1/L2実行。
3. UIファイル変更時の `.ui-verified` マーカー・ハッシュ照合（2時間以内の有効期限）。

**つまり ruff・mypy・bandit・black は pre-commit では強制されない。** コミット前に開発者（人間・AIエージェント）が手動で `make lint` と `make security` を実行する必要がある。この事実は品質保証計画書（`WS2D-QA-001`）§3にも明記し、ゲートの「自動」と「手動」の境界を偽らない。

## 18. レビュー観点チェックリスト

コードレビュー（人間・`code-reviewer` エージェントいずれも）で確認する観点:

- [ ] 機能整合性: 実行パス（UI→API→backend route→service/core→出力→永続化→エラー処理→利用者可視の証跡）が実際に動くことを確認したか（`.claude/rules/functional-integrity.md`）。
- [ ] 新機能は `quality/feature_contracts.yml` に登録されているか（`scripts/quality_harness.py` の `_validate_all_modules_registered` が機械検証する）。
- [ ] critical/highリスク機能に `failure_modes` と `required_tests`（happy_path・error_path等）が定義されているか。
- [ ] 型ヒント・`from __future__ import annotations` があるか。
- [ ] docstringが日本語で書かれ、必要に応じて「主張境界」を明記しているか。
- [ ] frozen dataclass / tuple によるイミュータブルなデータ受け渡しになっているか。
- [ ] エラーを握りつぶさず、日本語の利用者向けメッセージとサーバ側ログの両方があるか。
- [ ] 秘密情報のハードコード・ログ出力がないか。
- [ ] 層分離（`web`→`src`の一方向依存）を破っていないか。
- [ ] コミットメッセージが `type: 説明` 形式で「なぜ」を含んでいるか。

## 19. 依存関係管理

- Python依存は `requirements.txt`（本番相当・実行に必須）と `requirements-dev.txt`（開発専用: pytest・black・ruff・mypy・bandit等）に分離する。
- playwrightは`1.44.0`固定（`docs/specs/spec-6-2_dependency_update_strategy.md`）。バージョン更新自体は本書の管轄外であり、`WS2D-RL-001`（リリース手順書）§5の判断基準・移行検証手順に従う。
- 依存の脆弱性監査は `make audit`（`pip_audit`。AutoRun実行時に生成される`output/.playwright_env`のnpm環境も対象）で行う。critical/highの脆弱性は`docs/security/`の記録に従って対応する（`Makefile`のauditターゲットのコメントより）。
- 新規の依存追加は最小限にする方針。実例: `src/diff/link_checker.py`のdocstringは「標準ライブラリ（urllib）のみで実装し、新規外部依存（requests等）は追加しない」と明記している。標準ライブラリで実現できる場合は依存を増やさない。
- フロントエンドのサードパーティ資産（`static/vendor/driver.js`, `static/vendor/mermaid`）はnpm経由ではなく同梱配布とし、`ASSET.md`にライセンスを記録する。CDN取得は行わない（オフライン完結の方針）。

## 20. AIエージェント向け追加規約

- `CLAUDE.md`（プロジェクトルート）が本規約群への入口（entrypoint）であり、`.claude/rules/functional-integrity.md`・`docs/process/functional-integrity-gate.md`・`docs/process/claude-entrypoint.md`・`quality/feature_contracts.yml`を実装・レビュー前に読むことを義務付けている。
- 実装完了を宣言する前に、可能な限り `python scripts/quality_harness.py` / `make test` / `make verify-ui` を実行する。実行できない場合は「未確認」と明記し、完了扱いにしない。
- AIエージェント（Claude・Codex等）が生成したコードも、本書§1〜18のすべての規約対象となる。「AIが書いたから」という理由での規約適用除外はない。
- 開発プロセスの失敗（規約違反の見落とし、品質ゲートのすり抜け等）が起きた場合は、`WS2D-QA-001`（品質保証計画書）§9が定める名前付きRCAフレームワーク（5 Whys/Fishbone/FMEA/CAPA/DoD update）を使う。フレームワーク名を伴わない場当たり的な反省は禁止する。
- AIエージェントが実装・レビュー・評価を「完了」と報告する際は、実際の実行パス（UI→API→backend route→service/core→出力→永続化→エラー処理→利用者可視の証跡）を検証したかどうかを明示する。検証していない場合は「未確認」と書き、「問題なし」「完了」と言い換えない。

## 改訂履歴

| 版 | 日付 | 内容 | 作成者 |
|---|---|---|---|
| 1.0 | 2026-07-16 | 新規作成 | 開発チーム |
| 2.0 | 2026-08-02 | 全面改訂。命名規則表・型ヒント方針・docstring規約・ファイル/関数サイズの実測基準・JS/CSS規約・コミットメッセージ実例・pre-commit強制範囲の明確化・依存関係管理・AIエージェント向け規約を追加し、250行以上に拡充 | 開発チーム |
