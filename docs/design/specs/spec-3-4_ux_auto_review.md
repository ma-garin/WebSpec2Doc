# SPEC-3-4 UX 自動エキスパートレビュー（Sprint C: axe-core＋ニールセン LLM 評価）

| 項目 | 値 |
|---|---|
| WBS | 3-4 |
| 優先度 / 見積 | P2 / 2sp |
| 依存 | 3-1（Shadow DOM 内要素も検査対象にするため） |
| 背景 | docs/11 §1-4・§3 Sprint C（一次判定ツール。自動検査の捕捉率は 30〜40%） |

## 1. 目的と背景

UX・ユーザビリティ検証サービスの「ツール一次判定」を提供する。(1) rules 層: クロール時に axe-core を注入して WCAG 違反を evidence 付き・confidence 1.0 で記録、(2) LLM 層: ニールセン 10 原則のヒューリスティック評価を要素レベル evidence 必須＋幻覚フィルタで生成（confidence ≤0.9）。LLM UX 評価は幻覚が既知の課題（専門家一致率 21.2% の報告）であり、**evidence-only 原則の適用が幻覚への直接対策**になる。

**現状の実装状態（実装前に必ず確認すること）:**

- 済: `src/crawler/link_extractor.py::extract_a11y_issues` — 素朴な 3 チェック（alt 欠落/ラベルなし/landmark）。**件数文字列のみで evidence なし**。PageData.a11y_issues として出力済み
- 済: `src/llm/provider.py` — LLMProvider Protocol・RulesProvider フォールバック・スキーマ違反棄却（`validate_viewpoint_payload` の前例）・evidence なし出力の除外（`_viewpoint_dicts` の前例）
- 済: ベンダリングの前例 — `static/vendor/mermaid/`（ASSET.md に version / source URL / SHA-256 / LICENSE を記録、CDN フォールバック禁止）
- 未: axe-core の同梱と注入実行・AxeViolation モデル・ニールセン評価・「UX 所見」タブ

## 2. 受け入れ条件（全て自動テストで検証すること）

- **AC-1**: axe 検査（Given: alt 欠落・ラベルなし入力を含むページ / When: `--ux-review` 付きクロール / Then: 違反が rule_id・impact・対象セレクタ・WCAG タグ・confidence 1.0 で記録される）
- **AC-2**: オフライン完結（Given: ネットワーク遮断相当の環境 / When: axe 実行 / Then: 同梱ファイルのみで動作し外部取得を行わない。同梱ファイルの SHA-256 が ASSET.md 記載値と一致する）
- **AC-3**: axe 失敗時のフォールバック（Given: axe 評価が例外 / When: クロール / Then: 警告ログを出し、既存 extract_a11y_issues の結果のみで完走する）
- **AC-4**: 幻覚フィルタ（Given: LLM が実在しないセレクタを根拠にした指摘を返す / When: 検証 / Then: その指摘は破棄され、破棄理由がログに記録される）
- **AC-5**: RulesProvider フォールバック（Given: OpenAI キーなし / When: `--ux-review` / Then: rules ベースのヒューリスティック所見（ラベルなし・タップ領域・必須表示等）が evidence 付きで生成され完走する）
- **AC-6**: レポート出力（Then: report.html に「UX 所見」タブ（重大度×画面マトリクス）と免責「自動検査は a11y 問題の 30〜40% を捕捉する一次スクリーニングです」が表示される）
- **AC-7**: `--ux-review` 未指定時、report.json のスキーマ・report_hash・既存テスト 1,222 件が変化しない
- **AC-8**: 実ブラウザ E2E がデモサイト新設ページで AC-1・3 を検証する

## 3. スコープ外

- 人の二次判定ワークフロー（指摘のトリアージ UI・ステータス管理）
- コントラスト比の独自実装（axe の color-contrast ルールに委ねる。rules フォールバックではコントラストは扱わない）
- ユーザテスト系機能（アイトラッキング・タスク完了率等）・スコアリング（点数化は誤解を生むため所見列挙のみ）
- axe-core の自動更新機構（バージョン固定・手動更新。更新手順は ASSET.md に記載）

## 4. 基本設計

### 4-1. 変更ファイル一覧

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 新規 | `src/ux/__init__.py`・`src/ux/axe_runner.py` | axe 注入・実行・AxeViolation 変換（解析層） |
| 新規 | `src/ux/assets/axe.min.js`・`ASSET.md`・`LICENSE` | axe-core 同梱（5-1） |
| 新規 | `src/ux/heuristics.py` | ニールセン 10 原則の観点テンプレートと rules フォールバック実装 |
| 変更 | `src/llm/provider.py` | Protocol へ `generate_ux_review` 追加・RulesProvider / OpenAIProvider 実装 |
| 変更 | `src/crawler/page_crawler.py` | crawl_page に ux_review オプション（axe 実行と結果保持） |
| 新規 | `src/generator/ux_reporter.py` | ux_review.json 生成・report.html「UX 所見」セクション |
| 変更 | `src/main.py` | `--ux-review` フラグ |
| 新規 | `demo/site/ux_bad.html` | 違反サンプル（alt 欠落・ラベルなし・低コントラスト・極小タップ領域） |
| 新規 | `tests/test_axe_runner.py`・`tests/test_ux_heuristics.py`・`tests/e2e/test_ux_review_e2e.py` | §6 |
| 変更 | `quality/feature_contracts.yml` | ux_review 契約を新設 |

### 4-2. データモデル

```python
# src/ux/axe_runner.py
@dataclass(frozen=True)
class AxeViolation:
    rule_id: str                      # 例: "image-alt"
    impact: str                       # "critical" / "serious" / "moderate" / "minor"
    description: str                  # 日本語化はしない（axe 原文。翻訳は幻覚リスク）
    wcag_tags: tuple[str, ...]        # 例: ("wcag2a", "wcag111")
    evidence: SourceEvidence          # selector=違反ノードの target、screenshot_path=画面撮影
    confidence: float = 1.0           # 実測（rules 層）固定

# src/ux/heuristics.py
@dataclass(frozen=True)
class UxFinding:
    principle: str                    # ニールセン原則 ID "N1"〜"N10"
    severity: str                     # "high" / "medium" / "low"
    finding: str                      # 指摘本文（日本語）
    evidence: SourceEvidence          # 必須。無い指摘は生成段階で破棄
    source: str                       # "rules" / "openai"
    confidence: float                 # rules=1.0 / LLM≤0.9
```

### 4-3. 処理フロー

```text
crawl_page(page, url, output_dir, ux_review=True)
  └─ 既存抽出の後: run_axe(page) → tuple[AxeViolation, ...]（失敗時 () ＋警告）
main._run_crawl（--ux-review 時のみ）
  ├─ 画面ごとに provider.generate_ux_review(screen_info)   # screen_info に要素インベントリ（実在セレクタ一覧）を同梱
  │    ├─ OpenAIProvider: Structured Outputs → validate_ux_payload → 幻覚フィルタ（5-3）
  │    └─ RulesProvider: heuristics.generate_ux_findings_by_rules（LLM なしで決定的）
  └─ ux_reporter.save_ux_outputs → output/{domain}/ux_review.json ＋ report.html「UX 所見」タブ
```

## 5. 詳細設計

### 5-1. axe-core の同梱方法（npm 資産の扱い）

- `src/ux/assets/axe.min.js` として単一ファイルをベンダリングする。取得元は npm パッケージ `axe-core` の `dist/axe.min.js`（jsDelivr の版数固定 URL）。mermaid の前例（`static/vendor/mermaid/ASSET.md`）に倣い、**ASSET.md に Version / Source URL / SHA-256 / 更新手順を記録**し、テストで SHA-256 一致を検証する（AC-2）
- **ライセンスは MPL-2.0**（docs/11 §1-4 の「MIT」記載は誤り。実装時に訂正すること）。ファイル無改変の同梱・注入実行は MPL-2.0 で問題ないが、`LICENSE` 全文を同ディレクトリに置く
- 配置を `static/vendor/` でなく `src/ux/assets/` にするのは、注入元が Python（src 層）であり、層分離（src から web/static へ依存しない）を守るため。読み込みは `Path(__file__).parent / "assets" / "axe.min.js"`

### 5-2. axe 実行（axe_runner）

```python
AXE_RUN_TIMEOUT_MS = 15_000

def run_axe(page: Page, screenshot_path: str | None = None) -> tuple[AxeViolation, ...]:
    """axe.min.js を page.evaluate で注入（既注入なら window.axe を再利用）し、
    axe.run(document, {resultTypes: ['violations']}) を実行して violations を変換する。
    3-1 の shadow DOM 対応後は axe が open shadow root も検査する（axe 標準機能）。
    例外・タイムアウト時は空タプルを返し警告ログ（AC-3）。"""
```

- evidence の selector は `violation.nodes[].target` の先頭（axe が返す実在セレクタ）。bbox は該当要素の bounding_box 取得を試み、失敗時 None（未取得と明示 — SPEC-3-1 §8 と同方針）
- 結果は PageData に**追加しない**（スキーマ互換保護）。crawl_page から `dict[url, tuple[AxeViolation, ...]]` をサイドチャネル（戻り値拡張でなく collector 引数）で収集し、ux_review.json に別ファイル永続化する

### 5-3. ニールセン LLM 評価と幻覚フィルタ

- Protocol 追加: `def generate_ux_review(self, screen_info: dict[str, Any]) -> list[dict[str, Any]]: ...`。screen_info には title・headings・fields（selector 付き）・buttons・axe 違反サマリ・screenshot_path と、**実在セレクタのインベントリ `known_selectors`** を含める
- OpenAIProvider: `UX_REVIEW_JSON_SCHEMA`（principle/severity/finding/selector 必須の strict schema）で Structured Outputs 実行。検証は viewpoint の前例（`validate_viewpoint_payload`）に倣い `validate_ux_payload` を新設し、(1) スキーマ違反 → 全棄却して RulesProvider へフォールバック、(2) **`selector` が known_selectors に存在しない指摘 → その 1 件を破棄し「幻覚フィルタ: 実在しないセレクタ %s を破棄」を警告ログ**（AC-4）。confidence は 0.9 を上限とする
- RulesProvider: `heuristics.py` の決定的チェック — ラベルなし入力（N6 認識負荷）、placeholder のみのラベル（N5 エラー防止）、required なのに視覚必須表示なし（N1 状態の可視性）、タップ領域 44px 未満のボタン（N7 柔軟性・効率）等。全て FieldData / bbox の実測から生成し confidence 1.0

### 5-4. エラー処理表

| 事象 | 振る舞い | ユーザー可視 |
|---|---|---|
| axe 注入・実行の失敗/タイムアウト | 空結果＋警告・クロール続行 | UX タブに「axe 検査は未実施（実行失敗）」 |
| 同梱 axe.min.js の欠落/改竄（SHA 不一致） | ux-review 開始前にエラー終了（黙って無検査にしない） | 「axe 資産が見つからないか破損しています」 |
| LLM スキーマ違反・API 失敗 | RulesProvider へフォールバック（provider.py の既存パターン） | 所見の source が "rules" と表示 |
| 幻覚指摘（実在しないセレクタ） | 該当 1 件のみ破棄・ログ記録 | 破棄件数を ux_review.json の meta に記録 |
| スクリーンショット未取得 | evidence.screenshot_path=None で継続（selector は必須のまま） | 該当指摘に「画像なし」表示 |

### 5-5. 既存コードとの接続点

- `page_crawler.py::crawl_page`（526 行〜）— extract_a11y_issues の隣で `ux_review` フラグ時のみ run_axe。既存 a11y_issues は**廃止せず併存**（互換）
- `provider.py::LLMProvider` Protocol — メソッド追加は既存実装 2 クラス（RulesProvider/OpenAIProvider）と同時に行い、`runtime_checkable` の isinstance 判定を壊さない
- `html_reporter.py::_section` / anchor 方式で「UX 所見」セクションを追加（ux_review.json がある時のみ描画 — report_hash に影響しない）
- 免責文言は docs/11 §3 Sprint C の文面を使用。全指摘に confidence と source を明示

## 6. テスト仕様

### 6-1. 単体テスト

| テスト名 | 入力 | 期待値 | AC |
|---|---|---|---|
| test_axe_asset_sha256_matches_manifest | 同梱ファイル | ASSET.md 記載の SHA-256 と一致 | AC-2 |
| test_run_axe_failure_returns_empty | evaluate が例外のフェイク page | ()・例外を出さない | AC-3 |
| test_axe_violation_has_evidence_and_confidence | フェイク axe 結果 | selector 付き evidence・confidence==1.0 | AC-1 |
| test_hallucination_selector_dropped | known_selectors 外の selector を含む LLM 応答 | 該当指摘のみ破棄・警告ログ | AC-4 |
| test_rules_fallback_generates_findings | キーなし環境相当・ラベルなしフィールド | source="rules"・evidence 付き所見 | AC-5 |
| test_schema_violation_falls_back_to_rules | 不正スキーマの LLM 応答 | 全棄却→rules 所見 | AC-4, 5 |
| test_report_json_unchanged_without_ux_review | 通常クロール相当 | ux_review.json なし・スキーマ不変 | AC-7 |

フェイク LLM 応答は `tests/test_llm_provider.py` の既存パターンに倣う。

### 6-2. 実ブラウザ E2E（tests/e2e/test_ux_review_e2e.py・専用スレッドパターン必須）

- 標的: 新設 `demo/site/ux_bad.html`（alt 欠落 img・ラベルなし input・低コントラストテキスト・20px ボタン）
- 検証: axe が image-alt / label / color-contrast 系違反を返す（AC-1）・外部ネットワークなしで完走（AC-2）・ux_review.json と report.html の UX タブ生成（AC-6）
- ポートは 8904 を使用（8898=3-1、8900=3-2、8902/8903=3-3 と衝突させない）

### 6-3. 回帰確認

- 既存 `tests/test_a11y_extraction.py`・`test_llm_provider.py`・`test_llm_wiring.py`・`test_html_reporter.py` が無変更で PASS
- `--ux-review` なしの report.json が `docs/demo/sample_output/report.json` とスキーマ差分なし（AC-7）

## 7. 完了チェックリスト（DoD）

- [ ] AC-1〜8 のテストが全て存在し PASS
- [ ] CONVENTIONS §3 の全ゲート通過
- [ ] feature_contracts.yml に ux_review 契約（failure_modes: axe_missing_asset / axe_runtime_error / llm_hallucination / llm_unavailable）
- [ ] ASSET.md（version・SHA-256・MPL-2.0 LICENSE 同梱・更新手順）の整備
- [ ] 実行パス確認: CLI `--ux-review` で ux_bad.html をクロールし、UX タブの指摘・evidence・免責表示・キーなし環境での rules フォールバックを目視確認

## 8. このタスク固有の罠

- **axe-core のライセンスは MIT ではなく MPL-2.0**（docs/11 の記載は誤り）。同梱時は LICENSE 全文必須。改変（min ファイルへのパッチ等）は MPL の開示義務を生むので行わない
- axe.min.js（約 500KB）を `page.add_init_script` で全ページに入れると**全クロールが遅くなる**。`--ux-review` 時のみ・検査直前に `page.evaluate` で 1 回注入し、`window.axe` 存在チェックで再注入を避ける
- bandit が `page.evaluate(大きな JS 文字列)` を警告することはないが、**assets の読み込みで open(...).read() の encoding 指定漏れ**は ruff で落ちる。`read_text(encoding="utf-8")` を使う
- LLM への入力に axe 違反を含めると、LLM が同内容を「自分の指摘」として再出力し二重計上になる。**rules 層由来と LLM 層由来はレポートで別セクションにし、confidence で区別**する（1.0 と ≤0.9 を混ぜない — CONVENTIONS §1-2）
- Protocol へのメソッド追加で、テスト内の自作フェイクプロバイダ（generate_viewpoints のみ実装）が isinstance(LLMProvider) を満たさなくなる可能性がある。既存フェイクの修正が必要か `grep -rn "LLMProvider" tests/` で必ず確認する
