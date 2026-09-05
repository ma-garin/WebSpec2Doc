# オートヒーリング 技術選定・構成・MVP・開発順序（2026-09-05）

根拠: `2026-09-05_oss-survey-auto-healing.md` / `_lit-agentic-repair-latest.md` / `_safety-and-practice-auto-healing.md`
古典 APR 文献（GenProg 系）は時間超過で打ち切り。過適合の論点は最新研究側で実測を確保済み。

## 1. 結論

既存の `web/services/healing/`（System 05）は要件 7 項目のうち 6 項目を満たしている。
**作り直さず、調査で判明した 3 つの弱点を補強する。**外部 OSS は依存先にせず設計思想のみ輸入する。

理由: Vibe Kanban（28,013★）sunset、Crystal 非推奨、gpt-engineer アーカイブ済み、Agentless 約 1 年 10 か月更新なし。
この分野の OSS 単体は短命で、依存すると保守が破綻する。

## 2. 技術選定

| 層 | 採用 | 不採用とその理由 |
|---|---|---|
| 隔離 | git worktree（既存踏襲） | Docker — 有償で使用不可。Nimbalyst/mini-swe-agent も worktree で成立している |
| 修正エンジン | 自作の薄い抽象＋CLI/API の差し替え | Aider 直接組込 — 自動コミット既定が承認ゲートより前に変更を確定させる |
| 実行モデル | `subprocess.run` の独立実行（mini-swe-agent の型） | ステートフルなシェル保持 — 並列時に状態が混ざる |
| 承認 | PR 単位（Repairnator/Dependabot 型）＋画面内 diff 逐次表示（Nimbalyst 型） | 自動マージ — 一次資料で自動マージまで踏み込んだ産業事例は 0 件 |
| LLM | OpenAI API / Ollama / Claude Code CLI / Codex CLI を対等に差し替え | 単一方式への固定 — エージェント型 vs 非エージェント型は研究上未決着 |

## 3. 補強すべき 3 点（調査で判明）

### 弱点 A: 「テスト通過＝修正成功」で確定している
実証: Lucky Pass 10.7%（AgentLens）／誤パッチ 345 件検出（UTBoost, ACL 2025）／
過学習検出はランダム選択に劣る（2026）。
対処: 検証結果を**確定ではなく証拠**として扱い、過適合リスクの兆候（テストのみ変更・
差分がテストファイルに閉じる・assert 削除）を機械的に検出して人に提示する。自動判定は導入しない。

### 弱点 B: 欠陥限局が traceback 正規表現のみ（`guess_suspect_files`）
実証: KGCompass / CoSIL / RGFL の 3 系統が独立に、限局精度の改善が解決率を数〜30pt 押し上げると報告。
対処: 限局を独立段階に切り出し、traceback に加えて import 関係・直近の変更履歴（`git log -L`）・
テスト名との対応を証拠として重ね、根拠つきで候補を出す。

### 弱点 C: バグレポートが成果物になっていない
現状は `Defect` の表と diff の折りたたみのみ。
対処: 1 欠陥 = 1 レポート（事象・再現手順・原因の判断・根拠・修正差分・未確認事項）として
画面と PR 本文の両方に出す。Getafix の「提案と人の最終判断の一致率」を後から測れる形で記録する。

## 4. システム構成（変更点のみ）

```
verification.run_verification        既存
  → localization.locate(defect)      【新】限局を独立段階に切り出す
  → agents.propose_fix(task)         既存（プロンプトに限局の証拠を渡す）
  → risk.assess(proposal)            【新】過適合リスクの兆候を検出
  → report.build(defect, proposal)   【新】バグレポート生成
  → git_ops / github_client          既存
```

`HealingAgent` Protocol は維持し、`propose_fix` の入力に限局結果を足す。
LLM バックエンドは `agents.py` の `_AGENT_CLASSES` に OpenAI / Ollama 実装を追加する。

## 5. MVP 範囲

**入れる**: 弱点 A・B・C の対処、OpenAI/Ollama バックエンド、既存 7 要件の維持。
**入れない**: 自動マージ、静的解析起点の欠陥検出、複数リポジトリ同時実行、修正案の A/B 比較。

## 6. 開発順序

| 順 | 内容 | 根拠 |
|---|---|---|
| 1 | 限局の独立段階化（弱点 B） | 解決率への寄与が最大。他の変更の入力になる |
| 2 | バグレポートの成果物化（弱点 C） | 限局の証拠が揃って初めて書ける |
| 3 | 過適合リスクの提示（弱点 A） | 修正案が出そろってから判定する |
| 4 | OpenAI / Ollama バックエンド追加 | 上記が固まってから差し替え先を増やす |
| 5 | 専用 pytest（現在 0 本） | PR #190 で「未作成」と自己申告済み |

## 7. 未確認・残課題

- 古典 APR 文献（GenProg・過適合の原典）は未収集。打ち切り。
- SapFix の一次資料に到達できず（404/403/429）。設計根拠に使っていない。
- 論文はすべて abstract ベース。本文一次確認は未実行。
- 解決率の数値はベンチマーク版・年・モデルが異なり直接比較不能。優劣の断定には使わない。
