---
name: ecc-daily-router
description: 各プロジェクトに対して、ECCのskills/rules/agentsをDAILYとLIBRARYに分類して使うためのルーティングスキル。QA document generator、UX audit tool、React finance PWA、QA portal、QA repository research tool、PWA、Playwright、Python、React、Django、E2E、QAレビュー、ECC活用への言及があればこのスキルを使う。
---

# ECC Daily Router

ECC を全部読むのではなく、対象プロジェクトに合う資産だけを選ぶ。

## 基本方針

- DAILY: そのプロジェクトで毎回使う
- LIBRARY: 必要時だけ検索・参照する
- OFF: 現状の文脈では使わない

## 最初に見る証拠

1. `AGENTS.md` / `CLAUDE.md`
2. `README.md`
3. `package.json`, `pyproject.toml`, `requirements.txt`
4. `tests/`, `test/`, `playwright.config.*`
5. 変更対象ファイルの近傍

大きいファイル全文や `node_modules`, `venv`, `dist`, `output`, `test-results` は読まない。

## Project Presets

### QA document generator

使う ECC:

- `skills/python-patterns`
- `skills/python-testing`
- `skills/e2e-testing`
- `skills/browser-qa`
- `skills/security-review`
- `skills/verification-loop`

併用する Kit skills:

- `test-automation`
- `qa-review-standards`
- `done-gate`
- `sdd-ecc-workflow`

### UX_Auto_Reviewer

使う ECC:

- `skills/browser-qa`
- `skills/accessibility`
- `skills/frontend-patterns`
- `skills/e2e-testing`
- `skills/security-review`

併用する Kit skills:

- `qa-review-standards`
- `design-system`
- `test-automation`

### React finance PWA / investment hypothesis PWA

使う ECC:

- `skills/react-patterns`
- `skills/vite-patterns`
- `skills/frontend-patterns`
- `skills/security-review`
- `skills/verification-loop`

併用する Kit skills:

- `personal-pwa`
- `nfr-standards`
- `done-gate`

### iOS wrapper project

上記 React / Vite に加え、Swift wrapper を触る時だけ Swift / iOS 系を LIBRARY から呼ぶ。

### QA repository research tool

使う ECC:

- `skills/deep-research`
- `skills/eval-harness`
- `skills/security-review`
- `skills/verification-loop`

併用する Kit skills:

- `agent-eval`
- `code-doc-search`
- `sdd-ecc-workflow`

### QA portal / Django portal

使う ECC:

- `skills/django-patterns`
- `skills/python-testing`
- `skills/backend-patterns`
- `skills/security-review`
- `skills/verification-loop`

併用する Kit skills:

- `streamlit-rag-app` when AI/RAG module work exists
- `qa-review-standards`
- `agent-eval`

## 出力フォーマット

```text
STACK
- 確認した manifest / docs / test surface

DAILY
- ECC資産: 根拠
- Kit資産: 根拠

LIBRARY
- 必要時だけ使う資産

NEXT
- 最小の次アクション
- 実行が重い場合の確認事項
```

## 注意

- `ecc plan` や install を実行する前に、まず分類だけを出す
- full install は原則避ける
- UI/E2E/ブラウザ実行は必要性を説明してから
- セキュリティ・秘密情報・localStorage・外部URL取得が絡む時は `security-review` を DAILY に昇格する
