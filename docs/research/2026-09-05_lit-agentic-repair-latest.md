# LLM エージェントによる自動修復 — 最新研究（2026-09-05 調査）

調査手段: Semantic Scholar Graph API（一部 429 でレート制限）／arXiv API。Google Scholar 不使用。
本文一次確認は行っていない（abstract ベース）。数値は各論文の abstract / 要約からの抽出であり、"実証" と明記した値のみ論文内で数値実証されたもの。

## 結論（3行以内）

- **非エージェント型パイプライン（Agentless）は、少なくとも 2024年時点の SWE-bench Lite では既存エージェント型より高精度・低コスト**（32.00% / $0.70）を実証済みだが、2025〜2026年はエージェント型・ハイブリッド型が SWE-bench Verified で 50〜77% まで急伸しており、「単純パイプラインが勝つ」という主張は年・ベンチマーク版で通用範囲が変わる。
- **LLM の自己修復（self-repair）は「限定的」が実証されている**：フィードバック品質に強くボトルネックされ、人間のフィードバックには及ばない（2023年実証）。一方 2026年の別研究は同じ「自己修復」でも表層バグでは大きく改善しうると報告しており、結論はバグの種類・ベンチマークで割れている。
- **パッチ正当性の自動判定は未解決問題として実証されている**：テスト通過が正しさを保証しない「Lucky Pass」が実測10.7%、さらに2026年の実証研究は「既存の過学習検出ツールはランダム選択に負ける」と報告している。

## 収集した論文（arXiv/Semantic Scholar 経由・abstract 確認分)

| # | 論文タイトル | 年 | arXiv/会議 | 被引用数 | URL | 一次確認 |
|---|---|---|---|---|---|---|
| 1 | SWE-bench: Can Language Models Resolve Real-World GitHub Issues? | 2023 | arXiv 2310.06770 / ICLR | 3,608 | https://www.semanticscholar.org/paper/94a5f96308729e31c1ffbc0f0618db87795092fe | 未実行(abstract) |
| 2 | Does SWE-Bench-Verified Test Agent Ability or Model Memory? | 2025 | arXiv 2512.10218 | 12 | https://www.semanticscholar.org/paper/f031232e7ed6ab33c59c546c4fa35062bb75c515 | 未実行 |
| 3 | Revisiting SWE-Bench: On the Importance of Data Quality for LLM-Based Code Models | 2025 | ICSE'25 Companion | 6 | https://www.semanticscholar.org/paper/b0fbc776cb4f9a09504f0720ff1e36910bdc5bc5 | 未実行 |
| 4 | UTBoost: Rigorous Evaluation of Coding Agents on SWE-Bench | 2025 | arXiv 2506.09289 / ACL | 45 | https://www.semanticscholar.org/paper/7e0d3c77e73a9aeb8e3ccc88e3fabc1d14fc16cc | 未実行 |
| 5 | The SWE-Bench Illusion: When SOTA LLMs Remember Instead of Reason | 2025 | arXiv 2506.12286 / SEIP@ICSE | 47 | https://www.semanticscholar.org/paper/a3ca45ea6d81a4a52d4ed8a38d79e31c0a82ef93 | 未実行 |
| 6 | MAGIS: LLM-Based Multi-Agent Framework for GitHub Issue Resolution | 2024 | arXiv 2403.17927 / NeurIPS | 197 | https://www.semanticscholar.org/paper/006c4c7470566327e5b02b94936d0be0033fc9f5 | 未実行 |
| 7 | Agentless: Demystifying LLM-based Software Engineering Agents | 2024 | arXiv 2407.01489 | 未取得(S2レート制限) | https://arxiv.org/abs/2407.01489 | 未実行 |
| 8 | SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering | 2024 | arXiv 2405.15793 | 未取得(S2レート制限) | https://arxiv.org/abs/2405.15793 | 未実行 |
| 9 | AutoCodeRover: Autonomous Program Improvement | 2024 | arXiv 2404.05427 | 未取得(S2レート制限) | https://arxiv.org/abs/2404.05427 | 未実行 |
| 10 | RepairAgent: An Autonomous, LLM-Based Agent for Program Repair | 2024 | arXiv 2403.17134 | 未取得(S2レート制限) | https://arxiv.org/abs/2403.17134 | 未実行 |
| 11 | SpecRover (AutoCodeRover拡張) | 2024 | arXiv 2408.02232 | 未取得 | https://arxiv.org/abs/2408.02232 | 未実行 |
| 12 | Is Self-Repair a Silver Bullet for Code Generation?（Olausson et al.） | 2023 | arXiv 2306.09896 | 未取得 | https://arxiv.org/abs/2306.09896 | 未実行 |
| 13 | How Many Tries Does It Take? Iterative Self-Repair in LLM Code Generation | 2026 | arXiv 2604.10508 | 未取得 | https://arxiv.org/abs/2604.10508 | 未実行 |
| 14 | Validation of Automatically Generated Patches: An Appetizer | 2019 | arXiv 1912.00117 | 未取得 | https://arxiv.org/abs/1912.00117 | 未実行 |
| 15 | Invalidator: Automated Patch Correctness Assessment via Semantic and Syntactic Reasoning | 2023 | arXiv 2301.01113 | 未取得 | https://arxiv.org/abs/2301.01113 | 未実行 |
| 16 | Unveiling Practical Shortcomings of Patch Overfitting Detection Techniques | 2026 | arXiv 2603.11262 | 未取得 | https://arxiv.org/abs/2603.11262 | 未実行 |
| 17 | Enhancing Repository-Level Software Repair via Repository-Aware Knowledge Graphs (KGCompass) | 2025 | arXiv 2503.21710 | 50 | https://www.semanticscholar.org/paper/42ed2516e0895da4c4863dcbf47fd1496380730c | 未実行 |
| 18 | Issue Localization via LLM-Driven Iterative Code Graph Searching (CoSIL) | 2025 | arXiv 2503.22424 / ASE | 21 | https://www.semanticscholar.org/paper/08839ffbd8dbbc8ecf5cf1b2218e95647a32842a | 未実行 |
| 19 | RGFL: Reasoning Guided Fault Localization for Automated Program Repair | 2026 | arXiv 2601.18044 | 未取得 | https://arxiv.org/abs/2601.18044 | 未実行 |
| 20 | AgentLens: Revealing The Lucky Pass Problem in SWE-Agent Evaluation | 2026 | arXiv 2605.12925 | 未取得 | https://arxiv.org/abs/2605.12925 | 未実行 |
| 21 | When Agents go Astray: Course-Correcting SWE Agents with PRMs | 2025 | arXiv 2509.02360 | 未取得 | https://arxiv.org/abs/2509.02360 | 未実行 |
| 22 | Kimi-Dev: Agentless Training as Skill Prior for SWE-Agents | 2025 | arXiv 2509.23045 | 未取得 | https://arxiv.org/abs/2509.23045 | 未実行 |

(以降、arXiv API から得た関連論文は本文中で個別に言及。全件は上表に収まらないため割愛)

## 各論文の要点

### 1. SWE-bench: Can Language Models Resolve Real-World GitHub Issues?（2023 / 被引用3,608）
- 主張: 2,294件の実 GitHub issue（12リポジトリ）から成るベンチマークを提案。LLM の実務的コード修正能力を測る。
- 実証の内容: 当時の LLM（GPT-4 等）は resolve rate が数% 台と低いことを提示（本調査では正確な数値を一次確認していないため引用しない）。
- 区分: 実証（ベンチマーク設計）。以降の数値は各後続研究に依存。
- **本件への含意**: 本件のオートヒーリングの評価軸そのもの。ただし後続研究（#2, #3, #5）が指摘する通り、そのまま「解決率」を信頼度の指標として使うのは危険。

### 2. Revisiting SWE-Bench: On the Importance of Data Quality（2025 / ICSE Companion）
- 主張: SWE-bench の「解決」判定には解答漏洩・弱いテストが混入しており、モデル能力を過大評価している。
- 実証の内容: 成功事例の **32.67% が解答漏洩（solution leakage）**、**31.08% が弱いテストケースの恩恵**を受けていたと報告。
- 区分: 実証。
- **本件への含意**: オートヒーリングの「再検証（テスト通過）→成功」という判定を無条件に信頼してはいけない。テスト強度自体を見直す設計が要る。

### 3. The SWE-Bench Illusion: When SOTA LLMs Remember Instead of Reason（2025 / SEIP@ICSE, 被引用47）
- 主張: 高い SWE-bench 性能の一部は学習データの記憶であり、真の推論ではない。
- 実証の内容: 未見リポジトリでの精度が既知リポジトリより有意に低いことを実測（具体的なポイント差は abstract からは未確認）。
- 区分: 実証（ただし本調査では効果量の具体的数値ポイントは未確認）。
- **本件への含意**: 自社アプリのコードは学習データに存在しない私有コードであるため、公開ベンチマークの解決率をそのまま自社への適用可能性の見積もりに使えない。

### 4. UTBoost: Rigorous Evaluation of Coding Agents on SWE-Bench（2025 / ACL, 被引用45）
- 主張: 既存の SWE-bench 評価用テストにも欠陥があり、リーダーボードの順位が誤っている。
- 実証の内容: LLM駆動のテスト生成で **345件の誤った合格パッチ** を検出し、順位を修正。
- 区分: 実証。
- **本件への含意**: 自動判定（テスト通過=成功）に依存するオートヒーリングのゲートは、テスト自体の脆弱性の影響を受ける。人間レビューを外さない設計の根拠になる。

### 5. Agentless: Demystifying LLM-based Software Engineering Agents（2024, arXiv 2407.01489）
- 主張: 複雑なエージェント（ツール呼び出し・行動計画）は不要であり、「局所化→修復→パッチ検証」の単純な3段パイプラインで十分。
- 実証の内容: SWE-bench Lite（300件）にて、**解決率 32.00%（96/300）・コスト $0.70/issue** を達成し、比較対象のオープンソースエージェント群の中で最高性能かつ最低コストと報告（原文: "the simplistic Agentless is able to achieve both the highest performance (32.00%, 96 correct fixes) and low cost ($0.70)"）。
- 区分: 実証（ただし比較対象エージェント個々の具体的ポイント差は本調査で未抽出。「最高性能」という定性的主張は原文で確認済み、正確な差分ポイントは未確認）。
- **本件への含意**: 依頼のオートヒーリングは「検証→構造化→修正案→修正→PR」というまさにパイプライン型。エージェント型（自律計画）を最初から採用する必然性は薄く、まず単純パイプラインで精度・コストを測ってから複雑化するのが合理的。

### 6. SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering（2024, arXiv 2405.15793）
- 主張: エージェント専用の「エージェント-コンピュータインタフェース（ACI）」を設計すると自律修正性能が上がる。
- 実証の内容: 発表時点で SWE-bench **pass@1 12.5%** を達成（当時の SOTA）。
- 区分: 実証。
- **本件への含意**: エージェント型の代表的アーキテクチャ。ただし発表から1年強で他手法（Agentless, MAGIS, 派生研究）に精度で追い越されており、単体アーキテクチャの優位は短命。

### 7. MAGIS: LLM-Based Multi-Agent Framework for GitHub Issue Resolution（2024 / NeurIPS, 被引用197）
- 主張: Manager・Repository Custodian・Developer・QA Engineer の役割分担型マルチエージェントで issue 解決を改善できる。
- 実証の内容: SWE-bench（フル2,294件）で **解決率13.94%**、GPT-4直接適用比で **8倍** の解決率向上。
- 区分: 実証。
- **本件への含意**: 役割分離（検証役・修正役・レビュー役を分ける）は効果が実証されている設計パターン。依頼の「修正エージェントは並列・差し替え可能」という要件と整合する。

### 8. AutoCodeRover: Autonomous Program Improvement（2024, arXiv 2404.05427）
- 主張: AST解析＋スペクトラムベース欠陥限局＋LLMコード検索で自律的に issue を解決。
- 実証の内容: SWE-bench Lite で **解決率19%**、平均コスト **$0.43/issue**。
- 区分: 実証。
- **本件への含意**: 欠陥限局の精度がコストと解決率の両方に効くという設計思想が、後続の CoSIL/KGCompass/RGFL（#17-19）でも一貫して支持されている。

### 9. RepairAgent: An Autonomous, LLM-Based Agent for Program Repair（2024, arXiv 2403.17134）
- 主張: 情報収集・修復材料収集・検証を自律的に織り交ぜる、プログラム修復専用の自律エージェント。
- 実証の内容: Defects4J で **164件のバグを自律修復**（うち39件は既存手法未解決）、**平均コスト約27万トークン/バグ（$0.14）**。
- 区分: 実証（ベンチマークは Defects4J であり SWE-bench とは別系統。直接比較不可）。
- **本件への含意**: 1件あたりコストの参考値として使える（ただしベンチマーク差を明記して引用すること）。

### 10. Is Self-Repair a Silver Bullet for Code Generation?（Olausson et al., 2023, arXiv 2306.09896）
- 主張: LLM の自己修復（自分の出力を自分でフィードバックして直す）は万能ではない。
- 実証の内容: Code Llama / GPT-3.5 / GPT-4 を HumanEval・APPS で評価。原文: "performance gains are often modest, vary a lot between subsets of the data, and are sometimes not present at all"。自己修復の効果はフィードバック品質にボトルネックされ、**人間によるデバッグ助言がLLM自身の自己フィードバックより有意に優れる**と報告。
- 区分: 実証。
- **本件への含意**: 「修正エージェントが自分の出したパッチの妥当性を自己判定する」設計は過信できない。本件が既に想定している「人間が画面上で判断する」ステップは、この実証結果からも省略不可。

### 11. How Many Tries Does It Take? Iterative Self-Repair in LLM Code Generation（2026, arXiv 2604.10508）
- 主張: 反復回数を増やした自己修復はモデル横断で一貫して有効。
- 実証の内容: 7モデル×HumanEval/MBPPで反復自己修復を評価。**HumanEval +4.9〜17.1pt、MBPP +16.0〜30.0pt** の解決率改善。ただし **assertionエラー（ロジックの誤り）は正答率約45%と最も直しにくい**、構文/命名エラーは高い成功率。
- 区分: 実証。
- **本件への含意**: #10 と一見矛盾するが、対象が異なる（構文・単純ミス中心のベンチマーク vs 実務issue）。実運用の欠陥はロジック誤りが多いと想定されるため、#10 の悲観的知見の方が本件に近い。

### 12. Unveiling Practical Shortcomings of Patch Overfitting Detection Techniques（2026, arXiv 2603.11262）
- 主張: 既存の「パッチ過学習検出（テスト通過だが実は不正解のパッチを見抜く）」手法は、現実的なデータでは機能不全。
- 実証の内容: 6つの過学習検出手法を現実的データでベンチマークした結果、**単純なランダム選択が大半のケースで全ての検出ツールを上回った**。
- 区分: 実証。
- **本件への含意**: 「テストが通ったら正しい」という自動判定はもちろん、「機械学習で正しさを判定する」という高度化も、現状では実務水準に届いていない。本件のPRベースの人間判断フローは、この実証結果を踏まえると省略してはならない必須ステップ。

### 13. AgentLens: Revealing The Lucky Pass Problem in SWE-Agent Evaluation（2026, arXiv 2605.12925）
- 主張: テストが通っても、その解決プロセスが場当たり的（試行錯誤・後戻り・検証省略）な「Lucky Pass」が一定割合存在する。
- 実証の内容: OpenHands の2,614軌跡（8モデル、SWE-bench Verified 60タスク）を分析。合格軌跡のうち **10.7%がLucky Pass**（モデル間で0.5%〜23.2%までばらつき）。プロセス品質でモデルを再順位付けすると、**最大5位の順位変動**が生じた。
- 区分: 実証。
- **本件への含意**: 「テスト通過=解決」という単純なバイナリ判定は、修正エージェントの信頼性評価には不十分。プロセス（差分の妥当性・修正理由）まで人間かレビューエージェントが見る必要がある。

### 14. KGCompass: Enhancing Repository-Level Software Repair via Repository-Aware Knowledge Graphs（2025, arXiv 2503.21710, 被引用50）
- 主張: リポジトリ全体をナレッジグラフ化し、欠陥限局を多段階のグラフ探索で行う。
- 実証の内容: 正しく局所化できたバグのうち **89.7%は明示的な手がかり（issue文中のファイル名等）を含まない**、つまり多くの実バグはテキスト一致では見つからない。グラフベース手法で **修復成功率58.3%**（純LLMベースラインより大幅に高い、と報告。具体的なベースライン値は未確認）。
- 区分: 実証。
- **本件への含意**: 「バグレポートの構造化」だけでは欠陥限局に不十分な可能性が高い。リポジトリ横断のコンテキスト取得（依存関係・呼び出しグラフ）を修正エージェントの前段に組み込む価値が実証されている。

### 15. CoSIL: Issue Localization via LLM-Driven Iterative Code Graph Searching（2025 / ASE, arXiv 2503.22424, 被引用21）
- 主張: コードグラフを反復探索することで欠陥限局精度を上げ、下流の修復に寄与する。
- 実証の内容: SWE-bench Lite/Verified で **Top-1局所化精度43.3%/44.6%**。これを Agentless に組み込むと **解決率が2.98〜30.5ポイント改善**（改善幅の広さはタスク難易度に依存と推定、要因分析は未確認）。
- 区分: 実証。
- **本件への含意**: 欠陥限局の精度改善が、そのまま最終解決率に大きく波及することを複数論文（#14, #15, #19）が一貫して支持。本件の「バグ構造化」フェーズへの投資対効果が高いことの根拠になる。

### 16. RGFL: Reasoning Guided Fault Localization for Automated Program Repair（2026, arXiv 2601.18044）
- 主張: 推論過程を明示的にガイドすることで欠陥限局精度を上げる。
- 実証の内容: SWE-bench Verified でファイルレベル局所化 Hit@1 を **71.4%→85%** に改善、Agentless に統合すると **エンドツーエンド修復率+12.8pt**。
- 区分: 実証。
- **本件への含意**: #15と合わせ、局所化精度→解決率の感応度が2025〜2026年の複数独立研究で再現されている頑健な知見。

### 17. When Agents go Astray: Course-Correcting SWE Agents with PRMs（2025, arXiv 2509.02360）
- 主張: プロセス報酬モデル（PRM）でエージェントの軌跡を途中介入・修正すると解決率が上がる。
- 実証の内容: 解決率を **40.0%→50.6%（+10.6pt）** に改善（ベンチマーク・ベースモデルの詳細は本調査で未確認）。
- 区分: 実証。
- **本件への含意**: 「修正エージェントを走らせっぱなしにしない」軌跡監視・介入の価値が実証されている。並列エージェントの品質管理に転用可能な発想。

### 18. Kimi-Dev: Agentless Training as Skill Prior for SWE-Agents（2025, arXiv 2509.23045）
- 主張: 「非エージェント型（Agentless）の学習で身につけたスキル」をエージェント型に転移させるハイブリッドが有効。
- 実証の内容: SWE-bench Verified で高い解決率を報告（**60.4%** と要約した抽出と **48.6%** と要約した抽出が食い違った。一次資料未確認のため下表・引用不可リストに分離して記載）。
- 区分: 主張は実証済みだが、具体数値は本調査では確定できず「未確認」。
- **本件への含意**: 2024年の「Agentless vs エージェント」の二項対立は、2025年以降「Agentless流の学習/設計思想＋エージェント的実行」のハイブリッドに収束しつつある可能性。ただし数値未確定のため設計判断の主根拠にはしない。

## 数値の比較表（解決率）

**注意: SWE-bench には無印（フル2,294件）／Lite（300件）／Verified（人手フィルタ500件）の3系統があり、年も手法も異なるため直接比較不可。** 参考値として横並びにするが、優劣の断定はしない。

| 手法 | ベンチマーク | 解決率 | 1件あたりコスト | 出典 |
|---|---|---|---|---|
| SWE-agent（エージェント型・ACI） | SWE-bench（無印, 2024時点） | 12.5% (pass@1) | 未確認 | Yang et al. 2024, arXiv 2405.15793 |
| MAGIS（マルチエージェント） | SWE-bench（無印） | 13.94%（GPT-4直接比 8倍） | 未確認 | Luo et al. 2024, arXiv 2403.17927 |
| AutoCodeRover（エージェント型） | SWE-bench Lite | 19% | $0.43 | Zhang et al. 2024, arXiv 2404.05427 |
| SpecRover（AutoCodeRover拡張） | SWE-bench Lite | AutoCodeRoverから効力+50%（絶対値未確認） | $0.65 | Ma et al. 2024, arXiv 2408.02232 |
| Agentless（非エージェント・パイプライン） | SWE-bench Lite | 32.00%（96/300） | $0.70 | Xia et al. 2024, arXiv 2407.01489 |
| CGM（オープンウェイト） | SWE-bench Lite | 43.00% | 未確認 | 2025, arXiv 2505.16901 |
| R2E-Gym | SWE-bench Verified | 51% | 未確認 | 2025, arXiv 2504.07164 |
| Agentic Rubrics | SWE-bench Verified | 54.2% | 未確認 | 2026, arXiv 2601.04171 |
| Context as a Tool（長期文脈管理） | SWE-bench Verified | 57.6% | 未確認 | 2025, arXiv 2512.22087 |
| Kimi-Dev（Agentless学習+エージェント適応） | SWE-bench Verified | 60.4% または 48.6%（**数値未確定・下記リスト参照**） | 未確認 | 2025, arXiv 2509.23045 |
| Fail-Fast Restart-Smart | SWE-bench（版未確認） | 71.8% | トークン14.6〜20.4%削減 | 2026, arXiv 2608.03222 |
| Live-SWE-agent（自己進化） | SWE-bench Verified | 77.4% | 未確認 | 2025, arXiv 2511.13646 |
| RepairAgent（別系統ベンチマーク） | Defects4J | 164件解決（既存未解決39件含む） | $0.14（27万トークン/バグ） | Bouzenia et al. 2024, arXiv 2403.17134 |
| GSO（性能最適化タスク・別種の難度） | GSO（102タスク） | <5% | 未確認 | 2025, arXiv 2505.23671 |

## 研究間で結論が割れている点

- **「単純パイプラインがエージェントに勝つか」**: Agentless（#5, 2024）は「勝つ」と実証（SWE-bench Lite, 32.00% vs 既存エージェント群中最高）。しかし2025〜2026年のエージェント型・ハイブリッド型（Live-SWE-agent 77.4%, Context as a Tool 57.6% 等、いずれも SWE-bench Verified）は Agentless 単体の初出値を大きく上回っている。**ただしベンチマーク版（Lite vs Verified）・年・ベースLLMが全て異なるため、これは「エージェントが後から逆転した」証拠ではなく、直接比較不能な数値を並べているだけ**という留保がつく。統合せず両論併記する。
- **自己修復の有効性**: Olausson et al. 2023（#10）は「効果は限定的・時に皆無、人間フィードバックに劣る」と実証。2026年の反復自己修復研究（#11）は「HumanEval/MBPPで一貫して有効（+5〜30pt）」と実証。対象ベンチマーク（構文/単純ミス中心 vs 実務issue相当）が異なるため、単純な矛盾ではなく「バグの種類依存」の可能性が高いが、これも推測であり未検証。
- **パッチ正当性の自動判定可能性**: Invalidator（2023, 79%精度）・RePaCA（2025, 83.1%精度）は「学習ベースの過学習検出は一定精度で機能する」と実証。一方 #12（2026）は「現実的データではランダム選択が既存検出ツール群を上回る」と実証。评価データの現実性（realistic data）の違いが原因の可能性があるが、断定はしない。

## 本件の設計に効く教訓

1. **「テスト通過=修正成功」を自動確定条件にしない。** UTBoost（誤ったパッチ345件検出）・AgentLens（Lucky Pass 10.7%）・過学習検出研究（#12, ランダム選択に劣る自動判定）が独立に、テスト通過だけでは正しさを保証できないと実証している。依頼仕様の「人間が画面上で判断」ステップは、この実証結果群からも省略してはならない。
2. **欠陥限局・リポジトリ理解への投資は解決率に直結する。** KGCompass・CoSIL・RGFLの3系統が独立に、局所化精度の改善が最終解決率を数〜30ポイント押し上げると実証している。バグレポート構造化フェーズにコンテキスト取得（呼び出しグラフ・依存関係）を組み込む価値が高い。
3. **修正エージェントの自己判定を過信しない。** Olausson et al. 2023 の実証（自己修復は人間フィードバックに劣る）に加え、依頼仕様通り「修正案の提示→人間判断→再検証」のループを外さないことが、複数の独立研究の知見と整合する設計。

## 引用してはいけない数値

- **Kimi-Dev の SWE-bench Verified 解決率**: 60.4%（Agentless比較文脈での抽出）と 48.6%（SWE-agent系検索での抽出）の**2つの異なる値が出た**。どちらも一次資料（arXiv 2509.23045 本文）を確認していないため、いずれの数値も設計判断の根拠にしない。
- **SpecRover の絶対解決率**: 「AutoCodeRoverから+50%の効力改善」という相対値のみ確認。絶対的な解決率（%）は本調査では未確認。
- **The SWE-Bench Illusion の具体的ポイント差**（既知/未知リポジトリ間の精度差）: 「有意に低い」という定性的記述のみ確認、数値は未確認。
- ベンダーブログ・マーケティング記事の数値: 本調査では一切使用していない（OpenAI/Anthropic/Google公式のSWE-bench Verifiedリーダーボード自己申告値は意図的に対象外とした）。

## 見つからなかったもの（どう検索したか）

- **「並列マルチエージェント（同一issueに複数インスタンスを同時投入し多数決/アンサンブルする）」のコスト対精度トレードオフを直接測った研究**は見つからなかった。Semantic Scholar で `multi-agent large language model software engineering collaboration cost` を検索したが、関連度の高い結果は得られず（データ分析用マルチエージェント論文などノイズが多かった）。役割分担型マルチエージェント（MAGIS）や軌跡途中介入（PRM）は見つかったが、「並列実行本数 vs 精度・コストの曲線」を扱う専用研究は本調査の範囲内（18回のツール実行）では特定できなかった。
- Semantic Scholar Graph API は同一メッセージ内での並列リクエストの一部が **HTTP 429（レート制限）** となり、"SWE-Bench Verified critique/contamination"「Agentless」「self-repair own code」「AutoCodeRover」「RepairAgent」の5クエリは代替として arXiv API で再検索し直した。Semantic Scholar 側の被引用数が取得できなかった論文（Agentless, SWE-agent, AutoCodeRover, RepairAgent, SpecRover 等）は上表で「未取得」と明記した。
