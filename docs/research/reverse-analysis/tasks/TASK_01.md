# Claude Code 実装指示

必読: CLAUDE.md、AGENTS.md、docs/design/specs/CONVENTIONS.md、docs/research/reverse-analysis/IMPLEMENTATION_PLAN.md。計画と最新利用者指示が過去の一般規約より優先。
Codexがオーケストレーター兼レビュー担当。あなたは指定Taskのみ実装する。必要な対象テストの作成・実行は利用者が明示承認済み。全体ゲートや無関係テストは行わない。
禁止: commit/push/PR/merge/pull/branch操作、依存・設定変更、install/update/setup、REA/Ghidra/JADX導入、GUI/System09/Android/Ghidra/Orchestration変更、無関係refactor、新規大規模調査、秘密情報/.env読取、他Task実装。既存dirty/untrackedファイルは他作業であり触らない。独自のエージェント委譲も行わない。
static candidateをobservedな仕様へ昇格しない。method/pathだけではmatched禁止。page_url originをAPI originにしない。
終了時は変更ファイル、実行テストコマンドと末尾結果、未検証事項、仕様外判断のみ短く報告。テスト出力は/tmp/webspec2doc-task-NN-tests.logへ保存する。失敗を放置せず対象内で修正。Task範囲外修正が必要なら停止報告する。

## Task 1: モデル・runtime入力・突合
変更可能: src/reverse_analysis/{__init__,models,runtime,reconcile}.py、tests/test_reverse_analysis_{runtime,reconcile}.pyのみ。必要な既存呼出元/依存は最小限読む。
計画§3/5/6、§11 Task 1、§12 AC 3/4/5/8/9/12を実装する。frozen dataclass/tuple、決定的ID。snapshot入力を厳密検証しload_snapshot/build_screen_api_mapを再利用し、snapshot digestと実在JSON pointerへ追跡できるruntime記録。欠測origin=null、query_scope=not_retained。候補のAPIの推論状態を保持。method/path唯一一致inferred、複数ambiguous、動的/query/method欠損unknown。現行snapshotはmatched=0。
テスト: venv/bin/python -m pytest tests/test_reverse_analysis_runtime.py tests/test_reverse_analysis_reconcile.py -q を実行。対象以外変更禁止。Task 2で使用するモデル公開インターフェースを要約する。

## Codexレビュー修正1
load_runtime_observationsでload_snapshot・build_screen_api_map・2回目read_bytesの例外が未処理。最初の最低限schema検証を通ってもPageDataの他の属性（例 elements=null）が既存ローダーで失敗し得る。入力変化/削除/既存loaderの構造不正をsanitized failed Diagnosticにし、tracebackや絶対pathを出さない。再読込失敗とnested不正の回帰テストを追加し対象テスト再実行。他モデル/Task範囲変更はしない。
