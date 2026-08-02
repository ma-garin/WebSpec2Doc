# WS2D-GL-001 用語集

- 文書ID: WS2D-GL-001
- 版数: 2.0 / 作成日: 2026-08-02
- `CONTEXT.md`（ユビキタス言語）を土台とし、`quality/feature_contracts.yml`（機能契約）・`docs/sdlc/_asbuilt/modules.json`（モジュール実測）・主要モジュールのdocstringから収集した用語を加え、6分野・80語以上に拡充した。

## 0. 本書の使い方

- 用語は6分野（認証・テナント／クロール・解析／ドキュメント生成・突合／テスト設計／実行・ジョブ／品質・プロセス）に分けて掲載する。同じ用語が複数分野にまたがる場合は、最も中心的な分野に1回だけ掲載し、他分野からは参照する。
- **太字**の用語は、混同しやすい・誤用実績がある・実装上の区別が重要な語である。§7「特に混同しやすい語」で改めてペアとして解説する。
- 「使用箇所」列はファイルパス・関数名・画面名など、実際にコードを確認できる場所を示す。列が「—」の場合はコード上の特定シンボルを持たない概念語（ユーザー向け概念のみ）であることを意味する。
- 定義に自信が持てない・裏付けが取れなかった語は「未確認」と明記した（例: FE、SDD）。
- 本書は`CONTEXT.md`（ユビキタス言語の一次情報源）と矛盾しない。定義に食い違いが生じた場合は`CONTEXT.md`を正とする。

## 1. 認証・テナント

| 用語（日本語） | 英語・コード識別子 | 定義 | 使用箇所 | 関連語・注意点 |
|---|---|---|---|---|
| **サイト認証（ログイン）** | login, `web/routes/login.py` | **ツールがクロール対象サイトへログインする**ことを指す。ID/PASSWORD送信後は即破棄し、セッション（Cookie等）のみ保存する | `src/crawler/auto_login.py`, `detect_login_wall()` | 下記「利用者ログイン」と完全に別概念。§7参照 |
| **利用者ログイン** | account_auth, `web/routes/account.py` | 利用者本人がWebSpec2Doc自体に入るための認証 | `web/auth.py`, `web/services/auth_store.py` | 上記「サイト認証」と混同しない。§7参照 |
| 自動ログイン | auto_login | ページ解析で検出したログインフォームへ、GUI上でユーザーが入力した値を自動送信する認証取得方式 | `src/crawler/auto_login.py` | 廃止された「手渡しログイン」（別ウィンドウ起動方式）とは別方式 |
| ログイン必要箇所 | login_wall | ページ解析中、認証によりアクセスがブロックされる地点（リダイレクト・パスワードフォーム・401/403） | `src/analyzer/login_wall.py: detect_login_wall()` | 検出は補助であり、ユーザーが手動でスキップ・追加できる前提 |
| セッション（サイト認証） | session, `auth.json` | 自動ログインで取得・保存する認証状態（storage_state＝Cookie等）。サイト単位で保存 | `src/crawler/session_guard.py`, `output/{domain}/auth.json` | 「認証情報」は避ける語（パスワード本体を連想させるため） |
| セッションcookie（利用者） | `ws2d_session`, `SESSION_COOKIE_NAME` | 利用者ログイン成立後にブラウザへ発行するセッションクッキー | `web/auth.py` | サイト認証の「セッション」とは別物 |
| セッション期限切れ検出 | session_guard | 再クロール中に認証ページへ弾かれた場合、保存セッションの失効を検出し中断する | `src/crawler/session_guard.py` | `detect_login_wall`を再利用。到達ページ激減の偽陽性ドリフトを防ぐ |
| 利用者 | user | メールアドレスで識別されるWebSpec2Docの使い手。1人が複数ワークスペースに所属しうる | `web/services/auth_store.py` | 「アカウント」は避ける（UserとCustomerの混同回避） |
| **ワークスペース** | tenant, `tenant_id` | 成果物・設定・観点DBをテナント単位で分離する作業単位 | `web/tenancy.py`, `output/tenants/{slug}/` | ユーザー向け語は「ワークスペース」、コード識別子は`tenant`。両者は同一概念の呼び分けであり別概念ではない。§7参照 |
| メンバーシップ | membership | 利用者とワークスペースの所属関係。ロール（owner/admin/member）を持つ | `list_memberships`, `set_memberships`（`auth_store.py`） | owner/adminは設定変更・メンバー管理が可能、memberは不可 |
| ロール | role | メンバーシップに付与される権限区分（owner／admin／member） | `web/services/auth_store.py: ROLE_ADMIN, ROLE_MEMBER` | 管理者専用画面（管理コンソール）はadmin以上が対象 |
| テナント分離 | tenant_isolation | 出力・観点DB・APIトークンをワークスペース単位で分離する仕組み | `web/tenancy.py: scoped_output_dir`, `scoped_instance_path` | パストラバーサルによるテナント越境を防止する境界でもある |
| 管理コンソール | admin console | テナント・ユーザーを管理する管理者専用画面 | `templates/admin/console.html`, `web/routes/tenant_admin.py` | 一般ロール（member）はアクセス不可 |
| 管理監査ログ | admin_audit | 管理操作を秘密値なしのJSONLへ記録する仕組み | `web/services/admin_audit.py: append_admin_audit` | ワークスペース単位で分離される（`instance/tenants/{slug}/admin_audit.jsonl`） |
| SSO（OIDC） | sso_oidc | OpenID ConnectによるシングルサインオンとAPIトークンのスコープ管理 | `web/routes/oidc.py`, `web/services/oidc.py` | Microsoft Entra ID・Google Workspaceを先行対応 |
| APIトークン | API token | プログラムからのAPI呼び出し用の認証トークン。スコープ付与が可能 | `create_api_token`（`auth_store.py`） | SSO経由の発行にも対応 |
| 初期セットアップ | setup | 最初のワークスペースとオーナーを作成する初回導入フロー | `/auth/setup`, `web/routes/account.py: signup_page` | 未実施の場合はログインより先に誘導される |
| アカウントロックアウト | account_locked | パスワード連続失敗によるアカウントの一時的な利用停止 | `web/services/auth_store.py`（failure_modes: `account_locked_after_repeated_failures`） | 「最後の管理者」保護（last_admin_protection）とは別の防御策 |

## 2. クロール・解析

| 用語（日本語） | 英語・コード識別子 | 定義 | 使用箇所 | 関連語・注意点 |
|---|---|---|---|---|
| サイト | site, domain | 監視対象として登録された1つのWebシステム。ドメインで識別され、クロール設定を保持する永続レコード | `src/registry/site_registry.py` | 「ドメイン」は出力フォルダのキーとしてのコード用語。ユーザー向け概念は「サイト」 |
| オートクローリング | autocrawl | 入力URLを起点にリンクをたどって到達ページを自動収集するクロール方式（本ツールの基本動作） | `src/crawler/page_crawler.py`, `parallel_crawler.py` | 「スクレイピング」「巡回」は使わない |
| ページ解析 | discover | オートクローリングの前段で到達ページ一覧を先に取得する軽量工程 | `web/routes/discover.py: discover_pages()` | コード識別子は`discover`。画面表記は「ページ解析」 |
| 再クロール | recrawl | 登録済みサイトを保存済み設定で取り直すこと。前回スナップショットとの差分検知の中核 | `static/js/recrawl.js` | 「クロール」単体は初回実行、「再クロール」は既存サイト前提 |
| クロール礼儀 | politeness | 対象サイトへ負荷や副作用を与えないための既定動作。token bucket方式のレート制御・robots.txt尊重・破壊的リクエスト遮断 | `src/crawler/politeness.py`, `network_interceptor.py` | 「送信ゲートウェイ」とは目的が異なる（対象サイトへの配慮 vs 自己防御）。§7参照 |
| 画面状態 | PageState, `state_signature` | クロール時・操作記録時に共用する画面状態の識別キー | `src/crawler/action_explorer.py: state_signature()` | 独自ハッシュの実装は禁止（CONVENTIONS §1-3） |
| フィンガープリント | fingerprint v2 | 画面の同一性判定に使う署名アルゴリズム | `src/analyzer/canonicalizer.py` | 現新比較（`pair_matcher.py`）でも構造署名部分を再利用する |
| アクション探索 | action_explorer | ボタン・タブ・アコーディオン等のクリックで出現する画面状態を検出し、バリデーションを実測する | `src/crawler/action_explorer.py` | 安全ホワイトリスト要素のみをクリックする |
| SPA遷移捕捉 | spa_monitor | pushState/replaceState/hashchangeを伴うURL変化を記録する | `src/crawler/spa_monitor.py` | transition_graphの遷移エッジとして供給される |
| データフロー追跡 | data_flow | ある画面で入力した値が別画面のテキストに反映されているかを観測する（Black Widow, S&P 2021） | `src/crawler/data_flow.py` | 送信を伴わない範囲でのみ動作 |
| 技術スタック検出 | stack_detector | フロントエンド・バックエンドの技術スタックをPlaywrightで自動検出する | `src/analyzer/stack_detector.py` | アーキテクチャ図生成の入力になる |
| パフォーマンス計測 | performance_probe | Core Web Vitals（LCP/CLS/TTFB等）のラボ計測 | `src/crawler/performance_probe.py` | INPは自動クロールでは原理的に測れず対象外。合否判定には使わない旨を明記する方針 |
| ネットワークインターセプト | network_interceptor | クロール中のXHR/fetchレスポンスを傍受しAPIエンドポイントを記録する | `src/crawler/network_interceptor.py` | API仕様の逆生成（apispec）の入力になる |
| フォーム到達クロール | form_navigator | 登録・検索フォームの先にある画面へ、実際に送信して到達するテスト環境限定機能 | `src/crawler/form_navigator.py` | 二重オプトイン（環境変数＋明示フラグ）必須。既定は完全無効 |
| evidence（根拠） | evidence | 生成された仕様・テスト条件・観点に紐づく実測の根拠（セレクタ・スクリーンショット座標・confidence） | evidence-only原則全体 | 実在する要素に紐づかない生成物は破棄する |
| 主張境界 | claim scope | モジュールが主張しないことを明示する、docstring中の定型的な記述慣行 | 各モジュールdocstring（例: `src/apispec/__init__.py`） | evidence-only原則をdocstringレベルで徹底する手段 |

## 3. ドキュメント生成・突合

| 用語（日本語） | 英語・コード識別子 | 定義 | 使用箇所 | 関連語・注意点 |
|---|---|---|---|---|
| Doc Fusion（文書×実測突合） | doc_fusion | アップロードした既存仕様書等と実測結果を突合しギャップを検出する機能 | `web/routes/traceability.py`, `src/ingest/` | 突合結果は「文書のみ」「実測のみ」「矛盾」の3分類で報告 |
| 文書由来仕様 | DocumentedScreen, DocumentedField | 既存文書（Excel/Word/PDF/Markdown/YAML/Gherkin等）から正規化した画面・項目の構造データ | `src/ingest/models.py` | 実測由来の`SourceEvidence`と対をなす`DocumentEvidence`を持つ |
| RFP要件トレーサビリティ | req_tracer | 文書由来の要件を実測画面・テストケースへマッピングする機能 | `src/ingest/req_tracer.py` | `web/services/traceability.py`の暫定実装（画面=要件とみなす）とは別物。web→src import禁止 |
| 文書の再生 | refresh_reporter | 古い参考文書の構造を保ったまま実測値で更新した新版仕様書を生成する（Doc Fusion Phase 3） | `src/generator/refresh_reporter.py` | LLMを使わない決定的マージ。自由文のリライトはしない |
| 画面遷移図 | transition diagram | クロール結果から画面間遷移を可視化したビュー（シーケンス/コミュニケーション/アクティビティ図） | `web/routes/report.py`, `src/graph/transition_graph.py` | 全ページの50%以上から出るリンクは共通ナビとして非表示にする |
| 画面遷移表 | state transition table | ISTQBの状態遷移テスト技法に基づく標準テーブル（状態×イベントのマトリクス） | `src/graph/state_table.py: build_state_table()` | 無効遷移・0-switch/1-switchパスも含む５要素をすべて生成する |
| アーキテクチャ図 | architecture_generator | 技術スタック・APIエンドポイント情報からMermaidアーキテクチャ図を生成する | `src/generator/architecture_generator.py` | 検出情報不足時は推定である旨を明示する |
| API仕様の逆生成 | apispec recovery | 観測したAPI呼び出しを「画面↔API対応表」とOpenAPI雛形へ変換する | `src/apispec/recovery.py` | 埋められない箇所は空欄のまま。推測で埋めない |
| 画面カバレッジマップ | screen_coverage_map | 自動テストが実際に踏んだ画面・遷移を遷移図に重ねて可視化する | `src/apispec/coverage_map.py` | 「踏んだ＝検証した」ではない。カバレッジ率を品質保証の数値として掲げない |
| 完全アーカイブ | full_archive | 規制業種向けに、ある時点の成果物一式をマニフェスト（SHA-256）付きで1つの書庫へ固める | `src/archive/full_archive.py` | 保持ポリシー（古いものを消す）とは逆に「消さずに固めて残す」仕組み |
| 外形監視 | external_monitor | sitemap/PDF文書の変化を検知する（QAユースケースに重なる範囲限定） | `src/archive/external_monitor.py` | 検知できるのは取得できた内容の変化のみ。問題かどうかは判断しない |
| トレーサビリティ | traceability | 画面→テスト観点→テストシナリオの対応関係の追跡 | `web/services/traceability.py` | Doc Fusionのreq_tracerとは別実装（暫定 vs 本格） |
| ROIダッシュボード | usage_roi | 利用実績（クロール数・生成文書数）から削減工数を明示係数で推定表示するビュー | `web/routes/usage.py`, `web/services/usage_tracker.py` | 係数は環境変数で調整可能。推定である旨を常に明記する |
| CLIモード | cli_mode | GUIを使わず端末から本体機能を実行するモード（System 03） | `src/cli.py`, `web/services/cli_runner.py` | 終了コード（0/1/2/130）で自動化から判定できる |

## 4. テスト設計

| 用語（日本語） | 英語・コード識別子 | 定義 | 使用箇所 | 関連語・注意点 |
|---|---|---|---|---|
| **観点（viewpoint）** | viewpoint | QAテスト設計における着眼点・確認すべき性質を表す抽象的な単位 | `web/services/viewpoint_store.py`, `web/routes/viewpoints.py` | 下記「テストケース」とは別物。§7参照 |
| **テストケース** | test case | 観点を具体的な前提条件・手順・期待結果に展開した実行可能な検証単位 | `src/generator/testcase_table.py`, `output/{domain}/testcases/` | 10列テストケース表として編集・実行される |
| **セット（観点セット）** | set, `set_id` | 観点を束ねる名前付きコレクション。セット/バージョン/アイテム3階層の最上位 | `viewpoint_store.py: create_set/get_set/list_sets` | §7で3階層を図解 |
| **バージョン** | version, `version_id` | セット内の1時点のスナップショット。ドラフト（編集可）と確定済み（`ImmutableVersionError`で変更不可）がある | `viewpoint_store.py: ensure_draft/list_versions` | セットとアイテムの中間層 |
| **アイテム** | item | バージョンに属する個々の観点エントリそのもの | `viewpoint_store.py: list_items/_resolve_items` | セット＞バージョン＞アイテムの最下層 |
| 境界値分析（BVA） | Boundary Value Analysis, bva | 実測バリデーション属性（maxlength/min/max/pattern等）からのテストケース導出技法 | `src/analyzer/bva.py`, `field_definition_bva`機能 | 根拠のない値は出力しない。例生成不能時は明示 |
| ペアワイズ法 | pairwise | 2因子網羅による組合せテストデータ生成（貪欲AETG系アルゴリズム） | `src/mbt/pairwise.py`, `src/techniques/combinatorial.py` | 決定的（乱数不使用）。値は実測した選択肢のみ使う |
| デシジョンテーブル | decision table, dt | 必須フィールドの入力有無の全組合せ（2^k真理値表） | `src/generator/test_design.py` | 原因結果グラフから導出することも可能 |
| 状態遷移テスト | state transition testing, st | 遷移グラフからNスイッチ経路を列挙する技法 | `src/generator/test_design.py`, `src/graph/state_table.py` | 0-switch/1-switchの両方を生成 |
| 分類ツリー法 | classification tree method | 対象を階層（画面→フォーム→項目→同値クラス）へ分解し組合せ設計する技法（Grochtmann & Grimm, 1993） | `src/autorun/classification_tree.py` | ペアワイズが表現できない「複数フォームの区別」を扱う |
| 直交表 | orthogonal arrays | 均等割付けされた組合せ表（GF(p)上の線形構成で生成、L9(3^4)等の表記） | `src/autorun/orthogonal_array.py` | ペアワイズとの違いは「出現回数が全て等しい」性質の保証 |
| 原因結果グラフ法 | cause-effect graphing | 入力条件（原因）と出力（結果）を論理ゲートで結びデシジョンテーブルを導出する（Myers） | `src/autorun/cause_effect.py` | 条件間の制約（E/I/O/R/M）を表現できる |
| ドメイン分析 | domain analysis | 1つの境界につきON/OFF/IN/OUTの4点を定める技法（Beizer/Binder、ISTQB CTAL-TA） | `src/autorun/domain_analysis.py` | 境界値分析が示さない「開境界/閉境界」を明示する |
| エラー推測 | error guessing | 欠陥タクソノミを実測項目へ突き合わせる経験ベース技法（ISTQB分類） | `src/autorun/error_guessing.py` | 出力は実測でなく一般知識由来（confidence 0.9固定） |
| ユースケーステスト | use case testing | 実測した遷移グラフとフォームから基本・代替・例外フローを導く技法 | `src/autorun/use_case_testing.py` | フローは候補であり業務上のユースケースと一致する保証はない |
| メタモルフィックテスト | metamorphic testing, MR | 複数の実行結果間に成り立つべき関係を検証する技法（Chen et al., 2018） | `src/mbt/metamorphic.py` | 期待値（オラクル）が無くても検証できる |
| 被覆配列 | covering array | t-way被覆を保証する組合せテスト表の正準実装 | `src/techniques/combinatorial.py` | 制約による被覆不能組は`uncoverable`に全件記録 |
| 項目定義書 | field definition document | 画面の入力項目を定義した文書（境界値データを含む） | `spec.xlsx`（項目定義書シート） | 日本のSIer開発で標準的な成果物形式 |

## 5. 実行・ジョブ

| 用語（日本語） | 英語・コード識別子 | 定義 | 使用箇所 | 関連語・注意点 |
|---|---|---|---|---|
| AutoRun | autorun | URL駆動または文書駆動で、ページ解析→クロール→QA生成→spec.ts生成→テスト実行を一つのフローで行うビュー | `web/routes/auto_run.py`, `src/mbt/` | 「全自動テスト」「ワンクリックテスト」は使わない |
| URL駆動 | URL-driven | 対象URLの実測を起点にテスト候補を生成する、AutoRunの既定モード | — | 「文書駆動」と対の概念 |
| 文書駆動 | document-driven, document_mbt | 参考文書から抽出・追跡した要件を起点に、実測済みの画面・遷移と突合してMBTモデルを生成するモード | `src/mbt/document_model.py` | 文書だけから未観測の画面や遷移は補わない |
| 段階承認パイプライン | stage approval pipeline | テスト目的→計画→フィーチャー分析→観点→基本設計→詳細設計→ケース→自動化の8段階を、提示→承認で進めるAutoRunの中核フロー | `src/autorun/stages.py` | 各段階は項目単位で修正できる。生成はルールベース主・LLM補助 |
| **Run（実行回）** | run, `RunMeta` | **完了した**1回の実行の成果物・履歴を指す単位 | `web/services/run_store.py: RunMeta`, `web/routes/runs.py` | 下記「Job」とは時制が異なる。§7参照 |
| **Job（ジョブ）** | job, `CrawlJob`, `AutoRunJob` | **実行中（または実行待ち）**の処理単位。状態（idle/discovering/crawling/…/complete）を保持する | `web/services/job_queue.py`, `web/services/auto_run_job.py` | §7参照 |
| **Schedule（スケジュール）** | schedule, `ScheduleConfig` | 定期実行の間隔・通知設定を保持する構成。Jobを定期的にトリガーする | `web/routes/schedule.py`, `web/services/scheduler.py` | Schedule→Job→Runの時系列。§7参照 |
| 実行方針 | test execution policy | AutoRunでテストを実行する前に選ぶ方針（全件実行／スモークのみ／重要画面のみ等） | — | 承認ステップ（awaiting_approval）で確認してから実行 |
| テスト選択基準 | test selection criterion | 文書駆動で実行パスを選ぶ規則（頂点網羅／エッジ網羅／到達目標のいずれか） | — | MBTのプライムパス選択基準に対応 |
| 実測バリデーション | measured validation | 実測ロケータへ根拠付きテストデータを入力し、クライアント側の検証状態だけを観測する工程 | `src/mbt/validation_observer.py` | 送信（POST/PUT/PATCH/DELETE）は行わない |
| 要確認キュー→決定への転換 | decisions | 観測では決められない事項を「前提」として質問形式（推奨付き2択）に変換し、実行を止めない仕組み | `src/autorun/decisions.py` | 旧称「要確認」から「決定すべきこと」への設計転換 |
| 自己検証 | mutation_verifier | 生成したテストが実際に欠陥検出能力を持つかをミューテーションテストで検証する | `web/services/mutation_verifier.py` | 「自己検証スコア」と「弱いテストの一覧」を出力 |
| 失敗の原因特定 | failure triage | テスト失敗の仮説を立てて検証し原因を絞り込む | `web/services/failure_hypothesis.py: triage()` | 説明できない失敗は`unexplained_failure`として明示 |
| 送信ゲートウェイ | egress gateway | AutoRunの全ての外向き通信が経由する唯一の出口。SSRF対策・送信予算・送信証跡を一元管理する | `web/services/egress_gateway.py: assert_target_allowed` | 「クロール礼儀」との違いは§7参照 |
| 非信頼コンテンツ境界 | untrusted content boundary | 対象サイト由来のデータを全て汚染済みとして扱う境界。LLMには構造化メタデータのみを渡す | `web/services/untrusted_content.py` | プロンプトインジェクション・stored XSS対策 |

## 6. 品質・プロセス

| 用語（日本語） | 英語・コード識別子 | 定義 | 使用箇所 | 関連語・注意点 |
|---|---|---|---|---|
| Functional Integrity Gate | functional integrity gate | 「UIがある」「テストが通った」だけで完了扱いすることを禁止する開発プロセスルール | `.claude/rules/functional-integrity.md`, `docs/process/functional-integrity-gate.md` | 実行パス（UI→API→…→evidence）の確認を必須とする |
| Definition of Done（DoD） | DoD | 変更タイプ（A:バックエンド/B:フロントエンド/C:ドキュメント）別の完了基準 | `docs/DEFINITION_OF_DONE.md` | IEEE 730-2014・ISTQB Foundation Level準拠 |
| 品質ハーネス | quality harness | 機能契約の整合性（未登録モジュール・シンボル実在・異常系必須）を機械検証するL0ゲート | `scripts/quality_harness.py` | pre-commitには含まれず手動実行が前提（`WS2D-QA-001`§3） |
| 機能契約 | feature contract | 機能ごとのUI/route/coreファイル・シンボル・失敗モード・必須テストを定義したデータ | `quality/feature_contracts.yml` | `feature_id`が要件のプライマリキー（2026-08-02時点で51件） |
| evidence-only原則 | evidence-only principle | 出力するすべての事実に実測・LLM・文書いずれかの根拠を紐づけ、根拠のない推定値を出さない原則 | プロダクト全体の設計原則 | confidence: 実測1.0固定／LLM 0.9以下／文書は quote 必須 |
| 未確認 | unconfirmed | 検証できていない事実を断定せずに明示するラベル | `functional-integrity-gate.md`「未確認ルール」 | 「完了」「検証済み」「問題なし」と言い換えてはならない |
| RCA | Root Cause Analysis | 開発プロセス失敗時に用いる名前付き原因分析枠組み（5 Whys/Fishbone/FMEA/CAPA/DoD update） | `.claude/rules/functional-integrity.md` | 場当たり的な反省（枠組みを伴わないもの）は禁止 |
| カバレッジギャップ | coverage gap | audit.jsonl・埋め込みiframe・未探索画面・未確認リンクを正規化した「見ていない領域」の集計 | `src/generator/coverage_gap.py` | 断定はしない。「未確認」「見ていない」事実のみ述べる |
| ドリフト | drift | 再クロール時に検知される、意図しない仕様変化という現象そのもの | `src/ci_drift.py`, `.github/workflows/spec-drift.yml` | 「差分(diff)」という計算機構の結果を「ドリフト」として解釈・通知する。§7参照 |
| 差分（diff） | diff | 2つのスナップショット間の変更を計算する技術的機構 | `src/diff/differ.py`, `src/diff/screenshot_diff.py` | ドリフト検知の計算基盤。§7参照 |
| 差分の重要度 | severity | 各差分にBREAKING/WARNING/INFOの重要度と根拠文言を付けるルールベース分類 | `src/diff/severity.py: score_changes()` | LLMを使わない決定的分類。安全/危険の判断そのものではない |
| **証跡（evidence pack）** | evidence pack | 検収・監査向けにテスト実行結果・観点・環境情報・スクリーンショットを1つの報告書へまとめたもの | `src/evidence/pack_reporter.py` | 「実行した事実」のみを主張し、品質の合否は判定しない。§7参照 |
| ユーザビリティスメル | usability smells | 実測した操作イベント列から検出するユーザビリティ問題の兆候（Kobold, IJHCS 2017） | `src/ux/usability_smells.py` | 改善提案はしない。検出のみで対処は人に委ねる |
| レイアウト故障検知 | layout failure detection | 要素のバウンディングボックスからViewport ProtrusionとElement Collisionを機械判定する（ReDeCheck型） | `src/viewport/layout_failures.py` | レスポンシブ設計として意図的な重なりと区別できないため断定はしない |
| 文言一貫性チェック | wording consistency | 辞書ベースで同義語混在・全角半角ゆれ・敬体常体混在を検出する | `src/wording/consistency.py` | 辞書に無いものは指摘しない（誤検知の抑制を優先） |

## 7. 特に混同しやすい語（重要）

**サイト認証（ログイン） vs 利用者ログイン**: 前者（`web/routes/login.py`）は「ツールがクロール対象サイトへログインする」ことであり、送信したID/PASSWORDは即座に破棄されセッション（Cookie）のみが残る。後者（`web/routes/account.py`）は「利用者本人がWebSpec2Doc自体に入るための認証」であり、パスワード・ロックアウト・アカウント管理・APIトークンを備える別システムである。`CONTEXT.md`は「認証」という語も対象サイト側専用の語として扱い、利用者側では使わない方針を明記している。

**観点（viewpoint） vs テストケース**: 観点はQAテスト設計における抽象的な着眼点（「境界値を確認する」等）であり、テストケースはそれを具体的な前提条件・手順・期待結果に展開した実行可能な検証単位である。観点1件から複数のテストケースが生成されうる、1対多の関係にある。

**観点の3階層（セット／バージョン／アイテム）**: `セット`は観点を束ねる名前付きコレクション（最上位）、`バージョン`はセット内の1時点のスナップショット（ドラフトは編集可、確定後は`ImmutableVersionError`で不変）、`アイテム`はバージョンに属する個々の観点エントリ（最下層）。階層は「セット＞バージョン＞アイテム」の順。

**Run／Job／Schedule**: 時系列で並べると `Schedule`（定期実行の設定）→ `Job`（実行中・実行待ちの処理単位、状態を持つ）→ `Run`（完了した1回の実行の成果物・履歴）という関係になる。JobとRunの違いは「時制」であり、Jobは進行中、Runは完了後の記録である。

**テナント vs ワークスペース**: この2語は**別々の概念ではない**。同一の対象（成果物・設定・観点DBを分離する作業単位）を指す2つの名前であり、`tenant`／`tenant_id`はコード識別子、「ワークスペース」はユーザー向けの表示用語である。「サイト」と「domain」の関係と同型の命名パターン（ユーザー向け語とコード識別子の使い分け）である。

**クロール礼儀 vs 送信ゲートウェイ**: 両者とも「通信を制御する」機構だが目的が異なる。クロール礼儀（politeness）は**対象サイトへの配慮**（robots.txt尊重・レート制御）が目的であり、送信ゲートウェイ（egress gateway）は**自己防御**（内部ネットワーク・クラウドメタデータへの誘導阻止、SSRF対策）が目的である。

**ドリフト vs 差分（diff）**: diffは2つのスナップショット間の変更を計算する技術的な機構（`src/diff/differ.py`）であり、ドリフトは「意図せず仕様が変化していく現象」を指す上位概念である。CI drift監視（`ci_drift.py`）はdiffの計算結果を解釈し「ドリフトが検知された」という形で通知する。diffは手段、ドリフトはそれによって捉える現象、という関係。

**証跡（evidence／evidence pack） vs レポート**: `evidence`は個々の事実（1つのテスト条件・1つの観点等）に紐づく根拠（セレクタ・座標・confidence）を指す最小単位である。`evidence pack`や`report.html`のような「レポート」は、多数のevidenceを集約して人が読める形にまとめた成果物であり、evidence packもまた広い意味でのレポートの一種だが、「検収・監査向けに実行事実だけをまとめる」という限定された目的を持つ点で一般のreportと区別される。

## 8. 略語一覧

| 略語 | 正式名称 | 定義・使用箇所 |
|---|---|---|
| AutoRun | （固有機能名） | URL駆動／文書駆動でテスト設計〜実行を自動化するWebSpec2Docの機能。`web/routes/auto_run.py` |
| QF | QualityForward（外部テスト管理ツール） | テストケース表の列構成をQF互換にする出力仕様。`src/autorun/qf_schema.py` |
| BVA | Boundary Value Analysis（境界値分析） | `src/analyzer/bva.py`、`field_definition_bva`機能 |
| MBT | Model-Based Testing（モデルベーステスト） | `src/mbt/`、`document_mbt`機能 |
| FE | Features（機能一覧）と推定 | 段階承認パイプラインの一段階名。`src/autorun/stages.py`本体のステージ識別子は本書執筆時に直接確認できておらず**未確認** |
| ADR | Architecture Decision Record（アーキテクチャ決定記録） | `docs/adr/0001`〜等（例: ADR-0002自動ログイン、ADR-0004アプリ利用者認証とワークスペース） |
| DoD | Definition of Done（完了の定義） | `docs/DEFINITION_OF_DONE.md`。IEEE 730-2014・ISTQB Foundation Level準拠 |
| RCA | Root Cause Analysis（根本原因分析） | `.claude/rules/functional-integrity.md`。5 Whys/Fishbone/FMEA/CAPA/DoD updateのいずれかを使う |
| SSRF | Server-Side Request Forgery | `src/crawler/url_safety.py`, `web/services/egress_gateway.py`で対策 |
| OIDC | OpenID Connect | `web/routes/oidc.py`, `web/services/oidc.py`。SSO実装に使用 |
| MFA | Multi-Factor Authentication（多要素認証） | 自動ログイン時に追加フィールドが出現した場合の対応（`src/crawler/auth_recorder.py`docstring） |
| WCAG | Web Content Accessibility Guidelines | `src/ux/axe_runner.py`。axe-coreによる違反検査 |
| ISTQB | International Software Testing Qualifications Board | 状態遷移テスト・ドメイン分析・エラー推測など複数のテスト技法の分類根拠として頻出 |
| IEEE | Institute of Electrical and Electronics Engineers | `docs/DEFINITION_OF_DONE.md`がIEEE 730-2014に準拠 |
| ISO/IEC 25010 | 品質モデル国際規格 | `WS2D-QA-001`品質保証計画書で8品質特性の評価に使用 |
| NIST | National Institute of Standards and Technology | `src/techniques/combinatorial.py`がNIST SP 800-142（組合せテスト）を一次出典として引用 |
| CTAL-TA | ISTQB Certified Tester Advanced Level Test Analyst | `src/autorun/domain_analysis.py`docstringでドメイン分析の資格分類として言及 |
| AETG | Automatic Efficient Test Generator | `src/techniques/combinatorial.py`が採用する組合せテスト生成アルゴリズムの系統名 |
| TF-IDF | Term Frequency - Inverse Document Frequency | `src/mbt/trace_suggestions.py`。要件↔画面の突合候補提示に使用 |
| SDD | Spec-Driven Development（仕様駆動開発） | 一般的な開発方法論の略語。本リポジトリのコード・ドキュメント内での使用は本書執筆時点で確認できず**未確認**（プロジェクト内使用実績なしという意味） |

## 9. 機能ID対照表（`feature_id` ↔ 画面名・機能名）

`quality/feature_contracts.yml`に登録された`feature_id`（コード上の識別子）と、対応する画面名・機能名の対照。本書§1〜6で個別解説していないものを中心に、2026-08-02時点で確認できた分を掲載する（`risk_level`はfeature_contracts.yml記載値）。

| feature_id | 名称 | risk_level |
|---|---|---|
| coverage_gap_report | カバレッジと未確認領域（網羅性証明） | medium |
| exploration_capture | 探索セッション記録／カバレッジヒートマップ | high |
| reverse_assets | リバース（記録セッション→テスト資産の逆生成） | medium |
| finding_ticket | 気づきマーク→再現手順付きバグ票 | medium |
| ci_warnings_cleanup | CI警告一掃 | low |
| old_new_comparison | 現新比較モード（移行検証支援） | high |
| ux_review | UX自動エキスパートレビュー | medium |
| snapshot_retention | スナップショット保持・容量・バックアップ運用 | high |
| multi_viewport | マルチビューポート仕様書 | medium |
| observability | 可観測性（メトリクス・構造化ログ） | medium |
| api_spec_recovery | API仕様の逆生成 | medium |
| qa_assistant_chat | QAアシスタント（LLMチャット） | medium |
| autorun_security_kernel | AutoRunセキュリティカーネル（送信ゲートウェイ・非信頼コンテンツ境界） | critical |
| ui_visual_complexity | UI視覚的複雑性の実測・回帰検知 | medium |
| technique_engine | テスト技法エンジン（被覆配列の正準実装） | high |
| autorun_extended_techniques | テスト技法の網羅的適用（分類ツリー法・直交表等） | high |
| zero_wait_sample_report | ゼロ待ちサンプルレポート | medium |
| spec_xlsx_full_export | テスト仕様書一式のExcel出力（7シート） | medium |
| condition_to_testcase_link | 画面別設計の条件⇄テストケースの接続 | medium |
| condition_run_status | テスト実行結果の設計への還元 | medium |

## 10. 主要な永続化先一覧

用語がコード上のどのファイル・ディレクトリに対応するかを、代表的なものに限って示す。

| 保存先 | 内容 | 関連用語 |
|---|---|---|
| `output/{domain}/auth.json` | サイト認証のセッション（storage_state） | セッション（サイト認証） |
| `output/{domain}/report.json` | クロール結果（画面一覧・テスト条件） | オートクローリング |
| `output/{domain}/snapshots/` | 再クロール差分検知用のスナップショット | ドリフト、差分（diff） |
| `output/{domain}/qa_process/` | AutoRunの成果物一式（自己検証・失敗仮説等を含む） | AutoRun、段階承認パイプライン |
| `output/tenants/{slug}/` | ワークスペース単位で分離された成果物ルート | ワークスペース、テナント分離 |
| `instance/auth.db` | 利用者認証・テナント管理のSQLiteストア | 利用者ログイン |
| `instance/tenants/{slug}/viewpoints.db` | ワークスペース単位の観点DB | 観点（viewpoint） |
| `instance/tenants/{slug}/admin_audit.jsonl` | 管理操作の監査ログ | 管理監査ログ |
| `output/usage_log.jsonl` | 利用実績ログ | ROIダッシュボード |

## 11. 主要な環境変数一覧

| 環境変数 | 用途 |
|---|---|
| `WEBSPEC2DOC_AUTH_MODE` | 利用者認証モード（既定`auto`） |
| `WEBSPEC2DOC_ALLOW_LOCAL` | ローカルURL（127.0.0.1等）へのクロールを許可 |
| `WEBSPEC2DOC_ALLOW_FORM_SUBMIT` | フォーム到達クロールでの送信を許可する二重オプトインの一方 |
| `WEBSPEC2DOC_LLM_BASE_URL` / `WEBSPEC2DOC_LLM_MODEL` | Ollama等、OpenAI以外のLLMエンドポイント指定 |
| `WEBSPEC2DOC_E2E_URL` | E2Eテスト対象のベースURL上書き |

## 12. 分野橋渡し用語（複数分野にまたがる概念）

| 用語 | 定義 | 関連分野 |
|---|---|---|
| フェイク（テスト） | 実ブラウザ・実LLMの代わりに使う軽量な代替実装（`_FakeRecorderPage`, `_FakeClock`等） | テスト設計 |
| 決定的（deterministic） | 同一入力から常に同一出力を返す性質。乱数・時刻に依存しないこと | テスト設計／品質・プロセス |
| confidence（確信度） | evidence-only原則における根拠の強さを表す数値（実測1.0／LLM0.9以下） | 品質・プロセス／クロール・解析 |
| オプトイン | 既定で無効にし、環境変数等で明示的に有効化する設計方針 | クロール・解析／品質・プロセス |
| バックオフ（backoff） | HTTP 429/503応答時の指数関数的な再試行間隔制御 | クロール・解析 |
| プライムパス選択基準 | MBTで文書駆動テストの実行パスを選ぶ規則（頂点網羅／エッジ網羅／到達目標） | 実行・ジョブ／テスト設計 |

## 改訂履歴

| 版 | 日付 | 内容 | 作成者 |
|---|---|---|---|
| 1.0 | 2026-08-02 | 新規作成 | 開発チーム |
| 2.0 | 2026-08-02 | 全面改訂。用語を26語から80語以上に拡充し、6分野（認証・テナント／クロール・解析／ドキュメント生成・突合／テスト設計／実行・ジョブ／品質・プロセス）にセクション化。混同しやすい語のペア解説を独立セクション化し、略語一覧を5件から19件に拡充。機能ID対照表・永続化先一覧・環境変数一覧・分野橋渡し用語を追加 | 開発チーム |
