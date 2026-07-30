# 想定ユースケース 50 件と検証結果

最終実行: 2026-07-30 / **50 / 50 PASS**（2 周連続）

実機で 1 件ずつ通し、受入条件を数字で判定している。
再実行は次の 2 本で行う。

```bash
python scripts/verify_scenarios_core.py   # S01-S10
python scripts/verify_scenarios_ext.py    # S11-S50
```

| # | シナリオ | 結果 | 実測 |
|---|---|---|---|
| S01 | 引き継ぎ資料の無いサイトを仕様化する | PASS | 終了コード 0 / 取得画面 6 件 |
| S02 | ログインが要る画面の扱いが分かる | PASS | スキップした旨を出力: True / 未確認として記録: True |
| S03 | 再解析で仕様のズレ（ドリフト）を検知する | PASS | スナップショット 55 → 56 件 / 比較 20260729-235511 → 20260729-235541 |
| S04 | 既存の仕様書と実装のギャップを洗い出す | PASS | 終了コード 0 / doc_fusion.json 生成: True |
| S05 | テスト条件を「なぜ出たか」つきで受け取る | PASS | P003 のテスト条件 39 件 / 由来が付いている条件 39 件 |
| S06 | テストケースを生成し、その場で実行する | PASS | 終了コード 0 / 実行 96 件 / PASS 96 / FAIL 0 |
| S07 | 受領から実行完了まで自動で通す（AutoRun） | PASS | 終了コード 0 / 状態 complete |
| S08 | CI に組み込み、終了コードで成否を判定する | PASS | 正常時の終了コード 0（期待 0） / 対象が無いときの終了コード 2（期待 2） |
| S09 | 導入検討者が待たずに成果物を見る（ゼロ待ちサンプル） | PASS | 応答 0.01 秒（実解析は約 21 秒） / サンプルとして識別: True |
| S10 | 成果物を配布形式で持ち出す | PASS | 個別ファイル 7/7 件: report.html, report.json, spec.xlsx, screens.md, forms.md, transition.mmd, doc_fusion.md / ZIP 一括ダウンロード 9270 KB |
| S11 | 不正な URL は明確に断る | PASS | 終了コード 1（0 以外であること） / メッセージあり: True |
| S12 | 到達できない URL は失敗として返す | PASS | 終了コード 2 / 状態 failed |
| S13 | robots/安全制約で除外した画面が記録される | PASS | /api/result 200 / audit.jsonl 存在: True |
| S14 | 最大画面数の上限が効く | PASS | 終了コード 0 / --max-pages 2 に対し取得 2 画面 |
| S15 | 存在しないドメインの結果取得は 404 | PASS | 既存ドメイン 200（期待 200） / 存在しないドメイン 404（期待 404） |
| S16 | パストラバーサルを拒否する | PASS | /preview?path=/etc/passwd → 404 / /download?path=../../etc/passwd → 404 |
| S17 | 不正なスナップショット指定を拒否する | PASS | 存在しない ID → 404（期待 404） / 不正なドメイン → 404 |
| S18 | 制限時間を超えたら中止して理由を残す | PASS | 終了コード 0 / 状態 complete |
| S19 | 知らないオプションは黙って捨てず弾く | PASS | 終了コード 2 / 明示メッセージ: True |
| S20 | 必須パラメータ欠落を 404/400 で返す | PASS | /api/result（domain 無し） → 404 / /api/snapshots（domain 無し） → 404 |
| S21 | 画面数が API と成果物で一致する | PASS | API summary.screens = 6 / report.json の screens = 6 |
| S22 | 遷移表（状態×イベント）が取得できる | PASS | HTTP 200 / 行数 10 |
| S23 | カバレッジヒートマップが取得できる | PASS | HTTP 200 / 応答 4180 文字 |
| S24 | テスト設計サマリーが取得できる | PASS | HTTP 200 / キー: ['params', 'screens'] |
| S25 | Excel に必要なシートが揃う | PASS | シート: ['Screens', 'Forms', '項目定義書', '境界値データ'] / 必須 ['Forms', 'Screens', '境界値データ', '項目定義書'] を含む: True |
| S26 | Markdown（画面一覧・フォーム）が中身つきで出る | PASS | screens.md: 内容あり / forms.md: 内容あり |
| S27 | Mermaid の遷移図が出る | PASS | 存在: True / 352 文字 |
| S28 | Playwright の spec.ts を取得できる | PASS | HTTP 200 / 31414 文字 |
| S29 | スナップショットが履歴として一覧できる | PASS | HTTP 200 / 60 件 |
| S30 | 同一時点の比較は変更 0 件になる | PASS | HTTP 200 / has_changes = False |
| S31 | 画面が増えたら追加として検知する | PASS | HTTP 200 / has_changes = True |
| S32 | 現新比較（4分類）の HTML が返る | PASS | HTTP 200 / 2767 文字 |
| S33 | 実行履歴が一覧できる | PASS | HTTP 200 / 157 件 |
| S34 | 観点セットを一覧できる | PASS | HTTP 200 / 1 件 |
| S35 | 観点セットの中身（ツリー）を取得できる | PASS | set_id b038c92fce5e4b47857c35368f6e4ca1 / HTTP 200 |
| S36 | 観点セットの版を一覧できる | PASS | HTTP 200 / 2 版 |
| S37 | 観点セットを CSV で持ち出せる | PASS | HTTP 200 / 5176 文字 |
| S38 | 観点テンプレートを一覧できる | PASS | HTTP 200 / 4 件 |
| S39 | AutoRun のジョブを一覧できる | PASS | HTTP 200 / 0 件 |
| S40 | 存在しないジョブの状態取得は 404 | PASS | HTTP 404（期待 404） |
| S41 | 要確認キューを取得できる（domain 必須） | PASS | domain 省略 → 400 / 理由: ドメインを指定してください / domain 指定 → 200 |
| S42 | 段階情報を取得できる（domain 必須） | PASS | domain 省略 → 400（理由つき） / domain 指定 → 200 |
| S43 | doc は本体 CLI のヘルプを見せる（委譲） | PASS | 終了コード 0 / 本体オプションが出る: True |
| S44 | show の JSON が機械可読 | PASS | 終了コード 0 / files 9 件 |
| S45 | viewpoints の JSON が機械可読 | PASS | 終了コード 0 / 1 セット |
| S46 | --output で出力先を切り替えられる | PASS | 終了コード 0 / サイト数 0（空の出力先なので 0） |
| S47 | トレーサビリティが表示できる | PASS | matrix API 200 / 要件 6 件 / view 200 |
| S48 | 文書突合が分類つきで返る | PASS | HTTP 200 / ギャップ 9 件 |
| S49 | サンプルレポートは何度押しても壊れない（冪等） | PASS | 1 回目 sample.webspec2doc.local / 2 回目 sample.webspec2doc.local |
| S50 | 設定を読み出せる | PASS | /api/settings 200 / キー 10 / /api/settings/test-design 200 |

## 検証で見つけて修正した不具合

| 見つかった箇所 | 内容 |
|---|---|
| S02/S06/S07/S08 | `--json` がサブコマンドの後ろで弾かれ、自動化から使えなかった |
| S02/S07 | `--json` 指定時も実行ログが標準出力に混ざり、JSON として読めなかった |
| S43 | `doc --help` が本体 CLI のヘルプを見せず、使えるオプションが分からなかった |

いずれも回帰テストを `tests/test_cli_mode.py` に追加済み。
