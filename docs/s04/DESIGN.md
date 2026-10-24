# S04 CLI / API 設計（2026-10-24）

## 画面一覧 × 状態 9 種（/cli）

| 状態 | ジョブ一覧 | 定期クロール | 出し方 |
|---|---|---|---|
| 通常 | 表＋右の詳細 | 表＋停止 | 実データ |
| 0件 | 投入を案内 | 作らない旨 | 実データ |
| 検索0件 | 条件解除 | 該当なし | 状態で絞る |
| 読込中 | 読込表示 | 読込表示 | 取得中 |
| 失敗 | 原因＋再試行 | 原因＋再読込 | 取得失敗 |
| 権限不足 | 役割を明記 | 停止で 403 | 401/403 |
| 未保存 | 未投入の入力 | — | 離脱確認 |
| 競合 | 動くジョブへ | — | 投入で 409 |
| 復元 | 前回の選択 | — | ?job= / 保存値 |

- 本文コンテナ `#cli-jobs-body` / `#cli-sched-body` の `data-state` で切替。画面上部「表示の確認」で 9 状態を撮れる。
- 判定帯（`p5-gates`）は「全体」と「今回の投入分」を別行にし、失敗ジョブを名指しする。語彙は 合格／不合格／未判定。

## 業務フロー

1. 投入: /cli「1. 投入する」→ POST /api/v1/sites/<domain>/crawl → `api_crawl` → `job_queue.start_crawl_job`（投入者・テナント範囲を `_JOB_META` に記録）→ 202。
   - 同じサイトで待機中・実行中があれば 409 conflict（`active_job_for_domain`）。
2. 状態: GET /api/v1/jobs → `api_jobs` → `list_jobs_in_scope(_out())`（他テナントのジョブは返さない）→ 各ジョブに `view{label,reason,next_action}` と `requested_by`。動いているジョブがある間だけ画面が 3 秒ごとに再取得（最大 60 回・ブラウザ内のみ）。
3. 結果: 完了ジョブは GET /api/v1/sites/<domain>/report（output/<domain>/report.json）。
4. 証跡: 右パネルに 投入者・投入/終了時刻・終了コード・ログ末尾・ジョブ ID。
5. 定期クロール: GET /api/v1/schedules（参照のみ）→ 停止は既存 DELETE /api/v1/sites/<domain>/schedule（管理者のみ）。新規作成の口は画面に置かない。
6. エラー: 全 /api/v1 応答を after_request（`web/services/api_v1_format.py`）で `{error:{code,message}}` に揃え、成功には `meta{target,version,source}` を足す。

## 変える点
- /cli の主役をコマンドビルダーから「投入→状態→結果→証跡」に変更（ビルダーは 4 番目に残す）。
- API v1: エラー形式・meta の統一、GET /jobs・GET /schedules の新設、crawl の 409。
- OpenAPI: components（Meta / Error / Success）、全操作の 4xx/5xx を Error 参照、crawl は 202・409。

## 変えない点
- /api/v1 の既存パスと成功時の既存キー。スケジュールの作成・更新 API の挙動。job_queue のメモリ保持（再起動で消える）。

## 共通への変更要求
- なし（右パネル・判定帯は本文内で S04 の CSS として実装。殻の新設後に移す）。
