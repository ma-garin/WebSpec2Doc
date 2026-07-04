# WebSpec2Doc 開発ハンドブック（自走用）

このドキュメントは、エージェント（Sonnet 等）が WebSpec2Doc の開発を**自走**するための完全ガイド。
要約は [CLAUDE.md](../CLAUDE.md)、UI変更フローは [AGENTS.md](../AGENTS.md) を参照。

---

## 0. まず読む順番

1. `CLAUDE.md` — プロジェクト要約・作業場所・ルール
2. `AGENTS.md` — クレジット節約方針 / UI変更の必須フロー
3. 本書 — アーキテクチャ・拡張手順・検証レシピ・ロードマップ
4. `docs/05_事業戦略提案.html` — なぜ作るか（ドリフト検知が収益の楔／オンプレが堀）

---

## 1. プロダクトの本質

- **入力**: 公開（または認証付き）Webサイトの URL。
- **出力**: 稼働システムから導出した**テスト分析インプット文書**（テストベース）。
- **位置づけ**: 「テストケース」そのものではなく、テスト設計の素材（画面・遷移・入力項目・**機械導出のテスト条件**）を供給する。テストケース確定には要件＋人の判断が要る。
- **読み手**: テスト担当 / 自動化担当 / 開発者 / PdM・PM・PMO。外部結合〜システム〜受け入れテストを想定。
- 準拠: ISO/IEC/IEEE 29119-3/4（テスト文書・設計技法）、JSTQB（テスト対象/観点/条件/手順/期待値）。

---

## 2. アーキテクチャとデータフロー

```
URL
 └─ crawler.page_crawler.crawl_site(url, depth, max_pages, output_dir, auth_state)
      ├─ Playwright(Chromium) で各ページ取得（networkidle待ち）
      ├─ link_extractor: リンク / フォーム(+制約+選択肢) / ボタン / 見出し / タイトル
      └─ → list[PageData]                         （frozen dataclass）
 └─ analyzer.html_analyzer.analyze_pages(pages)
      └─ → list[AnalyzedPage]（page_id付与, buttons/nav_elements）
 └─ graph.transition_graph.build_graph(analyzed) → networkx.DiGraph
 └─ analyzer.form_analyzer.summarize_forms(analyzed) → list[dict]（md/excel用）
 └─ generator.*               → screens.md / forms.md / transition.mmd / report.html / spec.xlsx
 └─ diff.snapshot.save_snapshot(pages) → snapshots/{ts}.json
 └─ (--compare) diff.differ.compute_diff(old,new) → diff_reporter → diff_report.html
```

CLI 全体は `src/main.py:run()` がオーケストレーション。GUI（`app.py`）は `/run` が `src/main.py` を subprocess 実行してログをストリームする薄いラッパ。

### 主要データ構造（`src/crawler/page_crawler.py`・すべて frozen）

```python
FieldData(field_type, name, placeholder, required,
          maxlength, minlength, min_value, max_value, pattern, default, options)
FormData(action, method, fields: tuple[FieldData, ...])
PageData(url, title, headings, links, forms, screenshot_path, buttons)
AnalyzedPage(page_id, page_data: PageData, buttons, nav_elements)  # html_analyzer
```

frozen なので変更は `dataclasses.replace()` で**新インスタンス**を作る（in-place禁止）。

---

## 3. レイヤ別「拡張のしかた」

| やりたいこと | 触る場所 |
|------------|---------|
| 取得項目を増やす（例: aria-label, alt） | `link_extractor._FORM_SCRIPT`(JS) → `_to_field_data` → `FieldData` に項目追加（**デフォルト値付き**で後方互換） |
| 新しいテスト条件の導出 | `analyzer/test_conditions.py:derive_conditions()` に分岐追加 |
| report.html の見た目・章立て | `generator/html_reporter.py`（**UI変更フロー厳守**） |
| 差分検知の対象を増やす | `diff/differ.py:compute_diff()` と `DiffResult` |
| 新しい出力形式 | `main.py:save_outputs()` に分岐 + `generator/` に新モジュール |
| GUI の画面/設定 | `app.py` はエントリーポイント（Flask + `web/` パッケージ）。**4ステップウィザード**（①解析: URL入力＋画面分析 → ②条件設定: 画面選択＋個別ログインフォーム＋差分ON/OFF → ③実行: ライブプレビュー＋4段階進捗バー → ④レポート）。`/api/discover` で画面一覧取得（タイムアウト180秒）、認証必要画面は per-page インラインフォームで個別ログイン（`/api/login/simple`）。結果配信は `/api/result`（生成物一覧＋サマリー）`/preview`（iframe・テキスト）`/download`・`/download-zip`（パスガード付き）。静的ファイルは `static/js/`（core/wizard/execution/results/qa-process/qa-tools/autorun 等 12モジュール）＋`static/app-view.js`＋`static/app.css`。テンプレートは `templates/index.html`（骨格）＋`templates/partials/`（13 partial）。 |
| QAプロセスビュー | `web/routes/qa_process.py`（薄いルート）＋`web/services/qa/`（helpers/doc_generator/advanced_generator/advanced_html の4モジュール）。`/api/qa-process/input` でレポート読み込み・`/api/qa-process/generate` でテスト計画〜横断レビューを生成。高度QA成果物（モデルグラフ・Playwright候補・品質観点）は `/api/qa-process/generate-advanced`。OpenAI API がある場合は補完、無い場合はローカルテンプレートでフォールバック。 |
| AutoRun | `web/routes/auto_run.py`。URL 入力から全自動テスト実行までをシングルフロー（discover → crawl → QA生成 → spec.ts 生成 → テスト実行）。ジョブ管理は `AutoRunJob` dataclass（状態遷移: idle→discovering→crawling→generating_qa→running_tests→complete）。ログは SSE ではなくポーリング（`/api/auto-run/status/<job_id>`）。 |
| spec.ts 生成・実行 | `web/services/spec_ts_generator.py`（Playwright spec 生成）＋`web/services/playwright_executor.py`（node_modules 共有・subprocess 実行）。AutoRun の最終ステップとして呼び出される。 |
| 結果ページのタブ | ①概要（画面インベントリ）②画面別仕様（スクショ+フォームカード+テスト条件。フォームなし画面はページ要素一覧）③**入力項目・テスト条件マトリクス**（全画面横断・フィルタ・CSV書き出し）④設計（技法推奨マトリクス）⑤**技法詳細**（画面別・技法別サンプル値カード）⑥**画面遷移図**（Mermaid UML 3サブタブ: シーケンス図/コミュニケーション図/アクティビティ図。図エッジ番号と対応表Noを連動。加えてテスト観点マップで遷移をQA観点へ分類）⑦遷移表（リンク先URLパス付き）⑧履歴・差分。エクスポートはヘッダーのドロップダウン（HTML/PDF/JSON/Excel/MD×2/Mermaid/差分/ZIP）。データ源は `report.json`（GUI実行時は常に生成）を `/api/result` で取得しクライアントで構築。 |
| 集計の真実源 | サマリー／概要／マトリクス／**履歴の画面数・入力項目数**は全て `_summary_for_domain()`＝**最新 `report.json`** から集計（無い旧データのみ snapshot→screens.md にフォールバック）。screens.md 行カウントは誤差が出るため真実源にしない。 |
| 実行履歴 | `/api/history` は各ドメインの最新 report.json から画面数・入力項目数・生成形式バッジを返す。行の「結果を見る」は `openResultsForDomain()` で**アプリ内の結果ページ（4タブ）を再表示**（OSでファイルを開くのではなく結果ページに統一）。 |
| ポート変更 | `WEBSPEC2DOC_PORT` 環境変数で変更可（既定8765）。例: `WEBSPEC2DOC_PORT=8766 python app.py`。 |

**dataclass にフィールド追加する時の鉄則**: 必ずデフォルト値付きで足す。既存のテスト・スナップショット復元・他コンストラクタを壊さないため。

---

## 4. 検証レシピ（変更後は必ず実行）

```bash
source venv/bin/activate

# 単一の真実ゲート（これだけ GREEN なら合格）
bash scripts/verify.sh   # py_compile + 800行ガード + ruff/black/mypy + pytest 349本 + スモーク

# 個別実行（デバッグ用）
python -m py_compile app.py $(find src web -name '*.py' -not -path '*__pycache__*')
python -m pytest tests/ -q                       # 349本 緑が基準
python -m pytest tests/ -q --cov=src --cov-report=term-missing  # 80%以上

# ライブ（フルパイプライン・回帰確認 = M0相当）
python src/main.py --url https://www.iana.org --depth 1 --max-pages 4 \
  --format md,html,excel --compare        # 1回目=初回snapshot
python src/main.py --url https://www.iana.org --depth 1 --max-pages 4 \
  --format md,html,excel --compare        # 2回目=diff_report.html生成
# → output/www.iana.org/ に screens.md/forms.md/transition.mmd/report.html/
#    spec.xlsx/diff_report.html/snapshots(2)/screenshots が揃えばOK

# GUI
python app.py    # http://127.0.0.1:8765 が200・3ビュー表示
```

UI を変えた時は加えて: ブラウザで開く → 1920x900 / 1366x768 で崩れ確認 → ナビ/スクロール/入力の操作確認（AGENTS.md の必須フロー）。

---

## 5. ロードマップ（マイルストーン）

```
[完了] クローラー / ドリフト検知 / 自動ログイン(GUI) / GUI多画面化 /
       テストベースレポート Phase A / レポートデザイン統一 /
       M1② PDF出力（--format pdf、Playwright page.pdf、@media print対応済み） /
       M1③ JSON出力（--format json、全画面+テスト条件+ロケータ候補） /
       M2 Phase B（⑤自動化ヒント:ロケータ候補列 / ⑥メタ拡充:クロール条件記録） /
       QAプロセスビュー（テスト計画〜横断レビュー生成・OpenAI補完/ローカルフォールバック） /
       AutoRun（URL入力→全自動クロール→QA生成→spec.ts生成→テスト実行） /
       コードベース整備（app.js→12モジュール・qa_process→4モジュール・index.html→13 partial・800行ガード） /
       ダッシュボード再設計（差分バッジ・鮮度ラベル・スナップショット数バッジ・空状態CTA） /
       レポート8タブ（テスト条件・技法詳細・遷移表を独立タブ化）/ 差分バッジ・タブカウントバッジ /
       画面遷移図刷新（Mermaid UML 3サブタブ＋テスト観点マップ・ズーム・エッジ番号対応表連動） /
       サイト削除機能（DELETE /api/site/<domain>）/ CSRF強化（urlparse netloc完全一致） /
       サイドバー折りたたみ・最大化ボタン（localStorage永続化）/ スレッドセーフ（_JOBS_LOCK） /
       テスト349本・コア90%+

LLM テスト観点     : src/llm/ 実装。各画面に観点を付与。OpenAI(.envのOPENAI_API_KEY/MODEL)。**最後に着手**。
M3  連携          : TestRail/Jira へのエクスポート、AGENTS.md(machine-readable)出力。

★ v1.0 完成 = M0 + M1(①②③) + M2 Phase B + QAプロセス + AutoRun + ドキュメント更新。
★ v1.1 以降 = LLM テスト観点（OpenAI）/ M3 連携。
```

詳細な事業背景は `docs/09_事業計画_統合版.md`（正）を参照。過去の経緯は `docs/05_事業戦略提案.html` / `docs/archive/plan.txt`。

---

## 6. ハーネス / エージェント運用ルール

- **モデル分担**: 設計・レビューは上位モデル、実装は Sonnet / Codex。日常運転は Sonnet で十分。
- **UI変更は必ず**「スキャン→方針提示→合意→実装→ブラウザ確認→2解像度→操作確認→コミット→py_compile→確認内容を明記して報告」（AGENTS.md）。
- **応答の末尾に進捗バー**を表示する慣習（例）:
  ```
  WebSpec2Doc  ████████░░ 70%
  [x] 完了マイルストーン
  [ ] 未着手
  ```
- **クレジット節約**: 大きなファイル全文取得・広域検索は避け、最小調査で方針を出す。2分超の作業は確認を取る。修正/コミット/pushはユーザー承認後。
- **Codex 連携**: 仕様が固まった実装の委任先。セッションを 014 で開けばランタイムも 014 に固定される（旧 008 アンカー事故を避ける）。委任後は成果物を必ずレビュー（過去に未配線スタブ混入の事例あり）。
- **コミット規約**: `feat:/fix:/docs:/refactor:/test:/chore:`。1マイルストーン=1〜数コミット。属性表記はグローバル設定で無効。

---

## 7. 既知のハマりどころ

| 症状 | 対処 |
|------|------|
| `Address already in use` (5000) | ポートは **8765**（AirPlay衝突回避済み）。旧プロセスを停止して再起動。 |
| greenlet ビルド失敗 | venv を **python3.12** で作る（3.13不可）。 |
| `ModuleNotFoundError: playwright` | `pip install -r requirements.txt` + `playwright install chromium`。スタブで誤魔化さない。 |
| report.html が巨大 | スクショは `full_page=False`・500KB超は埋め込みスキップ済み。 |
| 画面遷移図が表示されない | Mermaid を CDN(jsdelivr)で動的ロード。オフライン環境ではUML図は表示されない。3サブタブ（シーケンス/コミュニケーション/アクティビティ）とテスト観点マップで切替可能。図が描画できない場合はMermaidソースをフォールバック表示する。 |
| 設定のAPIキーが消える | `/api/settings` は部分更新。GET はキー本体を返さない（マスクのみ）。 |

---

## 8. テストの考え方

- 純粋関数（normalize_url, compute_diff, derive_conditions, markdown生成 等）は手組みデータで網羅。
- Playwright/ブラウザ/`input()` は `unittest.mock` でモック（実ブラウザを起動しない）。例: `test_auth.py`（`new_context` への storage_state 配線を max_pages=0 で検証）。
- カバレッジが届かないのは `page_crawler` の実ブラウザ依存部のみ（許容）。
- 新モジュールを足したら対応する `tests/test_*.py` を必ず追加し 80% を維持。
