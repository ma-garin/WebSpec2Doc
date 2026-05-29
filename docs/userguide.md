# WebSpec2Doc クイックスタートガイド

URL を渡すだけで QA テストインプット文書を自動生成するツール。

---

## セットアップ（初回のみ）

```bash
# 1. 仮想環境を作成
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 2. 依存パッケージをインストール
pip install -r requirements.txt

# 3. Playwright ブラウザをインストール
playwright install chromium
```

---

## 基本的な使い方

```bash
# 最小構成（Markdown 出力）
python src/main.py --url https://example.com

# HTML レポート付き
python src/main.py --url https://example.com --format md,html

# 深さ・ページ数を指定
python src/main.py --url https://example.com --depth 2 --max-pages 30

# 仕様ドリフト検知（前回クロールとの差分を出力）
python src/main.py --url https://example.com --compare
```

---

## オプション一覧

| オプション | デフォルト | 説明 |
|---|---|---|
| `--url` | 必須 | クロール対象 URL |
| `--depth` | `3` | リンクを辿る深さ（1〜3 推奨） |
| `--max-pages` | `50` | クロールする最大ページ数 |
| `--output` | `./output` | 出力先ディレクトリ |
| `--format` | `md` | 出力形式（`md` / `html` / `excel` をカンマ区切り） |
| `--compare` | off | 前回スナップショットとの差分を `diff_report.html` に出力 |

---

## 出力ファイル

実行後に `output/{ドメイン名}/` に以下が生成されます。

| ファイル | 内容 |
|---|---|
| `screens.md` | 画面一覧表（Markdown テーブル） |
| `forms.md` | フォーム・入力項目一覧 |
| `transition.mmd` | 画面遷移図（Mermaid 形式） |
| `report.html` | 上記をまとめたレポート＋スクリーンショット付き |
| `spec.xlsx` | Excel 仕様書（`--format excel` 指定時） |
| `screenshots/` | 各画面のスクリーンショット（PNG） |
| `diff_report.html` | 仕様ドリフト差分レポート（`--compare` 指定時） |

---

## よくある使い方

```bash
# テスト対象サイトのドキュメントを素早く作る
python src/main.py --url https://対象サイト.example.com --depth 2 --format md,html

# ページ数が多いサイトは上限を設定
python src/main.py --url https://大規模サイト.example.com --depth 1 --max-pages 20

# Excel も欲しいとき
python src/main.py --url https://example.com --format md,html,excel
```

---

詳細は [userManuel.md](./userManuel.md) を参照してください。
