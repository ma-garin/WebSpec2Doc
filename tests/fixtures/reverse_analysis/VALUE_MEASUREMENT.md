# reverse analysis 価値測定（Before/After・fake provider）

2026-10-19。**fake provider による測定**。偽の rea が固定 fixture `rea_6_7_0_application_evidence.json` を返した。
実 REA は実行していないため、計画 §10・AC10 の価値ゲートは**未検証（保留）**。数値は
`value_measurement.json`、決定的な値（SHA・件数・位置）は `test_受入_固定snapshotのBeforeAfterを測定記録と照合し正解位置で数える` が毎回照合する。

## 条件

- 入力: `app/`（自己所有 3 ファイル）、固定 snapshot `runtime_snapshot.json`（SHA-256 `ccf45b4d…75b5`）
- Before: `build_screen_api_map(load_snapshot(snapshot))` の JSON（sort_keys）。SHA-256 `57b5213c…83b7`
- After: 同じ snapshot＋同じ app で `src/main.py --reverse-analysis` を実プロセス実行

## 結果

| 指標 | Before | After |
|---|---|---|
| API 実測レコード | 3 | 3（不変） |
| 静的 Evidence | 0 | 4 |
| 有用な新規 Evidence | — | 3 |
| 誤抽出・重複 | — | 0・0 |

- 新規 3 件（正解位置と照合済み）:
  - `dist/app.js` 3:41–92 の別 origin API `https://api.example.test/v1/orders`（query 依存の印付き）
  - `dist/app.js` 2:41–66 の動的 path `` `/api/users/${id}` ``（path は確定させない）
  - `dist/app.js.map` から元ソース名 `../src/app.ts`（本文は map に無く unavailable）
- 数えないもの: `dist/app.js` 1:40–59 の `/api/items` は Before の実測と同じ path なので新規に数えない。
- 対応推論: matched 0・inferred 0・ambiguous 0・unknown 6。method を provider が返さないため
  `/api/items` も実測と対応付けていない（ダミー method は補っていない）。
- 増えていないもの: route 候補 0（provider が返さない）、module 候補 0（fixture の application graph に
  `javascript-module` node が無い）、module 依存 edge は JSON に保持されない。

## 費用（fake provider）

| 指標 | Before | After |
|---|---|---|
| wall 秒（中央値） | 0.110 | 0.415 |
| peak RSS（最大） | 33.7MB | 72.1MB |
| 出力バイト | 886 | 10,942 |

- 追加秒 0.305（中央値）。After は main.py の起動（依存 import）を含む。
- 5 回計測（`/usr/bin/time -l`）。peak RSS は親プロセスのみで、fake provider の子は含まない。
- macOS 27.0.1 arm64・Python 3.12.13。5 回の After 出力はバイト一致。
- 実 REA の解析時間・メモリは未計測。
