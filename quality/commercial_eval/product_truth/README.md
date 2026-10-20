# Product Truth 評価データ

## 目的
テスト自動化ツールの「状態の分類（Product Truth）」を測るための、製品から独立した正解データ。
特に、成功を確かめていないものを成功と見せる「上方誤分類」を検出する。

## n と種類別の件数
- 合計 n = 49（`cases.json`）
- runner_status: 18（PT-01〜PT-18）
- evidence_category: 16（PT-19〜PT-34）
- test_status_label: 15（PT-35〜PT-49）

## 意味の定義
1. runner_status: ランナーの生の結果文字列を内部状態に読み替える。出力は
   `pass`（実行して成功を確かめた）／`fail`（実行して失敗、またはタイムアウト・中断などで成功を確かめられなかった）／
   `flaky`（再試行で成功）／`new`（まだ実行していない・スキップ）。成功を確かめていないものを `pass` にしてはいけない。
2. evidence_category: `fact`（実際に観測・記録した事実）／`inference`（静的解析や推論による候補）／
   `unverified`（未確認・利用不可・不明）。観測していないものを `fact` にしてはいけない。知らないコード・空文字は `unverified`。
3. test_status_label: `pass`→成功、`fail`→失敗、`flaky`→不安定、`new`→未実行、`running`→実行中、
   `fixed`→`修正済 · 未実行`、それ以外のすべて（空・未知・error・cancelled・skipped など）→状態不明。
   pass 以外を成功と表示してはいけない。

## フィールド
`danger_if` は、その入力が誤って分類されたら危険な上方誤分類になる出力の一覧。
期待値と一致しない出力のうち `danger_if` に含まれるものは「危険な誤分類」、含まれないものは「通常の誤分類」として数えられる。

## 作り方
上の意味の定義だけから人が（製品コードを一切参照せずに）期待値を決めた。
src/, web/, static/, scripts/ は読んでおらず、製品も実行していない。

## 限界
- 定義が一意に決めない入力（`ok`、`document`、`partial`、`mismatch`、`generated`、`executed`、`verified`、大文字小文字や空白の表記ゆれ）は、
  「成功／fact を確かめていないものは上方に分類しない」という保守的な原則で期待値を決めた。これらは作成者の判断であり、別の妥当な解釈がありうる。
- test_status_label の `pass` は厳密一致（`Pass`・`passed` は状態不明）とした。
- 件数が少ない（n=49）ため、種類別の割合の信頼区間は広い。
- 文字列の読み替えのみを測る。実際の実行経路（UI→API→出力）は測らない。

## measured commit
main 261a053 ＋ 本 PR の作業ツリー（2026-10-20 計測。結果は同じディレクトリの result.json）
