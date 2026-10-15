# SPEC-4-2 MCP サーバー化（復元仕様の AI エージェント供給）

| 項目 | 値 |
|---|---|
| WBS | 4-2 |
| 優先度 / 見積 | P2（戦略） / 1sp |
| 依存 | なし（output/ 配下の既存成果物のみを読む） |
| 背景 | docs/11 §5 アイデアカタログ C1 — 評価◎（戦略的本命） |

## 1. 目的と背景

復元済み仕様（report.json・doc_fusion・遷移グラフ）の消費者を人間から AI コーディングエージェントへ広げる。Claude Code 等が「このレガシー画面の項目・バリデーション・遷移は？」を問い合わせながらリプレイス開発できるよう、既存の生成物を MCP tools として公開する**薄い read-only サーバー**を追加する。生成ロジックは一切持たず、`output/{domain}/` 配下の既存ファイルを読むだけの PoC 構成とする（docs/11 の「Flask API が既にあるため薄いラッパーで PoC 可能」に対応）。

**現状の実装状態（実装前に必ず確認すること）:**

- 済: HTTP API `web/routes/api_v1.py` — `/api/v1/sites`・`/sites/<domain>/report`・`/snapshots`・`/diff`・`/test-cases` を提供済み（MCP 化の参照実装。ドメイン検証は `web/validation._valid_domain`）
- 済: 読み取り対象の成果物 — `output/{domain}/report.json`（`generate_json_report`: meta＋screens[].forms/fields/test_conditions_detail/transitions/page_states/official_name）、`output/{domain}/doc_fusion.json` / `doc_fusion.md`（`src/generator/fusion_reporter.py::FUSION_JSON_NAME/FUSION_MD_NAME`）、`output/{domain}/transition.mmd`、`output/{domain}/snapshots/*.json`
- 済: 差分計算 `src/diff/differ.py::compute_diff` ＋ `src/diff/snapshot.py::load_snapshot`（api_v1.py の `/diff` と同じ再利用が可能）
- 未: MCP プロトコル対応の一切（Python MCP SDK は requirements.txt に無い）

## 2. 受け入れ条件（全て自動テストで検証すること）

- **AC-1**: `list_sites` ツールが output/ 配下の report.json を持つドメイン一覧（domain・target_url・crawled_at・screen_count）を返す（Given: report.json を置いた tmp output / When: ツール呼び出し / Then: メタ情報つき一覧）
- **AC-2**: `list_screens(domain)` / `get_screen(domain, page_id)` が画面一覧（page_id・url・title・official_name）と画面詳細（forms・fields・validation・page_states・transitions）を返す
- **AC-3**: `get_field_definitions(domain, page_id)` がフィールドの実測属性（required/maxlength/pattern 等）と evidence・confidence を欠落なく返す（evidence-only: confidence を削ぎ落とさない）
- **AC-4**: `get_transitions(domain)` が遷移エッジ一覧（from/to page_id）と transition.mmd の本文を返す
- **AC-5**: `get_doc_fusion(domain)` が doc_fusion.json の内容を返し、未実行のドメインでは「Doc Fusion 未実行」を明示するエラー応答（結果でっち上げ禁止）
- **AC-6**: `get_drift(domain)` が最新 2 スナップショットの差分（added/removed/field_changes/api_changes 件数と明細）を返し、スナップショット 2 件未満なら明示エラー
- **AC-7**: 不正な domain（`../` 等のパストラバーサル・不正文字）は全ツールで拒否され、output/ 外のファイルは一切読めない
- **AC-8**: 全ツールが read-only（ファイル書き込み・クロール起動・削除の手段を持たない）。サーバー起動が既存 CLI / Web UI / テストに影響しない（`mcp` パッケージ未導入環境でも既存テスト全件 PASS）

## 3. スコープ外

- MCP 経由のクロール起動・スケジュール操作などの書き込み系ツール（Phase 2。まず read-only で価値検証）
- HTTP/SSE トランスポート（Phase 1 は stdio のみ。リモート公開は認証設計が別途必要）
- 生成物が無い場合のオンデマンド生成（「クロール未実行」を案内するのみ）
- MCP resources / prompts の公開（tools のみ。resources 化は利用実績を見て判断）
- Flask API（api_v1.py）の変更・共通化リファクタ

## 4. 基本設計

### 4-1. 変更ファイル一覧

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 新規 | `mcp_server/__init__.py` `mcp_server/__main__.py` | パッケージ・起動口（`python -m mcp_server`） |
| 新規 | `mcp_server/server.py` | FastMCP 定義と @tool 登録（SDK 依存はこのファイルに閉じる） |
| 新規 | `mcp_server/tools.py` | ツール本体（純関数。SDK 非依存 — 単体テストはここを叩く） |
| 新規 | `requirements-mcp.txt` | `mcp` パッケージ（本体 requirements.txt には追加しない — AC-8） |
| 新規 | `tests/test_mcp_tools.py` | 単体テスト（§6-1。SDK 不要） |
| 新規 | `tests/test_mcp_server_integration.py` | SDK 経由の結合テスト（§6-2。`pytest.importorskip("mcp")`） |
| 変更 | `quality/feature_contracts.yml` | feature_id: `mcp_server` を追加 |
| 変更 | `Makefile` / `README.md` | `make mcp-serve` と Claude Code 登録例の追記 |

配置は web/ と並ぶ**最上位の入出力層**とする（層分離: `mcp_server/ → src/` の一方向 import のみ。web/ は import しない — ドメイン検証は tools.py 内に実装する）。

### 4-2. ツール一覧（データモデル）

| ツール | 引数 | 返却（JSON 直列化可能な dict） | 読み取り元 |
|---|---|---|---|
| `list_sites` | なし | `{sites: [{domain, target_url, crawled_at, screen_count}]}` | `output/*/report.json` の meta |
| `get_site_summary` | domain | report.json の meta ＋ 生成物の有無（doc_fusion/transition.mmd/snapshots 件数） | 同上 |
| `list_screens` | domain | `{screens: [{page_id, url, title, official_name?}]}` | report.json screens |
| `get_screen` | domain, page_id | screen dict 全体（forms/fields/test_conditions_detail/page_states/transitions） | 同上 |
| `get_field_definitions` | domain, page_id | `{fields: [...]}` — 実測属性＋evidence＋confidence | 同上 |
| `get_transitions` | domain | `{edges: [{from, to}], mermaid: "..."}` | screens[].transitions ＋ transition.mmd |
| `get_doc_fusion` | domain | doc_fusion.json の内容 | doc_fusion.json |
| `get_drift` | domain | DiffResult の dataclasses.asdict | snapshots/ 最新 2 件 → compute_diff |

### 4-3. 処理フロー

```text
python -m mcp_server（stdio トランスポート）
  mcp_server/server.py
    FastMCP("webspec2doc") に @mcp.tool() で 8 ツール登録
      └─ 各ツールは mcp_server/tools.py の同名純関数へ委譲
           ├─ _validate_domain(domain)            # 不正なら ToolInputError
           ├─ _site_dir(domain) → resolve() して OUTPUT_DIR 配下か検証
           └─ ファイル読取 / compute_diff（src/diff 再利用）
```

出力ルートは環境変数 `WEBSPEC2DOC_OUTPUT_DIR`（既定 `output`。web/config.py::OUTPUT_DIR と同値）。

## 5. 詳細設計

### 5-1. SDK の使い方（server.py）

公式 Python MCP SDK（PyPI `mcp`）の FastMCP を使う。SDK 依存はこのファイルだけに閉じる:

```python
from mcp.server.fastmcp import FastMCP

from mcp_server import tools

mcp = FastMCP("webspec2doc")

@mcp.tool()
def list_sites() -> dict:
    """クロール済みサイト一覧（復元仕様が存在するドメイン）を返す。"""
    return tools.list_sites()

# ... 8 ツール分同様 ...

def main() -> None:
    mcp.run()  # stdio

if __name__ == "__main__":
    main()
```

ツールの docstring は AI エージェントが読む説明文になるため、**何が返るか・どの引数に何を渡すか（domain は list_sites で得る、page_id は list_screens で得る）を日本語で具体的に書く**こと。

Claude Code への登録例（README に記載）:

```bash
claude mcp add webspec2doc -- /path/to/venv/bin/python -m mcp_server
```

### 5-2. エラー処理・サイズ制御（tools.py）

```python
class McpToolError(ValueError):
    """ツール呼び出しの利用者起因エラー（メッセージはそのままエージェントへ返す）。"""

_DOMAIN_RE = re.compile(r"^[a-z0-9.\-_:]{1,255}$", re.IGNORECASE)  # web/validation と同水準
MAX_RESPONSE_BYTES = 200_000  # get_screen 等の返却上限。超過時は要約と分割取得の案内
```

| 事象 | 振る舞い | エージェント可視 |
|---|---|---|
| domain 不正・パストラバーサル | McpToolError | 「不正なドメイン指定です」（AC-7） |
| report.json 不在 | McpToolError | 「クロール未実行です。CLI --format json で生成してください」 |
| doc_fusion 不在 | McpToolError | 「Doc Fusion 未実行です（--reference-doc 付きで再クロール）」（AC-5） |
| snapshots 2 件未満 | McpToolError | 「差分には 2 回以上のクロールが必要です」（AC-6） |
| JSON 破損 | McpToolError（詳細はサーバーログのみ） | 「report.json を読めませんでした」 |
| 返却が MAX_RESPONSE_BYTES 超 | 切らずにエラー化し、`get_screen`/`get_field_definitions` での分割取得を案内 | 案内文言 |

FastMCP は tool 内例外を isError 付き結果に変換するため、McpToolError のメッセージが唯一のユーザー可視情報になる。**メッセージに絶対パス・環境情報を含めない**（bandit / 情報漏えい対策）。

### 5-3. 既存コードとの接続点

- `src/diff/snapshot.py::load_snapshot` と `src/diff/differ.py::compute_diff` — `get_drift` が api_v1.py の `/diff`（L138-148）と同じ手順で再利用（sys.path 調整は `web/__init__.py` と同様に `mcp_server/__init__.py` で `src` を追加）
- `src/generator/fusion_reporter.py::FUSION_JSON_NAME`（"doc_fusion.json"）— ファイル名はこの定数を import して使う（文字列の重複定義をしない）
- `src/main.py::JSON_REPORT_FILE_NAME`（"report.json"）— 同上

## 6. テスト仕様

### 6-1. 単体テスト（tests/test_mcp_tools.py — SDK 不要・tmp_path に output を構築）

| テスト名 | 入力 | 期待値 | AC |
|---|---|---|---|
| test_list_sites_reads_meta | report.json 2 ドメイン分 | domain・crawled_at・screen_count 一致 | AC-1 |
| test_get_screen_returns_fields | フィールド付き report.json | maxlength/pattern/evidence/confidence が透過 | AC-2, 3 |
| test_get_transitions_edges_and_mermaid | transitions＋transition.mmd | edges と mermaid 本文 | AC-4 |
| test_doc_fusion_missing_is_explicit | doc_fusion.json 無し | McpToolError「未実行」 | AC-5 |
| test_get_drift_two_snapshots | snapshots 2 件（フィールド変更あり） | field_changes 非空 | AC-6 |
| test_get_drift_single_snapshot_error | snapshots 1 件 | McpToolError | AC-6 |
| test_domain_traversal_rejected | domain="../../etc" ほか不正 4 態 | McpToolError・output 外を読まない | AC-7 |
| test_broken_json_error | 壊れた report.json | McpToolError（絶対パス非含有） | 5-2 |
| test_response_size_cap | 巨大 screen | 分割取得の案内エラー | 5-2 |

### 6-2. 結合テスト（tests/test_mcp_server_integration.py）

先頭で `pytest.importorskip("mcp")`（CI unit ジョブに `mcp` が無くても落ちない — CONVENTIONS §4-3 と AC-8）。`mcp` の InMemory クライアント（`mcp.shared.memory` の create_connected_server_and_client_session 相当）で server.py の FastMCP に接続し、`list_tools` に 8 ツールが載ること・`call_tool("list_sites")` が JSON を返すこと・例外が isError になることを検証する。

### 6-3. 回帰確認

- `mcp` 未導入の venv で既存ユニット全件 PASS（import が既存経路に混入していないこと。AC-8）
- `python -m mcp_server` 起動→Ctrl-C 終了で output/ 配下に書き込みが発生しない（mtime 比較）

## 7. 完了チェックリスト（DoD）

- [ ] AC-1〜8 のテストが全て存在し PASS
- [ ] CONVENTIONS §3 の全ゲート通過（black/ruff/mypy/bandit/pytest/quality_harness — mypy は mcp_server/ も対象に含める）
- [ ] feature_contracts.yml に `mcp_server`（core_files: mcp_server/tools.py, mcp_server/server.py / failure_modes: invalid_domain, missing_report, missing_fusion, broken_json, oversized_response / required_tests: happy_path, error_path, traversal_path, evidence）
- [ ] 実行パス確認: 実際に `claude mcp add`（または MCP Inspector）で接続し、デモサイトのクロール結果に対して list_sites → list_screens → get_field_definitions の 3 段を対話実行して目視確認。実行できない環境なら「未確認」と報告
- [ ] README / Makefile に導入・登録手順（requirements-mcp.txt・claude mcp add）が載っている

## 8. このタスク固有の罠

- **パッケージ名を `mcp/` にしない**。SDK のトップレベルパッケージ名が `mcp` のため、リポジトリ直下に同名ディレクトリを作ると import が自分自身を差してサーバーが起動しなくなる（sys.path 先頭はカレント）。必ず `mcp_server/` とする
- **stdio トランスポートでは stdout に print しない**。stdout は JSON-RPC のワイヤそのもの。ログは logging（stderr）へ。既存コードの `sys.stdout.write("CRAWL_EVENT:...")` 系の癖を持ち込むとプロトコルが壊れる
- FastMCP のツール返却は JSON 直列化可能であること。`compute_diff` の DiffResult は frozen dataclass ネストなので `dataclasses.asdict` を通す（api_v1.py L148 と同じ）。FieldData 等を生で返すと直列化エラー
- domain 検証を「output/ 配下に実在するディレクトリか」だけで済ませない。`Path(output_dir, domain).resolve()` 後に `is_relative_to(output_dir.resolve())` を必ず確認（シンボリックリンク経由の脱出対策）
- `mcp` パッケージは Python 3.10+ が必要で本リポジトリの 3.11〜3.12 制約とは両立するが、**requirements.txt に直接足すと CI unit ジョブ（venv なし環境）の前提が変わる**。requirements-mcp.txt 分離と importorskip を崩さない
