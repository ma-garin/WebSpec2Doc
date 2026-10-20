# a11y オラクル比較

- Native: webspec2doc-native-a11y / axe: 4.10.2 / ブラウザ: chrome

## Fixture（正解は manifest）

| 指標 | 値 | 基準 | 判定 |
|---|---|---|---|
| Precision | 1.000 | ≥0.95 | PASS |
| Recall | 1.000 | ≥0.90 | PASS |
| 重大 A/AA Recall | 1.000 | =1.00 | PASS |

- 重大 fixture: 50 件（評価 50 / NOT_EVALUATED 0）
- NOT_EVALUATED fixture: 0 件（PASS に数えない）
- 失敗分類: 見逃し 0 / 誤検出 0 / ルール未実装 0 / 対応付け不能 0
- 参考 axe 対正解: Precision 0.977 / Recall 0.796
