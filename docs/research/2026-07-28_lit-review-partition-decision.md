# 同値分割・決定表文献レビュー（技法エンジン更新・R6）

作成日: 2026-07-28 / 対象: 同値分割の形式化（category-partition法）・分類ツリー・原因結果グラフ・決定表・MC/DC の一次文献確認と現実装ギャップ判断

## 結論(3行)

1. 現実装の「全真1+各原因単独偽のn規則」（n+1規則）は、AND決定に対する unique-cause MC/DC のテスト集合と同型であることが一次資料（NASA/TM-2001-210876）で裏づけられた。ただしMC/DCは本来コード構造カバレッジ基準であり、仕様ベースでは「決定表の圧縮基準としての借用」と位置づけるのが正確。
2. TSLの error/single 選択子は「異常系・特殊系を組合せから隔離して1件にする」圧縮機構で、現実装のn+1規則が実質的にこれを機械化している。生成ロジックの変更は不要で、クラスへの error/single 属性ラベル付与（文献準拠の明示）のみ導入価値がある。
3. Myersの制約記号（E/I/O/R/M）・トレースバック規則、Grochtmannの組合せ規則の正式名称、Elmendorf 1973原典は**一次未確認**。設計書・論文で引用する場合は必ず「未確認・引用禁止リスト」に従うこと。

## 実証された知見（出典必須）

一次資料（原文またはabstract原文）で確認できた事実のみを記載する。

### 1. Category-Partition法（Ostrand & Balcer 1988）

- 出典: Thomas J. Ostrand, Marc J. Balcer, "The category-partition method for specifying and generating functional tests", CACM 31(6), 1988. DOI: 10.1145/62959.62964。被引用795（OpenAlex 2026-07-28時点）
- abstract原文で確認した範囲:
  - テストエンジニアがシステム仕様を分析し、**形式的テスト仕様**を書き、**生成ツール**が test description を生成する方法である（"writes a series of formal test specifications, and then uses a generator tool to produce test descriptions"）
  - **制約（constraints）のアノテーションによって、テストの複雑さと数を制御できる**ことが本手法の主要な利点として明記されている（"can control the complexity and number of the tests by annotating the test specification with constraints"）
- つまり「組合せ爆発の抑制は制約アノテーションで行う」という設計思想自体は一次確認済み。ただし categories / choices / properties / selectors / error / single の**個別定義は本文にあり、abstract外＝一次未確認**（後述）。

### 2. 分類ツリー法（Grochtmann & Grimm 1993）

- 出典: Matthias Grochtmann, Klaus Grimm, "Classification trees for partition testing", Software Testing, Verification and Reliability 3(2), 1993. DOI: 10.1002/stvr.4370030203。被引用291
- abstract原文で確認した範囲:
  - 分割テスト（partition testing）に基づき、入力領域を**テスターが関連とみなす観点（aspect）ごとに、互いに素かつ完全な分類（disjoint and complete classifications）**に分ける
  - 分類から生じたクラスは**さらに再帰的に分類できる**（現実装の「画面→フォーム→項目→クラス」の階層に対応）
  - テストケースは**異なる分類のクラスを組み合わせて**形成し、木から**組合せ表（combination table）**を作ってテストケースをマークする
  - 拡張記法と**ツールサポート**により大規模テスト問題にも適用可能（CTEツールの存在を示唆）
- 「最小被覆（各クラス1回以上）vs 全組合せ」という組合せ規則の正式な定義・名称はabstract外＝一次未確認。

### 3. MC/DC（Chilenski & Miller 1994 / Hayhurst et al. 2001）

- 出典1: John Joseph Chilenski, Steven P. Miller, "Applicability of modified condition/decision coverage to software testing", Software Engineering Journal 9(5), 1994. DOI: 10.1049/sej.1994.0025。被引用510
  - abstract原文で確認: MC/DCは**構造カバレッジ基準**であり、「decision内の各conditionが、decisionの結果に**独立かつ正しく影響することを実行によって示す**」ことを要求する（"each condition within a decision is shown by execution to independently and correctly affect the outcome of the decision"）。安全性重視分野の複雑なBoolean式の徹底テストのために開発された。
- 出典2: Kelly J. Hayhurst, Dan S. Veerhusen, John J. Chilenski, Leanna K. Rierson, "A Practical Tutorial on Modified Condition/Decision Coverage", NASA/TM-2001-210876, 2001. NTRS 20010057789。**全文を一次確認**（NTRS公開テキスト）。以下すべて原文引用に基づく:
  - **n+1ケース性**: 「一般に、n入力のdecisionに対し最小 n+1 テストケースを要する」（"in general, a minimum of n+1 test cases for a decision with n inputs"）。例: (A or B) は (TF), (FT), (FF) の3ケースでMC/DC達成
  - **unique-cause方式**: 独立影響を示す原方式。対象condition以外の値を固定し、対象conditionだけを反転させるペア（independence pair）で示す
  - **unique-causeの限界**: 「反復条件や強結合条件があるdecision（例: (A and B) or (A and C)）には適用できない」（"The unique-cause approach cannot be applied, however, to decisions where there are repeated or strongly coupled conditions"）
  - **masking MC/DC**: 他conditionの変化をゲートの論理でマスクして独立影響を示す代替方式。unique-causeと同じ最小テストケース数で、結合条件にも適用でき、DO-178Bの目的に対して許容される
  - **MC/DCの運用位置づけ**: DO-178Bでは、テストケース自体は**要求ベース（requirements-based）**で作り、構造カバレッジ分析はそれが**コード構造をどれだけ実行したかを測る**工程である（"Structural coverage analysis determines how much of the code structure was executed by the requirements-based tests"）。つまりMC/DCはブラックボックス生成規則としてではなく、要求ベーステストの十分性測定として定義されている。

### 4. 原因結果グラフの研究系譜（存在確認のみ）

- Paradkar, Tai, Vouk, "Specification-based testing using cause-effect graphs", Annals of Software Engineering, 1997. DOI: 10.1023/a:1018979130614。被引用37 — cause-effect graphが仕様ベーステストの研究対象として継続していることの確認（内容はabstract未取得）
- Srivastava et al., "Cause effect graph to decision table generation", ACM SIGSOFT SEN, 2009. DOI: 10.1145/1507195.1507216 — グラフ→決定表変換の自動化研究の存在確認（同上）

## 主張どまりの知見

広く流通しているが、本レビューでは一次資料で確認できなかった知見。**設計判断の参考にはするが、根拠として引用しない。**

1. **TSLの構成要素の詳細定義**: category（パラメータ・環境条件の特性）/ choice（各categoryの代表値）/ property・selector（if条件による組合せ制約）/ **error**（エラーを表すchoiceで、他categoryと組み合わせず単独で1テストフレームのみ生成）/ **single**（代表1回のみテストする）— 教科書（Ammann & Offutt, Introduction to Software Testing 等）で一致して説明される通説だが、CACM原文はACM DL paywall（403）で一次確認不能だった。
2. **分類ツリーの組合せ規則**: 最小被覆（各葉クラスを少なくとも1回=1-wise相当）と全組合せの2水準がCTE（Classification-Tree Editor）でサポートされるという通説。STVR原文はWiley paywall（Unpaywall判定 is_oa: false）。
3. **Myersの原因結果グラフ制約記号**: E (exclusive) / I (inclusive, at least one) / O (one and only one) / R (requires) / M (masks)、および**トレースバック規則**（各effectを真にする入力組合せをグラフを後方に辿って列挙する際、ORノードでは真にする入力を1つに限定して列の爆発を抑える）— Myers, The Art of Software Testing (1979) の通説的内容。書籍のため本レビューの手段（API経由）では原文未確認。
4. **Elmendorf 1973が原因結果グラフの原典**という系譜: Myers自身がElmendorfのIBM技術報告書を引用しているとされるが、報告書自体はOpenAlex未収録・入手不能（下記リスト参照）。

## 未確認・引用禁止リスト

| # | 項目 | 状態 | 禁止理由 |
|---|---|---|---|
| 1 | TSL error/single 選択子の正確な生成規則（error choiceが「他categoryはデフォルト値と組む」のか「完全に単独」なのか等） | 一次未確認 | CACM原文にアクセス不能。二次資料間で細部の記述が揺れる可能性 |
| 2 | 分類ツリーの組合せ規則の正式名称（"minimal criterion" 等） | 一次未確認 | STVR原文にアクセス不能。名称を引用すると捏造リスク |
| 3 | Myersの制約記号5種の正確な初出（Myers 1979 か Elmendorf 1973 か） | 未確認 | どちらの原文も未入手。「Myersが定式化」と断定しない |
| 4 | Elmendorf 1973 の正確な書誌事項（"Cause-Effect Graphs in Functional Testing", IBM TR-00.2487 とされる） | 未確認 | OpenAlex未収録・原本未入手。TR番号を含め引用禁止 |
| 5 | 「MC/DCは常にn+1ケースで達成可能」という強い主張 | 反証あり | Hayhurst原文は "in general, a minimum of n+1" であり、結合条件ではunique-causeが**適用不能**（一次確認済み）。「常に」は誤り |
| 6 | CTEツールの機能一覧（GUI編集・自動組合せ生成等） | 一次未確認 | 論文原文・ツールマニュアルとも未入手 |

## 現実装とのギャップ

### 1. TSLの error/single 選択子は導入価値があるか → 属性ラベルとしてのみ導入（生成ロジック変更不要）

- 現実装は「必須項目の全入力+1つずつ欠落」（n+1規則）と「各原因単独偽」で、**異常系を組合せ空間から隔離して1件ずつにする**ことを既に行っている。これはerror選択子の意図（一次確認済みの「制約アノテーションで数を制御」の具体化）と機能的に同等。
- ギャップは**分類の明示性**のみ: 現実装は「なぜこのケースは1件でよいのか」の根拠をデータとして持たない。equivalence_classes の無効クラスに `error`、境界的・特殊値に `single` 相当の属性を付け、設計書・QFカラムに出せば、category-partition法準拠を説明できる。工数小・価値中。
- 注意: error/singleの詳細規則は一次未確認のため、ドキュメント上は「category-partition法のerror/single選択子**に相当する**」という表現に留める（「準拠」と断定しない）。

### 2. n+1規則はMC/DCと同型か → 同型（AND決定・unique-cause）。ただし適用範囲の限定を明記すべき

- 必須n項目のフォーム送信は決定 `D = c1 AND c2 AND ... AND cn` とみなせる。「全真1件」+「ci単独偽のn件」は、各ciについて独立影響ペア（全真ケースを共有）を構成し、**unique-cause MC/DCの最小テスト集合そのもの**。n+1性はHayhurst原文で一次確認済み。
- ただし2点の限定がある:
  - (a) MC/DCは本来**構造カバレッジ測定**であり（DO-178Bの運用位置づけ、一次確認済み）、仕様ベース生成規則としての使用は「決定表の圧縮基準としての借用」。設計書にはこの位置づけで書く。
  - (b) 現実装のM制約（必須未入力が形式検査を隠す）はまさに**マスク関係**であり、マスクされた原因の単独偽ケースは独立影響を示せない。Hayhurstのmasking MC/DCの考え方（ゲート論理でマスクを考慮して有効テストを選ぶ）に対応する処理が必要。現実装がM制約下で「c1偽（必須未入力）のときc2（pattern違反）の判定は未検証」と扱えているなら整合、単純にn+1を数えているだけなら**カバレッジの過大主張**になる。ここは実装確認が必要（本レビューでは未確認）。

### 3. トレースバック規則の導入価値 → 現時点では見送り

- トレースバック規則（通説）はORノードの列爆発を抑える手続きだが、現実装の原因結果グラフはNOT/ANDゲート中心で、決定表縮約は固定規則（全真1+単独偽n）で済んでいる。中間ORノードがほぼ無い現状では導入効果が薄い。
- 将来、複数バリデーションの「いずれかで拒否」（OR→エラー表示）のような中間ノードを持つグラフに拡張したときに再検討する。その際も規則の詳細はMyers原文の一次確認を先に行うこと（現状は引用禁止リスト#3）。

### 4. 分類ツリーの1-wise最小組合せ → 維持で妥当

- 「異なる分類のクラスの組合せでテストケースを形成し、組合せ表でマークする」枠組みは一次確認済みで、現実装の階層+クラス被覆(1-wise)はこの枠組みの一実装として説明できる。全組合せを採らない判断は、Ostrand & Balcerの「制約で数を制御する」思想とも整合する。

## WebSpec2Docへの適用判断（表）

| # | 項目 | 判断 | 根拠 | 工数 |
|---|---|---|---|---|
| 1 | 無効クラスへの error 属性・特殊値への single 属性のラベル付与（生成ロジックは不変） | 採用 | n+1規則が実質同等の圧縮を既に実装。ラベルだけで文献対応が明示できる | 小 |
| 2 | 設計書での位置づけ表現を「category-partition法のerror/single選択子に相当」とする（「準拠」と書かない） | 採用 | 詳細規則が一次未確認（引用禁止リスト#1） | 極小 |
| 3 | n+1規則の説明に「AND決定に対するunique-cause MC/DCの最小テスト集合と同型」と明記 | 採用 | Hayhurst NASA/TM-2001-210876で一次確認 | 極小 |
| 4 | M制約下で、マスクされた原因の検査結果を「未検証」と明示する挙動の確認・是正 | 要確認 | masking MC/DCの独立影響の考え方。現実装の挙動は本レビュー未確認 | 中 |
| 5 | トレースバック規則の実装 | 見送り | 中間ORノードがない現状で効果薄。Myers原文も未確認 | - |
| 6 | 分類ツリーの全組合せモード追加 | 見送り | 組合せ爆発。制約で数を制御する思想（一次確認済み）に反する | - |
| 7 | Elmendorf 1973・CTE機能一覧の引用 | 禁止 | 原典未入手（引用禁止リスト#4, #6） | - |

## 検索方法（再現手順）

| 項目 | 内容 |
|---|---|
| 一次DB | OpenAlex API（`api.openalex.org/works`）。`title.search:` で4技法の原典を直接検索し、DOI指定でabstract_inverted_index・open_access情報を取得 |
| クエリ句 | category-partition method / classification trees partition testing / modified condition decision coverage / cause-effect graph / Elmendorf cause-effect functional testing |
| OA探索 | Unpaywall API（`api.unpaywall.org/v2/<DOI>`）でOA版所在を確認。CACM 1988はACM DL PDFが唯一のOA所在だが取得403、STVR 1993は is_oa: false |
| 全文一次確認 | NASA NTRS API（`ntrs.nasa.gov/api/citations/search`）で NASA/TM-2001-210876 の公開フルテキスト（20010057789.txt, 約19万字）を取得し、n+1 / unique-cause / masking / coupled conditions / requirements-based の該当箇所を抽出 |
| 到達できなかった経路 | ACM DL（curl・WebFetchとも403）、Wiley（OA無し）、Offutt著者サイトのミラー（404）、Elmendorf IBM技術報告書（OpenAlex未収録） |
| 被引用数の基準時点 | 2026-07-28のOpenAlex値。Google Scholarとは異なる |

未実施: Google Scholar・CiNii手検索、書籍（Myers 1979, Ammann & Offutt教科書）の原文確認、CTEツール文書の確認。本レビューの一次確認カバレッジは「Hayhurst全文」「4本のabstract原文」まで。

## 引用時の注意（このファイルの信頼度）

- **全文を読んだのは Hayhurst et al. 2001 のみ**。Ostrand & Balcer / Grochtmann & Grimm / Chilenski & Miller はabstract原文まで、Paradkar 1997・Srivastava 2009はメタデータのみ。
- 「実証された知見」節の引用文はすべて取得した原文からの転記。「主張どまりの知見」節は通説であり、外部文書に書く場合は必ず原文確認を先行させること。
