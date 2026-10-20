# Technical Completion Gate

判定: **COMPLETE**

完成度: **100%**（現行スコープ。法務・LICENSE・脆弱性窓口は対象外）

対象: main 0d4d855（#308）＋本 PR。Ghidra/native・Security・Auth・Product Truth 全体・GUI Wave2〜5・主要 5 フローは再監査していない（No-op Gate）。

## Tests

| 種別 | 結果 |
|---|---|
| Unit | 4091 件成功・**失敗 0 件**・6 件スキップ（理由はすべて明記。PostgreSQL 未起動 2 件、root 環境 2 件、未認証の性能基準 1 件、実 REA 未導入 1 件） |
| E2E | 142 件成功・**失敗 0 件**・44 件スキップ。うち 42 件は「解析済みサイトが必要」で、`WEBSPEC2DOC_E2E_DOMAIN=127.0.0.1:8767` を指定すると 42 件すべて成功。残る 2 件はスキップ理由を明記済み（K1 の専用シナリオ、ST-013 のセレクタ未確定） |
| Browser | PASS（AutoRun・結果表示・System02 の実行中 KPI を 816 / 1024 / 1280 で確認。横スクロール 0、JS エラー 0、再読み込み・戻るも確認） |
| 見切れ | 0 件（`scripts/check_clipping.py`、26 画面 × 2 幅） |

## Fixed

| 残件 | 分類 | Before | After |
|---|---|---|---|
| E2E：AutoRun の「設定」が 2 つある（9 件） | 製品の不具合 | 全体設定（ナビ）と、静的候補探索の「対象ドメインを決める」ボタンが同じ「設定」というラベルだった | 後者を「対象サイトに指定」に変更。表示中のボタンにラベルの重複は無い |
| E2E：設定画面の上に結果パネルが出る（1 件） | 製品の不具合 | `showResults` の取得失敗経路だけが、所属する画面への移動をせずにパネルを出していた | 成功経路と同じ `_revealResultPanel()` を通す。設定画面にいても、パネルは所属する画面（generate）で開く |
| System02 の実行中 KPI | 製品の不具合（Product Truth に関わる） | 実行状況 API の `passed` / `failed` を、画面は `pass` / `fail` で数えていた。そのため実行中は KPI が 0 のままで、失敗したテストの行も既定の「成功」表示に落ちていた | ステータスを正規化した。実行中の KPI は帯と同じ「今回の実行」を数え、不安定は「—（完了後に判定）」、残りは「実行待ち」と出す。27 回の実測で帯と KPI の不一致 0、完了後と再読み込み後も一致 |
| 観点ストアの同時初期化 | 製品の不具合 | スキーマ移行と seed の「無ければ作る」が、別の接続と同時に走ると UNIQUE 競合になった（単一プロセス内のスレッドでも発生。失敗率 6〜9/15） | 初期化の全体を、DB と同じ場所のロックファイル（`fcntl.flock`）で直列化した。20 回連続で失敗 0 |
| Unit：`healing_demo::test_add` | 意図した挙動 | 実証用にわざと失敗させるテストが、通常のテスト結果に混ざっていた | `norecursedirs` で通常の収集から外した。実証するときは `pytest tests/healing_demo` とパスを指定する（従来どおり 1 件失敗する） |
| Unit：`test_notify_drift` のワークフロー 2 件 | 陳腐化したテスト | CI 禁止の方針で削除した `.github/workflows/*.yml` を読んでいた | 2 件を削除した。通知そのもののテスト 3 件は残っている |
| Unit：`test_reverse_analysis_cli[unreadable_dir]` | 環境の問題 | root では chmod 000 が効かず、誤って失敗していた | root のときだけ理由を付けてスキップする（隣の `iterdir_error` ケースが同じ例外経路を検証する） |
| Unit：`test_viewpoint_store_concurrency` | 製品の不具合 | 上記の同時初期化と同じ | 上記の修正で解消 |

## Explicit limitations

- サポートする運用構成は単一プロセス（runbook §1）。観点ストアの初期化は複数プロセスでも安全になったが、サポート範囲は広げていない。
- TLS 終端はリバースプロキシで行う。
- ファイルロックを使うのは POSIX（Linux/macOS）のみ。Windows ではプロセス内のロックだけになる（単一プロセス運用なら足りる）。
- スコープ外：Ghidra / native・Android・.NET の解析。

## Remaining known bugs

0 件。

## Final assessment

技術 P0 = 0、P1 = 0。通常の Unit と E2E の FAIL はどちらも 0 件で、残るスキップにはすべて理由がある。AutoRun の既知 P2 は解消し、System02 の KPI は実行中も完了後も帯と同じ意味で表示される。観点ストアのサポート範囲は単一プロセスに確定し、その範囲内の競合も解消した。現行スコープの WebSpec2Doc は、システムとして完成している。

実行環境の注記：Chromium はコンテナに入っている 1194 を、Playwright 1.61 が期待する 1228 として scratchpad にリンクして使った。
