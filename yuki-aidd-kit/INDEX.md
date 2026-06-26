# AIDD Kit — INDEX

AI 駆動開発を高速・高品質にするための統合キット。Claude Code / Codex / claude.ai / ECC 横断。

## クイックスタート

```bash
cd <YOUR_WORKSPACE>/yuki-aidd-kit
./scripts/install.sh
./scripts/verify.sh
```

HTML版の取り扱い説明書:

```bash
open docs/yuki-aidd-kit-manual.html
```

新規プロジェクト:

```bash
./scripts/init-project.sh my-app pwa      # pwa | html | streamlit
```

アプリ群の現状確認:

```bash
./scripts/audit-app-workspace.sh <APP_WORKSPACE>
```

## DAILY スキル

| スキル | いつ効くか |
|---|---|
| `ecc-daily-router` | 対象プロジェクトに合う ECC 資産を DAILY / LIBRARY に分類 |
| `sdd-ecc-workflow` | 仕様駆動開発。spec / plan / tasks 生成 |
| `qa-review-standards` | ISO 25010、ISTQB severity、Whittaker ツアー |
| `test-automation` | Playwright / pytest / smoke / E2E |
| `done-gate` | 「完成」判定前の Definition of Done |
| `retro` | AIDDの進め方を lessons.md に蓄積 |
| `design-system` | AIDDツール群のUI・色・余白・レイアウト |
| `personal-pwa` | GitHub Pages PWA、localStorage、スマホUI |
| `single-html-tool` | 単一HTMLツール、社内配布、PoC |
| `streamlit-rag-app` | PMO / RAG / Streamlit / マルチテナント |
| `agent-eval` | LLM / RAG / AIエージェントの品質評価 |
| `code-doc-search` | 技術ドキュメント検索 |
| `nfr-standards` | 非機能要件の標準値 |

## ECC 連携

| ECC 資産 | 扱い | 理由 |
|---|---|---|
| `skills/e2e-testing` | DAILY | Playwright 利用プロジェクトが複数ある |
| `skills/browser-qa` | DAILY | UX audit tool / QA document generator と直結 |
| `skills/accessibility` | DAILY | alt / label / WCAG 観点が継続的に必要 |
| `skills/frontend-patterns` | DAILY | React / Vite / 静的HTMLが多い |
| `skills/python-patterns` | DAILY | Python / Flask / Django / Streamlit が多い |
| `skills/security-review` | DAILY | APIキー、localStorage、外部サイト取得が多い |
| `skills/verification-loop` | DAILY | 完了前の検証漏れ防止 |
| `skills/deep-research` | DAILY | OSS比較、QA技術調査、競合調査 |
| `rules/swift` | LIBRARY | iOS wrapper project でのみ使用 |
| Java / Go / Rust / PHP 系 | LIBRARY | 現状の主戦場ではない |

詳細は `docs/ECC-ASSET-MAP.md` を参照。

## スラッシュコマンド

| コマンド | 機能 |
|---|---|
| `/ecc-daily` | 現在のプロジェクトに合う ECC 資産を選ぶ |
| `/app-scan` | `<APP_WORKSPACE>` の棚卸し観点でプロジェクトを読む |
| `/sdd-start` | SDD 10ステップ起動 |
| `/new-pwa` | 新規PWA立ち上げ |
| `/qa-review` | ISO / ISTQB 準拠レビュー |
| `/doc-search` | 技術ドキュメント検索 |
| `/eval` | AIシステムの eval |
| `/retro` | レトロと学びの蓄積 |
| `/token-check` | トークン使用量確認 |

## 運用原則

- 全量導入より、対象プロジェクトに合う DAILY だけを読む
- LIBRARY は削除ではなく、必要時だけ検索・参照する
- UI変更はスクリーンショットかE2Eで確認する
- AI出力品質は `agent-eval`、コード動作は `test-automation`、完了判定は `done-gate` で分ける
- セッション終了時は `CURRENT_STATE.md` と `lessons.md` を更新する
