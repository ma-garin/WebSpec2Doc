# AIDD Kit — INDEX

YukiのAI駆動開発を高速・高品質にするための統合キット。Claude Code / Codex / claude.ai 横断。

## クイックスタート

```bash
# 1. キット導入（~/.claude へ）
./scripts/install.sh
./scripts/verify.sh        # 配置確認

# 2. 新規プロジェクト作成
./scripts/init-project.sh my-app pwa      # pwa | html | streamlit

# 3. Claude Code / Codex で開発開始
# → スキルは自動発動、コマンドは /sdd-start 等で起動
```

---

## 全体構成と役割

### スキル（自動発動。会話内容に応じてClaudeが参照）
| スキル | いつ効くか |
|---|---|
| `design-system` | UI・色・レイアウトを決める時。具体的なhex/px値を提供 |
| `single-html-tool` | UX Reviewer / QA Lens系の単一HTMLツール作成 |
| `personal-pwa` | GitHub Pages PWA（家計簿・日記・スケジュール） |
| `streamlit-rag-app` | pmo_agent系。VeriRAG・16モジュール・マルチテナント |
| `sdd-ecc-workflow` | 仕様駆動開発。spec/plan/tasks生成・cc-sdd・ECC |
| `qa-review-standards` | レビュー・テスト。ISO 25010・ISTQB・Whittaker |
| `nfr-standards` | 非機能要件をspec.mdに書く時。種別別NFR |
| `code-doc-search` | 技術ドキュメント検索（web_search最適化・無料） |
| `test-automation` | 成果物の実テスト生成・実行（Playwright/pytest） |
| `agent-eval` | 自作AIシステムのeval（Weave相当・無料スタック） |
| `retro` | AIDDプロセスの振り返り・学びの蓄積 |
| `done-gate` | 「完成」判定の前。Definition of Done検証 |

### スラッシュコマンド（明示的に呼ぶ）
| コマンド | 機能 |
|---|---|
| `/sdd-start` | SDD 10ステップ起動（spec/plan/tasks生成） |
| `/new-pwa` | 新規PWA立ち上げ |
| `/qa-review` | ISO/ISTQB準拠レビュー実行 |
| `/doc-search` | 技術ドキュメント特化検索 |
| `/eval` | 自作AIシステムのeval実行 |
| `/retro` | レトロと学びの蓄積 |
| `/token-check` | トークン使用量確認・最適化提案 |

### Hooks（完全自動）
| hook | タイミング |
|---|---|
| `pre-write-check` | 書き込み前: 秘密情報・外部分割を警告 |
| `post-write-html` | HTML保存後: 行数・localStorage確認 |
| `session-summary` | セッション終了: コミット漏れ・記録漏れ検出 |

### テンプレート
| ファイル | 用途 |
|---|---|
| `CLAUDE.md.template` | Claude Code グローバル設定 |
| `AGENTS.md.template` | Codex グローバル設定 |
| `templates/CURRENT_STATE.md` | セッション間引き継ぎ（最重要） |
| `templates/ADR-template.md` | 設計判断の記録 |
| `templates/lessons.md` | AIDDプロセス改善ログ（retro用） |

### CI/CD（GitHub Actions・全て無料枠）
| ファイル | 機能 |
|---|---|
| `github-actions/deploy.yml` | GitHub Pages 自動デプロイ |
| `github-actions/secret-scan.yml` | gitleaksで秘密情報スキャン |
| `scripts/pre-commit` | ローカルのコミット前スキャン |

---

## コンテキスト維持の運用（速度に最も効く）

毎セッションの「どこまで進んだか説明」をゼロにするのが高速化の核心。

1. プロジェクトごとに `CURRENT_STATE.md` を置く
2. セッション終了時に5分で更新（session-summary hookが促す）
3. 次回開始: `CURRENT_STATE.mdを読んで再開して` の1行

## モデル使い分け（コスト・品質の最適化）
- **設計・仕様策定・難しい判断**: Opus（品質優先）
- **実装・反復編集・定型作業**: Sonnet（速度・コスト優先）

## 3面の使い分け
- **claude.ai（Fold5・外出先）**: 構想・仕様策定・AIDDラボで議論
- **Claude Code（M1 Mac）**: 実装・レビュー・コミット
- **Codex**: AGENTS.mdで同じ規約を共有。Claude Codeの代替/併用

---

## 品質ループ（test / eval / retro）

3層で品質を担保する。責務を混同しない。

| 層 | 問い | ツール |
|---|---|---|
| **test-automation** | コードは動くか（決定的） | Playwright / pytest |
| **agent-eval** | AI出力は良いか（非決定的） | DeepEval + Langfuse自前 |
| **retro** | 進め方は良いか（プロセス） | lessons.md |

### eval（Weave相当）の無料スタック
- **DeepEval**: pytest-nativeの回帰ゲート（`evals/`）
- **Langfuse セルフホスト**: NEC Mate SFFにDocker。トレース・データセット・LLM-as-judge UI。Tailscale経由でFold5から閲覧
- **judge**: 業務はOpenAI API（GPT-4o系）、個人PWAはGemini無料枠/Ollama

### 最初の一歩
1. `evals/datasets/` に実運用ログから20-50件のゴールデンデータを作る
2. `/eval pmo_agent` でスコアラーを選定しベースライン記録
3. プロンプト変更のたびに `/eval` で回帰チェック → done-gateが要求
