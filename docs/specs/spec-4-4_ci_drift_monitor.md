# SPEC-4-4 CI 組み込みドリフト監視（定期クロール → 差分検出時の通知）

| 項目 | 値 |
|---|---|
| WBS | 4-4 |
| 優先度 / 見積 | P2 / 1sp |
| 依存 | なし |
| 背景 | docs/11 §5 アイデアカタログ C4 — 評価◎（docs/09「仕様ドリフト監視（月額）」サービスの製品機能化・収益メニュー直結） |

## 1. 目的と背景

「定期クロール → 差分検出時に通知」を、顧客の CI（GitHub Actions 等）にそのまま組み込める形で完成させる。部品はほぼ揃っている — `--compare` / `--fail-on-drift`、Slack/Email/Webhook 通知、ワークフロー例まで存在する — が、**繋がっていない**。特に既存ワークフローは実行ごとに output/ が空の状態から始まるため前回スナップショットが存在せず、毎回「初回スナップショット保存」で終わり実質的にドリフトを検出できない。また通知は Web UI のジョブ経由でしか発火せず、件数がゼロ固定である。本仕様はこの断線を繋ぐ。

**現状の実装状態（実装前に必ず確認すること）:**

- 済: `src/main.py` — `--compare`（L119・前回スナップショットとの差分→ `diff_report.html`）、`--fail-on-drift`（L126-130・drift 時 exit 1、L349-359）。exit code 2 は SESSION_EXPIRED で使用済み（L309）
- 済: `src/diff/snapshot.py::latest_snapshot / save_snapshot` — `output/{domain}/snapshots/YYYYMMDD-HHMMSS.json`
- 済: `web/services/notifier.py` — `DriftNotification` / `NotifierConfig` / `send_drift_notification`（Slack・SMTP・汎用 Webhook。`build_notification(diff_result, ...)` で件数を実数化できる）
- 済（ただし欠陥あり）: `.github/workflows/spec-drift.yml` — workflow_dispatch＋週次 cron で `--compare --fail-on-drift` 実行、成果物 upload。**snapshots が run 間で永続化されないため差分が永遠に出ない**。通知なし。`playwright install chromium` 直叩き（リポジトリ方針 `.runtime/` 固定と不整合 — CI 上は許容されているが要確認）
- 済（ただし欠陥あり）: `web/services/job_queue.py::_try_slack_notify`（L140-170）— diff_report.html の存在だけを見て**件数ゼロ固定**の DriftNotification を送る（`build_notification` 未使用）。diff が無くてもファイルが残っていれば通知される
- 済: `web/services/scheduler.py::_run_crawl`（L149-170）— Web UI スケジュール実行は `--compare` 付き子プロセスだが**通知に接続されていない**
- 未: 差分の機械可読サマリ出力（CI が件数・重大度を読めない）、CLI/CI からの通知経路（notifier は web/ 層にあり src/main.py から import できない — 層分離 CONVENTIONS §1-1）

## 2. 受け入れ条件（全て自動テストで検証すること）

- **AC-1**: `--compare` 実行時、`output/{domain}/drift_summary.json` が生成される（has_changes・added_pages・removed_pages・field_changes・link_changes・title_changes・api_changes の件数、breaking/warning/info の attribute_diffs 件数、report_url、site_url、compared_at）。初回（前回スナップショット無し）は `has_changes: false` と `first_run: true`
- **AC-2**: exit code 契約が明文化・維持される — 0=差分なし（or --fail-on-drift 無し）、1=--fail-on-drift 有効かつ差分あり、2=セッション失効。既存挙動の回帰なし
- **AC-3**: `scripts/notify_drift.py` が drift_summary.json を読み、has_changes が真のときのみ Slack Webhook（`SLACK_WEBHOOK_URL`）へ実数入りの通知を送る（Given: field_changes=3 のサマリ / Then: 通知テキストに「3件」）。差分なし・first_run では送らない（exit 0）
- **AC-4**: 通知失敗（HTTP エラー・URL 未設定）はクロール/CI 判定を壊さない — notify_drift.py は送信失敗で exit 0＋stderr 警告（ドリフト判定は --fail-on-drift の exit 1 が担う）。Webhook URL をログ・エラーメッセージに出力しない
- **AC-5**: `.github/workflows/spec-drift.yml` が snapshots を run 間で永続化し（actions/cache）、2 回目以降の実行で実際に差分を検出できる。drift 時に notify_drift.py が実行され、workflow は失敗（赤）になる
- **AC-6**: Web UI ジョブ通知（job_queue._try_slack_notify）が drift_summary.json を読んで実数を通知し、has_changes が偽なら通知しない（ゼロ固定・常時通知の欠陥修正）
- **AC-7**: report.json のスキーマ・report_hash は変化しない（drift_summary.json は独立ファイル）

## 3. スコープ外

- PR コメント通知の実装（ワークフロー例の中で `gh` CLI を使うサンプルをコメントとして載せるのみ。実装・テスト対象にしない）
- Web UI スケジューラの通知接続（scheduler._run_crawl → 通知は AC-6 のジョブ経路が既にカバー。scheduler 直結は Phase 2）
- 通知チャンネルの追加（Teams 等）・通知テンプレートのカスタマイズ
- SaaS 的な監視ダッシュボード・履歴集計（usage_tracker 連携は WBS-3-5）
- GitLab CI / CircleCI 例（README に GitHub Actions からの読み替え指針を 1 段落書くのみ）

## 4. 基本設計

### 4-1. 変更ファイル一覧

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 変更 | `src/main.py` | `_save_diff_report` 内で drift_summary.json を出力（`DIFF_SUMMARY_FILE_NAME = "drift_summary.json"` 定数追加） |
| 新規 | `scripts/notify_drift.py` | サマリ読取→ `web.services.notifier` 再利用で Slack 送信（scripts/ は層外ユーティリティ — quality_harness.py と同格） |
| 変更 | `web/services/job_queue.py` | `_try_slack_notify` を drift_summary.json ベースの実数通知に修正 |
| 変更 | `.github/workflows/spec-drift.yml` | snapshots の cache 化・通知ステップ・continue-on-error 整理（§5-3） |
| 新規 | `tests/test_drift_summary.py`・`tests/test_notify_drift.py` | 単体テスト（§6-1） |
| 変更 | `quality/feature_contracts.yml` | feature_id: `ci_drift_monitor` を追加 |
| 変更 | `README.md` | CI 組み込み手順（secrets 設定・cache の意味・exit code 契約） |

### 4-2. データモデル（drift_summary.json）

```json
{
  "version": 1,
  "site_url": "https://example.com",
  "compared_at": "2026-07-04 03:00 UTC",
  "first_run": false,
  "has_changes": true,
  "counts": {
    "added_pages": 1, "removed_pages": 0, "field_changes": 3,
    "link_changes": 2, "title_changes": 0, "api_changes": 1
  },
  "severity_counts": {"breaking": 1, "warning": 2, "info": 0},
  "report_url": "output/example.com/diff_report.html"
}
```

- `severity_counts` は `DiffResult.attribute_diffs[].severity`（differ.py の SEVERITY_BREAKING/WARNING/INFO）を集計
- `version` キーで将来の拡張に備える（consumers は未知キーを無視する契約）

### 4-3. 処理フロー

```text
[CI（GitHub Actions）]
  actions/cache restore（key: spec-drift-snapshots-<domain>）
    → output/{domain}/snapshots/ が前回状態で復元される
  python src/main.py --url $TARGET --compare --fail-on-drift --format json,html
    ├─ latest_snapshot → compute_diff → diff_report.html（既存）
    ├─ drift_summary.json 出力（新規・AC-1）
    └─ drift ⇒ exit 1（既存）
  if failure（= drift）:
    python scripts/notify_drift.py output/<domain>/drift_summary.json   # Slack 実数通知
  actions/cache save（always）
  upload-artifact（always・既存）

[Web UI ジョブ]
  job_queue._run_job 完了後 → _try_slack_notify
    └─ drift_summary.json を読み has_changes 時のみ build 済み実数で送信（AC-6）
```

## 5. 詳細設計

### 5-1. src/main.py の変更

`_save_diff_report(prior_snapshot, new_snapshot, pages, output_dir, primary_url)` は現在 bool（drift 有無）を返す。この関数の中で compute_diff 結果を持っている箇所に集計を追加し、`output_dir / "drift_summary.json"` を**毎回**書く（差分なしでも `has_changes: false` を書く — CI/ジョブ側が「ファイルが無い＝比較していない」と「差分なし」を区別できるようにする）。prior_snapshot が None の場合は `first_run: true` で書く。

書式は `json.dumps(..., ensure_ascii=False, indent=2, sort_keys=True)`。site_url は primary_url、report_url は `output/{domain}/diff_report.html` 相対パス。

### 5-2. scripts/notify_drift.py

```text
usage: python scripts/notify_drift.py <path/to/drift_summary.json>
env:   SLACK_WEBHOOK_URL（必須。無ければ警告して exit 0）
       WEBSPEC2DOC_NOTIFY_REPORT_URL（任意。CI の artifact URL 等で report_url を上書き）
```

- `web.services.notifier` の `NotifierConfig(NOTIFIER_SLACK, webhook_url)` と `DriftNotification` を**再利用**する（送信ロジックの重複実装をしない。scripts/ は quality_harness.py と同様に web/src 両方を import できる層外ツール）
- has_changes=false / first_run=true → 「通知不要」を stdout に出して exit 0
- 送信結果 False（notifier は例外を握って False を返す）→ stderr 警告・exit 0（AC-4）。**exit 1 にしない**: CI のドリフト判定は main.py の exit code が担い、通知はベストエフォート
- Webhook URL は例外メッセージ含め一切出力しない（notifier 側は URL をログに出す実装（`_post_json` の logger.error）があるため、呼び出し前に URL 妥当性を確認し、notifier のログレベル調整ではなく **notifier._post_json のログから URL を落とす修正**も本仕様に含める — AC-4）

### 5-3. .github/workflows/spec-drift.yml の改修

```yaml
# 差分の要点のみ（全文は実装時に）
      - name: Restore snapshots
        uses: actions/cache/restore@v4
        with:
          path: output/**/snapshots
          key: spec-drift-snapshots-${{ inputs.target_url || vars.WEBSPEC_TARGET_URL }}-${{ github.run_id }}
          restore-keys: spec-drift-snapshots-${{ inputs.target_url || vars.WEBSPEC_TARGET_URL }}-
      - name: Run spec drift detection
        id: drift
        continue-on-error: true
        run: python src/main.py --url "$TARGET_URL" --compare --fail-on-drift --format json,html
      - name: Save snapshots
        if: always()
        uses: actions/cache/save@v4
        with: {path: output/**/snapshots, key: spec-drift-snapshots-...-${{ github.run_id }}}
      - name: Notify drift (Slack)
        if: steps.drift.outcome == 'failure'
        env: {SLACK_WEBHOOK_URL: '${{ secrets.SLACK_WEBHOOK_URL }}'}
        run: python scripts/notify_drift.py output/*/drift_summary.json
      - name: Fail on drift
        if: steps.drift.outcome == 'failure'
        run: exit 1
```

- cache key はターゲット URL を含める（複数サイト監視時の混線防止）。run_id 付き save＋restore-keys 前方一致は「毎回保存・最新を復元」の定石
- exit code 2（SESSION_EXPIRED）と 1（drift）の区別: `steps.drift.outcome` は両方 failure になるため、Notify ステップ内で drift_summary.json の存在＋has_changes を notify_drift.py が判定する（誤通知しない — AC-3）
- PR コメント通知は同ワークフローにコメントアウトのサンプル（`gh api repos/.../issues/$PR/comments`）として併記（スコープ外の明示）

### 5-4. job_queue._try_slack_notify の修正

- 現在: diff_report.html の存在チェックのみ・件数ゼロ固定（L159-166）
- 修正後: `output/{domain}/drift_summary.json` を読み、`has_changes` が真のときだけ counts を `DriftNotification` に詰めて送信。summary 不在（旧バージョン出力・compare なしジョブ）の場合は従来挙動へフォールバックせず**通知しない**（誤通知の温床を断つ）。例外は現行同様握りつぶし＋警告ログ

### 5-5. エラー処理表

| 事象 | 振る舞い | ユーザー可視 |
|---|---|---|
| SLACK_WEBHOOK_URL 未設定 | notify_drift.py が警告して exit 0 | stderr「Webhook 未設定のため通知をスキップ」 |
| Webhook 送信失敗（4xx/5xx/接続不能） | exit 0・URL を含まない警告 | stderr 警告＋CI ログ |
| drift_summary.json 不在/破損 | notify_drift.py exit 0・警告（CI 判定は drift step が既に確定済み） | stderr 警告 |
| セッション失効（exit 2） | summary が書かれない → 通知されない | 既存の SESSION_EXPIRED 出力 |
| cache 未ヒット（初回） | first_run: true・exit 0・通知なし | ログ「初回スナップショットを保存しました」（既存文言） |

## 6. テスト仕様

### 6-1. 単体テスト

| テスト名 | 入力 | 期待値 | AC |
|---|---|---|---|
| test_summary_written_on_compare | 差分ありスナップショット 2 世代（tmp_path） | drift_summary.json の counts/severity_counts が compute_diff と一致 | AC-1 |
| test_summary_first_run | prior=None | first_run=true・has_changes=false | AC-1 |
| test_summary_no_changes | 同一スナップショット | has_changes=false のファイルが**書かれる** | AC-1 |
| test_exit_code_contract | drift あり＋--fail-on-drift | SystemExit(1)（既存テストの拡張） | AC-2 |
| test_notify_sends_real_counts | field_changes=3 のサマリ＋フェイク urlopen | POST ボディに「3」・URL 非ログ | AC-3, 4 |
| test_notify_skips_no_changes | has_changes=false / first_run=true | 送信 0 回・exit 0 | AC-3 |
| test_notify_failure_exit_zero | urlopen が HTTPError | exit 0・stderr 警告に URL 非含有 | AC-4 |
| test_job_notify_uses_summary | drift_summary.json（実数） | DriftNotification の件数一致・has_changes=false で非送信 | AC-6 |
| test_report_hash_unchanged | 既存ページ相当 | report.json 不変 | AC-7 |

通知系のフェイクは `urllib.request.urlopen` の monkeypatch（notifier.py は urllib 直呼び）。時刻は compared_at 検証用に FakeClock 注入パターン（tests/test_real_site_resilience.py 参照）。

### 6-2. 結合確認（CI ワークフロー）

- workflow YAML は実行環境依存のため自動テスト対象外とし、**actionlint 相当の静的検証**（`python -c` で YAML ロード＋必須ステップ存在確認）を tests/test_notify_drift.py に含める
- 手動検証手順を README に記載: workflow_dispatch を 2 回実行 → 1 回目 first_run / 2 回目でデモサイト改変後に drift 検出・Slack 着信

### 6-3. 回帰確認

- 既存の --compare / --fail-on-drift / diff_report.html テストが無変更で PASS
- Web UI ジョブの既存テスト（job_queue）PASS・通知が「diff_report.html 存在＝送信」でなくなったことの明示テスト

## 7. 完了チェックリスト（DoD）

- [ ] AC-1〜7 のテストが全て存在し PASS
- [ ] CONVENTIONS §3 の全ゲート通過（black/ruff/mypy/bandit/pytest/quality_harness）
- [ ] feature_contracts.yml に `ci_drift_monitor`（core_files: src/main.py, scripts/notify_drift.py, web/services/notifier.py / failure_modes: missing_webhook, notify_http_error, missing_summary, first_run, session_expired / required_tests: happy_path, error_path, no_change_path, evidence）
- [ ] 実行パス確認: ローカルでデモサイトを 2 回クロール（間に demo HTML を 1 箇所改変）→ drift_summary.json の実数→ `scripts/notify_drift.py` を webhook.site 等に向けて実送信し着信を目視確認。実送信できない環境なら「未確認」と報告
- [ ] README に CI 組み込み手順（secrets.SLACK_WEBHOOK_URL・vars.WEBSPEC_TARGET_URL・cache の役割・exit code 0/1/2 の契約表）

## 8. このタスク固有の罠

- **snapshots の永続化こそが本体**。actions/cache を入れ忘れる（または path を output/ 全体にして巨大 screenshot を毎回往復させる）と従来と同じ「毎回初回」に戻る。cache path は `output/**/snapshots` に限定する
- `actions/cache`（restore/save 分離形）を使うこと。単純な `actions/cache@v4` は**同一 key ではヒット時に保存しない**ため、run_id 入り key＋restore-keys 前方一致にしないと 2 回目以降のスナップショットが積み上がらない
- exit code 1 は「ドリフト」、2 は「セッション失効」。ワークフローの `outcome == 'failure'` はどちらでも真になるため、**通知の最終判定は drift_summary.json の has_changes**（notify_drift.py 内）で行う。exit code だけで通知すると失効時に「ドリフト検知」と誤報する
- notifier.py の `_post_json` は現在エラーログに URL を出す（L87）。Slack Webhook URL は秘密情報であり、CI ログに漏れる。この 1 行の修正を忘れると AC-4 を満たさない
- スケジュール実行（scheduler.py）はタイムアウト 600 秒の子プロセス。大規模サイトで --compare が遅い場合にサマリが書かれないまま終わる — summary 出力は diff 計算直後・save_outputs より前に行い、途中失敗の影響を受けにくい位置に置く
- pre-commit が pytest を強制する（CONVENTIONS §3）。workflow YAML だけの修正コミットでもテストが走る前提で作業を分割する
