# System 06 ドキュメント検証 — 引き継ぎ（2026-10-18 19:02）

## 守るルール（このセッションで保守者が決めたもの。最優先から順に）
1. **最大効率・高速**: 独立した単位は同時に起動する（上限 30 本・次セッションから有効）。待ち時間に統合・検証を重ねる。見積を超えた担当は止めて「未反映」で進む
2. **トークン節約**: 担当の完了ごとに返答しない（中間報告は節目だけ 1 行）。担当は本数を絞り model: sonnet。報告は結論 3 行・表 1 個まで。長くなったら /clear を勧める
3. **進捗報告は 3 項目**: `見積: N分 / 実測: M分 / 完了見込み: HH:MM`。応答の最後の行も同じ 3 項目
4. **回答は短く**: 結論 1〜3 行。見出し・箇条書きの列挙は求められたときだけ
5. **共有 API**: arXiv・Semantic Scholar を叩く担当は 2〜3 本まで（20 本同時で 429 になった）
6. **評価の公正さ**: 規則を作るときに見た組で精度を語らない。pair_v2 は未見の評価用。中身を見たら pair_v3 を作って測り直す
7. **UI は実装前に HTML 案で承認**。Ollama は使わない（PC が重くなる）。LLM を使う場合は OpenAI（要判断）
8. **共有ツリー**: 他セッションが同時に作業している。`git status` の自分以外の変更は触らない。コミットは worktree で（`git worktree add <scratchpad>/wt -b <名前> origin/main`）。`git checkout --`・`reset`・`stash` 禁止。サーバは 8766 以降（8765 は共有）
9. **ブラウザを個別に起動しない**: 画面の確認は Chrome 拡張の既存タブを使い回す（Playwright などで別のブラウザを立ち上げない）。サーバは必ず `FLASK_TESTING=1` を付けて起動する（付けないとタブが増える）。`#` 以降だけ違う URL は再読み込みされないので `?reload=1` を付ける
10. **ゲート**: pytest / make test / lint は要求時のみ。未実行は「未実行」と書く。テストで確かめていない数値は「未確認」と添える

## このセッションで分かった事実
- 画面（templates/docverify/_global.html・_r3.html・_r4.html）は別セッションが改修中（左ナビの再構成・検証観点のタブ）。触る前にそのセッションと分担を決める
- docverify のコード地図: `.claude/rules/docverify-map.md`（自動で読み込まれる）。詳細 `docs/design/docverify/codemap.md`

## 完了（main にマージ済み）
- コード地図 `.claude/rules/docverify-map.md`（docverify のファイルを触ると自動で読み込まれる）
- 競合・先行研究 `docs/research/docverify/F_winning_strategy.md`、トレーサビリティ `G_traceability.md`
- 対検査の評価セット `quality/docverify_eval/pair_v1`（11 組）・`pair_v2`（5 組・未見の評価用）
- 対検査エンジン `web/services/docverify/pair/`、予測 `scripts/docverify_pair_predict.py`、採点 `scripts/docverify_pair_eval.py`

## 精度（pair_v2 = どの担当も開発に使っていない 5 組）
| 区分 | 適合率 | 再現率 |
|---|---|---|
| 全体 | 0.77 | 0.60 |
| 追跡リンク | 0.89 | 0.68 |
| 用語ゆれ | 0.0 | 0.0 |
| 余分な設計 | 0.0 | 0.0 |
- pair_v1 は開発中に全組を見たため、汎化の根拠にしない
- 用語ゆれ・余分な設計は文字 n-gram の規則では汎化しない（言い換え・語の重なり）。意味の比較（埋め込みか LLM）が要る → 要判断: LLM（OpenAI）を検出の二段目に使うか。Ollama は使わない

## 次の一手
1. 検証観点の画面: 案 `docs/design/docverify/checklists-v1.html` の承認待ち（4 方向: 対検査の観点・V 字の対・編集・自社基準の取り込み）。承認後に実装
2. 用語ゆれ・余分な設計: 上の要判断を受けて方式を決める。評価は pair_v2 で行い、pair_v2 の中身を見て規則を作らない（見たら pair_v3 を作る）
3. エンジンを画面（R3 集合検査）へ結線（未実施）

## 未実行
- pytest・lint・画面の結線確認
- 共有ツリーの他セッション: 8765 共有、自分の検証は 8766 以降
