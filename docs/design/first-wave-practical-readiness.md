# 第1弾「信頼の底＋即効」実装設計

- 対象: P0-1 → P0-2 → QW-1 → QW-2 → P0-3
- 作成日: 2026-07-16
- 根拠: `docs/research/2026-07-16_実務レベル引き上げ調査.md`
- 対象外: P0-4 以降、cron 式、外部 CDN、LLM 必須機能

## 1. 完了条件

1. スケジュールを曜日・時間帯・タイムゾーンで制限でき、失敗時に設定回数まで指数バックオフで再試行する。
2. スケジュール実行の成功・失敗・試行回数・所要時間がサイト単位の JSONL に永続化され、既存の「実行履歴」で確認できる。
3. 最終失敗が Slack / Teams / Email / Webhook に通知される。通知テンプレート、差分上位件数、テスト送信を設定できる。
4. 標準クロールで、到達ページの HTTP エラー、到達済み内部リンクのリンク切れ、JavaScript コンソールエラー、混在コンテンツを実測保存し、HTML レポートに表示する。
5. 標準クロールで同梱 axe-core を実行し、機械判定可能な WCAG 違反だけを HTML レポートに表示する。手動確認が必要な項目を明記する。
6. 初回利用者に 3〜5 ステップのツアーと成功チェックリストを表示し、完了状態を利用者単位で保存する。認証無効時のみ localStorage へフォールバックする。

## 2. データモデル

### 2.1 `schedule.json`（後方互換の追加キー）

```json
{
  "timezone": "Asia/Tokyo",
  "weekdays": [0, 1, 2, 3, 4],
  "window_start": "02:00",
  "window_end": "05:00",
  "retry_max": 2,
  "retry_backoff_seconds": 60,
  "notify_template": "...",
  "diff_summary_limit": 5
}
```

- 曜日は Python/ISO と同じ月曜=0〜日曜=6。
- 曜日が空なら全曜日。開始・終了が空なら終日。
- `window_start > window_end` は日跨ぎウィンドウとして扱う。
- 既存ファイルに追加キーがなくても従来どおり動作する。

### 2.2 `schedule_history.jsonl`

サイトディレクトリ直下へ追記する。秘密値や stderr 全文は保存しない。

```json
{
  "run_id": "uuid",
  "domain": "example.com",
  "site_url": "https://example.com",
  "started_at": "2026-07-16T02:00:00+09:00",
  "finished_at": "2026-07-16T02:01:20+09:00",
  "status": "complete",
  "attempts": 1,
  "duration_sec": 80.0,
  "trigger": "scheduled",
  "error": ""
}
```

最大表示件数は API 側で制限し、壊れた行は読み飛ばす。

### 2.3 クロール検査成果物

- `technical_health.json`: ページ HTTP 状態、到達済み内部リンク切れ、console error、mixed-content の実測値。
- `accessibility_audit.json`: axe の rule id、impact、selector、help URL、画面 URL、スクリーンショット根拠。
- 既存 `report.json` / snapshot の必須スキーマは変更しない。検査成果物は独立ファイルとして保存する。

### 2.4 利用者ツアー状態

- 認証 DB schema v2 で `users.tour_completed_at` を nullable 追加。
- 認証有効時はサーバーを正とし、本人だけ更新可能。
- 認証無効時は localStorage の `wsd_tour_completed` を使う。

## 3. サービス境界

### P0-1 スケジューラ

- 日時計算を純粋関数として分離し、IANA timezone とウィンドウを検証する。
- 子プロセス結果を値オブジェクトで返し、成功判定・再試行・履歴記録・最終失敗通知を呼び出し側で制御する。
- 二重実行防止のため次回時刻は実行開始前に更新する。履歴は実行終了後に1件だけ確定記録する。

### P0-2 通知

- 既存 `NotifierConfig` と `DriftNotification` はデフォルト値を追加して互換維持する。
- Jinja2 `SandboxedEnvironment` + `StrictUndefined` を使い、テンプレート長と描画結果長を制限する。
- Teams は webhook に JSON を POST する。失敗通知はドリフト通知と別データ型にし、共通レンダラーを使う。
- テスト送信は保存済み設定を利用し、endpoint をレスポンスやログへ出さない。
- `GET /schedule/config` は `notify_endpoint_set` の真偽だけを返す。空欄のまま再保存・テスト送信した場合は同一チャネルの保存済みendpointを保持する。

### QW-1 技術ヘルス

- `crawl_page` の既存 Playwright 応答とイベントから収集し、追加の外部クロールは行わない。
- リンク切れは「実際に到達し HTTP 4xx/5xx を観測した内部ページ」だけを断定する。未到達・外部リンクは切れと断定しない。
- console は `error` のみ、mixed-content は HTTPS ページから観測した HTTP リソースだけを保存する。

### QW-2 アクセシビリティ

- 既存 `src/ux/axe_runner.py` と同梱資産を標準クロールへ配線する。
- 既存 `--ux-review` のニールセン/LLM評価とは分離し、axe 監査は OpenAI 未設定でも完結する。
- レポートに「自動検査は適合性を保証せず、手動確認が必要」と明記する。

### P0-3 オンボーディング

- driver.js の JS/CSS/LICENSE を `static/vendor/driver.js/` に固定版で同梱する。
- ツアーはダッシュボード→新規解析→実行→レポートの価値を4ステップ・各140字以内で案内する。
- 「サイト登録・初回クロール・レポート閲覧」のチェックリストはツアー実行中だけ表示し、完了・スキップ後は隠す。達成状態は既存成果物から算出する。
- empty state にローカルのデモサイト起動方法への導線を置く。外部 CDN は使わない。

## 4. HTTP API

- `GET/POST /schedule/config`: 追加設定の取得・検証・保存。
- `GET /schedule/history?domain=...&limit=...`: スケジュール履歴。
- `POST /schedule/notify/test`: 保存前の入力値を含むテスト通知。
- `GET /api/onboarding`: ツアー完了状態とチェックリスト。
- `POST /api/onboarding/complete`: 本人のツアー完了状態を保存。

API はドメイン・URL・timezone・曜日・時刻・数値範囲をサーバー側で再検証する。

## 5. UI完成状態

- 設定画面に「運用監視」タブを追加する。サイト選択、周期、曜日、時間帯、timezone、再試行、通知チャネル、endpoint、テンプレート、テスト送信を1画面にまとめる。
- 実行履歴に「スケジュール」タブを追加し、既存6列のまま試行回数・所要時間を主要数値欄へ表示する。
- HTML成果物のサイドバーに「技術ヘルス」「アクセシビリティ」を追加し、概要カード→画面別根拠の順で表示する。
- 初回ツアーは既存操作を遮らず、スキップ・再開・完了ができる。設定画面から再表示できる。

## 6. TDDで合意済みの公開境界

1. Flask test client から見た設定・履歴・通知テスト・オンボーディング API。
2. 一時 output ディレクトリを入力したスケジュール実行サービスの JSONL と通知結果。
3. Playwright を模した Page 境界から生成される検査 JSON、および `generate_html_report` の表示。
4. ブラウザからの設定保存、履歴閲覧、レポート閲覧、ツアー完了フロー。

各縦切りを Red → Green で進め、最後に既存全テストを一度だけ実行する。

## 7. 検証・リリース

1. 対象単体テストを各縦切りで実行。
2. `make test`。
3. `make verify-ui`（`.ui-verified`生成必須）。
4. `tests/e2e/screenshots/` を目視し、1920×1080 / 1366×768を確認。
5. 設定→テスト通知→スケジュール履歴、標準クロール→2タブ、初回ツアーを端から端まで操作。
6. `./scripts/verify.sh`。
7. コードレビュー後、topic branchへコミット・push、PR、CI成功、squash merge、ローカルmain同期。

### 環境互換対応

- macOS 26.5.2 で旧 Playwright 1.44.0 同梱Chromiumが起動直後に異常終了したため、Playwrightを1.61.0へ更新する。機能追加ではなく、必須E2Eゲートを実行可能にするための互換対応。
- 既に800行を超えていた既知ファイルは、単純除外せず `scripts/verify.sh` にファイル別の現行上限を固定する。今後の増加は同じゲートで拒否する。
