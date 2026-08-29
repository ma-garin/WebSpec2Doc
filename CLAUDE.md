# WebSpec2Doc — 開発ガイド（エージェント向け）

## 開発速度（着手前に必ず読む）

`AGENTS.md` の「開発速度の規律」を順守する。2026-08-01 の実測から特定した無駄への対処。

最重要は次の 3 つ:

1. **実装の前に実データを 1 回叩く**（S-1）。手戻りの最大要因。着手 2〜3 分 vs 手戻り 15〜25 分。
2. **pytest / make test / make verify-ui / make lint はユーザーが要求した時のみ実行する**（H-7・2026-08-22）。
   コミットは `--no-verify` で直行する。無断のゲート実行はフック（.claude/hooks/block-gates.py）が物理的に拒否する。
3. **検証を省いた箇所は「未実行」と明記して納品する。**黙って省くのと明示して省くのは別物。

加えて `.claude/rules/speed-harness.md`（2026-08-22 実測）を順守する。
サーバ起動・認証オフ・検証の型・委譲の型・標準コマンドは**そこからコピーし、その場で探索しない**。

## このリポジトリの役割（2026-08-29 ユーザー指示）

開発は別環境でも進む。**このリポジトリは「機能単位で作り込み、他環境へアセットを渡す」場**とする。
受け渡しのイメージは「実行履歴画面のフォルダを、そのまま渡す」。

- 受け渡しの単位は `quality/feature_contracts.yml` の `feature_id`。新しい単位を作らない。
- **機能を作り込んだら、必ず契約に登録する。**契約に無いものはアセットとして渡せない。
  UI（テンプレート・JS・CSS）も `ui_files` に登録する。ハーネスは `.py` しか見ていないため、
  登録漏れはゲートを素通りし、渡した先で「画面が出ない」になる。
- 手順・形式・受け側の検証方法 → `docs/process/asset-distribution.md`

```bash
make assets-list                  # 渡せる機能の一覧
make assets F=<機能ID>            # 1 件エクスポート（dist/assets/ に出る）
make assets-verify B=<バンドル>   # 出荷前 / 受け入れ時の検証（SHA-256 照合）
make assets-audit                 # 契約に未登録の UI ファイルを洗い出す
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
