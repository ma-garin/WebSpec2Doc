# System06 Document Assurance — 構成と分類（2026-10-21 時点）

既存実測: `web/services/docverify/` 約 4,900 行・`web/routes/doc_verify*.py` 6 本・保存は **JSON ファイル**（テナント別 `docverify/<iid>/inspection.json`。DB なし）・テストは `tests/test_docverify_*.py` 10 本。

## 既存の分類
| 対象 | 分類 | 理由 |
|---|---|---|
| store.py / perm.py / audit.py | KEEP | 版管理・権限・監査は流用。保存形式は変えない |
| checks.py / pair/*（矛盾・用語・リンク） | EXTEND | 新エンジンの比較基準。既存出力は変えない |
| process.py / setcheck.py / trace.py | KEEP | 既存レビュー工程・組検査・追跡 |
| llm_assist.py / llm_settings.py | EXTEND | provider 共通口（LLMClient）を Review Board が再利用 |
| doc_verify*.py（ルート） | KEEP | 追加は新 blueprint `doc_assure.py`（`/api/docassure/*`） |
| 新規 `web/services/docassure/` | NEW | 付加のみ。サイドカー `docverify/<iid>/assurance.json`（旧データに影響なし） |

## 新パッケージ（`web/services/docassure/`）
model / requirement_engine / rules（データ駆動 pack） / units・conflict・glossary / testability・quality・completeness・boundary・readiness / pipeline（統括） / store（サイドカー）。

## 真実規律
出所 OBSERVED/DERIVED/INFERRED、状態 CANDIDATE…。指摘 0 件を 100 点にしない（評価不能は `None`）。矛盾は truth=UNKNOWN。

## 優先度
P0（本 PR 群）: model・要件単位・ルール・品質・テスト可能性・矛盾・準備判定・API。
P1: 意味矛盾(AI)・Review Board・意味 diff・System01/02/09 連携・Trace Graph GUI。 P2: 傾向・フィードバック学習・組織 policy。
