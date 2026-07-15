# WS2D-IF-001 API / インターフェース設計書

- 版数: 1.0 / 作成日: 2026-07-16 / 準拠: IPA 共通フレーム（外部設計）
- **as-built**: 本一覧は `web/routes/*.py` から機械抽出（再生成コマンド末尾）。
- 総 Blueprint 17・総エンドポイント 112。全て同一オリジン（既定 127.0.0.1:8765）。

## 1. 共通仕様

- 認証: 既定は認証なし（localhost）。`WEBSPEC2DOC_AUTH` 有効時は `/auth/*` 以外に
  ガード（未ログイン→`/auth/login`、未選択→`/auth/tenants`）。
- 状態変更（POST/PUT/PATCH/DELETE）は Origin/Referer による CSRF ガード（同一オリジン）。
- 応答: 主に JSON。プレビュー/ダウンロードはファイル。エラーは `{"error": "..."}`。
- 外部公開 API は `api_v1`（`/sites/...`, `/healthz`）。

## 2. エンドポイント一覧（Blueprint 別）

### 外部公開 API `api_v1`（9）
- `GET /healthz` / `GET /sites` / `GET /sites/<domain>/report` /
  `GET /sites/<domain>/snapshots` / `GET /sites/<domain>/diff` /
  `POST /sites/<domain>/crawl` / `GET /jobs/<job_id>` /
  `GET /sites/<domain>/jobs` / `GET /sites/<domain>/test-cases`

### 利用者認証 `auth`（5）
- `GET/POST /auth/login` / `GET /auth/tenants` / `POST /auth/tenants/select` / `POST /auth/logout`

### 解析・クロール
- `discover`（2）: `POST /api/discover`, `POST /api/discover-stream`
- `crawl`（5）: `POST /run`, `POST /api/cancel`, `GET /api/live-screenshot`,
  `POST /api/reference-docs`, `GET /api/doc-fusion`
- `history`（5）: `GET /api/history`, `DELETE /api/site/<domain>`, `GET /api/snapshots`,
  `GET /api/snapshot-diff`, `GET /api/snapshot-comparison`
- `site`（1）: `GET /api/site`

### サイト認証 `login`（7）
- `POST /api/login/simple|scrape|submit`, `POST /api/login/record/start|complete|cancel`,
  `GET /api/login/record/status`

### AutoRun `auto_run`（10）
- `POST /api/autorun/start|cancel|approve|submit-input`,
  `GET /api/autorun/status|preview|report|live-screenshot|jobs`, `GET /api/history/runs`

### QA 生成・レポート
- `qa_process`（7）: `GET /api/qa-process/input|result|advanced`,
  `POST /api/qa-process/generate|generate-advanced`, `GET /api/testcases`, `GET /api/test-design`
- `report`（7）: `GET /preview|download|download-zip|open|api/result|api/coverage-heatmap`,
  `GET /api/report/<domain>/spec-ts`
- `review`（3）: `GET /review/cases|export`, `POST /review/update`

### 観点管理 `viewpoints`（34）
セット/バージョン/アイテム/割当/提案/テンプレ/ツリーの CRUD＋版管理。代表例:
- `GET/POST /api/viewpoint-sets`, `GET/PATCH/DELETE /api/viewpoint-sets/<set_id>`,
  `POST .../versions/<version>/publish|rollback`, `POST /api/viewpoint-items/bulk`,
  `GET /api/viewpoint-templates`, `POST .../templates/<key>/apply`,
  `GET /api/viewpoint-selection`（全 34 は再生成コマンド参照）

### その他
- `settings`（7）: `GET/POST /api/settings`, `.../test-connection|test-design|allow-local`
- `schedule`（4）: `GET/POST /schedule/config`, `POST /schedule/run-now`, `GET /schedule/status`
- `traceability`（2）: `GET /traceability/matrix|view`
- `usage`（2）: `GET /api/usage`, `GET /usage`
- `pages`（2）: `/`, `/<view_name>`（SPA 配信）

## 3. 再生成コマンド（as-built 検証）

```bash
python - <<'PY'
import re, pathlib
for f in sorted(pathlib.Path("web/routes").glob("*.py")):
    if f.stem == "__init__": continue
    for method, path in re.findall(r'@\w+\.(route|get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']', f.read_text()):
        print(f.stem, method.upper(), path)
PY
```
