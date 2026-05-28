# WebSpec2Doc

**URL → QA テストインプット文書 自動生成ツール**

公開 Web サービスの URL を渡すだけで、QA エンジニアがテスト設計を始めるために必要な文書を自動生成します。

> 「ドキュメントがないので、まず触って覚えてください」という現場でも、初日からテスト設計を始められる状態を実現します。

---

## 生成できる文書

| ファイル | 内容 |
|---------|------|
| `screens.md` | 全画面の URL・タイトル・フォーム数・遷移先 |
| `forms.md` | フォーム・入力フィールド一覧（型・必須・placeholder） |
| `transition.mmd` | 画面遷移図（Mermaid 形式） |
| `report.html` | 上記すべて＋スクリーンショットをまとめた HTML レポート |
| `spec.xlsx` | Excel 仕様書（TestRail / Jira 転記用） |
| `screenshots/` | 各画面のスクリーンショット（PNG） |

---

## セットアップ

```bash
git clone https://github.com/ma-garin/WebSpec2Doc.git
cd WebSpec2Doc

python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

pip install -r requirements.txt
playwright install chromium
```

---

## 使い方

```bash
# 最小構成（Markdown 出力）
python src/main.py --url https://example.com

# HTML レポート付き（推奨）
python src/main.py --url https://example.com --format md,html

# 全オプション指定
python src/main.py \
  --url https://example.com \
  --depth 2 \
  --max-pages 30 \
  --output ./output \
  --format md,html,excel
```

### オプション一覧

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| `--url` | 必須 | クロール対象 URL |
| `--depth` | `3` | リンクを辿る深さ |
| `--max-pages` | `50` | クロールする最大ページ数 |
| `--output` | `./output` | 出力先ディレクトリ |
| `--format` | `md` | 出力形式（`md` / `html` / `excel` をカンマ区切り） |

出力先は `{output}/{ドメイン名}/` に生成されます。

---

## ドキュメント

- [クイックスタートガイド](docs/userguide.md)
- [ユーザーマニュアル（詳細版）](docs/userManuel.md)

---

## 制約事項

- ログインが必要なページは対象外
- 対象は公開されている Web ページのみ
- robots.txt に従いクロールをスキップする場合あり

---

## 技術スタック

| 用途 | ライブラリ |
|------|-----------|
| ブラウザ自動操作 | [Playwright](https://playwright.dev/python/) |
| グラフ処理 | [networkx](https://networkx.org/) |
| Excel 出力 | [openpyxl](https://openpyxl.readthedocs.io/) |
| テスト | pytest（カバレッジ 85%） |

- Python 3.11+

---

## ライセンス

MIT
