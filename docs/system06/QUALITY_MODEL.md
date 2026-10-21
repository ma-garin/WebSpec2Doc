# System06 品質モデル

対象: `quality.py`・`testability.py`・`readiness.py`・`decisions.py`・`pipeline.py`。
原則: 指摘 0 件を 100 点にしない。評価できない範囲は点数にせず「評価不能」（value=None）。

## 次元（10 ＋ Overall）

Clarity・Completeness・Consistency・Atomicity・Testability・Traceability・Measurability・ExceptionCompleteness・BoundaryCompleteness・StateCompleteness。画面の表示は 6 つ（総合・明確さ・網羅性・一貫性・テスト可能性・追跡可能性）。

| 次元 | 固有判定（要件 1 件） |
|---|---|
| Testability | testability の判定: CAN_TEST=100、PARTIALLY=50、NOT_TESTABLE=0 |
| Measurability | 数値＋単位があれば 100。曖昧語のみで数値なしなら 0。どちらも無ければ評価しない |
| Atomicity | 接続語（かつ・および等）が 2 個以上で未分割なら 0、他は 100 |
| ExceptionCompleteness | functional のみ。例外項目か失敗語があれば 100、無ければ 0 |
| BoundaryCompleteness | 数量語がある要件のみ。境界値を決める数値が無ければ 0 |
| StateCompleteness | 状態語がある要件のみ。state 項目があれば 100、語だけなら 50 |
| Completeness | テンプレのトリガー語がある要件のみ。不足候補数の割合で減点 |
| Consistency / Traceability | pipeline の後段で算出（下記） |
| Clarity | 固有判定なし |

## スコアの出し方

1. 次元ごとに、要件ごとの値を作る（固有判定と、紐づく指摘の減点の小さい方）。
2. 指摘の減点: critical 40・high 25・medium 12・low 5・info 0（要件ごとの合計を 100 から引く）。NOT_EVALUATED の結果は数えない。
3. 値を出せた要件が全体の 50% 未満なら value=None（`MIN_COVERAGE=0.5`）。
4. 次元の値は要件値の平均。coverage は値を出せた要件の割合。
5. Overall は重み付き平均。重みは Testability 3・Consistency 3・Completeness 1.5・Clarity 1.5・他 1。評価できた次元の重みが全体の 50% 未満なら None。
6. 各 Score は included（評価に含めた要件）・not_evaluated（除外した要件）・explanation（減点上位 3）を持つ。画面の「根拠を見る」で表示する。

### 実装上の事実（default pack との関係）

- 次元への指摘の紐づけは rule_id に TESTAB・AMBIG・COMPLET 等の語を含むかで決まる。default pack の 12 本（AMB-001 等）はどれも該当せず、**pack の指摘は次元スコアを減点しない**（実測で `_dim_of` が全件 None）。
- そのため Clarity は常に評価不能。Overall も、主要次元が欠けると None になりやすい。
- pack の指摘は準備状態ゲート（high 指摘の数）には効く。

### Consistency と Traceability（pipeline の後段）

- Consistency: 文書が 2 本以上で conflicts 段が成功したときだけ。100 − 20 × 未解決の矛盾（status が未設定または UNRESOLVED）。文書 1 本は評価不能で、理由は「文書間の比較をしていない」。
- Traceability: 2 本以上のときだけ。詳細は [TRACEABILITY.md](TRACEABILITY.md)。

## テスト可能性（testability）

- 判定語: CAN_TEST / PARTIALLY_TESTABLE / NOT_TESTABLE / UNKNOWN（原文が空）。
- 見る 5 点: 成功条件・失敗時の挙動・閾値と単位・測定条件・対象データ量。不足は `missing` に出る。
- 曖昧語（高速・適切等 70 語超）があり閾値が無い、または成功条件・閾値・条件が全て無い → NOT_TESTABLE。成功条件と閾値があり曖昧語が無く、失敗か条件がある → CAN_TEST。他は PARTIALLY。
- NOT_TESTABLE と PARTIALLY には書き換え提案が付く。「提案（未承認・原文は変更しない）」で、原文に無い値は作らない（`rewrite.py`）。

## 準備状態ゲート（readiness.gate）

状態は BLOCKED / DRAFT / REVIEWABLE / CONDITIONALLY_READY / READY。reasons に根拠数値を入れる。AI は承認しない。

| 順 | 条件 | 結果 |
|---|---|---|
| 1 | 未解決の critical 矛盾・必須節欠落・critical かつ NOT_TESTABLE・承認未完 | BLOCKED |
| 2 | スコアが無い、または評価できた次元が 0 | DRAFT |
| 3 | 主要 4 次元（Testability・Consistency・Completeness・Clarity）に評価不能がある | REVIEWABLE |
| 4 | high 指摘あり、未解決の high 以上の矛盾あり、trace coverage 未評価または 0.8 未満 | CONDITIONALLY_READY |
| 5 | Overall が 70 未満、または主要次元に 60 未満 | REVIEWABLE |
| 6 | 上記に当たらない | READY |

- 失敗した分析段階が 1 つでもあれば READY にしない（DRAFT に落とす）。
- 実装上の事実: 主要 4 次元のうち Clarity が常に評価不能のため、default pack では順 3 で止まり READY に到達しない。単一文書では trace coverage も未評価。
- 必須節・承認・テスト可能性の方針などは `policy` 引数で渡す口があるが、`analyze` API は渡さない（既定値のまま）。

## decisions の適用

- 対象は人の decision だけ。同じ target は最後の記録が勝つ。
- Finding: accepted→ACCEPTED、rejected→REJECTED、resolved→RESOLVED、waived→WAIVED。
- waived は期限切れまたは期限が読めないと無効。指摘は CANDIDATE に戻り再浮上する。
- Conflict: conflict_decided→DECIDED、rejected→REJECTED、resolved→RESOLVED。truth は UNKNOWN のまま（人の決定は記録であって事実の証明ではない）。
- ゲートは RESOLVED・DECIDED・REJECTED・WAIVED・CONFIRMED_RESOLVED を処理済みとして high 指摘・矛盾から除く。ACCEPTED は除かない。
- 判断を記録すると、保存済み原文から全分析をやり直してスコア・準備状態に反映する。

関連: [RULE_ENGINE.md](RULE_ENGINE.md) / [DOMAIN_MODEL.md](DOMAIN_MODEL.md) / [README.md](README.md)
