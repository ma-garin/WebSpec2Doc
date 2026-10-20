# 単一製品アーキテクチャ監査（2026-10-20）

対象: origin/main `a82e44f`（#314）。コード変更なし。静的な読解（git grep・該当箇所の目視）のみで、実行による確認はしていない。

## 0. 要件（確定）

- 標準構成: WebSpec2Doc + OpenAI API ／ 閉域構成: WebSpec2Doc + Ollama
- 顧客が導入・操作するのは WebSpec2Doc だけ。REA・Semgrep・Joern・Schemathesis・MobSF・Ghidra 等は「導入させない・同梱しない・CLI/executable/server として呼ばない・実行時依存にしない」
- 取り込むのはアルゴリズム・データモデル・Evidence 設計・技法・処理フローだけ。OSS コードの複写はせず、公開仕様から独立実装する
- 決定論で解ける処理は AI に逃がさない。AI は意味分類・説明・曖昧候補の補助に限る

分類: **A** Native ／ **B** 言語ライブラリ（pip・同梱 JS 資産）／ **C** OpenAI API ／ **D** Ollama ／ **E** 外部 OSS 製品依存（廃止対象）

## 1. 外部プロセス起動の全量（本体コード 50 か所・tests を除く）

| 起動先 | 呼び出し元 | 分類 | 判定 |
|---|---|---|---|
| 自プロセス（`sys.executable src/main.py`） | crawl・discover・login・record・auto_run_pipeline・job_queue・scheduler・backendtest/runner | A | 適合 |
| **REA 実行ファイル**（rea-agents 6.7.0） | `src/reverse_analysis/rea_adapter.py:384` | **E** | **違反** |
| **`claude` CLI**（Claude Code） | `web/services/healing/agents.py:160-176` | **E** | **違反** |
| **`codex` CLI** | `web/services/healing/agents.py:249-265` | **E** | **違反** |
| **`gh` CLI**（GitHub CLI） | `web/services/healing/github_client.py:60-266`（6 か所） | **E** | **違反** |
| **`npx` / `npm` / `node`**（`@playwright/test` の実行と実行時 `npm install`） | `web/services/playwright_executor.py`（10 か所） | **E** | **違反**（Node.js と npm レジストリが実行時に必要） |
| `npx playwright install`（ブラウザ取得） | 同上 606-648 | E | 違反（閉域で取得不可） |
| `git` CLI | healing/git_ops・localization・project_store・verification、orchestration/onboarding（GitHub から clone） | E | 違反（System 05 の実行時必須） |
| 被試験システムのコマンド | backendtest/codegen_runtime:156・batchtest/codegen:75 | A | 適合（顧客の SUT を試験として実行する機能そのもの） |
| `open`（macOS） | `web/routes/report.py:556` | A | 適合（ローカル利用時の補助。サーバ配備では無効） |
| `pgrep` | `web/services/orchestration/agents/run_agent.py:246` | A | 適合（OS 標準。psutil 等への置換は任意） |
| `mmdc`（mermaid-cli、devDependency） | `scripts/build_delivery_docs.py` | B | 適合（開発時のみ。製品に含まれない） |

## 2. 機能別の監査表

| 機能 | 現在実装 | 依存先 | 実行時必須か | 標準構成で動くか | 閉域構成で動くか | 単一製品要件適合 | 対応方針 |
|---|---|---|---|---|---|---|---|
| クロール・画面抽出 | `src/crawler` | Playwright（pip）＋Chromium | 必須 | 動く | ブラウザ同梱なら動く | 適合（B） | 配布物に Chromium を同梱（パッケージングの課題） |
| UX 検査（a11y） | `src/ux/axe_runner.py` | 同梱 `axe.min.js`（MPL-2.0） | 必須 | 動く | 動く | 適合（B） | 維持 |
| 図・ガイド表示 | `static/vendor/mermaid`・`driver.js` | 同梱 JS | 必須 | 動く | 動く | 適合（B） | 維持 |
| **リバース解析（静的）** | `rea_adapter.py` → REA 実行ファイル | **REA 6.7.0**（`~/.local/share/webspec2doc-tools/rea-6.7.0/bin/rea` または `WEBSPEC2DOC_REA_COMMAND`） | 必須（無いと「導入されていません」） | 管理者が REA を導入した場合のみ | 同左 | **違反（E）** | Native Reverse Analysis へ置換（§4） |
| リバース解析（JS 収集・API 解決・突合） | `reverse_analysis_run.capture_scripts`・`api_resolve.py`・`runtime.py`・`reconcile.py`・`normalize.py`・`reporter.py` | なし | ― | 動く | 動く | 適合（A） | 維持・再利用 |
| 静的 route の到達確認（System 03） | `static_route_probe*` | REA の run.json | REA 経由で必須 | REA 次第 | REA 次第 | 間接違反 | 入力を Native 解析結果へ |
| オートヒーリングの修正エージェント | `healing/agents.py` | `claude`／`codex` CLI、または OpenAI／Ollama エージェント（540・608 行） | 選択制 | CLI を除けば動く | Ollama で動く | **違反（E）**（CLI 2 種） | CLI エージェントを廃止し OpenAI／Ollama に一本化 |
| オートヒーリングの PR 作成 | `healing/github_client.py` | `gh` CLI（一部は urllib で REST） | 必須 | gh 導入時のみ | 閉域 Git ホストは非対応 | **違反（E）** | GitHub REST API（urllib）に一本化 |
| オートヒーリングのリポジトリ操作 | `healing/git_ops.py` ほか | `git` CLI | 必須 | git 導入時のみ | 同左 | 違反（E） | 要判断（下記「要判断」1） |
| テスト自動化の実行（System 02/03） | `playwright_executor.py` | Node.js・npx・`@playwright/test`（実行時 `npm install`） | 必須 | Node 導入時のみ | npm 取得不可で失敗 | **違反（E）** | Python Playwright による Native 実行器へ（要判断 2） |
| LLM 共通クライアント | `src/llm/openai_client.py`（12 モジュールが利用） | OpenAI 互換 API | 任意 | 動く（C） | `WEBSPEC2DOC_LLM_BASE_URL` で Ollama（D） | 適合 | 全 LLM 呼び出しをここへ集約 |
| 画面分類 | `src/llm/screen_classifier.py:27` | `api.openai.com` 直書き | 任意 | 動く | **切替不可** | 部分違反 | 共通クライアントへ |
| 文書対応付けの埋め込み | `docverify/pair/semantic.py:21` | `/v1/embeddings` 直書き | 任意 | 動く | **切替不可** | 部分違反 | 共通クライアント（`impact/engine/embed.py` は切替済み）へ |
| QA 生成 | `web/services/openai_qa.py:12` | `/v1/responses` 直書き（Ollama 非対応 API） | 任意 | 動く | 接続確認のみ切替、生成は不可 | 部分違反 | chat/completions へ寄せ共通化 |
| 観点提案 | `web/services/viewpoint_proposals.py:121` | urllib 直呼び（宛先は未検証） | 任意 | 未検証 | 未検証 | 未検証 | 共通クライアントへ |
| 設定画面・バックエンドテスト・DocVerify | `settings.py`・`backend_test.py`・`docverify/llm_settings.py` | OpenAI／Ollama 選択 | 任意 | 動く | 動く | 適合（C/D） | 維持 |
| reverse_doc 純粋関数 | `web/vendor/reverse_doc` | 自社リポジトリ ma-garin/reverse_doc の写し | ― | 動く | 動く | 適合（A） | 維持 |
| 外部連携（任意） | notifier（Slack）・oidc・各種連携クライアント | 顧客が選ぶ SaaS | 任意 | 設定時のみ | 閉域では無効 | 適合（任意機能） | 閉域では未設定で無効のまま |

## 3. 列挙された OSS の状態

| OSS | 出現箇所 | 状態 |
|---|---|---|
| REA | コード 41・文書 25 | **実行時依存（E）**。§4 |
| Semgrep・Joern・MobSF | 0 | 存在しない |
| Ghidra | 文書 14（`docs/research/reverse-analysis/*GHIDRA*` ほか） | 名前のみ。適合性調査の文書だけで、コードに無い |
| Schemathesis | `web/services/qa/advanced_generator.py:418` | 名前のみ。生成する観点の文言「Schemathesis等の契約テスト候補を提示する」が利用者に OSS 導入を促す |
| ZAP・Lighthouse | `static/mock/system06/sidebar/index.html` | 名前のみ（モックの文言） |
| axe-core | 同梱資産 | ライブラリとして適合（B） |

## 4. REA 依存の全経路

```
[System 01] reverse_analysis_run.capture_scripts  …… 配布 JS を同一ホストから収集（Native）
      ↓ 入力ディレクトリ
reverse_analysis_run.rea_command()  ← WEBSPEC2DOC_REA_COMMAND ／ ~/.local/share/webspec2doc-tools/rea-6.7.0/bin/rea
      ↓ provider_status(): probe_version（--version）
rea_adapter.run_bounded → subprocess.Popen([rea, "analyze-javascript-application", <dir>, "--json"])   ★E
      ↓ stdout（Evidence JSON・6.7.0 契約）→ validate_application_graph（commitment 検証）
normalize.py → api_resolve.py（Native で method・URL を補完）→ runtime.py＋reconcile.py（実測と突合）
      ↓ reporter.py → run.json（snapshot_sha256・provider 版）
web/routes/reverse_analysis.py（/api/.../reverse-analysis、site_evidence）
      ├→ [System 03] static_route_probe（rea_snapshot_sha256 で結果を束縛）・rea_impact_layer・impact.py
      ├→ [System 02] rea_test_viewpoints（ラベル「REA 追加」）・ws-rea-viewpoints.js
      ├→ ta2.py・home_summary・autorun-static-routes.js
      └→ [System 09] Evidence 連携（下流の接続点は未検証）
CLI: src/main.py --reverse-analysis → service.run_reverse_analysis（同じ adapter）
```

REA が担い、Native に移す能力: JS の構文解析（AST）、module・import/export・dynamic import の関係グラフ、endpoint の呼び出し位置、route 宣言（既知のルーターのみ）、source map 参照、node／edge の commitment（`jag_node_`・`ev_` + 正規 JSON の SHA-256）。

既に Native のもの: JS の収集、API の URL・HTTP method の解決（fetch・XHR・axios、3 段のヘルパー）、到達不能コードの除外、runtime の読み込みと突合、正規 JSON・digest（`canonical_json`／`canonical_digest` は自社コードとして再利用できる）、Evidence 状態・confidence・limitation の表現（`models.py`）。

利用者に「REA」が見えている箇所: `reverse_analysis_run.py:101-102`（「静的解析ツール（REA）が導入されていません／管理者に REA 6.7.0 の導入を依頼」）、`static/js/ta2/ws-reverse.js:168`（「利用可能・REA <版>」）、`rea_test_viewpoints.py:161`（「REA 追加」）、`routes/reverse_analysis.py:236`、`service.py:50-55` の制限文。

## 5. Native 化の対象と優先順位

| 順 | 対象 | 理由 | 工数（AI・並列前提） |
|---|---|---|---|
| 1 | Native Reverse Analysis | 製品境界の中心。導入作業が無いと機能が使えない | 3〜5 時間 |
| 2 | LLM 呼び出しの共通化（4 モジュール） | 閉域構成で動かない機能がある | 30〜45 分 |
| 3 | ヒーリングの claude・codex・gh CLI の廃止 | OpenAI／Ollama エージェントと REST が既にあり置換が小さい | 1〜1.5 時間 |
| 4 | テスト実行の Node・npx 依存 | 生成コードの言語に波及（要判断 2） | 2〜4 時間 |
| 5 | git CLI | System 05 の前提（要判断 1） | 判断次第 |
| 6 | 名前のみの箇所（Schemathesis 文言・モック） | 利用者に外部導入を促す文言 | 15 分 |

工数は未計測の見込み（根拠: 置換対象の行数。rea_adapter 1,209 行・reverse_analysis 全体 3,731 行）。既存の実 REA 計測値（`docs/research/reverse-analysis/REAL_REA_VALUE_MEASUREMENT.json`）を Native 実装の比較基準（オラクル）にして、検出件数の劣化を測る。

### Native Reverse Analysis の構成案

- JS 構文解析: 推奨は **acorn（MIT）を同梱資産として、既存の Playwright の Chromium 内で実行**（axe-core と同じ方式。新たな実行時依存なし）。代替は自前のトークナイザ＋限定パーサ（ES2022 の完全対応は重い）
- source map: v3 仕様と VLQ のデコードを自前実装（公開仕様のみ）
- module graph・import/export・dynamic import（`import()` の引数が文字列でなければ「候補」に）、route（React Router／Vue Router／Next の規約を宣言パターンで）、API は既存の `api_resolve.py` を拡張
- Evidence: `models.py` を正本とし、provider を `webspec2doc-native/<VERSION>` に。commitment は既存の digest を流用
- 決定論で解けないもの（意味分類・曖昧な候補の説明）だけを LLM の共通クライアントへ

## 6. 既存の GUI・API・Evidence への影響

- API パス（`/api/sites/<d>/reverse-analysis`・`static-routes/probe`）は維持できる
- run.json の `snapshot_sha256` と、probe 側の `rea_snapshot_sha256` は provider 非依存の名前へ改名し、旧名は読込時に別名として受ける（既存の保存結果を無効にしない）
- 画面: リバース解析画面の provider 表示・未導入時の案内を削除（導入作業そのものが無くなる）。「REA 追加」は「リバース解析で追加」へ
- System 01→03→02→09 の連携は run.json の契約を保てば変わらない。System 09 の接続点は未検証
- 制限文（「method を返さない」「route 宣言が無い」）は Native の実際の能力に合わせて書き直す

## 7. GUI 商用化の再開地点

- **今すぐ再開できる**: リバース解析・オートヒーリング設定・テスト実行設定を除く全画面
- **残りの画面**: 優先順 1 の最初の段「Evidence 契約の provider 非依存化（run.json の改名と別名の読込）」のマージ後。画面が依存するのは契約だけで、解析エンジンの中身ではないため

## 要判断

1. git CLI の扱い: Python ライブラリ（dulwich、Apache-2.0）へ置換するか、「顧客のリポジトリ操作は顧客環境の git を前提」と例外にするか
2. テスト実行: 生成コードを TypeScript（`@playwright/test`）から Python（pytest-playwright）へ切り替えるか。切り替えると System 02 の出力形式が変わる
3. JS 構文解析: acorn の同梱（ライブラリ・B 分類）を許容するか、自前パーサにするか

## 未検証

- 実行による確認は無し（静的読解のみ）
- `viewpoint_proposals.py` の宛先、System 09 の接続点
