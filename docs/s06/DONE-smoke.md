# S06 W3 検証データ投入と通し確認（2026-10-24 17:49）

## 投入（scripts/docverify_pair_seed.py）
- 本体は W2 が pair_review.seed() を呼ぶ形に書き換えた。W3 は検証用の付与・退避オプションを足した
- 実行: `venv/bin/python scripts/docverify_pair_seed.py <A_order_payment dir> --replace <退避先>`（既存 pair/ は削除せず mv）
- **検証用の付与（元データに無い値）**: V1-A-01・V1-A-05 を severity=重大、V1-A-01・V1-A-03・V1-A-08 を changed_in_current=true。meta.json の note にも同文を記録。付けない場合は `--no-test-marks`
- 結果: 指摘 12 件、重大 2 件、今回の変更分 3 件

## 通し確認（scripts/docverify_pair_smoke.py → 8767・W2 起動の認証オフサーバ）
| 手順 | 要求 | 期待 | 実際 | 判定 | エラー文 |
|---|---|---|---|---|---|
| 指摘の取得 | GET /findings | 200 | 200 | OK |  |
| 採否 V1-A-01 | POST /findings/V1-A-01/decide | 200 | 200 | OK |  |
| 採否 V1-A-02 | POST /findings/V1-A-02/decide | 200 | 200 | OK |  |
| 採否 V1-A-03 | POST /findings/V1-A-03/decide | 200 | 200 | OK |  |
| 取消 V1-A-03 | POST /findings/V1-A-03/revoke | 200 | 200 | OK |  |
| 判定（未合格） | GET /gate | 200 | 200 | OK |  |
| 承認（未合格） | POST /approve | 403 | 403 | OK | 承認にはログインが必要です。ログインしてから承認してください。 |
| 不採用 V1-A-01 | POST /findings/V1-A-01/decide | 200 | 200 | OK |  |
| 採用 V1-A-02 | POST /findings/V1-A-02/decide | 200 | 200 | OK |  |
| 採用 V1-A-03 | POST /findings/V1-A-03/decide | 200 | 200 | OK |  |
| 採用 V1-A-04 | POST /findings/V1-A-04/decide | 200 | 200 | OK |  |
| 不採用 V1-A-05 | POST /findings/V1-A-05/decide | 200 | 200 | OK |  |
| 採用 V1-A-06 | POST /findings/V1-A-06/decide | 200 | 200 | OK |  |
| 採用 V1-A-07 | POST /findings/V1-A-07/decide | 200 | 200 | OK |  |
| 採用 V1-A-08 | POST /findings/V1-A-08/decide | 200 | 200 | OK |  |
| 採用 V1-A-09 | POST /findings/V1-A-09/decide | 200 | 200 | OK |  |
| 採用 V1-A-10 | POST /findings/V1-A-10/decide | 200 | 200 | OK |  |
| 採用 V1-A-11 | POST /findings/V1-A-11/decide | 200 | 200 | OK |  |
| 採用 V1-A-12 | POST /findings/V1-A-12/decide | 200 | 200 | OK |  |
| 判定（合格） | GET /gate | 200 | 200 | OK |  |
| 承認（合格） | POST /approve | 403 | 403 | OK | 承認にはログインが必要です。ログインしてから承認してください。 |
| 証跡 | GET /trail | 200 | 200 | OK |  |

OK=22 / NG=0

- 証跡: finding_decided 15・decision_revoked 1・review_started 1。認証オフのため user は "_none"
- 承認は認証オフで 403（合格条件どおり）。メッセージ「承認にはログインが必要です。ログインしてから承認してください。」
- 承認の成功・同一人物の 403: **未検証（認証ありで C2/S10 が確認）**
- 1 回目は全件「採用」で実行し、判定が未合格のまま（NG=1）になった。pair_review._judge は重大を「不採用」以外すべて未解決として数えるため。2 回目は重大を不採用にして合格経路を確認した（上の表）

## 横スクロール（ヘッドレス Chrome・8769 の自前サーバ・DV.show('pair')）
| 幅 | 横スクロール | 状態 | カード |
|---|---|---|---|
| 1024 | 0 px | normal | 12 |
| 1366 | 0 px | normal | 12 |
| 1920 | 0 px | normal | 12 |
- 対検査ビュー内で、はみ出したまま overflow が auto/scroll/hidden になっていない要素: 0 件（3 幅とも）
- 一覧からのクリックではなく、DV.state.review を入れて DV.show('pair') で開いた。一覧から開く導線は未検証
- スクショ: scratchpad の pair-1024.png / pair-1366.png / pair-1920.png

## 要判断
1. 「採用」の意味: 契約の合否規則では、重大を採用（＝不具合として認める）にすると未解決として残る。「全件採用で承認可」になるのは不採用か修正済みの扱いを足した場合だけ。W2 の解釈（採用＝未解決）でよいか
2. v1-a-order-payment は既存の検査（inspection）に無いため、レビュー一覧に出ない可能性がある（未確認）
