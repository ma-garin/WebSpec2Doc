# WS2D-RL-001 リリース手順書

- 版数: 1.0 / 作成日: 2026-07-16
- 依存更新方針は `docs/specs/spec-6-2_dependency_update_strategy.md`。

## 1. ブランチ運用

- 変更はフェーズ/機能ブランチで実施し `--no-ff` で `main` へマージ。
- ブランチ命名例: `feat/*`, `fix/*`, `docs/*`。

## 2. リリース前ゲート（pre-commit / `.githooks/pre-commit`）

コミット時に自動実行される（`make setup-hooks` で導入）:
1. Python 構文チェック。
2. `make test`（L1/L2）green。
3. UI ファイル（.html/.js/.css）変更時: `.ui-verified` マーカーの UI ハッシュ照合
   （`make verify-ui` 実行済みであること）。

手動での完全ゲート:
```bash
make verify-all      # quality-harness + test + verify-ui
make coverage        # カバレッジ ≥80%
make lint            # ruff + mypy
make security        # bandit + pip-audit
```

## 3. リリース判定基準

`WS2D-TP-001` §3 を満たすこと（L0 PASS / L1・L2 全 green / L3 skip0 全 green /
カバレッジ ≥80% / 表示崩れなし / Console error ゼロ）。判定は `WS2D-TR-001` に記録。

## 4. UI 変更時の追加手順

- 見た目を変えた場合はビジュアル回帰ベースラインを意図に沿って再取得
  （`tests/e2e/snapshots/*.png` を削除 → `make verify-ui` で再生成 → 目視確認）。
- ベースラインは gitignore（環境ローカル）。

## 5. ロールバック

- マージは `--no-ff` のため、問題時は該当マージコミットを `git revert -m 1` で戻す。
- データ（`instance/` `output/`）はバックアップからリストア（`WS2D-OP-001` §4）。

## 6. 依存更新

- `make audit` で脆弱性確認 → 更新 → `make verify-all` green を確認してマージ。
