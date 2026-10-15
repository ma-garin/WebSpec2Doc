# WebSpec2Doc バックアップ／リストア手順

対象はリポジトリ直下の `output/` と `instance/` です。この2ディレクトリは必ず同じ時点の対として扱います。`output/` だけを戻すと、認証・テナント・保持設定・スケジュール情報との整合が失われます。

## バックアップ対象

- `output/`: 収集結果、スナップショット、レポート、差分、テスト成果物
- `instance/`: 認証DB、テナント別設定、保持設定、管理監査ログ
- `.env`: APIキー等を含むため、必要な場合だけ別の秘密情報保管庫へ保存する（通常のバックアップアーカイブには含めない）

バックアップには認証情報・画面内容・監査証跡が含まれます。保存先を暗号化し、アクセス権を運用管理者に限定してください。

## バックアップ

1. 実行中のクロールとスケジューラがないことを確認し、WebSpec2Doc プロセスを停止します。SQLite と生成ファイルを同じ時点で保存するため、稼働中のコピーは行いません。
2. リポジトリ直下で次を実行します。

   ```bash
   stamp=$(date +%Y%m%d-%H%M%S)
   mkdir -p backups
   tar -czf "backups/webspec2doc-${stamp}.tar.gz" output instance
   shasum -a 256 "backups/webspec2doc-${stamp}.tar.gz" > "backups/webspec2doc-${stamp}.tar.gz.sha256"
   chmod 600 "backups/webspec2doc-${stamp}.tar.gz" "backups/webspec2doc-${stamp}.tar.gz.sha256"
   ```

3. アーカイブの一覧とチェックサムを検証します。

   ```bash
   tar -tzf "backups/webspec2doc-${stamp}.tar.gz" | sed -n '1,40p'
   shasum -a 256 -c "backups/webspec2doc-${stamp}.tar.gz.sha256"
   ```

4. アーカイブと `.sha256` を同じ保持単位で、リポジトリ外の暗号化ストレージへ複製します。復旧要件に応じて日次・週次・月次の保管世代を決めます。

## リストア

リストアは既存データを置き換えます。対象アーカイブ、復旧時点、作業者を変更記録に残してから実行してください。

1. WebSpec2Doc プロセスを停止します。
2. チェックサムを検証します。

   ```bash
   shasum -a 256 -c backups/webspec2doc-YYYYMMDD-HHMMSS.tar.gz.sha256
   ```

3. 作業用ディレクトリへ展開し、`output/` と `instance/` 以外が含まれていないことを確認します。

   ```bash
   restore_dir=$(mktemp -d)
   tar -xzf backups/webspec2doc-YYYYMMDD-HHMMSS.tar.gz -C "$restore_dir"
   find "$restore_dir" -maxdepth 2 -print | sed -n '1,80p'
   ```

4. 現在のデータを退避してから、対で入れ替えます。`RESTORE_TIMESTAMP` は同じ値を使用します。

   ```bash
   RESTORE_TIMESTAMP=$(date +%Y%m%d-%H%M%S)
   mv output "output.pre-restore-${RESTORE_TIMESTAMP}"
   mv instance "instance.pre-restore-${RESTORE_TIMESTAMP}"
   mv "$restore_dir/output" output
   mv "$restore_dir/instance" instance
   ```

5. 所有者と権限を実行ユーザーに合わせ、WebSpec2Doc を起動します。管理者ログイン、サイト一覧、最新レポート、スケジュール設定、監査ログを確認します。
6. 問題がなければ退避データを所定の変更管理手順で削除します。問題がある場合はプロセスを再停止し、同じ手順で `*.pre-restore-*` を戻します。

## 復旧確認チェックリスト

- [ ] 管理者がログインできる
- [ ] 期待するワークスペースとメンバーが表示される
- [ ] サイトと最新スナップショット件数が一致する
- [ ] レポートを開ける
- [ ] 保持ポリシーとスケジュール／通知設定が一致する
- [ ] 管理監査ログを閲覧できる
- [ ] 次回のスケジュール実行が成功する

少なくとも四半期ごとに、隔離環境でリストア演習を行い、実測した復旧時間と欠落データの有無を記録してください。
