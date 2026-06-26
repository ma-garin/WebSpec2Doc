# AIDD Kit

AI 駆動開発を、QA・E2E・仕様駆動・個人PWA・ローカル業務ツールに最適化するための個人用キットです。

この版は、`<APP_WORKSPACE>` の実プロジェクト群をスキャンした結果を反映し、ECC の資産を DAILY / LIBRARY に分けて使う前提に更新しています。

## 何が強化されたか

- ECC の膨大な skills / rules / agents を、このキットの運用方針に合わせて絞り込む `ecc-daily-router` を追加
- QA文書生成、UX監査、React PWA、QAリサーチ、QAポータル への適用表を追加
- QA / E2E / React / Python / Django / Swift の使い分けを `docs/` に整理
- Claude Code 用コマンドに `/ecc-daily` と `/app-scan` を追加
- Qiita風サイドメニュー付きの取り扱い説明書 `docs/yuki-aidd-kit-manual.html` を追加
- 今後の開発では「毎回読むもの」と「必要時だけ探すもの」を分離

## 取り扱い説明書

初心者向けのHTML版ガイドを同梱しています。

```bash
open docs/yuki-aidd-kit-manual.html
```

ブラウザで開くと、サイドメニュー付きでキットの使い方、ECCとの関係、プロジェクト別の使い分けを確認できます。

## 推奨する使い方

普段の開発では、まずこの順で使います。

1. `ecc-daily-router` で対象プロジェクトに合う ECC 資産を選ぶ
2. 仕様や大きめの変更は `sdd-ecc-workflow` で spec / plan / tasks に分ける
3. 実装後は `test-automation` と ECC の `verification-loop` を使う
4. UI / UX / QA 観点は `qa-review-standards` と ECC の `browser-qa` / `accessibility` を併用する
5. 完了前に `done-gate` を通す
6. つまずきや改善は `retro` で `lessons.md` に蓄積する

## DAILY にする ECC 資産

あなたの現在の開発傾向では、以下が常用候補です。

| ECC 資産 | 使う場面 |
|---|---|
| `skills/e2e-testing` | Playwright / E2E / スモーク確認 |
| `skills/browser-qa` | Web画面のブラウザ確認、表示崩れ、操作フロー |
| `skills/accessibility` | alt、フォームラベル、コントラスト、WCAG観点 |
| `skills/frontend-patterns` | React / Vite / HTML / CSS のUI実装 |
| `skills/react-patterns` | React finance PWA / investment hypothesis PWA 系 |
| `skills/vite-patterns` | Vite PWA / GitHub Pages 配信 |
| `skills/python-patterns` | QA document generator / storage-manager 系 |
| `skills/python-testing` | pytest / pyproject / ruff / mypy |
| `skills/django-patterns` | QA portal portal 系 |
| `skills/tdd-workflow` | ロジック変更前のテスト設計 |
| `skills/verification-loop` | 完了前の検証ストーリー |
| `skills/security-review` | APIキー、localStorage、XSS、秘密情報確認 |
| `skills/deep-research` | 技術調査、OSS比較、競合調査 |
| `skills/eval-harness` | AI出力品質、RAG、LLM judge |

## LIBRARY 扱いでよい ECC 資産

以下は必要時だけ参照します。

- Swift / iOS 系: `iOS wrapper project` の iOS wrapper に触る時だけ
- Go / Java / Kotlin / Rust / PHP / Laravel / Quarkus: 現状の `<APP_WORKSPACE>` では日常対象外
- Blockchain / DeFi / prediction market 系: 現状の主要プロジェクトとは距離がある
- 大規模 orchestration 系: 使う前に目的と費用対効果を確認

## キット構成

```text
yuki-aidd-kit/
├── README.md
├── INDEX.md
├── AGENTS.md.template
├── CLAUDE.md.template
├── docs/
│   ├── ECC-ASSET-MAP.md
│   ├── OPERATING-MODE.md
│   └── PROJECT-FIT-REPORT.md
├── skills/
│   ├── ecc-daily-router/
│   ├── sdd-ecc-workflow/
│   ├── qa-review-standards/
│   ├── test-automation/
│   ├── done-gate/
│   ├── retro/
│   └── ...
├── claude-code/
│   ├── commands/
│   │   ├── ecc-daily.md
│   │   ├── app-scan.md
│   │   └── ...
│   └── hooks/
├── scripts/
│   ├── install.sh
│   ├── verify.sh
│   └── audit-app-workspace.sh
└── templates/
```

## 導入

```bash
cd <YOUR_WORKSPACE>/yuki-aidd-kit
./scripts/install.sh
./scripts/verify.sh
```

アプリ群の棚卸しを更新する場合:

```bash
./scripts/audit-app-workspace.sh <APP_WORKSPACE>
```

## 今後の開発時の合言葉

- 「このプロジェクトに合うECCだけ選んで」 → `ecc-daily-router`
- 「仕様から進めたい」 → `sdd-ecc-workflow`
- 「UI/UXを見て」 → `qa-review-standards` + ECC `browser-qa`
- 「E2E/動作確認」 → `test-automation` + ECC `e2e-testing`
- 「完成判定」 → `done-gate` + ECC `verification-loop`
