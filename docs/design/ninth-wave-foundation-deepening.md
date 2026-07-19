# 第9弾 設計書 — 基盤の深化（E: Page Object出力 / H: ユーザビリティスメル / I: 画面間データ依存＋⑧フォーム到達）

- 作成日: 2026-07-19 / ステータス: **レビュー待ち**
- 根拠: ①APOGEN（SQJ 2017）・⑦Kobold（IJHCS 2017）・⑤Black Widow（S&P 2021）・⑧フォーム入力生成
- 実装担当: Opus 4.8 / 前提: 第8弾完了
- **重要な方針決定**: ⑧フォーム到達クロールは (a) **テスト環境限定・明示オプトイン・監査ログ必須** で採用（ユーザー判断 2026-07-19）

## 主張境界

| 機能 | 主張してよい | 主張してはならない |
|---|---|---|
| E Page Object | 実測要素から生成した操作抽象 | 生成コードが無修正で完全であること |
| H スメル | 実測操作イベントに現れた兆候 | それがユーザビリティ問題だと確定すること |
| I 依存追跡 | 観測した画面間のデータ伝播 | 全依存を網羅したこと |
| ⑧ フォーム到達 | 送信で新たに到達した画面の観測 | 本番安全性（テスト環境限定機能である） |

---

## E. Page Object 形式の spec.ts 出力

### 目的
APOGEN の知見（Page Object層を挟むとテストの保守性が上がり、生成コードの75%が実用）。現行のフラットな spec.ts に対し、**画面ごとのPage Objectクラス**を併産する。UI変更時の修正が1ファイルに集約され、test_rot 対策になる。

### 実装
`web/services/spec_ts_generator.py` に出力モードを追加（既定は従来のフラット、`page_object=True` で切替）:

```python
def generate_page_objects(candidates, report) -> dict[str, str]
    # page_id ごとに PageObject クラス（ロケータをプロパティ、操作をメソッド化）
def generate_spec_ts(..., page_object: bool = False)
    # page_object 時は pages/ ディレクトリ＋ PO を import する spec を出力
```

- ロケータは実測の element_id/name/aria_label から**多属性フォールバック列**（第10弾候補のSimilo型の布石として `getByRole` 優先→id→text の順）
- 出力構成: `qa_process/pages/<PageId>.page.ts` ＋ `autorun.spec.ts`（PO利用版）
- 承認モーダルに「出力形式: フラット / Page Object」トグルを追加（既定フラット・後方互換）

### 受け入れ基準
- AC-E1: PO版spec.tsが tsc 構文的に妥当（既存のnode --check相当）
- AC-E2: 同一候補からフラット版・PO版が生成でき、テストケース数が一致
- AC-E3: PageObjectクラスが画面のロケータをプロパティとして持つ
- AC-E4: 既定（page_object=False）の出力が従来と完全一致（回帰なし）

---

## H. ユーザビリティスメルの検出

### 目的
Kobold の知見（実測ユーザー操作イベントからユーザビリティ問題の兆候を検出）。ペルソナ評価と異なり**観測ベース**なので本システムの原則と整合。既存の探索セッション記録（exploration_capture / ヒートマップ）が入力データを既に持っている。

### 検出するスメル（実測イベントから機械判定できるもののみ）
| スメル | 兆候 | 実測ソース |
|---|---|---|
| 誤クリック多発 | 同一非操作領域への連続クリック | 記録イベントの座標クラスタ |
| フォーム離脱 | フォーム入力開始後、送信せず離脱 | field イベント→遷移 |
| 行き来（pogo-sticking） | A→B→A の短時間往復 | 遷移列 |
| 過剰スクロール | 目的要素到達前の大量スクロール | scroll イベント量 |

### 実装
新規 `src/ux/usability_smells.py`:

```python
CLAIM_SCOPE = "observed_interaction_signals_only"

def detect_smells(session_events: list[dict]) -> dict
    # 各スメルを閾値で検出。{smells: [{type, evidence, occurrences}], summary}
    # 閾値は定数化し、根拠（何イベント観測したか）を必ず併記
```

- `src/registry/session_store.py` の記録イベントを入力に取り、`exploration` 成果物へ `usability_smells.json` を追加
- 各スメルに「なぜそう判定したか」の実測数値を付す。**改善提案（Koboldのrefactoring相当）はしない** — 観測に留め、対処は人へ

### 受け入れ基準
- AC-H1: 4スメルそれぞれ、該当イベント列で検出・非該当で不検出
- AC-H2: 各検出に occurrences と evidence（実測数値）が付く
- AC-H3: claim_scope が付き、改善提案フィールドが存在しない
- AC-H4: 空セッションで例外を出さず smells=[] を返す

---

## I. 画面間データ依存の追跡

### 目的
Black Widow の知見（フォームで作ったデータが別画面に現れる依存の追跡）。本システムに欠けている「入力→伝播」の可視化。検索語・登録名などが**どの画面に反映されたか**を追う。

### 実装
新規 `src/crawler/data_flow.py`（**非送信の範囲で**）:

```python
CLAIM_SCOPE = "observed_reflection_only"

def track_reflections(report: dict) -> dict
    # フォームに入力された既知トークン（第3弾のtest_dataで使った値）が
    # 他画面のテキストに出現するかを突合。{flows: [{value, source_page, sink_pages}]}
```

- 第3弾の実測バリデーション（validation_observer）が入力した値を「マーカー」とし、後続クロール画面のテキストへの反映を検出
- 送信を伴わない範囲（入力観測で使った値の反映）に限定。本格的な依存追跡は⑧と統合

### 受け入れ基準
- AC-I1: source画面で入力した値がsink画面に現れる合成データで flow を1件検出
- AC-I2: 反映が無ければ flows=[]
- AC-I3: claim_scope が付く

---

## ⑧. フォーム到達クロール（テスト環境限定・オプトイン）

### 目的
登録・検索フォームの**先にある画面**へ到達し、カバレッジを本質的に上げる。送信を伴うため、本システムの非送信原則に対する**明示的で監査可能な例外**として設計する。

### 安全設計（必須要件）
1. **既定で完全無効**。有効化は環境変数 `WEBSPEC2DOC_ALLOW_FORM_SUBMIT=1` **かつ** CLI/API の明示フラグ `--allow-form-submit` の**二重オプトイン**
2. **対象ホスト許可リスト必須**: `--form-submit-hosts` で指定したホストのみ。未指定なら送信しない
3. **本番URLパターンの拒否**: `WEBSPEC2DOC_ALLOW_LOCAL` と同様のガードを流用し、明らかな本番ドメインは追加確認
4. **全送信の監査ログ**: `audit.jsonl` へ `event="form_submitted"`・method・action・入力フィールド名（値は記録しない）を必ず記録
5. **入力値は第3弾のテストデータ生成**（実測制約準拠・安全な合成値）を使用。破壊的操作の疑いがあるボタン（delete/削除/購入/決済 等の文言）はスキップ

### 実装
新規 `src/crawler/form_navigator.py`:

```python
def form_submit_enabled() -> bool
    # 二重オプトイン + ホスト許可の全成立を確認
def navigate_through_forms(page, form, host_allowlist, on_audit) -> list[str]
    # 安全な合成値で埋め、危険文言ボタンを避けて送信し、到達URLを返す
def _is_destructive_button(text: str) -> bool
    # delete/削除/購入/支払/decline 等を拒否
```

- `crawl_site` に到達拡張として組み込み。無効時は現行の非送信クロールと完全に同一動作
- `docs/userguide.md`・`docs/sdlc/50_operation/運用手順書` へ「テスト環境限定機能」として手順と警告を明記

### 受け入れ基準
- AC-8-1: 二重オプトインが揃わなければ send は発生しない（フェイクpageで送信ゼロを検証）
- AC-8-2: 許可リスト外ホストでは送信しない
- AC-8-3: 破壊的文言ボタンはスキップされる
- AC-8-4: 送信時に audit.jsonl へ値を含まないレコードが必ず残る
- AC-8-5: 全機能無効時、既存クロールの成果物が完全一致（回帰なし）

---

## 対象ファイル・実装順序

新規: `src/crawler/data_flow.py`, `src/crawler/form_navigator.py`, `src/ux/usability_smells.py`, `web/services/`（PO生成は spec_ts_generator 拡張）, 各テスト
変更: `web/services/spec_ts_generator.py`, `static/js/autorun-approval.js`, `src/registry/session_store.py` 参照, `src/crawler/page_crawler.py`, `docs/userguide.md`, `docs/sdlc/50_operation/*`, `quality/feature_contracts.yml`

順序: E → H → I → ⑧（⑧は影響最大かつ安全設計の検証に最も時間をかけるため最後）。⑧は単独PRとし、安全設計のレビューを厚く行う。

非スコープ: スメルの自動修復（Koboldのrefactoring）/ ⑧の多段フォーム（ウィザード）到達は初版では1段のみ / データ依存のLLB的な本格追跡は将来。
