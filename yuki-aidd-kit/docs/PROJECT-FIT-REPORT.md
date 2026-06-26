# Project Fit Report

作成日: 2026-06-23

対象: `<APP_WORKSPACE>`

## Summary

現在の開発スタイルは、ECC の以下の領域と親和性が高いです。

- QA / software testing
- Playwright / browser automation
- Python web tooling
- React / Vite / localStorage PWA
- UX / accessibility review
- spec-driven development
- AI output eval / RAG evaluation

ECC は full bundle として使うより、DAILY と LIBRARY に分けて薄く接続するのが合います。

## Evidence

スキャンで見えた主なファイル傾向:

- `.md`: 多い。仕様、AGENTS、README、戦略文書を重視
- `.py`: QA document generator / QA portal / storage-manager
- `.js` / `.html`: UX audit tool / 学習PWA / 静的ツール
- `.jsx` / `.tsx` / `.ts`: React / Vite / TypeScript
- `.swift`: iOS wrapper project の iOS wrapper

代表プロジェクト:

- `014_QA document generator`: Flask / Playwright / pytest / QAドキュメント生成
- `UX_Auto_Reviewer`: Node / Express / Playwright / UX監査
- `React finance PWA`: React 19 / Vite / MUI / localStorage
- `iOS wrapper project`: React/Vite + Swift wrapper
- `QA repository research tool`: QA会社向けOSS調査・分類・評価
- `sandbox/QA portal`: Django / HTMX / SQLite / QAポータル
- `yuki-aidd-kit`: 個人AIDD運用キット

## Recommendation

1. `ecc-daily-router` をこのキットの入り口にする
2. QA document generator / UX audit tool / React finance PWA / QA portal ごとに DAILY を切り替える
3. `done-gate` と `verification-loop` を常に完了前に使う
4. つまずいた運用は `retro` でキットへ戻す
5. 将来的に install を自動化する場合も、ECC full ではなく selected skills を使う
