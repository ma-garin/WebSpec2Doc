# 単一製品アーキテクチャ監査（2026-10-20・改訂 1）

対象: origin/main `a82e44f`（#314）。コード変更なし。静的な読解（git grep・該当箇所の目視）のみで、実行による確認はしていない。

改訂 1: 製品境界の解釈を保守者の確定ルールに合わせて修正した。「同梱 JS 資産だから適合」とした判定（axe-core・Mermaid・driver.js）と、Chromium・acorn の同梱案を撤回した。

## 0. 確定ルール

| 区分 | 内容 |
|---|---|
| 禁止 1 | 顧客に OSS 製品・CLI・runtime を別途導入させる |
| 禁止 2 | WebSpec2Doc の配布物に OSS 実体を同梱する |
| 許可 3 | 通常の依存ライブラリ（pip でパッケージ管理されるもの）として利用する |
| 許可 4 | OSS の仕組み・アルゴリズム・設計思想を参考に独自実装する |

- 標準構成: WebSpec2Doc + OpenAI API ／ 閉域構成: WebSpec2Doc + Ollama
- 決定論で解ける処理は AI に逃がさない。AI は意味分類・説明・曖昧候補の補助に限る

分類:

| 記号 | 意味 | 扱い |
|---|---|---|
| A | WebSpec2Doc Native | 維持 |
| B | 通常の依存ライブラリ（pip。配布物にファイルとして含めない） | 許可 |
| C | OpenAI API | 許可（標準） |
| D | Ollama | 許可（閉域） |
| E | 外部製品依存（別途導入させる CLI・runtime・外部 CDN） | 廃止 |
| X | 同梱 OSS 実体（リポジトリ・配布物にコピーした OSS ファイル） | 廃止 |

判断の線: **パッケージ管理（pip）で解決される依存は B。リポジトリに OSS のファイルを置くのは X。顧客の PC に別のソフトを入れさせる・外部から実行時に取得するのは E。**

## 1. 要件違反一覧

| # | 違反 | 分類 | 箇所 |
|---|---|---|---|
| V1 | REA 実行ファイルを起動 | E | `src/reverse_analysis/rea_adapter.py:384`、導入先 `~/.local/share/webspec2doc-tools/rea-6.7.0/bin/rea` |
| V2 | `claude` CLI を起動 | E | `web/services/healing/agents.py:160-176` |
| V3 | `codex` CLI を起動 | E | `web/services/healing/agents.py:249-265` |
| V4 | `gh` CLI を起動 | E | `web/services/healing/github_client.py:60-266`（6 か所） |
| V5 | `git` CLI を起動 | E | healing/git_ops・localization・project_store・verification、orchestration/onboarding |
| V6 | Node.js・npm・npx を要求し、実行時に `npm install @playwright/test` | E | `web/services/playwright_executor.py`（10 か所） |
| V7 | Playwright のブラウザ実体を実行時に取得（`playwright install`） | E | `playwright_executor.py:606-648` ほか導入手順 |
| V8 | 生成レポートが Mermaid を CDN から読み込む | E | `src/generator/html_reporter.py` ほか（`cdn.jsdelivr.net/npm/mermaid@10.9.x`）。閉域では図が出ない |
| V9 | axe-core を同梱 | X | `src/ux/assets/axe.min.js`（MPL-2.0） |
| V10 | Mermaid を同梱 | X | `static/vendor/mermaid/mermaid.min.js`（MIT） |
| V11 | driver.js を同梱 | X | `static/vendor/driver.js/`（MIT） |
| V12 | ショーケースに V10・V11 の写し | X | `pages/app/static/vendor/`（GitHub Pages 用。配布物から外せば解消） |
| V13 | 利用者に外部 OSS の導入・名前を見せる文言 | 文言 | REA の導入依頼（`web/services/reverse_analysis_run.py:101-102`）、「利用可能・REA <版>」（`static/js/ta2/ws-reverse.js:168`）、「REA 追加」（`web/services/rea_test_viewpoints.py:161`）、「Schemathesis等の契約テスト候補」（`web/services/qa/advanced_generator.py:418`） |
| V14 | 閉域で OpenAI から切り替えられない LLM 呼び出し | 構成 | `src/llm/screen_classifier.py:27`、`web/services/docverify/pair/semantic.py:21`、`web/services/openai_qa.py:12`（responses API）、`web/services/viewpoint_proposals.py:121`（宛先は未検証） |

## 2. 通常の依存ライブラリとして許可されるもの（B）

`requirements.txt` の実行時依存。いずれも pip で解決され、配布物に実体を含めない。

| ライブラリ | 用途 | 注記 |
|---|---|---|
| playwright | クロール・画面操作 | 保守者判定で許可。ライブラリ内部に Node ドライバを持つが規則 3 の範囲。ブラウザ実体の取得は V7 |
| networkx | グラフ処理 | |
| jinja2・flask | Web UI | |
| openpyxl・python-docx・pypdf・pdfminer.six | 文書の読み書き | |
| PyYAML・defusedxml | 設定・XML の安全な読込 | |
| Pillow・numpy | 視覚複雑度の計測 | |
| python-dotenv・prometheus-client・Authlib | 設定・メトリクス・SSO | |
| psycopg[binary] | System 08 の PostgreSQL 接続 | LGPL-3.0。要法務確認（`THIRD_PARTY_NOTICES.md` の既存の注記） |
| Faker | System 08 のテストデータ生成 | |

- 開発時だけのもの（配布物の外）: pytest 系（`requirements.txt` に混在しているので dev 側へ分離が望ましい）、npm の devDependencies（mermaid-cli・jsdom・vitest）。顧客の環境には不要
- `web/vendor/reverse_doc` は自社リポジトリ（ma-garin/reverse_doc）の写しで、OSS 実体ではない（A）

## 3. 外部製品依存として廃止すべきもの（E）

| 依存 | 現在の役割 | 置換先 |
|---|---|---|
| REA（V1） | JS の静的解析 | Native Reverse Analysis（§5） |
| claude・codex CLI（V2・V3） | ヒーリングの修正エージェント | 既存の OpenAI／Ollama エージェント（`agents.py:540・608`）に一本化 |
| gh CLI（V4） | PR 作成 | GitHub REST API（`github_client.py:296` に urllib 経路が既にある） |
| git CLI（V5） | 顧客リポジトリの操作 | pip のライブラリ（dulwich、Apache-2.0）＝ B。worktree 相当の操作への対応は未検証 |
| Node・npm・npx（V6） | 生成テストの実行 | Python Playwright による Native 実行器（要判断 1） |
| ブラウザの実行時取得（V7） | クロールの実行環境 | 顧客 PC にある Chrome／Edge を Playwright の `channel` で使う（要判断 2） |
| Mermaid の CDN（V8） | レポートの図 | Native の SVG 描画（§5） |

## 4. 同梱している OSS 実体（X）

| ファイル | OSS | 使用箇所 | 置換先 |
|---|---|---|---|
| `src/ux/assets/axe.min.js`＋LICENSE・ASSET.md | axe-core（MPL-2.0） | `src/ux/axe_runner.py`（UX 検査） | Native のアクセシビリティ検査（要判断 3） |
| `static/vendor/mermaid/` | Mermaid（MIT） | 解析 HTML の図（`static/js/view-transition.js` ほか） | Native の SVG 描画 |
| `static/vendor/driver.js/` | driver.js（MIT） | 初回ガイド（`static/js/onboarding.js`・`templates/index.html`） | Native のガイド部品 |
| `pages/app/static/vendor/` | 上 2 つの写し | GitHub Pages のショーケース | 本体の置換に追従。ショーケースは配布物から除外 |

ほかに OSS 実体の同梱は無い（LICENSE・ASSET.md・`*.min.js`・`vendor/`・フォント・wasm を全量で照合。tests・docs・demo を除く）。

## 5. Native 化の対象

| 順 | 対象 | 違反 | 工数（見込み） |
|---|---|---|---|
| 1 | Native Reverse Analysis | V1・V13 | 4〜6 時間 |
| 2 | LLM 呼び出しの共通化（4 か所） | V14 | 30〜45 分 |
| 3 | ヒーリングの外部 CLI 廃止（claude・codex・gh・git） | V2〜V5 | 1.5〜2.5 時間 |
| 4 | 生成テストの実行を Python Playwright へ | V6 | 2〜4 時間 |
| 5 | ブラウザの実行時取得をやめる | V7 | 1 時間 |
| 6 | Native のアクセシビリティ検査 | V9 | 3〜5 時間 |
| 7 | Native の図描画（同梱と CDN の両方） | V8・V10 | 3〜5 時間 |
| 8 | Native のガイド部品 | V11 | 1 時間 |
| 9 | 名前・導入を促す文言の削除 | V12・V13 | 15 分 |

工数は未計測の見込み（根拠: 置換対象の行数。`rea_adapter.py` 1,209 行・`src/reverse_analysis` 全体 3,731 行）。

### 5.1 Native Reverse Analysis

- **JS 構文解析: 自前の字句解析＋限定構文解析**（acorn 同梱案は撤回）。必要な構文は import／export／`import()`／`require()`／呼び出し式（fetch・XHR・axios）／route 宣言の型だけで、完全な AST は要らない。文字列・テンプレート・正規表現リテラル・コメントを正しく読み飛ばす字句解析器が核になる。既存の `api_resolve.py` は同じ方針（原文の静的読解）で動いているので、それを土台に広げる
- source map: v3 の公開仕様と VLQ のデコードを自前実装
- module graph: ファイル→module→import/export の有向グラフ（networkx＝B）。dynamic import の引数が静的文字列でなければ「候補」とし、confidence を下げる
- route: React Router・Vue Router・Next.js の規約を宣言パターンで認識する。規約外は limitation として明示する
- API・HTTP method: `api_resolve.py` を拡張。method は REA に無かった能力で、既に Native
- Evidence: `src/reverse_analysis/models.py` を正本にする。provider を `webspec2doc-native/<VERSION>` とし、commitment は既存の `canonical_json`／`canonical_digest`（自社コード）を使う
- runtime の突合: 既存の `runtime.py`・`reconcile.py` をそのまま使う
- 比較の基準: 実 REA の計測値（`docs/research/reverse-analysis/REAL_REA_VALUE_MEASUREMENT.json`）と件数を突き合わせ、Native が下回った種類を limitation に記録する
- AI の出番は、意味分類と曖昧な候補の説明だけ

### 5.2 そのほか

- アクセシビリティ検査: WCAG 2.2 の達成基準のうち、DOM と計算済みスタイルから決定論で判定できるもの（コントラスト・代替テキスト・ラベル・見出しの順序・ランドマーク・フォーカス可能性 等）を Playwright 経由で Native 実装する。axe と同じ網羅性は目指さず、対応範囲を limitation として明示する
- 図: `mermaid_generator.py` が作る図の種類（画面遷移・構成）に絞り、階層レイアウト（Sugiyama 法）で SVG を直接出力する
- ガイド部品: 強調枠と吹き出しだけの小さな部品として自作する

## 6. 既存の GUI・API・Evidence への影響

- API パス（`/api/sites/<d>/reverse-analysis`・`static-routes/probe`）は維持できる
- run.json の `snapshot_sha256` と probe 側の `rea_snapshot_sha256` は provider に依存しない名前に変え、旧名は読込時に別名として受ける（既存の保存結果を無効にしない）
- 画面: リバース解析の provider 表示と未導入時の案内は削除する（導入作業そのものが無くなる）
- 生成レポート: 図の出力が Mermaid のテキストから SVG に変わる。PDF 出力も同じ経路
- UX 検査: 指摘の rule id が axe から Native の id に変わる。過去の結果との比較には対応表が要る
- System 01→03→02→09 の連携は run.json の契約を保てば変わらない。System 09 の接続点は未検証

## 7. GUI 商用化の再開地点

- **今すぐ再開できる**: リバース解析・オートヒーリング設定・テスト実行設定・初回ガイド・UX 検査結果・図を含むレポート表示を除く全画面
- **残りの画面**: 該当する Native 化（順 1・3・4・6・7・8）の「出力契約の確定」段のマージ後。画面が依存するのは出力の契約で、エンジンの中身ではない

## 設計決定（2026-10-20 保守者確定）

本番で許可: WebSpec2Doc 自身の実装／requirements 等の通常依存ライブラリ／OpenAI API／Ollama／顧客環境に既にある Chrome・Edge。
禁止: 外部 OSS 製品・CLI・runtime の別途導入／OSS のコード・バイナリの vendor 同梱／外部解析製品の runtime 呼び出し／Node・npm・npx の runtime 前提／CDN の runtime 依存／実行時ダウンロード。
REA・axe-core・Schemathesis 等は、開発・研究・精度比較用のオラクルとしてのみ使ってよい（製品の runtime 依存にしない）。

1. **System 02**: 製品内で実行する正式な形式は Python Playwright。TypeScript Playwright は成果物のエクスポートとして残し、generated／not executed／not verified を区別して表示する。Node・npm・npx の自動導入は禁止
2. **ブラウザ**: Python Playwright から、顧客環境にある Google Chrome／Microsoft Edge を自動検出して使う。見つからなければ成功扱いにせず `BLOCKED / browser unavailable` と明示する。実行時ダウンロードとインストーラでの取得は禁止
3. **Accessibility**: vendor 同梱の axe-core は runtime から除去する。対応する WCAG／ACT の観点を先に定義し、対象ルールについて Native と axe-core（開発時のオラクル）を fixture と実サイトで比較する。未実装のルールは明示し、PASS 扱いにしない。「axe より少なくてよい」とはしない
4. **JS 解析**: パーサを自作する前に、pip で管理できる JavaScript パーサライブラリ（tree-sitter 系など）を調査する。条件は、vendor コピーしない・runtime で外部 CLI／server を起動しない・商用利用可能なライセンス・import／export／`import()`、fetch／XHR／axios、route 宣言、source location を取得できること。条件を満たすものがあれば使う。完全なパーサの自作は最後の手段（§5.1 の自作方針はこれで置き換える）

## 未検証

- 実行による確認は無し（静的読解のみ）
- `viewpoint_proposals.py` の宛先、System 09 の接続点、dulwich の worktree 対応
