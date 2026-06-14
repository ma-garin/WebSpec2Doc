# WebSpec2Doc — 開発ガイド（エージェント向け）

URL を渡すと、稼働中の Web システムから **QA テスト分析インプット文書**（画面一覧・画面遷移・入力項目仕様・テスト条件・スクリーンショット）を自動生成する Python ツール。
第三者検証会社が「ドキュメントなし現場」で初日からテスト設計を始めるためのもの。

## 最優先ルール

実装・レビュー・UX評価・ペルソナ評価・戦略評価・完了報告の前に、必ず以下を読むこと。

- `.claude/rules/functional-integrity.md`
- `docs/process/functional-integrity-gate.md`
- `docs/process/claude-entrypoint.md`
- `quality/feature_contracts.yml`

完了前に、実行できない明確な理由がない限り以下を実行すること。

```bash
python scripts/quality_harness.py
make test
make verify-ui
```

`UI → API → backend route → service/core → output → persistence → error handling → user-visible evidence` を確認していない作業は、完了扱い禁止。

> 詳細な自走用ハンドブックは [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)、UI変更の必須フローは [AGENTS.md](AGENTS.md) を参照。
> テスト戦略: [docs/TESTING_STRATEGY.md](docs/TESTING_STRATEGY.md) / 完了定義: [docs/DEFINITION_OF_DONE.md](docs/DEFINITION_OF_DONE.md)
