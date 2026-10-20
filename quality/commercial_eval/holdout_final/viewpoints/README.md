# テスト観点生成 最終判定用 holdout

最終判定用の holdout。**改善に使っていない**。製品の出力を採点するだけで、結果を見て製品を直し、このデータを直す、という使い方はしない。

## 目的
製品が画面から生成する「テスト観点」が、QA の専門家が必要とする観点をどれだけ網羅しているかを測る独立した正解データ。開発セット (`quality/commercial_eval/viewpoints/`) と画面を重ねていない。

## 独立性
- 製品コード (src/, web/, static/, scripts/) は参照していない (読んでも grep してもいない)。製品も実行していない。git・pytest も使っていない。
- 開発セットから借りたのは形式 (README の構成と expected.json のキー) だけ。

## 構成
- `site/` : 静的サイト (`index.html` と `w01.html`〜`w16.html`)。外部 CDN なし。各画面に「画面の説明」(仕様文)と、HTML 属性つきの画面部品がある。
- `expected.json` : `categories` (10 個) と、画面ごとの `required_viewpoints` (カテゴリ ID)・`notes` (根拠)。
- `build_holdout.py` : site/・expected.json・README を再生成する。

## 画面数
n = 16 (必須観点の延べ数 58、1 画面あたり 0〜8 個)

| 内訳 | 画面 |
|---|---|
| 観点が 1〜2 個の単純な画面 | w01, w02, w06, w12 |
| 5 個以上の複雑な画面 | w03, w05, w10, w11, w14, w15, w16 |
| API で保存する画面 | w04 (PUT), w10 (POST) |
| エラー表示と再試行の説明がある画面 | w05, w14 |
| 権限で表示が変わる画面 | w06, w11, w14 |
| 状態遷移の説明がある画面 | w07, w14, w16 |
| どの観点にも当たらない説明だけの画面 (hard negative) | w08, w09 (required_viewpoints = []) |

## カテゴリ別の件数
| ID | 名称 | 出現画面数 |
|---|---|---|
| `normal` | 正常 | 14 |
| `abnormal` | 異常値の入力 | 3 |
| `boundary` | 境界値 | 5 |
| `required` | 必須 | 7 |
| `format` | 形式 | 3 |
| `state_transition` | 状態遷移 | 3 |
| `permission` | 権限 | 3 |
| `error` | エラーの表示と回復 | 9 |
| `api` | API 連携 | 8 |
| `persistence` | 保存と再表示 | 3 |

## 正解の作り方
- 画面上の説明文と HTML 属性から、QA の観点で人が決めた。`required_viewpoints` は、その画面に必ず要る観点だけ。説明文に書かれていない観点は付けていない。
- 説明文が無い観点を HTML 属性だけから足すことはしていない (例: w01 の form に入力形式の記述が無いので `format` は付けない)。
- hard negative は、観点が空であることが正解。観点を出しすぎた場合は過剰生成として数える。

## 限界
- 作成者は 1 名で、裁定(第三者による合意)は行っていない。
- 画面からカテゴリへの対応づけ自体が主観を含む。特に `abnormal` と `error`、`boundary` と `format` の境目は人によって分かれうる(w15 の「下限が上限より大きい」は abnormal と error の両方にした)。
- 表現の違いは評価側でカテゴリ ID に寄せる前提で、ここでは ID のみを使う。
- 画面数が 16 と少ない。1 画面の判断が全体の数 % に響く。日本語のみ。

## measured commit
main 48c97cb に Commercial Accuracy Finalization の変更を載せた作業ツリーで、2026-10-20 に 1 回だけ測定した（改善はすべて開発セットで行い、このセットの結果を見た後に製品は変更していない）。結果は `result.json`。
