# 引き継ぎ: テスト活動支援（System 02）の継続実装

以下を新セッションの最初のプロンプトとして貼る。

---

テスト活動支援（System 02）の実装を継続する。まず次の 3 ファイルを読んでから着手すること:

1. `.claude/rules/speed-harness.md` — 作業規律（H-1 着手前3行 / H-4 サブエージェント複数並列必須 / H-7 pytest等はユーザー要求時のみ / H-8 進捗のステータスライン提示）
2. `docs/common-assets-docs-vs-testlab.md` — System 01 との共通資産 16 件と適用順序（P0/P1/P2）
3. `docs/test-activity-support-scope.md` — 機能スコープ・8 工程・要判断事項

## 現状（2026-08-22 時点・すべて main にマージ済み）

- 4 システム構成（システム選択 4 カード）と 10 画面の UI は完成（PR #171）
- 読み取り配線済み 3 画面: 分析（`static/js/ta-analysis.js`・report.json の遷移）/
  設計（`static/js/ta-design.js`・`/api/testcases/table`・実データ 68 件確認済み）/
  実行（`static/js/ta-execution.js`・`/api/history/runs`）
- 書き込み系はすべて未実装。各画面末尾に「未実装」と明記してある
- 検証用データは domain `hotel-example-site.takeyaqa.dev`（10 画面・ケース 68 件）

## 今回やること（P0: 既存 API の共用で足りる範囲。新規共有層は作らない）

1. **設計画面のケース編集**: 既存の `static/js/testcase-grid-edit.js`（System 01 のケース表編集・保存）の
   仕組みを流用し、`ta-design.js` のテーブルから編集→保存を通す。正本は `web/services/testcase_table_store.py`
2. **実行起動**: 実行画面の「実行」ボタン（現在 disabled）から既存の実行系
   （`web/services/playwright_executor.py` 系の既存 API。`web/routes/` で実在エンドポイントを確認してから）を叩く
3. **分析→設計のテスト条件引き継ぎ**: 分析画面で抽出した条件を設計画面の「テスト条件」枠へ渡す
   （まずは sessionStorage 経由の画面間受け渡しでよい）

禁止: AutoRun のステージ定義との混在・「実行結果」の意味の統合（`docs/common-assets-docs-vs-testlab.md` 第 3 節）。

## 進め方の指定

- サブエージェント複数並列（生成系と検証系を分離。検証系には「壊れている箇所を探せ」で指示）
- 実装前に対象 API を curl で 1 回実叩きして形状確認（S-1）
- サーバ起動・認証オフはハーネス H-2 のコマンドをコピー（探索しない）
- UI に見える変更を入れる場合は、実装前に HTML 案を出して承認を得る（メモリの規約）
- 完了後: 代表画面を Playwright で実確認 → コミットは `--no-verify` で add(パス明示)→commit→push→PR→マージまで
- pytest / make test / verify-ui / lint は私が要求しない限り実行しない（フックでもブロックされる）

## 途中で確認が要る判断（勝手に決めない）

- テストケース生成（AI 生成）の実装に入る場合: 使用 LLM は設定画面の既存 LLM 設定
  （OpenAI / Ollama）に従うこと。外部 LLM へソースコードを送る機能は、送信可否を私に確認してから
- GitHub 連携（トークン保存・PR 作成）に入る場合: 書き込み権限の扱いを私に確認してから
