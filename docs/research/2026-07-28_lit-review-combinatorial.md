# 組合せテスト文献レビュー（技法エンジン更新・R1）

作成日: 2026-07-28 / 対象: WebSpec2Doc 組合せテスト生成エンジン（貪欲AETG系・決定的）の更新判断

## 結論(現実装への適用可否を3行)

1. 現実装の「乱数なし1候補の決定的貪欲」は、Bryce–Colbourn の決定的貪欲フレームワーク（2005/2007）と同じ系譜にあり、文献上の裏付けがある妥当な設計。オリジナルAETGの乱数候補方式に戻す必要はない。
2. 次の投資順位は 制約(forbidden tuples) → seeding → mixed-strength。3つとも貪欲one-test-at-a-timeの被覆対象tuple集合と初期状態の操作だけで実現でき、決定的純関数のまま追加可能。
3. SATソルバ連携・SA/PSO等のメタヒューリスティクスは、乱数依存または外部依存のため不採用。t=3への強度引き上げは NASA実測（2-wayで93%、3-wayで98%）を根拠にオプションとして検討価値あり。

## 実証された知見（出典・効果量つき）

### 1. 相互作用ルールと実測パーセンテージ（本文一次確認済み）

出典: Kuhn, Kacker, Lei, *Practical Combinatorial Testing*, NIST SP 800-142, 2010. https://nvlpubs.nist.gov/nistpubs/legacy/sp/nistspecialpublication800-142.pdf （本文 pp.4–10, 16–17 を直接読了）

- **Interaction Rule 原文**（p.5）: "Most failures are induced by single factor faults or by the joint combinatorial effect (interaction) of two factors, with progressively fewer failures induced by interactions between three or more factors."
- **NASAアプリの実測**（p.5）: 単一パラメータで67%、2-wayで93%、3-wayで98%の故障を誘発。他ドメイン（Med. Devices / Browser / Server / NASA Distributed DB, Figure 2）も同様の曲線で、**4〜6-wayで100%に到達**。原データの一次出典は Kuhn, Wallace, Gallo, "Software Fault Interactions and Implications for Software Testing", IEEE TSE 30(6), 2004, DOI: 10.1109/tse.2004.24（OpenAlex被引用792・上位1%）。
- SP 800-142自身が "While not conclusive" と留保している点に注意（絶対法則ではなく経験則）。
- **テスト数のオーダー**（p.9）: t-way被覆に必要なテスト数は v^t log n に比例（n=パラメータ数, v=値数）。
- **被覆配列 vs 純乱数**（pp.9–10）: 10パラメータ・各4値の3-way被覆は被覆配列で151件、純乱数生成では900件超が必要。
- **実例の効果量**（p.16, Android 3^4 4^4 5^2 系・172,800全組合せ）: t=2で29件(0.02%)、t=3で137件(0.08%)、t=4で625件、t=5で2,532件、t=6で9,168件(5.3%)。

### 2. AETG（乱数候補型貪欲の原典）

出典: Cohen, Dalal, Fredman, Patton, "The AETG System: An Approach to Testing Based on Combinatorial Design", IEEE TSE 23(7), 1997, DOI: 10.1109/32.605761（被引用1,026）。

- pairwise〜n-way被覆をone-test-at-a-timeの貪欲で生成し、テスト数はパラメータ数に対して**対数的に成長**する（abstract確認）。
- 決定性の問題: Bryce & Colbourn, "The density algorithm for pairwise interaction testing", STVR 17(3), 2007, DOI: 10.1002/stvr.365 は、AETG系貪欲の限界に対し**対数サイズ保証と決定的再現性を両立する貪欲アルゴリズム**を提示（abstract確認）。決定的貪欲の一般枠組みは Bryce, Colbourn, Cohen, "A framework of greedy methods for constructing interaction test suites", ICSE 2005, DOI: 10.1145/1062455.1062495。

### 3. IPOG（決定的・パラメータ逐次拡張型）

出典: Lei, Kacker, Kuhn, Okun, Lawrence, "IPOG: A General Strategy for T-Way Software Testing", IEEE ECBS 2007, DOI: 10.1109/ecbs.2007.47（被引用344）; 同著者 "IPOG/IPOG-D: efficient test generation for multi-way combinatorial testing", STVR 2007, DOI: 10.1002/stvr.381（被引用244）。

- IPOGは**決定的**: 最初のt列の全組合せから始め、水平拡張（列追加）＋垂直拡張（行追加）で構築。AETGのone-test-at-a-timeと構造が異なる。
- IPOG-D は再帰構成で t-tuple の明示的列挙を削減（abstract確認）。ACTSツール（NIST公式・無償, csrc.nist.gov/acts）の中核。
- AETGとの配列サイズの定量比較は今回一次確認できず（「主張どまり」節参照）。

### 4. 制約付き被覆配列

出典: Cohen, Dwyer, Shi, "Constructing Interaction Test Suites for Highly-Configurable Systems in the Presence of Constraints: A Greedy Approach", IEEE TSE 34(5), 2008, DOI: 10.1109/tse.2008.50（被引用316・上位1%）。

- 貪欲CIT生成にSATソルバを組み込み、制約違反の組合せを探索空間から刈る方式。abstractは非制約手法比で約30%のコスト削減を報告（比較の詳細条件は未確認）。
- SP 800-142（pp.16–17, 一次確認）: 制約対応の実務指針として「**無効組合せを含むテストを単純削除してはならない**（そのテストが被覆していた他の必要組合せまで失う）。被覆配列生成器が制約 `(OS != "XP") => (Browser = "Firefox")` の形で制約を受け取り、生成段階で無効組合せを除外すべき」と明記。ACTSは論理・算術演算子による制約指定をサポート。
- 分野の全体地図: Nie & Leung, "A survey of combinatorial testing", ACM Computing Surveys 43(2), 2011, DOI: 10.1145/1883612.1883618（被引用717）が constraints を主要研究カテゴリの一つとして分類。

### 5. Mixed/variable-strength と seeding

- **Variable-strength covering array の定義原典**: Cohen, Gibbons, Mugridge, Colbourn, "Constructing test suites for interaction testing", ICSE 2003, DOI: 10.5555/776816.776822（被引用311）。mixed-level covering array（列ごとに値数が異なる）と variable strength array（特定のパラメータ部分集合だけ高強度tを課し、全体は低強度）を導入。ヒューリスティック探索（焼きなまし）が貪欲より小さい配列を得たと報告（効果量は未確認）。
- **seeding**: 既存テストケースを配列に固定席として先に置き、それらが被覆するtupleを差し引いた残りを生成で埋める方式。IPOGへのseeding＋制約追加の近年例: Muazu, Hashim, Sarlan, Abdullahi, "SCIPOG: Seeding and constraint support in IPOG strategy for combinatorial t-way testing", J. King Saud Univ. CIS, 2022, DOI: 10.1016/j.jksuci.2022.11.010（abstract確認）。

## 主張どまりの知見（実証データなし・今回未検証）

- **「IPOG/ACTSはAETGより小さい表を出す」**: IPOG-D論文abstractがAETG等への優位を主張するが、具体的なサイズ差の数値は今回未確認。逆方向（AETG系貪欲が小さいケース）の報告も確認できておらず、**どちらが小さいかは構成依存で一般解なし**として扱うべき。
- MIPOG / MC-MIPOG（Younis & Zamli, 2010–2011）がIPOG・Jenny・TConfig等より小さい配列を出すという主張（abstractのみ、被引用24–47と小さい）。
- Cohen et al. 2003 の「焼きなまし＞貪欲」のサイズ差の大きさ（abstractに数値なし）。
- Cohen/Dwyer/Shi 2008 の「約30%削減」の比較対象・条件の詳細。

## 未確認・引用禁止リスト（一次確認できなかった数値・命題）

| 項目 | 状態 |
|---|---|
| 医療機器66%/97%、Browser 29%/76% 等のドメイン別詳細% | 禁止。SP 800-142 Figure 2はグラフのみで数値ラベルなし。本文に数値があるのはNASA(67/93/98)のみ。TSE 2004本文は未読 |
| 「20X〜700X のテスト数削減」（NIST ACTSプロジェクトページの文言） | 禁止。原データ未確認 |
| IPOGの計算量オーダー（O記法） | 禁止。本文未確認 |
| オリジナルAETGの「乱数候補50本から選ぶ」 | 未確認（1997年論文の本文未読。現実装設計メモ由来の伝聞として扱う） |
| 「IPOG and ACTS generally produce smaller test sets than AETG」というSP 800-142の記述 | 禁止。WebFetch要約モデルが返したが、読了した本文範囲(pp.2–18)に存在せず。捏造の可能性が高い |
| SP 800-142がseedingを推奨しているという記述 | 未確認。読了範囲に該当なし。seedingの出典はSCIPOG等の論文側を使うこと |

## 現実装とのギャップ

| 観点 | 現実装 | 文献上の位置づけ | ギャップ |
|---|---|---|---|
| 生成方式 | 貪欲one-test-at-a-time、辞書順最小tupleを種に被覆ゲイン最大で列を埋める。乱数なし・1候補 | Bryce–Colbourn決定的貪欲（2005/2007）と同系。AETG原法（乱数候補）とは異なるが、決定性はむしろ文献が改良点として提示した性質 | 方式選択は妥当。1候補ゆえの配列サイズ増の可能性はあるが、その効果量を示す一次データは未確認 |
| 制約 | 未対応 | SP 800-142が実務必須と明記（単純削除は被覆喪失）。貪欲内でのforbidden tuple検査は決定的に実装可能。SAT連携は大規模制約向け | **最大のギャップ**。実Webフォームには依存制約が普通に存在する |
| mixed-strength | 未対応（全列同一強度） | Cohen et al. 2003が定義。被覆対象tuple集合の差し替えで貪欲に載る | 中。リスク集中箇所だけt=3にする用途 |
| seeding | 未対応 | SCIPOG等。既存ケースの被覆分を差し引いてから生成 | 中。既存回帰ケースとの重複削減に直結 |
| 直交表 | GF(p)線形構成で別途実装済み | 被覆配列とは別系統（均衡性を持つが値数・強度の自由度が低い） | ギャップなし。併存でよい |
| 強度t | （現状の既定を維持） | NASA実測: t=2で93%、t=3で98%、t=4–6で100% | t=3オプションの根拠が一次確認済みで揃った |

## WebSpec2Docへの適用判断

| 項目 | 採用/不採用 | evidence-only適合性 | 理由 |
|---|---|---|---|
| forbidden tuples を貪欲の被覆ゲイン計算・値選択時に検査（制約対応） | **採用（次期・最優先）** | 適合（決定的純関数のまま実装可） | SP 800-142が「単純削除は不可、生成段階で除外」と明記。SAT不要の禁止tuple列挙で実務制約の大半を賄える |
| SATソルバ連携（Cohen/Dwyer/Shi方式） | 不採用 | 不適合寄り（外部依存追加・ソルバ内部の非決定性管理が必要） | 現対象規模（Webフォーム由来の数十パラメータ）では禁止tuple方式で十分。効果量30%も条件未確認 |
| seeding（既存ケースを種に固定） | **採用（次期）** | 適合（種は入力として与えられ、生成は決定的） | 既存回帰ケースとの重複を減らす。被覆済みtupleの差し引きのみで実装可 |
| mixed/variable-strength | 採用候補（seedingの後） | 適合（被覆対象tuple集合の定義変更のみ） | 定義原典あり（Cohen et al. 2003）。UIでの強度指定設計が先に必要 |
| オリジナルAETGの乱数候補方式へ回帰 | 不採用 | **不適合（乱数不可原則に違反）** | 決定的貪欲の文献裏付け（density algorithm）があり、回帰の利益は未実証 |
| SA/PSO等メタヒューリスティクス | 不採用 | 不適合（乱数依存） | サイズ削減の主張はあるが、決定性喪失の代償に見合う一次データなし |
| IPOG方式への置き換え | 不採用（現時点） | 適合はする（IPOGも決定的） | 「AETG系より小さい」の効果量が未確認のまま実装を置き換えるのはevidence-only原則に反する。現方式で問題が実測されたら再検討 |
| t=3オプションの提供 | 採用候補 | 適合 | NASA実測（93%→98%）が一次確認済み。コストは v^t log n 比例で見積もり提示可能 |

## 検索方法（再現手順）

| 項目 | 内容 |
|---|---|
| 一次DB | OpenAlex API（`api.openalex.org/works`）＋ NIST一次資料（csrc.nist.gov / nvlpubs.nist.gov） |
| 絞り込み | `title_and_abstract.search:<句>` または `title.search:<句>`。**OR句・一般語のみのクエリは分野外ノイズ（遺伝学等）が混入して失敗**した（2クエリ）。固有名詞（AETG, IPOG）か論文タイトル語での title.search が確実 |
| 並び順 | `cited_by_count:desc` |
| クエリ句 | AETG / IPOG t-way testing / "fault interactions" software testing / covering array constraints test generation / interaction test suites highly-configurable constraints / constructing test suites interaction testing（計7本、うち有効5本） |
| 本文確認 | NIST SP 800-142 PDF の pp.2–18（17ページ）を直接読了。相互作用ルール・NASA数値・制約指針・テスト数実例はここで一次確認 |
| 被引用数の基準時点 | 2026-07-28 のOpenAlex値 |
| ツール実行回数 | 計14回（上限20回以内）: Read 2・ToolSearch 1・WebFetch 10・Write 1 |

未実施: Kuhn/Wallace/Gallo TSE 2004 本文（ドメイン別詳細%の一次確認）、AETG 1997 本文（乱数候補数の一次確認）、IPOG論文の実験表（AETG比サイズの効果量）。いずれも「未確認・引用禁止リスト」に反映済み。
