# Claude Code 実装指示

必読: CLAUDE.md、AGENTS.md、docs/design/specs/CONVENTIONS.md、docs/research/reverse-analysis/IMPLEMENTATION_PLAN.md。計画と最新利用者指示が過去の一般規約より優先。
Codexがオーケストレーター兼レビュー担当。あなたは指定Taskのみ実装する。必要な対象テストの作成・実行は利用者が明示承認済み。全体ゲートや無関係テストは行わない。
禁止: commit/push/PR/merge/pull/branch操作、依存・設定変更、install/update/setup、REA/Ghidra/JADX導入、GUI/System09/Android/Ghidra/Orchestration変更、無関係refactor、新規大規模調査、秘密情報/.env読取、他Task実装。既存dirty/untrackedファイルは他作業であり触らない。独自のエージェント委譲も行わない。
static candidateをobservedな仕様へ昇格しない。method/pathだけではmatched禁止。page_url originをAPI originにしない。
終了時は変更ファイル、実行テストコマンドと末尾結果、未検証事項、仕様外判断のみ短く報告。テスト出力は/tmp/webspec2doc-task-NN-tests.logへ保存する。失敗を放置せず対象内で修正。Task範囲外修正が必要なら停止報告する。

## Task 2: REA adapter・静的正規化
変更可能: src/reverse_analysis/rea_adapter.py、normalize.py、tests/test_reverse_analysis_adapter.py、test_reverse_analysis_normalize.py、tests/fixtures/reverse_analysis/の最小provider fixtureのみ。Task 1モデルは読むだけ。
計画§4/8、§11 Task2、AC3/6/7/9/11/12。argv専用CLI固定6.7.0、local directoryのみ、version5s/解析120s、bounded stdout32MiB/stderr1MiB、所有processgroup停止・reap（3s後kill）・cancelを実装。JSON/schema/commitment検証、未知kindやpartial/coverage保持、source位置単位/digest/relativepath検証。symlink/traversal/root外拒否、source本文永続化禁止。map欠損/古い/不正を根拠なく成功やoriginalsourceにしない。provider stderr/raw stdoutは表示しない。
新規Web調査は禁止。既に一次情報を保存した/tmp/webspec2doc-rea/ と/tmp/webspec2doc-rea-release/内の該当CLI/Evidence/graph sourceを必要な箇所だけ参照する。既存調査REA_GHIDRA_FIT_ANALYSIS.mdに一次参照あり。fixtureは6.7.0の実際のEvidence構造に準拠し、その出所を記録。形を都合よく創作しない。provider実行/導入禁止、fake executableだけでテスト。
Task1公開モデルはsrc/reverse_analysis/models.pyを参照。アダプタ/normalizerの結果型も自分の許可ファイル内で定義。Task3のserviceが使う入口を終了要約に示す。テスト実行: venv/bin/python -m pytest tests/test_reverse_analysis_adapter.py tests/test_reverse_analysis_normalize.py -q（ログ/tmp/webspec2doc-task-02-tests.log）。

## Codex追加指示: 限定一次ソースの参照
保存済資料の不足を報告したため、実装に不可欠な6.7.0固定タグのsrc/domain/javascript/javascriptApplicationGraph.ts、javascriptApplicationAnalysis.tsとCLI version実装、正規化/Evidence定数の直接依存だけは公式repositoryから/tmpへ取得して参照してよい。Phase1文書にある公式URLを使い、rea-agents-6.7.0へ固定。これは実装契約の確認であり新規大規模調査ではない。install/実provider起動は禁止。指定Task2を最後まで実装して対象テストを実行する。架空shapeで埋めない。これ以外へ調査を拡大しない。

## Codexレビュー修正1
1. `validate_input_directory`がroot自体のlstatしか確認せず、内部symlinkをprovider起動前に拒否していない。入力rootの親成分と内部symlink/特殊fileを起動前検証し、外部を読ませない。verify_fileのopen/read OSErrorもsanitized failed診断にし、例外で落とさない。テスト追加。
2. normalize_staticのcandidates.setdefault(id, candidate)は同位置/kindでも異なるendpoint値や観測を黙って捨てる。衝突する候補は意味と出典で区別して全件保持し、同じmethod/pathが複数あるとき曖昧性が失われないようにする（モデルは変更せずmake_id併用可）。回帰テスト。
3. 固定タグのCLI dispatch/formatter/versionの直接実装を限定参照し、実際のargv・JSONの外枠・version出力とadapterの整合を確定する。実行による検証でないことは明記するが、一次ソースで確定できるものを未確認のまま放置しない。必要ならadapterとfixture修正。semantic_graphは上流schema完全shapeに合わせ、自己実装だけで計算したIDについて可能な既存一次テストvectorで照合する。新規調査拡大/実provider起動/導入禁止。
HTTP method欠測/route未提供は捏造せず制限として保持し、Task3へ引継ぐ。変更対象はTask2内のみ。対象49件と追加テストを実行する。
