# Document Assurance 決定論検出ベンチマーク

- fixture: 63 件（期待 47 項目、トラップ 16 件）。LLM は使わない
- 注意: 自作 fixture での測定値。fixture 件数が少なく、実文書への一般化や他製品との優劣を示すものではない。
- 再生成: `python scripts/docassure_benchmark.py`

## 全体

- precision 1.0 / recall 0.979 / F1 0.989 / critical recall 1.0（対象 28 件）
- TP 46 / FP 0 / FN 1、FP を含むケース率 0.0、検出密度 18.47 件/100行
- 目標（参考値）precision >= 0.98、critical recall >= 0.95: 達成 {'precision': True, 'critical_recall': True}

## カテゴリ別

| カテゴリ | 件数 | P | R | F1 | critR | FP |
|---|---|---|---|---|---|---|
| ambiguity | 5 | 1.0 | 1.0 | 1.0 | None | 0 |
| boundary_gap | 4 | 1.0 | 1.0 | 1.0 | 1.0 | 0 |
| broken_reference | 4 | 1.0 | 1.0 | 1.0 | 1.0 | 0 |
| contradiction | 4 | 1.0 | 1.0 | 1.0 | 1.0 | 0 |
| false_positive_trap | 16 | None | None | None | None | 0 |
| missing_condition | 5 | 1.0 | 1.0 | 1.0 | 1.0 | 0 |
| numeric_conflict | 5 | 1.0 | 1.0 | 1.0 | 1.0 | 0 |
| permission_inconsistency | 4 | 1.0 | 1.0 | 1.0 | 1.0 | 0 |
| state_gap | 4 | 1.0 | 0.75 | 0.857 | None | 0 |
| trace_orphan | 4 | 1.0 | 1.0 | 1.0 | 1.0 | 0 |
| undefined_term | 4 | 1.0 | 1.0 | 1.0 | None | 0 |
| untestable | 4 | 1.0 | 1.0 | 1.0 | 1.0 | 0 |

## 敵対 fixture（検出してはいけない）

- 16 件中 FP 0 件、must_not 違反 0 件

## ミューテーション（正常仕様に欠陥を注入）

- 12 件中 6 件検出（0.5）。基準仕様の検出 0 件: True
  - timeout_value_change: 3/3
  - condition_deleted: 0/3
  - permission_changed: 3/3
  - error_path_deleted: 0/3

## 未検出（FN）

- sg-02: REQ-ITEMS@A:5

## 誤検出（FP、トラップ以外）

