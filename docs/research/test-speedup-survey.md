# テスト高速化の先行研究サーベイと施策

- 作成: 2026-07-20
- 目的: E2E の実行時間を、勘ではなく**先行研究の知見に基づいて**徹底的に short にする
- 調査手順: キーワード検索 → 被引用の多い論文 → その引用網 → 最新論文で現在地。**古典＋最新**の両方

> **書誌情報の確度**: Web 検索で確認したもので、Scholar / CiNii の被引用数を直接取得したものではない。
> 引用前に再確認すること。★ は検索で書誌・数値を確認できたもの。

---

## 1. 文献リスト

### A. 総説（ここから読む）

| # | 文献 | 要点 |
|---|---|---|
| 1★ | **Yoo, Harman. _Regression testing minimization, selection and prioritization: a survey_. STVR 22(2):67–120, 2012**（被引用 **1,440**） | 【古典・最重要】テスト削減を **Minimization（減らす）／Selection（選ぶ）／Prioritization（並べ替える）** の3戦略に整理。本分野の地図 |

### B. 古典 — 回帰テスト選択（RTS）

| # | 文献 | 要点 |
|---|---|---|
| 2★ | Rothermel, Harrold. _A Safe, Efficient Regression Test Selection Technique_. ACM TOSEM 6(2):173–210, 1997 | 【古典】制御フローグラフの差分から「変更コードを通るテスト」だけを選ぶ。**safe**（欠陥検出力を落とさない）概念の定式化 |
| 3★ | Rothermel, Harrold. _Empirical Studies of a Safe Regression Test Selection Technique_. IEEE TSE, 1998 | 実証評価 |
| 4 | Rothermel, Untch, Chu, Harrold. _Prioritizing Test Cases for Regression Testing_. IEEE TSE 27(10), 2001 | 【古典】早く失敗を出す順に並べる |
| 5 | Harrold, Gupta, Soffa. _A Methodology for Controlling the Size of a Test Suite_. ACM TOSEM 2(3), 1993 | 【古典】スイート縮小の原典 |
| 6 | Elbaum, Malishevsky, Rothermel. _Test Case Prioritization: A Family of Empirical Studies_. IEEE TSE, 2002 | 優先順位付けの効果測定 |

### C. 現代の RTS 実装（実測値がある）

| # | 文献 | 要点 |
|---|---|---|
| 7★ | **Gligoric, Eloussi, Marinov. _Practical Regression Test Selection with Dynamic File Dependencies_ (Ekstazi). ISSTA 2015** | テストが依存する**ファイル**を動的に記録し、変更時に関連テストだけ実行。32プロジェクト・615リビジョン・約500万行で検証し、**平均32%短縮／長時間スイートでは54%短縮** |
| 8★ | Gligoric et al. _Ekstazi: Lightweight Test Selection_. ICSE Demo 2015 | 実装 |
| 9★ | Legunsen et al. _An Extensive Study of Static Regression Test Selection in Modern Software Evolution_. FSE 2016 | 静的 RTS の限界 |
| 10★ | Vasic et al. _File-level vs. Module-level Regression Test Selection for .NET_. FSE 2017 | 粒度の比較。**ファイル単位が実用的** |

### D. 産業規模の現在地【最新寄り】

| # | 文献 | 要点 |
|---|---|---|
| 11★ | **Memon, Gao et al. _Taming Google-Scale Continuous Testing_. ICSE-SEIP 2017** | Google ですら全変更の全回帰テストは不可能。コード・テスト・開発者・変更頻度の**相関をモデル化**してテスト負荷を制御 |
| 12★ | **Machalica, Samylkin, Porth, Chandra. _Predictive Test Selection_. arXiv:1810.05286 / ICSE-SEIP 2019** | 過去のテスト結果から**機械学習（勾配ブースティング木）**で実行対象を選択。**インフラコスト半減**しつつ、個々のテスト失敗の **95%以上**、欠陥のある変更の **99.9%以上**を検出 |
| 13★ | Google. _Advances in Continuous Integration Testing @Google_ | 大規模 CI の実務 |

### E. flaky = 再実行コスト（速度に直結）

| # | 文献 | 要点 |
|---|---|---|
| 14★ | **Luo, Hariri, Eloussi, Marinov. _An Empirical Analysis of Flaky Tests_. FSE 2014** | 【古典】flaky の原因分類。**最大要因は非同期待ち（async wait）** |
| 15★ | Parry, Kapfhammer, Hilton, McMinn. _Test flakiness' causes, detection, impact and responses: A multivocal review_. JSS, 2023 | 【総説】原因・検出・影響・対処の全体像 |
| 16★ | Parry et al. _Empirically Evaluating Flaky Test Detection Techniques Combining Test Case Rerunning and Machine Learning Models_. EMSE 28(72), 2023 | 再実行 vs ML |
| 17★ | **Parry et al. _Systemic Flakiness: An Empirical Analysis of Co-Occurring Flaky Test Failures_. EASE 2025** | 【最新】flaky は独立でなく**共起する**。根本原因を1つ潰すと複数が治る |
| 18★ | Gruber, Parry et al. _Do Automatic Test Generation Tools Generate Flaky Tests?_ ICSE 2024 | 【最新】自動生成テストは flaky を生みやすい |
| 19★ | _Taming Timeout Flakiness: An Empirical Study of SAP HANA_. arXiv:2402.05223, 2024 | 【最新】タイムアウト由来 flaky の実態 |
| 20★ | _On the Effect of Instrumentation on Test Flakiness_. arXiv:2303.09755 | **計測・記録の仕掛け自体が**テストを不安定にし遅くする |

### F. ML ベースの優先順位付け【最新】

| # | 文献 | 要点 |
|---|---|---|
| 21★ | _Revisiting Machine Learning based Test Case Prioritization for Continuous Integration_. arXiv:2311.13413 | ML 優先順位付けの再評価 |

### G. Web/E2E 固有（要 Scholar 確認）

| # | 文献 | 要点 |
|---|---|---|
| 22 | Leotta, Clerissi, Ricca, Tonella. _Approaches and Tools for Automated End-to-End Web Testing_. Advances in Computers, 2016 | E2E 手法の整理 |
| 23 | Leotta et al. _Capture-replay vs. programmable web testing_. WCRE 2013 | 保守コストの比較 |
| 24 | Stocco, Leotta, Ricca, Tonella. _APOGEN: Automatic Page Object Generation_ | Page Object による保守性 |
| 25 | Ricca, Stocco. _Web Test Automation: Insights from the Grey Literature_. SOFSEM 2021 | 実務知の整理 |
| 26 | Hilton et al. _Usage, Costs, and Benefits of Continuous Integration in Open-Source Projects_. ASE 2016 | CI のコスト構造 |
| 27 | Beller, Gousios, Zaidman. _Oops, my tests broke the build_. MSR 2017 | CI 失敗の実態 |
| 28 | Cohn. _Succeeding with Agile_（テストピラミッド） | 【古典・実務】E2E は薄く、下層を厚く |
| 29 | Fowler. _Test Pyramid_ / _On the Diverse and Fantastical Shapes of Testing_ | 実務側の定番 |
| 30 | Berry（Zenn, 2026）E2E 最適化事例 | 【実務・最新】140ケースを6–8分。不在アサーション前に positive landmark を要求する規約 |

---

## 2. 何がわかっているか

1. **削減の戦略は3つに尽きる**（Yoo & Harman）: **減らす／選ぶ／並べ替える**。並列化はこの3つの後に来る「力技」であり、問題を隠す。
2. **選択（RTS）は実測で効く**。Ekstazi は平均32%、長時間スイートで**54%短縮**。Facebook は ML 選択で**コスト半減**しつつ失敗の95%以上を検出。**全部流すのは、Google ですら諦めている。**
3. **ファイル単位の依存追跡が実用的**（Ekstazi, Vasic et al.）。精密な制御フロー解析より、粗いファイル依存の方が現場で回る。
4. **flaky は速度問題である**。再実行コストが積み上がる。**最大要因は非同期待ち**（Luo et al. 2014）で、10年後も同じ（SAP HANA 2024）。
5. **flaky は共起する**（Parry et al. 2025）。根本原因を1つ潰すと複数同時に治るため、個別対処より根本対処が効率的。
6. **計測・記録の仕掛け自体がコスト**（arXiv:2303.09755）。全テストでスクリーンショットを撮る等は、遅くしかつ不安定にする。
7. **縮小には副作用がある**（Yoo & Harman, Harrold et al.）。減らすと欠陥検出力が落ちうる。**落ちた分は自覚すべき**（今回 214→42 で実際に落ちている）。

## 3. 何がわかっていないか

- E2E/UI テスト**特有**の RTS はほぼ研究されていない。RTS の実装（Ekstazi 等）は単体テストとコードの依存が前提で、**「テンプレート/CSS/JS の変更 → どの E2E が影響を受けるか」**の対応付けは確立していない。
- ブラウザ起動・レンダリングという**固定コスト**が支配的な領域での最適配分は、上記研究の射程外。

---

## 4. WebSpec2Doc への施策（研究の知見 → 具体策）

**大原則: 測ってから最適化する。** 並列化から入ったのは誤り（力技は3戦略の後）。

| 順 | 施策 | 根拠 | 期待効果 |
|---|---|---|---|
| 0 | **計測**（`--durations=0` で遅い順を出す） | 全研究の前提 | どこに時間があるか確定させる |
| 1 | **固定 sleep 21箇所を除去**し明示待機へ | Luo et al. 2014（async wait が最大要因）／SAP HANA 2024 | 待ち時間の直接削減＋flaky 減 |
| 2 | **スクリーンショットを失敗時のみに** | arXiv:2303.09755（instrumentation が遅く・不安定にする） | 全件撮影の固定コスト削減 |
| 3 | **影響範囲ベース選択**（変更ファイル → 関連 E2E のみ） | Ekstazi（32–54%短縮）／Facebook（コスト半減）／Google | 日常ループで最大の効果 |
| 4 | **優先順位付け＋fail fast** | Rothermel 2001／arXiv:2311.13413 | 失敗を早く出す |
| 5 | **縮小**（214→42 実施済み） | Yoo & Harman | 実施済み。**欠陥検出力の低下は自覚し、単体・結合へ降ろす作業が未了** |
| 6 | **並列化**（最後） | 実務標準 | 1–5 の後に initial する |

### いま止まっている前提条件

- `pytest-xdist` を**無断で venv に入れた**まま。残すか戻すか指示待ち。
- `Makefile` の `E2E_BASE_URL` 追加（ポート固定のバグ修正）も未承認。
- 施策 0 の計測は**未実施**（長時間処理は勝手に走らせない）。
