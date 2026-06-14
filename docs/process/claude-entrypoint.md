# Claude Entrypoint

Claude Code は、実装・レビュー・評価・完了報告の前に以下を参照します。

- `.claude/rules/functional-integrity.md`
- `docs/process/functional-integrity-gate.md`
- `quality/feature_contracts.yml`

完了前に以下を実行します。

```bash
python scripts/quality_harness.py
make test
make verify-ui
```

機能整合性ゲートに失敗した場合、完了報告は禁止です。

## CLAUDE.mdとの関係

`CLAUDE.md` はプロジェクト全体の要約です。
このファイルは Functional Integrity Gate への入口です。

本文は `CLAUDE.md` に重複させず、以下に分離します。

- Claude向け行動ルール: `.claude/rules/functional-integrity.md`
- 人間/AI共通プロセス: `docs/process/functional-integrity-gate.md`
- 機能契約: `quality/feature_contracts.yml`
- 自動検査: `scripts/quality_harness.py`
