# Final Release Gate

判定: **NO-GO**（LEGAL_APPROVAL_REQUIRED / SECURITY_CONTACT_REQUIRED）

Release commit: 候補は本 PR（#308）のマージコミット。GO になった時点で `v1.0.0` タグを付ける
Version: 1.0.0（候補。`VERSION` ファイル）
Date: 2026-10-20

## Gate

| 項目 | 結果 |
|---|---|
| Core E2E | PASS（下記の 5 フロー。REA の解析実行のみ #307 以前の証跡を再利用） |
| Unit | PASS（4087 件成功。既知の FAIL 5 件はすべて分類済み・非ブロッカー） |
| E2E | PASS（130 件成功・10 件失敗・46 件スキップ。失敗 10 件は P2 で主要フローを壊さない） |
| UI | PASS（`make verify-ui` と同じ中身の `tests/e2e` を直接実行。見切れ 0 件） |
| Security | PASS（SSRF は #307 の修正を UI と API の両方で実証。外部公開時の認証既定値の危険を本 PR で修正） |
| Auth/AuthZ | PASS（本 PR で修正後） |
| Product Truth | PASS（#307 以降の変更は判定・表示ロジックに触れていない。SSRF で除外した URL を「0 件・安全制約で除外」と表示し、成功扱いにしない） |
| Operations | PASS（`docs/process/OPERATIONS_RUNBOOK.md`：起動・必須の環境変数・TLS 終端・ログ・バックアップ・ヘルスチェック・更新と切り戻し） |
| License/Legal | **FAIL** |
| Release Identity | PASS（本 PR で `VERSION`・バージョン方針・リリースノートを追加） |

### 本 PR で直した P1（Final Gate 中に発見）

| 項目 | Before | After |
|---|---|---|
| 外部公開時の認証 | `WEBSPEC2DOC_TRUSTED_HOSTS` を設定しても、未設定なら `AUTH_MODE=auto`（ユーザー 0 人の間は認証なし）と `AUTH_MOCK=1`（パスワードなしログイン）のまま公開されていた | 外部公開構成で未設定のときは `required`・モック無効に倒す。明示した設定は優先する（`tests/test_auth_external_defaults.py`） |
| 指揮のサイドバー | 「ガイド」が `/docs`、「設定」が `/settings/general` を指し、どちらも 404 だった | `/user-guide`・`/settings`（どちらも 200） |
| 見切れ | `/test-automation` の「いま」ボタンが 1280×720 で切れていた | 0 件 |

## Known limitations

- **単一プロセス運用のみをサポートする**（runbook §1。`app.run` の内蔵サーバ）。観点ストアを複数プロセスで同時に初期化すると、約 40% で失敗する。
- **TLS 終端**はリバースプロキシで行う。アプリ自体は HTTPS を提供しない。
- Ghidra / native バイナリの解析は対象外（#305 で LATER 判定）。
- e2e の P2 2 種：
  - 自動実行の画面に「設定」ラベルのボタンが 2 つある（全体設定と区間設定で、操作は別物）。
  - 設定画面にいる間に結果表示が呼ばれると、レポートパネルが設定画面の上に出る。
- System02 で実行している間、帯と KPI の件数が一時的に食い違う（完了時には一致する）。
- 推奨の動作環境は PC ブラウザ（幅 816px 以上）。Chromium は Playwright が実行時に取得し、リポジトリには同梱していない。

### 既知 FAIL 5 件の最終扱い

| テスト | FAIL 理由 | 商品への影響 | ブロッカー | 扱い |
|---|---|---|---|---|
| `healing_demo/test_healing_demo.py::test_add` | 自己修復の実証用に、わざと失敗させている | なし | 否 | B. 商品対象外（実証用の素材） |
| `test_notify_drift.py::test_spec_drift_workflow_…` | 削除済みの `.github/workflows/spec-drift.yml` を読んでいる | なし（CI 禁止の方針でワークフローを同梱しない） | 否 | A. 陳腐化。削除は保守者が判断する |
| `test_notify_drift.py::test_generated_spec_workflow_…` | 削除済みの `generated-spec.yml` を読んでいる | なし | 否 | A. 陳腐化。同上 |
| `test_reverse_analysis_cli.py[unreadable_dir]` | root で実行すると chmod 000 が効かない | なし（root 以外の環境では通る） | 否 | C. 環境依存 |
| `test_viewpoint_store_concurrency.py::…converge` | 複数プロセスでの初回初期化で seed が UNIQUE 競合を起こす | 単一プロセス運用では発生しない | 否 | D. known limitation（単一プロセスのみサポート） |

## Blockers

| ID | 理由 | 解消者 | コード修正 | 最小解消条件 |
|---|---|---|---|---|
| LEGAL_APPROVAL_REQUIRED | 製品自身の LICENSE が無く、誰がどの条件で使える製品なのかが未定義。提供形態（SaaS／顧客へのソース配布／社内限定）がコードと文書から確定できない。README は clone と venv による自前構築を案内しており、配布（形態 B）に当たる可能性がある。依存に psycopg（LGPL-3.0-only）があり、推移的依存と Playwright が取得する Chromium のライセンスは未確認 | 保守者・法務 | 否（LICENSE ファイルと利用条件の追加のみ） | 提供形態を決め、製品ライセンス（または利用規約）を LICENSE としてリポジトリに置く。その形態での psycopg・推移的依存・Chromium の扱いについて法務の承認を得る |
| SECURITY_CONTACT_REQUIRED | `SECURITY.md` の報告窓口と受領連絡の期限が `<保守者が記入>` のまま。利用者が脆弱性を報告できない | 保守者 | 否 | 実在する窓口（メールアドレスまたは報告フォーム）と応答期限を `SECURITY.md` に記入する |

## Evidence

- 実ブラウザ（Chromium 141・#307 後の main ＋本 PR・DemoMart をローカルで配信）
  1. サイト登録 → 画面解析 → 生成 → 保存 → 再読み込み：PASS（1280 幅。7 画面・テストケース 116 件が再読み込み後も表示され、JS エラー 0）
  2. System02 の全件実行：PASS（115 件成功・1 件失敗・37 秒。再読み込み後も結果が残る）。REA / System03 / System09 は画面表示が 3 幅で PASS。REA の解析実行は #307 以前の証跡を再利用（#307 と本 PR はこの経路を変更していない）
  3. 指揮 → サイト選択 → 戻る → 再読み込み：PASS（816 / 1024 / 1280。サイドバーのリンクはすべて 200）
  4. System06：要件定義書と、「REQ-001 を実現する」と書いた設計書を登録 → 承認。指摘は `UNCOVERED REQ-002` の 1 件だけで、REQ-001 は参照として扱われた：PASS（起動中のサーバの API で確認。画面表示は 3 幅で JS エラー 0）
  5. SSRF：`WEBSPEC2DOC_ALLOW_LOCAL` を付けないサーバで `169.254.169.254` を解析すると、UI に「取得可能な画面は0件です。1件が…安全制約により除外されました。」と表示される。`/api/v1/sites/x/crawl` で `10.0.0.1` を指定したジョブは「安全でない URL をスキップ」で終了し、外向きの通信は発生しない：PASS
  - 27 画面 × 3 幅を巡回：404 は 2 件（指揮のサイドバーのリンク。本 PR で修正）、横スクロールは `/sites/…/tests` の 816・1024 幅で 2 件（P2）
- `tests/e2e`：130 件成功・10 件失敗・46 件スキップ。失敗の内訳は、自動実行の画面で同じラベルのボタンが重複 9 件と、レポートパネルが別画面の上に出る 1 件（どちらも P2）
- `scripts/check_clipping.py`：見切れ 0 件（26 画面 × 2 幅）
- 認証まわりのテスト：81 件成功（新規 3 件を含む）
- 実行環境の注記：コンテナ内の Chromium（1194）を Playwright 1.61 が期待するリビジョン 1228 として scratchpad にリンクして実行した

## Release notes（1.0.0 候補）

- 対象：URL から画面仕様書・テスト設計・テストケースを生成する（System01）、テストの実行（System02）、REA、ドキュメント検証とトレーサビリティ（System06）、指揮
- サポート条件：単一プロセス、TLS はリバースプロキシで終端、本番の必須設定は runbook §1 のとおり
- 既知の制約：上記の Known limitations のとおり
