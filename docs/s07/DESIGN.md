# S07 バッチ・スクリプトのテスト 設計（v1・2026-10-24）

## 画面一覧 × 状態 9 種

| 画面 | 対応する状態 | 主な文言 |
|---|---|---|
| 案件一覧 | 通常・0件・検索0件・失敗 | 0件: 新しい案件を作る |
| 取り込み | 通常・読込中・失敗 | 形式外は理由と次の行動 |
| 観点とケース表 | 通常・0件・失敗・未保存 | 要確認は推測で埋めない |
| 判定帯 | 通常・0件・失敗 | 未検証を ID で名指し |
| テストコード・書き出し | 通常・0件・失敗 | stale を明示 |

- 権限不足・競合・復元は共通（ui-states.js）の責任。S07 は 403 の文言を返すだけ（変更なし）。

## 業務フロー
1. 取り込み → POST /api/batch-test/jobs/<id>/files → store.add_file → data/batchtest/<id>/files/
2. 読み取る → POST …/analyze → parse.analyze ＋ docverify.ingest（仕様書） → job.json の facts / spec
3. 観点とケース表 → POST …/cases → design.design ＋ boundary.cases → judge.mark_changed → job.json の cases（results は空に戻す）
4. テストコード → POST …/code → codegen.generate → job.json の sources
5. 実行（手元） → 書き出した pytest / Pester / bats を利用者が実行し JUnit XML を得る
6. 結果 → POST …/results → judge.parse_junit → job.json の results
7. 判定 → 全応答の job.verdict（store.with_export_state で毎回計算・保存しない）
- エラー文言: 「結果ファイルを読めません。JUnit 形式の XML を選んでください。」「ケース表の ID と一致する結果がありません。最新のテストコードで実行した結果を選んでください。」ほか既存。

## 今回変える点
- 既定の観点を追加（boundary.py）: 日付境界・月末／うるう年／年度末／タイムゾーン、冪等性、部分失敗・再開。
  仕様書に根拠があれば「ファイル 行（REQ-ID）」を根拠仕様に、無ければ要確認。部分失敗の再開は自動化できないので「手動確認」。
- タイムゾーンのケースは setup.env_set（TZ=UTC）で生成コードに渡す（pytest）。
- 実行結果（JUnit XML）の取り込みと、ケースごとの状態（合格／不合格／未実行／要確認／手動確認）。
- 判定帯: 「全体」と「今回の変更分」（前回の作成から観点・入力・期待結果が変わったケース、追加・記入したケース）を分けて合否、未検証を名指し、既定観点の欠落を警告。
- ケース表の列名を「入力」「根拠仕様」に揃えた。

## 変えない点
- 固定サイドバー・上部バー・殻。共通 API v1 は参照しない（S07 は自前 API のまま）。
- 既存の再実行ケース（状態遷移）は「冪等性」観点に統合した（同じ setup.rerun）。

## 共通への変更要求
- なし（v1）。承認・採否の証跡（common-contract §4）への接続は v2 で CR を出す。
