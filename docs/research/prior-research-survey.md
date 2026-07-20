# 先行研究サーベイ — WebSpec2Doc の位置づけ

- 作成: 2026-07-20
- 目的: 「何がわかっていて、何がわかっていないか」を明確にし、本研究（WebSpec2Doc）の位置づけを定める
- 調査手順: (1) キーワード検索 → (2) 被引用の多い論文から精読 → (3) その論文の引用文献を辿る → (4) 最新論文で現在地を確認。**古典と最新の両方**を押さえる方針

> **文献情報の確度について（重要）**
> 本サーベイは Web 検索で収集・確認したもので、Google Scholar / CiNii の被引用数を直接取得したものではありません。
> 研究計画書へ引用する前に、各文献の書誌情報（著者・巻号・ページ・年）と被引用数を Scholar / CiNii で再確認してください。
> 本文中の【古典】は分野で定番として繰り返し参照される文献、【最新】は 2024 年以降の動向を指します。

---

## 1. クラスタ別 文献リスト（30本）

### A. 画面モデルの自動推論（クロール／GUI リッピング）

| # | 文献 | 位置づけ |
|---|---|---|
| 1 | Memon, Banerjee, Nagarajan. *GUI Ripping: Reverse Engineering of Graphical User Interfaces for Testing*. WCRE 2003 | 【古典】実行可能な GUI から構造（GUI Forest / Event-Flow Graph）を逆生成する原型 |
| 2 | Memon. *An event-flow model of GUI-based applications for testing*. STVR 17(3), 2007 | 【古典】モデルを一本化し、イベント空間探索戦略として体系化 |
| 3 | Mesbah, van Deursen, Lenselink. *Crawling Ajax-Based Web Applications through Dynamic Analysis of User Interface State Changes*. ACM TWEB 6(1), 2012（Crawljax） | 【古典】DOM 状態差分で動的 Web の状態遷移グラフを推論。本領域の基準点 |
| 4 | Mesbah. *Crawl-based analysis of web applications: Prospects and challenges*. Science of Computer Programming, 2015 | クロール型解析の展望と限界の整理 |
| 5 | *Fragment-Based Test Generation For Web Apps*. arXiv:2110.14043 | 画面断片単位でのテスト生成 |

### B. テスト網羅基準・設計技法

| # | 文献 | 位置づけ |
|---|---|---|
| 6 | Ammann, Offutt. *Introduction to Software Testing* (2nd ed.), 2016 | 【古典】プライムパス網羅などグラフ網羅基準の標準的定式化 |
| 7 | Kuhn, Kacker, Lei. *Practical Combinatorial Testing*. NIST SP 800-142, 2010 | 【古典】組合せ（ペアワイズ）テストの実務的基盤 |
| 8 | Chen, Cheung, Yiu. *Metamorphic Testing*（初出 1998）／ Chen et al. *Metamorphic Testing: A Review of Challenges and Opportunities*. ACM CSUR, 2018 | 【古典＋レビュー】期待結果が確定できない場合の検証手法 |

### C. オラクル問題（本研究の核心に直結）

| # | 文献 | 位置づけ |
|---|---|---|
| 9 | **Barr, Harman, McMinn, Shahbaz, Yoo. *The Oracle Problem in Software Testing: A Survey*. IEEE TSE 41(5):507–525, 2015** | 【古典・最重要】「正しい振る舞いをどう判定するか」が自動化の本質的ボトルネックであることを体系化。被引用 1000 超 |
| 10 | *Test Oracle Automation in the era of LLMs*. arXiv:2405.12766, 2024 | 【最新】LLM でオラクル問題がどこまで動いたかの現在地 |

### D. 表示・レイアウト・ビジュアル回帰

| # | 文献 | 位置づけ |
|---|---|---|
| 11 | Mahajan, Halfond. *WebSee: A Tool for Debugging HTML Presentation Failures*. ICST 2015 | 【古典】画像差分による表示故障の検出と HTML/CSS への原因局所化 |
| 12 | Walsh, Kapfhammer, McMinn. *ReDeCheck: Automated layout failure detection for responsive web pages*. ISSTA 2017 | 【古典】重なり・はみ出し等のレイアウト故障の自動検出 |
| 13 | *Beyond Pixel Diffs: Benchmarking Image Change Captioning for Web UI Visual Regression Testing*. arXiv:2607.01728 | 【最新】画素差分を超えた変更の意味づけ。現新比較の最前線 |

### E. 不安定テスト（flaky）と待機戦略

| # | 文献 | 位置づけ |
|---|---|---|
| 14 | **Luo, Hariri, Eloussi, Marinov. *An Empirical Analysis of Flaky Tests*. FSE 2014** | 【古典】flaky の原因分類。最大要因が非同期待ち（async wait）であることを実証 |
| 15 | *Robust waiting strategies for web GUI testing in industrial software systems*. ASE 2024 | 【最新】産業システムにおける待機戦略。10 年後も同じ問題が残る証拠 |

### F. テスト資産の保守性

| # | 文献 | 位置づけ |
|---|---|---|
| 16 | Stocco, Leotta, Ricca, Tonella. *APOGEN: Automatic Page Object Generation for Web Applications* | Page Object の自動生成による保守性向上 |

### G. トレーサビリティ復元

| # | 文献 | 位置づけ |
|---|---|---|
| 17 | **Antoniol, Canfora, Casazza, De Lucia, Merlo. *Recovering Traceability Links between Code and Documentation*. IEEE TSE 28(10), 2002** | 【古典】情報検索（TF-IDF）による成果物間リンク復元。文書と実装を結ぶ原点 |

### H. アクセシビリティ自動評価の「限界」（主張範囲の定量的根拠）

| # | 文献 | 位置づけ |
|---|---|---|
| 18 | **Vigo, Brown, Conway. *Benchmarking web accessibility evaluation tools: measuring the harm of sole reliance on automated tests*. W4A 2013** | 【古典・決定的】8 ツールを比較し、**カバレッジ最大 32.4%／完全性 10–59%／正確性 平均 70.7%** を実測。自動検査のみに依存する危険を定量化 |
| 19 | *Automated Evaluation Tools for Web and Mobile Accessibility: A Systematic Literature Review*, 2022 | SLR による全体像 |
| 20 | *Web accessibility automatic evaluation tools: to what extent can they be automated?* CCF Trans. Pervasive Computing and Interaction, 2023 | 【最新】どの達成基準が自動化可能かの切り分け |

### I. ユーザビリティの自動検出

| # | 文献 | 位置づけ |
|---|---|---|
| 21 | Grigera, Garrido, Rivero, Rossi. *Automatic detection of usability smells in web applications*. IJHCS, 2017 | 操作ログ・UI 構造から使いにくさの兆候を検出 |

### J. 深いクロールとデータフロー

| # | 文献 | 位置づけ |
|---|---|---|
| 22 | Eriksson, Pellegrino, Sabelfeld. *Black Widow: Blackbox Data-driven Web Scanning*. IEEE S&P 2021 | 画面をまたぐデータ依存を辿る深いクロール。到達性の限界を押し広げた |

### K. LLM 時代の現在地【最新】

| # | 文献 | 位置づけ |
|---|---|---|
| 23 | Wang et al. *Software Testing with Large Language Models: Survey, Landscape, and Vision*. IEEE TSE, 2024 | LLM×テストの全体地図 |
| 24 | *Large Language Model-Brained GUI Agents: A Survey*. arXiv:2411.18279, 2024 | GUI エージェントの系譜と構成要素 |
| 25 | *Large Language Models for Software Testing: A Research Roadmap*. arXiv:2509.25043 | 未解決課題のロードマップ |
| 26 | *Temac: Multi-Agent Collaboration for Automated Web GUI Testing*. arXiv:2506.00520 | マルチエージェントによる Web GUI テスト |
| 27 | *LLM-Assisted Model-Based GUI Testing for Vue.js Web Applications*. arXiv:2606.27665 | モデルベース＋LLM の融合 |
| 28 | *TestEval: Benchmarking Large Language Models for Test Case Generation*. NAACL Findings 2025 | 生成能力のベンチマーク |
| 29 | *Leveraging Large Vision-Language Models for Automatic Web GUI Testing*. ICSME 2024 | 視覚言語モデルの適用 |
| 30 | *Intent-Driven Mobile GUI Testing with Autonomous LLM Agents*. ICST 2024 | 意図駆動の自律エージェント |

---

## 2. 何がわかっているか（Established）

1. **画面のモデル推論は成熟している。** GUI リッピング（2003）から Crawljax（2012）を経て、実行中のアプリから状態遷移グラフを起こす技術は 20 年の蓄積があり、再発明の価値は低い。
2. **網羅基準と組合せ技法は理論的に確立している。** プライムパス網羅（Ammann & Offutt）、ペアワイズ（NIST）は定式化済みで、実装は工学問題に落ちている。
3. **オラクル問題は本質的に未解決である。** Barr et al.(2015) が体系化したとおり、「観測した振る舞いが正しいか」の判定は自動化の最大のボトルネックであり、LLM 時代でも解消していない（#10, #25）。
4. **自動検査で到達できる範囲は限定的で、その限界は定量化されている。** アクセシビリティでは自動ツールのカバレッジは最大 32.4%、完全性 10–59%（Vigo et al. 2013）。**自動検査の「指摘なし」は「問題なし」を意味しない**ことが実証されている。
5. **flaky の主因は非同期待ちである。** Luo et al.(2014) の分類は 10 年後の産業研究（#15）でも再確認されており、生成したテストの信頼性設計には待機戦略が不可欠。
6. **テスト生成そのものはコモディティ化しつつある。** LLM／エージェントによる Web GUI テスト生成は 2024–2026 で急速に一般化した（#23–#30）。

## 3. 何がわかっていないか（Gaps）

> ここが本研究の空白地帯であり、位置づけの根拠になる。

**G1. 「主張範囲（claim_scope）」を成果物に埋め込む設計が研究されていない。**
自動検査の限界は #18–#20 で定量化されているにもかかわらず、ツールの出力が「**未検証**」と「**非該当**」と「**問題なし**」を区別して報告する設計論はほぼ存在しない。多くのツールは指摘の有無しか返さず、読み手が「不在の証明」と誤読する構造的リスクを放置している。オラクル問題（#9）の帰結を、**レポートの表現形式の問題として扱った研究は見当たらない。**

**G2. 実測から ISO/IEC/IEEE 29119 のテスト文書体系を自動生成する研究がほぼない。**
既存研究の出力は「テストケース」または「不具合指摘」で止まる。テスト分析・テスト設計・**テスト計画**といった上位文書を、実測した画面・入力・遷移から体系的に生成する試みは空白である。実務では 29119 準拠の文書が要求されるのに、研究と実務の間に断絶がある。

**G3. 要件文書と実測画面を突合し、それをテスト設計の入力にする体系がない。**
Antoniol et al.(#17) のトレーサビリティ復元は「コード↔文書」であり、「**要件文書↔実測画面↔生成テスト**」の三点を結んでテスト設計を駆動する枠組みには至っていない。LLM 研究（#23–#30）も入力は主に URL／画面であり、**文書駆動**は主流ではない。

**G4. 「観測できないこと」に直面したときの停止しない設計が扱われていない。**
対応ブラウザ・認証ロール・副作用の扱い・合否基準は観測では決まらない。既存研究は前提を人手で与える設定を置くが、**前提を自動で置いて走り切り、置いた前提を成果物に明示する**という運用設計は研究対象になっていない。

**G5. 現新比較（ドリフト検知）におけるベースライン不在の扱いが体系化されていない。**
ビジュアル回帰研究（#11–#13）は「比較対象がある」ことを前提とする。**初回実行時は比較が原理的に成立しない**という事実をユーザーにどう伝え、基準確立フェーズをどう位置づけるかは論じられていない。

## 4. 本研究（WebSpec2Doc）の位置づけ

> **既存研究が強い領域では戦わない。空白（G1–G5）に賭ける。**

- **やらないこと（コモディティ）**: 画面グラフの推論そのもの、LLM によるテストケース生成の精度競争。ここは #3, #23–#30 に対して優位を主張できない。
- **本研究の主張**:
  1. **証跡と主張範囲を第一級の成果物として設計する**（G1）。全出力に claim_scope を付与し、「未検証」を「非該当」や「問題なし」と決して混同させない。Barr の オラクル問題と Vigo の定量的限界を、**レポート設計の要件**として引き受ける。
  2. **実測から 29119 準拠の文書体系（分析・設計・ケース・計画）を生成する**（G2）。研究の出力単位を「テストケース」から「テスト文書一式」へ引き上げる。
  3. **文書駆動**——要件文書と実測画面を突合し、テスト設計を駆動する（G3）。Antoniol の系譜を三点接続へ拡張する。
  4. **止まらない実行と前提の明示**（G4）。観測で決まらない事項は前提化して走り切り、前提をレポートに残す。
  5. **ベースライン不在を正直に扱うドリフト検知**（G5）。初回は「基準確立のみ」と明示する。

## 5. 次の一手

- [ ] 各文献の書誌情報と被引用数を Google Scholar / CiNii で確認し、本表を確定させる
- [ ] G1（claim_scope の設計論）に絞って、さらに引用網を辿る（Barr et al. の被引用文献から、報告様式・不確実性提示を扱うものを抽出）
- [ ] 実務事例の補強: 医療機器企業の E2E 最適化事例（Berry, Zenn）——flaky 対策の「不在アサーションの前に positive landmark を要求する」は、G1 と同じ問題意識に実務側から到達した例として引用価値がある
- [ ] 空白 G2 について、29119 と自動生成を結びつけた文献が本当に無いかを重点確認（無いことの確認は慎重に。**無いことの証明はできない**ため「調査範囲では見当たらない」と記述する）
