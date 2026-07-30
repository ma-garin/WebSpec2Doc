# CLI モード 想定ユースケース 100 件と検証結果

最終実行: 2026-07-30 / **100 / 100 PASS**

画面を持たない実行経路のため、「端末から叩いて期待どおりの結果と終了コードが返るか」
を実機で 1 件ずつ判定している。判定できないものは PASS にせず理由を残す。

```bash
# 検証用のデモサイトを 8767 で起動しておく
python scripts/verify_cli_scenarios.py
```

観点の内訳:

| 区分 | 観点 | 番号 |
|---|---|---|
| A | 引数の受け取り（順序・別名・欠落・不正） | C001-C020 |
| B | 終了コード（CI から成否を判定できるか） | C021-C035 |
| C | 出力の契約（人が読む形 / 機械が読む形） | C036-C055 |
| D | 実行系（doc / autorun / test） | C056-C070 |
| E | 参照系（sites / show / viewpoints） | C071-C085 |
| F | 安全性・堅牢性（不正入力・境界・冪等） | C086-C100 |

| # | シナリオ | 結果 | 実測 |
|---|---|---|---|
| C001 | 共通オプションが効く: sites --json | PASS | 終了コード 0 / JSON として読めた: True |
| C002 | 共通オプションが効く: --json sites | PASS | 終了コード 0 / JSON として読めた: True |
| C003 | 共通オプションが効く: show --domain 127.0.0.1:8767 --json | PASS | 終了コード 0 / JSON として読めた: True |
| C004 | 共通オプションが効く: --json show --domain 127.0.0.1:8767 | PASS | 終了コード 0 / JSON として読めた: True |
| C005 | 共通オプションが効く: viewpoints --json | PASS | 終了コード 0 / JSON として読めた: True |
| C006 | 共通オプションが効く: --json viewpoints | PASS | 終了コード 0 / JSON として読めた: True |
| C007 | --output が効く: sites --output /tmp/tmp18g7i0pt | PASS | 終了コード 0 / 空の出力先で 0 件になる |
| C008 | --output が効く: --output /tmp/tmp18g7i0pt sites | PASS | 終了コード 0 / 空の出力先で 0 件になる |
| C009 | --output が効く: sites --output /tmp/tmp18g7i0pt | PASS | 終了コード 0 / 空の出力先で 0 件になる |
| C010 | --output が効く: --output /tmp/tmp18g7i0pt --json | PASS | 終了コード 0 / 空の出力先で 0 件になる |
| C011 | 必須引数の欠落を弾く: test の --domain | PASS | 終了コード 2 / メッセージ: python src/cli.py test: error: the following arguments are r |
| C012 | 必須引数の欠落を弾く: show の --domain | PASS | 終了コード 2 / メッセージ: python src/cli.py show: error: the following arguments are r |
| C013 | 必須引数の欠落を弾く: autorun の --url | PASS | 終了コード 2 / メッセージ: python src/cli.py autorun: error: the following arguments ar |
| C014 | サブコマンド無しは使い方を出して弾く | PASS | 終了コード 2 |
| C015 | 知らないサブコマンドを弾く | PASS | 終了コード 2 |
| C016 | 不正な値を弾く: --depth に文字列 | PASS | 終了コード 2 / python src/cli.py autorun: error: argument --depth: invalid  |
| C017 | 不正な値を弾く: --max-pages に文字列 | PASS | 終了コード 2 / python src/cli.py autorun: error: argument --max-pages: inva |
| C018 | 不正な値を弾く: --timeout に不正値 | PASS | 終了コード 2 / python src/cli.py autorun: error: argument --timeout: invali |
| C019 | 不正な値を弾く: --approve に許可外の値 | PASS | 終了コード 2 / python src/cli.py autorun: error: argument --approve: invali |
| C020 | 不正な値を弾く: --case-id の値欠落 | PASS | 終了コード 2 / python src/cli.py test: error: argument --case-id: expected  |
| C021 | 終了コード: sites は 0 | PASS | 実際 0 / 期待 0 |
| C022 | 終了コード: viewpoints は 0 | PASS | 実際 0 / 期待 0 |
| C023 | 終了コード: 既存ドメインの show は 0 | PASS | 実際 0 / 期待 0 |
| C024 | 終了コード: 存在しないドメインの show は 2 | PASS | 実際 2 / 期待 2 |
| C025 | 終了コード: 知らないオプションは 2（argparse の慣例） | PASS | 実際 2 / 期待 2 |
| C026 | test: 対象が無ければ 2 | PASS | 終了コード 2 / error: report.json がありません: output/nope.invalid/ |
| C027 | test: 該当ケース 0 件なら 2（成功と見せない） | PASS | 終了コード 2 / error: 実行対象のテストケースがありません |
| C028 | test: 全件 PASS なら 0 | PASS | 終了コード 0 / PASS 8 / FAIL 0 |
| C029 | test: 実行件数が 0 でない | PASS | total 8 |
| C030 | test: 所要時間が記録される | PASS | 2856 ms |
| C031 | autorun: 完走なら 0 | PASS | 終了コード 0 / status complete |
| C032 | autorun: job_id が返る | PASS | job_id 538749af7e2f |
| C033 | autorun: ドメインが確定する | PASS | domain 127.0.0.1:8767 |
| C034 | autorun: 所要が記録される | PASS | 21.5 秒 |
| C035 | autorun: 到達できなければ完走にしない | PASS | 終了コード 2 / status failed |
| C036 | --json の stdout が純粋な JSON: sites | PASS | 先頭 '{' / パース可: True |
| C037 | --json の stdout が純粋な JSON: show | PASS | 先頭 '{' / パース可: True |
| C038 | --json の stdout が純粋な JSON: viewpoints | PASS | 先頭 '{' / パース可: True |
| C039 | autorun: --json でも stdout は JSON だけ | PASS | stdout 1601 文字 / パース可 True / stderr にログ 5407 文字 |
| C040 | autorun: 実行ログは stderr に出る（消さない） | PASS | stderr 5407 文字 |
| C041 | --quiet でログを止められる | PASS | stdout 1601 / stderr 0 |
| C042 | sites: command キーを持つ | PASS | sites |
| C043 | sites: sites 配列を持つ | PASS | 5 件 |
| C044 | sites: 各要素が domain/screens/fields/snapshots を持つ | PASS | キー ['domain', 'fields', 'screens', 'snapshots'] |
| C045 | show: files 配列を持つ | PASS | 9 件 |
| C046 | show: 各ファイルが exists を持つ | PASS | 全要素に exists |
| C047 | show: testcase_run を持つ | PASS | True |
| C048 | viewpoints: sets 配列を持つ | PASS | 1 件 |
| C049 | 人が読む形に見出しが出る: sites | PASS | 『解析済みサイト』を含む |
| C050 | 人が読む形に見出しが出る: show | PASS | 『成果物』を含む |
| C051 | 人が読む形に見出しが出る: viewpoints | PASS | 『観点セット』を含む |
| C052 | show: 存在するファイルに印が付く | PASS | ✓ を含む |
| C053 | show: 見つからないときは理由を出す | PASS | 見つかりません: output/nope.invalid |
| C054 | sites: 0 件でも黙らず理由を出す | PASS | 出力先がありません: /tmp/__empty_out__ |
| C055 | ヘルプに終了コードの説明がある | PASS | 130 を含む |
| C056 | doc は本体のヘルプへ委譲 | PASS | 終了コード 0 / 『--format』を含む |
| C057 | autorun のヘルプ | PASS | 終了コード 0 / 『--login-user』を含む |
| C058 | test のヘルプ | PASS | 終了コード 0 / 『--case-id』を含む |
| C059 | sites のヘルプ | PASS | 終了コード 0 / 『--output』を含む |
| C060 | show のヘルプ | PASS | 終了コード 0 / 『--domain』を含む |
| C061 | viewpoints のヘルプ | PASS | 終了コード 0 / 『--json』を含む |
| C062 | doc: 本体オプションがそのまま効く | PASS | 終了コード 0 |
| C063 | doc: report.json が生成される | PASS | /home/user/WebSpec2Doc/output/127.0.0.1:8767/report.json |
| C064 | doc: 不正 URL を弾く | PASS | 終了コード 1 |
| C065 | doc: 未知の出力形式を弾く | PASS | 終了コード 2 |
| C066 | doc: --max-pages 1 が効く | PASS | 取得 1 画面 |
| C067 | autorun: --approve skip が通る | PASS | status complete |
| C068 | autorun: 自動で通した判断が全て出る | PASS | 9 件 |
| C069 | autorun: 未確認項目が記録される | PASS | 3 件 |
| C070 | autorun: --require-login で資格情報が無ければ中止 | PASS | 終了コード 1 / status awaiting_input / 理由: ['ログインが必要だが資格情報が無いため中止した'] |
| C071 | sites: 解析済みが 1 件以上出る | PASS | 5 件 |
| C072 | sites: 画面数が数値 | PASS | 全て int |
| C073 | sites: 隠しディレクトリを出さない | PASS | ドット始まり無し |
| C074 | sites: tenants を出さない | PASS | tenants 無し |
| C075 | sites: 履歴数が数値 | PASS | 全て int |
| C076 | show: 主要な成果物を列挙する | PASS | 9 種 |
| C077 | show: パスが絶対または相対で示される | PASS | 全要素に path |
| C078 | show: ラベルが日本語で読める | PASS | 全要素に label |
| C079 | show: 実在するものだけ ✓ になる | PASS | 9/9 件が実在 |
| C080 | show: テスト実行の実績を出す | PASS | {'ok': True, 'passed': 8, 'failed': 0, 'skipped': 0, 'total': 8, 'duration_ms': 2856, 'error': ''} |
| C081 | viewpoints: 1 件以上出る | PASS | 1 件 |
| C082 | viewpoints: 名称を持つ | PASS | 全要素に name |
| C083 | viewpoints: set_id を持つ | PASS | 全要素に set_id |
| C084 | viewpoints: 人が読む形に公開版が出る | PASS | 『公開版』を含む |
| C085 | show: 出力先を変えると見つからない扱いになる | PASS | 終了コード 2 |
| C086 | 危険なドメイン名を扱わない: ../etc | PASS | 終了コード 2 / 内容が漏れない: True |
| C087 | 危険なドメイン名を扱わない: ../../etc/passwd | PASS | 終了コード 2 / 内容が漏れない: True |
| C088 | 危険なドメイン名を扱わない: ..%2f..%2fetc | PASS | 終了コード 2 / 内容が漏れない: True |
| C089 | 危険なドメイン名を扱わない: /etc/passwd | PASS | 終了コード 2 / 内容が漏れない: True |
| C090 | 危険なドメイン名を扱わない: a/../../b | PASS | 終了コード 2 / 内容が漏れない: True |
| C091 | test: 危険なドメイン名で実行しない | PASS | 終了コード 2 |
| C092 | 空のドメインを弾く | PASS | 終了コード 2 |
| C093 | sites: 続けて実行しても結果が変わらない | PASS | 2 回とも同じ |
| C094 | show: 冪等 | PASS | 2 回とも同じ |
| C095 | viewpoints: 冪等 | PASS | 2 回とも同じ |
| C096 | ロケールが C でも落ちない | PASS | 終了コード 0 |
| C097 | 読めない出力先でも落ちず理由を返す | PASS | 終了コード 0 / 出力先がありません: /proc/self/no-such |
| C098 | 壊れた report.json があっても一覧は落ちない | PASS | 終了コード 0 / 1 件（画面数は 0 で表示） |
| C099 | 共通オプションを 2 つ前置しても効く | PASS | 終了コード 0 |
| C100 | 共通オプションを 2 つ後置しても効く | PASS | 終了コード 0 |
## 検証で見つけて修正した不具合

| 見つかった箇所 | 内容 | 修正 |
|---|---|---|
| C065 | `--format nosuchformat` が終了コード 0 で終わり、成果物が 1 つも出ていないことに気づけなかった | `_parse_formats` が有効な形式ゼロなら、不明な指定と選択肢を示して終了コード 2 で止める |
| C092 | `show --domain ""` が出力先そのものを一覧して終了コード 0 を返し、成果物があるように見えた | `test` / `show` の入口でドメインとして扱えない指定（空文字・パス区切り・`..`・先頭ドット）を終了コード 2 で弾く |

いずれも回帰テストを追加済み（`tests/test_cli_mode.py` / `tests/test_main.py` / `tests/test_main_cli.py`）。

## テスト側の誤りとして修正したもの

| # | 内容 |
|---|---|
| C070 | `--require-login` の停止を `--max-pages 2` で検証していたが、上限に達してログイン画面に到達しないため前提が成立していなかった。上限と制限時間を引き上げて再検証。 |
