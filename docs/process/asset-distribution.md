# 機能アセットの受け渡し（このリポジトリの役割）

作成日: 2026-08-29

開発は別環境でも進む。**このリポジトリの役割は「機能単位で作り込み、他環境へアセットを渡す」こと**に置く。
受け渡しのイメージは「実行履歴画面のフォルダを、そのまま渡す」。
本書はその運用手順と、なぜこの形にしたかを定める。

## 1. 受け渡しの単位は feature_id

単位は `quality/feature_contracts.yml` の `feature_id` に一致させる。新しい単位を作らない。

理由は 3 つ。

- **既にある。** 53 機能ぶん、UI / route / core のファイル一覧が登録済み。
- **完了判定と同じ単位。** `scripts/quality_harness.py` が同じ ID で機能の実行パスを見ている。
  渡す単位と完了を判定する単位がずれると、「渡したが未完成」が検出できない。
- **受け側でも使える。** 契約はそのまま受け側の完了判定に移植できる（第 5 節の注意を参照）。

**新しい機能を作り込んだら、まず契約に登録する。** 契約に無いものはアセットとして渡せない。

## 2. 受け渡しの形式: バンドル（manifest + SHA-256）

`scripts/export_feature_asset.py` が次の構造を出力する。

```
assets/
    README.md                          システム → 画面 → 機能の目次
    01_ドキュメント作成支援/
        実行履歴/
            差分 ・ 履歴 ・ 再クロール/
                PROMPT.md              受け側の AI へそのまま貼る指示文
                INTEGRATION.md         組み込み手順（配置・配線・依存・受け入れ確認）
                manifest.json          ファイル一覧・SHA-256・依存・提供API・警告
                contract.json          当該機能の契約
                files/                 ファイル実体。リポジトリ相対パスをそのまま保持
                    web/routes/history.py
                    static/js/view-run-history.js
                    templates/partials/view-run-history.html
                    ...
        _画面なし（API・基盤）/         画面を持たない機能はここへ
    02_AutoRun/
    03_テスト活動支援/
    04_共通/
```

### なぜこの形式が確実か

| 論点 | この形式での担保 |
|---|---|
| 受け側が配置先を間違える | `files/` がリポジトリ相対パスを保持。`rsync -a files/ <受け側>/` で終わる |
| 転送・展開で壊れる | 全ファイルの SHA-256 を manifest に持ち、受け側で照合できる |
| どの版か分からなくなる | 版 = `YYYYMMDD-<生成元の short sha>`。manifest に生成元リビジョンを記録 |
| 依存の伝え漏れ | 内部モジュール・サードパーティ・環境変数・呼び出す API を静的解析で棚卸し |
| 契約の登録漏れに気づかない | 対になるはずのテンプレート / CSS の未同梱を検出して警告に出す |
| 経路に縛られる | ディレクトリと tar.gz の両方。コピー / git / scp / 共有ストレージのどれでも同じ結果 |

別リポジトリへの push や submodule は採らない。権限・CI・履歴の同期という失敗点が増え、
受け渡しそのものより運用の面倒が大きい。バンドルは経路非依存なので、後から git に載せることもできる。

## 3. 送る側の手順（3 コマンド）

```bash
# 1. 機能を作り込んだら、契約に登録されているか点検する
make assets-audit

# 2. アセットを出す（assets/ 配下に出る。git 管理下なので zip に入る）
make assets F=diff_history

# 3. 出荷前に自分で検証してから、コミット & push
make assets-verify B=assets/diff_history/<版>
git add assets/ && git commit && git push
```

**警告が 0 になってから push する。** 警告は「渡した先で画面が出ない」に直結する。
作業ツリーが汚れていると manifest に `working_tree_dirty: true` が立つので、
**コミットしてからエクスポートする**。

## 4. 受け取る側の手順（zip → フォルダを開く → 貼る）

送る側がやることは push まで。受け側は次の 6 ステップで終わる。

1. GitHub からリポジトリの zip をダウンロードする
2. zip を解凍する
3. `assets/` を開き、**システム名のフォルダ**を選ぶ
   （`01_ドキュメント作成支援` / `02_AutoRun` / `03_テスト活動支援` / `04_共通`）
4. **画面名のフォルダ**を選ぶ（`設定` / `ダッシュボード` / `実行履歴` など。
   画面を持たない API・基盤の機能は `_画面なし（API・基盤）` にまとまっている）
5. **機能名のフォルダ**を選ぶ（`AIトークン利用管理` など）
6. そのフォルダの `PROMPT.md` を開き、中身をコピーして Codex / Claude Code に貼る

`assets/README.md` がシステム → 画面 → 機能の目次になっている。探すときはここから入る。

`PROMPT.md` はエクスポート時に自動生成される。次を含む。

- 検証コマンド（`verify_feature_asset.py <フォルダ> --against .`）と「`[NG]` なら配置するな」の指示
- 配置コマンド（`rsync -a <フォルダ>/files/ ./`）
- 配線は `INTEGRATION.md` 第 2 節を読ませる
- 受け入れ確認は `INTEGRATION.md` 第 5 節（**送り側では未実行**であることを明示）
- その機能固有の注意（同梱外の内部モジュール数・依存する他機能・必要な環境変数・残っている警告）

検証スクリプトは標準ライブラリだけで動くため、受け側に venv がなくても走る。

`--against` が報告する `[NG] 受け側に内部モジュールがない` は、**そのモジュールも渡す必要がある**
という意味。別の feature_id に属していれば、そのアセットも併せてエクスポートして push する。

### システム・画面の決まり方

手で対応表を保守しない。次の優先順位で機械的に決める。

1. 契約に `system` / `screen` を書いた場合はそれ（人が明示したものを最優先）
2. 契約の `ui_files` にある画面テンプレート
   → partial 内の `<section class="view" id="view-XXX">` の XXX
   → `templates/partials/nav.html` の `data-system` / ラベル
   （`view-ta-plan.html` が `test-plan` に対応するように、ファイル名からは導けない）
3. 画面が無ければ実装ファイルのパスと機能名（`web/routes/test_activity` → テスト活動支援 など）

1 機能が 3 画面以上にまたがる場合は、画面ではなくシステム直下の `_システム全体` に置く。

## 5. 渡してはいけないもの・そのまま使ってはいけないもの

`docs/common-assets-docs-vs-testlab.md` 第 3 節の判断をここでも守る。

| 対象 | 扱い |
|---|---|
| `feature_id` そのもの | **受け側の体系で付け直す。** 共通 ID にすると、完了判定が他方の変更で壊れる |
| AutoRun のステージ定義 | 基盤は共用してよいが、定義の混在は段階承認の意味を壊す |
| 「実行結果」の意味 | System 01 は文書生成の成果物、System 02 はテストの PASS/FAIL。統合しない |
| 認証・テナント（`web/auth.py` / `web/tenancy.py`） | 横断部品であって機能ではない。アセットではなく受け側の基盤として先に用意する |

## 6. この仕組みが確認していないこと

エクスポータが行うのは**静的解析による棚卸し**である。次は確認していない。

- 動的 import・文字列組み立てで作られる URL・実行時にのみ解決される参照（検出できない）
- 受け側での実際の動作（pytest / verify-ui / 実画面操作はいずれも **未実行**。
  `.claude/rules/speed-harness.md` H-7 に従い、ユーザーが要求したときだけ実行する）

**受け入れ確認は受け側の責任範囲。** INTEGRATION.md 第 5 節（出力・永続化・失敗経路・対応テスト）を
実際に踏んで初めて完了とする。`.claude/rules/functional-integrity.md` の
「UI → API → backend route → service/core → output → persistence → error handling → user-visible evidence」
を通していないものを「渡した＝完了」と report しない。

## 7. 現状（2026-08-29 時点・全 53 機能を実際にエクスポートした実測）

| 状態 | 機能数 |
|---|---:|
| 警告なし（そのまま渡せる） | 50 |
| 警告あり（渡す前に確認が要る） | 3 |

残っている 3 件:

| feature_id | 内容 | 判断 |
|---|---|---|
| `condition_run_status` | 画面 HTML が同梱にも共通資産にも見当たらない（`view-design.js` は `templates/index.html` から直接読み込まれ、専用の partial を持たない） | 渡す前に、どの画面に載る機能かを確認する |
| `evidence_pack` | 同上（`autorun.js`） | 同上 |
| `diff_severity` | `src/generator/diff_reporter.py` が Python 3.11 では構文解析できない（f-string 内のバックスラッシュ。3.12 以降は解析できる）。このファイル分の依存抽出が抜ける | 3.12 以降でエクスポートすれば解消する |

### 着手時に見つかった契約の登録漏れ（修正済み）

「実行履歴画面のフォルダを渡す」を実際に試したところ、`diff_history` の契約に
**画面テンプレートと主要 JS が登録されていなかった**。フォルダとして渡しても画面が出ない状態だった。

| 機能 | 追加したファイル |
|---|---|
| `diff_history` | `templates/partials/view-run-history.html` / `view-run-result.html` / `static/js/view-run-history.js`（24KB） |
| `account_auth` | `templates/auth/_shell.html`（認証画面 4 枚が extends する共通レイアウト） |
| `autorun_stage_approval` | `static/css/autorun-review.css` |

## 8. 構造的な原因と、残っている宿題

登録漏れが起きたのは注意力の問題ではなく、**ゲートが UI ファイルを見ていない**ため。

`scripts/quality_harness.py` の `_validate_all_modules_registered()` は
`FEATURE_SOURCE_ROOTS = ("src", "web/routes", "web/services")` の **`.py` だけ**を対象にしている。
テンプレート・JS・CSS はどの契約にも登録されていなくてもゲートが通る。
機能単位で渡そうとした時点で初めて「画面が出ない」が露見する。

現状を測るコマンドを用意した。

```bash
make assets-audit
```

2026-08-29 時点の実測: **登録済み 307 件に対し、未登録の UI ファイルが 36 件（約 390KB）**。
参照元テンプレートも併記されるので、次の 2 つに仕分けできる。

- **機能に属するもの** → `quality/feature_contracts.yml` の `ui_files` へ登録する
- **複数機能から参照される共通基盤**（`static/css/components.css` / `static/js/view-utils.js` /
  `table-utils.js` / `events.js` / `templates/index.html` / `templates/partials/nav.html` など）
  → 機能アセットではない。**受け側へ先に渡す土台**として別扱いにする

宿題（本書では未実施）:

1. 未登録 36 件の仕分けと登録
2. 仕分け後、`quality_harness.py` に UI ファイルの登録チェックを追加してゲート化する
   （先にゲート化すると、仕分けが終わるまでハーネスが赤のままになる）
3. 共通基盤を「基盤アセット」として切り出し、機能アセットの前提として渡せるようにする
