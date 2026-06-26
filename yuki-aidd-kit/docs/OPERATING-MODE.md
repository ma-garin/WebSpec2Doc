# Operating Mode

AIDD Kit を使う時の標準作業モードです。

## 1. まずプロジェクト種別を決める

| 種別 | 代表例 | 常用スキル |
|---|---|---|
| QA Web crawler / report | QA document generator | `python-patterns`, `e2e-testing`, `qa-review-standards` |
| UX audit tool | UX_Auto_Reviewer | `browser-qa`, `accessibility`, `design-system` |
| React / Vite PWA | React finance PWA, investment hypothesis PWA | `react-patterns`, `vite-patterns`, `personal-pwa` |
| QA research / scoring | QA repository research tool | `deep-research`, `eval-harness`, `agent-eval` |
| Django portal | QA portal | `django-patterns`, `python-testing`, `security-review` |
| Single HTML tool | demo / PoC | `single-html-tool`, `qa-review-standards` |

## 2. 読む範囲を絞る

最初に読むのは原則この順です。

1. `AGENTS.md` / `CLAUDE.md`
2. `README.md`
3. `package.json` / `pyproject.toml` / `requirements.txt`
4. 変更対象に近いファイル
5. テストファイル

`node_modules`, `venv`, `.pytest_cache`, `dist`, `test-results`, `output` は通常読まない。

## 3. ECC の使い方

DAILY:

- 毎回の判断・実装・検証で使う
- プロジェクトの主要技術に一致している
- トークンを使っても回収できる

LIBRARY:

- 必要時だけ参照する
- 現在のプロジェクトでは日常利用しない
- 削除ではなく検索対象に残す

## 4. 実装ループ

```text
調査
→ 方針提示
→ 合意
→ 小さく実装
→ 軽量テスト
→ 必要ならE2E
→ done-gate
→ CURRENT_STATE / lessons 更新
```

UI変更では、ブラウザまたはスクリーンショット確認を省略しない。

## 5. 完了判定

「動いた」では完了にしない。

- ロジック変更: unit / pytest / vitest
- UI変更: smoke / Playwright / screenshot
- AI出力変更: eval / golden dataset
- セキュリティ境界: security-review
- 仕様変更: docs / CURRENT_STATE 更新

## 6. クレジット節約

- 大きなファイルを全文取得しない
- まず `rg --files` と短い `rg`
- 2分を超えそうなら方針確認
- `npm ci`, Playwright, ブラウザ実行、外部配信確認は必要性を説明してから
- full ECC ではなく `ecc-daily-router` で選ぶ
