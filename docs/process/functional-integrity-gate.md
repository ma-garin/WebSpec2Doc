# Functional Integrity Gate

作成日: 2026-06-14

## 目的

このゲートは、WebSpec2Doc の開発で「画面がある」「ボタンがある」「テストが通った」だけで完了扱いすることを禁止するための開発プロセスルールです。

過去の問題では、UX評価・ペルソナ評価・戦略レビュー・コードレビューを実施したにもかかわらず、解析速度、ログイン必須画面、途中停止、robots 制限、途中結果保存などの根幹機能が評価対象から漏れました。

この文書は、Claude / Codex / 人間レビューの共通ルールです。

## 完了判定の必須実行パス

新機能・変更・レビュー・評価は、以下の実行パスを確認するまで完了扱い禁止です。

```text
UI → API → backend route → service/core → output → persistence → error handling → user-visible evidence
```

## 不十分な完了根拠

以下だけでは完了扱いしません。

- UIが存在する
- ボタンが存在する
- テストが通る
- ペルソナ評価をした
- 戦略レビューをした
- 画面が見やすい
- コードがきれい
- それっぽい説明ができる

## 必須確認観点

critical / high risk 機能では、最低限以下を確認します。

- happy path
- failure path
- timeout
- cancellation
- auth / login wall
- robots / access restriction
- partial result / recovery
- logs or evidence
- user-visible status or error

## 未確認ルール

未確認の項目は必ず `未確認` と書きます。
未確認の項目を `完了`、`検証済み`、`問題なし` と表現してはいけません。

## RCAルール

開発プロセスの失敗が起きた場合、場当たり的な反省は禁止です。
最低限、以下の枠組みを明示して分析します。

- 5 Whys
- Fishbone
- FMEA
- CAPA
- DoD update

## ハーネス実行

完了前に以下を実行します。

```bash
python scripts/quality_harness.py
make test
make verify-ui
```

UI変更がない場合でも、品質ゲート対象の機能変更であれば `quality_harness.py` は必須です。

## 未実装 UI（WIP）の宣言義務

追加日: 2026-08-24

画面に置いたが中身が無い操作は、必ず **`data-wip="1"`** を付けて無効化し、
`quality/feature_contracts.yml` の当該機能の `wip_ui` に理由付きで宣言します。

```html
<button type="button" id="ta-plan-generate" disabled data-wip="1">AIで計画草案を作る</button>
<span class="ta-wip-note">準備中</span>
```

```json
"status": "partial",
"wip_ui": [
  { "control": "ta-plan-generate", "reason": "AIによる計画草案生成。生成処理が未実装" }
]
```

`python scripts/quality_harness.py` が以下を機械検証します。

| 規則 | 失敗させる状態 |
|---|---|
| 所有 | `data-wip` を持つテンプレートがどの機能の `ui_files` にも属していない |
| status 整合 | 未実装 UI を持つ機能が `status: "implemented"` を名乗っている |
| 宣言漏れ | 画面にある `data-wip` が `wip_ui` に無い |
| 残骸 | `wip_ui` にあるのに画面に `data-wip` が無い（実装済みなら宣言を消す） |
| 理由 | `wip_ui` の要素に `reason` が無い |

`data-wip` を持つ要素には `id` か `data-ta-action` を必ず付けます（識別子が無いと突き合わせできません）。

JS 側のユーザー可視な未実装メッセージ（`ta-wip-note` / 「準備中です」/「未実装です」）は
宣言と 1:1 で対応付けられないため、`WIP_MESSAGE_BASELINE` で件数を凍結し**増加のみ**を失敗させます。
減らしたときは BASELINE も一緒に下げます。

**なぜこの規則があるか**: 2026-08-24 まで、ハーネスの未実装検出は英語の探索語
（`UI only` / `not implemented` 等）だけを見ており、このリポジトリが実際に使っている
`data-wip` / 「準備中」を 1 件も検出できませんでした。その結果、未実装 UI を 22 箇所
抱えたテスト活動支援が `status: "implemented"` のままゲートを通過していました。

## 禁止事項

- コードを読まずにレビュー済みと言う
- 実行パスを追わずに価値評価だけで完了扱いする
- UIだけ存在する未接続機能を、`data-wip` と `wip_ui` で宣言せずに残す
- エラーをユーザーに見せずに失敗する
- 証跡なしに検証済みと報告する
