# WebSpec2Doc

**URL → QA テストインプット文書 自動生成ツール**

公開 Web サービスの URL を渡すだけで、QA エンジニアがテスト設計を始めるために必要な文書を自動生成します。

## 生成できる文書

| 文書 | 内容 |
|------|------|
| 画面一覧表 | 全画面の URL・タイトル・主要要素・遷移先 |
| 画面遷移図 | Mermaid 形式のフローチャート |
| 入力項目一覧 | フォーム・入力フィールドの一覧と推定バリデーション |
| 画面仕様書（LLM オプション） | 各画面の目的・操作・テスト観点 |

## セットアップ

```bash
git clone <this-repo>
cd 008_CrateSpec2HTML
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
# .env を編集して ANTHROPIC_API_KEY を設定（--llm オプション使用時のみ必要）
```

## 使い方

```bash
# シンプルに使う（LLM なし・無料）
python src/main.py --url https://example.com

# LLM 解析付き（各画面の目的・テスト観点を AI が推定）
python src/main.py --url https://example.com --llm

# 詳細オプション
python src/main.py \
  --url https://example.com \
  --depth 3 \          # クロール深さ（デフォルト: 3）
  --max-pages 50 \     # 最大ページ数（デフォルト: 50）
  --output ./output \  # 出力先ディレクトリ
  --llm \              # AI 解析を有効化
  --format html,md,excel  # 出力形式（カンマ区切り）
```

## 制約事項

- ログインが必要なページは対象外
- JavaScript を多用する SPA は一部未対応の場合あり
- 対象は公開されている Web ページのみ

## 技術スタック

- Python 3.11+
- Playwright（ブラウザ自動操作）
- networkx（グラフ処理）
- Claude API / Haiku（LLM 解析オプション）
- Jinja2（HTML テンプレート）
- openpyxl（Excel 出力）

## ライセンス

社内利用限定
