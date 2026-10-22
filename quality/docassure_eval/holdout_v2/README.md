# Document Assurance holdout 測定

- 件数: 83 ケース（期待 59 項目）。LLM は使わない
- 注意: 検出器の実装を見ずに作った自作セット。件数が少なく、過学習の可能性・ラベル（rule 名）の付け誤りを含みうる。実文書への一般化や他製品との優劣を示すものではない。
- 再生成: `python scripts/docassure_holdout.py`

## 全体

- precision 0.844 / recall 0.644 / F1 0.731 / critical recall 0.605（対象 43 件）
- TP 38 / FP 7 / FN 21、FP を含むケース率 0.084

## カテゴリ別

| カテゴリ | 件数 | P | R | F1 | FP |
|---|---|---|---|---|---|
| ambiguity | 6 | 1.0 | 1.0 | 1.0 | 0 |
| boundary_gap | 5 | 1.0 | 1.0 | 1.0 | 0 |
| broken_reference | 5 | 1.0 | 1.0 | 1.0 | 0 |
| contradiction | 6 | 1.0 | 0.167 | 0.286 | 0 |
| false_positive_trap | 24 | 0.0 | None | None | 3 |
| missing_condition | 5 | None | 0.0 | None | 0 |
| numeric_conflict | 6 | 0.5 | 0.333 | 0.4 | 2 |
| permission_inconsistency | 5 | 0.75 | 0.6 | 0.667 | 1 |
| state_gap | 5 | 1.0 | 0.2 | 0.333 | 0 |
| trace_orphan | 5 | 1.0 | 1.0 | 1.0 | 0 |
| undefined_term | 5 | 1.0 | 1.0 | 1.0 | 0 |
| untestable | 6 | 0.833 | 0.833 | 0.833 | 1 |

## 未検出（FN）

- co2-01: temporal@A:6
- co2-02: semantic_candidate@A:5
- co2-03: temporal@A:5
- co2-04: semantic_candidate@A:5
- co2-05: semantic_candidate@A:5
- mc2-01: NOT_TESTABLE@A:6
- mc2-02: NOT_TESTABLE@A:6
- mc2-03: NOT_TESTABLE@A:6
- mc2-04: NOT_TESTABLE@A:6
- mc2-05: NOT_TESTABLE@A:6
- nc2-01: numeric@A:6
- nc2-03: numeric@A:5
- nc2-04: numeric@A:5
- nc2-05: numeric@A:6
- pi2-02: permission@A:5
- pi2-03: permission@A:6
- sg2-01: NOT_TESTABLE@A:5
- sg2-02: NOT_TESTABLE@A:5
- sg2-04: NOT_TESTABLE@A:5
- sg2-05: NOT_TESTABLE@A:5
- un2-02: NOT_TESTABLE@A:6

## 誤検出（FP）

- fp2-04: testability:NOT_TESTABLE
- fp2-14: conflict:numeric
- fp2-23: finding:TERM-001
- nc2-01: conflict:numeric
- nc2-05: conflict:numeric
- pi2-03: conflict:permission
- un2-04: finding:AMB-001
