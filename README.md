# WebSpec2Doc

**URL → QA テストインプット文書 自動生成ツール**

稼働中の Web システムの URL を渡すだけで、QA エンジニアがテスト設計を始めるために必要な文書を自動生成します。

> 「ドキュメントがないので、まず触って覚えてください」という現場でも、初日からテスト設計を始められる状態を実現します。

---

## 主な機能

| 機能 | 説明 |
|------|------|
| **画面仕様の自動生成** | 入力フィールド・制約・ロケータ候補・テスト条件を画面ごとに整理 |
| **テスト設計技法の推奨** | 同値分割・境界値分析・デシジョンテーブル等を画面要素から自動判定 |
| **画面遷移図・遷移表** | UML 遷移図（シーケンス図・コミュニケーション図・アクティビティ図・テスト観点マップ）＋ ISTQB 標準の画面遷移表 |
| **仕様ドリフト検知** | 再クロールで前回との差分（追加/削除/変更）を自動検出 |
| **自動ログイン** | ID/PASSWORD をGUIで入力し、認証が必要なサイトにも対応 |
| **スクリーンショット** | 全画面のキャプチャを仕様と並べて表示 |

---

## 生成できる成果物

| ファイル | 内容 |
|---------|------|
| `report.html` | 画面別仕様・テスト条件・スクリーンショット付きレポート |
| `report.json` | 構造化 JSON（自動化・CI 連携用） |
| `spec.xlsx` | Excel 仕様書（TestRail / Jira 転記用） |
| `screens.md` / `forms.md` | Markdown 形式の画面・フォーム一覧 |
| `transition.mmd` | 画面遷移図（Mermaid 形式） |
| `report.pdf` | PDF 版レポート |
| `diff_report.html` | 仕様ドリフト差分レポート（`--compare` 時） |
| `screenshots/` | 各画面のスクリーンショット（PNG） |

---

## セットアップ

```bash
git clone https://github.com/ma-garin/WebSpec2Doc.git
cd WebSpec2Doc

# Python は 3.12 を使う（3.13 は greenlet がビルド失敗するため非対応）
python3.12 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

pip install -r requirements.txt
playwright install chromium
make setup-hooks    # pre-commit フックをインストール（品質ゲート有効化）
make test           # 動作確認
```

---

## GUI で使う（推奨）

```bash
python app.py   # → http://127.0.0.1:8765 が開く
```

### 4ステップで使えます

```
ステップ1 解析    → URL を入力して「画面分析」。N件の画面を検出
ステップ2 条件設定 → 取得する画面を選択・ログイン設定・差分オプション
ステップ3 実行    → クロール中はライブプレビューで進捗確認
ステップ4 レポート → 8つのタブで成果物を確認・エクスポート
```

#### 認証が必要なサイト

画面分析でログインが必要な画面を検出すると、画面リストの直下に「要ログイン」バッジとともに ID/PASSWORD 入力フォームが自動表示されます。「ログイン」ボタンを押すと自動ログインして認証後ページを含めた再解析が実行されます。パスワードはセッション確立後に即破棄され、保存されません。

---

## CLI で使う

```bash
# 最小構成
python src/main.py --url https://example.com

# HTML レポート付き（推奨）
python src/main.py --url https://example.com --format md,html,excel,json

# 仕様ドリフト検知
python src/main.py --url https://example.com --compare

# ログインセッション保存（認証後ページ対応）
python src/main.py --login https://example.com/login
python src/main.py --url https://example.com --auth auth.json
```

### CLI オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| `--url` | 必須 | クロール対象 URL |
| `--depth` | `3` | リンクを辿る深さ |
| `--max-pages` | `50` | クロールする最大ページ数 |
| `--output` | `./output` | 出力先ディレクトリ |
| `--format` | `md` | 出力形式（`md,html,excel,pdf,json` をカンマ区切り） |
| `--compare` | off | 前回スナップショットとの差分を出力 |
| `--auth` | — | 保存済みセッション（auth.json）を使ってクロール |

---

## ドキュメント

- [クイックスタートガイド](docs/userguide.md)
- [開発者向けハンドブック](docs/DEVELOPMENT.md)

---

## 技術スタック

| 用途 | ライブラリ |
|------|-----------|
| ブラウザ自動操作 | [Playwright](https://playwright.dev/python/) |
| グラフ処理 | [networkx](https://networkx.org/) |
| 遷移図描画（GUI）| [Mermaid](https://mermaid.js.org/)（シーケンス図・コミュニケーション図・アクティビティ図） |
| Excel 出力 | [openpyxl](https://openpyxl.readthedocs.io/) |
| Web サーバ | [Flask](https://flask.palletsprojects.com/) |
| テスト | pytest（956 件・コアカバレッジ 90%+） |

- Python 3.12（3.13 は greenlet ビルド失敗のため非対応）
- GUI ポート: **8765**（macOS AirPlay との衝突回避）

---

## ライセンス

MIT
