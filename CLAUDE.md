# WebSpec2Doc — 開発ガイド（エージェント向け）

## 開発速度（着手前に必ず読む）

`AGENTS.md` の「開発速度の規律」を順守する。2026-08-01 の実測から特定した無駄への対処。

最重要は次の 3 つ:

1. **実装の前に実データを 1 回叩く**（S-1）。手戻りの最大要因。着手 2〜3 分 vs 手戻り 15〜25 分。
2. **`make verify-ui` はコミット直前の 1 回だけ**（S-2）。途中実行はハッシュ照合で無効になる。
3. **コミット直前の `make test` は流さない**（S-3）。pre-commit が同じものを実行する。

ゲート自体は省略しない。減らすのは**重複実行と手戻り**であって、検証ではない。

## 作業場所（重要）

このリポジトリの正本は `/Users/fujimagariyuki/dev/active/webspec2doc`。セッションは必ずこのディレクトリで開く。
旧コピー（`Desktop/app/014_WebSpec2Doc`・`Desktop/app/WebSpec2Doc`・`~/WebSpec2Doc`・`Desktop/app_開発/WebSpec2Doc`）は2026-07-03に統合済み・参照禁止。014の未マージ作業は `rescue/014-worktree-20260703` ブランチに保全されている。

## Functional Integrity Gate

Before implementation, review, UX evaluation, persona evaluation, strategy review, or completion judgment, read:

- `.claude/rules/functional-integrity.md`
- `docs/process/functional-integrity-gate.md`
- `docs/process/claude-entrypoint.md`
- `quality/feature_contracts.yml`

Before marking work complete, run when possible:

```bash
python scripts/quality_harness.py
make test
make verify-ui
```

Do not mark work complete unless the execution path has been checked:

```text
UI -> API -> backend route -> service/core -> output -> persistence -> error handling -> user-visible evidence
```

This file is only the entrypoint. Detailed functional integrity rules live in the files above.
