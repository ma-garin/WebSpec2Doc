# S08 バッチ・バックエンドのテスト — 設計（波 B）

## 画面 × 状態
| 画面 | 通常/0件 | 読込中/失敗 | 権限/未保存/競合/復元 |
|---|---|---|---|
| 案件一覧 | 表／案件作成の案内 | 既存バナー | 共通待ち |
| 実行履歴 | 表／未実行の文 | 既存バナー | 共通待ち |
| 観点カタログ | 表／検索 0 件 | 既存バナー | 共通待ち |
| 案件（段階1〜8） | 工程バー＋各段 | 既存バナー | 403/409 を文で表示 |

- 権限不足・未保存・競合・復元の表示関数は common-contract §2.3 で共通担当が追加する。S08 は呼ぶだけ（今回は未対応）。

## 業務フロー（入口 → 結果保存）
- 画面 /backend-test → POST /api/backend-test/jobs（案件作成）→ store.save → data/backendtest/<jid>/job.json
- 取り込み POST …/files → intake / intake_ddl → files/ と facts
- 段階 1〜6 POST …/stages/<n>/generate・approve → stages.put_generated → versions/
- 接続先（環境）POST …/envs・…/envs/<eid>/check → dbconn
- 実行 POST …/runs/preview → 確認トークン → POST …/runs → runner.start → evidence/<rid>/<case>
- 結果 GET …/runs/<rid>/results → results.merged
- 判定 POST …/judge → judge.summarize / verdict ＋ gate.bands（新設）→ job.json の judgement
- 書き出し GET …/export/report.xlsx → export
- エラー文言: 「段階 7（実行）が未承認です。先に承認してください。」「案件が見つかりません。一覧から選び直してください。」等（既存）

## 今回変える点
- 判定帯（全体／今回の変更分）を段階 8 の先頭に新設。語は共通語彙（合格／不合格／判定不能／未判定）。
- 件数だけでなく、不合格・期待値未確定・未検証のケースを名指し（ケース番号・名前・期待結果。根拠はツールチップ）。
- 判定時にケース番号一覧を保存し、次回判定で「今回の変更分」を求める。

## 変えない点
- 工程バー（段階 1〜8 のステッパー）・ケースの根拠／期待結果の保持（既存 cases の basis・expected・oracle.state）。
- ルート f-string 由来の 16 件（envs 2 / run 8 / stages 6）は capability-map の分類どおり「流用」。改名・移設しない。
- 既存 judge.verdict の文言（保留（未検証 N 件）等）は既存テスト互換のため残す。

## 共通への変更要求
- CR-08-1: 下部判定帯を殻（templates/layouts/system.html）に置き、S08 の帯を移す。
