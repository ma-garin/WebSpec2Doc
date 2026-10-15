# docs

| フォルダ | 中身 |
|---|---|
| [guide/](guide/) | 利用者向けの手引き |
| [process/](process/) | 開発規約・品質・ADR |
| [plans/](plans/) | ロードマップ・計画 |
| [design/](design/) | 画面見本・機能仕様 |
| [research/](research/) | 調査（出典付き） |
| [sdlc/](sdlc/) | 工程別の納品文書 |
| [demo/](demo/) | 見本の出力 |

- 手引きは [guide/userguide.md](guide/userguide.md)（日本語の詳細は [guide/GUIDE_ja.md](guide/GUIDE_ja.md)）
- 完了の定義は [process/DEFINITION_OF_DONE.md](process/DEFINITION_OF_DONE.md)、テスト方針は [process/TESTING_STRATEGY.md](process/TESTING_STRATEGY.md)
- sdlc/ の docx は `scripts/build_delivery_docs.py` で md から作り直す。画面カタログは `scripts/screens/` で撮り直す（2026-10-15 に削除。生成物のため）
- 削除した文書は git の履歴にある（`git log --diff-filter=D --name-only -- docs`）
