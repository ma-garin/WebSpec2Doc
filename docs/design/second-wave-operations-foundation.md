# 第2弾「運用基盤」実装設計

- 対象: P0-4 データ保持・バックアップ / P0-5 管理監査ログ / P1-1 Drift Check as Code
- 作成日: 2026-07-17
- 根拠: `docs/research/2026-07-16_実務レベル引き上げ調査.md`
- 既存設計の統合: `docs/specs/spec-4-4_ci_drift_monitor.md`

## 1. 完了条件

1. スナップショット保持を「無制限・世代数・日数」から選べ、既定は無制限である。
2. スケジュール成功後に保持ポリシーを適用し、削除結果を監査ログへ記録する。
3. ワークスペースにスコープされた `output/` と `instance/` の使用量を管理者が確認できる。
4. `output/` と `instance/` を同じ復旧点として扱うバックアップ・リストア手順が文書化される。
5. 利用者ログイン成否、メンバー/ロール変更、運用設定変更、エクスポートを JSONL に記録する。
6. owner/admin が監査ログを検索・閲覧でき、member は取得できない。認証無効のローカル単独利用では管理者相当として利用できる。
7. `--compare --ci` が JSON サマリーを標準出力し、0=差分なし、1=ドリフト、2=実行エラーの終了コード契約を守る。
8. GitHub Actions が前回スナップショットを復元・今回分を保存し、実際のドリフトをCIゲートにできる。

## 2. データモデル

### 2.1 `retention.json`

保存先:

- ワークスペースあり: `instance/tenants/{slug}/retention.json`
- 認証無効: `instance/retention.json`

```json
{
  "version": 1,
  "mode": "unlimited",
  "generations": null,
  "days": null,
  "updated_at": "2026-07-17T00:00:00+00:00",
  "updated_by": "user-id"
}
```

- `mode`: `unlimited | generations | days`
- generations: 1〜10000、days: 1〜3650
- 旧環境・ファイル不在・破損時は `unlimited` へ安全にフォールバックする。
- 世代モードは各サイトの新しい N 件、日数モードは現在時刻から N 日以内を保持する。
- 最新1件は設定にかかわらず残す。

### 2.2 `admin_audit.jsonl`

保存先:

- ワークスペースあり: `instance/tenants/{slug}/admin_audit.jsonl`
- 認証無効: `instance/admin_audit.jsonl`
- 存在する利用者に対するログイン失敗は所属ワークスペースへ記録する。
- 未知メールアドレスの失敗は情報漏えいを避け、ワークスペース非特定の `instance/admin_audit.jsonl` へ記録する。

```json
{
  "version": 1,
  "id": "uuid",
  "at": "2026-07-17T00:00:00+00:00",
  "actor_id": "user-id",
  "actor_email": "user@example.com",
  "action": "schedule.settings_updated",
  "target_type": "site",
  "target_id": "example.com",
  "outcome": "success",
  "detail": {"changed_fields": ["interval", "timezone"]}
}
```

- `outcome`: `success | failure`
- detail は JSON オブジェクトに限定し、パスワード、セッショントークン、APIキー、Webhook URL、SMTP資格情報を禁止する。
- 1行64KiB、detailの文字列値は500文字に制限する。
- 末尾追記はプロセス内ロックと1回の write で行う。壊れた行は閲覧時に読み飛ばす。

### 2.3 `drift_summary.json`

`diff_summary.json` は通知本文向けの既存成果物として維持し、CI契約は独立した versioned JSON にする。

```json
{
  "version": 1,
  "site_url": "https://example.com",
  "compared_at": "2026-07-17T00:00:00+00:00",
  "first_run": false,
  "has_changes": true,
  "counts": {
    "added_pages": 1,
    "removed_pages": 0,
    "field_changes": 3,
    "link_changes": 2,
    "title_changes": 0,
    "api_changes": 1
  },
  "severity_counts": {"breaking": 1, "warning": 2, "info": 0},
  "report_url": "output/example.com/diff_report.html"
}
```

## 3. サービス境界

### 3.1 保持サービス

- `web/services/retention.py` が設定の検証・保存・ディスク集計・GCを担当する。
- GC はサイトの `snapshots/*.json` だけを対象にし、スクリーンショットやレポートを暗黙削除しない。
- symlink は追跡せず、対象ディレクトリ外のパスを削除しない。
- scheduler は成功した実行の後だけGCを呼び、失敗してもクロール成功自体を失敗へ変えない。

### 3.2 管理監査サービス

- `web/services/admin_audit.py` が append/read/filter を担当する。
- 記録点: 利用者ログイン成功/失敗、利用者作成・ロール/有効状態変更、schedule設定変更、通知テスト、保持設定変更、保持GC、report/review/viewpoint/spec.tsのサーバー側エクスポート。
- 読み取りAPIは新しい順、最大100件、action/outcome/queryフィルタを提供する。

### 3.3 CIモード

- `--ci` は `--compare` を内包する。比較結果を1行JSONでstdoutの最後に `CI_SUMMARY:` 接頭辞付きで出す。
- 初回は `first_run=true`、差分なしとして exit 0。
- ドリフトは summary を保存して exit 1。
- セッション失効、axe資産異常、クロール0件等の運用失敗は exit 2。
- workflow は `actions/cache/restore` / `actions/cache/save` を分離し、`output/**/snapshots` だけをrun間で保持する。

## 4. HTTP API

- `GET /api/admin/storage`: output/instanceの使用量、サイト別スナップショット数と容量。
- `GET /api/admin/retention`: 現在の保持設定。
- `PUT /api/admin/retention`: 保持設定を検証・保存。
- `GET /api/admin/audit`: 管理監査ログの検索・ページング。

全APIは認証有効時にowner/adminを要求する。テナントの外側を読まない。

## 5. UI完成状態

### データ管理タブ

- output/instance/合計の使用量カード。
- 保持方式セレクトと世代数/日数の条件入力。
- サイト別に「スナップショット件数・使用量・最終更新」を表示。
- 既定値「無制限」を明示する。
- バックアップ/リストア手順書へのリンクを表示し、破壊的な復元ボタンは置かない。

### 監査ログタブ

- owner/adminだけに表示し、日時・操作者・操作・対象・結果を表形式で表示する。
- action/outcome/キーワードで絞り込み、壊れた行や秘密値を表示しない。
- 認証無効のローカル単独利用では表示する。

### CI連携カード

- 既存の運用監視タブへ `--compare --ci` の例、終了コード、workflowテンプレートの場所を表示する。

## 6. TDD公開境界

1. Flask test clientから見たadmin storage/retention/audit APIと権限制御。
2. 一時ディレクトリを入力したretention/admin auditサービスのファイル成果物。
3. CLI `run()` のstdout、`drift_summary.json`、SystemExitコード。
4. ブラウザからの保持設定保存、使用量表示、監査ログ絞り込み、CIカード表示。

各機能を1テスト→最小実装の縦切りで進める。

## 7. 検証・リリース

1. 対象単体テスト。
2. `make test`。
3. `make verify-ui` と1920×1080 / 1366×768画像目視。
4. 保持設定→スケジュール成功→GC→監査ログ、利用者操作→監査閲覧、CI初回→差分ありの全フロー。
5. `./scripts/verify.sh`。
6. Standards/Specレビュー、topic branch push、PR、CI、squash merge、local main同期。
