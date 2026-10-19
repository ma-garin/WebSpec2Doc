# IMPLEMENTATION PLAN — 最小reverse analysis

2026-10-19。承認済み [Phase 0](CURRENT_STATE.md) / [Phase 1](REA_GHIDRA_FIT_ANALYSIS.md) を前提とする。
状態: 計画のみ。実装・依存導入・設定変更・Claude Code起動は未実施。本書提出後に停止する。

## 1. 最小アーキテクチャ

### 実装前のAPI recovery結線確認（必要最小限）

- `src/apispec/recovery.py` の build_screen_api_map/build_openapi_draft は存在し、
  `tests/test_apispec_recovery.py` から呼ばれる。
- src/webのシンボル・import検索では定義以外の製品呼出を確認できない。
  `src/main.py::run/save_outputs/_save_json_output` にも呼出はない。
- `web/routes/api_v1.py` のreport endpointはreport.json、snapshots endpointは一覧を返す。
  `/openapi.json` はWebSpec2Doc自身のAPI仕様であり、対象サイトのAPI復元出力ではない。
- `web/routes/report.py` のpreview/downloadは既存ファイルの提示経路。
  API復元関数を呼び出して保存する経路があるとの根拠にはならない。
- `src/diff/snapshot.py::save_snapshot/load_snapshot` はPageData.api_callsを保存・復元する。
  一方report.jsonはAPI観測の十分な入力にならない。
- **追加確認**: `network_interceptor.py::_record` はresponse URLからpathだけを保存する。
  ApiEndpointはorigin/queryを持たない。page.urlのoriginをAPI接続先とみなしてはならない。

判断: 標準製品経路への結線は引き続き未確認。本sliceでは既存snapshotを入力にして
build_screen_api_mapを再利用し、reverse_analysis.jsonのruntime節へ実測を保存・CLIで提示する。
これは新しい明示CLI経路の結線であり、既存クロールのAPI recovery全体を修正したとは称さない。
OpenAPI draftの独立export・既存GUIへの接続は別の既存改善として保留する。

```text
local JS directory（local source mapを含めてよい）
  → REA CLI固定版 → 検証済み静的Evidence → 最小正規化
既存snapshot.json
  → 入力検証 → load_snapshot → build_screen_api_map → 観測の正規化
両入力 → 純粋な限定対応付け → 原子的JSON保存 → CLI要約・出力先
                                          reverse_analysis.json
```

対象JSの実行、新規クロール、source mapのHTTP取得はしない。
既存report.json/snapshotは読み取りのみ。REA標準reconcileは使わない。

## 2. 変更/追加ファイル候補

候補名はこの計画の実装契約。実装中に範囲追加が必要になれば計画へ戻す。

- 追加 `src/reverse_analysis/{__init__,models,runtime,rea_adapter,normalize,reconcile,reporter,service}.py`。
- 変更 `src/main.py`: 明示CLI引数と既存run分岐より前の独立実行分岐。
- 変更 `quality/feature_contracts.yml`: reverse_analysisの独立契約。
- 追加 `tests/test_reverse_analysis_{runtime,adapter,normalize,reconcile,cli}.py`。
- 追加 `tests/fixtures/reverse_analysis/`: 小さな自己所有JS/map/snapshot・最小REA応答fixture。
- 追加 `docs/guide/reverse-analysis.md`: CLI、制限、推論の読み方。

src/cli.py docは追加引数をsrc/main.pyへ転送する既存経路を利用し、変更しない。
requirements/package.json、Web route、GUI、System09 DB、Android/Ghidra、指揮は変更対象外。

## 3. データモデル

frozen dataclass・tuple、純粋関数、既存層方向に従う。出力schema_versionは1。

- Artifact: 相対path、SHA-256、size、producer/版。local絶対rootは出力せず入力labelで識別。
- StaticCandidate: id、kind(route/api/module/source)、artifact/source参照、source range、
  method/origin/path/expressionの取得可能値、resolution(exact/partial/unavailable)、
  epistemic_state(observed/inferred/unknown/unavailable)、authority、limitations。
- RuntimeObservation: id、snapshot SHA-256、JSON pointer、page_url、method、path、status_code、
  content_type、sample_fields、origin=null、query_scope=not_retained。
- Relation: static_ids、runtime_ids、classification(matched/inferred/ambiguous/unknown)、
  epistemic_state、basis、limitations。matchedでも関係のepistemic_stateはinferred。
- Coverage: static/runtime別のstatus、truncated、omitted_count（不明ならnull）、limitations。
- Diagnostic: code、severity、処理段階、利用者向けmessage、next_action。

候補がAST内に実在する事実と、そのAPIが実在/実行される推論を分ける。
SourceEvidenceへ詰め込まず、数値confidence=1.0への変換もしない。
IDは出典digest＋位置＋kindから決定的に作り、取得時刻とPIDを混ぜない。

## 4. REA adapter境界

- 絶対pathの利用者管理REA executableのみ。npx/install/setup/updateを実行しない。
- 初期受入版は公開版6.7.0。別版はunsupported_provider_versionとし自動fallbackしない。
- subprocessのargvで専用 `analyze-javascript-application` を呼び、`--json` を明示。
  generic analyzeはsingle JS/native等の別laneへ入り得るため使わない。
- 初回入力は実在するlocal directoryに限定。ASAR、単体ファイル、URLは受け付けない。
- adapterは実行・出力検証まで、normalizeはREA Evidenceからモデルへの純粋変換。
  upstream schemaそのものを既存WebSpec2Docの標準型にしない。
- 正規化で未知kindを発見したらunsupportedとして件数/位置を保持し、黙って捨てない。
- source mapはdirectory内の正規化path・digest・取得可否だけを信用する。
  symlink、traversal、外部rootを受入拒否。original sourceがなければunknown。
- 元Evidenceはraw_result/ソース本文を丸ごと永続化しない。採用した出典・位置・digest・
  provider・coverageを独立JSONに残す。source内容の出力は初回範囲外。
- REAのmodel上のcommitment/schema整合を検証できない入力はinvalid_provider_output。
  識別子形式だけの検査を暗号的真正性検証とは呼ばない。

## 5. runtime/static限定突合ルール

1. API候補だけをruntime APIへ比較する。route/module/sourceをAPIに混ぜない。
2. methodは明示値を大文字化する。欠損をGETと推定しない。
3. pathはpercent decode・末尾slash除去・動的parameter化・prefix補完をしない。
   静的URLのpath抽出は構文的に確定する場合だけ。query条件は保存されない旨を保持。
4. 完全一致のmethod/pathがあり、候補・観測が一意でも、既存snapshotのorigin欠測により
   **classification=inferred、basis=method_path_only、limitation=runtime_origin_not_recorded**。
   これはsource call-siteと観測の同一性証明ではない。
5. 一対多/多対一の対応可能性はambiguous。候補ID・観測IDを全て保持する。
   status違い等を勝手に一件へ潰して一意としない。
6. 動的式・template・method欠損・query条件付き候補はunknownとして自動対応を保留。
   静的に確定した別origin同士を同じ対象に潰さない。
7. staticのみはinferred（未観測候補）。runtimeのみはobserved記録を保ち、関連はunknown。
   「未観測」を「存在しない」「到達不能」と表示しない。
8. matchedは完全なmethod/origin/path等の識別根拠が揃う将来用の予約状態。
   **現行snapshotだけからmatchedを出さない**。利用者の設定originも実測根拠に昇格させない。
9. REA標準reconcileへのEvidence偽装はしない。script identity/因果/実行順の推論は範囲外。

## 6. reverse_analysis.json schema

トップレベルの必須キーを以下に固定。未知schema_versionは拒否する。

```text
schema_version: 1
status: complete | partial | unavailable | failed | cancelled
producer: {name, version, provider_version}
inputs: {static_root_label, static_artifact_sha256, runtime_snapshot_sha256}
artifacts: [Artifact]
static_candidates: [StaticCandidate]
runtime_observations: [RuntimeObservation]
relations: [Relation]
coverage: {static: Coverage, runtime: Coverage}
diagnostics: [Diagnostic]
summary: {static_candidates, observed_api_records, inferred_relations,
          ambiguous_relations, unknown_relations, matched_relations}
```

- kind別のsource_locationにはartifact相対path、line/columnまたはbyte range、位置の単位を保持。
  UTF-16位置とUTF-8 byte offsetを混ぜず、不明値はnullと理由。
- summaryのobserved_api_recordsは取得レコード数であり、全API数/呼出回数/網羅率ではない。
- collection空とcoverage unavailableを区別する。必須値欠損を空配列で偽装しない。
- status=completeは選択入力の処理完了であり、全システム網羅や確定仕様の意味ではない。
- 保存はtmp＋os.replace。実行失敗でも書込可能ならdiagnosticを残す。
  保存不能時はstderrに次の行動を示して終了し、成果物があるとは報告しない。
- 同じ入力・provider応答から同じJSONを生成。処理時間等は別の価値測定記録に保存する。

## 7. feature flag / opt-in

永続設定・環境変数は追加せず、CLIの明示モードのみ。

```text
python src/main.py --reverse-analysis
  --js-input <local-directory>
  --runtime-snapshot <snapshot.json>
  --rea-command <absolute-executable>
  --output <dedicated-output-directory>
```

上記は計画するCLI契約であり、現時点では未実装。
reverse-analysis指定時は3入力を必須にし、--url/--urls/--compare等のクロールモードとの併用は拒否。
専用出力ディレクトリへreverse_analysis.jsonのみを書き、入力rootやsnapshot配下への出力は拒否。
flagなしではREA探索・version probe・新規キー/成果物/挙動を一切追加しない。

## 8. エラー・timeout・provider不在

- adapterのversion probe上限5秒、解析全体上限120秒（いずれも製品側の初期policy）。
  REA側source deadlineと別に親が管理する。成功所要時間の見積値ではない。
- stdoutは最大32MiB、stderrは最大1MiB。逐次drainし、超過時は停止・明示エラー。
  先頭だけを切り取ったJSONを成功としてparseしない。
- cancellation/timeout/上限超過では所有するprocess groupを停止し、3秒猶予後kill、
  wait/reapと一時ファイルの所有cleanupを行う。無関係プロセスを停止しない。
- missing_provider/version mismatchはunavailable。壊れた入力/応答はfailed。
  producerがpartialを返した場合だけ、検証できた部分をpartialとして採用する。
  kill後の途切れたJSONを部分Evidenceとして扱わない。
- 初期exit契約: complete=0、partial/unavailable/failed=2、cancelled=130。
  REA終了0でもpartial/unknownを検査する。static_only候補があるだけでは処理失敗ではない。
- provider不在でもsnapshot由来の実測は保存可能。static=[]とunavailableを明示し成功扱いしない。
- stderr/raw stdoutはそのまま出力せず、秘密・絶対pathを除いたdiagnosticと次の行動を表示。
- providerにruntime由来originがない問題は障害ではなく、突合根拠の制限として常時表示。

## 9. テスト方針

新規ロジックと同一タスクで受入条件に直結するテストを作成。mirror-onlyな件数テストは作らない。

- L1: schema、出典/状態保持、candidate normalization、method/path/欠測/曖昧性、決定性。
- L2: tmp_pathの実snapshot/JS/map、既存API map関数、fake executableの
  version/JSON/stderr/timeout/cancel/上限/異常終了、最終JSONとCLI表示の実物。
- CLI統合: クロールせず完走、flag OFFで既存出力hashと挙動不変、入力ファイル不変。
- 偽REAは固定版の実Evidenceから選んだ最小fixtureを使い、都合のよい架空shapeを作らない。
- 実REAの価値実証は利用者が導入済みの環境で明示許可時のみ。未導入ならfake合格と
  実provider未検証を分け、実測成功・価値ゲート合格を宣言しない。
- pytest/quality_harness等の開発ゲートは利用者の要求時のみ実行。
  本Phaseではテストコード作成・テスト実行を行わない。

## 10. Before/After価値測定

同じ自己所有fixtureに既存runtimeで観測するAPIと、JSにしかないAPI/route候補、
module import、source map対応を置く。実行しない対象コードも根拠位置が追えるようにする。

- Before: 固定snapshotから既存観測・既存復元成果物を記録し、そのSHA-256を保存。
- After: 同じsnapshotにlocal静的解析を追加。新しい有用candidate/source/module Evidenceと
  inferred/ambiguous/unknownを数える。matched=0が現行snapshotの正しい期待値。
- 有用発見は人手の正解fixtureと位置照合し、既存にない探索対象/レビュー判断に使えるものを数える。
  重複DOM/API・誤抽出・単なるaliasの水増しは数えない。
- wall time/追加秒/測定可能なpeak RSS/output bytes/候補数/有用新規数/誤警告数を記録。
  既存API export改善の価値は新しいstatic Evidenceの価値と別計上。
- 有用新規Evidenceが1件未満なら価値ゲート不合格。mapなし・不適切対象はその理由を残す。

## 11. Claude Codeへ渡すタスク分割

最大4タスク、順次受入。新しい調査・依存追加・GUI変更・指定外refactorは禁止。
このPhaseではtaskファイル作成やClaude起動を行わない。

### Task 1: モデル・runtime入力・突合

- 対象: models.py/runtime.py/reconcile.py/__init__.py、runtime/reconcileテスト。
- 既存snapshotを検証してload_snapshot/build_screen_api_mapを再利用。
- §3/5/6を実装し、origin欠測・曖昧性・状態保持を純粋テストで固定する。
- 出口: 旧snapshotにoriginを捏造せず、method/path一致でもmatchedを出さない。

### Task 2: REA adapter・静的正規化

- 対象: rea_adapter.py/normalize.py、adapter/normalizeテスト、最小provider fixture。
- §4/8のprocess境界・固定版JSON・coverage/出典を実装する。
- 出口: fake providerで正常・部分・欠損・不正・timeout・cancel・上限を識別できる。

### Task 3: CLI・保存・契約

- 対象: service.py/reporter.py/src/main.py/feature_contracts.yml、CLIテスト。
- Task1/2を接続し、明示CLI→既存API map生成→reverse_analysis.json保存→CLI要約まで通す。
- 出口: 入力/report.json不変、flag OFF不変、エラー時も結果の状態が利用者に分かる。

### Task 4: 価値検証・利用説明

- 対象: controlled fixtures、最終CLI受入テスト、docs/guide/reverse-analysis.md、測定記録。
- §10/12で最終JSONの実物・出典・未検証をレビュー。要求された検証だけ実行する。
- 出口: fake/実providerの結果を分離し、新規Evidenceの価値と費用を報告する。
  実provider未検証なら価値ゲート保留として残し、完成扱いしない。

各タスクのdiffをCodexがscope/evidence/error/互換性の観点でレビューしてから次へ進む。
自動commit/pushや実装開始の承認をこの計画から推定しない。

## 12. Acceptance Criteria

1. Given flag OFF / When既存CLI実行 / Then REA未呼出・既存report/snapshot/hash不変。
2. Given local JS/mapと固定snapshot / When明示実行 / Then独立JSONが保存され、CLIに要約と出力先。
3. Given staticのみのAPI/route / Then根拠path/range/digest付き候補になり、observed仕様へ混入しない。
4. Given origin欠測snapshot / Whenmethod/path一致 / Theninferred＋欠測理由、matched=0。
5. Given複数候補・動的式・query依存 / Thenambiguous/unknownとなり、候補・理由を落とさない。
6. Given mapなし/古いmap/不正map / Then原ソースを捏造せず、unknown/partial/failedを区別。
7. Given provider不在/不一致/不正JSON/timeout/cancel/超過 / Then明示状態・次の行動・非成功exit、
   所有child終了と一時データcleanup。未観測/未解析を0件成功にしない。
8. Given既存API観測 / Thenfile digestとJSON pointerまで追跡でき、画面originをAPI originにしない。
9. Given同じ入力・provider結果 / ThenID・順序・JSONが同じ。入力と既存成果物を書き換えない。
10. Given controlled fixture / ThenQA上有用な新規Evidenceが1件以上、誤警告と追加費用も記録。
    実provider未実行ならこの価値実証は未検証と報告する。
11. Given承認済みslice / ThenGUI/09/Android/Ghidra/指揮への変更、install/setup/updateを含めない。
12. 出力を読んだ利用者が「実測」「静的構文の事実」「対応推論」「未確認」を区別できる。

本書で停止。実装指示書の発行・Claude Code起動・実装は次の利用者指示を待つ。
