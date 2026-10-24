# System 02 テスト自動化 — テスト設計ボード DESIGN（2026-10-24）

## 目的
S06 の要件・指摘から作られたテストケースを、根拠要件・観点・期待結果・状態つきで一覧し、
「全体」と「今回の変更分」の合否と未検証の名指しを出す。利用者はコードを書かない QA。

## 画面一覧 × 状態 9 種
対象画面: /test-automation（ホーム）内「テスト設計と判定」区画（ws-design-sec）

| 状態 | 出すもの | 出し方 | 確認 |
|---|---|---|---|
| 通常 | 表・右パネル・判定帯 | data-state=normal | 3 幅で撮影 |
| 0件 | 理由と次の行動 | only-empty 文 | 3 幅で撮影 |
| 検索0件 | 条件の提示と解除 | 条件を解除ボタン | 3 幅で撮影 |
| 読込中 | 骨組み表示 | p1-skel | 3 幅で撮影 |
| 失敗 | 原因と次の行動 | p2-banner | 3 幅で撮影 |
| 権限不足 | 必要な役割名 | 403 文言 | 文言のみ |
| 未保存 | 該当なし | 編集を持たない | 対象外 |
| 競合 | 再読込の案内 | 409 と警告帯 | API と撮影 |
| 復元 | URL から選択復元 | ?design=&case= | 直開きで確認 |

- 未保存: このボードは閲覧と基準記録だけで、編集中の値を持たない。ケース編集は既存の自動化画面が担う。
- 権限不足: 403 は ta2 の before_request が返す。画面側は「管理者に権限付与を依頼」を表示。

## 業務フロー
入口 /test-automation?design=<設計>&case=<ID>
→ GET /api/ta2/design/sources（ta2.design_sources → ta2_design.sources）
→ GET /api/ta2/design?domain=（ta2.design_board → ta2_design.board）
→ 出力: ケース（根拠要件・要件本文・関連指摘・観点・手順・期待結果・状態・根拠区分・変更有無）と判定 2 行
→ 保存: 基準記録のみ POST /api/ta2/design/baseline → output/<テナント>/<設計>/ta2/design_baseline.json（記録者・時刻・履歴 50 件）
→ エラー: 400「domain が不正です」／404「このテスト設計はまだありません。一覧から別の設計を選んでください。」／409「他の人が先に基準を記録しました。画面を再読み込みしてから記録してください。」

## 判定の規則（共通語彙 合格／不合格／判定不能／未判定）
- ケース状態: 期待結果が空か要確認 → 要確認。未実行（実行記録なし）→ 未実行。pass → 合格、fail → 失敗、flaky・不明 → 要確認。
- 判定: 0 件 → 未判定。失敗 1 件以上 → 不合格。要確認・未実行・欠落リンクが 1 件以上 → 判定不能。それ以外 → 合格。
- 名指し: 失敗・要確認・未実行のケース名、欠落リンク（S06 要件でケースが無いもの）、変更分では基準から削除されたケース。
- 今回の変更分: 記録済み基準との設計内容の差（名前・要件・観点・手順・期待結果）。基準が無ければ全件を変更分とし、その旨を表示。

## 06→02 の受け口
S06 push は擬似 domain docassure-<iid> の tests.json に入る（links_sys02.py）。ボードでは
「ドキュメント検証から受領（検証 <iid>）」と表示し、一覧の先頭に並べる。要件本文と指摘は S06 の assurance.json を読み取りだけで参照する。

## 今回変える点 / 変えない点
- 変える: web/services/ta2_design.py（新設）、web/routes/ta2.py 末尾に 3 ルート追加、templates/workspace.html にボード区画、static/js/ta2/ws-design.js・static/css/ta2-design.css（新設）。クラス名は proposal-1（p1-states・p1-side・p1-g・p1-g-h・p1-verdict・p1-tag・p1-skel）。
- 変えない: tests.json の形式、links_sys02 の I/F、既存の自動化・実行・変更・定期実行・報告パネル、ワークスペース全体の骨格（サイドバー・上部バーは共通殻のまま）。

## 廃止候補 7 ルート（test_activity.py）
GET/POST /api/ta/datasets、DELETE /api/ta/datasets/<id>、GET/POST /api/ta/manual-runs、POST /api/ta/rca、POST /api/ta/process/reopen。
- 今回は触らない（コード・応答とも変更なし）。capability-map で利用 0 件だが外部利用は未確認。
- 次段: 応答ヘッダに非推奨表示（Deprecation）を付け、1 版後にアクセスログで 0 件を確認してから削除。テストデータ管理と手動実行は本ボードの「状態」へ統合する方針。

## 共通への変更要求
- CR-02-001: /sites/<domain>/tests が docassure-<iid> を開けない（report.json 前提で / へ転送）。docs/change-requests/S02-1.md
