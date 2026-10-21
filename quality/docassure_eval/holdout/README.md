# Document Assurance holdout 測定

- 件数: 60 ケース（期待 44 項目）。LLM は使わない
- 注意: 検出器の実装を見ずに作った自作セット。件数が少なく、過学習の可能性・ラベル（rule 名）の付け誤りを含みうる。実文書への一般化や他製品との優劣を示すものではない。
- 再生成: `python scripts/docassure_holdout.py`

## 全体

- precision 0.935 / recall 0.977 / F1 0.956 / critical recall 1.0（対象 27 件）
- TP 43 / FP 3 / FN 1、FP を含むケース率 0.05

## カテゴリ別

| カテゴリ | 件数 | P | R | F1 | FP |
|---|---|---|---|---|---|
| ambiguity | 4 | 0.667 | 1.0 | 0.8 | 2 |
| boundary_gap | 4 | 1.0 | 1.0 | 1.0 | 0 |
| broken_reference | 4 | 0.8 | 1.0 | 0.889 | 1 |
| contradiction | 4 | 1.0 | 1.0 | 1.0 | 0 |
| false_positive_trap | 16 | None | None | None | 0 |
| missing_condition | 4 | 1.0 | 1.0 | 1.0 | 0 |
| numeric_conflict | 4 | 1.0 | 1.0 | 1.0 | 0 |
| permission_inconsistency | 4 | 1.0 | 1.0 | 1.0 | 0 |
| state_gap | 4 | 1.0 | 1.0 | 1.0 | 0 |
| trace_orphan | 4 | 1.0 | 1.0 | 1.0 | 0 |
| undefined_term | 4 | 1.0 | 0.75 | 0.857 | 0 |
| untestable | 4 | 1.0 | 1.0 | 1.0 | 0 |

## 未検出（FN）

- h-trm-04: TERM-001@A:5

## 誤検出（FP）

- h-amb-01: testability:NOT_TESTABLE
- h-amb-03: testability:NOT_TESTABLE
- h-ref-01: testability:NOT_TESTABLE
