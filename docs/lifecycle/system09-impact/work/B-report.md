# B 担当報告（engine / jobs / 評価）
- 作成: web/services/impact/engine/{__init__,text,changes,embed,llm_judge,candidates,risk,tests,run}.py, web/services/impact/jobs.py, tests/test_impact_engine.py, tests/fixtures/impact_eval/（文書 6 本・cases.json 20 件・schema.sql＝DD-001 の DDL）, scripts/impact_eval.py
- テスト: `pytest tests/test_impact_engine.py -q` → 18 passed in 0.24s（PASS=18 / FAIL=0）
- 評価（`scripts/impact_eval.py --mode rule`、54 項目×20 件）: 再現率 0.974／適合率 0.532／候補率 0.129（full は接続先が無いため未実行）
- 逸脱1: jobs は調整後の契約 `start(sid, cr_code, actor, db_file, confirm_send)`・`status/cancel(db_file, job_id)` で実装。テスト・評価用に `jobs.wait(job_id)` を追加。`run.analyze` にキーワード専用の引数 `allow_send`・`judge_fn`・`embedder` を追加（confirm_send=False → 規則のみ）
- 逸脱2: 語の一致の必須語を「主題語の先頭 1 語」から「主題語のいずれか」に広げた（先頭 1 語だと再現率 0.895）。起点の項目（変更箇所そのもの）は 0 段目の候補として含める
- 逸脱3: 規則の影響度で、つながり・内容の近さだけで届いた候補は 2（BD は 3/+1/4 のみ規定）。指示文の kind は「X から Y に」→modify、削除・廃止→delete、追加→add、それ以外 text（発生可能性は条件変更 3 扱い）
- 要判断1: 分析完了後の CR の状態は analyzing のまま（DD-007 に完了時の遷移先の規定なし）。中止・失敗・中断は draft に戻す
- 要判断2: 適合率 0.532 は再現率を優先した結果。degraded_recall/precision の既定値として使うかは判断が要る
