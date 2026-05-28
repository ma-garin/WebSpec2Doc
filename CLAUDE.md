# WebSpec2Doc — 開発ガイド

URL を渡すと QA テストインプット文書を自動生成する Python ツール。
第三者検証会社が「ドキュメントなし現場」で初日からテスト設計を始めるためのツール。

## プロジェクト構成

```
008_CrateSpec2HTML/
├── docs/               ← ビジネス文書（HTML / ベリサーブデザイン）
├── src/                ← Pythonアプリケーション
│   ├── main.py         ← CLI エントリポイント
│   ├── crawler/        ← Playwright クローラー
│   ├── analyzer/       ← HTML 構造解析
│   ├── graph/          ← 画面遷移グラフ
│   ├── generator/      ← 文書生成（Mermaid/Markdown/HTML/Excel）
│   └── llm/            ← Claude API 連携
├── tests/              ← テストスイート
└── output/             ← 生成された QA 文書（Git 除外）
```

## セットアップ

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
# .env に ANTHROPIC_API_KEY を設定
```

## 使い方

```bash
# 基本（LLM なし）
python src/main.py --url https://example.com

# LLM 解析付き（Claude API 必要）
python src/main.py --url https://example.com --llm

# オプション全指定
python src/main.py \
  --url https://example.com \
  --depth 3 \
  --max-pages 50 \
  --output ./output \
  --llm \
  --format html,md,excel
```

## 出力ファイル

| ファイル | 内容 |
|---------|------|
| `output/{domain}/screens.md` | 画面一覧表（Markdown） |
| `output/{domain}/transition.mmd` | 画面遷移図（Mermaid） |
| `output/{domain}/report.html` | HTML レポート（提出物向け） |
| `output/{domain}/spec.xlsx` | Excel 仕様書（テスト管理ツール転記用） |
| `output/{domain}/screenshots/` | 各画面スクリーンショット |

## 開発ルール

- 言語：Python 3.11+
- クローラー：Playwright（同期 API）
- グラフ：networkx.DiGraph
- LLM：Claude Haiku（claude-haiku-4-5）/ プロンプトキャッシュ使用
- テスト：pytest / カバレッジ 80% 以上
- イミュータブル：データ変換は新しいオブジェクトを返す（in-place 変更禁止）
- ファイルサイズ：800行以内
- 関数サイズ：50行以内

## セキュリティ

- `.env` は絶対に Git にコミットしない
- `output/` は Git 除外（クライアント情報が含まれる可能性）
- API キーはハードコード禁止
