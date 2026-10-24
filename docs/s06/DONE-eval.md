# V1 検出率の実測（DONE）

- 実行: `venv/bin/python scripts/docverify_v1_eval.py --v1 /Users/fujimagariyuki/Desktop/20261024/claude-commercial-handoff/evidence/A1/v1 --out <scratchpad>/v1_after.json`
- 所要時間: スクリプトの実行は 1 秒未満。作業全体は 18:20〜18:24（約 4 分）
- 回帰確認: `WEBSPEC2DOC_DOCVERIFY_SEMANTIC=off venv/bin/python scripts/docverify_pair_predict.py --out-defects d.jsonl --out-trace t.jsonl` を修正前（main）と修正後で比べ、バイト一致
- 結果: 合計 TP=8 / FN=28 / FP=1、再現率 0.22、適合率 0.89（詳細: evidence/V1-eval.md）
- エンジンの変更: `web/services/docverify/pair/segment.py`（REQ-A-001 形式の ID と、「機能要件」の章が無い書式への対応）
- 未実行: pytest
