# SPEC-4-3 API 仕様復元（XHR/fetch 観測 → OpenAPI 3.1 推定生成）

| 項目 | 値 |
|---|---|
| WBS | 4-3 |
| 優先度 / 見積 | P2 / 2sp |
| 依存 | なし（4-2 MCP と将来連結すると価値増） |
| 背景 | docs/11 §5 アイデアカタログ B1 — 評価◎（リプレイス案件の武器。HAR→OpenAPI 変換単体ツールは存在するが「UI 仕様と API 仕様を紐づけて同時納品」は空白地帯） |

## 1. 目的と背景

クロール中に傍受した XHR/fetch の観測を拡張し、OpenAPI 3.1 スキーマの推定生成と UI 画面との紐づけを行う。既存の傍受基盤（NetworkCapture）は method・path・status・content_type・レスポンス JSON のトップレベルキーまでを記録しており、API 仕様書として納品するにはクエリパラメータ・リクエスト内容・レスポンス構造（型）・path パラメータ化が足りない。観測を深掘りして `openapi.json` を生成し、各 operation に「どの画面から呼ばれたか」（page_id）を拡張フィールドで付与する。

**現状の実装状態（実装前に必ず確認すること）:**

- 済: `src/crawler/network_interceptor.py::NetworkCapture` — response イベント傍受。静的拡張子除外（STATIC_EXTENSIONS）、JSON/form 以外の 2xx 除外、`ApiEndpoint(method, path, status_code, content_type, sample_fields)` を method+path+status で重複除去（`finalize`）。レスポンスボディは 32KB 上限・トップレベルキー最大 20 件のみ（`_extract_response_fields`）
- 済: `src/crawler/page_crawler.py` — crawl_page 内で attach/detach（L549-600）、`PageData.api_calls: tuple[ApiEndpoint, ...]` に画面単位で格納（＝**UI 紐づけの原資は既にある**）
- 済: `src/generator/architecture_generator.py::merge_api_endpoints` — 全ページの ApiEndpoint を method+path で統合し architecture.mmd に出力
- 済: `src/diff/differ.py::_api_changes` — API の追加/削除/変更ドリフト検出（path 単位）
- 済: `MutationBlocker` — POST/PUT/DELETE/PATCH を既定遮断し `blocked: list[(method, url)]` に記録（`WEBSPEC2DOC_ALLOW_MUTATION=1` で解除）
- 未: クエリパラメータ・リクエストボディの観測、レスポンス構造の型推定（トップレベルキー名のみで型が無い）、path パラメータ化（`/users/123` → `/users/{id}`）、OpenAPI 出力、report.json/成果物への画面×API 対応表
- 未: デモサイトに JSON API が無い（`demo/site/*.html` に fetch なし・`demo/demo_site.py` は静的配信のみ）— E2E 用に追加が必要

## 2. 受け入れ条件（全て自動テストで検証すること）

- **AC-1**: クエリパラメータ名が観測される（Given: `/api/items?page=2&sort=name` への fetch / When: crawl_page / Then: ApiEndpoint に `query_params=("page","sort")`。**値は記録しない** — PII 対策）
- **AC-2**: JSON レスポンスの構造が型として推定される（`{"items":[{"id":1,"name":"a"}],"total":2}` → object/array/integer/string の型ツリー。深さ 2 まで・**値そのものは保存しない**）
- **AC-3**: 数値・UUID セグメントを持つ path が `{id}` にパラメータ化され、`/api/products/1` と `/api/products/2` が 1 operation に統合される（元 path は観測例として保持）
- **AC-4**: `--format openapi` で `output/{domain}/openapi.json` が生成され、OpenAPI 3.1（`"openapi": "3.1.0"`）として妥当（必須キー info/paths、operation に parameters/responses）
- **AC-5**: 各 operation に UI 紐づけ拡張 `x-webspec2doc-screens: [page_id, ...]`（その API を呼んだ画面）と観測メタ `x-webspec2doc-observed`（観測回数・観測ステータス一覧・crawled_at）が付く
- **AC-6**: 推定であることが成果物上で区別される — サンプル由来の型には `description` に「実測サンプルからの推定」、**required は断定せず出力しない**。MutationBlocker が遮断した mutation は `x-webspec2doc-observed.blocked: true` の operation スタブ（未実測明示）として載る
- **AC-7**: report.json のスキーマ・report_hash・既存スナップショット互換が変化しない（ApiEndpoint への追加フィールドは既定値付き＝旧スナップショット読込可。openapi は独立ファイル）
- **AC-8**: 実ブラウザ E2E: デモサイト新設ページの fetch（一覧＋詳細 2 件＋クエリ付き検索）から openapi.json が生成され、AC-1〜5 を満たす

## 3. スコープ外

- リクエスト/レスポンスの**値**の保存（HAR 相当の生ログ化はしない。キー名と型のみ — パッシブかつ PII 最小化）
- 認証方式（securitySchemes）の推定（Authorization ヘッダの有無記録すら Phase 2）
- mutation の能動的な送信による観測拡充（MutationBlocker の既定は変えない。`WEBSPEC2DOC_ALLOW_MUTATION=1` 環境ではリクエストボディのキー名まで観測するが、既定環境の挙動は不変）
- OpenAPI YAML 出力・$ref による components 共通化（Phase 2。まず inline schema）
- GraphQL / WebSocket / gRPC-web（対象は HTTP+JSON の XHR/fetch のみ）

## 4. 基本設計

### 4-1. 変更ファイル一覧

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 変更 | `src/crawler/page_crawler.py` | `ApiEndpoint` に既定値付きフィールド追加（§4-2） |
| 変更 | `src/crawler/network_interceptor.py` | `_record` の観測拡張（query/request/型推定）、`finalize` の重複除去キー維持 |
| 新規 | `src/analyzer/api_spec.py` | path パラメータ化・observation 統合（ApiOperation 組み立て） |
| 新規 | `src/generator/openapi_generator.py` | ApiOperation → OpenAPI 3.1 dict → openapi.json |
| 変更 | `src/main.py` | `SUPPORTED_FORMATS` に "openapi" 追加・`save_outputs` に出力分岐追加 |
| 変更 | `src/diff/snapshot.py` 系 | 変更なしが原則（追加フィールドは既定値で吸収されることをテストで保証） |
| 新規 | `demo/site/api_demo.html`・変更 `demo/demo_site.py` | fetch 3 種（一覧/詳細×2/クエリ検索）と JSON ハンドラ `/api/products`・`/api/products/<n>` |
| 新規 | `tests/test_api_spec.py`・`tests/test_openapi_generator.py` | 単体テスト（§6-1） |
| 新規 | `tests/e2e/test_api_recovery_e2e.py` | 実ブラウザ E2E（§6-2・ポート 8899） |
| 変更 | `quality/feature_contracts.yml` | feature_id: `api_spec_recovery` を追加 |

### 4-2. データモデル

```python
# src/crawler/page_crawler.py — ApiEndpoint 拡張（全て既定値付き = スナップショット後方互換）
@dataclass(frozen=True)
class ApiEndpoint:
    method: str
    path: str
    status_code: int
    content_type: str
    sample_fields: tuple[str, ...]
    # ---- SPEC-4-3 追加（既定値付き・値は保存しない）----
    query_params: tuple[str, ...] = ()        # クエリパラメータ名（昇順・重複除去）
    request_content_type: str = ""            # リクエストの content-type
    request_fields: tuple[str, ...] = ()      # リクエスト JSON/form のトップレベルキー名
    response_schema_json: str = ""            # 型ツリーの JSON 文字列（frozen 制約のため str。sort_keys=True）

# src/analyzer/api_spec.py — 統合後の operation
@dataclass(frozen=True)
class ApiOperation:
    method: str
    path_template: str                        # "/api/products/{id}"
    path_params: tuple[str, ...]              # ("id",)
    query_params: tuple[str, ...]
    request_content_type: str
    request_fields: tuple[str, ...]
    responses: tuple[tuple[int, str], ...]    # (status, response_schema_json)
    screen_ids: tuple[str, ...]               # 呼び出し元 page_id（UI 紐づけ）
    observed_paths: tuple[str, ...]           # 実測 path の例（最大 3 件）
    observation_count: int
    blocked: bool = False                     # MutationBlocker 遮断由来（未実測）
```

### 4-3. 処理フロー

```text
crawl_page                                    # 既存位置（page_crawler.py L549-600）
  NetworkCapture._record（拡張）
    ├─ urlparse(url).query → parse_qs のキー名のみ → query_params
    ├─ response.request.post_data / headers["content-type"] → request_fields（JSON/form のキー名のみ）
    └─ _infer_schema(body) → 型ツリー（深さ 2・array は先頭要素のみ・値破棄）
  MutationBlocker.blocked → crawl_page が blocked 分を ApiEndpoint(status_code=0, ...) として api_calls に追加はしない
                            （PageData 互換維持のため blocked は保存せず、openapi 生成時に再収集 — §5-3）

save_outputs（"openapi" in formats）
  analyzer.api_spec.build_operations(pages)   # pages[].page_data.api_calls を統合
    ├─ parameterize_path("/api/products/1") → "/api/products/{id}"
    ├─ (method, path_template) でグループ化・responses/screens/query を合算
    └─ ApiOperation 一覧
  generator.openapi_generator.generate_openapi(operations, target_url, crawled_at)
    └─ output/{domain}/openapi.json
```

## 5. 詳細設計

### 5-1. 観測の拡張（network_interceptor.py）

- `_record` の除外規則（STATIC_EXTENSIONS・非 JSON/form 2xx 除外）は**変更しない**（既存の api_calls 内容が変わると report/architecture の回帰になる）
- query: `parse_qs(parsed.query, keep_blank_values=True)` のキーを sorted tuple 化。値は即破棄
- request: `response.request.post_data` は例外を握って None 許容（Playwright はバイナリ等で例外）。content-type が json なら `json.loads` キー名、`application/x-www-form-urlencoded` なら `parse_qs` キー名。**既定環境では mutation が遮断されるため観測されるのは主に GET**（この非対称は openapi の description に明記する — AC-6）
- `_infer_schema(data, depth=2)`: dict → `{"type":"object","properties":{k: 再帰}}`、list → `{"type":"array","items": 先頭要素の再帰}`（空なら items 省略）、str/bool/int/float/None → 対応する JSON Schema type（int は "integer"、None は `{"type":"null"}` — 3.1 では null 型が正式）。深さ超過は `{}`（任意）。プロパティ数上限 30
- `finalize` の重複除去キーは (method, path, status) のまま。同一キーで観測が複数回来た場合、query_params / request_fields は**和集合**、response_schema_json は最初の非空を採用（サンプル 1 件主義 — 推定を「複数サンプルの合成」に見せない）

### 5-2. path パラメータ化（analyzer/api_spec.py）

```python
_NUM_RE = re.compile(r"^\d+$")
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

def parameterize_path(path: str) -> tuple[str, tuple[str, ...]]:
    """数値・UUID セグメントを {id}/{id2}... に置換し、テンプレートとパラメータ名を返す。"""
```

- 置換は数値・UUID のみ（過剰一般化しない。`/api/v1/...` の "v1" を潰さないため英数混在は対象外）
- 統合キーは `(method, path_template)`。observed_paths に元 path を最大 3 件保持（根拠の提示）
- screen_ids: `AnalyzedPage.page_id` を利用（pages を舐めて api_calls を含む画面を逆引き）

### 5-3. OpenAPI 3.1 出力（generator/openapi_generator.py）

```json
{
  "openapi": "3.1.0",
  "info": {"title": "<domain> 復元 API 仕様（実測由来）", "version": "<crawled_at>",
           "description": "クロール中に観測した XHR/fetch からの推定。値は記録せずキー名と型のみ。POST 等は既定で遮断されるため未実測の場合がある。"},
  "paths": {
    "/api/products/{id}": {
      "get": {
        "parameters": [{"name": "id", "in": "path", "required": true, "schema": {}},
                        {"name": "sort", "in": "query", "required": false, "schema": {}}],
        "responses": {"200": {"description": "実測サンプルからの推定",
                               "content": {"application/json": {"schema": { ...型ツリー... }}}}},
        "x-webspec2doc-screens": ["P001"],
        "x-webspec2doc-observed": {"count": 3, "statuses": [200], "paths": ["/api/products/1"], "blocked": false}
      }
    }
  }
}
```

- required（クエリ・request body のプロパティ）は**一切出力しない**（観測 1 回では必須性を断定できない — AC-6 / evidence-only）
- blocked な mutation: crawl 側では保存しないため、openapi 生成時のみ `MutationBlocker.blocked` を crawl_page から `save_outputs` へ**運ばない**設計とした（PageData 不変）。代わりに Phase 1 では「blocked 情報は audit ログ経由」とし、`append_audit_log` の `mutation_blocked` イベント（既存 crawl 契約の failure_modes に mutation_blocked あり）を openapi 生成時に読み取れる場合のみスタブ化する。読み取れなければスタブなし（無いものを出さない）
- 出力は `json.dumps(..., ensure_ascii=False, indent=2, sort_keys=True)`（docs-as-code 差分安定）

### 5-4. エラー処理表

| 事象 | 振る舞い | ユーザー可視 |
|---|---|---|
| post_data 取得例外・バイナリ | request_fields=() で続行 | なし（debug ログ） |
| レスポンス JSON パース失敗 | response_schema_json=""（既存 sample_fields と同じ振る舞い） | なし |
| api_calls が全画面で空 | openapi.json を**生成しない**・info ログ「観測 API なし」 | ログ |
| 旧スナップショット（追加フィールド無し）読込 | 既定値で復元・diff が誤検知しない | なし |

### 5-5. 既存コードとの接続点

- `page_crawler.py::crawl_page` L549-600 — attach/detach 位置は不変。ApiEndpoint 生成は `NetworkCapture.finalize` 内のみ
- `architecture_generator.merge_api_endpoints`（L89）— キー (method, path) のまま動くこと（追加フィールドは無視される）をテストで保証
- `diff/differ.py::_api_modified`（method/status のみ比較）— 挙動不変。query/schema の差分検出は Phase 2
- `src/main.py::_parse_formats`／`SUPPORTED_FORMATS`（L45, L825）— "openapi" 追加。`--format json,openapi` 併用可

## 6. テスト仕様

### 6-1. 単体テスト

| テスト名 | 入力 | 期待値 | AC |
|---|---|---|---|
| test_query_param_names_only | フェイク Response（?page=2&sort=name） | query_params=("page","sort")・値非保存 | AC-1 |
| test_schema_inference_depth2 | ネスト JSON | object/array/integer/string の型ツリー・深さ 2 で打ち切り | AC-2 |
| test_schema_no_values | 個人情報風の値を含む JSON | response_schema_json に値文字列が一切含まれない | AC-2 |
| test_parameterize_numeric_and_uuid | /api/products/1, /users/<uuid>/orders | {id} 置換・"v1" は不変 | AC-3 |
| test_operations_merged_across_pages | 2 画面から同一 API | 1 operation・screen_ids に両 page_id | AC-3, 5 |
| test_openapi_31_structure | ApiOperation 2 件 | openapi=3.1.0・parameters/responses/x- 拡張 | AC-4, 5 |
| test_required_never_emitted | 全種 operation | 出力 JSON に `"required"` が path パラメータ以外に現れない | AC-6 |
| test_old_snapshot_loads | 追加フィールド無しのスナップショット JSON | ApiEndpoint 既定値で復元・compute_diff 誤検知なし | AC-7 |
| test_report_hash_unchanged | 既存ページ相当 | generate_json_report 出力不変 | AC-7 |
| test_no_api_no_file | api_calls 空 | openapi.json 非生成 | 5-4 |

フェイクは `network_interceptor` の `_record` に渡す Response 相当を `tests/test_capture.py::_FakeRecorderPage` に倣って自作する（url/headers/body/request.method/request.post_data を注入可能に）。

### 6-2. 実ブラウザ E2E（tests/e2e/test_api_recovery_e2e.py・専用スレッドパターン必須・ポート 8899）

デモサイトに追加: `api_demo.html`（読み込み時に `fetch("/api/products")`・`fetch("/api/products/1")`・`fetch("/api/products/2")`・ボタンで `fetch("/api/products?sort=name&page=1")`）。`demo/demo_site.py` に JSON ハンドラを追加（配列＋オブジェクト応答）。

| テスト名 | 検証 | AC |
|---|---|---|
| test_openapi_generated_from_demo | crawl(api_demo) → openapi.json 生成・/api/products と /api/products/{id} の 2 path | AC-3, 4, 8 |
| test_query_and_screens_recorded | sort/page が parameters に・x-webspec2doc-screens に api_demo の page_id | AC-1, 5, 8 |
| test_response_schema_types | products 応答の型ツリー（array→object→integer/string） | AC-2, 8 |

### 6-3. 回帰確認

- 既存ユニット全件・実ブラウザ E2E・`docs/demo/sample_output/report.json` 比較（AC-7）
- architecture.mmd の出力が api_demo 追加分以外で不変

## 7. 完了チェックリスト（DoD）

- [ ] AC-1〜8 のテストが全て存在し PASS
- [ ] CONVENTIONS §3 の全ゲート通過（black/ruff/mypy/bandit/pytest/quality_harness）
- [ ] feature_contracts.yml に `api_spec_recovery`（core_files: network_interceptor.py, analyzer/api_spec.py, generator/openapi_generator.py / failure_modes: binary_body, broken_json, no_observation, legacy_snapshot / required_tests: happy_path, error_path, privacy_path, evidence）
- [ ] デモサイト新ページが `make demo` で表示され API が応答する
- [ ] 実行パス確認: CLI `--format json,openapi` で api_demo をクロールし、openapi.json を Swagger Editor 等（またはスキーマバリデータ）に通して目視確認。通せない環境なら「未確認」と報告

## 8. このタスク固有の罠

- **response イベントは crawl_page の attach 中しか拾えない**。SPA の遅延 fetch（タイマー・ユーザー操作後）は `explore_page_actions` 実行中に発火する分だけが観測される。「観測できた範囲の仕様」であることを info/description で常に明示する（網羅と誤認させない）
- `response.body()` は既に `_extract_response_fields` が呼んでいる。**型推定で二重に body() を呼ばない**（Playwright はレスポンスごとに取得コストがある＆detach 後は取得不能）。1 回読んで sample_fields と schema の両方を作る構造に直す
- frozen dataclass に dict を持たせられないため型ツリーは JSON 文字列で保持（CONVENTIONS §4-10）。`sort_keys=True` で正規化しないと同一スキーマが別文字列になり重複除去・diff が壊れる
- ApiEndpoint のフィールド追加は**必ず末尾・既定値付き**。位置引数で生成している既存箇所（network_interceptor.py L170-176 はキーワード引数なので安全）を grep で確認してから追加する
- demo_site.py への JSON ハンドラ追加は、既存デモページのクロール結果（screen_count・report_hash 検証をしている既存テスト）に影響しないよう、`api_demo.html` を他ページからリンクしない独立ページにする（クロール起点で明示指定した時のみ到達）
- ポートは 8899 を使用（8765/8766/8894/8896/8898 は使用済み — CONVENTIONS §4-7・SPEC-3-1）
