# 作業状態（System 06 ドキュメント検証）2026-10-18

## 運用ルール（保守者指示・絶対遵守。memory にも保存済み）
- 最大効率・高速が最優先。サブエージェントを駆使して並列化。複数ファイルの実装も 1 本にまとめず、本線が先に DOM id・クラス名・関数名の対応表を書き、ファイルごとに並列委譲
- コーディング（実装・案 HTML）は Sonnet 5.5（Agent に model: sonnet）。本線（Opus）は分解・判断・結合・検証・報告だけ
- 返答はシンプル。途中経過を書かない。トークン節約（スクショ最小・同じ情報を二度取らない・方針確定前にエージェントを起動しない）
- UI はコード前に HTML 案で承認（案は static/mock/system06/sidebar/index.html を上書き。ファイルを増やさない）。案は商用ツール品質で 3〜10 案、タブ切替で 1 枚に
- サイドメニューは必須・固定。状況で中身を変えない
- PC 専用。商用ツールとして既存（ConTrack・Jama 等）を超える
- 検証観点画面は別セッション担当（触らない）。8766 が自分の検証サーバ

## 決定済み
- サイドは固定 5 項目（ドキュメント検証・トレーサビリティ・履歴・検証観点・設定）＋各 1 行説明。各項目内は上部タブ。PR #268 マージ済み
- サイドは静的メニュー。進行・状態・役割で中身を変えない（絶対）
- 競合・論文調査: docs/research/RESEARCH-traceability-competitors.md（PR #270）
- トレーサビリティ画面: 見本 static/mock/system06/sidebar/index.html の案 4 上段（文書の流れ図）＋案 3（直すべきことの一覧）。各行に根拠と確信度
- 検証観点画面は別セッションが担当（触らない）

## 進行中
- トレーサビリティ画面の実装（仕様: work/trace-spec.md、Sonnet 委譲）
  - /clear 後に再開する場合: `git diff --stat templates/docverify/_r3.html static/js/docverify-r3.js static/css/docverify-r3.css` で変更を確認 → 8766 再起動 → #setcheck を撮影 → check_clipping 0 件 → パス明示で commit → worktree で PR・マージ

## 未対応
- トレーサビリティをレビュー単位でなくプロジェクト単位にする（API 変更が要る）
- 監査ログ・判定の記録を「履歴」に集約
