# Claude × Codex 実践ガイド

このプロジェクトで得た知見 + 公式ドキュメント調査をまとめたもの。

> **正本は harness。** 実際の運用ルールは `AGENTS.md`（Codex 契約書）と `scripts/`
> （verify.sh / codex-task.sh / task-template.md）が単一の真実。本ガイドは背景と教訓を補足する。

---

## 役割分担（最重要）

| 担当 | 仕事 |
|------|------|
| **Claude** | 計画・設計・タスク分割・コードレビュー・最終確認・**commit** |
| **Codex** | 指示書の範囲内の実装（ファイル編集まで）。git 操作はしない |

> Claude が設計図を描き、Codex が現場で建てる。検証と commit は必ず Claude が行う。

---

## Codex への委任手順（決定的ループ）

過去の失敗（スタブ捏造・規約無視・タスク迷子）を防ぐため、必ず harness 経由で委任する。

```bash
# 1. 雛形からタスク指示書を作る
cp scripts/task-template.md /tmp/task.md   # ゴール / 触るファイル / 完了条件 / スコープ外 を埋める

# 2. 委任 → codex exec(workspace-write) → 直後に自動で verify.sh
./scripts/codex-task.sh /tmp/task.md

# 3. verify.sh が ALL GREEN でも、Claude が git diff をレビューしてから commit
git diff
```

### タスク指示書の書き方のコツ
- **触るファイルを明示**し、それ以外は変更させない（スコープ外も書く）
- **完了条件は `bash scripts/verify.sh` が ALL GREEN** を含める（コマンドで検証できる形）
- 推測の余地を残さない（関数名・データクラス・期待入出力まで具体的に）
- データクラスを変えるなら「`diff/snapshot.py` の (de)serialize も更新」と明記

---

## 3重の検証ゲート（なぜ harness が効くか）

過去の Codex 失敗は全て「強制力ある検証ゲートの不在」が原因だった。harness はこれを塞ぐ。

1. **AGENTS.md（規約ゲート）** — Codex が自動読込。スタブ捏造・venv編集・git操作・スコープ外変更を禁止
2. **verify.sh（機械ゲート）** — py_compile→pytest→実クロール2回→成果物チェック。スタブで「動くフリ」をすると実クロールで落ちる
3. **Claude レビュー（人的ゲート）** — green でも diff を必ず確認してから commit

---

## リトライ戦略

```
1回目失敗（verify.sh が落ちる）
  → Claude が diff と verify.sh のエラーを読み、指示書を具体化して再委任
2回目失敗
  → 指示書を分割して小さくする（1ファイル1責務）
3回目失敗
  → Claude が直接実装する（時間的に同等かそれ以下）
```

**教訓：** Codex の出力サマリーが「成功」と言っても過信しない。判定は verify.sh と diff のみ。

---

## このプロジェクトでの実績

| タスク | 担当 | 結果 |
|--------|------|------|
| Phase 2 全モジュール実装 | Codex | 成功（要レビュー修正あり） |
| mermaid `flowchart TD` → `graph LR` 修正 | Claude | 直接修正 |
| Excel生成 openpyxl 化 | Claude | 直接修正 |
| html_reporter.py | Codex → **失敗** → Claude | Claude が直接実装 |

**教訓：** Codex は「新規ファイル1本だけ作る」タスクより「既存コードベースを理解した上での大規模編集」が得意。小さな新規ファイルは Claude が直接書いた方が速い。
