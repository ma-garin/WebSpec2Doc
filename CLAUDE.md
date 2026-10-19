# WebSpec2Doc — 開発ガイド（エージェント向け）

## トークン消費（最上位・2026-09-21 実測）

実測で cache_read 244M の実質すべてが**自分の過去出力の再読**だった。
再読総量 ≒ 平均出力 × ターン数² / 2。平均出力 1,312 → 400 トークンで**総消費 74% 減**。

1. 1 ターンの出力を減らす（報告 3 行・表 1 個・選択肢を列挙しない・相槌と前置きを書かない）
2. ターン数を減らす（確認のための往復を作らない。結論を変えない調査を実行しない）
3. 常時ロードのファイルを削る　4. 設定を調整する（数 % 未満・最後）

**聞かれた粒度で答える（0 番・上の 1〜3 より先）。**一行で済む質問には一行で返す。
問われていない背景・前提・補足・使い分け・代替案を足さない。判断を求められた時だけ判断軸を出す。
「〜とは」には定義を 1〜2 行で返し、内部構造や採否の話に広げない。

**CI と自己ウェイクは厳禁**（`.claude/rules/no-ci-no-wakeup.md`・フックが物理的に拒否する）。
根拠と検証手順は `docs/process/token-economics.md`。

## 最初に（複数セッションが同居している）

**この作業ツリーは複数の Claude セッションが同時に使う。**着手前に必ず `git pull --ff-only`
してからブランチを切る。開発サーバ 8765 は共有なので、自分の検証は `WEBSPEC2DOC_PORT=8766`
以降で別ポートに立てる。`git status` に自分が触っていない変更が出ていたら他セッションのもの。
触らない・退避しない・commit しない。詳細は `.claude/rules/speed-harness.md` の H-9。

## CI 厳禁・自己ウェイク厳禁（他のどの規約よりも優先する）

`.claude/rules/no-ci-no-wakeup.md` を順守する。2026-09-21 のインシデント（1 時間ごとの
自己チェックインが Fable の週間上限を月曜に使い切らせた）を受けた最上位の規約。

- `.github/workflows/` を作らない・復活させない。CI の提案もしない
- `send_later` / `create_trigger` / `CronCreate` / `ScheduleWakeup` / `/loop` / PR 購読を使わない
- 「監視します」「1 時間後に確認します」と言わない
- 手元で実行できない検証は **「未検証」と明記して納品する**。仕組みで代替しない

`.claude/hooks/block-ci.py` がツール実行の段で物理的に拒否する。

## 開発速度（着手前に必ず読む）

最重要は次の 3 つ。これで足りる。`AGENTS.md` と
`docs/process/speed-harness-history.md` は**必要になった時だけ**開く
（全文を読む往復そのものが数十万トークンになる）。

1. **実装の前に実データを 1 回叩く**（S-1）。手戻りの最大要因。着手 2〜3 分 vs 手戻り 15〜25 分。
2. **pytest / make test / make verify-ui / make lint はユーザーが要求した時のみ実行する**（H-7・2026-08-22）。
   コミットは `--no-verify` で直行する。無断のゲート実行はフック（.claude/hooks/block-gates.py）が物理的に拒否する。
3. **検証を省いた箇所は「未実行」と明記して納品する。**黙って省くのと明示して省くのは別物。

加えて `.claude/rules/speed-harness.md` を順守する。
サーバ起動・認証オフ・検証の型・委譲の型・標準コマンドは**そこからコピーし、その場で探索しない**。

## 自己点検（実行で確認する。文章を信用しない）

```bash
python3 scripts/selftest/test_block_ci.py   # CI 厳禁フックが生きているか（52 件）
python3 scripts/token_report.py             # このセッションの消費構造を実測
```

## 作業場所（重要）

このリポジトリの正本は `/Users/fujimagariyuki/dev/active/webspec2doc`。セッションは必ずこのディレクトリで開く。
旧コピー（`Desktop/app/014_WebSpec2Doc`・`Desktop/app/WebSpec2Doc`・`~/WebSpec2Doc`・`Desktop/app_開発/WebSpec2Doc`）は2026-07-03に統合済み・参照禁止。014の未マージ作業は `rescue/014-worktree-20260703` ブランチに保全されている。

## Functional Integrity Gate

Before implementation, review, UX evaluation, persona evaluation, strategy review, or completion judgment, read:

- `.claude/rules/functional-integrity.md`
- `docs/process/functional-integrity-gate.md`
- `docs/process/claude-entrypoint.md`
- `quality/feature_contracts.yml`

Run the gates below ONLY when the user explicitly asks for them (H-7).
Otherwise deliver with the untested parts explicitly marked 未実行/未検証:

```bash
python scripts/quality_harness.py   # 要求時のみ
make test                           # 要求時のみ
make verify-ui                      # 要求時のみ
```

Do not mark work complete unless the execution path has been checked:

```text
UI -> API -> backend route -> service/core -> output -> persistence -> error handling -> user-visible evidence
```

This file is only the entrypoint. Detailed functional integrity rules live in the files above.

## サーバ起動（必須）

**`app.py` の起動は必ず `FLASK_TESTING=1` を付ける。**付けないと起動のたびに `webbrowser.open` でユーザーのブラウザにタブが増える。

正: `FLASK_TESTING=1 WEBSPEC2DOC_ALLOW_LOCAL=1 nohup venv/bin/python app.py &`
