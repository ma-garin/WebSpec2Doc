# Sprint 3 並列実行計画（0705_plan.md の実装ガイド）

作成日: 2026-07-05 ／ ステータス: **レビュー待ち（着手前の設計ドキュメントゲート）**
前提: `docs/0705_plan.md` Sprint 3（5タスク・未対応22項目）。本書はその「どう並列で安全・高速に回すか」を確定する実行計画。

## 0. 事前作業（完了済み）

- ✅ stale クローン `WebSpec2Doc/`（Sprint 1 時点 `bfd9592`・clean・全push済み）を正本外へ退避:
  `/Users/fujimagariyuki/dev/active/_rescue/WebSpec2Doc-stale-clone-20260705`。GitHub から完全復元可能。正本 `git status` はクリーン。

## 1. 分業の軸（プロジェクト規約）

- **実装コード = Codex／テストコード = Claude**（`~/.claude/CLAUDE.md`）。
- UI/E2E は **Playwright（MCP優先）**。
- 各PRの完了ゲート（必須・`CLAUDE.md`）:
  ```bash
  python scripts/quality_harness.py
  make test
  make verify-ui
  ```
- コミット単位でも: black(Python3.12実機)/ruff/mypy/bandit/pytest。

## 2. 競合分析の結論（律速点）

| 共有ファイル | 触るタスク | 対処 |
|---|---|---|
| `static/js/results.js`（`TAB_DEFS` 8–17行 / `LEGACY_TAB_MAP` 20–28行） | B(test-design.subs) / 4(新タブ) / D(history系) | **単一オーナーが集約**。各レーンはここに触らず、統合レーンで最後にタブ登録 |
| `templates/partials/view-generate.html`（354行, パネル追加） | B / 4 | 同上（パネル`div`追加を統合レーンで） |
| `web/routes/report.py`（`files`辞書 183–197行） | 4 / (D) | 4が主。Dは`history.py`に寄せて回避 |

→ **タブ登録（results.js / view-generate.html）を"統合レーン"に切り出す**ことで、機能レーンは互いに衝突しなくなる。

## 3. レーン編成（4レーン）

### レーンA｜ドキュメント（S3-5, D-01/02/03）— 完全独立・コードゼロ
- 担当: Claude（文章主体・実装コード非該当）
- 削除(`git rm`): `docs/01〜06_*.html`＋`docs/index.html`、`07_商用化戦略.{md,html}`、`08_プロダクト機能戦略.md`、`09_事業計画_統合版.md`、`10_社内ベンチャー準備タスク.md`、`demo/PITCH_OUTLINE.md`、`archive/SELLABLE_PRODUCT_PLAN.md`、`archive/plan.txt`
- 編集: `docs/11*ロードマップ`（事業/大会文言除去）、`demo/DEMO_SCRIPT.md`、`docs/README.md`、`README.md`、`DEVELOPMENT.md`
- 新規: `docs/GUIDE_ja.md`／`docs/GUIDE_en.md`（非エンジニア向け）／`README_en.md`
- 依存: なし。**即着手・単独PR**。

### レーンB｜フローチャート（S3-3, R2-12）— 完全独立
- 担当: Codex(実装) + Claude(E2E)
- 対象: `static/js/view-transition.js` **のみ**（569行）。`:208-210` にサブタブボタン「フローチャート」、`:451-453` dispatcher分岐、新規 `_flowchartDiagram(rows)`（既存 `_communicationDiagram` の `flowchart LR` パターン流用）
- 依存: なし。`results.js` 不要（`flow` タブ内の内部サブ切替）。**単独PR**。

### レーンC｜バックエンド・エンジン（S3-1 B・S3-2 D・S3-4 の純粋部）— 相互独立
新規/バックエンドは互いに衝突しない。3サブレーンを並列可。
- **C1 = B エンジン**: 新規 `src/generator/test_design.py`（`TestDesignParams`(frozen)/`build_test_design(report, params)`、evidence-only、自前貪欲IPOペアワイズ・Nスイッチ経路列挙）。設定API `/api/settings/test-design` は **S1-4で実装済み**（`web/routes/settings.py:66-76`）→ 再利用。
- **C2 = D エンジン**: `src/diff/comparison.py` から `compare_analyzed_pages(old_pages, new_pages, *, dynamic_masks, check_links=False, ...)` を抽出（既存 `run_old_new_comparison`/`_classify_pair` からロジック抽出、**バイト同一の挙動**）。新ルート `GET /api/snapshot-comparison` を `web/routes/history.py`（既存 `api_snapshot_diff` 110行の隣）に追加。
- **C3 = ヒートマップ生成**: `src/generator/heatmap_reporter.py`（206行）の `_bucket`/`_cell` 再利用で、解析用3色（取得/未取得/要ログイン）・AutoRun用2軸（実行回数×成否）HTMLを生成する関数追加。
- 担当: Codex(実装) + Claude(単体テスト)。各サブレーンは**別ファイル**なので3並列可、**サブレーンごとに単独PR可**。

### レーンD｜UI統合（タブ登録＋各機能UI）— **C完了後に直列で1本**
機能レーンが作った関数/エンドポイントを、共有ファイルに一括配線する“最後の1本”。
- `static/js/results.js`: `TAB_DEFS['test-design'].subs` に MBT サブ追加 / ヒートマップ用の新タブ or `screens` サブ追加 / history系のモード。`LEGACY_TAB_MAP` も更新。
- `templates/partials/view-generate.html`: 対応パネル`div`追加。
- `templates/partials/view-settings.html`: 「テスト設計」タブ追加（現状 api/crawl/notify の3タブ・4行目パターン踏襲）＋ `static/js/settings.js` にハンドラ、値カタログ編集表。
- `static/js/view-design.js`: MBT サブビュー（技法チップ→対象画面→モーダル）。既存 `renderMatrix`/`renderDesign`/`renderTechniqueDetail`（167/239行）に**追加**、**matrixは既定のまま**（既存E2E無傷）。
- D(現新比較)のUI: モード切替ラジオ「現新比較（既定）／簡易ドリフト差分」、`iframe.srcdoc` 表示。
- 担当: Codex(実装) + Claude(E2E: MBT設計モーダル/現新比較/ヒートマップ/設定テスト設計タブ)。**単独PR**。

## 4. 実行順序（依存グラフ）

```
      ┌── レーンA ドキュメント ───────────────┐（完全並列・独立PR）
      ├── レーンB フローチャート ─────────────┤
start─┤                                        ├─→ 各PR: 完了ゲート→push→PR→CI green→即マージ
      ├── レーンC1 Bエンジン ─┐                │
      ├── レーンC2 Dエンジン ─┼→ レーンD UI統合 ┘（Cのマージ後に着手）
      └── レーンC3 ヒートマップ┘
```

- **第1波（同時着手可）**: A / B / C1 / C2 / C3（5並列。全て別ファイル・独立）
- **第2波**: D（第1波のC群がマージされた後。共有ファイルへの配線を1本に集約しコンフリクト回避）
- マージ規律（確立済みパターン）: スプリント/レーン単位で コミット→push→PR→CI green→**即マージ**。第2波着手前に第1波を main へ取り込む。

## 5. 新規E2E（Claude担当・ポート8912〜割当）

- MBT 設計モーダル（BVA表/DT真理値表/PW行/ST系列＋根拠＋パラメータ表示）
- スナップショット現新比較（4分類・モード切替）
- カバレッジヒートマップ（解析3色／AutoRun2軸の描画）
- 設定「テスト設計」タブ（技法ON/OFF・値カタログ編集の保存往復）
- フローチャートサブタブの描画

## 6. リスクと非破壊担保

- Dで旧簡易diff(`api_snapshot_diff`)を**残置**→ r-diff-badge / CI `--fail-on-drift` 導線を非破壊。
- Bで matrix サブを既定維持→ `test_report_tabs_e2e.py` 等のタブ数/既定アサーション無傷。
- タブ登録を第2波に集約→ 第1波5PRが `results.js`/`view-generate.html` で相互コンフリクトしない。
- 値カタログは S1-4 の `instance/test_design_settings.json`(value_catalog) と**同一ストア共有**（二重定義しない）。

## 7. 着手可否

本書は設計ドキュメント。プロジェクト規約（`~/.claude/CLAUDE.md`「設計ドキュメント生成後は一旦停止しレビュー」）に従い、**レビュー承認後にレーンA/B/C を第1波として並列着手**する。
