# Claude Code 実装指示

必読: CLAUDE.md、AGENTS.md、docs/design/specs/CONVENTIONS.md、docs/research/reverse-analysis/IMPLEMENTATION_PLAN.md。計画と最新利用者指示が過去の一般規約より優先。
Codexがオーケストレーター兼レビュー担当。あなたは指定Taskのみ実装する。必要な対象テストの作成・実行は利用者が明示承認済み。全体ゲートや無関係テストは行わない。
禁止: commit/push/PR/merge/pull/branch操作、依存・設定変更、install/update/setup、REA/Ghidra/JADX導入、GUI/System09/Android/Ghidra/Orchestration変更、無関係refactor、新規大規模調査、秘密情報/.env読取、他Task実装。既存dirty/untrackedファイルは他作業であり触らない。独自のエージェント委譲も行わない。
static candidateをobservedな仕様へ昇格しない。method/pathだけではmatched禁止。page_url originをAPI originにしない。
終了時は変更ファイル、実行テストコマンドと末尾結果、未検証事項、仕様外判断のみ短く報告。テスト出力は/tmp/webspec2doc-task-NN-tests.logへ保存する。失敗を放置せず対象内で修正。Task範囲外修正が必要なら停止報告する。

## Task 3: CLI・保存・契約
変更可能: src/reverse_analysis/service.py、reporter.py、src/main.py、quality/feature_contracts.yml、tests/test_reverse_analysis_cli.pyのみ。Task1/2ファイルは参照のみ。
計画§1/6/7/8/11のTask3と§12 AC1/2/7/8/9/11/12を実装する。CLI明示--reverse-analysis、--js-input、--runtime-snapshot、--rea-commandを追加し3入力必須。--url/--urls/--compare等既存モードと併用拒否。通常クロール分岐より前で独立実行。--output専用dirにreverse_analysis.jsonだけをtmp+os.replaceで保存。入力root内/snapshot親内やsymlink出力を拒否。既存report/snapshot変更禁止、flagOFFでprovider probe/import副作用禁止。
load_runtime_observations→run_static_analysis→normalize_static→reconcile→summarizeを結線。adapter無いときruntimeは残しstatic unavailable、非成功exit。既定policy版probe5s解析120s、partial/unavailable/failed=2、cancelled=130、complete0。KeyboardInterrupt/cancellationもCLIから取り扱い、write不能はsanitized次の行動付きstderrで成果物ありと称さない。最終JSONのトップキーは計画§6、各dataclassはモデル再利用。coverageと欠測理由を表示。unknown schema_version拒否をreporterで検証。deterministic output、時刻/PID/絶対root/生stderr/source本文なし。unsupportedノードは件数だけでなくkind/node_id/provider JSON pointerをdiagnosticなど許容schema内で保持する。
Task2入口: run_static_analysis(rea_command,input_dir,cancel_event=None)→AdapterResult、normalize_static(result)→StaticNormalization(status/provider_version/root_artifact_sha256/artifacts/candidates/coverage/unsupported/diagnostics)。
重要な既知制限: REA6.7 endpointはHTTP method未提供→method=Noneのまま、現実adapterからのAPI突合はunknown。route nodeも未提供→route捏造禁止。これをJSONの制限とCLI表示に明示し、対応できたと称さない。candidate observedは静的構文の存在だけであり、APIが実行された仕様に昇格させない。
fake provider fixtureはTask2の完全schema fixtureを読む。互換テストは既存pipelineを無駄に走らせず、flagOFFで既存入口/保存に新挙動が無いことを意味のあるテストで確認。必要に応じて既存API recovery/snapshotテストも実行してよい。テストコマンドと結果を/tmp/webspec2doc-task-03-tests.logへ保存。最終CLI JSON/表示/失敗保存/保存不能/入力不変/決定性の実物検査を含める。
Task4は未着手。新規調査/依存追加/実provider実行/commit/pushは禁止。

## Codexレビュー修正
prepare_output_dirはoutput自身/targetだけのsymlink検査で、親成分のsymlinkを通る出力を拒否していない。既存親成分もlstatで検査し拒否する。またresolve/exists/is_dir/iterdirがOSError/リンクloop等で例外になる場合をsanitized _write_failed/_output_rejectedへ変換する。作成前の権限不正やiterdir例外でもCLI tracebackが出ない回帰テストを追加。src/main.pyはエラー/要約の表示対象に生の絶対pathを混ぜない（出力先はユーザーが指定したlabelで可）。対象Task3範囲以外は変更しない。対象CLIとreverse_analysis一式+API recoveryのテストを再実行する。
