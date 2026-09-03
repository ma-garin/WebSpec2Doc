# プロンプトライブラリ

WebSpec2Doc の URL → テスト設計・テストケース生成ロジックを分解し、
ChatGPT / Claude のチャットで同等の成果物を得るためのプロンプト集。

| ファイル | 用途 |
|---|---|
| `url-to-testdesign-prompts.md` | 原本。GitHub・社内 wiki 用（表組みそのまま） |
| `note-article.md` | note 限定公開記事への貼り付け用（表を箇条書きへ変換済み） |

`note-article.md` は原本から生成する。原本を直したら次を実行して再生成する。

```bash
python3 scripts/prompt_library/build_note_article.py docs/prompt-library/note-article.md
```

## 内容の出所

プロンプトに埋め込んだ変換ルール・文言テンプレート・既定値は、次の実装に準拠している。
実装を変えたときはプロンプト側も追随させること。

| プロンプト | 準拠する実装 |
|---|---|
| P0 共通ルール | `src/llm/prompt_guard.py`（QA_PRINCIPLES / untrusted_block） |
| P1 画面棚卸し・P2 画面仕様化 | `src/crawler/link_extractor.py`, `src/analyzer/canonicalizer.py` |
| P3 テスト観点 | `src/llm/viewpoint_generator.py`, `data/viewpoint_templates/*.json` |
| P4 テスト条件 | `src/analyzer/test_conditions.py` |
| P5 境界値 | `src/analyzer/bva.py` |
| P6 デシジョンテーブル・P7 ペアワイズ | `src/generator/test_design.py`, `src/techniques/combinatorial.py` |
| P8 遷移図・遷移テスト | `src/generator/mermaid_generator.py`, `src/graph/state_table.py` |
| P9 テストケース表 | `src/generator/testcase_table.py` |
| P10 メタモルフィック | `src/mbt/metamorphic.py` |
| P11 未確認領域 | `src/generator/coverage_gap.py` |
| P12 テスト計画 | `src/generator/test_plan_generator.py` |
| 画面種別・優先度 | `src/llm/screen_classifier.py` |
| 認証壁の判定 | `src/analyzer/login_wall.py` |
