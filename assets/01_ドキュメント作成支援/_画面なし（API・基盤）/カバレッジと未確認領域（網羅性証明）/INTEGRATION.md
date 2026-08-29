# 組み込み手順: カバレッジと未確認領域（網羅性証明）

| 項目 | 値 |
|---|---|
| feature_id | `coverage_gap_report` |
| 版 | `20260829-34d52a3` |
| 生成元 | `WebSpec2Doc` @ `34d52a3` |
| 生成日時 (UTC) | 2026-08-29T09:32:20Z |
| リスク / 状態 | medium / implemented |
| 同梱ファイル数 | 6 |
| 生成時の作業ツリー | **未コミットの変更あり**（再現性が落ちる。コミット後の再生成を推奨） |

## 0. 先に検証する

配置の前にバンドルの完全性を確認する。SHA-256 が 1 つでも合わなければ、
転送か展開が壊れているので配置しない。

```bash
python3 scripts/verify_feature_asset.py <このディレクトリ>
# 受け側リポジトリの依存充足も見る場合
python3 scripts/verify_feature_asset.py <このディレクトリ> --against <受け側リポジトリのルート>
```

## 1. ファイルを配置する

`files/` 配下は **リポジトリ相対パスをそのまま保持** している。配置先はパスそのもの。

```bash
rsync -a files/ <受け側リポジトリのルート>/
```

### サービス / コア（6 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `src/generator/coverage_gap.py` | 8041 | `400019b64b70` |
| `src/generator/html_reporter.py` | 54598 | `2e1e13c1f799` |
| `src/crawler/page_crawler.py` | 61123 | `e90a414ce2be` |
| `src/generator/comparison_reporter.py` | 14977 | `77c0f977bf47` |
| `web/services/traceability.py` | 5932 | `4a8aa5b435ba` |
| `src/health/technical_health.py` | 2307 | `6622385cea76` |

## 2. 配線する

### 2-1. Blueprint を登録する

- このアセットに Blueprint は含まれない（登録作業なし）。

### 2-3. 機能契約を登録する

受け側でも完了判定を機械化する場合は、`contract.json` の内容を受け側の
`quality/feature_contracts.yml` の `features` に追加する。
**feature_id はそのまま流用せず、受け側の体系で付け直す**
（`docs/common-assets-docs-vs-testlab.md` 第 3 節: 契約の形式は共用してよいが中身は各システム固有）。

## 3. 同梱していない依存（受け側に必要なもの）

ここが埋まらないとアセットは動かない。配置前に 1 つずつ確認する。

### 3-1. 内部モジュール（同梱外）

同梱ファイルが import しているが、このアセットには含まれないもの。
受け側に同名・同パスで実在する必要がある。

- `src/analyzer/html_analyzer.py`
- `src/analyzer/login_wall.py`
- `src/analyzer/stack_detector.py`
- `src/analyzer/test_conditions.py`
- `src/crawler/action_explorer.py`
- `src/crawler/link_extractor.py`
- `src/crawler/network_interceptor.py`
- `src/crawler/parallel_crawler.py`
- `src/crawler/performance_probe.py`
- `src/crawler/playwright_runtime.py`
- `src/crawler/politeness.py`
- `src/crawler/session_guard.py`
- `src/crawler/spa_monitor.py`
- `src/crawler/url_safety.py`
- `src/diff/comparison.py`
- `src/generator/architecture_generator.py`
- `src/generator/test_design.py`
- `src/ux/axe_runner.py`

### 3-2. サードパーティ

| import 名 | requirements の指定 |
|---|---|
| `networkx` | networkx==3.3 |
| `playwright` | playwright==1.61.0 |

### 3-3. 環境変数

- なし

### 3-4. 呼び出す API（受け側に実在が必要）

- なし

### 3-5. データファイル

- なし

### 3-6. 同梱外のテンプレート / 静的ファイル参照

- なし

### 3-7. 同梱 JS が参照するグローバル

他アセット由来のものが混ざっていれば、そのアセットも併せて受け渡す。

- なし

## 3-8. 併せて渡す必要のある他機能の資産

このアセットと対で動くが、**別の機能契約に属している**ファイル。
受け側に無ければ、その機能のアセットも別途エクスポートして渡す。

- なし

## 4. このアセットが提供する API

- なし

## 5. 受け入れ確認（契約より）

組み込み後、受け側で次を確認する。**本バンドルの生成時には実行していない。**

### 出力

- `report.html「カバレッジと未確認領域」節`
- `comparison.html「網羅性サマリ」節`

### 永続化

- なし

### 失敗経路（すべて実際に踏むこと）

- audit_log_missing
- audit_log_corrupt_line
- coverage_missing
- comparison_json_missing
- stale_crawl_started_records

### 対応テスト

- `happy_path`
- `empty_path`
- `evidence`

## 6. 未検証事項（エクスポート側の申告）

- 本バンドルの依存一覧は **静的解析による棚卸し**。動的 import・文字列組み立てによる
  URL・実行時にのみ解決される参照は検出できない。
- 実行検証（pytest / verify-ui / 実画面操作）は **未実行**
  （`.claude/rules/speed-harness.md` H-7 に従い、要求時のみ実行する）。
- 受け側での組み込み後の動作確認は **受け側の責任範囲**。第 5 節を実行して初めて完了とする。
