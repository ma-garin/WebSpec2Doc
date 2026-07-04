# WebSpec2Doc — 開発ガイド（エージェント向け）

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
