# /retro — レトロと学びの蓄積

引数: $ARGUMENTS（プロジェクト名 or 空＝横断レトロ）

## 実行内容

retroスキルに従い振り返りを行う。

1. 対象セッション/プロジェクトの作業を Keep / Problem / Try で整理
2. CURRENT_STATE.md・直近のコミット・evalスコア推移があれば参照して材料にする
3. lessons.md への追記内容を生成（templates/lessons.md形式、3-5行）
4. キット反映候補を提示:
   - 発火しなかったスキル → description追加案
   - 繰り返した手作業 → コマンド化案
   - 繰り返したミス → hook / done-gate項目追加案

引数が空なら直近の作業を対象にする。
