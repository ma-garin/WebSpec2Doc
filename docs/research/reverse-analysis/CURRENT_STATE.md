# CURRENT STATE ANALYSIS — WebSpec2Doc

調査日: 2026-10-19（Asia/Tokyo）。対象: ローカル main、HEAD `c0da96a`。
範囲: HANDOFF_REA_GHIDRA.md §22–23、System 01〜09・01 app・指揮。
判定: **Phase 0 の静的な現行理解を整理済み。実行確認は未実行。Phase 1 へ進まない。**
本書以外のコード・依存・設定は変更していない。調査で見つけた問題も修正していない。

## 1. 調査方法と根拠の限界

- 引き継ぎ書は先頭から末尾（1〜1875行）まで読了。
- CLAUDE.md、AGENTS.md、CONTEXT.md を確認。CONVENTIONS.md の実在位置は
  [docs/design/specs/CONVENTIONS.md](../../design/specs/CONVENTIONS.md)。ルート直下にはなかった。
- README、DEVELOPMENT、feature_contracts、functional-integrity、CODEX_GUIDE、
  docs/README、docs/sdlc/README、関連する現行ルート・service・src を照合した。
- システム番号は [選択画面](../../../templates/system-select.html) のカードと
  [Blueprint登録](../../../web/__init__.py) を照合。README に残る「03 CLI」は現行番号と異なる。
- 「接続あり」はソース上の呼び出し・ファイル受け渡しを確認した意味。
  UI操作・実クロール・実DB接続・外部リポジトリ修正の成功を意味しない。
- 機能不在候補は `rg` のファイル名・シンボル検索に加え、Python の Path.rglob による
  src/web の Python 本文走査でも再確認した。検索語がないことだけで一般的な不在は断定しない。
- zsh の未一致glob、誤ったパス、出力打ち切りは機能の不在根拠にしない。
  実在パスを列挙して再検索・範囲読みした。例: API recovery は `src/apispec/recovery.py`、
  テストは `tests/test_apispec_recovery.py`、impact API は `web/routes/impact_api.py`。
- 共有ツリーには既存の未コミット・未追跡変更がある。触らず、退避・コミットもしない。
  リモートmainとの一致は未確認。ローカルコードの分析である。
- REA/Ghidra の最新仕様・実機能の調査は Phase 1 のため未実施。
  以下の重複候補は引き継ぎ書に列挙された用途と現行能力の比較であり、導入判断ではない。

## 2. 全体理解

WebSpec2Doc は、稼働Webの実測を仕様・QA資産へ変換する中核に、文書検査、
バッチ設計・実行、影響度分析、修正支援を加えたQAプラットフォームである。
全Systemが単一パイプラインで自動連結されているわけではない。

依存の基本方向は web/routes → web/services → src の入力・解析・出力層。
ただし全機能をsrcが提供する構造ではなく、06〜09などはweb/servicesに処理本体を持つ。
既存コメント・契約の implemented 表記より、入口から出力までの実際の結線を優先する。

## 3. System一覧

各Systemの詳細に入力・ルート・service・src・データ・成果物・Evidence・外部依存・
実装状態・モック・他System接続・評価候補を記す。表は入口一覧に限定する。

| System | 目的 | UI入口 |
|---|---|---|
| 01 | Web仕様復元 | /dashboard |
| 01 app | アプリ仕様デモ | /doc-app |
| 02 | テスト自動化 | /test-automation |
| 03 | 一連の工程実行 | /auto-run |
| 04 | CLI・API利用 | /cli |
| 05 | 修正支援 | /healing |
| 06 | 文書検査 | /docverify |
| 07 | スクリプトQA | /batch-test |
| 08 | バックエンドQA | /backend-test |
| 09 | 変更影響分析 | /impact |
| 指揮 | 工程の連結 | /orchestration |

### 01: ドキュメント作成

- 入力: URL、選択URL、クロール条件、対象サイトの認証状態、参考文書。
- 入口: [discover.py](../../../web/routes/discover.py) `/api/discover-stream`、
  [crawl.py](../../../web/routes/crawl.py) `/run`、CLI `src/main.py`。
- 処理: [page_crawler.py](../../../src/crawler/page_crawler.py) の crawl_site/crawl_urls →
  PageData → [html_analyzer.py](../../../src/analyzer/html_analyzer.py) analyze_pages →
  [transition_graph.py](../../../src/graph/transition_graph.py) build_graph → generator。
- データ・成果物: outputのサイト単位に report.json/html、screens/forms.md、spec.xlsx、
  transition.mmd、architecture.mmd、スクリーンショット、snapshots、差分。形式指定で出力が変わる。
- Evidence: DOM属性・selector・bbox・画像・API応答・状態遷移・文書出典。
- 依存: Playwright/Chromium、NetworkX、形式別出力ライブラリ。接続コードあり、今回の実行は未確認。
- 接続: 02/03はreport.jsonを利用。参考文書突合・操作記録は別入力経路。
- 評価候補: 観測に現れないソース上のroute/API/module候補。導入可否は未判定。

### 01 app: ドキュメント作成(app)

- 入力UI: APK/.app向けの入口。ただし実際の分岐キーは `https://app.<package>` の擬似URL。
- [pages.py::doc_app](../../../web/routes/pages.py)、discover/crawlのapp_mock分岐 →
  [app_mock.py](../../../web/services/app_mock.py) discover_sse/run_stream → fixtureコピー。
- `demo/sample_report_app` の6画面・スクリーンショット・成果物を使用する。
  インストール・エミュレータ起動を示すログは固定デモの進行表示であり実処理の証拠ではない。
- 実行時に選択画面を絞る一方、最後のcopytreeはfixture一式をコピーする。
  選択条件が最終reportへ反映されるかは未確認。
- 実機探索・APK解析・Manifest/Activity抽出をこの経路では行わない。
  app_mockのuiautomator2/WebDriverAgent記載は将来差し替え先のコメント。
- 接続: Webと同じイベント・出力位置を使いレポート表示へ流す。Evidenceはfixture由来。
- 評価候補: 実アプリの静的情報と実機観測。REA/JADXで代替可能かは未確認。

### 02: テスト自動化

- 入力: report.json、テストケース表、観点・実行方針。
- 入口: [ta2.py](../../../web/routes/ta2.py) `/api/ta2/tests`、`/api/ta2/run` 等。
- QA処理: [advanced_generator.py](../../../web/services/qa/advanced_generator.py) が
  graph、coverage、playwright_candidates、品質観点、テストケースHTMLを生成。
- [spec_ts_generator.py::generate_spec_ts](../../../web/services/spec_ts_generator.py) は
  候補JSONとreportを読み、フォーム操作・遷移・検証アサーション・meta JSONを生成。
  manual-reviewはskip、allow_submitは既定False。K1送信ゲートウェイをimportする。
- 指揮のTestsAgent経路は `testcases/testcases.spec.ts` を作り、AutoRunの
  `qa_process/autorun.spec.ts` と区別する（[tests_agent.py](../../../web/services/orchestration/agents/tests_agent.py)）。
- 実行: [playwright_executor.py](../../../web/services/playwright_executor.py)。Node/Playwright依存。
- Evidence: page_id、fingerprint、trace_id、実測locator、実行結果。接続コードあり・実行未確認。
- 評価候補: 静的候補を人の探索対象へ提示する余地。自動実行への昇格は別判定。

### 03: AutoRun

- 入力: URLまたは文書駆動の条件。入口: [auto_run.py](../../../web/routes/auto_run.py)。
- 中核: [auto_run_pipeline.py::_run_job](../../../web/services/auto_run_pipeline.py)。
  discover → login入力待ち → crawl → QA → 文書モードのみMBT → 段階承認 → spec生成 → 実行。
- データ: AutoRunJob、report、viewpoint_snapshot、stages、候補、Playwright結果・証跡。
- 重要: `_await_stage_approval` にはタイムアウト時に未確認を記録して先へ進む経路がある。
  「必ず人の承認まで止まる」と一律には説明できない。設定ごとの実挙動は未確認。
- 01/02/文書MBT/実行を連結。Playwright・子プロセス・LLM利用時のproviderに依存。
- 評価候補: 新しい静的推論を承認・未確認の管理へどう流すか。現時点で設計しない。

### 04: CLI / API

- [src/cli.py](../../../src/cli.py) の doc/autorun/test/sites/show/viewpoints 等。
  docは従来CLIへ委譲、autorunはサービス経路を利用。
- [api_v1.py](../../../web/routes/api_v1.py) `/api/v1` はサイト・クロール・レポート・
  snapshot・diff等を提供。`/cli` 自体はコマンド案内画面。
- [openapi_spec.py](../../../web/services/openapi_spec.py) は **WebSpec2Doc自身のAPI** の仕様。
  対象サイトで観測したAPIの復元とは別機能。
- 01/02/03の入力と成果物を再利用。CLIの承認自動化はREADMEに記載されるが、
  静的推論の承認に流用できるかは未確認。

### 05: オートヒーリング

- 入力: 接続リポジトリ・検証コマンド・不具合・修正指示。
- [healing.py](../../../web/routes/healing.py) →
  [orchestrator.py](../../../web/services/healing/orchestrator.py) → verification/agents/git_ops/
  run_store/report等。_run_loop_innerでリポジトリ・コマンド確認から処理を開始。
- 分離worktreeを使う設計。実行記録・修正提案・報告・PR作成・人の判断を扱う。
- 02/03のテスト成果物・指揮のhealing agentと接続。Git、修正agent、GitHub利用時の接続に依存。
- コード位置の根拠と実行結果が重要。外部リポジトリでの修正成功は今回未確認。
- 評価候補: 根拠付きmodule関係の補助。修正根拠として採用する可否は未判定。

### 06: ドキュメント検証

- 入力: 仕様文書、参加者・役割、観点、版、質問への回答。
- [doc_verify.py](../../../web/routes/doc_verify.py) とR2〜R5系ルート →
  web/services/docverify の ingest/checks/process/metrics/store等。
- 文書断片・位置・引用 → finding候補 → candidate/adopted/rejected/fixed/verified、版比較、
  follow-up、質問CSV/XLSX、検査報告。storeはテナント別inspection.jsonを保存する。
- Evidenceは文書断片。読取ライブラリ・vendor reverse_docを利用し、System01の実測突合入口もある。
- 接続コードあり。全規則の精度・UI状態・承認の実動作は未確認。
- 評価候補: 静的解析結果を文書との差分候補として利用できるか。自動結合は確認していない。

### 07: バッチ・スクリプトのテスト

- 入力: .bat/.cmd/.sh/.ps1と仕様書、設定。入口: [batch_test.py](../../../web/routes/batch_test.py)。
- [parse.py::analyze](../../../web/services/batchtest/parse.py) は**実行せず規則で**引数・環境変数・
  入出力・終了コード・ログを行番号付きで抽出。design → cases → codegen → exportへ接続。
- analyze入口はスクリプトなし・複数本をエラーにし、facts/spec/settingsをstoreへ保存する。
- データ・成果物: job、files、facts、spec、cases、テストコード・エクスポート。
- 文書読取を06のingestと共有。静的仕様候補をQAへ変換する能力は既存。
- 07内の実行機能・生成コードの対象環境での成功は未確認。08との自動引き渡しも未確認。
- 評価候補: 既存のテキスト規則では扱えない対象があるか。一般的静的解析の新設は重複に注意。

### 08: バッチ・バックエンドのテスト

- 入力: 案件・テストレベル・ジョブ定義・仕様・ソース・DDL・入出力・golden・DB接続。
- [backend_test.py](../../../web/routes/backend_test.py) と stages/run/envsルート →
  backendtest の intake/stages/cases/oracle/codegen/runner/judge/export。
- [intake.py](../../../web/services/backendtest/intake.py) は根拠file/line/text、origin、
  confirmed=Falseを持つfactsに正規化。未読・不一致はquestionsへ送る。
- [store.py](../../../web/services/backendtest/store.py) のTARGET_KINDSは **batchのみ**。
  integration_internal/external/system/acceptanceの4レベル・8段階・承認/版/証跡がある。
  引き継ぎ書の「API/DB等」は、独立API対象を登録できるとの意味には拡張しない。
- [runner.py](../../../web/services/backendtest/runner.py) は生成pytestを子プロセスで実行。
  停止・制限時間・部分結果・証跡保存がある。codegen_runtimeのDB接続はpsycopgを使う。
- [judge.py](../../../web/services/backendtest/judge.py) はpass/failと
  undetermined/not_run/cancelled/errorを区別し、0件を合格にしない。
- DATA_DIRのテナント別backendtestに案件・版・files・code・evidenceを保存。
- 接続コードあり、実DB・実バッチの成功は未確認。07との自動接続は未確認。
- 評価候補: 根拠付き静的情報の拡充。既存intakeとの重複を先に比較する必要がある。

### 09: 影響度分析

- 入力: 変更指示、旧新文書、変更要求、文書項目・リンク・ベースライン。
- 旧経路: [impact.py](../../../web/routes/impact.py) → impact/analyze.py/store/report。
  文書差分・一致語から影響候補と優先度を生成し、CSV/XLSXへ出力する。
- v2: [impact_api.py](../../../web/routes/impact_api.py)・impact_api_cr.py →
  [engine/run.py::analyze](../../../web/services/impact/engine/run.py) →
  changes/candidates/llm_judge/risk/tests → SQLite保存。
- [candidates.py](../../../web/services/impact/engine/candidates.py) は文書項目のlinksを
  双方向の隣接リストにしBFS、意味類似・一致語を統合する。静的なJSのcall graphではない。
- Evidenceはlink/semantic/keyword/llmとscore。System01のSourceEvidenceと同型ではない。
- テスト選択はリンク先のtestcase文書項目のcode。01/02のpage_id・spec metaへの
  自動変換は今回確認していない。dbはテナント別impact/impact.db。
- 評価候補: 文書のリンクと実module/API依存を結ぶ追加情報。グラフ機能そのものは既存。

### 指揮: Orchestration

- [orchestration.py](../../../web/routes/orchestration.py) → conductor/goals/registry/agents/run_store。
- [registry.py](../../../web/services/orchestration/registry.py) の登録は docs/tests/run/healing。
  **06〜09を含む全System連結ではない**。
- goalsはonboard=docs→tests→run→healing、daily=run→healing、continue、heal。
  [goals.py](../../../web/services/orchestration/goals.py) で列を定義する。
- [DocsAgent](../../../web/services/orchestration/agents/docs_agent.py) は既存AutoRunの
  discover/login/crawlフェーズを再利用。TestsAgentはreportからQAとtestcases.spec.tsを生成。
- Contextのout_dir/domain・成果物パスとrun記録を介して段を渡し、waiting_humanや失敗を扱う。
- Evidenceは各段の成果物・実行記録。新しい観測エンジンではない。

## 4. 実データフロー

```text
URL + 選択条件 + 認証状態
  → discover / run（web/routes）または src/cli.py doc → src/main.py
  → _run_crawl → _do_crawl → crawl_urls / crawl_site
  → Playwright DOM・属性・状態・API応答 → PageData
  → analyze_pages → AnalyzedPage（page_id）
  → build_graph + summarize_forms + 遷移品質
  → reference_docがあれば文書読取・fuse・rule_conditions
  → snapshot保存 → compare指定時にdiff
  → save_outputs → JSON/HTML/Markdown/Excel/PDF（指定形式）

report.json（meta・screens）
  → QA doc_generator / advanced_generator
  → screen_transition_graph / playwright_candidates / テストケース
  → URLモードは候補からspec生成
  → 文書モードは要件と実測を突合するMBT経路を追加
  → spec.ts + .meta.json + 送信ゲートウェイ
  → playwright_executor → 実行結果・スクリーンショット・記録
```

report.jsonは01→QA/02/03の構造化受け渡しであり、PageDataの全観測をそのまま保存する形式ではない。
[json_reporter.py](../../../src/generator/json_reporter.py) の `_screen_dict` はAPI呼び出しを
直列化していない。APIはsnapshotのPageData保存とHTML/architecture生成の別経路を持つ。
`meta.report_hash` はscreensの正規化JSONのSHA-256。推論キーの無条件追加は比較互換に影響する。

```text
参考文書 → ingest.loader → DocumentBundle + DocumentEvidence
  → ingest.matcher.fuse（実測画面との対応・差異）
  → doc_fusion.json/md・要件trace・正式名・文書由来条件
  → refresh指定ならrefreshed_spec.md / refresh_log.json

人の操作 → session_recorder → sessions/session_*.jsonl
  → report.jsonとの突合 → coverage / reverse_assets
  → recorded_assets.json / recorded_candidates.json / セッションMarkdown
  → src/main.py::_merge_recorded_candidates → QAのPlaywright候補

文書 → 06 ingest（断片） → finding・検査保存
スクリプト + 文書 → 07 parse/design → cases/code/export
ジョブ定義 + DDL等 → 08 intake → facts/questions → 承認 → cases/oracle/code → 実行証跡 → 判定
変更指示 + 文書/リンク → 09候補探索 → risk/test選択 → DB・レポート
```

06のingestは07の仕様書読取と共有される。09旧経路は06のdiff処理を利用する。
07→08、01→09、06→指揮の自動データ移送は未確認であり、図に接続済みとは書かない。

## 5. Evidence体系

| 種類 | 出所 | 意味 |
|---|---|---|
| SourceEvidence | DOM要素 | selector・bbox等 |
| DocumentEvidence | 入力文書 | file・位置・引用 |
| runtime | ブラウザ実測 | API・状態・検証 |
| recorded session | 人の操作記録 | 操作列・訪問・観察 |
| snapshot/diff | 保存した実測 | 版間の変化 |
| 08 facts | ジョブ・DDL等 | 行付き未確定事実 |
| 09 evidence | 文書リンク等 | 類似・関係の根拠 |

- SourceEvidence自体はselector/html_attribute/screenshot_path/bboxを保持する。
  confidenceはFieldData・TestCondition・ValidationObservation等の側にある。
- 実測由来confidence=1.0は「観測した値の出所」を表し、仕様網羅・業務上の正しさを保証しない。
- DocumentEvidenceはfile/location/quote。表抽出とLLM抽出のsource/confidenceを区別し、
  DocumentedRuleのLLM由来confidenceはモデル上0.7既定・規約上0.9以下。
- API: ApiEndpoint(method/path/status_code/content_type/sample_fields)。レスポンス値や
  必須性・エラー全体を網羅したモデルではない。NetworkCaptureは応答本文に上限を持つ。
- PageState・SpaTransition・EmbeddedFrameで隠れ状態や未読フレームも区別する。
  open shadow rootの再帰探索があり、closed rootを読めるとは主張しない。
- 記録由来RecordedTestCaseはsession・selector・観察・page_idsを持つ。
  reportに対応しない訪問は未確認として扱う。
- snapshotはPageDataを保存し、差分は観測版間の変化。未到達部分の不存在は証明しない。
- 08はconfirmedとoracleの確定・実行fact・判定を分ける。09のscore/confidenceは
  類似度や推論の評価であり、UI実測のconfidenceとは意味が異なる。
- observed/matched/inferred/ambiguous/unknown/unavailableの統一モデルは、
  今回確認した既存型には存在しない。SourceEvidenceへ静的出典を無理に詰める設計は未採用。

## 6. 既存reverse / static / runtime能力と重複候補

| 既存能力 | 根拠 | 重複候補 |
|---|---|---|
| DOM・フォーム実測 | page_crawler | Browser/CDP観測 |
| modal等の状態探索 | action_explorer | 隠れ状態探索 |
| XHR/fetch観測 | NetworkCapture | network解析 |
| 操作記録・再生 | capture | 操作reverse |
| 記録からQA逆生成 | reverse_generator | reverse資産生成 |
| 文書×実測の突合 | ingest.matcher | 複数根拠の突合 |
| script規則抽出 | batchtest.parse | 静的QA分析 |
| DDL・ソース読取 | backendtest.intake | 静的仕様抽出 |
| 文書リンクBFS | impact.engine | 関係グラフ探索 |

- main.pyには record-session/replay-session/import-recording/exploration-coverage/
  reverse-assets/export-findings の分岐があり、単なる設計書上の名称ではない。
- API recovery: [recovery.py](../../../src/apispec/recovery.py) は画面↔API対応表と
  OpenAPI draftを生成し、CLAIM_SCOPE=observed_calls_onlyを明示する。
  sample_fieldsの型は空定義で、未観測のエラーを補完しない。
- ただしPath.rglobとrgの両検索でbuild_screen_api_map/build_openapi_draftの
  src/web内の使用は定義のみ。テストからは呼ばれる。
  feature_contractはimplementedだが、標準CLI/API→保存成果物の経路は確認できなかった。
  **生成関数あり／製品への出力結線未確認**と分類する。
- 一方API実測自体はpage_crawler→PageData→HTML/architecture.mmdに使われる。
  API recoveryの結線問題と、network観測が無いという主張を混同しない。
- 既存SPA探索は安全なホワイトリスト要素のクリックで状態差分を実測する。
  JS bundle内の未実行routeを列挙する機能とは対象が異なる。

## 7. 未実装・モック・不足能力

コード根拠が直接ある範囲と、探索で確認できなかった範囲を分ける。

1. **モック確認**: 01 appはfixture経路。契約doc_app_mockもstatus=partial。
   現行経路では実APK/.appから仕様を復元しない。
2. **結線未確認**: API recoveryの純粋関数と単体テストはあるが、製品出力まで未確認。
   「API復元が全面的に未実装」とは判断しない。
3. **対象制約を確認**: 08のtarget_kindはbatch。独立API対象・任意DB製品への対応は未確認。
4. **観測モデルの不足**: PageData/SourceEvidence/ApiEndpointにはbundleファイル、
   source mapの原ソース位置、module依存辺、native symbol/xrefを表すフィールドがない。
5. **製品経路未確認**: src/webの2方式検索でJS bundle静的解析・source map解析・
   REA/JADX/Ghidra実行アダプタを確認できなかった。外部ツールで手動分析できるかとは別問題。
6. **接合未確認**: 09の文書リンクと01/02の画面・module・API・テストを一貫した
   根拠付き識別子で自動接合する経路は未確認。09にグラフが無いとの意味ではない。
7. **統一認識状態の不足**: 根拠の出所やconfirmed/未判定は既存だが、静的候補とruntimeの
   matched/ambiguous等を統一する型・出力契約は確認できなかった。

これらはREA/Ghidra採用の結論ではない。既存結線の改善、直接実装、他のツール、
導入しない選択も含め、価値・誤推定・実行/依存コストを比較するのはPhase 1以降。
設計資料全件と全コードの実行を網羅していないため、上記以外を「未実装一覧」として断定しない。

## 8. 安全境界と実装を開始しない理由

- [network_interceptor.py](../../../src/crawler/network_interceptor.py) のMutationBlockerは
  POST/PUT/PATCH/DELETEを既定遮断、許可は明示opt-in。
- 同attachにはroute登録失敗時に警告を残す経路がある。今回、安全境界の実効性を
  実ブラウザで検証したわけではない。発見事項として記録するだけで修正しない。
- URL安全性、robots/rate limit、auth state、テナント別out_dirを保つ必要がある。
- spec生成のallow_submit=Falseとクロールのmutation遮断は別経路の制御である。
- データ・秘密・.env・鍵の中身は調査しない。providerの導入や認証設定変更も行わない。
- スキーマ互換: report_hash/snapshot既存意味を保つ。静的candidateを観測APIへ混ぜない。

## 9. 未確認事項と確かめ方

| 未確認事項 | 確かめ方 |
|---|---|
| 実行経路の実動作 | 許可後にfixture実行 |
| API復元の動的呼出 | 実行traceと成果物確認 |
| app選択条件の反映 | 選択入力と出力比較 |
| AutoRun承認条件 | 設定別に待機を検証 |
| 07→08自動接続 | 呼出とI/Oを追加追跡 |
| 01→09の自動接合 | 識別子と取込を追跡 |
| 06全規則の精度 | 評価資料と出力比較 |
| 08の実DB動作 | 許可済みDBで実行 |
| healing外部連携 | 許可済みrepoで検証 |
| REA/Ghidra適合 | Phase 1で一次調査 |
| リモートmainとの差 | 合意後にfetch比較 |

実行済み: 指定文書読取、実在パス再探索、ソース呼出/出力/保存追跡、契約照合、
2方式の不在候補再検索、文書リンクの存在確認。
未実行: pytest、make test、verify-ui、verify.sh、quality_harness、サーバ起動、
ブラウザ操作、クロール、DB接続、REA/Ghidraインストール・実行、CI、修正・実装。
未検証: 実行時の全Systemフロー・性能・精度・安全境界・テナント分離の実効性。

## 10. Phase 0 の出口確認

HANDOFF §23の11項目について、以下の章で現行コード上の説明が可能になった。

- 01〜09の役割・指揮: §3。
- System間受け渡し・report.json: §4。
- Evidence種類: §5。
- Playwright/API recovery/reverse-assets: §3/§6。
- 01 appのモック範囲: §3/§7。
- 重複能力と不足能力: §6/§7。

**現行理解の静的成果物を提出し、ここで停止する。**
実機能の動作保証やREA/GhidraのGO判断は行わない。
Phase 1の外部調査・適合評価・Phase 2の設計・コード変更には進まず、次の指示を待つ。
