# CI/CD への組み込み

WebSpec2Doc を利用者のプロジェクトの CI パイプラインへ組み込み、
**仕様ドリフトとテスト結果でビルドを通す／落とす**ための手引き。

`python src/cli.py ci gate` が判定の入口。クロールもテスト実行もせず、
`output/<domain>/` に残っている成果物だけを読んで合否を返す。

```bash
python src/cli.py ci gate --domain example.com \
  --fail-on breaking \
  --max-failed 0 \
  --junit-xml reports/webspec2doc-gate.xml
```

雛形: [`docs/guide/ci-templates/github-actions.yml`](ci-templates/github-actions.yml)
（利用者のリポジトリの `.github/workflows/` へコピーして使う）

## 判定に使う入力

| 入力 | 既定の場所 | 無いとき |
| --- | --- | --- |
| 仕様ドリフト | `output/<domain>/drift_summary.json` | 該当チェックを `skipped`（理由「未取得」）にする |
| テスト結果 | `output/<domain>/testcases/run_result.json`（無ければ `testcases/playwright_report.json` 等を順に探す） | 該当チェックを `skipped`（理由「未取得」）にする |

**判定材料が両方とも無い場合は合格にせず、終了コード 2 を返す。**
「見ていない」と「問題なし」を CI 上で取り違えないため。

## 終了コード

| コード | 意味 | CI での扱い |
| --- | --- | --- |
| 0 | 合格。しきい値を超える差分・失敗がない | ジョブ成功 |
| 1 | 完了したが失格。ドリフト検出またはテスト失敗 | ジョブ失敗（レビュー対象） |
| 2 | 実行エラー。判定材料がない・出力先を読めない | ジョブ失敗（設定を疑う） |
| 130 | 中止（タイムアウト・シグナル） | ジョブ中断 |

## オプション

| オプション | 既定 | 意味 |
| --- | --- | --- |
| `--domain` | 必須 | `output/` 配下のドメイン名 |
| `--fail-on` | `breaking` | 落とす重大度の下限（下表） |
| `--max-failed` | `0` | 許容するテスト失敗数。超えたら失格 |
| `--max-added` | `-1` | 追加画面数の上限。`-1` は無制限 |
| `--max-removed` | `-1` | 削除画面数の上限。`-1` は無制限 |
| `--junit-xml` | 空 | JUnit XML の書き出し先。CI のテストレポート表示に使う |
| `--json` | — | 判定結果を JSON で出す |

### `--fail-on` の意味

| 値 | 失格になる条件 |
| --- | --- |
| `none` | ドリフトでは落とさない（テスト結果だけで判定する） |
| `info` | info / warning / breaking のいずれかが 1 件以上 |
| `warning` | warning / breaking のいずれかが 1 件以上 |
| `breaking` | breaking が 1 件以上（既定。後方互換を壊す変更だけ止める） |
| `any` | `has_changes` が真（差分が 1 件でもあれば止める） |

初回実行（`first_run: true`）は比較対象が無いため、ドリフト判定は
`skipped` になり、その旨が理由に残る。

## 出力

- **標準出力**: `CI_SUMMARY:{...}` の 1 行（`exit_code` を含む機械可読サマリ）。
  ログを grep して外部へ通知するときに使う。
- **JUnit XML**: `--junit-xml` 指定時。チェック 1 件が testcase 1 件。
  失格は `<failure>`、判定できなかった項目は `<skipped>` になる。
- **ステップサマリ**: 環境変数 `GITHUB_STEP_SUMMARY` があれば、
  チェック一覧の表を Markdown で追記する（GitHub Actions のジョブ要約に出る）。

## GitLab CI

```yaml
webspec2doc-gate:
  image: python:3.12
  script:
    - pip install -r requirements.txt
    - python src/cli.py doc --url "$TARGET_URL" --format json --compare
    - python src/cli.py ci gate --domain "$TARGET_DOMAIN" --junit-xml gate.xml
  artifacts:
    when: always
    reports:
      junit: gate.xml
```

## Jenkins（Declarative Pipeline）

```groovy
stage('WebSpec2Doc ゲート') {
  steps {
    sh 'pip install -r requirements.txt'
    sh 'python src/cli.py doc --url "$TARGET_URL" --format json --compare'
    sh 'python src/cli.py ci gate --domain "$TARGET_DOMAIN" --junit-xml gate.xml'
  }
  post { always { junit 'gate.xml' } }
}
```

`sh` は非ゼロ終了コードでステージを失敗させる。ドリフト検出（1）を
警告扱いにしたい場合は `sh(returnStatus: true)` で受けて判断する。

## よくある落とし穴

- **前回のスナップショットを復元していない**と毎回 `first_run` になり、
  ドリフト判定が常にスキップされる。CI のキャッシュか artifact で
  `output/<domain>/` を持ち越す。
- **`--domain` は URL ではなくホスト名**。`output/` 配下のディレクトリ名と一致させる。
- テスト結果を出さない構成では `--fail-on` だけが効く。テスト側のチェックは
  `skipped` として XML とサマリに残るので、CI 上で気付ける。
