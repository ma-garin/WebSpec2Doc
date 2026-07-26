# 先行研究レビュー: LLM/自動化によるWebアプリのテスト設計・仕様抽出・QA自動化

作成日: 2026-07-26 / 対象: ESCAPE研究計画書の「先行研究の整理」節

## 1. 検索方法（再現手順）

| 項目 | 内容 |
|---|---|
| 一次DB | OpenAlex API（`api.openalex.org/works`）。Semantic Scholar APIは429で使用不可 |
| 絞り込み | `primary_topic.field.id:fields/17`(Computer Science) + `title_and_abstract.search:<句>` |
| 並び順 | `cited_by_count:desc`（被引用数降順＝「よく引用されている論文から読む」に対応） |
| 年代 | 「古典」1998–2021 と「最新」2022–2026 を別クエリで取得し、両方を必ず含めた |
| クエリ句 | GUI testing / web application testing / test case generation / model-based testing / large language models AND test generation / unit test generation / crawling AND web application / LLM agents AND web / requirements AND test cases / human-in-the-loop AND software testing / end-to-end AND test automation ほか計19本 |
| 取得件数 | 候補 約400件 → 分野ノイズ除去・重複排除後 45件を採録 |
| 被引用数の基準時点 | 2026-07-26 のOpenAlex値。Google Scholarとは値が異なる（GSのほうが大きく出る） |

未実施: Google Scholar・CiNii の手検索、および引用文献の芋づる追跡（手順(3)）。本レビューは手順(1)(2)(4)までのカバレッジ。

## 2. 収集した論文（45本）

### A. 古典: Web/GUI テスト自動化の基盤

| # | 年 | 被引用 | 論文 | 掲載 | DOI |
|---|---|---|---|---|---|
| 1 | 2004 | 382 | GUI ripping: reverse engineering of graphical user interfaces for testing | - | 10.1109/wcre.2003.1287256 |
| 2 | 2012 | 517 | Using GUI ripping for automated testing of Android applications | - | 10.1145/2351676.2351717 |
| 3 | 2012 | 300 | Crawling Ajax-Based Web Applications through Dynamic Analysis of User Interface State Changes | ACM Transactions on the Web | 10.1145/2109205.2109208 |
| 4 | 2016 | 80 | Approaches and Tools for Automated End-to-End Web Testing | Advances in computers | 10.1016/bs.adcom.2015.11.007 |
| 5 | 2014 | 37 | Prevalence and Maintenance of Automated Functional Tests for Web Applications | - | 10.1109/icsme.2014.36 |
| 6 | 2018 | 77 | Visual web test repair | - | 10.1145/3236024.3236063 |
| 7 | 2022 | 42 | Similarity-based Web Element Localization for Robust Test Automation | ACM Transactions on Software Engineering and Methodology | 10.1145/3571855 |
| 8 | 2021 | 26 | Web Test Automation: Insights from the Grey Literature | Lecture notes in computer science | 10.1007/978-3-030-67731-2_35 |

### B. 古典: テスト生成理論・オラクル問題

| # | 年 | 被引用 | 論文 | 掲載 | DOI |
|---|---|---|---|---|---|
| 9 | 2004 | 1362 | Search-based software test data generation: a survey | Software Testing, Verification and Reliability | 10.1002/stvr.294 |
| 9b | 2012 | 588 | Whole Test Suite Generation | IEEE Transactions on Software Engineering | 10.1109/tse.2012.14 |
| 10 | 2005 | 1657 | CUTE | - | 10.1145/1081706.1081750 |
| 11 | 2006 | 1095 | Practical Model-Based Testing: A Tools Approach | - | - |
| 12 | 2005 | 405 | Automating the generation and sequencing of test cases from model-based specifications | Lecture notes in computer science | 10.1007/bfb0024651 |
| 13 | 2014 | 1046 | The Oracle Problem in Software Testing: A Survey | IEEE Transactions on Software Engineering | 10.1109/tse.2014.2372785 |
| 14 | 2021 | 1076 | Introduction to Software Testing | Cambridge University Press eBooks | 10.1017/9781108974073.004 |
| 15 | 2008 | 605 | Requirements Coverage as an Adequacy Measure for Conformance Testing | Lecture notes in computer science | 10.1007/978-3-540-88194-0_8 |

### C. 中間期: 探索型・モデルベースGUIテスト（モバイル中心）

| # | 年 | 被引用 | 論文 | 掲載 | DOI |
|---|---|---|---|---|---|
| 16 | 2015 | 465 | Automated Test Input Generation for Android: Are We There Yet? (E) | - | 10.1109/ase.2015.89 |
| 17 | 2013 | 424 | Targeted and depth-first exploration for systematic testing of android apps | - | 10.1145/2509136.2509549 |
| 18 | 2013 | 321 | Guided GUI testing of android apps with minimal restart and approximate learning | - | 10.1145/2509136.2509552 |
| 19 | 2014 | 279 | MobiGUITAR: Automated Model-Based Testing of Mobile Apps | IEEE Software | 10.1109/ms.2014.55 |
| 20 | 2020 | 172 | Reinforcement learning based curiosity-driven testing of Android applications | - | 10.1145/3395363.3397354 |
| 21 | 2022 | 52 | Fastbot2: Reusable Automated Model-based GUI Testing for Android Enhanced by Reinforcement Learning | - | 10.1145/3551349.3559505 |
| 22 | 2016 | 158 | Automated model-based Android GUI testing using multi-level GUI comparison criteria | - | 10.1145/2970276.2970313 |
| 23 | 2022 | 79 | Pynguin | - | 10.1145/3510454.3516829 |

### D. 最新: LLMによるテスト生成

| # | 年 | 被引用 | 論文 | 掲載 | DOI |
|---|---|---|---|---|---|
| 24 | 2024 | 774 | Large Language Models for Software Engineering: A Systematic Literature Review | ACM Transactions on Software Engineering and Methodology | 10.1145/3695988 |
| 25 | 2024 | 429 | Software Testing With Large Language Models: Survey, Landscape, and Vision | IEEE Transactions on Software Engineering | 10.1109/tse.2024.3368208 |
| 26 | 2023 | 308 | An Empirical Evaluation of Using Large Language Models for Automated Unit Test Generation | IEEE Transactions on Software Engineering | 10.1109/tse.2023.3334955 |
| 27 | 2023 | 242 | CodaMosa: Escaping Coverage Plateaus in Test Generation with Pre-trained Large Language Models | - | 10.1109/icse48619.2023.00085 |
| 28 | 2023 | 179 | Large Language Models are Few-shot Testers: Exploring LLM-based General Bug Reproduction | - | 10.1109/icse48619.2023.00194 |
| 29 | 2024 | 116 | ChatUniTest: A Framework for LLM-Based Test Generation | - | 10.1145/3663529.3663801 |
| 30 | 2024 | 113 | Evaluating and Improving ChatGPT for Unit Test Generation | Proceedings of the ACM on software engineering. | 10.1145/3660783 |
| 31 | 2024 | 112 | Effective test generation using pre-trained Large Language Models and mutation testing | Information and Software Technology | 10.1016/j.infsof.2024.107468 |
| 32 | 2024 | 91 | LLM-Based Test-Driven Interactive Code Generation: User Study and Empirical Evaluation | IEEE Transactions on Software Engineering | 10.1109/tse.2024.3428972 |

### E. 最新: LLMエージェントによるGUI/Web操作・仕様側

| # | 年 | 被引用 | 論文 | 掲載 | DOI |
|---|---|---|---|---|---|
| 33 | 2024 | 98 | Make LLM a Testing Expert: Bringing Human-like Interaction to Mobile GUI Testing via Functionality-aware Decisions | - | 10.1145/3597503.3639180 |
| 34 | 2023 | 113 | Fill in the Blank: Context-aware Automated Text Input Generation for Mobile GUI Testing | - | 10.1109/icse48619.2023.00119 |
| 35 | 2024 | 44 | Testing the Limits: Unusual Text Inputs Generation for Mobile App Crash Detection with Large Language Model | - | 10.1145/3597503.3639118 |
| 36 | 2024 | 153 | Prompting Is All You Need: Automated Android Bug Replay with Large Language Models | - | 10.1145/3597503.3608137 |
| 37 | 2024 | 34 | AutoWebGLM: A Large Language Model-based Web Navigating Agent | - | 10.1145/3637528.3671620 |
| 38 | 2025 | 144 | LLM-Based Multi-Agent Systems for Software Engineering: Literature Review, Vision, and the Road Ahead | ACM Transactions on Software Engineering and Methodology | 10.1145/3712003 |
| 39 | 2023 | 27 | WebArena: A Realistic Web Environment for Building Autonomous Agents（OpenAlex上の題名は誤登録。arXiv原文で確認済み） | arXiv (Cornell University) | 10.48550/arxiv.2307.13854 |
| 40 | 2024 | 148 | Advancing Requirements Engineering Through Generative AI: Assessing the Role of LLMs | - | 10.1007/978-3-031-55642-5_6 |
| 41 | 2022 | 92 | RESTful API Testing Methodologies: Rationale, Challenges, and Solution Directions | Applied Sciences | 10.3390/app12094369 |

### F. 人間との協働・信頼

| # | 年 | 被引用 | 論文 | 掲載 | DOI |
|---|---|---|---|---|---|
| 42 | 2022 | 52 | Trust enhancement issues in program repair | Proceedings of the 44th International Conference on Software Engineering | 10.1145/3510003.3510040 |
| 43 | 2022 | 45 | Adaptive Testing and Debugging of NLP Models | Proceedings of the 60th Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers) | 10.18653/v1/2022.acl-long.230 |
| 44 | 2023 | 154 | Towards Human-Bot Collaborative Software Architecting with ChatGPT | - | 10.1145/3593434.3593468 |

## 3. 何が分かっているか（Established）

1. **UIからモデルを起こしてテストを回す枠組みは20年前に確立している。** GUI ripping（#1, 2004）→ Crawljax によるAjax状態遷移グラフ抽出（#3, 2012）→ モバイルのモデルベース探索（#17–#22）と系譜が連続しており、「画面を巡回して状態機械を作る」こと自体は新規性がない。
2. **テスト入力の自動生成は探索ベース（SBST）と記号実行で成熟している。** McMinnのサーベイ（#9）、Whole Test Suite Generation / EvoSuite（#9b）、CUTE（#10）。カバレッジという明確な適合度関数がある領域では、人手を上回る生成が可能。
3. **LLMは単体テスト生成でSBSTの弱点（カバレッジ・プラトー、可読性）を補える。** CodaMosa（#27）はSBSTが停滞した箇所にLLMを差し込み到達率を改善。TSE掲載の実証（#26）や ChatUniTest（#29）、ChatTester（#30）、変異テスト併用（#31）が続く。
4. **LLMエージェントはGUIを人間らしく操作できるところまで来た。** GPTDroid（#33）、AdbGPT（#36）、AutoWebGLM（#37）、WebArena（#39）。
5. **「何が正解か」の判定＝オラクル問題が依然として最大の障壁である。** Barrらのサーベイ（#13）が定式化した問題は、LLM時代にも解消していない（#25のサーベイが同様に指摘）。
6. **Webの E2E テストは壊れやすく、保守コストが本質的問題である。** ロケータ破損と修復（#5, #6, #7, #8）。

## 4. 何が分かっていないか（Gap＝本研究の空き地）

| # | 未解明の点 | 根拠 |
|---|---|---|
| G1 | **LLMテスト生成の研究はコード起点（単体テスト）に偏っており、「動いているWebサイトそのもの」を入力に、仕様書とテスト設計書を成果物として出す系統の実証がほぼ無い。** | #24–#32 はすべてソースコード or リポジトリを入力に取る。UI起点は#33–#37だがいずれも出力は「操作」であって「設計文書」ではない |
| G2 | **生成されたテスト設計の品質を、カバレッジ以外の尺度で評価する方法が確立していない。** | 既存研究の主指標は行/分岐カバレッジと欠陥検出数。テスト観点の網羅性・トレーサビリティ（ISO/IEC/IEEE 29119 のテスト設計技法）に基づく評価はレビュー範囲内で見つからなかった |
| G3 | **「LLMが出したテスト観点を人間QAがどこで承認・棄却するか」の設計知見が乏しい。** | HITL側の文献（#42–#45）はプログラム修復・NLPモデル・アーキテクチャ設計が対象で、テスト設計の段階承認を扱ったものは未発見 |
| G4 | **クロール由来の不完全な情報（ログイン壁・robots制限・部分取得）を前提にした、「不在を欠陥と断定しない」出力設計の研究が見当たらない。** | 探索型テスト研究は到達率を上げる方向の議論が中心で、到達できなかった範囲を成果物にどう明示するかは扱われていない |

## 5. 本研究の位置づけ（1文）

先行研究が「コードから単体テストを生成する」ことと「エージェントがGUIを操作する」ことを別々に進めてきたのに対し、本研究は **公開されているWebアプリの実挙動を入力として、人間QAが段階的に承認できる形式でテスト設計文書を生成し、その品質をカバレッジではなくテスト設計技法の観点網羅で評価する** 点に位置づけられる（G1＋G2＋G3を同時に扱う）。

## 6. 引用時の注意（このファイルの信頼度）

- 被引用数は **OpenAlex 2026-07-26時点**。論文の重複レコードがあり（例: #9 は同一論文に複数レコードが存在し値が1362/133/75に分裂）、絶対値を計画書に書くなら最新のGoogle Scholar値で取り直すこと。
- 本レビューで **abstract以上を読んだのは1本（WebArena, arXiv原文で題名を確認）のみ**。他44本はタイトル・掲載誌・被引用数のメタデータのみで採録しており、内容の要約は既知情報に基づく推定を含む。**計画書に書く前にセクション3・4の主張を支える論文（少なくとも#3, #13, #25, #26, #27, #33）は本文確認が必要。**
- ISO/IEC/IEEE 29119（ソフトウェアテスト規格）は論文ではないため表に含めていないが、G2の評価軸として引用する場合は規格原本を参照すること。
