# S06 認証ありの承認フロー実証（2026-10-24）

## 実行
- 作業ツリー: feat/s06-auth の worktree。サーバは worktree 直下で `FLASK_TESTING=1 WEBSPEC2DOC_ALLOW_LOCAL=1 WEBSPEC2DOC_PORT=8771 venv/bin/python app.py`（認証 auto・worktree の instance/auth.db。起動時に初期管理者 admin/password が作られる）
- `venv/bin/python scripts/docverify_pair_auth_smoke.py <A_order_payment dir> --base http://127.0.0.1:8771`
- 手順: admin でログイン→テナント選択→/api/auth/users で A（検証レビュアーA）・B（検証承認者B）を作成→A・B が /auth/login と /auth/tenant で実ログイン（Cookie ws2d_session）→seed はテナント default の保存先へ in-process 投入→A が重大 2 件を不採用・残り 10 件を採用→解消済み→承認・取消を実行
- 認証オフの 403 だけは同じ実ルートを `create_app().test_client()`（WEBSPEC2DOC_AUTH_MODE=off）で通した

## 結果
| 手順 | 期待 | 実際 | 判定 | メッセージ |
|---|---|---|---|---|
| 利用者作成 検証レビュアーA | 200 | 200 | PASS |  |
| 利用者作成 検証承認者B | 200 | 200 | PASS |  |
| 利用者作成 検証レビュアーA | 200 | 200 | PASS |  |
| 未ログインで承認 | 401 | 401 | PASS |  |
| A が一覧を開く（起票者になる） | 200 | 200 | PASS |  |
| A 承認（未合格） | 403 gate_not_passed | 403 gate_not_passed | PASS | 判定が不合格のため承認できません。該当の指摘を開いて採否を決めてください。 |
| A 不採用 V1-A-01 | 200 | 200 | PASS |  |
| A 解消済み V1-A-02 | 200 | 200 | PASS |  |
| A 解消済み V1-A-03 | 200 | 200 | PASS |  |
| A 解消済み V1-A-04 | 200 | 200 | PASS |  |
| A 不採用 V1-A-05 | 200 | 200 | PASS |  |
| A 解消済み V1-A-06 | 200 | 200 | PASS |  |
| A 解消済み V1-A-07 | 200 | 200 | PASS |  |
| A 解消済み V1-A-08 | 200 | 200 | PASS |  |
| A 解消済み V1-A-09 | 200 | 200 | PASS |  |
| A 解消済み V1-A-10 | 200 | 200 | PASS |  |
| A 解消済み V1-A-11 | 200 | 200 | PASS |  |
| A 解消済み V1-A-12 | 200 | 200 | PASS |  |
| 判定 | 200 | 200 | PASS |  |
| 判定が合格 | 真 | 真 | PASS | 重大な未解決の指摘・要確認・対応の抜けはありません。; 未判定の指摘はありません。; 承認できます。 |
| A 承認（起票者本人） | 403 same_person | 403 same_person | PASS | 起票者は自分のレビューを承認できません。別の承認者に依頼してください。 |
| B 承認（理由なし） | 400 reason_required | 400 reason_required | PASS | 承認の理由を入力してください。 |
| B 承認 | 200 | 200 | PASS |  |
| 証跡 | 200 | 200 | PASS |  |
| 証跡の承認者＝B の表示名 | 真 | 真 | PASS | approved.user=検証承認者B |
| 証跡の起票者＝A の表示名 | 真 | 真 | PASS | review_started.user=検証レビュアーA |
| A 承認取消（承認者でない） | 403 not_approver | 403 not_approver | PASS | 承認を取り消せるのは承認した本人だけです。承認者に依頼してください。 |
| 表示名変更 b-6bdabf@example.com | 真 | 真 | PASS | 1 行 |
| B 承認取消（理由なし） | 400 reason_required | 400 reason_required | PASS | 取消の理由を入力してください。 |
| 表示名を変えた B が承認取消 | 200 | 200 | PASS |  |
| B 再取消（承認なし） | 400 not_approved | 400 not_approved | PASS | 取り消す承認がありません。一覧を再読み込みしてください。 |
| A と同じ表示名の別利用者 C が承認 | 200 | 200 | PASS |  |
| 証跡（C 承認後） | 200 | 200 | PASS |  |
| C 承認の user_id が A と異なる | 真 | 真 | PASS | C=08903b97ba3b4ad7b657684dc1c23920 A=356a2854af1c49f3b7bb8df9178d2317 |
| user_id 無しの承認を C が取消 | 403 not_approver | 403 not_approver | PASS | 承認を取り消せるのは承認した本人だけです。承認者に依頼してください。 |
| 認証オフで承認 | 403 auth_required | 403 auth_required | PASS | 承認にはログインが必要です。ログインしてから承認してください。 |

PASS=36 / FAIL=0

## 修正点
- 承認の取消 API が無かった（手順「取消 → B 本人のみ可」を実行できない）。最小差分で追加した
  - web/services/docverify/pair_review.py: `active_approval()`（最後の approved で、その後に approval_revoked が無いもの）と `revoke_approval()`（未ログイン 403 auth_required／理由なし 400／承認なし 400 not_approved／承認者以外 403 not_approver）
  - web/routes/doc_verify_pair.py: `POST /api/docverify/<iid>/pair/approve/revoke`
  - web/services/docverify/pair_cases.py: 案件一覧の段階「承認」を有効な承認だけで判定（取消後は承認に戻らない）
- 既存の承認規則（起票者本人 403・未合格 403・認証オフ 403・理由必須 400）は修正不要で効いていた。web/auth.py は未編集

- 本人判定を表示名から利用者 ID に変更（指揮官決定 2026-10-24）
  - Trail に user_id、Decision に by_id を追記（表示名 user / by は残す）。比較は same_user()（user_id 一致）、表示は表示名
  - user_id の無い既存行・ID 不明は本人扱いしない: 承認は 403 author_unknown、取消は 403 not_approver
  - smoke に「A と同じ表示名の別利用者 C が承認 → 200」「表示名を変えた B が取消 → 200」「user_id 無しの承認行の取消 → 403」を追加
  - 表示名の変更 API が無いため、smoke は worktree の instance/auth.db の users.name を直接更新して改名を再現した

## 未検証
- 取消ボタンの画面（UI）は未実装・未検証。API のみ
- pytest は未実行（指示により禁止）
- 本人承認を許す承認ポリシー（approval_policy.forbid_self_approval=false）の経路は未検証

## 要判断
1. 「取消」を承認の取消と解釈して API を足した。指摘の採否の取消（/findings/<fid>/revoke）を本人限定にする意味だった場合は別対応が要る（現状は誰でも取り消せる）
2. 未合格時の 403 文言が reasons の末尾「該当の指摘を開いて採否を決めてください。」だけで、何が不足かが出ない
