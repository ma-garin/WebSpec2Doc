# 保守運用手順書 — System 09 影響度分析

> 上位: `07-system-test.md`・`08-acceptance-test.md`

| ID | 項目 | 手順 |
|---|---|---|
| OPS-001 | 起動 | 既存アプリと同じ（`FLASK_TESTING=1 WEBSPEC2DOC_ALLOW_LOCAL=1 venv/bin/python app.py`）。追加の常駐は無い。分析はアプリ内のスレッドで動く |
| OPS-002 | データの場所 | テナントごとに `data/tenants/<slug>/impact/impact.db`（認証オフ時は `data/impact/impact.db`）。文書の作業ファイルは同じフォルダの `work/` |
| OPS-003 | バックアップ | アプリ停止中に `impact.db` と `impact.db-wal` を複製する。稼働中は `sqlite3 impact.db ".backup <先>"` |
| OPS-004 | 中断した分析の復旧 | 再起動後、その DB に最初にアクセスした時点で実行中だった分析は「中断」になり、変更要求は起票に戻る。画面から再分析する |
| OPS-005 | LLM の接続 | 既存の設定（WEBSPEC2DOC_LLM_BASE_URL / OPENAI_API_KEY）。埋め込みは WEBSPEC2DOC_EMBED_MODEL（未設定なら文字 n-gram に縮退）。対象システムの送信方針が優先される |
| OPS-006 | 精度の再測定 | `venv/bin/python scripts/impact_eval.py --mode rule`（縮退）／`--mode full`（接続時）。結果を設定画面の精度表示に反映する |
| OPS-007 | 現行データの移行 | 画面の対象システム一覧の「旧データを移行」または `POST /api/impact/v2/migrate`。冪等（2 回目は取り込まない） |
| OPS-008 | 監査ログ | 追記のみ（DB のトリガで更新・削除を拒否）。保存期間の削除はしない。書き出しは監査画面の CSV |
| OPS-009 | 変更の手順 | 要件の変更は `01-requirements.md` → 設計 → テストの順に直し、`trace-check.sh docs/lifecycle/system09-impact` を通してから実装する |
