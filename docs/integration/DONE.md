# 統合 wave B 結果

## マージ（feat/commercial-redesign・すべて --no-ff・衝突 0）
c0 ba61a80 / c2 7a0b119 / c3 e8b8ca2 / s06-pair-review 882bf20 / s00 972f69b / s01 39b912b / s02 dc1f8e3 / s03 06dddbc / s07 bed27d3 / s08 b96edce / s05 f5557f0 / s09 0666755 / s10 87ed970 / s04 7a18635

## 衝突
0 件（docs/integration/CONFLICTS.md）

## CR 適用
docs/integration/CR-APPLIED.md（15 件）

## 語彙・規則
- 判定保留→判定不能: batchtest/judge.py 1、batch-test.css 1、backendtest/judge.py 2（＋docstring 1）
- 保留（未検証 n 件）→判定不能: backendtest/judge.py 1、backendtest/stages.py 1（＋コメント 1）
- 未検証≥1→判定不能: S07 は上記置換で充足。S08 gate.py・S00 case_overview は既に充足。S09 impact/decision.py の「要確認残り」を未判定→判定不能に修正。S01・S02・S05 は UNDECIDABLE 定数の存在のみ grep で確認（計算の読み込みは未検証）
- upstream_failed 流用→internal_error: common_api.py（汎用例外 500）、orchestration.py（502→500）、store.py に internal_error:500 を追加。refs.py・versions.py は参照先読取りの失敗なので維持
- C2 revoke: 起票者または承認者以外は 403 forbidden

## 通し
- seed: v1-a-order-payment 12 件投入（src: Desktop/20261024/claude-commercial-handoff/evidence/A1/v1/A_order_payment）
- smoke docverify_pair_smoke.py @8767: OK=22 / NG=0（認証オフのため承認は 403 が期待値）

| URL | status |
|---|---|
| /orchestration /systems /dashboard | 200 |
| /test-automation /auto-run /cli | 200 |
| /healing /docverify /batch-test | 200 |
| /backend-test /impact /settings/api | 200 |
| /settings/approval /doc-app | 200 |
| /api/common/v1/cases /dev/states | 200 |
| /api/v1/jobs /api/v1/schedules | 200 |

500 は 0 件、ログの Traceback 0 件。8767 は稼働したまま。

## 未解決・要判断
- 要判断: 「未判定」（未実行の初期状態）は S01/S02/S03/S08/S09/S05 で第 4 語として使われている。判定語 3 語の規則に入れるなら全置換が必要（今回は未実行状態として残した）
- 要判断: CR-10-2 のテナント人数の取得元が無く、小規模テナント例外は人数不明として適用しない（常に禁止側）
- 要判断: S09-1 は title 一致で重複判定（差分本文は比較していない）。再利用ではなく 409 を採用
- 未検証: S05 409・S09-1 409・CR-02-001・revoke 制限・1024 幅のタブ表示・S09 非活性表示は実データでの通しを未実行。pytest・lint は未実行
