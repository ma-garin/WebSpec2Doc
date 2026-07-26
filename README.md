# WebSpec2Doc

**URL → QA テストインプット文書 自動生成ツール**

稼働中の Web システムの URL を渡すだけで、QA エンジニアがテスト設計を始めるために必要な文書を自動生成します。

> 「ドキュメントがないので、まず触って覚えてください」という現場でも、初日からテスト設計を始められる状態を実現します。

> **はじめての方へ（非エンジニアの方も歓迎）**: 専門用語なしの入門ガイドを用意しています → **[docs/GUIDE_ja.md](docs/GUIDE_ja.md)**（日本語）／ [docs/GUIDE_en.md](docs/GUIDE_en.md)（English）。英語版 README は [README_en.md](README_en.md)。

> **📱 オンラインショーケース（スマホ対応）**: インストール不要で画面と動きを確認できます → **https://ma-garin.github.io/WebSpec2Doc/**（実機UIの操作動画・スクリーンショット・生成レポートのサンプル。ソースは [`pages/`](pages/)、公開手順は [pages/README.md](pages/README.md)）。

---

## 主な機能

| 機能 | 説明 |
|------|------|
| **画面仕様の自動生成** | 入力フィールド・制約・ロケータ候補・テスト条件を画面ごとに整理 |
| **テスト設計技法の推奨** | 同値分割・境界値分析・デシジョンテーブル等を画面要素から自動判定 |
| **画面遷移図・遷移表** | UML 遷移図（シーケンス図・コミュニケーション図・アクティビティ図・テスト観点マップ）＋ ISTQB 標準の画面遷移表 |
| **状態探索** | モーダル・タブ・アコーディオン等の操作で現れる「隠れた状態」を自動で開いて記録（SPA 対応） |
| **根拠（evidence）付与** | 生成される仕様・テスト条件に、実測したセレクタ・スクリーンショット座標を紐づけ |
| **観点管理** | テスト観点をツリー分類・インライン編集で管理（3ペイン UI・AI 提案） |
| **仕様ドリフト検知** | 再クロールで前回との差分（追加/削除/変更）を自動検出し、影響画面を分析 |
| **トレーサビリティ** | 画面 → テスト観点 → テストシナリオの対応関係を追跡 |
| **自動ログイン** | ID/PASSWORD を GUI で入力し、認証が必要なサイトにも対応 |
| **クロール礼儀** | robots.txt 尊重・per-origin レート制御・破壊的リクエスト遮断を既定で有効化 |
| **ROI ダッシュボード** | 利用実績から削減工数（時間・円）を推定して表示（`/usage`） |
| **スクリーンショット** | 全画面のキャプチャを仕様と並べて表示 |

---

## 生成できる成果物

| ファイル | 内容 |
|---------|------|
| `report.html` | 画面別仕様・テスト条件・スクリーンショット付きレポート |
| `report.json` | 構造化 JSON（自動化・CI 連携用） |
| `spec.xlsx` | Excel 仕様書（テスト管理表への転記用） |
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

pip install -r requirements-dev.txt
python scripts/manage_playwright_runtime.py install
make setup-hooks    # pre-commit フックをインストール（品質ゲート有効化）
make test           # 動作確認
```

Chromium はユーザー共有キャッシュではなく、既定で
`./.runtime/ms-playwright` に導入されます。Playwright 更新後も、必ず同じ仮想環境の
`manage_playwright_runtime.py install` を再実行してください。`make check-runtime` は
Chromiumを実際に起動して、パッケージとブラウザの組み合わせを検証します。

---

## すぐ試す（同梱デモ）

外部サイトも OpenAI API キーも不要で、全機能を同梱デモサイトで体験できます。

```bash
make demo       # デモサイト(8766)と本体(8765)を同時起動
# → 本体の URL 欄に http://127.0.0.1:8766/ を入力して「画面分析」
```

デモの流れは [docs/demo/DEMO_SCRIPT.md](docs/demo/DEMO_SCRIPT.md)、
生成物のサンプルは [docs/demo/sample_output/](docs/demo/sample_output/) にあります。

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
| `--ci` | off | `--compare --fail-on-drift` を有効化し、`CI_SUMMARY:` JSONをstdoutへ出力 |
| `--auth` | — | 保存済みセッション（auth.json）を使ってクロール |
| `--parallelism` | `1` | クロールの並列ワーカー数（1〜4、GUI 既定は 2）。オートクローリング・明示 URL の両モードで有効 |

### クロール速度のチューニング

並列化してもサイトへの礼儀は変わりません（robots.txt の Crawl-Delay と per-origin レート制御は
全ワーカー共有で維持されます）。速度と観測の深さは次の環境変数で調整できます。

| 環境変数 | デフォルト | 説明 |
|---|---|---|
| `WEBSPEC2DOC_CRAWL_INTERVAL_SEC` | `1.0` | リクエスト間隔の下限（秒）。robots の Crawl-Delay が長い場合はそちらを採用 |
| `WEBSPEC2DOC_STABILITY_TIMEOUT_MS` | `3000` | ページ読み込み後の networkidle 安定待ち上限（ms）。`0` で待機なし |
| `WEBSPEC2DOC_FULL_SCREENSHOT` | `1` | `0` で全体スクリーンショット（`{id}_full.png`）を省略し、ビューポート版のみ保存 |
| `WEBSPEC2DOC_MAX_ACTIONS_PER_PAGE` | `10` | ページ内アクション探索（モーダル・タブ等）の最大クリック数 |

### CI で仕様ドリフトをゲートする

同梱の [`.github/workflows/spec-drift.yml`](.github/workflows/spec-drift.yml) は、前回スナップショットだけを GitHub Actions cache に保存し、2回目以降の実行で実際の差分を検出します。

1. Repository variable `WEBSPEC_TARGET_URL` に監視URLを設定します（手動実行時は `target_url` 入力で上書き可能）。
2. Slack通知を使う場合だけ Repository secret `SLACK_WEBHOOK_URL` を設定します。未設定・送信失敗でもドリフト判定結果は変わりません。
3. Actions の `Spec Drift Detection` を実行します。初回はベースライン保存、2回目以降は差分ありでジョブが失敗します。

ローカルまたは他のCIでは次を実行し、`output/<domain>/snapshots/` を実行間で永続化してください。

```bash
python src/main.py --url https://example.com --ci --format json,html
python scripts/notify_drift.py output/example.com/drift_summary.json
```

| exit code | 意味 |
|---:|---|
| `0` | 初回ベースライン、または差分なし |
| `1` | 仕様ドリフトあり |
| `2` | セッション失効、取得不能などの実行エラー |

GitLab CI や CircleCI でも同じ2コマンドと exit code を利用できます。キャッシュ対象は `output/**/snapshots` のみにし、スクリーンショットやレポート全体をキャッシュしないでください。

### 生成済み spec.ts を Actions で実行する

AutoRun が生成した `output/<domain>/qa_process/autorun.spec.ts` を、たとえば
`tests/generated/autorun.spec.ts` として対象リポジトリへ保存します。同梱の
[`.github/workflows/generated-spec.yml`](.github/workflows/generated-spec.yml) を手動実行し、
`spec_path` にそのリポジトリ内パスを指定してください。ワークフローは固定バージョンの
PlaywrightとChromiumを準備してテストを実行し、HTMLレポートをActions artifactへ保存します。

生成されたテストは対象サイトへ実アクセスします。認証情報が必要な場合はリポジトリへ
直接保存せず、GitHub Actions secretsから対象サイトのログイン処理へ渡してください。

---

## 社内サーバへ展開（venv + systemd）

> **コンテナは使用しない方針。** 従業員 1,000 人超の組織では Docker Desktop が有償ライセンス対象となるため、本プロジェクトは Docker への依存を持たない（Dockerfile・compose 定義は置かない）。

```bash
# Python 3.12 の venv を作成し依存をインストール
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/manage_playwright_runtime.py install --with-deps
.venv/bin/python scripts/manage_playwright_runtime.py check

# 既定はローカルループバックのみ許可（外部からは 403）
# 社内ネットワークから使う場合は許可ホストを明示的に指定する
WEBSPEC2DOC_TRUSTED_HOSTS=webspec2doc.internal .venv/bin/python app.py
```

常駐運用する場合は systemd サービスにする（例: `/etc/systemd/system/webspec2doc.service`）:

```ini
[Unit]
Description=WebSpec2Doc
After=network.target

[Service]
WorkingDirectory=/opt/webspec2doc
Environment=WEBSPEC2DOC_TRUSTED_HOSTS=webspec2doc.internal
Environment=PLAYWRIGHT_BROWSERS_PATH=/opt/webspec2doc/.runtime/ms-playwright
ExecStart=/opt/webspec2doc/.venv/bin/python app.py
Restart=on-failure
User=webspec2doc

[Install]
WantedBy=multi-user.target
```

`WEBSPEC2DOC_TRUSTED_HOSTS` が未設定なら現行どおり localhost 限定で動作します。

---

## ドキュメント

**[docs/README.md](docs/README.md) が全文書のインデックス**（現行/歴史のステータス付き）。主要な入口:

- [はじめての方へ（非エンジニア向けガイド）](docs/GUIDE_ja.md) / [English](docs/GUIDE_en.md)
- [クイックスタートガイド](docs/userguide.md)
- [開発者向けハンドブック](docs/DEVELOPMENT.md)
- [機能拡張ロードマップ](docs/11_機能拡張ロードマップ_現新比較とUX検証.md)
- [デモ台本](docs/demo/DEMO_SCRIPT.md)

---

## 技術スタック

| 用途 | ライブラリ |
|------|-----------|
| ブラウザ自動操作 | [Playwright](https://playwright.dev/python/) |
| グラフ処理 | [networkx](https://networkx.org/) |
| 遷移図描画（GUI）| [Mermaid](https://mermaid.js.org/)（シーケンス図・コミュニケーション図・アクティビティ図） |
| Excel 出力 | [openpyxl](https://openpyxl.readthedocs.io/) |
| Web サーバ | [Flask](https://flask.palletsprojects.com/) |
| テスト | pytest（1,194 件・コアカバレッジ 90%+）＋ Playwright E2E（64 件） |

- Python 3.12（3.13 は greenlet ビルド失敗のため非対応）
- GUI ポート: **8765**（macOS AirPlay との衝突回避）

---

## トラブルシュート — ローカルで取得に失敗する場合

環境不一致（Python / Playwright / Chromium / 依存バージョン）が原因のことが
ほとんどです。まず環境ドクターで一括診断してください:

```bash
make doctor
```

FAIL の項目に修正コマンドが表示されます。典型的な原因:

| 症状 | 原因 | 対処 |
|---|---|---|
| pip install が失敗 / 起動時に greenlet エラー | Python 3.13 以降（playwright 1.44 の wheel なし） | Python 3.12 で venv を作り直す |
| `Executable doesn't exist` 等でブラウザ起動失敗 | Chromium ランタイム不一致 | `make setup-runtime` |
| 127.0.0.1 や社内 IP の取得が拒否される | SSRF 保護（既定で有効） | `WEBSPEC2DOC_ALLOW_LOCAL=1` を設定 |
| 特定ページだけスキップされる | ログインウォール検出 / robots Disallow | ログで理由を確認（`audit.jsonl` に記録） |

環境が正常（全 PASS）なのに失敗する場合は、対象サイト側の要因（認証・robots・
レート制限）を `output/<domain>/audit.jsonl` と実行ログで確認してください。

---

## ライセンス

MIT
