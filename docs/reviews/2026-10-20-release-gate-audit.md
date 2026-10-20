# 商用リリース前監査（2026-10-20）

判定: **READY_FOR_FINAL_GATE**（P0=0・P1=0）。製品ライセンスの決定だけは保守者・法務の判断待ちで、このゲートの対象外とする。

範囲は No-op Gate の残り。Ghidra（#305）・D-P0-3（#306）・Wave2〜5 の確認済み画面は監査していない。

## 修正した P1

| # | 項目 | Before | After | 確認 |
|---|---|---|---|---|
| 1 | SSRF（DNS 経由） | `validate_target_url` は IP リテラルしか見ず、内部 IP に解決される公開名を通していた | 名前解決した全アドレスを検査する | `tests/test_url_safety.py` |
| 2 | SSRF（リンク検査） | `link_checker` がクロール先のリンクを無検証で `urlopen` し、内部へのリダイレクトも追っていた | `safe_urlopen`（宛先とリダイレクト先を検証）を使い、拒否した宛先は「未確認」として返す | 同上 |
| 3 | SSRF（Webhook 通知） | 通知先 URL を無検証で POST していた | `safe_urlopen` を通し、拒否時は送信失敗として記録する | 同上・`tests/test_notifier.py` |
| 4 | System06 判定の退行 | 2179047 の Word 見出し判定が「REQ-001 を実現する」などの参照行を定義と誤判定し、未定義参照・未カバー要件・追跡線が崩れていた | ID が 1 つだけで、直後が助詞・区切りでない行だけを見出しとみなす | `tests/test_tierflow_traceability_ids.py` 3 件が緑 |
| 5 | 機能台帳（quality harness が FAIL） | 未登録モジュールが 40 本超、削除済み `spec-drift.yml` を参照 | 既存機能へ登録し、影響分析を `impact_analysis` として新設。参照を削除 | `scripts/quality_harness.py` PASS（72 機能） |
| 6 | 文書不足 | 運用手順書・SECURITY.md・第三者ライセンス表が無く、README は同梱していないワークフローを案内していた | `docs/process/OPERATIONS_RUNBOOK.md`・`SECURITY.md`・`THIRD_PARTY_NOTICES.md` を追加し、README を修正 | 見出しと環境変数の掲載数（61 箇所）を確認 |

## 既知 FAIL 5 件の分類（全体の単体テストは 4087 件成功・5 件失敗）

| テスト | 分類 | 理由 |
|---|---|---|
| `healing_demo/test_healing_demo.py::test_add` | 仕様どおり | 自己修復の実証用に、わざと失敗させている。既定の収集からは外れている |
| `test_notify_drift.py` のワークフロー 2 件 | P2・陳腐化 | CI 禁止の方針で削除した `.github/workflows/*.yml` を読んでいる。削除するかどうかは保守者が判断する |
| `test_reverse_analysis_cli.py[unreadable_dir]` | 環境依存 | root で実行すると chmod が効かない（クラウドのコンテナ）。root 以外の環境では通る |
| `test_viewpoint_store_concurrency.py` | P2・既存の競合 | 6 プロセス同時の初回初期化で約 40% 失敗する（修正前も同程度）。`journal_mode` の読み取りで落ちる経路は塞いだが、seed 投入の UNIQUE 競合は残っている。単一プロセス運用では発生しない。複数ワーカーで運用するなら P1 に上げる |

## 残り（P2・ゲート外）

- System02 の全件実行中に、帯の「成功 29」と KPI の「成功 0」が食い違う。完了時には一致する（実行中の表示だけの問題）
- 依存の psycopg が LGPL-3.0。同梱して配布する形態なら法務の確認が必要（`THIRD_PARTY_NOTICES.md`）
- 製品の LICENSE ファイルが無い（保守者・法務の判断）

## 未実行・未検証

- 実ブラウザでの E2E 再確認（GUI からのサイト登録 → 解析 → 保存 → 再読み込み、System02 の全件実行）は、同日に保守者の Mac で通過済み。今回の修正後には再実行していない
- `make verify-ui`・`tests/e2e` は未実行
