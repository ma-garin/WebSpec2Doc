# SPEC-4-5 ○評価群のまとめ仕様（7 機能のミニ仕様集）

| 項目 | 値 |
|---|---|
| WBS | 4-5 |
| 優先度 / 見積 | P3 / 各 0.5〜1sp |
| 依存 | 個別（各ミニ仕様に記載） |
| 背景 | docs/11 §5 アイデアカタログの○評価群: A3・A4・B5・B6・C2・C3・D2 |

## 1. 目的と本仕様書の位置づけ

◎評価（4-1〜4-4）に続く○評価 7 件を、**個別着手時に独立仕様書（SPEC-4-5-x）へ分割する前提**のミニ仕様として束ねる。各項目は「現状（済/未）・ミニ AC・設計方針・固有の罠」を 20〜30 行で確定し、着手判断（優先順位・見積の再評価）に足る解像度を持たせる。共通の絶対制約:

- evidence-only 原則（実測 confidence 1.0・推定は根拠明示・読めないものは「未確認」）
- report.json への追加は**オプトイン**（機能未使用時にキーを追加しない — report_hash 互換）
- 層分離（web→src の一方向）・frozen dataclass・品質ゲート（CONVENTIONS §3）は全項目に適用

## 2. 受け入れ条件（本仕様書自体の AC）

- **AC-0-1**: 各ミニ仕様のミニ AC が、分割時にそのまま SPEC-4-5-x §2 の受け入れ条件に昇格できる粒度（Given/When/Then で読める）であること
- **AC-0-2**: 各項目の「済/未」が実装の現物（ファイル・シンボル）で裏づけられていること
- **AC-0-3**: セキュリティ所見（§5-4）はパッシブ原則 — **受信レスポンスの観測のみで能動的診断リクエストを一切送らない** — が AC に明記されていること

## 3. スコープ外（全項目共通）

- 本仕様段階での実装・テスト作成（分割後の各 SPEC-4-5-x で行う）
- Confluence/Notion 連携（C3 の次段）、多言語検出（B7 は△評価のため対象外）、業務ルール推定（B4 同）

## 4. 基本設計（共通方針）

- 新規解析は `src/analyzer/`・新規出力は `src/generator/`・クロール時観測は `src/crawler/` に置く（既存層に従う）
- クロール時間が延びる機能（マルチビューポート・帳票取得・CWV）は**すべて CLI フラグ / 環境変数によるオプトイン**とし、既定のクロール時間・出力を変えない
- 各分割仕様は feature_contracts.yml に契約を追加し、E2E が必要なものは未使用ポート（8900 番台）を新規割当する

## 5. 詳細設計 — ミニ仕様の集合

### 5-1. 帳票 PDF/CSV 比較（A3 — 現新比較の拡張。依存: WBS-3-3）

- **現状**: 未。ダウンロード検出は皆無（`src` に expect_download / download 処理なし）。比較の器は `src/diff/` にあり、pypdf は Doc Fusion で導入済み（requirements.txt）。CSV 出力の作法は `src/generator/csv_reporter.py`（utf-8-sig）
- **ミニ AC**:
  - AC-1: クロール中に `download` イベント（または Content-Disposition / PDF・CSV content-type 応答）を検出し `output/{domain}/artifacts/` に保存、PageData に「帳票あり（ファイル名・取得元セレクタ evidence）」がオプトインキーで記録される
  - AC-2: 現新比較モードで同名（または対応付けされた）帳票同士を比較し、PDF はページ数＋抽出テキストの差分、CSV はセル単位差分がレポートに載る
  - AC-3: 取得はリンククリック等の**安全なアクション経由のみ**（mutation 遮断は既定のまま）。取得失敗・パース不能は「未確認」記録
- **設計方針**: `crawler/artifact_collector.py`（page.on("download") + 応答 content-type 判定）→ `diff/artifact_diff.py`（pypdf テキスト抽出・csv モジュール）→ diff_report.html に「帳票差分」節。バイナリ完全一致→内容比較の二段で高速化。サイズ上限（既定 10MB）と拡張子ホワイトリスト（.pdf/.csv/.xlsx）
- **罠**: Playwright のダウンロードは `accept_downloads=True` のコンテキストが必要（現在の `_browser_page` は未設定）。PDF テキスト抽出は生成器依存で揺れるため「テキスト一致」でなく正規化（空白圧縮）後に比較する。帳票 URL がワンタイム（トークン付き）の場合は再取得不能 — 取得時刻を evidence に含める

### 5-2. マルチビューポートクロール（A4）

- **現状**: 未。viewport 設定は `src/crawler/` に存在しない（`_browser_page` は既定ビューポートのみ）
- **ミニ AC**:
  - AC-1: `--viewports mobile,tablet,desktop`（既定: desktop のみ）で同一 URL を各ビューポートで取得し、スクリーンショットが `screenshots/{page_id}_{viewport}.png` に分かれて保存される
  - AC-2: ビューポート間の実測差（モバイルで消えるフォーム/リンク/ボタン）が「レスポンシブ差分」としてレポートに載る（差分は集合差の機械算出 — confidence 1.0）
  - AC-3: 未指定時の出力（report.json・スクリーンショット名・report_hash）が完全に不変
- **設計方針**: プリセット（mobile=375x812 / tablet=768x1024 / desktop=1280x800、`WEBSPEC2DOC_VIEWPORTS` で上書き可）。基準ビューポート（desktop）の PageData を正とし、他は `viewport_variants` としてオプトインキーで付加（PageData 複製による画面数の水増しをしない — 画面同定 fingerprint が壊れるため）。比較は名前ベース（field.name / link URL / button label）
- **罠**: 状態探索（explore_page_actions）やバリデーション実測まで全ビューポートで行うとクロール時間が約 3 倍になる — 変種側は**静的抽出＋スクリーンショットのみ**に限定する。fingerprint / state_signature はビューポートでレイアウトが変わっても安定な実装かを canonicalizer で必ず確認（CONVENTIONS §1-3: 独自ハッシュ禁止）

### 5-3. Core Web Vitals 実測（B5）

- **現状**: 未。性能計測コードは皆無（LCP/CLS/PerformanceObserver への言及なし）。移行検証では現新の性能比較（WBS-3-3）にも接続できる
- **ミニ AC**:
  - AC-1: `--web-vitals`（オプトイン）でページごとに LCP・CLS・TTFB（および取得可能なら INP 相当）を実測し、report.json の screen にオプトインキー `web_vitals` として記録される（実測値 = confidence 1.0）
  - AC-2: 計測不能な指標は欠損として記録され、0 等のでっち上げ値を出さない（「未計測」明示）
  - AC-3: report.html に画面×指標の一覧（しきい値の良/要改善/不良は Google 公表基準を注記付きで適用）
- **設計方針**: `crawler/web_vitals.py` — goto 前に `page.add_init_script` で PerformanceObserver（largest-contentful-paint / layout-shift）を仕込み、抽出完了後に `page.evaluate` で回収。TTFB は `performance.getEntriesByType("navigation")`。外部ライブラリ（web-vitals.js の CDN 注入）は使わない — 自前 JS のみ（オフライン・SSRF 保護環境で完走するため）
- **罠**: LCP はユーザー操作後に確定するためヘッドレス・無操作では「その時点までの最大」しか取れない — 値に `observed_until_ms` を添えて計測条件を明示する。CLS は explore_page_actions が DOM を操作した**後**に回収すると探索起因のシフトが混入する — 回収は静的抽出直後・探索前に行う（page_crawler.py L584 の「DOM を変更する探索は静的抽出の後」の順序に割り込む位置を明記して実装）

### 5-4. パッシブセキュリティ所見（B6）

- **現状**: 部分的に土台あり。`crawl_page` が `response.headers` を取得済み（page_crawler.py L570 — 現在は detect_stack にのみ使用）。所見化・Cookie/mixed content 検査は未
- **ミニ AC**:
  - AC-1: **受信レスポンスの観測のみ**で所見を生成し、診断目的の追加リクエスト（ポートスキャン・パス探索・パラメータ改変・強制エラー誘発等の能動的診断）を**一切送信しない**ことを AC として明記・テストで送信リクエスト一覧を検証する（パッシブ原則）
  - AC-2: 検査項目 — セキュリティヘッダの有無（CSP / HSTS / X-Content-Type-Options / X-Frame-Options / Referrer-Policy）、Cookie 属性（Secure / HttpOnly / SameSite — `context.cookies()` から）、mixed content（https ページ内の http サブリソース — 既存 NetworkCapture の観測 URL から）、Server/X-Powered-By によるバージョン露出
  - AC-3: 所見は report.json オプトインキー＋report.html「セキュリティ所見」節。各所見に根拠（ヘッダ名と実値/欠落・対象 URL）と、「本結果は受動観測による簡易チェックであり脆弱性診断ではない」旨の免責を必ず表示
- **設計方針**: `analyzer/passive_security.py` — 入力は response_headers（メインドキュメント）＋ NetworkCapture の観測（サブリソース URL スキーム）＋ context.cookies()。ルールは (項目, 判定, 重大度 info/low/medium, 根拠) の宣言的テーブルで実装し、severity の付け方は qa-review 系既存慣行に合わせる
- **罠**: ヘッダ検査は「無い」ことの証明なので誤検知しやすい — meta タグ CSP（`<meta http-equiv>`）等の代替手段を確認してから欠落と判定する。Cookie はクロール認証（auth_state）由来のものが混ざる — 対象ドメインの Cookie に限定。**bandit ではなく本機能自身が「セキュリティツール」に見える文言を避け**、成果物名は「パッシブセキュリティ所見（簡易）」で統一（診断サービスとの誤認は事業リスク）

### 5-5. Playwright テストコードエクスポート（C2）

- **現状**: **コア生成は済**。`web/services/spec_ts_generator.py::generate_spec_ts` が playwright_candidates.json から .spec.ts（filter_mode / 強アサーション / self-healing ロケータ / PageObject / meta.json 併産）を生成し AutoRun（web/routes/auto_run.py）内部で使用中。未: 顧客 CI にそのまま置ける**納品パッケージ化**（package.json・playwright.config.ts・README）と CLI からの出力経路
- **ミニ AC**:
  - AC-1: CLI（`--export-playwright <dir>` 相当）で `spec.ts + playwright.config.ts + package.json + README.md` 一式が生成され、`npm i && npx playwright test` がそのまま動く構成である（生成物の静的検証: 必須ファイル・baseURL 注入）
  - AC-2: 生成テストの各ケースに test_id・page_id・根拠（fingerprint）コメントが残る（既存 meta.json と同内容 — トレーサビリティ）
  - AC-3: 既存 AutoRun の生成・実行経路が無変更で動く（spec_ts_generator の共通化はシグネチャ互換で行う）
- **設計方針**: 生成本体は移設せず再利用（web/services のまま CLI から subprocess ではなく、`spec_ts_generator` を **src へ移す場合は層分離の再設計が必要** — Phase 1 は「エクスポートは Web UI のダウンロード機能として提供」し CLI 化は分割仕様で判断）。テンプレート（config/package.json）は jinja2 既存依存で生成
- **罠**: spec_ts_generator は web/ 層にあり src/main.py から import できない（CONVENTIONS §1-1 の依存方向）。CLI 対応を安易に足すと層違反になる — 分割仕様の最重要論点として明記。self-healing ロケータは report.json の locators 前提のため、エクスポート時に report.json を同梱するか否か（顧客納品物に内部情報を含めるか）の判断が必要

### 5-6. docs-as-code 出力（C3）

- **現状**: **大部分が済**。`--format md` で screens.md / forms.md / transition.mmd / architecture.mmd を出力（src/main.py::_save_markdown_outputs L729-754）。未: Git 差分管理に耐える出力保証（安定ソート）・目次（index.md）・Mermaid を埋め込んだ単一閲覧導線・エクスポート一括コマンド
- **ミニ AC**:
  - AC-1: 同一サイトを 2 回クロールした markdown 出力が、実体差分ゼロならテキスト差分もゼロ（画面順・リンク順・タイムスタンプの揺れを排除 — crawled_at 等の可変値はフロントマターに隔離）
  - AC-2: `docs-export`（新フォーマット名または make ターゲット）で `index.md`（画面一覧目次・遷移図 Mermaid 埋め込み ```mermaid フェンス）を含む `docs/` 構成一式が生成される
  - AC-3: 既存 md 出力のファイル名・内容の後方互換を維持（変更する場合は AC-1 の安定化に必要な範囲のみ・回帰テストで差分箇所を明示）
- **設計方針**: `generator/markdown_generator.py` の出力順序を canonical 化（page_id 昇順・links は既に dict.fromkeys 重複除去済みの到達順 → URL 昇順へ変更可否を回帰確認の上決定）。index.md は既存 generate_screens_markdown の目次部を抽出・再構成
- **罠**: 「安定ソート化」は既存 golden ファイル（docs/demo/sample_output）と快適に衝突する — サンプル出力の再生成コミットを同時に行い、diff で意図した差分だけかをレビューする。crawled_at をフロントマター化すると md を読む既存テスト・Doc Fusion の md 参照が壊れないか grep 確認

### 5-7. 業界観点パック（D2）

- **現状**: **基盤は済**。観点ストア `web/services/viewpoint_store.py`（SQLite・バージョン管理・`ALLOWED_RULE_FIELDS` に **industry** を含む適用ルール・draft/published 状態遷移・標準セット "WebSpec2Doc標準観点"）と提案生成 `viewpoint_proposals.py`、UI（web/routes/viewpoints.py）が稼働中。未: 業界別プリセット（EC/金融/医療等）のシードデータとインポート導線、LLM 観点生成プロンプトへの業界文脈注入
- **ミニ AC**:
  - AC-1: 業界パック（最低 EC・金融の 2 種）が定義ファイル（yaml/json・リポジトリ同梱）として存在し、UI またはインポート API から 1 操作で観点セットとして取り込める（例: EC=カート・決済・在庫、金融=桁あふれ・端数処理・権限）
  - AC-2: 取り込んだ観点は industry ルールで対象画面に自動適用され、テスト観点出力に業界観点由来であることが表示される（出典=パック名を evidence 相当のメタとして保持）
  - AC-3: LLM 観点生成（openai_qa 経由）に業界コンテキストが注入される場合も confidence ≤ 0.9・幻覚フィルタ（実在しないセレクタ参照の破棄）が適用される
- **設計方針**: `quality/viewpoint_packs/{industry}.yaml` → viewpoint_store の既存スキーマ（rules: industry eq）へ変換するローダを web/services に追加。パック内容はルールベース観点を主とし LLM 依存を最小化（RulesProvider フォールバックで完走 — CONVENTIONS §1-1）
- **罠**: viewpoint_store は SCHEMA_VERSION=2 の SQLite で楽観ロック（ConflictError）・published 版のイミュータブル制約（ImmutableVersionError）がある — パック再インポートは「新バージョン作成」として設計し、上書き更新にしない。業界判定（画面がどの業界か）は自動推定しない — ユーザーがサイト単位で industry を指定する（推定は幻覚リスク）

## 6. テスト仕様（共通方針）

分割後の各 SPEC-4-5-x で AC と 1 対 1 以上の単体テストを定義する。本まとめ仕様の段階での横断的要求のみ規定する:

| 横断要求 | 内容 |
|---|---|
| オプトイン検証 | 全項目に「機能未使用時に report.json 不変（report_hash 一致）」テストを必須とする |
| パッシブ検証（5-4） | フェイク page で送信リクエストを全記録し、所見生成が追加リクエストゼロであることを検証 |
| 時間予算 | クロール系（5-1/5-2/5-3）は既定 OFF の確認と、ON 時の 1 ページあたり追加時間を E2E で計測しログ出力 |
| E2E ポート | 新規 E2E は 8900 番台から採番（8765/8766/8894/8896/8898/8899 使用済み） |

## 7. 完了チェックリスト（DoD — 本まとめ仕様の完了条件）

- [x] 7 項目すべての「済/未」が実装現物と一致している（レビュー時に grep で再確認）— 2026-07-04 再確認済み（本セッションの並行実装群は 5-1〜5-7 のいずれのファイル・シンボルにも触れていないため §5 記載の現状は不変）
- [x] 各項目の分割仕様書番号を予約（SPEC-4-5-1〜4-5-7、§5 の順）し、WBS-4-5 行から参照できる
- [ ] 個別着手時: 分割仕様書を spec-3-1 と同一の章構成（1〜8 章）で起こし、本ミニ仕様の AC を §2 に昇格・詳細化する
- [ ] 個別着手時: feature_contracts.yml への契約追加・CONVENTIONS §3 全ゲート・実行パス確認（UI→API→core→出力→永続化→エラー→ユーザー可視証跡）を各分割仕様の DoD に含める

## 8. このタスク固有の罠（横断）

- **オプトイン破り**が最大のリスク。7 項目のうち 5 項目が PageData / report.json への追加を伴う — 1 つでも無条件キー追加をすると report_hash・スナップショット互換・既存テスト 1,200 件超に波及する。「official_name 方式（値がある時のみキー出現）」を全項目の共通実装規約とする
- クロール時間の複利: 5-1〜5-3 を同時に ON にすると 1 ページの処理時間が数倍になる。politeness（レート制御・Crawl-Delay）との積で実サイトの巡回が非現実的にならないよう、各分割仕様で「全部 ON の実測時間」を DoD に含める
- ○評価群は「小さく見えて器（レポート表示・UI・契約・E2E）が毎回必要」— 0.5sp 見積の項目でも UI 表示まで含めると 1sp に膨れる。分割時に「コア出力のみ（レポート節なし）を Phase 1 とする」切り方を許容する
- 本仕様の「済/未」は 2026-07-04 時点の main の状態。分割着手時には必ず現物を再確認すること（他 WBS の進行で状態が変わる）
