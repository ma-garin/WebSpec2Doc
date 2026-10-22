# System06 ルールエンジン

対象: `web/services/docassure/rules/engine.py`・`rules/detectors.py`・`rules/packs/default.json`。
LLM は使わない。同じ入力は同じ結果になる。

## 構造

| 層 | 中身 |
|---|---|
| pack（データ） | `packs/default.json`。rules と params |
| 検出器（コード） | `detectors.py` の関数。`DETECTORS` 辞書で名前に結びつく |
| エンジン | `run_rules`。pack の rules を順に回し Finding と結果表を返す |

pack のキー: name・version・profile（既定 standard）・params・rules。
rule のキー: rule_id・version・name・detector・severity・why・how_to_fix・profile・enabled。

## 検出器一覧（default pack の 12 本）

| rule_id | 検出器 | 重大度 | 見るもの |
|---|---|---|---|
| AMB-001 | ambiguity | medium | 曖昧語（24 語） |
| TBD-001 | tbd | high | 未決事項（9 パターン） |
| PLH-001 | placeholder | medium | 仮置き値（5 パターン） |
| REF-001 | broken_ref | high | 参照切れ（節・別紙） |
| ID-001 | id_duplicate | high | ID 重複 |
| ID-002 | id_gap | low | ID 欠番 |
| ID-003 | id_format | low | ID 形式不一致 |
| ID-004 | id_orphan | info | 孤立 ID |
| TERM-001 | term_variance | low | 用語の表記揺れ候補 |
| NUM-001 | number_unit | medium | 単位なしの数値 |
| NUM-002 | number_range | high | 範囲の逆転 |
| REQ-ITEMS | required_items | medium | 必須項目の欠落 |

- 全ルールの profile は standard・strict。
- REQ-ITEMS は設定した必須項目に加え、文書種別ごとの必須項目（認証・アップロード・決済）と状態記述の欠け（`_state_gaps`）も見る。種別は判定語が 4 語以上あるときだけ決める。
- 各 Finding は why（なぜ重要か）・reason（原文の語を引用）・how_to_fix・confidence_basis・counter_evidence を持つ。

## 結果の 4 値

| result | 条件 |
|---|---|
| FAIL | 検出器が hit を返した |
| PASS | hit が無く skip も無い |
| NOT_APPLICABLE | enabled=false、または今の profile が対象外 |
| NOT_EVALUATED | 検出器が未実装、または評価材料が無く skip |

NOT_EVALUATED になる skip の理由（実装にある文言）:
- 本文が空
- IDの定義が文書に無い（id_duplicate / id_format / id_orphan 系）
- 連番を判定できるIDが2件以上の接頭辞が無い
- 参照元となる他文書（other_docs）が無く孤立を判定できない
- 単位必須の文脈語が未定義
- 必須項目が未設定、かつ文書種別・状態の記述から評価できない

- NOT_EVALUATED は PASS として数えない。品質スコアでも除外する（`quality._score_dim`）。
- 注意: 検出器が checked=0 のまま skip なしで終わると PASS になる（`INDEPENDENT_REVIEW.md` が同じ点を要確認としている）。

## プロジェクト固有語の足し方

エンジン側の口は `load_pack(name, extra)`。`extra` の扱い:

| キー | 動作 |
|---|---|
| ambiguous_terms | 語（文字列）を追記。正規表現はエスケープされる |
| disabled_rules | 列挙した rule_id を enabled=false にする |
| profile | pack の profile を上書き（strict 等） |
| その他の params キー | リストなら追記、それ以外は上書き（tbd_patterns・id_prefixes・required_items・term_groups 等） |

- pack 名は英数字・`_`・`-` のみ。無い pack は FileNotFoundError。
- 呼び出し口は `pipeline.analyze(..., pack_extra=...)` と、その引数 `profile`（pack 名として使われる）。

### 未結線（重要）

- `/api/docassure/.../analyze` は `pack_extra` を渡さない。HTTP 経由で語を足す手段は無い。
- `PUT /policy` は required_terms・ambiguous_terms・project_terms・disabled_rules を保存・検証できる（各 200 件以内・各語 100 字以内）。しかし `policy.as_pack_extra` を呼ぶ箇所が `web/` に無く、分析に反映されない。
- `as_pack_extra` 自体も project_terms を写さない。required_terms は required_items に写る。
- したがって現状、組織固有語を効かせるのはコードから `pack_extra` を渡す場合だけ。

## 他の検出系（pack の外）

| モジュール | 役割 |
|---|---|
| testability | 要件ごとの CAN_TEST / PARTIALLY_TESTABLE / NOT_TESTABLE / UNKNOWN |
| completeness | 要件タイプ別テンプレから網羅の候補を列挙（欠陥断定はしない） |
| boundary | 数値の上下限から境界値・同値クラスを導出。数値が無ければ TESTABILITY_GAP |
| conflict | 矛盾候補（numeric・permission・temporal・semantic_candidate） |
| glossary | 用語集の候補。同義は候補で断定しない |
| state_transition / decision_table / crud_matrix / nfr | 状態遷移・判定表・CRUD・非機能分類（すべて候補） |

- state_transition が出す検査: conflicting_transition・undefined_state・unreachable_state（high）、dead_end・no_error_path（medium）、duplicate_transition（low）。
- nfr は 16 カテゴリに分類し、数値＋単位が無ければ measurable=False。ISO/IEC 25010 は参考分類で準拠は主張しない。
- decision_table は条件が 1 変数だけなら作らない。組合せが 64 超なら pairwise 候補。原文に無い値は INFERRED。
- これらの出力は `analyzers` に入る。品質スコアには反映されない（completeness・boundary は一部の次元の固有判定に使われる）。

関連: [QUALITY_MODEL.md](QUALITY_MODEL.md) / [DOMAIN_MODEL.md](DOMAIN_MODEL.md) / [README.md](README.md)
