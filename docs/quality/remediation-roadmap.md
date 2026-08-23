# 品質是正ロードマップ（2026-08-23 フルテスト結果に基づく）

入力: `docs/quality/iso29119-test-completion-report.md`（判定: 条件付き可）・`iso29119-incident-report.md`・
`iso25010-coverage.md`・`iso29119-test-design-spec.md`・`iso9000-qms-assessment.md`。
すべてのタスクは **Sonnet が単独実行できる粒度**（変更ファイル・期待値・完了判定コマンド）で書く。

## 凡例

- **Sonnet 適性**: ◎=この文書だけで委譲可 / ○=参照文書込みで委譲可 / △=調査・判断が混じる / **承認**=ユーザー決定が先
- 完了判定のコマンドは必ず `GATES_REQUESTED=1` を付ける（`.claude/hooks/block-gates.py` が要求時フラグなしのゲート実行を拒否するため）

## 全体像

| Phase | 狙い | タスク | 完了すると |
|---|---|---|---|
| 0 即日 | リリース条件 C-3/C-4 を閉じる | R-01, R-02 | pip-audit 0 件・L1/L2 全緑 |
| 1 今週 | E2E 資産の 4 システム化追随・ゲート全緑化 | R-03〜R-06 | L3 全緑・`.ui-verified` 更新・判定「可（GO）」 |
| 2 来週 | 新規検出欠陥 INC-P01 の修正 | R-07, R-08 | 履歴 API のスケール問題解消・性能回帰の自動検出 |
| 3 今月 | 構造的な品質空白の解消 | R-09〜R-11 | JS ユニットテスト・境界値・契約追跡 |
| 4 方針 | プロセス矛盾の解消（ユーザー決定） | R-12, R-13 | テスト資産の腐敗が最長 1 週間で検出される |

依存: R-06 は R-02〜R-05 完了後。R-08 は単独可（R-07 完了時に上限値を更新）。他は独立。

---

## Phase 0 — 即日（各 30 分以内・S サイズ）

### R-01 pypdf の脆弱性解消（完了報告 C-3）— Sonnet ◎

- **根拠**: pip-audit 実測で pypdf 6.14.2 に PYSEC-2026-3655 / PYSEC-2026-3656（修正版 6.15.0）
- **変更**: `requirements.txt` の pypdf 行を `pypdf>=6.15.0` へ。`venv/bin/pip install -U "pypdf>=6.15.0"`
- **完了判定**:
  1. `GATES_REQUESTED=1 venv/bin/python -m pip_audit -r requirements.txt --progress-spinner off` → `No known vulnerabilities`
  2. `GATES_REQUESTED=1 venv/bin/python -m pytest tests/ --ignore=tests/e2e -q -k "pdf"` → 全 PASS（pypdf 利用箇所の回帰確認）
  3. 出力を `docs/quality/evidence/pip-audit-after-fix.log` に保存

### R-02 UI 契約テストの 4 システム追随（完了報告 C-4）— Sonnet ◎

- **根拠**: 実装は 4 カード（`templates/system-select.html:45,63,81,99` = doc/test/run/cli、文言 "CLI / API"）。
  テスト（`tests/test_ui_contract.py:123-138`）は 3 カード・"CLI モード" を期待し 2 件失敗（8/22 の 4 システム化 `d9ff9cf` に未追随）
- **変更**: `tests/test_ui_contract.py` の `TestSystemSelect` のみ
  - `test_offers_exactly_three_systems` → 名称を `test_offers_exactly_four_systems` に変え、期待値 `sorted(cards) == ["cli", "doc", "run", "test"]`。docstring も 4 系統に更新
  - `test_names_all_systems` → `"CLI モード"` を `"CLI / API"` に変更し、`"テスト活動支援"` の存在確認を追加
  - `test_links_to_each_system` → `assert 'href="/test-activity"' in systems` を追加
- **禁止**: 実装側（templates/）を変えない。他のテストクラスに触れない
- **完了判定**: `GATES_REQUESTED=1 venv/bin/python -m pytest tests/test_ui_contract.py -q` → 全 PASS。
  続けて `GATES_REQUESTED=1 venv/bin/python -m pytest tests/ --ignore=tests/e2e -q --tb=line` → `0 failed`

---

## Phase 1 — 今週（E2E 復旧・M〜L サイズ）

前提知識はすべて `docs/quality/iso29119-incident-report.md` にある。**各タスクの委譲時は同ファイルを必ず読ませる。**

### R-03 認可系 E2E 3 件の新ロールモデル追随 — Sonnet ○

- **対象**: `tests/e2e/system/test_st6_admin.py` の ST-026 / ST-027 / ST-028
- **根拠**（インシデント報告 §2.2/2.3 で確定済み）:
  - owner ロールは admin に統合済み（`web/services/auth_store.py:37-43`、`_LEGACY_ROLE_ALIASES = {"owner": ROLE_ADMIN}`）
  - 不変条件は「テナントの管理者を 0 人にしない」（`auth_store.py:713-716` → `_assert_admin_remains` :873-893）
  - API トークン失効は論理削除（`auth_store.py:1255-1262` が `revoked_at` を設定。一覧からは消えない）
- **変更方針**:
  - ST-027: fixture で admin が 2 名いるため降格が成功するのは正しい挙動。テストを「admin を 1 名にした状態で降格を試み、HTTP 400（`last_admin` 系エラー）を期待」に書き換える
  - ST-028: 「一覧から消える」ではなく「`revoked_at` が設定される」を検証に変更。加えて**失効トークンでの API アクセスが 401 になる**ことを検証に追加（仕様 `docs/system_test_cases.csv:29` の合否基準）
  - ST-026: 現行ロールモデル（admin/member の 2 値）で書き直す
- **注意**: 失効トークンの認証拒否が実装されているかは**未確認**（インシデント報告の未判定 R-7）。テストを先に書き、落ちたら実装欠陥として `docs/quality/iso29119-incident-report.md` に追記して報告を上げる（黙って skip にしない）
- **完了判定**: `GATES_REQUESTED=1 venv/bin/python -m pytest tests/e2e/system/test_st6_admin.py -q` → 全 PASS

### R-04 ナビ・画面系 E2E 9 件の追随 — Sonnet ○（1 ファイル = 1 委譲に分割）

- **対象と分割**（各タスクの根拠はインシデント報告のサマリ表）:
  1. `test_st2_navigation.py`（2 件）: ST-008 は `[data-view="auto-run"]` が docs 系画面で非表示になる設計変更（`static/js/system-scope.js:58-62`）に未追随。システム選択経由の遷移に書き換える。ST-031 はタイムアウト箇所の要素参照を現行 DOM に合わせる
  2. `test_st3_docgen.py`（3 件）: 4 システム化後の入口 URL・セレクタ追随
  3. `test_st4_autorun.py`（3 件）: 同上（AutoRun 入口は `/auto-run`）
  4. `test_st5_member_views.py`（3 件）: ST-020 の 404 は URL 変更の可能性。現行ルート（`web/routes/` の実在パス）を先に `grep` で確定してから直す
  5. `test_stale_state_e2e.py`（1 件）: 「解析結果 0 件」は前提データ不足。テスト内で解析データを seed する（他テストの fixture を流用）
- **共通ルール**: 実装を変えない。テストの期待値変更は必ず現行実装の該当行を根拠にコメントへ書く。直せない・実装が怪しいと判断したものは PASS を偽装せず報告に「未解決・理由」を書く
- **完了判定**: 各ファイル単位で `GATES_REQUESTED=1 venv/bin/python -m pytest <対象ファイル> -q` → 全 PASS

### R-05 判定不能 2 件の再調査 — Sonnet △

- **対象**: ST-012（実行履歴のテナントスコープ）・ST-029（自分のパスワード変更）
- **作業**: インシデント報告の未判定事項 R-1〜R-7 のうちこの 2 件を、実装読解＋単独再実行で製品欠陥かテスト欠陥かを確定し、同報告に追記する
- **完了判定**: `iso29119-incident-report.md` の「判定不能」が 0 件になる

### R-06 ゲート全緑化と証跡の完成（完了報告 C-5/C-6/C-7）— Sonnet ◎（R-02〜R-05 完了後）

- **手順**（順に実行し、出力をすべて `docs/quality/evidence/` へ保存）:
  1. `GATES_REQUESTED=1 make test` → 0 failed
  2. `GATES_REQUESTED=1 make verify-ui` → 全 PASS（成功すると `.ui-verified` に当該ビルドの git hash + UI hash が自動記録される = C-5 完了）
  3. `venv/bin/python scripts/check_e2e_conventions.py` と `venv/bin/python scripts/check_fetch_error_handling.py --fail-on-missing`
  4. テスト計画の UAT 定義に従い未実施の受入シナリオ（完了報告 §2.4 の UAT-07）を実施し、スクリーンショットを `tests/e2e/screenshots/uat-07.png` に保存
  5. `docs/quality/iso29119-test-completion-report.md` の判定を「可（GO）」へ改訂（改訂履歴に日付と根拠を追記）
- **完了判定**: 上記 5 点の成果物が存在し、`.ui-verified` のタイムスタンプが実施日

---

## Phase 2 — 来週（INC-P01 修正・M サイズ）

### R-07 実行履歴 API のページング導入（完了報告 C-8 / INC-P01）

- **根拠**: 実測 3,770 件 / 1.76MB / 175〜189ms を全件返却（他エンドポイントは 2〜12ms）。消費側 2 箇所が全件を DOM 一括描画
- **API 側（Sonnet ○）**: `web/routes/auto_run.py:199-211` の `api_history_runs` に `limit`（既定 200・最大 1000）と `offset` を追加し、応答へ `total` を含める。パラメータ省略時は既定 limit を適用（後方互換のため `limit=0` で従来の全件も許す）。`build_run_history` 側でのソート順は変えない
- **UI 側（承認が先）**: `static/js/ta-execution.js:82` と `static/js/view-run-history.js:119` を「直近 200 件＋『さらに表示』」へ。
  **UI に見える変更のため、実装前に HTML 案を提示して承認を得ること**（プロジェクト規約）。承認前は API 側のみ先行してよい（既定 limit の適用で応答は即改善する）
- **完了判定**: `curl -s 'http://127.0.0.1:8765/api/history/runs' | wc -c` が 200 件相当まで縮む・`limit/offset/total` が機能する API テストを `tests/test_history_runs_paging.py` に追加し PASS

### R-08 性能回帰テストの新設 — Sonnet ◎

- **根拠**: 性能効率性テストは 3,106 件中 5 件。INC-P01 を検出できる自動テストが存在しなかった
- **変更**: `tests/test_perf_baseline.py` を新設。Flask test client で `docs/quality/evidence/perf-baseline.csv` の 8 エンドポイントを叩き、**応答バイト数の上限**をアサートする（時間は CI で flaky になるため件数・サイズ中心。`/api/history/runs` は R-07 完了までは現状値 +20% を暫定上限とし、完了後に 200 件相当へ引き下げる）
- **完了判定**: `GATES_REQUESTED=1 venv/bin/python -m pytest tests/test_perf_baseline.py -q` → PASS

---

## Phase 3 — 今月（構造的空白・L サイズ）

### R-09 フロントエンド JS ユニットテスト基盤 — **承認が先**、導入後は Sonnet ○

- **根拠**: `static/js` 51 ファイルにユニットテスト 0・テストランナー未導入（テスト設計仕様 §5）
- **判断が要る点**: ランナー導入（vitest + jsdom を推奨。理由: 設定最小・ESM 不要の classic script でも `eval` ロードで検証可能）はリポジトリ構成への追加なのでユーザー承認が先
- **承認後の初弾**（純関数から。DOM 不要で確実に回るもの）: `esc`（各ファイル実装）・`fmtDuration`（ta-execution.js）・`readConditions` の契約検証（ta-design.js）・`statusBadge`
- **完了判定**: `npm test`（新設）で 20 件以上の JS ユニットテストが PASS

### R-10 境界値テストの定数直結 — Sonnet ○

- **根拠**: 定数 295 行中、テストが定数名を参照するのは 3 件のみ（テスト設計仕様 §3 の突合表）。定数を変えてもテストが赤くならない
- **変更**: 突合表の 17 定数から着手。各定数につき「定数を import して境界の両側を検証する」テストを追加（`MAX_PARALLELISM=8`・`DEFAULT_MAX_PAGES=50`・TIMEOUT 系を優先）
- **完了判定**: 追加テストが定数参照で書かれている（リテラル再記載は不可）こと・全 PASS

### R-11 機能契約→テストの追跡強化 — **承認が先**（2026-08-23 に前提を訂正）

- **根拠**: `scripts/quality_harness.py:103-106` は `required_tests` が空でないことしか検査しない。failure_mode がテストに現れない機能 15/52（critical 1 = `tenant_isolation`）
- **訂正**: 初版は「required_tests に列挙されたテストが `pytest --collect-only` で解決可能かを検査する」と書いたが、**これは実装できない**。
  `quality/feature_contracts.yml` の `required_tests` は `happy_path` / `error_path` / `evidence` / `cancel_path` といった**抽象ラベル**であり、テスト関数名ではない（`quality/feature_contracts.yml:48-52` 等・52 機能すべて同形式）。ラベルと実テストを機械的に突き合わせる手段が現状は存在しない
- **判断が要る点**: 突き合わせを可能にするには対応付けの規約を新設する必要がある。選択肢:
  - (a) テスト側に pytest マーカーを付ける（例: `@pytest.mark.contract("autorun_execution", "error_path")`）。既存 3,268 テストへの後付けは段階的
  - (b) 契約側に実テスト名を書く欄（`test_refs`）を追加する。契約ファイルの改修のみで済むが、テスト改名時に腐る
  - (c) 現状維持とし、`tenant_isolation` など critical 機能だけ手動で対応表を作る
- **承認後の共通作業**: `tenant_isolation`（critical・failure_mode がテストに現れていない唯一の critical）のテストを最優先で追加する
- **完了判定**: 選んだ方式で「対応が取れていない critical 機能が 0 件」を quality_harness が検出できること

---

## Phase 4 — 方針決定（ユーザーにしか決められない）

### R-12 NC-01: ゲート運用の矛盾解消 — **承認**

- **事実**: `DEFINITION_OF_DONE.md` は「全コミット前にゲート」、`CLAUDE.md` H-7 は「要求時のみ・フックで物理拒否」。この矛盾の実害として、E2E が 8/16〜8/23 の 1 週間実行されず、8/22 の 4 システム化でテスト資産 12 件が腐敗した（完了報告 §6.4）
- **選択肢**（推奨は a。今回の実損害「1 週間の腐敗」にちょうど対応し、H-7 の速度規律を壊さない）:
  - (a) 週次の定期フルゲート実行を設け、結果を `docs/quality/evidence/` に自動保存（腐敗の検出上限 = 1 週間）
  - (b) CI（GitHub Actions）でのゲートを必須化（マージブロック。ただしメモリの「CI を待たない」方針と衝突）
  - (c) 現状維持＋「マイルストーン毎に手動でフルゲート」を DoD に明文化
- **どれを選んでも必須**: 優先関係を 1 文書（DoD）に宣言し、`iso9000-qms-assessment.md` の NC-01 を閉じる

### R-13 NC-02/03/04: 軽量 QMS 運用 — **承認**

- 月次で (1) `/qa-review` 実行と記録（内部監査の代替）(2) `feedback.jsonl` のレビュー（顧客満足の監視）を行う運用を決め、記録先を `docs/quality/` に定める

---

## この計画の弱点

- R-04 の「1 ファイル = 1 委譲」は失敗 9 件の原因が本当に全件テスト側にある前提。実行して初めて実装欠陥が露見する可能性は残る（その場合は R-03 の注意書きと同じく報告へ差し戻す）
- R-06 の UAT-07 は定義の所在（テスト計画）を確認してから実施する必要があり、定義が曖昧なら追加の判断が要る
- Phase 3 の工数は未計測（特に R-09 は基盤導入込みで最大）。着手前に各タスクで見積を取り直すこと
