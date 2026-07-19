# 第4弾 設計書 — 商用パッケージ（P1-3 / P1-8 / P1-7）

- 作成日: 2026-07-19
- ステータス: **実装完了**（レビュー指摘3点は自己判断で確定。下記「9. 確定した判断」参照）
- 対象: `docs/12_実務化施策ロードマップ.md` の P1-3・P1-8・P1-7
- 前提: 第3弾（PR #55）までが main へ統合済み。`src/mbt/` の成果物と `src/diff/` の比較基盤が利用できる
- 粒度方針: 実装モデルが本書のみで再現できるレベル（対象ファイル・データ形式・関数シグネチャ・受け入れ基準を明記）

## 0. なぜこの3件を同一弾にするか

- **P1-3** は第3弾の成果物（MBTモデル・手動手順書・テストデータ・観測結果）と既存のテスト実行結果を**束ねるだけ**で成立し、新規の技術検証を必要としない。最短で顧客提出物になる。
- **P1-8** は `src/diff/` に閉じ、レポート表示層のみ触る。P1-3 の証跡パックに「差分の重要度」を載せられるため相乗する。
- **P1-7** は API 層に閉じ、上記2件と衝突しない。並行実装が安全。

いずれも**外部ネットワークに依存しない**（Swagger UI は同梱、LLM 要約は任意で既定オフ）。

## 1. 主張境界（evidence-only 原則の適用）

本弾で追加する成果物が主張してよいことと、してはならないことを先に固定する。

| 機能 | 主張してよい | 主張してはならない |
|---|---|---|
| P1-3 証跡パック | 「いつ・どの環境で・何を実行し・結果がどうだったか」の記録 | 品質の合否、テストの十分性・網羅性 |
| P1-8 重要度 | ルールが付けたスコアと、その根拠となった変更種別 | 「この変更は安全／危険」という価値判断 |
| P1-8 無視ルール | 「利用者が指定したパターンを除外した」事実 | 除外分が無害であること |
| P1-7 API | 公開エンドポイントの入出力仕様 | 未実装エンドポイントの存在 |

各成果物のヘッダに主張境界を必ず明記する（第3弾の `claim_scope` と同じ方針）。

---

## 2. P1-3 検収・監査向けテスト実施証跡パック

### 2.1 目的

テスト実行結果・スクリーンショット・観点との対応・実行環境情報を、**検収提出用の1つの報告書**に自動整形する。現状これらは `output/<domain>/qa_process/` に個別ファイルとして散在し、提出のたびに人が集める必要がある。

### 2.2 入力（すべて既存の生成物）

| 材料 | ファイル | 使う情報 |
|---|---|---|
| テスト実行結果 | `qa_process/playwright_report.json` | ケースID・タイトル・結果・所要時間・エラー |
| 失敗分類 | `web/services/failure_classifier.py` の出力 | env_issue / test_rot / app_change の別 |
| 観点対応 | `qa_process/quality_viewpoints.json` | ケース ↔ 品質観点の対応 |
| 実行環境 | `qa_process/autorun.meta.json` | 実行日時・対象URL・ブラウザ・件数 |
| スクリーンショット | `output/<domain>/screenshots/*.png` | 画面の実測証跡 |
| 手動手順（第3弾） | `qa_process/manual_procedures.md` | 手動実施分の手順と証跡 |
| 監査ログ | `output/<domain>/audit.jsonl` | 遮断・操作の記録 |

材料が欠けている場合は**その欄を「未取得」と明記して出力する**（欠落を黙って埋めない）。

### 2.3 新規モジュール

`src/evidence/` を新設（`src/mbt/` と同じ粒度で分割し、各ファイル 400 行以内）。

```
src/evidence/__init__.py
src/evidence/pack_model.py      # 証跡パックのデータ構造組み立て（純関数）
src/evidence/pack_reporter.py   # Markdown / HTML 出力
```

**`pack_model.py`**

```python
EVIDENCE_CLAIM_SCOPE = "executed_record_only"

def build_evidence_pack(
    report: dict,              # playwright_report.json
    viewpoints: dict | None,   # quality_viewpoints.json
    meta: dict | None,         # autorun.meta.json
    classifications: list[dict] | None,  # failure_classifier の結果
    screenshots: dict[str, str] | None,  # page_id -> 相対パス
    manual_procedures: str | None,       # manual_procedures.md の本文
) -> dict:
    """検収提出用の証跡パックを組み立てる。欠落材料は "未取得" として保持する。"""
```

戻り値の構造:

```json
{
  "meta": {
    "generated_at": "2026-07-19T10:00:00+09:00",
    "target_url": "https://example.com",
    "browser": "chromium 1.44.0",
    "claim_scope": "executed_record_only",
    "missing_inputs": ["quality_viewpoints"]
  },
  "summary": {"total": 42, "passed": 40, "failed": 2, "skipped": 0, "duration_sec": 128},
  "cases": [
    {
      "case_id": "PW-0001",
      "title": "ログインできる",
      "result": "passed",
      "duration_sec": 3.2,
      "viewpoint_ids": ["QV-03"],
      "screenshot_path": "../screenshots/P001.png",
      "failure_category": "",
      "error_excerpt": ""
    }
  ],
  "environment": {"python": "3.12.13", "playwright": "1.44.0", "os": "..."},
  "manual_section": "…（manual_procedures.md 本文。無ければ空）",
  "audit_excerpt": [{"event": "mutation_blocked", "method": "POST", "url": "..."}]
}
```

**`pack_reporter.py`**

```python
def save_evidence_pack(pack: dict, out_dir: Path) -> dict[str, Path]:
    """evidence_pack.md と evidence_pack.html を出力する。"""
```

- HTML は既存の `src/generator/html_reporter.py` と同じスタイル方針（自己完結・外部CDN不使用）
- 先頭に主張境界の但し書きを固定文で出す:
  > 本書はテストを**実行した事実の記録**であり、品質の合否・テストの十分性を判定するものではない。
- スクリーンショットは相対パス参照（第3弾の手順書と同じ方式。実在するものだけ結び付ける）

### 2.4 配線

- `web/services/failure_classifier.py` の**出口**に整形層を置く（分類器自体は変更しない）
- 呼び出し: AutoRun のテスト実行完了後（`web/routes/auto_run.py` の `_execute_tests` 完了時）に生成
- 出力先: `output/<domain>/qa_process/evidence_pack.{md,html}`
- `job.outputs` に `evidence_pack_md` / `evidence_pack_html` を追加し、AutoRun の成果物一覧に表示（`static/js/autorun.js` の `AUTORUN_OUTPUT_LABELS` へ追加。カテゴリは「実行」）

### 2.5 受け入れ基準

- AC-1: 全材料が揃った状態で `build_evidence_pack` を呼ぶと、cases の件数が `playwright_report.json` の件数と一致する
- AC-2: `quality_viewpoints.json` が無い場合、`meta.missing_inputs` に `"quality_viewpoints"` が入り、各 case の `viewpoint_ids` は空配列になる（例外を投げない）
- AC-3: 生成された HTML/MD の先頭に主張境界の但し書きが必ず含まれる
- AC-4: 実在しないスクリーンショットパスは `screenshot_path` に入らない
- AC-5: 失敗ケースには `failure_category`（env_issue / test_rot / app_change）が入る

---

## 3. P1-8 差分の見せ方強化（誤検知フィルタ・重要度）

### 3.1 現状の土台

| 既存 | 内容 | 本弾での扱い |
|---|---|---|
| `src/diff/differ.py` | `FieldChange` / `PageChange` / `LinkChange` / `TitleChange` / `ApiChange` の構造化変更型と `compute_diff` | **変更しない**。スコアリングの入力として使う |
| `src/diff/impact_analyzer.py` | 変更 → 影響テストの対応付け | 重要度スコアの材料として参照 |
| `src/diff/screenshot_diff.py` | `compare_screenshots` によるピクセル差分率 | 比較ビューの数値ソースとして使う |

不足しているのは **(a) 重要度スコアと変更要約、(b) 無視ルールの前処理、(c) 比較ビュー**の3点。

### 3.2 (b) 無視ルール — 前処理として追加

新規 `src/diff/ignore_rules.py`（200行以内）。

```python
@dataclass(frozen=True)
class IgnoreRule:
    kind: str        # "selector" | "regex" | "field"
    pattern: str
    note: str = ""

def load_ignore_rules(path: Path) -> list[IgnoreRule]:
    """output/<domain>/diff_ignore.json を読む。無ければ空リスト。"""

def apply_ignore_rules(
    diff_result: DiffResult, rules: list[IgnoreRule]
) -> tuple[DiffResult, list[dict]]:
    """除外後のDiffResultと、除外された変更の記録を返す。元のDiffResultは変更しない。"""
```

- 設定ファイル: `output/<domain>/diff_ignore.json`

```json
{
  "rules": [
    {"kind": "regex", "pattern": "^\\d{4}/\\d{2}/\\d{2}$", "note": "日付表示"},
    {"kind": "selector", "pattern": "#visitor-counter", "note": "アクセスカウンタ"},
    {"kind": "field", "pattern": "csrf_token", "note": "トークン"}
  ]
}
```

- **除外は「捨てる」のではなく別枠に退避する**。レポートに「除外 N 件（ルール別内訳）」を必ず表示する。黙って消すと誤検知フィルタ自体が信用を失うため。
- 不変性: 入力の `DiffResult` は変更せず、新しいインスタンスを返す（コーディング規約の immutability に従う）

### 3.3 (a) 重要度スコアと変更要約 — ルールベースを既定に

新規 `src/diff/severity.py`（300行以内）。

```python
SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW = "high", "medium", "low"

def score_changes(diff_result: DiffResult, impacted: list[ImpactedTest]) -> list[dict]:
    """各変更に重要度と根拠を付ける。LLMは使わない。"""
```

スコアリング規則（決定的・説明可能であること。根拠を必ず併記）:

| 条件 | 重要度 | 根拠文言 |
|---|---|---|
| 画面の削除 / 入口ページの消失 | high | 到達できない画面が発生 |
| フォーム項目の削除、`required` の追加 | high | 入力できる値の範囲が狭まった |
| 既存テストが参照するロケータの変更 | high | 影響テスト N 件 |
| 遷移リンクの削除 | medium | 到達経路が減少 |
| 項目の `maxlength` 等の属性変更 | medium | 入力制約が変化 |
| タイトル・文言のみの変更 | low | 表示文言の変化 |
| 画面の追加 | low | 既存経路への影響なし |

- 変更要約は**テンプレート組み立て**（例: 「フォーム項目 3 件が削除、うち必須 1 件」）。
- OpenAI 設定時のみ LLM 要約に差し替え可能とするが、**既定はルールベース**。この環境では LLM を前提にできないため、LLM 経路が無くても全機能が成立すること。

### 3.4 (c) スクリーンショット比較ビュー

- `src/generator/diff_reporter.py` に、既存 `compare_screenshots` の結果を使う比較セクションを追加
- 表示: before / after を横並び、差分率（`tabular-nums`）、しきい値超過のみ既定展開
- 画像は相対パス参照。存在しない場合はその旨を表示（欠落を隠さない）

### 3.5 受け入れ基準

- AC-1: 無視ルール適用後、除外された変更が `excluded` として件数・ルール別内訳とともにレポートに現れる
- AC-2: 同一入力に対する `score_changes` の出力は常に同一（決定的）
- AC-3: 画面削除を含む差分では、その変更の重要度が `high` になり根拠文言が付く
- AC-4: OpenAI 未設定でも (a)(b)(c) すべてが動作する
- AC-5: `apply_ignore_rules` は入力の `DiffResult` を変更しない

---

## 4. P1-7 REST API 拡充と OpenAPI 公開

### 4.1 追加エンドポイント

既存の `web/routes/api_v1.py`（9ルート）に、スケジュールと通知設定の CRUD を追加する。実体は既存のファイル駆動設定に載せる。

| メソッド | パス | 対応する既存実装 |
|---|---|---|
| GET | `/api/v1/sites/<domain>/schedule` | `output/<domain>/schedule.json` を読む |
| PUT | `/api/v1/sites/<domain>/schedule` | 同ファイルを書く（`web/routes/schedule.py` の検証を再利用） |
| DELETE | `/api/v1/sites/<domain>/schedule` | 同ファイルを削除 |
| GET | `/api/v1/sites/<domain>/notifications` | 通知設定を読む |
| PUT | `/api/v1/sites/<domain>/notifications` | `notifier_config_from_mapping` で検証して書く |

- **認可**: スケジュール・通知の変更は管理者のみ。`web/routes/schedule.py` の `_schedule_admin_guard` と同等のガードを適用する
- **テナント分離**: 既存 API と同じく、リクエスト元のワークスペース配下の domain のみ操作可能
- 破壊的操作（DELETE / PUT）は監査ログ（`audit.jsonl`）へ記録する

### 4.2 OpenAPI 仕様の生成

新規 `web/services/openapi_spec.py`（400行以内）。

```python
def build_openapi_spec(app: Flask) -> dict:
    """登録済み api_v1 ルートから OpenAPI 3.0 ドキュメントを組み立てる。"""
```

- 方針: **apispec を追加せず、Flask の `url_map` から生成する**。依存を1つ増やすより、対象が `api_v1` の十数ルートに限られる現状では自前生成のほうが軽い。各ルートの docstring とデコレータで宣言したスキーマを読む。
  （※ apispec 採用も選択肢。レビューで指示があれば差し替える）
- エンドポイント: `GET /api/v1/openapi.json`
- **実装済みルートのみを列挙する**（主張境界: 未実装のエンドポイントを仕様に載せない）

### 4.3 Swagger UI 同梱

- CDN 不使用。`static/vendor/swagger-ui/` に配置し、`GET /api/v1/docs` で配信
- 取得方法は `scripts/` に固定バージョンの取得手順を置き、`requirements.txt` と同じくバージョン固定
- CSP・オフライン環境で動作すること（外部ホストへの参照を含まないこと）を E2E で検証

### 4.4 受け入れ基準

- AC-1: `GET /api/v1/openapi.json` が OpenAPI 3.0 として妥当（`openapi` / `info` / `paths` を持つ）
- AC-2: 仕様に列挙されたパスが、すべて実際に登録済みである（未実装パスが載らない）
- AC-3: 一般ユーザーが PUT/DELETE を呼ぶと 403 になる
- AC-4: 他ワークスペースの domain を指定すると 404 または 403 になる（存在を漏らさない）
- AC-5: `/api/v1/docs` が外部ネットワーク遮断下でも描画される
- AC-6: スケジュール PUT の内容が `output/<domain>/schedule.json` に反映され、スケジューラが次回実行に反映する

---

## 5. 対象ファイル一覧

**新規**

```
src/evidence/__init__.py
src/evidence/pack_model.py
src/evidence/pack_reporter.py
src/diff/ignore_rules.py
src/diff/severity.py
web/services/openapi_spec.py
static/vendor/swagger-ui/（同梱アセット）
tests/test_evidence_pack.py
tests/test_diff_ignore_rules.py
tests/test_diff_severity.py
tests/test_api_v1_schedule.py
tests/test_openapi_spec.py
tests/e2e/test_evidence_pack_e2e.py
tests/e2e/test_api_docs_e2e.py
```

**変更**

```
web/routes/auto_run.py          # 証跡パック生成の呼び出し（数行）
web/routes/api_v1.py            # schedule/notification CRUD・openapi.json・docs
src/generator/diff_reporter.py  # 重要度・除外内訳・スクショ比較セクション
static/js/autorun.js            # 成果物ラベル追加
docs/12_実務化施策ロードマップ.md  # 該当項目のステータス更新
CONTEXT.md / docs/DEVELOPMENT.md # 用語と構成の追記
```

800行ガードに抵触しないよう、`api_v1.py` が肥大する場合は `web/routes/api_v1_schedule.py` へ分割する。

## 6. テスト計画

1. **L1/L2**: 上記 `tests/test_*.py`。特に決定性（同一入力→同一出力）、欠落材料時の挙動、不変性、認可・テナント分離を固定する
2. **L3(E2E)**: 証跡パックが AutoRun 完了後に成果物として現れること、`/api/v1/docs` が外部通信なしで描画されること
3. `make test` → `make verify-ui` → スクリーンショット目視 → `./scripts/verify.sh`
4. CI: 本弾はコード変更のため全ジョブ（E2E 含む）が走る

## 7. 実装順序

1. P1-8 (b) 無視ルール → (a) 重要度 → (c) 比較ビュー（`src/diff/` に閉じる。単独で価値が出る）
2. P1-3 証跡パック（P1-8 の重要度を取り込めるよう後に置く）
3. P1-7 API・OpenAPI・Swagger UI 同梱（他と独立）

## 8. 非スコープ

- LLM による差分要約の本実装（設定時のみの任意経路に留める）
- SAML / SCIM（P2-5）
- 証跡パックの PDF 出力（既存 `pdf_reporter.py` の流用は次弾で検討）
- apispec 等の新規依存追加（4.2 の判断がレビューで覆る場合を除く）

## 9. 確定した判断（当初レビュー事項）

1. **OpenAPI 生成方式** → 自前生成を採用。対象が十数ルートで、本リポジトリは依存ピン管理が厳格（spec-6-2）なため依存を増やさない
2. **証跡パックの形式** → Markdown + HTML の2種。HTMLから印刷でPDF化できるため本弾はこれで足りる
3. **無視ルールの設定** → ファイル（`diff_ignore.json`）のみ。UI は次弾送り

## 10. 実装時に設計から変えた点

- **重要度の語彙**: 設計時の high/medium/low をやめ、既存 `differ.py` の
  `SEVERITY_BREAKING / WARNING / INFO` に統一した。並行する語彙を増やさないため。
- **Swagger UI の同梱**: 配布形態上、外部からアセットを取得できないため取りやめ。
  代わりに仕様をサーバ側でHTMLへ描き切る `openapi_docs.py` を用意した。
  JavaScript も外部ホストも使わないため、遮断環境で開ける要件はより強く満たす。
- **無視ルールの kind**: 差分モデルにCSSセレクタが無いため、`selector` は
  `FieldData.element_id` との一致として実装し、URL 正規表現の `url` を追加した。
