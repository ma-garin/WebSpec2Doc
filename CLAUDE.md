# WebSpec2Doc — 開発ガイド（エージェント向け）

URL を渡すと、稼働中の Web システムから **QA テスト分析インプット文書**（画面一覧・画面遷移・入力項目仕様・テスト条件・スクリーンショット）を自動生成する Python ツール。
第三者検証会社が「ドキュメントなし現場」で初日からテスト設計を始めるためのもの。

> このファイルは常時ロードされる要約。**詳細な自走用ハンドブックは [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)**、UI変更の必須フローは [AGENTS.md](AGENTS.md) を参照。

## 作業場所（重要）

```
/Users/fujimagariyuki/Desktop/app/014_WebSpec2Doc
```
- 旧 `app_趣味/008_CrateSpec2HTML` は**廃止**（venv 破損・参照禁止）。
- セッションは必ずこの 014 ディレクトリで開く（Codex 等のランタイムもここに固定される）。

## プロジェクト構成

```
014_WebSpec2Doc/
├── app.py              ← ブラウザGUI エントリポイント（Flask, port 8765）
├── WebSpec2Doc.command ← ダブルクリック起動（GUI）
├── run.sh              ← CLIワンライナー
├── src/
│   ├── main.py         ← CLI エントリポイント
│   ├── crawler/        ← Playwright クローラー
│   │   ├── page_crawler.py   ← crawl_site / PageData・FormData・FieldData(frozen)
│   │   ├── link_extractor.py ← リンク/フォーム/ボタン/制約 抽出
│   │   ├── auth.py           ← storage_state ログインセッション保存
│   │   ├── auto_login.py     ← GUIフォーム自動ログイン
│   │   ├── login_signal.py   ← ログイン壁検出シグナル
│   │   ├── session_guard.py  ← セッション期限切れ検出
│   │   └── url_safety.py     ← URL正規化・安全検証
│   ├── analyzer/
│   │   ├── html_analyzer.py    ← AnalyzedPage 付与
│   │   ├── form_analyzer.py    ← フォーム集約（md/excel用）
│   │   ├── login_wall.py       ← ログイン壁判定
│   │   └── test_conditions.py  ← 制約→境界値/同値分割を機械導出
│   ├── graph/transition_graph.py ← networkx.DiGraph 構築
│   ├── generator/
│   │   ├── html_reporter.py    ← report.html（サイドバー型・テストベース文書）
│   │   ├── diff_reporter.py    ← diff_report.html（ドリフト差分）
│   │   ├── json_reporter.py    ← report.json 出力
│   │   ├── pdf_reporter.py     ← report.pdf 出力
│   │   ├── markdown_generator.py
│   │   └── mermaid_generator.py ← 遷移図mmd（nav抑制付き・CLIエクスポート用）
│   ├── diff/           ← 仕様ドリフト検知
│   │   ├── snapshot.py ← クロール結果のJSON保存/復元/最新取得
│   │   └── differ.py   ← 2スナップショットの差分(DiffResult)
│   ├── registry/       ← サイト永続管理
│   │   ├── site_registry.py ← サイト登録/取得/削除
│   │   └── session_store.py ← auth.json パス管理
│   └── llm/            ← LLM連携（未実装・最後に着手）
├── web/                ← Flask Blueprintパッケージ
│   ├── routes/         ← エンドポイント（crawl/discover/history/report/login/site/auto_run/qa_process/settings）
│   ├── services/       ← ビジネスロジック（qa/spec_ts_generator/playwright_executor/openai_qa）
│   ├── security.py     ← CSRF ホスト検証（urlparse netloc完全一致）
│   └── summary.py      ← ドメインサマリー集計
├── static/
│   ├── app.css         ← 全スタイル（ウィザード/レポート/ダッシュボード/遷移図 etc.）
│   ├── app-view.js     ← 後方互換スタブ（実体は static/js/ に移行済み）
│   └── js/             ← モジュール分割フロントエンド（12モジュール）
│       ├── core.js           ← ビュー切替・サイドバー・ウィザードステップ管理
│       ├── wizard.js         ← ステップ1-2（解析・条件設定）
│       ├── execution.js      ← ステップ3（クロール実行・ライブログ）
│       ├── results.js        ← ステップ4（レポート8タブ・差分バッジ）
│       ├── history.js        ← 履歴・差分タブ（鮮度ラベル・差分バッジ）
│       ├── view-transition.js ← 画面遷移図（Mermaid UML 3タブ＋テスト観点マップ）
│       ├── view-overview.js  ← 概要タブ
│       ├── view-report.js    ← 画面別仕様タブ
│       ├── view-design.js    ← 設計・技法詳細タブ
│       ├── autorun.js        ← AutoRunビュー
│       ├── qa-process.js     ← QAプロセスビュー
│       └── [他: events/file-preview/recrawl/settings/qa-tools/view-shots/view-utils/view-export-settings]
├── templates/
│   ├── index.html      ← HTML骨格（partials を include）
│   └── partials/       ← 13 partial（view-generate/dashboard/auto-run/qa-* etc.）
├── tests/              ← pytest（349本・src/web コア90%+）
├── docs/               ← ビジネス文書(HTML) + userマニュアル + DEVELOPMENT.md
└── output/             ← 生成物（Git除外・顧客情報を含む可能性）
```

## セットアップ

```bash
python3.12 -m venv venv          # 3.13はgreenletビルド不可。3.12を使う
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## 使い方

```bash
# CLI（基本）
python src/main.py --url https://example.com --format md,html

# 全オプション
python src/main.py --url <URL> --depth 2 --max-pages 30 \
  --output ./output --format md,html,excel --compare

# ログイン対応（認証後ページ）
python src/main.py --login <ログインURL>        # 手動ログイン→auth.json保存
python src/main.py --url <URL> --auth auth.json # セッション再利用してクロール

# 指定URLのみ（リンク追跡なし）/ 画面リスト探索（GUIのクロールモードで使用）
python src/main.py --urls <URL1,URL2> --format md,html  # 指定URLだけクロール
python src/main.py --url <URL> --discover               # 到達ページ一覧をJSONで出力

# GUI
./WebSpec2Doc.command   # or: python app.py  → http://127.0.0.1:8765
```

### CLI フラグ
| フラグ | 既定 | 説明 |
|--------|------|------|
| `--url` | （必須※） | クロール対象URL |
| `--urls` | — | リンク追跡せず指定URLのみクロール（カンマ区切り、--url の代わり） |
| `--discover` | — | 到達ページ一覧(URL+タイトル)をJSONでstdout出力して終了 |
| `--login` | — | ログインセッション保存モード（--url不要） |
| `--auth` | — | 保存済み auth.json を使ってクロール |
| `--depth` | 3 | リンク追跡の深さ |
| `--max-pages` | 50 | 最大クロールページ数 |
| `--output` | ./output | 出力先 |
| `--format` | md | md,html,excel,pdf,json をカンマ区切り |
| `--compare` | off | 前回スナップショットとの差分を diff_report.html に出力 |
※ `--url` または `--login` のどちらかが必要。

## 出力ファイル（`output/{domain}/`）

| ファイル | 内容 |
|---------|------|
| `screens.md` / `forms.md` / `transition.mmd` | Markdown 画面一覧・フォーム・遷移図 |
| `report.html` | テストベース文書（サイドバー型・画面別カード＋テスト条件＋ロケータ候補） |
| `report.pdf` | report.html の PDF 版（`--format pdf`） |
| `report.json` | 全画面・テスト条件・ロケータ候補の構造化 JSON（`--format json`） |
| `diff_report.html` | ドリフト差分（`--compare` 時） |
| `spec.xlsx` | Excel 仕様書（`--format excel`） |
| `snapshots/*.json` | クロール結果スナップショット（差分検知用） |
| `screenshots/*.png` | 各画面のスクショ |

## 開発ルール（厳守）

- Python 3.11+（venvは3.12）。`from __future__ import annotations` + 全関数型ヒント。
- **イミュータブル**: frozen dataclass、データ変換は新オブジェクトを返す（in-place禁止）。
- 1関数50行以内 / 1ファイル800行以内。
- `print` 禁止 → `logging`。HTML出力は必ず `html.escape()`。
- マジックナンバー/文字列は定数化。
- テスト: pytest / カバレッジ80%以上。`python -m pytest tests/ -q`。

## セキュリティ

- `.env`（OPENAI_API_KEY 等）・`auth.json`（セッション）・`output/` は **Git除外済み**。コミット禁止。
- API キーのハードコード禁止。GUI設定はキー本体を返さず .env にサーバ保存。

## ハマりどころ

- ポート **8765**（5000はmacOS AirPlayと衝突するため変更済み）。
- venv は **python3.12**（3.13はgreenletビルド失敗）。
- 現行の API設定は **OpenAI**（ANTHROPIC ではない）。LLM機能自体は**未実装**。
- 旧 008 ディレクトリは使わない。

## 現在地と次

- 完了: クローラー / ドリフト検知 / 自動ログイン(GUI) / GUI多画面化 / テストベースレポート / M1②PDF出力 / M1③JSON出力 / M2 Phase B（ロケータ候補列・クロール条件メタ） / 4ステップウィザード / 個別ログインフォーム / 技法詳細タブ / Mermaid UML 3サブタブ＋テスト観点マップ / エクスポートドロップダウン / コードベース分割（app.js→12モジュール・qa_process→4モジュール・index.html→13 partial） / ダッシュボード再設計（差分バッジ・鮮度ラベル・スナップショット数）/ サイト削除機能 / CSRF強化（urlparse netloc完全一致） / サイドバー折りたたみ＋最大化ボタン / レポート8タブ化（テスト条件・技法詳細・遷移表を独立タブ化） / 差分バッジ・タブカウントバッジ / スレッドセーフ対応（_JOBS_LOCK）/ テスト349本・コア90%+。
- 次: LLMテスト観点（src/llm/ OpenAI統合・最後に着手）→ M3 連携（TestRail/Jira）。
- **ロードマップ・拡張手順・検証レシピは [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)**。
