# WebSpec2Doc — 開発ガイド（エージェント向け）

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

`AGENTS.md` の「開発速度の規律」を順守する。2026-08-01 の実測から特定した無駄への対処。

最重要は次の 3 つ:

1. **実装の前に実データを 1 回叩く**（S-1）。手戻りの最大要因。着手 2〜3 分 vs 手戻り 15〜25 分。
2. **pytest / make test / make verify-ui / make lint はユーザーが要求した時のみ実行する**（H-7・2026-08-22）。
   コミットは `--no-verify` で直行する。無断のゲート実行はフック（.claude/hooks/block-gates.py）が物理的に拒否する。
3. **検証を省いた箇所は「未実行」と明記して納品する。**黙って省くのと明示して省くのは別物。

加えて `.claude/rules/speed-harness.md`（2026-08-22 実測）を順守する。
サーバ起動・認証オフ・検証の型・委譲の型・標準コマンドは**そこからコピーし、その場で探索しない**。

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
