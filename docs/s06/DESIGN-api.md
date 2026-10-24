# S06 対検査レビュー API 設計（W2）

契約: docs/s06/CONTRACT.md。指揮官決定（2026-10-24）: iid は `[a-z0-9-]{3,64}`、起票者 = 最初に findings を読んだ認証済み利用者（trail の review_started）、認証オフの承認は 403。

## 構成
| 層 | ファイル | 役割 |
|---|---|---|
| ルート | web/routes/doc_verify_pair.py | 入力取り出し・エラー形式 |
| 業務 | web/services/docverify/pair_review.py | 保存・判定・証跡・承認 |
| 既存接続 | pair/engine.inspect | POST /analyze から呼ぶ |
| 登録 | web/routes/doc_verify.py 末尾 | 暫定（CR S06-1） |

## 業務フロー
画面 → `/api/docverify/<iid>/pair/*` → doc_verify_pair の各関数 → pair_review.* → `<data>/docverify/<iid>/pair/{findings,decisions,trail}.json` に原子的書き込み（tempfile + os.replace、fcntl ロック）→ JSON 応答。失敗は `{error:{code,message}}`、message は日本語＋次の行動。

## 規則
- 保存先: `scoped_output_dir(config.DATA_DIR)/docverify/<iid>/pair/`（テナント有効時は tenants/<t>/ 配下）。既存 store の iid 検証は変えない。
- 採否: decisions.json に追記のみ。取消は `revoke: true` の行を追記し、指摘の status は decisions の再生で決める（取消し切ったら取り込み時の status＝initial_status に戻る）。findings.json は再生結果で上書き。
- rev = decisions.json の件数。body に rev があり不一致なら 409。無ければ検査しない。
- 判定: unresolved_critical = 重大 かつ 不採用以外／needs_review = 要確認／unverified = 未判定（合否に影響しない）／missing_links = 要件の REQ ID（範囲表記を展開）で基本設計書に現れないもの。pass = 前 3 つが 0。changed は changed_in_current の指摘と、meta.changed_sections.requirements の節だけで計算。
- 承認: 認証オフ（利用者 `_none`）→403 auth_required、理由空→400、未合格→403 gate_not_passed、起票者未記録→403 no_author、起票者と同一→403 same_person、通れば trail に approved。
- 起票者: GET /findings を認証済み利用者が最初に開いたとき review_started を追記（`_seed`・`_none` は起票者に数えない）。
- 利用者: web.auth.auth_enabled() と g.auth_user（settings.current_user 経由）。web/auth.py は編集しない。

## 変えない点
既存 inspection.json・store の iid 規則・web/__init__.py・web/auth.py。
