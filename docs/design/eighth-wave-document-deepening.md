# 第8弾 設計書 — 文書駆動の深化（D: TF-IDF突合候補 / G: Gherkin互換テンプレート / B: レイアウト故障検知）

- 作成日: 2026-07-19 / ステータス: **レビュー待ち**
- 根拠: ④トレーサビリティ（Antoniol TSE 2002 の系譜）・⑩BDD・ReDeCheck（ISSTA 2017）
- 実装担当: Opus 4.8 / 前提: 第7弾完了

## 主張境界

| 機能 | 主張してよい | 主張してはならない |
|---|---|---|
| D 突合候補 | テキスト類似度に基づく**候補**と根拠スコア | 候補が正しい対応であること（確定は人のみ） |
| G テンプレート | 記法に従うと抽出精度が上がる仕組みの提供 | 記法外の文書が扱えないこと（従来経路は維持） |
| B レイアウト故障 | 観測した幾何情報（座標・はみ出し・重なり） | それがバグであること（意図的デザインと区別不能） |

---

## D. TF-IDF類似による要件↔画面の突合候補提示

### 目的
文書駆動の価値＝突合率。現行はルールベースの一致のみで「対応画面なし」が出やすい。トレーサビリティ研究の20年来のベースライン（ベクトル空間モデル、Antoniol系譜）を**LLM無し・追加依存無し・決定的**に導入し、未突合要件へ候補を提示する。**自動リンクは絶対にしない**（phantom links 対策。研究の結論どおり確定は人）。

### 実装
新規 `src/mbt/trace_suggestions.py`（標準ライブラリのみ）:

```python
CLAIM_SCOPE = "textual_similarity_candidates_only"
SUGGESTION_THRESHOLD = 0.15   # これ未満は候補に出さない（雑音抑制）
TOP_K = 3

def tokenize(text: str) -> list[str]
    # 英数字は単語単位（小文字化）、日本語は文字bigram。決定的
def build_screen_corpus(report: dict) -> dict[str, list[str]]
    # page_id -> トークン列（title + headings + フィールドname/placeholder/aria_label + ボタン文言）
def suggest_matches(unmatched_requirements, report) -> list[dict]
    # 各未突合要件に対し TF-IDF cosine 上位 TOP_K を
    # {req_id, candidates: [{page_id, score, matched_terms}]} で返す
```

- IDF はコーパス（全画面）から計算。`matched_terms` に寄与上位語を入れ、**なぜこの候補か**を人が検証できるようにする
- 閾値未満しか無い要件は `candidates: []`（無理に出さない）

### 配線
- `web/services/document_autorun.py`: モデル構築後、`model["unmatched_requirements"]` に対して suggest_matches を実行し、`document_mbt.json` へ `unmatched_requirement_suggestions` として保存
- 承認モーダル（`static/js/autorun-approval.js`）: 未突合要件の一覧に候補を「候補: P012 (0.42)」形式で表示。**クリックで採用させるUIは作らない**（採用は文書側の修正 or 要件IDの明示付与で行わせ、ツール内で確定させない）
- 手動手順書（manual_procedures）の未突合節にも候補を併記

### 受け入れ基準
- AC-D1: 決定的（同一入力→同一出力）
- AC-D2: 自動リンクが発生しない（model["nodes"] の requirement_ids は従来と不変）
- AC-D3: 閾値未満の候補は出力されない / 候補ゼロの要件は空配列
- AC-D4: 日本語要件（例「宿泊プランを検索できる」）が「プラン検索」画面を候補上位に出す
- AC-D5: matched_terms が各候補に付く

---

## G. Gherkin互換の要件記述テンプレート

### 目的
boilerplate研究の知見（統制記法で抽出精度が構造的に向上）を、独自記法ではなく**BDD実務標準のGherkin**で実現する。顧客のBDD資産・人材とそのまま接続できる。

### 実装
新規 `src/ingest/gherkin_reader.py`:

```python
def is_gherkin(text: str, filename: str) -> bool     # .feature 拡張子 or Feature:/機能: 行
def parse_gherkin(text: str) -> list[dict]
    # Scenario/シナリオ → 1要件。{req_id, title, given, when, then, tags}
    # req_id: @REQ-xxx タグがあれば採用、無ければ "GH-<連番>" を付与
    # 日本語キーワード（機能/シナリオ/前提/もし/ならば）と英語の両対応
```

- 既存の参考文書取り込み（`src/ingest/` 経由の requirement_trace 生成側）に Gherkin 分岐を追加。`then` 節は期待結果として手動手順書の expected_result に引き渡す
- テンプレート提供: `docs/templates/requirements-template.feature`（日本語記入例付き）を新設し、文書駆動UIのアップロード欄近くに「記述テンプレート」リンク（`view-auto-run.html`）を追加
- 従来のMarkdown/Excel等の経路は**一切変更しない**

### 受け入れ基準
- AC-G1: 日本語・英語キーワード両方の .feature が要件として取り込まれる
- AC-G2: @REQ タグの要件IDが requirement_trace に保持され、突合・トレースに乗る
- AC-G3: Then 節が手動手順書の期待結果に現れる
- AC-G4: 非Gherkin文書の取り込み結果が従来と完全一致（回帰なし）

---

## B. レイアウト故障検知（ReDeCheck型・2類型から）

### 目的
マルチビューポート機能（P1-9）は「項目の有無」しか比較していない。ReDeCheck 5類型のうち機械判定の確実な **Viewport Protrusion（画面外はみ出し）** と **Element Collision（要素の重なり）** を幾何情報で検知する。

### 実装
1) 幾何採取 — `src/crawler/page_crawler.py`:
- `crawl_page(..., capture_geometry: bool = False)` を追加。True のとき evaluate で主要要素（`a, button, input, select, textarea, h1-h3, [role=button]`、最大200個）の `{selector概略, x, y, w, h}` と `document.documentElement.scrollWidth / clientWidth` を採取し、`PageData.element_boxes: tuple[dict, ...]`・`PageData.horizontal_overflow: bool` へ格納。既定 False（通常クロールは不変）
- `viewport/runner.py` の各ビューポートクロールでのみ `capture_geometry=True`

2) 判定 — 新規 `src/viewport/layout_failures.py`:

```python
CLAIM_SCOPE = "observed_geometry_only"
COLLISION_MIN_OVERLAP_PX = 4   # AAやborder由来の1-2px接触を故障と呼ばない

def detect_viewport_protrusion(page, viewport_width) -> list[dict]
    # bbox.x + bbox.w > viewport_width + 許容2px、または horizontal_overflow
def detect_element_collision(page) -> list[dict]
    # 葉要素（インタラクティブ要素）同士の bbox 交差面積 >= 閾値。
    # 祖先子孫関係にある要素対は除外（包含は正常）
def build_layout_failure_report(observations) -> dict
    # viewport別に {protrusions, collisions, horizontal_overflow_pages}
```

3) 出力 — `src/viewport/reporter.py` の viewport_report へ「レイアウト観測」節を追加（該当なしなら「なし」）。文言は「〜がはみ出して観測された」で統一し、**バグ断定表現を使わない**

### 受け入れ基準
- AC-B1: 幾何フィクスチャ（合成bbox）で protrusion / collision / 清浄の3系を判定できる
- AC-B2: 祖先子孫の包含は collision にならない / 2px以下の接触は報告しない
- AC-B3: capture_geometry=False の通常クロールで PageData 既存フィールドが不変（回帰なし）
- AC-B4: E2E: 故意にはみ出す要素を持つテストページで protrusion が1件検知される

---

## 対象ファイル・実装順序

新規: `src/mbt/trace_suggestions.py`, `src/ingest/gherkin_reader.py`, `src/viewport/layout_failures.py`, `docs/templates/requirements-template.feature`, 各テスト
変更: `web/services/document_autorun.py`, `static/js/autorun-approval.js`, `src/crawler/page_crawler.py`, `src/viewport/runner.py`, `src/viewport/reporter.py`, `templates/partials/view-auto-run.html`, `docs/userguide.md`, `quality/feature_contracts.yml`

順序: D → G → B（DとGは突合精度で相乗、Bは独立）。弾内でも項目ごとにコミット・マージ可。

非スコープ: 候補の自動採用UI（設計上禁止）/ ReDeCheck残り3類型（Small-Range・Wrapping・Element Protrusion の親子版）は観測データが揃った後に判断 / Gherkin の Examples テーブル展開は初版では非対応（1シナリオ=1要件）。
