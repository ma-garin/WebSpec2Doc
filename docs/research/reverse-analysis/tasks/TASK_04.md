# Claude Code 実装指示

必読: CLAUDE.md、AGENTS.md、docs/design/specs/CONVENTIONS.md、docs/research/reverse-analysis/IMPLEMENTATION_PLAN.md。計画と最新利用者指示が過去の一般規約より優先。
Codexがオーケストレーター兼レビュー担当。あなたは指定Taskのみ実装する。必要な対象テストの作成・実行は利用者が明示承認済み。全体ゲートや無関係テストは行わない。
禁止: commit/push/PR/merge/pull/branch操作、依存・設定変更、install/update/setup、REA/Ghidra/JADX導入、GUI/System09/Android/Ghidra/Orchestration変更、無関係refactor、新規大規模調査、秘密情報/.env読取、他Task実装。既存dirty/untrackedファイルは他作業であり触らない。独自のエージェント委譲も行わない。
static candidateをobservedな仕様へ昇格しない。method/pathだけではmatched禁止。page_url originをAPI originにしない。
終了時は変更ファイル、実行テストコマンドと末尾結果、未検証事項、仕様外判断のみ短く報告。テスト出力は/tmp/webspec2doc-task-NN-tests.logへ保存する。失敗を放置せず対象内で修正。Task範囲外修正が必要なら停止報告する。

## Task 4: 価値検証・利用説明
変更可能: tests/fixtures/reverse_analysis/のcontrolled fixtures/測定記録、tests/test_reverse_analysis_cli.py、docs/guide/reverse-analysis.md。Task1～3実装src/qualityは変更不可。不具合を発見したらCodexへ修正内容を示す。
計画§10/§12 AC1～12で最終CLI JSONの実物を受入テストし、docs/guideにCLI、入力要件、status/exit、実測/静的構文/対応推論/unknown、provider未検証、既知制限を記載。Before固定snapshot（既存build_screen_api_map含む）→After同じsnapshot+fixture provider結果を計測。SHAと入力不変、候補の正解source位置照合、重複水増しなし、誤抽出/追加seconds/可能なpeak RSS/output bytesを記録。fake測定はfakeだと明示。実REAの価値ゲートAC10は未検証とする。
HTTP method未提供で実adapterからinferred対応が出ない/route未提供/module依存edgeは現sliceJSONで保持されていないことは正直に明記し、ダミーmethodやrouteをfixtureに足して成果を偽装しない。新Evidenceはstatic-only endpoint/module/source位置で何を増やしたか、未検証との境界を示す。
最終CLI受入テスト追加: 実プロセスCLIにSIGINTを送るケース（fakeproviderが開始合図後、子プロセスも含め終了、exit130、cancelledJSON/一時ファイルcleanup）、flagOFF既存report/snapshotのバイト/hash不変、古いmap/壊れたmap/欠測mapの区別を利用者出力まで確認。実行で不具合が見つかればsrcを勝手に直さず具体報告する。fakeprovider/一時dirは自己所有のみ停止/cleanup。
必要な対象テストは承認済み。reverse_analysis5ファイル+tests/test_apispec_recovery.pyを最終1回実行し/tmp/webspec2doc-task-04-tests.log保存。時間に依存する再現検証は必要性がある場合のみ反復。fixture/測定記録パスはtests/fixtures/reverse_analysis/value_measurement.jsonとVALUE_MEASUREMENT.mdを推奨。レポートを増やしすぎない。実provider実行/導入/new research/GUI/09/Android/Ghidra/指揮/commit/push禁止。
終了報告は変更files、テスト末尾、AC1～12のPass/Fail/未検証、BeforeAfter実数、残課題を短く示す。
