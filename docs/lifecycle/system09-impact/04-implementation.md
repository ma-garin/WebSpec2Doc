# 実装記録 — System 09 影響度分析

> 上位: `03-detailed-design.md`。1 タスク＝1 論理変更。

| ID | 内容 | 対応 DD | ファイル |
|---|---|---|---|
| T-001 | データ層: SQLite・リポジトリ・役割・レポート・移行 | DD-001, DD-002, DD-003, DD-009, DD-010 | web/services/impact/db.py, repo/*.py, roles.py, report.py, migrate.py |
| T-002 | 分析の処理: 差分・候補（つながり／意味検索／LLM／語の一致）・リスク値・テスト選定・ジョブ・評価 | DD-004, DD-005, DD-011 | web/services/impact/engine/*.py, jobs.py, scripts/impact_eval.py, tests/fixtures/impact_eval*/ |
| T-003 | API v2 | DD-006, DD-007 | web/routes/impact_api.py, impact_api_cr.py, web/__init__.py |
| T-004 | 画面 | DD-008 | templates/impact_analysis.html, static/js/impact/{api,app,system,cr,graph}.js, static/css/impact.css |

## 結合で見つけて直した欠陥

| ID | severity | 内容 | 原因 | 修正 |
|---|---|---|---|---|
| DEF-001 | Critical | 対象システムを開くと「読み込み中」のまま止まる | system.js・cr.js が app.js より先に読まれ、共通部品 IM.ui が未定義 | 読み込み順を api → graph → app → system → cr に |
| DEF-002 | Major | 役割が常に閲覧者として扱われる | 画面が my_role を system の中から読んでいた（API は外側に返す） | 両方から読む |
| DEF-003 | Major | 見本のあと影響の一覧へ移らない（REQ-F-042 の操作 2 回以内を満たさない） | 見本作成後の遷移先が対象システム | 変更要求の影響タブへ移す |
| DEF-004 | Major | 1 行の書き換えが「追加＋削除」に分かれる | 分析の処理が独自に code で差分を作り、差し替えで code が変わる | repo の差分（本文の類似で対応づけ）を使う |
| DEF-005 | Major | 関係図に線が出ない・影響の詳細に変更箇所が出ない | 影響は変更を code で持ち、画面は id で探していた | code と id の両方で突き合わせ |
| DEF-006 | Major | 影響が全件 P1 になり優先度で区別できない | 既定の閾値 P1≥8 が「規則に触れる 3 × 条件変更 3 ＝ 9」を全て P1 にする | 既定を P1≥10・P2≥6 に（REQ-F-003 を改訂） |
| DEF-007 | Major | 影響の画面が横に大きくはみ出す（1440px で 2273px） | fieldset の legend に visually-hidden が効かない | legend の隠し方を個別に指定 |
| DEF-008 | Major | 認証オフでは承認が永久にできない | 利用者が local 1 人で、本人承認の禁止に必ず当たる | 認証オフの local だけ本人承認を許し、監査に明記 |
| DEF-009 | Minor | 確認の窓で Tab のフォーカスが窓の外へ出る | 閉じ込めの処理が無い | Tab / Shift+Tab を窓の中で循環 |
| DEF-010〜019 | Major/Minor | 画面検証（work/V2-ui.md）の DEF-001〜011 | API と画面の応答の形の食い違い、表示の整形漏れ | 修正し IT-013 で再発防止。ブラウザで再確認済み（監査の表示・横はみ出し・関係図の点・改修後レビュー） |
