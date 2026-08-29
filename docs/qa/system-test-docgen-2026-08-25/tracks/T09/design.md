# テスト設計仕様書 T09 信頼性（障害許容・回復性・データ保全）

## 1. 対象と前提

- SUT: 破壊試験専用インスタンス `http://127.0.0.1:8766`（PID 実測 3742、`WEBSPEC2DOC_DATA_DIR=<scratchpad>/data8766`、CWD=リポジトリ直下）。**8765 には一切触れない。**
- モック: `http://127.0.0.1:9109`（T09 専用割当）。出力先は両インスタンス共通の `output/127.0.0.1:9109/`（CWD 相対、実測で `web/config.py: OUTPUT_DIR = Path("output")` を確認）。
- 対象コード（読み取りのみ・改変禁止）: `web/routes/crawl.py`（`/run`, `/api/cancel`, `_RUNNING_PROCS`）、`web/process.py`（`_terminate_proc`）、`web/routes/report.py`（`/api/result`）、`src/main.py` 子プロセス。
- 障害注入の対象は「クロール子プロセス（src/main.py）」「8766 本体」「`output/127.0.0.1:9109/` 配下のファイル・権限」のみ。改変は必ず バックアップ→試験→復元 をセットで行い、前後を証跡化する。
- 実行手段: curl / ps / kill / chmod のシェルスクリプト（`scripts/`）。UI 経由の操作は本トラックの範囲外（API 層で信頼性を判定する）。

## 2. テスト条件一覧

| 条件ID | テスト条件 | 契約 failure_mode | 25010 特性 | ツアー/手法 | リスク |
|---|---|---|---|---|---|
| T09-D01 | 同時実行: /run 複数本同時で run_id・_RUNNING_PROCS・出力先・SUMMARY が混線しない | crawl.partial_checkpoint（成果物の完全性） | 信頼性（成熟性） | 障害注入・並行実行 | High |
| T09-D02 | 実行中のクロール子プロセス強制終了後、UI/API がハングせず失敗を通知し、部分成果物が残り、次の実行が可能 | crawl.partial_checkpoint / crawl.cancel | 信頼性（障害許容性・回復性） | Saboteur Tour・障害注入 | High |
| T09-D03 | 本体（8766）実行中クラッシュ→再起動後、履歴にゴミレコードが残らず、成果物整合が保たれ、新規実行が可能 | crawl.partial_checkpoint | 信頼性（回復性） | 障害注入 | High |
| T09-D04 | 出力先書き込み不能時にエラーが利用者へ顕在化する（サイレント失敗しない） | crawl.partial_checkpoint（保全） | 信頼性（障害許容性） | Saboteur Tour | High |
| T09-D05 | 破損 report.json に対し /api/result が 500 でなく制御されたエラーを返す | zero_wait_sample_report 系のデータ源保全 | 信頼性（障害許容性） | 障害注入（データ破損） | Medium |
| T09-D06 | /api/cancel の冪等性: 同一 run_id 2 回・存在しない run_id で安全な応答 | crawl.cancel | 信頼性・機能適合性 | 契約ベース | Medium |
| T09-D07 | 429（Retry-After）・500・到達不能ホスト混在でも 1 ページの失敗が全体を落とさず部分結果で継続 | crawl.rate_limit_backoff / crawl.timeout | 信頼性（障害許容性） | 契約ベース・Saboteur Tour | High |

## 3. 網羅性の根拠

- ISO/IEC 25010 信頼性の副特性 4 件に全条件を対応付けた: 成熟性（D01）、可用性（D02/D03 の「次の実行が可能」「再起動後に稼働」）、障害許容性（D02/D04/D05/D07）、回復性（D02/D03）。
- `quality/feature_contracts.yml` crawl 契約の failure_modes 11 件のうち、本トラック担当分 `cancel` / `partial_checkpoint` / `timeout` / `rate_limit_backoff` を D02/D06、D01〜D04、D07、D07 でトレースした（残る `login_wall_during_crawl` 等 7 件は T02/T03/T06 担当）。
- 障害注入の対象分類は「プロセス（子/親）・ストレージ（権限/破損）・ネットワーク（429/500/到達不能）・並行性」の 4 軸で、SUT の構成要素（Flask 本体 → subprocess → ファイル出力 → 対象サイト）を経路順に網羅する。

## 4. 意図的に除外した条件と理由

| 除外条件 | 理由 |
|---|---|
| ディスクフル・I/O エラーの物理再現 | ホスト全体に影響し 8765・他トラックを巻き込むため。権限剥奪（D04）で書き込み失敗経路を代替検証 |
| 出力ディレクトリ「不存在」ケース | `output/` は起動時から存在し、他ドメインと共有のため削除禁止。読み取り専用化（chmod 555）で書き込み失敗を代替 |
| OS 再起動・電源断 | 実機が共用開発機であり許容不能。プロセス SIGKILL（D02/D03）で近似 |
| 8765 側との相互干渉試験 | 計画の絶対制約（8765 停止禁止）による。両者は同一 `output/` を共有するが、T09 は自ドメイン 9109 のみに書くため干渉しない |
| LLM API 障害時の縮退 | 本環境は実 LLM 非接続（計画 2.2 範囲外） |
