# pair_v1 — 要件定義書⇔基本設計書 対検査の評価セット

## 目的

V 字モデルの左側で行う「上流文書と下流文書の対検査」（要件定義書と基本設計書の突き合わせ）を、
ネットワーク・LLM を使わずにオフラインで測る。検出器の出力（不整合の指摘・追跡リンク）を
正解と照合し、適合率・再現率・F1 を出す。採点は `scripts/docverify_pair_eval.py`。

## 構成

```text
pair_v1/
  README.md
  <組 ID>/              1 組 = 要件定義書 1 本と、それを受けた基本設計書 1 本
    requirements.md     要件定義書（日本語）
    basic_design.md     基本設計書（日本語）
    defects.jsonl       正解の不整合（1 行 1 件）
    trace.jsonl         正解の追跡（要件 1 件ごとに 1 行）
```

## データ形式

行番号は 1 始まり。`[a, b]` は a 行目から b 行目まで（両端を含む）。quote は該当行範囲の中にそのまま含まれる文字列。

`defects.jsonl` の 1 行:

```json
{"pair": "P01", "id": "D1", "type": "CONTRADICTION", "req_lines": [3, 3], "design_lines": [3, 3],
 "req_quote": "8文字以上", "design_quote": "6文字以上", "explanation": "最小桁数が食い違う"}
```

- `type` は次の 7 種: `MISSING_IN_DESIGN` / `EXTRA_IN_DESIGN` / `CONTRADICTION` / `TABLE_MISMATCH` / `TERM_INCONSISTENCY` / `AMBIGUOUS` / `UNTESTABLE`
- 該当しない側の行範囲は `[]`、quote は `""`

`trace.jsonl` の 1 行（`design_lines` が `[]` なら設計に反映なし）:

```json
{"pair": "P01", "req_key": "REQ-2", "req_lines": [3, 3], "design_lines": [[3, 3], [7, 9]]}
```

## 検査（--validate）

全組について次を確かめ、NG を一覧して exit 1 で終わる。

- 4 ファイルが揃っている／`pair` がディレクトリ名と一致する
- 行範囲がファイルの行数内／quote が指定行範囲に実在する
- `type` が 7 種のどれか／組の中で `id`・`req_key` が重複しない
- `MISSING_IN_DESIGN` の要件は trace で `design_lines` が空。逆に trace で反映なしの要件には `MISSING_IN_DESIGN` がある

## 照合規則

- 不整合（`--defects`）: 予測は同じ形式で、`pair`・`type`・行範囲だけ必須。同じ `pair`・同じ `type` で、
  正解に行範囲がある側（req / design）の少なくとも一方で 1 行以上重なれば一致。
  重なり行数の大きい組から 1 対 1 で貪欲に割り当てる（同点は出現順）。type 別と全体（マイクロ平均）を出す
- 追跡（`--trace`）: 予測は `{"pair","req_lines","design_lines"}`。リンク = (要件の行範囲, 設計の行範囲 1 つ)。
  要件側と設計側の両方が重なれば一致（1 対 1・貪欲）。別に「設計に反映なしの要件」（`design_lines` が空の行）を
  要件側の重なりで照合し、適合率・再現率を出す
- 評価セットに無い組の予測は採点から除外し、組 ID を表示する

## 実行例

```bash
venv/bin/python scripts/docverify_pair_eval.py --validate
venv/bin/python scripts/docverify_pair_eval.py --defects pred_defects.jsonl
venv/bin/python scripts/docverify_pair_eval.py --trace pred_trace.jsonl --json --out /tmp/trace_result.json
```

- 既定は日本語の表を標準出力。`--json` で機械可読の結果、`--out` で結果 JSON を保存
- `--dataset <DIR>` で評価セットの場所を変えられる。入力の形式不正は exit 2

## 限界

- AI が生成し、AI 1 名が注釈した合成データ。注釈者間一致（Cohen's kappa 等）は未測定
- 実文書での精度を示すものではない
- 照合は行範囲の重なりだけで判定する。指摘の説明文の正しさ・quote の一致は採点しない
- 行範囲が広い予測ほど一致しやすい。範囲の広さへの罰則は無い
