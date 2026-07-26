# 先行研究レビュー: Webサイトのビジュアルデザイン／UI美観の評価手法

作成日: 2026-07-26 / 対象: ESCAPE研究計画書の「先行研究の整理」節
範囲: 美的評価（aesthetics）・ヒューリスティック評価・ユーザビリティ指標・自動評価

## 1. 検索方法（再現手順）

| 項目 | 内容 |
|---|---|
| 一次DB | OpenAlex API（`api.openalex.org/works`）。Semantic Scholar APIは429で使用不可 |
| 検索式 | `title_and_abstract.search:<句>` および `title.search:<句>`（ランドマーク論文の直接照合） |
| 並び順 | `cited_by_count:desc`（被引用数降順） |
| 年代 | 「古典」1990–2015 と「最新」2023–2026 を別クエリで取得し両方を必ず含めた |
| クエリ句 | heuristic evaluation / aesthetics AND usability / website aesthetics / first impression AND web page / visual complexity / computational aesthetics / System Usability Scale / eye tracking AND web page / web accessibility evaluation / LLM AND heuristic evaluation / generative AI AND UI design AND evaluation / dark patterns ほか計26本 |
| 採録 | 候補 約500件 → 分野ノイズ除去・重複排除後 51本 |
| 被引用数の基準時点 | 2026-07-26 のOpenAlex値（Google Scholarより小さく出る傾向） |

未実施: CiNii（日本語文献）、および引用文献の芋づる追跡（手順(3)）。

## 2. 収集した論文（51本）

### A. 古典: 美しさの知覚と評価（心理実証）

| # | 年 | 被引用 | 論文 | 掲載 | DOI |
|---|---|---|---|---|---|
| 1 | 2000 | 1352 | What is beautiful is usable | Interacting with Computers | 10.1016/s0953-5438(00)00031-x |
| 2 | 2003 | 1321 | Assessing dimensions of perceived visual aesthetics of web sites | International Journal of Human-Computer Studies | 10.1016/j.ijhcs.2003.09.002 |
| 3 | 2006 | 1032 | Attention web designers: You have 50 milliseconds to make a good first impression! | Behaviour and Information Technology | 10.1080/01449290500330448 |
| 4 | 2006 | 344 | Evaluating the consistency of immediate aesthetic perceptions of web pages | International Journal of Human-Computer Studies | 10.1016/j.ijhcs.2006.06.009 |
| 5 | 2007 | 354 | Aesthetics and credibility in web site design | Information Processing & Management | 10.1016/j.ipm.2007.02.003 |
| 6 | 2006 | 247 | Interaction, usability and aesthetics | - | 10.1145/1142405.1142446 |
| 7 | 2012 | 293 | The role of visual complexity and prototypicality regarding first impression of websites: Working towards understanding aesthetic judgments | International Journal of Human-Computer Studies | 10.1016/j.ijhcs.2012.06.003 |
| 8 | 2016 | 141 | The Determinants and Impacts of Aesthetics in Users’ First Interaction with Websites | Journal of Management Information Systems | 10.1080/07421222.2016.1172443 |
| 9 | 2013 | 153 | User Evaluation of Websites: From First Impression to Recommendation | Interacting with Computers | 10.1093/iwc/iwt033 |
| 10 | 2015 | 149 | Linking objective design factors with subjective aesthetics: An experimental study on how structure and color of websites affect the facets of users’ visual aesthetic perception | Computers in Human Behavior | 10.1016/j.chb.2015.02.056 |
| 11 | 2009 | 628 | Exploring Human Images in Website Design: A Multi-Method Approach1 | MIS Quarterly | 10.2307/20650308 |
| 12 | 2010 | 373 | Affect in Web Interfaces: A Study of the Impacts of Web Page Visual Complexity and Order1 | MIS Quarterly | 10.2307/25750702 |

### B. 古典: ヒューリスティック評価法とその限界

| # | 年 | 被引用 | 論文 | 掲載 | DOI |
|---|---|---|---|---|---|
| 13 | 1990 | 3454 | Heuristic evaluation of user interfaces | - | 10.1145/97243.97281 |
| 14 | 1992 | 1062 | Finding usability problems through heuristic evaluation | - | 10.1145/142750.142834 |
| 15 | 1994 | 1380 | Enhancing the explanatory power of usability heuristics | - | 10.1145/191666.191729 |
| 16 | 2001 | 425 | The Evaluator Effect: A Chilling Fact About Usability Evaluation Methods | International Journal of Human-Computer Interaction | 10.1207/s15327590ijhc1304_05 |
| 17 | 2010 | 411 | Number of people required for usability evaluation | Communications of the ACM | 10.1145/1735223.1735255 |
| 18 | 1991 | 621 | User interface evaluation in the real world | - | 10.1145/108844.108862 |
| 19 | 2004 | 282 | Heuristic evaluation of virtual reality applications | Interacting with Computers | 10.1016/j.intcom.2004.05.001 |

### C. 美観・複雑性の客観指標と自動計算

| # | 年 | 被引用 | 論文 | 掲載 | DOI |
|---|---|---|---|---|---|
| 20 | 2003 | 195 | Modelling interface aesthetics | Information Sciences | 10.1016/s0020-0255(02)00404-8 |
| 21 | 2002 | 21 | Aesthetic measures for screen design | - | 10.1109/ozchi.1998.732197 |
| 22 | 2015 | 135 | Computation of Interface Aesthetics | - | 10.1145/2702123.2702575 |
| 23 | 2014 | 82 | Quantification of interface visual complexity | - | 10.1145/2598153.2598173 |
| 24 | 2015 | 143 | Computerized measures of visual complexity | Acta Psychologica | 10.1016/j.actpsy.2015.06.005 |
| 25 | 2013 | 305 | Predicting users' first impressions of website aesthetics with a quantification of perceived visual complexity and colorfulness | - | 10.1145/2470654.2481281 |
| 26 | 2018 | 92 | Aalto Interface Metrics (AIM) | - | 10.1145/3266037.3266087 |
| 27 | 2001 | 879 | The state of the art in automating usability evaluation of user interfaces | ACM Computing Surveys | 10.1145/503112.503114 |
| 28 | 2014 | 22 | GUIEvaluator: A Metric-tool for Evaluating the Complexity of Graphical User Interfaces. | - | - |
| 29 | 2011 | 50 | Objective and Subjective Measures of Visual Aesthetics of Website Interface Design: The Two Sides of the Coin | Lecture notes in computer science | 10.1007/978-3-642-21602-2_4 |
| 30 | 2011 | 60 | Investigating Effects of Screen Layout Elements on Interface and Screen Design Aesthetics | Advances in Human-Computer Interaction | 10.1155/2011/659758 |
| 31 | 2009 | 131 | Toward a definition of visual complexity as an implicit measure of cognitive load | ACM Transactions on Applied Perception | 10.1145/1498700.1498704 |
| 32 | 2008 | 178 | Visual complexity and aesthetic perception of web pages | - | 10.1145/1456536.1456581 |
| 33 | 2011 | 24 | Investigating objective measures of web page aesthetics and usability | ENLIGHTEN (Jurnal Bimbingan dan Konseling Islam) | - |
| 34 | 2014 | 141 | Quantifying visual preferences around the world | - | 10.1145/2556288.2557052 |
| 35 | 2018 | 158 | Learning Design Semantics for Mobile Apps | - | 10.1145/3242587.3242650 |

### D. ユーザビリティ指標（尺度）

| # | 年 | 被引用 | 論文 | 掲載 | DOI |
|---|---|---|---|---|---|
| 36 | 1996 | 8153 | SUS: A 'Quick and Dirty' Usability Scale | - | 10.1201/9781498710411-35 |
| 37 | 2018 | 1931 | The System Usability Scale: Past, Present, and Future | International Journal of Human-Computer Interaction | 10.1080/10447318.2018.1455307 |

### E. 最新: LLM/生成AIによるデザイン評価

| # | 年 | 被引用 | 論文 | 掲載 | DOI |
|---|---|---|---|---|---|
| 38 | 2024 | 74 | Generating Automatic Feedback on UI Mockups with Large Language Models | - | 10.1145/3613904.3642782 |
| 39 | 2024 | 41 | SimUser: Generating Usability Feedback by Simulating Various Users Interacting with Mobile Applications | - | 10.1145/3613904.3642481 |
| 40 | 2024 | 70 | Generative AI in User Experience Design and Research: How Do UX Practitioners, Teams, and Companies Use GenAI in Industry? | Designing Interactive Systems Conference | 10.1145/3643834.3660720 |
| 41 | 2025 | 14 | Towards a Working Definition of Designing Generative User Interfaces | - | 10.1145/3715668.3736365 |
| 42 | 2026 | 3 | Bridging Gulfs in UI Generation through Semantic Guidance | - | 10.1145/3772318.3791966 |
| 43 | 2025 | 4 | StarryStudioAI: Automating UI Design with Code-Based Generative AI and RAG | - | 10.1109/ccwc62904.2025.10903712 |
| 44 | 2024 | 13 | AI-Driven Design Thinking: A Comparative Study of Human-Created and AI-Generated UI Prototypes for Mobile Applications | - | 10.1109/incit63192.2024.10810565 |

### F. 規範ベースの自動評価（アクセシビリティ・ダークパターン）

| # | 年 | 被引用 | 論文 | 掲載 | DOI |
|---|---|---|---|---|---|
| 45 | 2013 | 208 | Benchmarking web accessibility evaluation tools | - | 10.1145/2461121.2461124 |
| 46 | 2023 | 33 | AidUI: Toward Automated Recognition of Dark Patterns in User Interfaces | - | 10.1109/icse48619.2023.00166 |
| 47 | 2021 | 49 | Ethical User Interfaces: Exploring the Effects of Dark Patterns on Facebook | - | 10.1145/3411763.3451659 |
| 48 | 2023 | 12 | Investigating Visual Countermeasures Against Dark Patterns in User Interfaces | - | 10.1145/3603555.3603563 |

### G. 視線・注意の実測

| # | 年 | 被引用 | 論文 | 掲載 | DOI |
|---|---|---|---|---|---|
| 49 | 2010 | 375 | Generation Y, web design, and eye tracking | International Journal of Human-Computer Studies | 10.1016/j.ijhcs.2009.12.006 |
| 50 | 2009 | 247 | What do you see when you're surfing? | - | 10.1145/1518701.1518705 |
| 51 | 2011 | 94 | The impact of salient advertisements on reading and attention on web pages. | Journal of Experimental Psychology Applied | 10.1037/a0024042 |

## 3. 何が分かっているか（Established）

各項目末尾の【】は確認レベル。**【本文確認】= abstractを一次ソース（OpenAlex/arXiv原文）で取得して確認、【未確認】= 出版社がabstractを非公開にしておりメタデータのみ。**

1. **見た目の印象は50ミリ秒で決まる。**【本文確認】Lindgaardら（#3）は3実験を実施し、500ms提示と50ms提示の視覚的魅力度評定が高相関、かつ反復測定間でも高相関であることを示した。原文の結論は "visual appeal can be assessed within 50 ms, suggesting that web designers have about 50 ms to make a good first impression"。
2. **美観は使いやすさの知覚を規定するが、逆は成り立たない。**【本文確認】Tractinskyら（#1）はATM模擬システムで、**美観の水準が使用後の「美観」と「ユーザビリティ」の両方の知覚に影響した一方、実際のユーザビリティの水準はどちらにも影響しなかった**と報告している。「美しいものは使いやすいと感じられる」の一次根拠はこの非対称性にある。
3. **美観は2因子（classical / expressive）に分解できる。**【未確認】Lavie & Tractinsky（#2）が提案し以後の尺度のデファクトとなっているが、**出版社がabstractを非公開にしており本レビューでは一次確認できていない。計画書で引用する前に本文入手が必須。**
4. **第一印象は「視覚的複雑性」と「色の豊かさ」から機械的に予測できる（説明率は約半分）。**【本文確認】Reineckeら（#24）は450サイト・548名の評定を収集し、複雑性とcolorfulnessの知覚モデルに年齢・学歴などの属性を加えて、**500ms提示後の美的魅力度評定の分散の約50%を説明**した。裏を返せば**残り半分は未説明**である。
5. **視覚的複雑性と典型性が第一印象を規定する。**【未確認】Tuchら（#7）。abstractが非公開で一次確認できていない。
6. **ヒューリスティック評価は再現しない（評価者効果）。**【本文確認】Hertzum & Jacobsen（#16）は認知的ウォークスルー・ヒューリスティック評価・思考発話法に関する11研究をレビューし、**同一UIを同一手法で評価した任意の2名の評価者間の平均一致率は5%〜65%**、3手法のいずれも一貫して優れてはいないと結論した。**これが本レビュー全体で最も重要な数値であり、「LLMを評価者にする」研究が比較されるべきベースラインでもある。**
7. **美観の自動計算はWebサービスとして実用段階にある。**【本文確認】AIM（#25）はURLを入力に、視覚的雑然さから視覚的学習容易性まで**17指標**を計算し、内訳・可視化・統計比較を返す（interfacemetrics.aalto.fi）。前史としてNgo（#19, #20）の幾何指標、Miniukovichら（#21, #22）の知覚ベース複雑性、Ivory & Hearst（#26）の自動化サーベイがある。
8. **LLMによるヒューリスティック評価の自動化は2024年に実証された。ただし反復すると劣化する。**【本文確認】Duanら（#35）はGPT-4にヒューリスティック評価を自動実行させるFigmaプラグインを作り、**51のUI・3種のガイドライン集合**で評価、**12名の専門デザイナー**に検証させた。**微細な誤り・文言・UI意味論の指摘には有用だった一方、「反復するにつれてフィードバックの有用性が低下した（feedback also decreased in utility over iterations）」**と明記されている。

## 4. 何が分かっていないか（Gap）

| # | 未解明の点 | 根拠 |
|---|---|---|
| G1 | **自動計算できる美観指標と、ヒューリスティック評価が見つける「問題」が接続していない。** 指標はスコアを返すが「どこをどう直すか」を返さない。 | #19–#25 の出力はいずれもスカラー値。改善指示に変換した研究はレビュー範囲内で未発見 |
| G2 | **LLMによるデザイン評価は登場したばかりで、評価者効果（#16）と同じ再現性の問題が検証されていない。** | #35（UIモックへの自動フィードバック, 2024）、#36（SimUser, 2024）はいずれも2024年以降。評価者を人からLLMに置き換えたときの一致率・安定性の実証は薄い |
| G3 | **既存の美観指標はスクリーンショット静止画が前提で、実際に動くWebサイトの状態遷移・レスポンシブ・動的表示を対象にしていない。** | #21–#25 は単一画面画像を入力とする。クロール由来の多画面集合をどう集約評価するかは未整理 |
| G4 | **「美観スコア」と「規範適合（アクセシビリティ・ダークパターン）」が別系統のまま統合されていない。** | #41–#44 はWCAG／倫理の観点で独立に発展し、美観指標群と共通の評価枠組みを持たない |
| G5 | **日本語圏では「アクセシビリティの規格適合評価」と「ユーザビリティ評価手法の改良」に研究が集中し、美観の計算的定量化（#21–#25系）の追試がCiNii検索では見つからなかった。** | 第5節の検索結果を参照。11クエリ中5クエリがヒット0件 |


## 5. 日本語文献の状況（CiNii検索結果）

検索日 2026-07-26 / `cir.nii.ac.jp/opensearch/all`（全文DB横断）/ 11クエリ。

| クエリ | 件数 | 主な該当 |
|---|---|---|
| アクセシビリティ 評価 JIS X 8341 | 17 | Webアクセシビリティ評価ツール検証用テストスイート開発（電子情報通信学会技報, 2008）／ウェブアクセシビリティ簡易評価手法（同, 2012）／Webアクセシビリティ診断技術（NTT技術ジャーナル, 2011）／地方自治体サイトの現状（情報通信学会誌, 2018）／WCAG 2.0の概要（情報管理, 2007） |
| ユーザビリティ 評価 ヒューリスティック | 14 | **構造化ヒューリスティック評価法の提案（ヒューマンインタフェースシンポジウム, 1997）**／ユーザビリティ評価の初心者に適したインスペクション法の提案（デザイン学研究, 2014）／取扱説明書向け構造化ヒューリスティック評価チェックリスト（人間生活工学, 2014）／ユーザビリティ評価システム「UIテスタ」（情報処理学会論文誌, 1997） |
| Webサイト 印象 評価 | 16 | ラフ集合によるWeb画面デザイン仕様の明確化（デザイン学研究, 2006）／**多次元尺度構成法によるWebデザイン印象評価の可視化（デザイン学研究, 2010）**／フォントの印象評価方法に関する考察（日本デザイン学会, 2022）／Webサイト閲覧時の印象評価のための脳波計測 |
| 画面 デザイン 印象 定量 | 3 | アイコンのデザインと印象／数理的ヴァルールを用いた絵画の構造分析（日本色彩学会誌, 2020） |
| ヒューリスティック評価 チェックリスト 提案 | 1 | 上記2014年の人間生活工学論文 |
| Webデザイン 美的 評価 | **0** | — |
| SD法 ウェブサイト 印象評価 | **0** | — |
| 感性工学 Webデザイン 印象 | **0** | — |
| Webサイト 審美性 信頼 | **0** | — |
| ユーザビリティ 尺度 日本語版 | **0** | — |
| 視覚的複雑性 画面 | 1 | 視覚心理学の論文であり画面デザインは対象外 |

**読み取れること**
1. 日本語圏の研究蓄積は **(a) JIS X 8341 準拠のアクセシビリティ評価** と **(b) ヒューリスティック評価法そのものの改良（構造化・初心者向け）** に偏っている。(b) は評価者効果（#16）への日本独自の応答と位置づけられ、本研究の直接の先行研究になりうる。
2. 印象評価はデザイン学会系にSD法・MDS・ラフ集合を用いた研究があるが、**Reinecke（#24）やAIM（#25）に相当する「スクリーンショットから美観を計算する」系統の日本語研究はヒットしなかった。**
3. 5クエリがヒット0件。**これは「日本語圏に研究が無い」ことの証明ではない**——次の限界がある: (i) J-STAGE本文検索・情報処理学会DL・HAI/HCIシンポジウム個別DBは未検索、(ii) 用語揺れ（「審美性」「美観」「印象」「感性」）を網羅していない、(iii) CiNiiは会議予稿の収録が不均一。**計画書で「日本語圏に空白がある」と主張するなら、最低でもJ-STAGEでの再検索が必要。**

## 6. 本研究の位置づけ（案・1文）

先行研究が「静止画1枚に対する美観スコア」と「人間評価者によるヒューリスティック評価」を別々に発展させてきたのに対し、本研究は **実稼働Webサイトを巡回して得た複数画面を対象に、自動計算指標とLLMによる指摘生成を統合し、その指摘の再現性（評価者効果に相当する指標間・実行間の一致率）を検証する** 点に位置づけられる（G1＋G2＋G3）。

## 7. 引用時の注意（このファイルの信頼度）

- **一次ソースでabstractを確認したのは 6/8本**（#1, #3, #16, #24, #25, #35）。第3節の該当項目は原文の記述に基づく。**#2（Lavie & Tractinsky 2003）と #7（Tuch 2012）は出版社がabstractを非公開にしており未確認。** 残る43本はメタデータのみ。
- **全文PDFは1本も読んでいない。** ACM Digital LibraryとScienceDirectはいずれもHTTP 403で取得不可。確認できたのはabstractまで。実験条件・統計手法の妥当性は検証していない。
- 被引用数は OpenAlex 2026-07-26 時点。同一論文が複数レコードに分裂している例がある（#15 が1380と333に分裂）。計画書に数値を載せるならGoogle Scholarで取り直すこと。
- #33（SUS: Past, Present, and Future）は総説であり、SUSの原典は #32（Brooke 1996, 書籍章）。原典引用が必要な場合は #32 を使うこと。
- 第5節の「0件」は CiNii 限定の否定的結果。J-STAGE等は未検索（第5節の限界を参照）。
- ISO 9241-11・WCAG 2.2・JIS X 8341-3 は論文ではないため表に含めていない。規範として引用する場合は規格原本を参照すること。
