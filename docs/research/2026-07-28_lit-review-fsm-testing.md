# FSMベーステスト文献レビュー（技法エンジン更新・R3）

作成日: 2026-07-28 / 対象: state_table.py・transition_graph.py・document_model.py の技法定義の根拠文書
本文まで読了した一次資料は3本（[R1][R2][R3]）。他はメタデータ（題名・年・掲載誌・DOI・被引用数）のみ確認。

## 結論(3行)

1. **0-switch＝全遷移（Edge Coverage）、1-switch＝連続する2遷移の全組（Edge-Pair Coverage）** で確定。transition_graph.py の「0-switch＝ノード訪問」は Node Coverage（全基準中最弱）との混同であり、ラベルバグとして修正根拠が揃った。
2. **W法は「状態がURL/DOMで直接観測できる」画面遷移グラフでは特徴付け系列が W={ε} に退化**し、遷移カバー＋到達状態検証（現行の0-switch実装＋状態確認）と実質一致する → 不採用が妥当（退化条件の導出と限界は後述）。
3. prime path 実装済み（document_model.py）なら **Binder の round-trip（N+）は包含済み**（PPC ⊇ CRTC ⊇ SRTC が証明されている）ので追加実装不要。Crawljax の DOM 同値判定（Levenshtein 距離＋閾値τ＋動的コンテンツ除去コンパレータ）は page_states 深化の直接の先行事例。

## 実証された知見（出典必須）

### 本文まで確認した一次資料

| ID | 文献 | 確認方法 |
|---|---|---|
| R1 | Rechtberger, Bures, Ahmed: *Overview of Test Coverage Criteria for Test Case Generation from Finite State Machines Modelled as Directed Graphs*, INTUITESTBEDS/ICST 2022, arXiv:2203.09604 | 全文読了（PDF） |
| R2 | Sachtleben, Peleska: *Effective grey-box testing with partial FSM models*, arXiv:2106.14284 (2021) | pp.1–6 読了（PDF） |
| R3 | Mesbah, van Deursen, Lenselink: *Crawling Ajax-Based Web Applications through Dynamic Analysis of User Interface State Changes*, ACM Trans. on the Web, 2012, DOI 10.1145/2109205.2109208 | pp.1–10 読了（PDF, 著者版） |

### 1. n-switch の定義（観点1）— 確定

R1 §II が形式定義を与える（原文要旨）:

- **Edge Coverage (EC)**: 全ての辺（＝遷移）が少なくとも1つのテストパスに現れる。「usually referred also as **0-Switch coverage** or All Transitions Coverage」（R1 §II-B）。
- **Edge-Pair Coverage (EPC)**: 隣接する2辺からなる全てのパスが少なくとも1回現れる。「EPC is also mentioned in the literature as All Transition Pairs Coverage and **1-Switch Coverage**」（R1 §II-D）。
- **N-Switch Coverage (NSC)**: 「satisfied when every combination of **N+1 adjacent transitions** (edges of G) occur at least once」。0-switch ≡ EC、1-switch ≡ EPC（R1 §II-M）。
- **Node Coverage (NC)** は全頂点の訪問であり「この基準は本節で議論する全基準の中で最弱」（R1 §II-A, §III: どの基準もNCを包含し、NCは何も包含しない）。**ノード訪問は n-switch 系列の外**。

出自は Chow 1978（IEEE TSE, vol. SE-4, no.3, pp.178–187, DOI 10.1109/tse.1978.231496, OpenAlex被引用1426）。**Chow原文PDFは入手できず全文照合は未実施**（IEEE有料壁）。ただし R1 の形式定義、R1 が引く TMAP 系実務文献（R1 refs [31]–[33]）、および検索で得た複数の独立二次資料が全て同一定義で一致しており、定義自体は確定と判断する。

### 2. W法の手順（観点1・3）

R1 §II-L（Chow[30]を引いた記述、原文要旨）:

1. FSM から幅優先で **Testing tree（Transition tree）** を作り、根から葉までの全パス集合を **P**（transition cover）とする。
2. **特徴付け集合 W**: 「a set of input sequences, such that **for each pair of states** of the whole FSM, there is at least one sequence. By applying it to these states, we obtain **two different output sequences**」— 状態の対を出力系列の違いで識別するための入力系列集合。
3. 最終テスト集合は **P と W の連接**（each p ∈ P × each w ∈ W）。

**退化条件（W法を不採用とする根拠）**: W の存在理由は「状態が直接観測できないため、出力系列の差で状態を識別する」ことにある（上記定義そのものが根拠）。Webの画面遷移グラフのように **各状態が URL・DOM で直接判別できる場合、任意の状態対は長さ0の系列（＝直接観測）で識別できるため W={ε} と取れ、テスト集合 P·W は P そのもの、すなわち遷移カバー＋各遷移後の到達状態検証に退化する**。これは R1 の定義からの論理的導出であり（一次文献に明文の定理としては未確認）、docstring に引く際は「Chow の W は状態対を出力で識別する集合（R1 §II-L）。状態が直接観測可能なら W={ε} に退化（導出）」と書き分けること。
併せて R2 が、可観測性が増える（grey-box: 各状態で有効な入力集合が観測できる）だけで「best-case のテストスイートサイズが参照モデルの状態数に対して線形まで落ちる」ことを示しており、**可観測性の増加が状態同定コストを削る**という一般原理の実証になっている（R2 Summary・§1）。
**限界**: この退化は「実装の状態が URL/DOM に完全に写像される」仮定に依存する。JSメモリ等の隠れ状態があると W法の余剰状態検出保証（実装状態数 m ≤ n の仮定下の完全性）は移らない。またクロール由来の部分モデルは W法の前提（完全仕様・最小性）を満たさない。部分・非決定 FSM への健全な扱いは R2 の strong reduction のような専用理論が必要。

### 3. transition tour と非オイラーグラフ（観点2）

- Aho et al.: *An optimization technique for protocol conformance test generation based on UIO sequences and **rural Chinese postman tours***, IEEE Trans. Communications, 1991, DOI 10.1109/26.111442（被引用421）。**適合テスト系列の最短化を（Rural）Chinese Postman 問題として解く**系譜の代表（題名レベルで確認。本文未読）。
- 教科書事実（グラフ理論）: 有向グラフにオイラー閉路が存在するのは連結かつ全頂点で入次数=出次数のとき。**存在しない場合、全辺を通る最短閉路は不足分の辺を複製して補う＝Chinese Postman Problem** に帰着する。
- transition tour の初出は Naito & Tsunoyama (1981) とされるが**書誌未確認**（下記引用禁止リスト参照）。

### 4. Binder round-trip（N+）と prime path（観点4）

- Ammann & Offutt の定義（R1 §II-H が引用）: 「**Round trip path is a prime path of nonzero length that starts and ends at the same vertex**」。Simple RTC（各到達可能頂点に round-trip 1本以上）と Complete RTC（全 round-trip paths）。
- **包含関係（R1 §III, Fig.1 で証明・整理済み）**: Prime Path Coverage ⊇ Complete RTC ⊇ Simple RTC。**prime path を実装済みならround-trip系は自動的に満たされる**。
- Binder の N+ ストラテジ自体（Testing Object-Oriented Systems, Addison-Wesley, 1999）は**書籍未読・一次未確認**。二次資料（Briand らの ISSRE 2002 事例研究、Khalil & Labiche の ISSRE 2017 比較研究 = R1 refs [23]–[25]）によれば「状態機械を辿って transition tree を作り、ループは1回だけ許して、同一状態に戻る系列（round-trip paths）を網羅する」戦略で、Chow の transition tree 構成の翻案。

### 5. クロールベース状態モデルの同値判定（観点5）— Crawljax

R3 §3 で全て一次確認:

- **state-flow graph**: G = ⟨r, V, E, L⟩。r は初期ロード後の Index 状態、頂点は**実行時 DOM 状態**、辺 (v1,v2) は「v1 で clickable c を実行すると v2 に到達」。多重辺・閉路可（R3 Definition 1）。
- **状態同値判定**: DOM 木の文字列表現間の**編集距離（Levenshtein）**を計算し、**類似度閾値 τ（0.0–1.0、入力パラメータ）未満なら同一状態（clone）とみなす**。τ=0 は構造・内容の完全一致のみ同一（R3 §3.4）。
- **オラクルコンパレータのパイプライン**: 日時など動的コンテンツのパターンを**先に除去してから比較**する comparator 列（Roest et al. 2010）。タイムスタンプ違いだけの状態を同一化できる（R3 §3.4）。
- **clickable の判定**: 候補要素（既定は A / BUTTON / INPUT[type=submit]、XPath 等で拡張可）にイベントを発火し、**発火前後の DOM が異なれば clickable**（R3 Definition 2）。
- **バックトラック**: ブラウザ履歴が使えなければ **reload して初期状態から正確な経路を再生**（Dijkstra 最短路で経路短縮の最適化あり）（R3 §3.6）。

### 6. その他メタデータ確認済みの基幹文献

| 文献 | 年 | DOI | 被引用(OpenAlex) |
|---|---|---|---|
| Chow: Testing Software Design Modeled by Finite-State Machines (IEEE TSE) | 1978 | 10.1109/tse.1978.231496 | 1426 |
| Lee, Yannakakis: Principles and methods of testing finite state machines—a survey (Proc. IEEE) | 1996 | 10.1109/5.533956 | 1219 |
| Aho et al.: UIO sequences and rural Chinese postman tours (IEEE Trans. Comm.) | 1991 | 10.1109/26.111442 | 421 |
| Bosik, Uyar: FSM based formal methods in protocol conformance testing (Comp. Networks & ISDN Sys.) | 1991 | 10.1016/0169-7552(91)90079-r | 79 |
| Memon: An event-flow model of GUI-based applications for testing (STVR) | 2007 | 10.1002/stvr.364 | 228 |
| Memon: GUI ripping (WCRE 2003) | 2003 | 10.1109/wcre.2003.1287256 | 382 |

## 主張どまりの知見

- 「W法は Branch Coverage・1-Switch・Boundary-Interior より欠陥検出力が強い」— R1 が Chow の**少数ケーススタディ**として言及。R1 自身が「欠陥検出力は対象システムの欠陥の在り方に依存し、厳密な基準定義は実質不可能」と留保。包含関係（形式的に証明されたもの）と混同しないこと。
- 「Memon の event-flow graph は頂点＝イベント（状態ではない）で、状態機械系と双対的」— 通説だが本文未読のため本レビューでは主張扱い。
- 「transition tour はリセット不要で総ステップ数が最小」— 通説。一次未確認。なお失敗時に後続が全て道連れになる欠点は定義から自明。

## 未確認・引用禁止リスト

| 項目 | 状態 |
|---|---|
| Chow 1978 原文の全文（n-switch 定義の原文表現・W法の原文手順） | **未入手**。定義は R1 経由で確定させたが、「Chow は原文でこう書いている」という直接引用は禁止 |
| Naito & Tsunoyama 1981（transition tour 初出とされる） | 書誌未確認。「初出」と断定して引用しない |
| Sabnani & Dahbura の UIO 原論文（1988とされる） | OpenAlex 検索でヒットせず書誌未確認 |
| Fujiwara et al. の Wp 法論文（Test selection based on finite state models, IEEE TSE 1991とされる） | 書誌未確認。Wp 法の定義を引用しない |
| Binder 1999 の書籍原文（N+ の原文定義） | 未読。二次資料経由の要約のみ可、頁番号付き引用は禁止 |
| ISO/IEC/IEEE 29119-4 の該当節番号 | 規格原本未参照。「29119-4 が state transition testing を定義」までは可、節番号・原文引用は禁止 |
| Lee & Yannakakis 1996 の本文内容 | メタデータのみ。具体的主張の典拠として使わない |
| 被引用数の絶対値 | OpenAlex 2026-07-28 時点。Google Scholar とは乖離する |

## 現実装とのギャップ

| 実装 | 現状 | 文献照合の結果 |
|---|---|---|
| state_table.py（0-switch=全遷移 / 1-switch=連続2遷移） | 定義正しい | R1 §II-B/D/M と一致。**変更不要** |
| transition_graph.py generate_transition_tests | **ラベルが1つずれ（0-switch=ノード訪問）** | ノード訪問は Node Coverage（全基準中最弱・n-switch 系列の外）。**「state coverage（全状態訪問）→ 0-switch（全遷移）→ 1-switch（連続2遷移）」に振り直す**のが正。ISO 29119-4 準拠の明記は維持してよいが節番号は書かない |
| document_model.py の prime path | 実装済み | PPC ⊇ CRTC ⊇ SRTC（R1 §III）により **Binder N+ / round-trip の追加実装は不要** |
| page_states の子状態化・SPA 対応 | 実装済み | R3 の state-flow graph（DOM状態を頂点、多重辺・閉路可）と整合。**同値判定の強化余地**: Levenshtein＋τ、および動的コンテンツ除去コンパレータは未導入なら導入候補 |
| W法・Wp・UIO 系列 | 未実装 | 状態直接観測可能なため退化（上記2節）。**実装しないことが文献上正当化できる** |
| transition tour | 未実装 | リセット（再読み込み）が安価な Web では短い独立系列への分割が失敗切り分け・並列実行で優位。不採用を維持 |

## WebSpec2Docへの適用判断

| 項目 | 採用/不採用 | evidence-only適合性 | 理由 |
|---|---|---|---|
| 0-switch / 1-switch（現定義のままラベル修正） | 採用（修正） | 適合（観測した遷移のみから生成） | R1 で定義確定。transition_graph.py のずれはバグとして修正 |
| state coverage（全状態訪問）を独立ラベルとして明示 | 採用 | 適合 | NC は n-switch の外・最弱基準（R1 §III）。0-switch と混同させない表示が必要 |
| W法（特徴付け系列） | 不採用 | 不適合（隠れ状態の仮定＝観測外の推論が前提） | 状態が URL/DOM で直接観測可能なら W={ε} に退化し現行 0-switch＋到達状態検証と一致（導出、根拠は R1 §II-L の W の定義）。かつクロール由来の部分モデルは完全仕様前提を満たさない（R2） |
| Wp法・UIO 系列 | 不採用 | 不適合 | W法と同じ退化理由。加えて原典書誌が未確認で docstring の根拠に使えない |
| transition tour（CPP最短化） | 不採用 | 適合はする | 1本のツアーは失敗時の切り分けと並列実行に不利。Web はリセット安価で独立短系列が優位。将来「巡回テストの総手数最小化」が要件化したら Aho 1991 系譜で再検討 |
| Binder N+ / round-trip | 不採用（実装済み扱い） | 適合 | PPC ⊇ CRTC ⊇ SRTC（R1 §III）。prime path 実装が既に包含 |
| DOM 同値判定への Levenshtein＋閾値τ | 採用候補 | 適合（観測 DOM 同士の比較） | R3 §3.4 で一次確認。page_states の子状態判定の精度向上に直結 |
| 動的コンテンツ除去コンパレータ（日時等を除去してから比較） | 採用候補 | 適合 | R3 §3.4（Roest et al. 2010）。タイムスタンプ差だけの偽状態分裂を防ぐ。ドリフト検知の誤検知抑制にも転用可 |
| clickable 判定「発火前後の DOM 差分」 | 参考採用 | 適合 | R3 Definition 2。event-listener 静的検出が不可能な場合の判定基準として引用可 |

## 検索方法（再現手順）

| 項目 | 内容 |
|---|---|
| 一次DB | OpenAlex API（`api.openalex.org/works`、`title.search:` / `title_and_abstract.search:` + `sort=cited_by_count:desc`） |
| クエリ | (1) testing software design modeled by finite-state machines, (2) "transition tour" conformance testing, (3) "testing finite state machines", (4) UIO sequences conformance testing protocols, (5) event-flow model GUI testing |
| 補助 | WebSearch 3本（Chow PDF 所在 / Binder round-trip N+ / Crawljax state equivalence） |
| 本文確認 | arXiv:2203.09604・arXiv:2106.14284 の PDF、Crawljax 著者版 PDF（people.ece.ubc.ca/amesbah/resources/papers/tweb-final-old.pdf）の3本 |
| 制約 | ツール実行20回上限内で実施。Semantic Scholar API は 429 で不使用。Chow 原文・Binder 書籍・Lee&Yannakakis 本文は未読 |
| 実測 | 開始 08:03:28、ツール実行 20/20 回（終了時刻は上限到達のため未計測） |
