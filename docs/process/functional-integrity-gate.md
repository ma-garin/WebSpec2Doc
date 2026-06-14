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

## 禁止事項

- コードを読まずにレビュー済みと言う
- 実行パスを追わずに価値評価だけで完了扱いする
- UIだけ存在する未接続機能を残す
- エラーをユーザーに見せずに失敗する
- 証跡なしに検証済みと報告する
