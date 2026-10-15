# 単体テスト記録（UT）— System 09 影響度分析

> 上位: `03-detailed-design.md`（DD 単位で分岐・境界を検証）

| ID | 検証する DD | テスト | 観点 |
|---|---|---|---|
| UT-001 | DD-001, DD-002, DD-003, DD-009, DD-010 | tests/test_impact_repo.py（13 件） | 各リポジトリの正常・400/403/404/409、監査の追記のみ、ベースラインの固定、差分、役割表、本人承認の禁止、Excel 5 シート、移行の冪等 |
| UT-002 | DD-004, DD-005, DD-011 | tests/test_impact_engine.py（18 件） | 文言のみの判定、つながりの段数、n-gram への縮退、送らない設定で LLM を呼ばない、注入文、リスク式と閾値、中止で保存しない、判断の引き継ぎ、ジョブの復帰 |

## 結果（2026-10-15 15:0x 実行）

- `pytest tests/test_impact_repo.py tests/test_impact_engine.py` : 31 passed
- カバレッジ（web/services/impact、旧版テスト含む全 60 件で測定）: 合計 91%（行・分岐合算）。最低は engine/embed.py 68%（外部の埋め込み API に接続する分岐。接続先が無く未通過）
