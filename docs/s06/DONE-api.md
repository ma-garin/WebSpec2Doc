# S06 対検査レビュー API 完了記録（W2・2026-10-24）

## 通した経路
- GET /api/docverify/v1-a-order-payment/pair/findings（W3 の投入データ）→ doc_verify_pair.findings → pair_review.listing → data/docverify/v1-a-order-payment/pair/findings.json → **200・findings 12 件**
- 採否・取消・承認は他担当の通し確認と同じデータを同時に書き換えるため、同じ docs・findings を複製した iid=s06-api-test で確認（使用後は退避済み）。

## 実サーバ（ポート 8767・認証オフ）

| 操作 | API | status | 期待 | 要点 |
|---|---|---|---|---|
| 一覧 | GET /findings | 200 | OK | findings=12 rev=0 pass=False |
| 判定 | GET /gate | 200 | OK | pass=False 重大未解決=['V1-A-01', 'V1-A-05'] 要確認=[] 抜け=0 / changed.pass=False |
| 文書 | GET /docs | 200 | OK | req v1 14節 / design v1 14節 |
| 証跡 | GET /trail | 200 | OK | 1件 actions=['review_started'] |
| 採用 | POST /findings/V1-A-01/decide | 200 | OK | {"at": "2026-10-24T08:48:08+00:00", "by": "_none", "finding_id": "V1-A-01", "reason": "要件30秒に合わせて設計を直す", "status": "採用"} |
| 採否値が不正 | POST /findings/V1-A-01/decide | 400 | OK | bad_status: 採否は「採用」「不採用」「要確認」から選んでください。 |
| 指摘が無い | POST /findings/NOPE/decide | 404 | OK | finding_not_found: 指摘が見つかりません。一覧を再読み込みしてください。 |
| rev 不一致 | POST /findings/V1-A-02/decide | 409 | OK | conflict: 他の人が先に更新しました。再読み込みしてから操作し直してください。 |
| rev 一致 | POST /findings/V1-A-02/decide | 200 | OK | {"at": "2026-10-24T08:48:08+00:00", "by": "_none", "finding_id": "V1-A-02", "reason": "誤検出", "status": "不採用"} |
| 取消 | POST /findings/V1-A-02/revoke | 200 | OK | {"at": "2026-10-24T08:48:08+00:00", "by": "_none", "finding_id": "V1-A-02", "reason": "", "revoke": true, "status": null |
| 取消対象なし | POST /findings/V1-A-03/revoke | 400 | OK | nothing_to_revoke: 取り消す採否がありません。先に採否を選んでください。 |
| 要確認 | POST /findings/V1-A-03/decide | 200 | OK | {"at": "2026-10-24T08:48:08+00:00", "by": "_none", "finding_id": "V1-A-03", "reason": "業務担当に確認", "status": "要確認"} |
| 判定(要確認あり) | GET /gate | 200 | OK | pass=False 重大未解決=['V1-A-01', 'V1-A-05'] 要確認=['V1-A-03'] 抜け=0 / changed.pass=False |
| 承認(認証オフ) | POST /approve | 403 | OK | auth_required: 承認にはログインが必要です。ログインしてから承認してください。 |
| iid 形式不正 | GET /findings | 404 | OK | not_found: レビューが見つかりません。レビュー一覧から開き直してください。 |
| iid 存在しない | GET /findings | 404 | OK | not_found: レビューが見つかりません。レビュー一覧から開き直してください。 |
| 自動検査(既存エンジン) | POST /analyze | 200 | OK | {"added": 1, "errors": [{"detector": "semantic", "error": "未実行: LLM の接続先またはキーが未設定"}]} |
| 証跡(最終) | GET /trail | 200 | OK | 6件 actions=['review_started', 'finding_decided', 'finding_decided', 'decision_revoked', 'finding_decided', 'finding_decided'] |

## 認証あり（アプリ内テストクライアント。利用者関数だけ差し替え）

| 操作 | API | status | 期待 | 要点 |
|---|---|---|---|---|
| 起票者が一覧を開く（利用者=起票者A） | GET /findings | 200 | OK | {"findings": [{"changed_in_current": true, "decided_at": "2026-10-24T08:48:08+00:00", "decided_by": "_none", " |
| 未合格で承認（利用者=起票者A） | POST /approve | 403 | OK | gate_not_passed: 判定が不合格のため承認できません。該当の指摘を開いて採否を決めてください。 |
| 全件採否後の判定（利用者=起票者A） | GET /gate | 200 | OK | {"changed": {"missing_links": [], "needs_review": [], "pass": true, "unresolved_critical": [], "unverified": [ |
| 起票者本人が承認（利用者=起票者A） | POST /approve | 403 | OK | same_person: 起票者は自分のレビューを承認できません。別の承認者に依頼してください。 |
| 理由なしで承認（利用者=起票者A） | POST /approve | 400 | OK | reason_required: 承認の理由を入力してください。 |
| 別人が承認（利用者=承認者B） | POST /approve | 200 | OK | {"action": "approved", "at": "2026-10-24T08:48:10+00:00", "reason": "重大なし・要確認なしを確認", "target": "s06-api-test", |
| 証跡 | GET /trail | 200 | - | review_started の user=['_seed', '起票者A'] / 最後=approved by 承認者B |

## 未検証
- 実ログイン（セッション Cookie）での承認。auth.db を触らない制約のため、利用者関数の差し替えで代用した
- テナント有効時の保存先（tenants/<t>/）
- 今回の変更分: 投入データに前版が無く、changed_in_current は W3 の付与値のみ。meta.changed_sections は空
- pytest は未実行（指示なし）

## 変更要求
- docs/change-requests/S06-1.md（web/__init__.py で doc_verify_pair.bp を登録。暫定は doc_verify.py 末尾 3 行）
