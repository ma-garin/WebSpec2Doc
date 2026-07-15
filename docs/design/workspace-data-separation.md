# 設計ドキュメント: ワークスペース別データ物理分離

> **注（2026-07-16 追記）**: 本 ADR で導入した軽量認証は、商用/共有サーバ向けの
> 認証・テナント分離実装（`docs/AUTH_TENANCY.md`、機能 `account_auth`/`tenant_isolation`）に
> 統合・置換された。本書は設計判断の履歴として保持する。

対象: WebSpec2Doc 本体（成果物・設定・DB のテナント分離）
作成日: 2026-07-16
状態: **設計のみ（本フェーズでは実装しない）**
前提: ADR-0004（利用者ログイン＋ワークスペース導入。データ分離は先送りと明記）

---

## 1. 背景と目的

ADR-0004 で利用者ログインとワークスペース選択を導入したが、成果物・履歴・DB は
全ワークスペースで共有されたままである。複数利用者・複数組織で運用する場合、
ワークスペースごとにデータを物理分離する必要が生じる。

本書はその**分離方式を設計として確定**し、次期実装の意思決定コストを下げることを
目的とする。**実装・テストは本フェーズの対象外**。着手時に本書を基に ADR を起こす。

VDD 観点: 現状は単一利用者運用が主で分離の価値が未発現のため、設計のみに留める
（`WEBSPEC2DOC_AUTH` 既定 OFF の現行運用を壊さない）。

## 2. 現状のデータ配置（棚卸し）

| データ | 現在の場所 | 形式 | 分離対象 |
|---|---|---|---|
| クロール成果物 | `output/{domain}/`（report.json / screens.md / forms.md / report.html / spec.xlsx / transition.mmd / screenshots/ / sessions/ / audit.jsonl） | ファイル | ○ |
| サイト認証セッション | `output/{domain}/auth.json` | ファイル | ○（機微） |
| 観点管理 | `instance/viewpoints.db` | SQLite | ○ |
| テスト設計設定 | `instance/test_design_settings.json` | JSON | ○ |
| 利用者・ワークスペース | `instance/auth/{users,tenants,memberships}.json` | JSON | －（既にテナント定義側） |
| secret_key | `instance/auth/secret.key` | ファイル | －（アプリ共通） |
| 観点テンプレート | `data/viewpoint_templates/*.json` | JSON | －（全テナント共有の参照データ） |
| API キー等 | `.env` | env | －（アプリ共通） |

分離対象は「クロール成果物（output/）」「観点 DB」「テスト設計設定」の 3 系統。

## 3. 解決の分離点（現状の結合箇所）

- **`web/config.py`**: `OUTPUT_DIR = Path("output")`, `VIEWPOINTS_DB`, `TEST_DESIGN_SETTINGS_FILE` の
  3 定数がグローバル固定。ここが唯一のパス解決の起点。
- **成果物アクセス**: 各 route（crawl / report / history / traceability / qa_process / auto_run）が
  `output/{domain}` を直接参照する。ドメインが主キー。
- **観点ストア**: `web/services/viewpoint_store.py` が `VIEWPOINTS_DB` を開く。
- **セッション**: 選択中ワークスペースは `session['tenant_id']`（`web/auth/session.py`）に既に保持済み。

→ 分離の要は「`web/config.py` のパス定数を**リクエストのテナントで解決する関数**へ置換」し、
各アクセス点をその関数経由にすること。

## 4. 分離方式の比較

### (A) パス名前空間化（推奨）
- 成果物: `output/{tenant_id}/{domain}/…`、設定: `instance/{tenant_id}/test_design_settings.json`
- 観点 DB: `instance/{tenant_id}/viewpoints.db`（テナントごとに SQLite ファイルを分ける）
- 長所: 実装が単純・既存のファイル/SQLite 構造をそのまま踏襲・バックアップ/削除がディレクトリ単位で完結・
  テナント間の物理境界が明快（情報漏洩リスク低）。
- 短所: 横断集計（全テナントの ROI 等）は集約処理が別途必要。

### (B) DB 行レベル tenant_id 列
- 観点 DB を単一のまま `tenant_id` 列で論理分離。成果物は依然ファイルなので (A) 併用が必要。
- 長所: 横断クエリが容易。
- 短所: 全クエリに tenant_id 条件の付与漏れ＝越境事故のリスク。成果物ファイルは別途分離が必要で
  二重管理になる。単一利用者ツール由来の SQLite には過剰。

### (C) instance 丸ごと分割 + シンボリックリンク等
- 運用が煩雑・移植性低。不採用。

**推奨 = (A) パス名前空間化。** ファイルベースの現構造と最も整合し、物理境界が明快で
削除・バックアップが単純。観点 DB もテナント単位ファイルとすることで越境事故を構造的に排除する。

## 5. 実装方針（次期・(A) 採用時の骨子）

1. `web/config.py` のパス定数を関数化:
   `output_dir_for(tenant_id)` / `viewpoints_db_for(tenant_id)` / `settings_file_for(tenant_id)`。
   `tenant_id` 未指定（認証 OFF）時は既定名（例 `default`）にフォールバックし現行と等価な単一空間にする。
2. 各 route はリクエスト解決した `tenant_id`（`current_tenant_id()`）を上記関数に渡す。
   薄いヘルパ `web/auth/tenant_paths.py` を新設して解決を一元化。
3. `viewpoint_store` はテナントごとに接続をキャッシュ（`{tenant_id: connection}`）。
4. **移行**: 既存の `output/*` と `instance/viewpoints.db` を既定テナント
   （`default`）配下へ移すマイグレーションスクリプト `scripts/migrate_to_tenant_layout.py` を用意。
   冪等・ドライラン対応。認証 OFF 環境は `default` 空間として無変更で動作継続。
5. **回帰防止**: 認証 OFF での全 E2E グリーン維持を受入条件にする。

## 6. 非対象（本フェーズで実施しない）

- 上記実装・テスト・マイグレーションの実行。
- テナント横断の集計 UI（ROI 等）の再設計。
- 既存 `session['tenant_id']` を用いたアクセス制御の厳密化（越境防止のミドルウェア）。

これらは実装着手時に **ADR-0005（仮）** を起こし、本書を実装仕様の基礎とする。

## 7. リスク

- パス関数化の適用漏れ（直接 `output/` を参照する箇所の取りこぼし）→ 実装時に
  `grep -rn "output/" web/ src/` で全参照点を洗い出しチェックリスト化する。
- 既存データのマイグレーション失敗 → ドライラン＋バックアップ必須、冪等設計。
- 認証 OFF 運用の回帰 → `default` テナントで現行と等価であることを E2E で担保。

## 8. 参照
- ADR-0004（`docs/adr/0004-app-user-auth-and-workspaces.md`）— 本書は 0004 の先送り事項の設計。
- `docs/design/auth-tenant-integration.md` — 認証・ワークスペースの実装済み範囲。
