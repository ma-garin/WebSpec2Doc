# REA / Ghidra FIT ANALYSIS — Phase 1

調査日: 2026-10-19（Asia/Tokyo）。Phase 0は利用者承認済み。
結論: **WebのローカルJS/source map解析と独立した根拠JSONを最初のGO候補とする。**
Playwrightとの突合には別途WebSpec2Doc側の設計が必要。Ghidraは導入しない。
本書のGOは次工程で計画する価値があるとの判断であり、実装開始・採用確定・動作保証ではない。
コード・依存・設定は変更せず、REA/Ghidraをインストール・実行せず、Claude Codeも起動していない。

## 1. 前提・調査範囲

正本: [CURRENT_STATE.md](CURRENT_STATE.md)。ローカルHEAD `c0da96a` に対するPhase 0の理解を継承する。

- 01 appはfixtureベース。実APK/.appの解析や実機探索を行っていない。
- API runtime観測は既存。API recoveryは関数・テストあり、標準製品経路への結線は未確認。
- 08はtarget_kind=batch。任意API/native対象を扱える前提にしない。
- 09には文書リンクBFS・類似度・risk/test selectionが既にある。
- 指揮はdocs/tests/run/healing中心。06〜09の全自動連結とは扱わない。
- JS source location/source map/module依存/native symbol/xrefの統一表現は現行にない。
- static candidateとruntimeの統一突合経路は未確認。

評価の最優先基準は「既存では取得できなかったQA上有用なEvidence/仕様情報が増えるか」。
重複取得、ツールの存在、星数、機能一覧の長さは価値として数えない。

調査手段: 公式GitHub APIで版・treeを取得し、固定commitの公式docs/sourceを読取。
検索結果は公式への入口にのみ使用。コマンドのglob未一致・誤パスは再実行で修正し、不在判定に使わない。
対象を動かす実験・性能計測は未実行。以下のコスト・価値はコードと公式契約に基づく評価である。

## 2. 最新版と一次情報の固定

### REA

GitHub最新release APIとnpm latestの双方で **rea-agents 6.7.0** を確認。
公開日時は `2026-10-18T07:45:18Z`。調査mainは
`3ea0d9489e52500ed76555926f1b78419f71c3cb`。
packageのNode条件は `^22.19.0 || ^24.11.0 || >=26.0.0`。
REA本体はMIT、外部provider・同梱第三者素材は別ライセンスを確認する。[R1][R2][R3]

mainとreleaseを別取得して比較した。JS artifact、application graph、runtime reconciliationの
資料は取得時点で一致。browser docsはmainにsource取得・解析の追加リソース境界記述があり、
workflow docsには追加の意味解析の注意、Android docsには検証手順の追記がある。
**mainの説明を全て6.7.0で保証される機能とは扱わない。**
特にbrowser解析のmain追記の上限値を公開版の保証に使わない。

### Ghidra

公式latest stableは **12.1.4**、tag `Ghidra_12.1.4_build`、
公開 `2026-09-21T17:38:59Z`、commit `8b6bbb857accdfa20dc5b2f5dea471178c2e9fbc`。
stableのJava最小版は21。masterの開発版12.2/JDK25とは区別する。
Ghidra本体はApache-2.0。REA側は12.1.xを受け付け、12.1.4/JDK21の検証を記載する。[G1][G2][G3][G4]

Ghidra本体はWindows/Linux/macOSを対象とするが、配布native部品はhost/architectureで異なる。
macOS x64/ARM64等ではnative部品のbuildが追加負荷となる。REA providerのhost条件は
さらに別の制限で、Windows x64はexperimental P0。headlessのJava scriptから抽出できるが、
Ghidra単体でREAと同じ共通JSON契約が得られるとは確認していない。[G4][G5][G8]

### アーキテクチャ

REAはCLI/MCPを共通application workflowへ接続し、domainのEvidence/graphと
ブラウザ・JS解析・JADX・Ghidra等のproviderを分離する。静的JSにはnative解析エンジン不要。
MCPのsetupはagent設定を変更するため本件では実行しない。将来もCLIを使う案ならMCP登録は不要。[R3][R4][R5]

## 3. 判定と評価尺度

- GO: 追加価値に根拠があり、範囲を絞って次工程の計画候補にする。
- LATER: 価値はあり得るが、対象・識別子・実行基盤・受入基準等の前提が不足。
- NO-GO: 今回の目的で重複だけになる、または根拠と主張が衝突する案。
- 高/中/低は相対評価。費用・所要時間・RSSの実測値ではない。
- 実装費はadapter/正規化/出典/検証を含む。実行費は追加プロセス・解析量・観測時間。
- 保守負荷は上流schema/provider/OS/版への追随。Security欄は追加の境界設計負荷。

### 能力別のコスト

| 能力ID | 実装費 | 実行費 | 導入負荷 |
|---|---|---|---|
| 1 CDP追加 | 中 | 中 | 中 |
| 2 JS/bundle | 中 | 中〜高 | 低〜中 |
| 3 source map | 中 | 低〜中 | 低〜中 |
| 4 route/API候補 | 中 | 中 | 低〜中 |
| 5 graph | 中→高 | 中〜高 | 低〜中 |
| 6 reconciliation | 高 | 中 | 中 |
| 7 APK/JADX | 中〜高 | 中〜高 | 高 |
| 8 native/Ghidra | 高 | 高 | 高 |
| 9 Evidence変換 | 中 | 低〜中 | 低 |
| 10 CLI/JSON | 中 | 低＋解析費 | 低〜中 |

JSはNode/REAを要し、JDK/Ghidraを要しない。APKはJDK/JADX、実機はさらにadb/端末、
nativeはJDK/GhidraとOS別native部品を要する。この違いが取り消し・運用コストを左右する。

### 安全性・保守・適合

| 能力ID | 安全境界負荷 | 保守負荷 | 判定 |
|---|---|---|---|
| 1 CDP追加 | 高 | 中〜高 | LATER |
| 2 JS/bundle | 中 | 中 | GO |
| 3 source map | 中 | 中 | GO |
| 4 route/API候補 | 中 | 中 | GO |
| 5 graph | 中 | 中〜高 | GO / LATER |
| 6 reconciliation | 高 | 高 | 条件付きGO |
| 7 APK/JADX | 高 | 高 | 静的GO・実機LATER |
| 8 native/Ghidra | 高 | 高 | LATER |
| 9 Evidence変換 | 中 | 高 | GO |
| 10 CLI/JSON | 中 | 中〜高 | GO |

## 4. 能力別比較

### 1. REA Browser / CDP

- 現行/重複: PlaywrightのDOM・フォーム・スクリーンショット・XHR/fetch・SPA状態探索。
  これを二重取得する案は **NO-GO**。
- 追加候補: 読み込まれたscriptの位置・ソースdigest、network initiator位置、worker/frame、
  WebSocketの観測メタデータ。QA上は「どの配布コードが観測中に存在したか」の追跡に有用。
- REAはattach型で、literal loopback CDPと厳密origin許可を要求する。
  現行Playwrightの通常起動がREAの必要なdiscovery endpointを持つとは限らない。[R6]
- 適用: 01/02、将来09。全面置換はNO-GO、追加項目だけの取得はLATER。
- 負荷理由: ブラウザ起動方式・認証状態・観測窓・mutation遮断を共有する設計が必要。
  passiveであってもCDP接続が既存の安全制御を継承する保証はない。
- Security: REAのURLはquery/fragmentを保存し得る。現行の監査URL短縮と同等ではない。
  token・PII・ソースの秘密を保存前に扱う方針が必要。保守はCDPとbrowser版の差が支配する。

### 2. JavaScript / bundle analysis

- 現行/重複: DOM解析・技術stack推定はあるが、JS AST/moduleの統一抽出は確認されていない。
- 新規情報: JS/TS、directory/ASAR、Webpack/Rspackのchunk/module factory、import/require、
  worker、静的request等の位置付き事実をartifact digestと共に保持できる。[R5][R7]
- QA価値: 実測で未到達の分岐・候補の探索計画、テスト不足の仮説、コード位置への追跡。
  完全な業務仕様復元や全bundle形式への対応とは扱わない。
- 適用: 01/02/04、将来09。**GO**、ローカル提供artifactを最初に限定する。
- 実装/運用: 子プロセス・版検証・JSON取込・出典変換が必要。標準でsourceごとの解析deadline
  300000msとV8 old-space 1024MiBが記載されるが、所要時間/RSSの実測値ではない。[R5]
- Security: 解析は対象JSを実行しないがparser/ASAR/圧縮/巨大ASTの境界が残る。
  保守は対応構文・bundle形式・graph schemaの変更が中心。
- 別機能のWakaru source recoveryはLinux x64・外部engine等の追加負荷があるためLATER。
  source map解析や通常AST解析と混同し、最初から必須化しない。[R8]

### 3. source map解析

- 現行: 統一モデルなし。追加はmapの宣言、配布物と原ソース候補の対応、原ソース名・digest・位置。
- REAはlocal mapの取込と、Web側の許可範囲でのmap取得を分ける。
  SourceMapFormatはv3のmappings/sourcesContent/sourceRoot・indexed sectionを検査する。[R5][R9]
- QA価値: bundle中の候補をレビュー可能な原ソース位置に戻せる場合がある。**GO**。
  最初は提供済みlocal mapのみ。HTTP取得・認証付きsource取得はLATER。
- 適用: 01/02/04、後で09。map欠損・null sourcesContent・malformed・stale mapは明示。
- Security/保守: traversal、別origin fetch、巨大data URL、private source流出に注意。
  digest付き原ソースの存在もgenerated bytesとの意味的等価性の保証ではない。
  mapなしで原ソースや元変数名を断定する案はNO-GO。[R8][R9]

### 4. route / endpoint candidate抽出

- 現行: リンク/SPA遷移/実測APIはある。未実行JS内のcall site候補は別の追加情報。
- REAはAST構文上のroute/request/RPC候補を返し、動的targetをpartialとして式と位置を保つ。
  文字列だけを実在API仕様や到達可能routeへ昇格させない。[R5][R7]
- QA価値: 未観測候補の追加探索・テスト分析の仮説。適用01/02/04、将来09。**GO**。
- 実装費: method/origin/path/動的部分/出典/coverageの正規化と重複判定が必要。
- Security/保守: 候補を自動アクセスしない。GETでも副作用がない保証はない。
  URL parameterizationやtemplate展開の誤結合がリスク。frameworkの抽出規則に追随する。

### 5. application / module graph

- 現行: 01の画面遷移graph、09の文書リンクBFSは既存。graph探索自体の再実装はNO-GO。
- 新規: artifact→asset/chunk/module→endpoint/source map、位置・authority・digest付きの辺。
  REA Application Graphは副作用のないdomain contractであり、それ自体が取得ツールではない。[R7]
- QA価値: 画面/テストとmodule/APIの間を説明する材料。01/02向け保持はGO。
  **09へ直接投入する段はLATER**。文書項目IDとコード実体IDの対応が未成立。
- Security/保守: 巨大graphの保存上限とschema検証が必要。REA内部domainを全コピーせず、
  出典リンクを保持した小さな交換契約を検討する。schema変更のadapter負荷は中〜高。

### 6. runtime/static reconciliation

- 現行: 文書×実測のfuseは既存。ただしJS static/runtime照合は未確認。
- REAの標準機能はartifact位置・digest・capture等からmatch/ambiguous/mismatch/unknownを返す。
  matchedでもcross-layerの辺はinferredのまま。loadedは機能実行やAPI因果を証明しない。[R10]
- **重要制約**: 入力はREA特定operationのEvidence。provider/operation/predicate/authority/
  digest/schemaを検査するため、WebSpec2Doc PageDataをそのまま渡すことはできない。
  検査コードassertEvidenceIdentityでも確認した。[R10][R11]
- 追加QA価値: 「このsource候補とこの観測が同一か/曖昧か」を出典付きで区別できる。
  適用01/02、将来09。**目的は条件付きGO、REA標準突合の直接流用はLATER**。
- 最初の代案: WebSpec2Doc自身の出典契約で限定的に候補とAPI観測を比較する。
  method+明示origin+厳密path等を使い、多対多・動的式はambiguous/unknown。
  これは独自の候補対応推論であり、REA標準のscript同一性照合やcall-site因果証明と呼ばない。
- Security/保守: runtimeをREA由来と偽装しない。単なるoperation名差し替えはNO-GO。
  正確なscript identityが必要なら、別途選択的CDP観測を計画してから進める。

### 7. Android APK / JADX / 実機

- 現行: 01 appはモック。APK digest、Manifest宣言、SDK/permission、Activity/deep link候補、
  class/method/referenceは実物から増やせる新しい情報。
- REAはheadless JADXを包み、入力APK・engine JARのdigestと結果・制限を保持する。
  呼び出し先はjadx-headless-mcp **0.7.1**。この番号はJADX本体の版ではない。[R12][R13]
- full JDK17+、Linux/macOS/Windows x64のprovider条件。Windows ARM64は対象外。
  最新メタデータbridgeの実検証hostは資料上限定され、全OSで同じ保証とはしない。
- **静的APK分析はGO**、01 app/04の独立候補。ただし初回Web sliceに同梱しない。
  JADXのJava逆コンパイルはderived、参照は静的であり実行済みActivityやruntime dispatchではない。
- **実機探索はLATER**。REA ADBは端末/画面/ログ/パッケージ取得・明示install等を提供するが、
  emulatorの起動管理やtap/type/monkeyによる探索は別lane。これだけでappモック置換は完結しない。[R14]
- layout/Navigation/Fragment/WebView/endpointの統一抽出、01の画面モデルへの変換、
  iOS .app探索は今回確認できていない。Manifest宣言を「未到達Activity」と断定しない。
- GhidraはManifest/DEX/JADXに不要。JNI .soの具体的問いが出た時のみ別評価。
- ライセンス: JADXとjadx-headless-mcpはApache-2.0を公式LICENSEで確認。
  Android platform-tools/SDK/imageの利用条件は別で、同梱可否は未確認。[R13][R15]
- Security/保守: 不正APK parser、zip展開、private source、端末への副作用、JDK/bridge/adb版が追加負荷。
  静的解析はAPKを実行しない。install/uninstallと実機操作は明示権限を別管理する。

### 8. native / Ghidra

- 現行: 統一symbol/xrefなし。増える情報はアドレス・symbol・参照・call/CFG・逆コンパイル。
- Ghidraはheadless、pre/post script、timeout/readOnly/max-cpu等を持つ。
  REAは一時projectでproviderを起動し、decompile/symbol/calls/typed xrefs等をEvidence化する。[G4][G5]
- ELF/PE/Mach-O等の対応はGhidra本体とREA providerのadmissionを区別する。
  Windows REAはexperimental P0・読取中心。Linux/macOSと同等とは主張しない。[G4][G6]
- QA追加価値はnative対象の具体例があればあるが、今回のWeb/DEX目的では必要性が未証明。
  **LATER、現在は導入しない。必須依存化・Web標準経路への常時起動はNO-GO。**
- 適用候補は将来の01 app/JNI、Electron addon、09 native依存。08はbatchのままで、
  native targetが登録可能とは扱わない。
- 初回import/autoanalysis、JDK、OS別native部品が高負荷。REA設定上startup330000ms、
  JVM maxheap2Gは上限/既定であり実測時間・RSSではない。[G4]
- Security: 一時project/private transportはsandboxではない。provider parserは利用者権限で動く。
  静的call/CFGを業務意味やruntime実行と断定しない。保守費はOS/JDK/Ghidra/REAの組合せに依存。[G6][G7]

### 9. REA Evidence・epistemic state

- 現行: SourceEvidence/DocumentEvidence、実測confidence、08 confirmed、09 score等がある。
- REA envelopeのconfidenceは **observed/derived/inferred** の文字列。
  graph観測のstateは **observed/inferred/unknown/unavailable**、confidenceは別尺度。
  match/ambiguous/mismatchは照合分類であり、このstateと同じenumではない。[R7][R16]
- 新規価値: authority・artifact digest・source/runtime位置・extractor/version・coverage/
  limitation・Evidence linkを維持し、仕様化できる範囲を明示できる。01/02/04/将来09にGO。
- 数値confidence=1.0へ一律変換する案はNO-GO。matchedだからobservedへの昇格もしない。
- 実装/保守: 別のreverse evidence出力で元の意味を保ち、既存型への破壊的統合を避ける。
  内容digestの検証はproducerの電子署名ではなく、runtime主張の真実性を自動保証しない。

### 10. 自動化・CLI・machine-readable output

- 現行CLI/APIあり。別GUI・MCPを先に作る価値は低い。
- REAはCLIとMCP共通workflow、JSON/Evidence export等を持つ。terminal既定TOONを
  JSONと誤認せず `--json` を使う。stdout結果とstderr進捗を分ける。[R4][R5]
- 終了0でもpartial/warnings/unknownがあり、exit codeだけを合格扱いしない。
- CLI opt-in adapterはGO。System04から01/02用の独立出力を扱う。03/指揮への接続はLATER。
- Security/保守: argv、絶対実行パス、版固定、timeout/中止、stdout/stderr/JSONサイズ上限、
  一時artifact、malformed/missing-provider/schema mismatchを明示処理する必要がある。
  自動update/setupを製品経路で実行しない。依存不在時も既存機能は保持する。

## 5. 重点A: Web bundle/source map + Playwright

優先度1。追加価値はartifact/source/moduleと候補の根拠であり、既存DOM/networkの取り直しではない。

比較案:

| 案 | 新規価値 | 損益 | 判定 |
|---|---|---|---|
| DOM/network全面置換 | 小 | 重複・移行費大 | NO-GO |
| local静的＋限定突合 | 高 | 追加依存限定 | GO |
| REA CDPも常時取得 | 中〜高 | 安全境界追加 | LATER |

推奨: local directory + source map + 既存snapshot/API観測の限定対応付け。
report.jsonはAPI観測を全て直列化しないため、reportだけを突合入力にすると欠測する。
API復元の既存出力確認/結線とsnapshot読取のどちらを使うかを次工程で決める。
REA native reconciliationとWebSpec2Doc独自対応付けを区別する。

source mapなしでも配布JSの位置・digest・候補を出せる設計にし、原ソース位置はunknown。
source mapあり時の追加価値も別に数える。loaded assetから内包module実行を断定しない。

## 6. 重点B: System01 app

| 選択肢 | 得られるもの | 未充足 | 判定 |
|---|---|---|---|
| 現行fixture | デモ成果物 | 実APK根拠 | 維持 |
| REA/JADX | Manifest/DEX根拠 | 実画面操作 | 静的GO |
| 実機探索基盤 | 画面・操作の実測 | 導入・端末制御 | LATER |
| Ghidra | JNI等のnative根拠 | 対象の必要性 | LATER |

静的APK inventoryはモックより明確な前進。ただしその成果物を実機画面仕様と称さない。
ADBは取得・状態観測の補助で、画面探索engineの代替とはならない。
直接JADX CLIも比較対象: adapterが単純になり得る一方、REAのartifact-bound Evidence/制限/JSON契約の
再実装が必要になる。どちらが安いかの実測は未実施で、REA必須との結論は出さない。

## 7. 重点C: System09への依存Evidence追加

優先度はAの後。既存BFS/risk/test selectionを再実装しない。

```text
変更要求・文書項目
  → 人が確認した文書項目↔画面/module対応
  → artifact版付きmodule/import/endpoint関係
  → 既存09の影響候補・リスク・関連test選択
```

追加するならリンク元Evidence・版・方向・関係種別・stateを保持し、文書上の関係と
静的依存推論を同じ確定辺に潰さない。依存追加でBFS候補が増えた件数だけを価値にしない。
手作業の正解セットで、新しい有用影響/誤警告/テスト不足の発見を比較する必要がある。

**LATER**。module/APIから文書item_id/testcase codeへの対応と、変更前後artifactの同定が先。
対応がない状態でgraphを全部投入する案はNO-GO。放置の損は見落としだが、誤結合による
影響候補の洪水は優先度判断を悪化させるため、段階導入が妥当。

### System全体への適用範囲

- 01/02/04: Aの主対象。01 appはBの独立した静的APK候補。
- 03: inferred候補を段階承認へ流す条件を定義するまではLATER。
- 05: source/module位置を修正根拠へ使うには実行結果との対応確認が必要でLATER。
- 06: 文書出典と静的出典は区別して保つ。REAで文書検査を置き換える理由はない。
- 07: 既存scriptの規則抽出と重複。JS/native用途が成立するまでREA追加はLATER。
- 08: batchの現行対象を維持。REA導入のためだけのtarget種別拡張はNO-GO。
- 09: Cの識別子対応・有用性実証後にLATERを再評価。
- 指揮: 新しいadapterを最初からdocs/tests/run/healingへ組み込む案はLATER。

## 8. REA不要で先に確認・改善する点

1. **API recoveryの結線確認**。recovery.pyのbuild_screen_api_map/build_openapi_draftは既存。
   API観測→生成→保存→利用者が読める成果物を通す改善は、新解析engineなしで可能な候補。
   関数・テストはあるが製品結線が未確認というPhase0結論を維持し、未実装と決めつけない。
2. **APIの受け渡し契約**。PageData/snapshotとreport.jsonで保持範囲が違う。
   新しいparserを入れる前に、観測が下流へ落ちない経路と出典を確認する。
3. **承認/未確認の扱い**。AutoRunのtimeout継続と新しいinferred候補を混ぜない。
   inferredを自動承認する既存条件への投入は別の受入判断が必要。

これらは「既存データを利用可能にする価値」。REAの「従来取れなかった情報を増やす価値」と別計上する。
本Phaseではどれも修正していない。

## 9. 最初のvertical slice候補

**候補: opt-inのlocal JS/source map解析 → 候補と出典のJSON → 既存API観測との限定対応付け。**
先にAPI recoveryの既存結線確認を行い、その結果をruntime入力の選定に使う。

```text
利用者提供のlocal JS directory / source map
  → 固定版REA analyze-javascript-application --json
  → artifact/module/source location/route/API candidateを検証
既存PageData snapshot/API観測
  → scopeを維持した最小観測データ
両者 → WebSpec2Doc独自の限定対応付け
  → reverse_analysis.json（report.json/OpenAPIとは別）
```

これは計画候補。実装仕様・ファイル名の確定・CLAUDEへのタスク化はPhase2で行う。
REA標準reconcileを使いたい場合は、REA CDP Evidence取得を含む別案として安全性/費用を再評価する。

### 増やすEvidence

- artifact SHA-256・版・相対ファイル位置とsource range。
- source mapの宣言・map/original source digest・位置（取得できた場合）。
- module/import/chunk関係と、route/endpoint候補のcall site・解決状態。
- 候補と既存API観測の関連付け根拠、候補だけのinferred、競合のambiguous、欠測のunknown。
- coverage/truncation/limitations、producer版と元Evidenceへの参照。

**増やさない主張**: 未観測APIの必須/エラー仕様、未到達routeの実在確定、
moduleの機能実行、source mapによるソース等価性、API呼出の因果証明。

### 想定変更範囲（未着手）

- srcの独立adapter・出力/候補モデル・限定対応付け・JSON writer。
- CLIの明示opt-in入口、既存snapshot読取、出力schema/feature contractと受入テスト。
- 既存SourceEvidence/report.json/snapshotのスキーマは無条件拡張しない。
- UI、MCP登録、Android、Ghidra、09 DB、healing、指揮の接続は初回範囲外。
- 実際の対象ファイル・実装見積はPhase2で確定。現時点で作成/変更していない。

### 次工程で必要な価値実証

同じcontrolled fixtureでBefore/Afterを比較する。最低限:

- 未実行route/API候補を持つartifactで、根拠付きの有用新規発見が1件以上。
- 候補だけの情報を既存observed API/OpenAPIへ混ぜず、観測件数を水増ししない。
- 同一URL異method・別origin・動的式・重複候補・stale/missing mapを安全に区別する。
- providerなし/timeout/中止/不正JSON/上限超過の結果が未確認として見える。
- feature OFFの既存出力hash・観測結果が変わらない。
- wall time、追加秒、peak RSS（測定可能時）、artifact/output bytes、候補数、有用発見数、
  誤警告数を記録。**今回の実測値はすべて未取得**。
- 追加有用情報0件なら価値ゲート不合格。対象不適切なら理由を残し、成果を捏造しない。

## 10. リスク・未確認・停止位置

- REAのJSON/schemaは変化が速い。6.7.0の固定契約とmainの差を継続的に区別する必要。
- JS難読化・eval・動的routing・signed URLはunknown/partialを増やす。
- 元source/map・APK・URL queryは秘密や個人情報を含み得る。ローカル解析も自動的に無害ではない。
- REA解析がlocalでも、agent経由で結果を送ればmodel providerへの送信範囲は別問題。[R3]
- cross-layerがinferredである意味を既存confidence/UIへどう保存するかは未設計。
- Web captureのmain追加制限が公開版でどう効くかは実コード・実行で別確認が必要。
- 具体的targetでの精度・速度・OS互換、公式検証記録の再現、licenseの再配布判断は未確認。
- 実端末探索・iOS .app・source mapの全形式・native QAへの実用性は未検証。
- 公式安全性記述を独立したセキュリティ検証として扱っていない。

実行済み: 公式repo/docs/source/release/npm metadata読取、主要資料のmain/tag比較、
Phase0前提との重複・価値・コスト評価、文書の参照先確認。
未実行: REA/Ghidra/JADX/ADBの導入・起動、対象解析、性能計測、pytest/E2E/品質ゲート、
コード/依存/設定変更、Claude Code起動、CI、commit/push/merge。

**Phase 1成果物を提出して停止。Phase 2・実装・依存追加には進まず、次の指示を待つ。**

## 一次資料

参照は取得版を固定。R番号はREA、G番号はGhidra。各URLは一次ソース。

[R1]: https://github.com/morluto/rea/releases/tag/rea-agents-6.7.0
[R2]: https://registry.npmjs.org/rea-agents/latest
[R3]: https://github.com/morluto/rea/blob/3ea0d9489e52500ed76555926f1b78419f71c3cb/README.md
[R4]: https://github.com/morluto/rea/blob/rea-agents-6.7.0/docs/cli.md
[R5]: https://github.com/morluto/rea/blob/rea-agents-6.7.0/docs/javascript-artifact-reconstruction.md
[R6]: https://github.com/morluto/rea/blob/rea-agents-6.7.0/docs/browser-observation.md
[R7]: https://github.com/morluto/rea/blob/rea-agents-6.7.0/docs/javascript-application-graph.md
[R8]: https://github.com/morluto/rea/blob/3ea0d9489e52500ed76555926f1b78419f71c3cb/docs/javascript-recovery.md
[R9]: https://github.com/morluto/rea/blob/3ea0d9489e52500ed76555926f1b78419f71c3cb/src/javascript/sourceMaps/SourceMapFormat.ts
[R10]: https://github.com/morluto/rea/blob/rea-agents-6.7.0/docs/javascript-runtime-reconciliation.md
[R11]: https://github.com/morluto/rea/blob/rea-agents-6.7.0/src/domain/javascript/javascriptRuntimeReconciliationInputValidation.ts
[R12]: https://github.com/morluto/rea/blob/rea-agents-6.7.0/docs/android-analysis.md
[R13]: https://github.com/morluto/rea/blob/3ea0d9489e52500ed76555926f1b78419f71c3cb/src/android/JadxRelease.ts
[R14]: https://github.com/morluto/rea/blob/rea-agents-6.7.0/docs/adb-device-analysis.md
[R15]: https://github.com/1013503897/jadx-headless-mcp/blob/v0.7.1/LICENSE
[R16]: https://github.com/morluto/rea/blob/rea-agents-6.7.0/src/domain/evidence.ts
[G1]: https://github.com/NationalSecurityAgency/ghidra/releases/tag/Ghidra_12.1.4_build
[G2]: https://github.com/NationalSecurityAgency/ghidra/blob/Ghidra_12.1.4_build/Ghidra/application.properties
[G3]: https://github.com/NationalSecurityAgency/ghidra/blob/Ghidra_12.1.4_build/LICENSE
[G4]: https://github.com/morluto/rea/blob/3ea0d9489e52500ed76555926f1b78419f71c3cb/docs/installation.md#ghidra
[G5]: https://github.com/NationalSecurityAgency/ghidra/blob/Ghidra_12.1.4_build/Ghidra/Features/Base/src/main/help/help/topics/HeadlessAnalyzer/HeadlessAnalyzer.htm
[G6]: https://github.com/morluto/rea/blob/3ea0d9489e52500ed76555926f1b78419f71c3cb/docs/ghidra-provider.md
[G7]: https://github.com/morluto/rea/blob/3ea0d9489e52500ed76555926f1b78419f71c3cb/SECURITY.md

[G8]: https://github.com/NationalSecurityAgency/ghidra/blob/Ghidra_12.1.4_build/GhidraDocs/GettingStarted.md
