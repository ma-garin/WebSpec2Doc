# SPEC-4-1 項目定義書（Excel）＋境界値分析（BVA）テストデータ自動生成

| 項目 | 値 |
|---|---|
| WBS | 4-1（docs/0703-01_plan.md WBS-4） |
| 優先度 / 見積 | P1（即効） / 1sp |
| 依存 | なし |
| 背景 | docs/11 §5 アイデアカタログ B2（項目定義書）＋ B3（境界値テストデータ）— 評価◎ |

## 1. 目的と背景

実測済みのバリデーション属性（maxlength・minlength・min/max・pattern・required・options）は FieldData に揃っているのに、日本の SIer 開発で必ず要求される標準成果物「項目定義書」の形では出力されておらず、境界値分析（BVA）のテストデータも文言レベル（「最大長: 49/50/51文字」）で止まっている。実測ルール由来＝根拠付きの項目定義書と具体的な境界値データを生成し、「URL を入れたら納品可能な Excel が出る」を完成させる。evidence-only 原則の直接延長であり、生成 AI テスト設計の激戦区に対する差別化点（全データに実測根拠が付く）でもある。

**現状の実装状態（実装前に必ず確認すること）:**

- 済: `src/crawler/page_crawler.py::FieldData`（L126）— maxlength / minlength / min_value / max_value / pattern / required / options / default / aria_label / has_visible_label / evidence / confidence=1.0 を実測済み
- 済: `src/analyzer/test_conditions.py::derive_conditions` — 属性→テスト条件文言の導出（「最大長: n-1/n/n+1文字」等）。`_get_representative_values` に代表値 3 件の簡易生成があるが、期待結果・根拠属性を持たない
- 済: `src/main.py::_save_excel_output` — `spec.xlsx`（`XLSX_FILE_NAME`、L46）に Screens / Forms の 2 シート。ただし `_write_forms_sheet` の入力 `summarize_forms`（`src/analyzer/form_analyzer.py`）は maxlength・pattern 等を**転記していない**（page_id/url/name/field_type/required/placeholder/evidence/confidence のみ）
- 済: Doc Fusion の `official_names`（page_id→正式画面名）が `save_outputs` まで届いている（json のみ使用中）
- 未: 項目定義書シート・境界値データシート、BVA の具体値生成（値・期待結果・根拠属性の三つ組）

## 2. 受け入れ条件（全て自動テストで検証すること）

- **AC-1**: maxlength=N のフィールドから L-1 / L / L+1 の 3 ケースが生成される（Given: maxlength=50 の FieldData / When: derive_boundary_cases / Then: 値の長さ 49・50・51、期待結果は 49・50=受理 / 51=エラー、根拠属性 "maxlength"、フィールドの evidence が転記される）
- **AC-2**: min/max（number・date・range）から min-1 / min / max / max+1 の境界ケースが生成される（範囲外 2 件は期待結果=エラー）
- **AC-3**: pattern から適合例 1 件・不適合例 1 件が生成される。**機械生成できない複雑パターンは値をでっち上げず「例生成不能（手動作成要）」と明示する**（evidence-only 原則: 根拠なき値を出さない）
- **AC-4**: required から空値ケース（期待結果=必須エラー。dry-run 実測メッセージ `ValidationObservation` があればそれを期待結果に転記・confidence 1.0）が生成される
- **AC-5**: spec.xlsx に「項目定義書」シートが追加され、項目名・ラベル・型・必須・桁（min/max 長）・入力規則（pattern）・選択肢・初期値・根拠セレクタ・確信度が全実測フィールド分並ぶ。Doc Fusion 実行時は正式画面名（official_name）が画面名列に注入される
- **AC-6**: spec.xlsx に「境界値データ」シートが追加され、各ケースが 画面 / 項目 / 観点 / 入力値 / 期待結果 / 根拠属性 / 根拠セレクタ の行になる
- **AC-7**: report.json のスキーマ・report_hash は変化しない（本機能の出力は Excel のみ。既存テスト全件が無変更で PASS）
- **AC-8**: 実ブラウザ E2E: デモサイト `checkout.html`（maxlength=19/4/5/40・pattern 3 種・min/max・required 5 件が実在）をクロールして生成した spec.xlsx に両シートが載り、カード番号 pattern `[0-9 ]{13,19}` の適合/不適合例が含まれる

## 3. スコープ外

- report.json / CSV への境界値データ出力（Phase 2。report_hash 互換の検討が別途必要）
- 文書由来ルール（Doc Fusion ④ 業務ルール注入）からの境界値生成（WBS-1-2 と接続予定 — 本仕様は DOM 実測属性のみ）
- 複雑な正規表現からの網羅的な値生成（rstr 等の依存追加はしない。既知パターン辞書のみ）
- ペアワイズ・デシジョンテーブルの変更（`generate_pairwise_cases` 等は現状維持）

## 4. 基本設計

### 4-1. 変更ファイル一覧

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 新規 | `src/analyzer/bva.py` | BoundaryCase データモデルと導出ロジック |
| 変更 | `src/main.py` | `_save_excel_output` に項目定義書・境界値データシート追加（official_names を渡す） |
| 変更 | `src/analyzer/test_conditions.py` | 変更なしが原則。`_REQUIRED_CONDITION_KEYWORD` 相当の実測転記ロジックを bva.py から再利用できるよう関数公開のみ検討 |
| 新規 | `tests/test_bva.py` | 単体テスト（§6-1） |
| 新規 | `tests/e2e/test_bva_excel_e2e.py` | 実ブラウザ E2E（§6-2） |
| 変更 | `quality/feature_contracts.yml` | feature_id: `field_definition_bva` を追加 |

### 4-2. データモデル

```python
# src/analyzer/bva.py
@dataclass(frozen=True)
class BoundaryCase:
    """実測バリデーション属性から導出した境界値テストケース。"""

    field_name: str
    kind: str            # "max_length" / "min_length" / "range_min" / "range_max" /
                         # "pattern_valid" / "pattern_invalid" / "required_empty" / "option"
    value: str           # 入力値（生成不能時は ""）
    expected: str        # "受理" / "エラー（最大長超過）" / dry-run 実測メッセージ等
    source_attribute: str  # 根拠となった DOM 属性名（"maxlength" 等）
    generated: bool = True  # False = 例生成不能（AC-3。value は空、expected に手動作成要と記す）
    evidence: SourceEvidence | None = None  # FieldData.evidence を転記
    confidence: float = 1.0  # DOM 実測由来のため 1.0 固定
```

### 4-3. 処理フロー

```text
save_outputs(...)（src/main.py）
  └─ "excel" in formats:
       _save_excel_output(output_dir, pages, form_summary, official_names)
         ├─ Screens / Forms シート（既存・変更なし）
         ├─ _write_field_definitions_sheet(ws, pages, official_names)   # 新
         └─ _write_bva_sheet(ws, pages)                                 # 新
              └─ analyzer.bva.derive_boundary_cases(field) を全フィールドに適用
                 ＋ attach 相当: ValidationObservation を required_empty の expected に転記
```

FieldData は `pages: list[AnalyzedPage]` → `page.page_data.forms[].fields[]` から直接読む（`summarize_forms` は属性欠落のため使わない — 既存 Forms シートは互換のためそのまま）。

## 5. 詳細設計

### 5-1. 導出規則（`derive_boundary_cases`）

| 属性 | 生成ケース（kind / 値 / 期待結果） |
|---|---|
| maxlength=L | L-1 文字=受理、L 文字=受理、L+1 文字=エラー。値は `"あ" * n`（マルチバイトで桁数計測の齟齬も検出）と `"a" * n` の 2 系統ではなく **半角 `"a" * n` のみ**（Phase 1。全角は罠 §8） |
| minlength=m | max(m-1,0) 文字=エラー、m 文字=受理 |
| min_value/max_value（number/range） | min-1=エラー、min=受理、max=受理、max+1=エラー（int 変換できない値は生成しない） |
| min_value/max_value（date） | 前日/当日/当日/翌日（ISO 形式のみ機械生成。パース不能なら generated=False） |
| pattern | 既知パターン辞書で適合例生成: `[0-9]{n}` 系・`[0-9 ]{a,b}` 系・固定選択 `(A\|B)/...` 系。不適合例は「空白1文字」「英字混入」等の単純変異。辞書に無いパターンは generated=False |
| required | 空文字=エラー。`ValidationObservation`（field_name 一致・message 非空）があれば expected に実測メッセージを転記 |
| options | 先頭値=受理、末尾値=受理、（required でなければ）未選択=受理 |
| field_type=email | `user@example.com`=受理、`user@`=エラー、`invalid`=エラー |

規則の追加・変更は必ず `test_conditions.derive_conditions` の文言（「最大長: n-1/n/n+1文字」）と観点が一致するように保つ（境界値データは既存テスト条件の**具体化**であり、別体系を作らない）。

### 5-2. Excel シート仕様

「項目定義書」列: 画面名（official_name > title）/ 画面ID / URL / 項目名(name) / ラベル（has_visible_label 時のラベル or aria_label。無ければ「未確認」）/ 型(field_type) / 必須 / 最小桁(minlength) / 最大桁(maxlength) / 範囲(min〜max) / 入力規則(pattern) / 選択肢 / 初期値(default) / placeholder / 根拠（`_evidence_cell` 再利用） / 確信度。

「境界値データ」列: 画面ID / 項目名 / 観点(kind の日本語) / 入力値 / 期待結果 / 根拠属性 / 根拠セレクタ / 確信度。generated=False の行は入力値セルを「（例生成不能 — 手動作成要）」とする。

### 5-3. エラー処理表

| 事象 | 振る舞い | ユーザー可視 |
|---|---|---|
| maxlength が異常値（0・負） | ケース生成をスキップ（L-1 が負になる組は出さない） | シートに当該観点行なし |
| min/max が数値変換不能 | range ケースは generated=False で 1 行のみ記録 | 「例生成不能」行 |
| pattern が正規表現として不正 | re.compile 失敗を捕捉し generated=False | 同上 |
| フィールドに evidence が無い | ケースは生成するが根拠セレクタ空欄・confidence はフィールド値を踏襲 | 空欄 |

### 5-4. 既存コードとの接続点

- `src/main.py::_save_excel_output`（L840）と `save_outputs` の excel 分岐（L723）— `official_names` の引き回しを追加（json 分岐 L721 に前例あり）
- `src/analyzer/test_conditions.py::attach_observed_validation` — 実測メッセージ転記の前例。bva.py では同等ロジックを required_empty に適用
- `src/main.py::_evidence_cell`（L886）— 根拠セルの文字列化を再利用

## 6. テスト仕様

### 6-1. 単体テスト（tests/test_bva.py）

| テスト名 | 入力 | 期待値 | AC |
|---|---|---|---|
| test_maxlength_three_cases | maxlength=50 | 長さ 49/50/51 の 3 件・期待結果 受理/受理/エラー・source_attribute="maxlength" | AC-1 |
| test_range_boundaries | min=100, max=1000000（number） | 99/100/1000000/1000001 の 4 件 | AC-2 |
| test_pattern_known_generates | pattern="[0-9]{3,4}" | 適合例 "123"（3〜4桁数字）・不適合例 1 件・generated=True | AC-3 |
| test_pattern_unknown_not_fabricated | pattern="(?=.*[A-Z])(?=.*\\d).{8,}" | generated=False・value=""・expected に「手動作成」 | AC-3 |
| test_required_uses_observed_message | required=True + ValidationObservation("このフィールドを入力してください") | expected が実測メッセージ・confidence 1.0 | AC-4 |
| test_evidence_propagated | evidence 付き FieldData | 全ケースに同一 evidence | AC-1 |
| test_excel_sheets_added | tmp_path に _save_excel_output | openpyxl で読み戻し「項目定義書」「境界値データ」シート存在・列ヘッダ一致 | AC-5, 6 |
| test_official_name_injected | official_names={page_id: "与信申込入力"} | 項目定義書シートの画面名列に注入 | AC-5 |
| test_report_json_unchanged | 既存ページ相当で generate_json_report | 出力 JSON にキー追加なし（スナップショット比較） | AC-7 |

### 6-2. 実ブラウザ E2E（tests/e2e/test_bva_excel_e2e.py・専用スレッドパターン必須）

標的は既存デモページ `checkout.html`（maxlength=19/4/5/40、pattern 3 種、min=100/max=1000000、required 5 件が実在 — 新規デモページ不要）。既存 e2e のデモサーバ fixture・ポートを再利用し、新規ポートは取らない。

| テスト名 | 検証 | AC |
|---|---|---|
| test_checkout_bva_sheet_generated | crawl→excel 出力→「境界値データ」にカード番号の 13-1/13〜19/19+1 相当と pattern 適合例が載る | AC-8 |
| test_field_definition_sheet_has_pattern | 項目定義書シートに pattern `(0[1-9]\|1[0-2])/[0-9]{2}` が転記される | AC-5, 8 |

### 6-3. 回帰確認

- 既存ユニット全件 PASS、`docs/demo/sample_output/report.json` と report_hash 一致（AC-7）
- 既存 Screens / Forms シートの列・行が変化しないこと

## 7. 完了チェックリスト（DoD）

- [ ] AC-1〜8 のテストが全て存在し PASS
- [ ] CONVENTIONS §3 の全ゲート通過（black/ruff/mypy/bandit/pytest/quality_harness）
- [ ] feature_contracts.yml に `field_definition_bva`（core_files: analyzer/bva.py, main.py / failure_modes: invalid_pattern, unparsable_range, no_evidence / required_tests: happy_path, error_path, evidence）
- [ ] 実行パス確認: CLI `--format excel` で checkout.html をクロールし、spec.xlsx を実際に開いて両シートを目視確認
- [ ] 生成値の妥当性: pattern 適合例を Python `re.fullmatch` で自己検証するアサーションが実装内にある（生成→検証→不一致なら generated=False に落とす）

## 8. このタスク固有の罠

- **maxlength は「文字数」であって「バイト数」ではない**。`"a" * (n+1)` で L+1 を作るのは正しいが、実サイトはサーバ側でバイト数検証のことがある。Phase 1 は DOM 属性由来の期待結果に限定し、期待結果文言を「（HTML 属性上）エラー」と断定しすぎない
- pattern の適合例は**必ず `re.fullmatch` で自己検証してから出力**する。HTML の pattern は暗黙に `^...$` 扱い（fullmatch 相当）。`re.search` で検証すると偽の適合例を出す
- `_get_representative_values`（test_conditions.py L148）は maxlength の値を `str(n-1)` と「数値の文字列」で返す既存バグ気味の挙動がある。bva.py はこれを**流用しない**（長さ n-1 の文字列を返すこと）。既存関数の挙動変更はペアワイズ生成の回帰になるため触らない
- Excel シート追加は `wb.active`（Screens）のタイトル設定順序（main.py L847-848）に依存しない位置に `create_sheet` すること。シート順は Screens → Forms → 項目定義書 → 境界値データ で固定し、テストで順序も検証する
- BoundaryCase は frozen dataclass。options 等コレクションを持たせる場合は tuple（CONVENTIONS §4-10）
