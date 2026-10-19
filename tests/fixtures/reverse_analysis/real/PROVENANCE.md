# real/ fixture の出所（実 REA 6.7.0）

`raw/*.rea.json` は実 REA 6.7.0（rea-agents、Node 24.11.0）の `analyze-javascript-application <dir> --json` の
stdout そのもの。手で組んだ値は無い。加工は次の 2 点だけ。

1. 絶対の入力パス（`normalized_result.input_path` と同じ文字列の出現すべて）を `<input>` に置換
2. 置換で変わった commitment（`jag_*`・`ev_`）を `tests/test_reverse_analysis_adapter.py` の `recommit` で計算し直し、
   `validate_evidence` が通ることを確かめた。JSON は区切りを詰めて保存（値は不変）

| raw | 入力 dir | 実行 |
|---|---|---|
| controlled.rea.json | `app/`（`routes/`=Wave A1、`modules/`=Wave A3、`mapped/`=Wave A2 normal を 1 つにまとめた自己所有 fixture） | 2026-10-19 exit 0・2.30s |
| missing.rea.json | `missing/`（Wave A2 missing。map 無し） | Wave A2 の実行結果を再利用 |
| malformed.rea.json | `malformed/`（Wave A2 malformed。壊れた map） | Wave A2 の実行結果を再利用 |

`measure_value.py` は Before（変更前コードの退避コピー）と After を同じ real/app・同じ runtime_snapshot.json で
実 REA に通し、`docs/research/reverse-analysis/REAL_REA_VALUE_MEASUREMENT.json` を書く（手動で 1 回だけ実行）。
