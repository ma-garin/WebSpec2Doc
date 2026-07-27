# メタモルフィックテスト文献レビュー（技法エンジン更新・R4）

作成日: 2026-07-28 / 対象: mbt/metamorphic.py の関係候補生成エンジン更新判断

## 結論(3行)

1. 6パターン分類（additive/multiplicative/permutative/invertive/inclusive/exclusive）の原典は **Murphy et al. 2008（Columbia TR / SEKE 2008）** であり、Segura サーベイ（TSE 2016）はそれを §5.1.5 で紹介している。Segura 自身の分類ではない。
2. 実証は厚い: 2015年までに **36ツール・295件の実欠陥** を MT が検出（Segura §6.3）、GCC/LLVM で **147確認バグ**（EMI）、**3〜6個の多様なMRでオラクルが検出できる欠陥の約90%** を検出（Liu et al. TSE 2014）。「少数MRで十分」という知見は現行3MR設計を支持する。
3. 現3MRは確立パターンに正対応（filter_subset＝inclusive/exclusive系・Chen CSUR のDB部分集合例そのもの、sort_invariance＝permutative）。追加候補は「等価クエリ/URL正規化」「絞込の冪等性」「絞込の可換性」「絞込解除の復元」がクロール実測で判定可能で優先度が高い。

## 実証された知見（出典必須）

一次資料を本文確認したもの（★＝本セッションでPDF本文を読んだ）:

- ★ **Segura, Fraser, Sanchez, Ruiz-Cortés, "A Survey on Metamorphic Testing", IEEE TSE 42(9), 2016.** DOI 10.1109/TSE.2016.2532875（著者版PDF p.3–18を確認）
  - **6分類の正確な一覧**（§5.1.5、原典は Murphy, Kaiser, Hu, "Properties of machine learning applications for use in metamorphic testing", Columbia Univ. Tech. Rep. 2008／SEKE 2008 版あり）: **additive（定数加算）/ multiplicative（定数倍）/ permutative（順序入替）/ invertive（反転）/ inclusive（要素追加）/ exclusive（要素削除）**。ML分野の入力変換として提案されたもの。
  - 1998–2015年の119本を系統的レビュー。**MT は 36ツールで約295件の実欠陥を検出、うち23が実世界プログラム**（§6.3）。
  - 応用分野の最大は **Webサービス/アプリ（16%）**、次いでCG(12%)・シミュレーション(12%)・組込み(10%)（Fig.4）。
  - **使用MR数は5〜9個が最多（39%）。10個未満で十分な成果が通例**（§6.4）。
  - ソーステストケースは **ランダム生成57%・既存スイート34%**。ランダム生成は手動の特殊値由来より欠陥検出で有効（§4.3・§6.2、Wu et al. / Segura et al.）。
  - 標準評価指標は **Mutation Score MS(t)=Mk/(Mt−Me)** と **Fault Detection Ratio FDR=Tf/Tt**（§6.5）。
  - **良いMRの性質**（§4.1）: (a) ドメイン意味論に根ざすMRが有効。等式・線形結合だけのMRは効果が低い（Mayer & Guderlei 2006）。(b) **ソースとフォローアップの実行差が大きいほど有効**——83故障プログラム×7距離指標で、欠陥検出力とテストケース非類似度（特に分岐カバレッジのマンハッタン距離）に統計的に有意な相関（Cao, Zhou, Chen QSIC 2013）。(c) システム全体より**部分を狙うMRのほうが検出力が高い**（Just & Schweiggert 2010、Xie et al. 2014）。
  - **Kanewala & Bieman**: 数値関数48個のコーパスで permutative/additive/inclusive の3種を機械学習で予測し、**予測MRが988故障中655件（66%）を検出**（§4.2）。
  - **Lindvall et al.（NASA DAT 受入テスト）**: 巨大テレメトリDBに対し「**同一クエリの等価な言い換えを発行し、結果集合が一致することを表明する**」MRで複数の実問題を検出（§5.1.11）。→ WebSpec2Doc の等価クエリ/URL正規化MRの直接の先行例。
  - **人間の対照実験（Hu et al.、38名）**: MTはアサーション式テストより**効率は劣るが欠陥検出力は高い**というトレードオフ（§6.6）。
  - **6つの公開課題**（§7）: MR構築ガイドライン不足 / MRの優先順位付け・最小化 / likely MR の自動生成（最難）/ MRの合成（IMT・CMR）/ ソーステスト自動生成 / 公開ツールの欠如（119本中ツール主貢献は2本のみ）。
- ★ **Chen, Kuo, Liu, Poon, Towey, Tse, Zhou, "Metamorphic Testing: A Review of Challenges and Opportunities", ACM Computing Surveys（HKU TR-2017-04 版 p.1–8を確認）**
  - MTは**テストケース生成とテスト結果検証の両方**を担う（オラクル問題＋reliable test set problem の両方に効く）。MRの形式定義: n≥2 入力にわたる必要性質 R ⊆ X^n × Y^n。
  - **Siemens スイート7プログラム中3つで新欠陥を検出**（20年間研究され尽くしたプログラム群）。**GCC/LLVMで100件超の欠陥**（Le et al. のEMI、単純な等価保存関係。Segura §5.1.10 では「147確認バグ」）。
  - **Liu, Kuo, Towey, Chen, "How effectively does metamorphic testing alleviate the oracle problem?", IEEE TSE 40(1), 2014**: 6被験プログラムで、**平均3〜6個の多様なMRがオラクル検出可能欠陥の90%以上を検出**。MTはオラクル無しランダムテストより常に多くの欠陥を検出。
  - **誤解されやすい概念**: (1) MRは複数入力を要する（単一入力の性質 −1≤sin(x)≤1 はMRではない）。(2) 入力のみ/出力のみの部分関係に分解できないMRもある。(3) **MRは等式に限らない**——例示は「DBクエリの条件 c_i を1つ外すと結果は元の部分集合 q(c1∨…∨c_{i−1}∨c_{i+1}∨…∨cn) ⊆ q(c1∨…∨cn)」（Concept 3, Example 2）。**WebSpec2Doc の filter_subset はこの標準例と同型**。(4) MTはオラクルが在る場合にも有効。
  - MTの利点: 概念の単純さ・実装の容易さ・自動化しやすさ・低コスト・**テストスイート規模に制約なし**。
- ★ **Zhou, Xiang, Chen, "Metamorphic Testing for Software Quality Assessment: A Study of Search Engines", IEEE TSE 42(3), 2016（オンライン2015）.** DOI 10.1109/TSE.2015.2478001（OpenAlexでabstract確認、被引用164）
  - Google/Bing/Baidu/中国語Bing の4大検索エンジンに**ユーザー視点MR**を適用し、返却内容とランキング品質の不整合（実障害）を検出。検証(verification)だけでなく**妥当性確認(validation)・品質評価**にMTを拡張した最初の系統的研究。前身は Zhou et al., "Automated functional testing of online search services", STVR 22(3), 2012（Google/Yahoo!/Live Search で不整合検出。Segura §5.1.1で確認）。
- **Andrade et al., "On Applying Metamorphic Testing: An Empirical Study on Academic Search Engines", MET@ICSE 2019.** DOI 10.1109/met.2019.00010（OpenAlexでabstract確認）
  - 学術検索エンジン（ACM/IEEE/ScienceDirect/Springer）に **MPublished / MPTitle / MPShuffleJD / Top1Absent** というMRを定義し挙動差を検出。→ 検索・絞込・ソート・ページング以外に「**タイトル完全一致検索**」「**クエリ語順シャッフル＋結果類似度**」「**トップ1が消えないこと**」系の関係が使われている実例。
- Webサービス向けMRの枠組み（Segura §5.1.1 で確認）: Chan et al. の SOA向け metamorphic services（QSIC 2005 / IJWSR 2007）、**Sun et al. の WSDL 記述からのMR導出＋ランダムソース生成（ICWS 2011 / IJWSR 2012、被引用45/39）**、Castro-Cabrera らの WS-BPEL 合成サービス向けMR選択。
- **Segura et al., "Metamorphic testing of RESTful web APIs", ICSE 2018.** DOI 10.1145/3180155.3182528（OpenAlexで存在・被引用75を確認）——クエリ型Web APIへのMT適用の代表研究。

## 主張どまりの知見

- 「MR識別は実はそれほど難しくない」（Chen CSUR Advantage 2）——経験談ベースで対照実験なし。
- 「MTはスプレッドシート・DB・Webアプリのエンドユーザーテストに使える」（Chen et al. 2013、Segura §5.1.11 で "briefly suggested" と明記）——提案どまり。
- MRの合成（CMR）は少ない実行回数で同等以上の検出力（Liu et al. 2012）——**生物情報学プログラム1本のケーススタディのみ**（n=1）。
- 「viewport/端末間の表示一貫性」をMRとして扱う研究は本調査の範囲では**見つからなかった**（Zhou 2016 のユーザー視点MRの延長として位置づけ可能、という解釈は当方の推測）。

## 未確認・引用禁止リスト

- Zhou TSE 2016 の個別MR名（MPSite・MPTitle・MPReverseJD 等）——abstractに名前が出ず**本文未確認**。名前を引用しないこと（Andrade 2019 のMR名と混同しやすい）。
- Segura RESTful API 論文の出力パターン名（equivalence/subset/disjoint 等の「MROP」6種とされるもの）——**本文未確認**。存在と被引用数のみ確認済み。
- Chen CSUR の正式書誌（CSUR 51(1), Article 4, 2018 / DOI 10.1145/3143561 とされる）——**TR-2017-04版で内容確認**。最終版ページ数・巻号は未確認のため書誌引用時は要再確認。
- Google Maps へのMT適用（HICSS 2018, DOI 10.24251/hicss.2018.713）の検出欠陥数——メタデータのみ。
- 被引用数はすべて **OpenAlex 2026-07-28時点**（Google Scholar とは乖離する）。

## 現実装とのギャップ（現3MRのパターン対応と追加可能MR）

| 現実装 | Murphy 6分類での対応 | 文献上の裏づけ |
|---|---|---|
| filter_subset（絞込⊆全体） | **inclusive/exclusive**（クエリ条件の追加/削除） | Chen CSUR Concept 3 の DB部分集合例と同型。標準パターンど真ん中 |
| sort_invariance（並替で集合不変） | **permutative** | Murphy 6分類の1つ。Kanewala の予測対象3種にも含まれる |
| pagination_consistency（ページ合計=総件数・重複なし） | 直接対応なし（集合分割の完全性・非重複） | 6分類の外だが、Webサービス系MTで使われる集合関係の一種。妥当 |
| MR_VIEWPORT_CONSISTENCY（未実装） | 直接対応なし | Zhou 2016 の「ユーザー視点MR」（検証→妥当性確認への拡張）の系譜に位置づく。先行研究は未発見（前節参照） |

ギャップ: 6分類のうち **invertive（絞込解除で元集合へ復元）** が未実装。また6分類の外で文献実証がある **等価クエリ（Lindvall: 等価な言い換え→同一結果）**、Webサービス系で常用の **冪等性（同一操作の再適用で不変）**・**可換性（絞込A→BとB→Aで同一結果）** が候補。additive/multiplicative は数値関数の入力変換であり、実測画面要素から導けないため対象外。

## WebSpec2Docへの適用判断

| MR候補 | 採用 | クロール実測データで判定可能か | 理由 |
|---|---|---|---|
| filter_subset（既存） | 継続 | 可能 | Chen CSUR の標準例と同型。evidence-only と整合 |
| sort_invariance（既存） | 継続 | 可能 | permutative の正対応 |
| pagination_consistency（既存） | 継続 | 可能 | 集合分割。Webで頻出 |
| 等価クエリ/URL正規化（同一内容への複数URL・trailing slash・クエリ順序） | **採用** | 可能（クロールが同一ページを複数URLで観測した事実から導出） | Lindvall（NASA DAT）の実証あり。実装コスト小 |
| 絞込の冪等性（同一絞込の再適用で結果不変） | **採用** | 可能（同一URL/同一状態の再訪データ） | Webサービス系MTの常用関係。リロード不変も同枠 |
| 絞込の可換性（A→B = B→A） | 採用（条件付き） | 条件付き可能（両順序の遷移を実測した場合のみ候補生成） | permutative の応用。未観測時は生成しない＝evidence-only 維持 |
| invertive（絞込解除で元の全体へ復元） | **採用** | 可能（絞込前後の要素集合を両方観測済みの場合） | 6分類の欠落枠を埋める。filter_subset の逆向き検査 |
| viewport一貫性（実装化） | 採用 | 可能（src/viewport/ に実測比較データが既在） | 定数だけ残す現状は死に筋。Zhou のユーザー視点MRとして正当化可能 |
| ログイン状態MR（認証前後で公開コンテンツ不変） | 保留 | 現状不可（認証クロールの整備待ち） | 関係自体は有効だが判定材料がない |
| キャッシュ/再訪一貫性（時間差再訪で不変） | 保留 | 部分的に可能 | ドリフト検知（プロダクト本体の機能）と役割が重複。MR化は二重実装になる |
| ランキング品質MR（語順シャッフル＋類似度、Top1Absent 等） | 不採用 | 不可（結果類似度の計算と検索エンジン特化の前提が必要) | Zhou/Andrade 系は検索エンジン評価向け。一般サイトの実測要素から導けない |
| additive/multiplicative（数値入力変換） | 不採用 | 不可 | 数値関数の入出力はクロールで観測できず evidence-only に反する |

## 検索方法（再現手順）

| 項目 | 内容 |
|---|---|
| 一次DB | OpenAlex API（`api.openalex.org/works`） |
| クエリ | `title_and_abstract.search:metamorphic testing web service` / `…search engines`（`cited_by_count:desc`）。**注意: `metamorphic testing` 単独は地質学（変成岩）論文が上位を占め使用不能**。分野フィルタか共起語が必須 |
| 一次資料 | Segura サーベイ著者版PDF（personal.us.es/sergiosegura/files/papers/segura16-tse.pdf、p.3–18読了）/ Chen CSUR＝HKU TR-2017-04（cs.hku.hk/data/techreps/document/TR-2017-04.pdf、p.1–8読了） |
| 個別確認 | Zhou TSE 2016 を DOI 指定で OpenAlex 取得（abstract復元） |
| 未実施 | Chen CSUR 後半（課題・機会の各論、p.9–27）、Segura RESTful API 論文の本文、Google Scholar 手検索 |

弱点: (1) Chen CSUR は前半8ページのみで、後半の「機会」各論（MR自動生成・ML応用等）は未読。(2) 適用判断表の「可換性・invertive」は文献対応を示したが、WebSpec2Doc のクロールが両状態を実測できる頻度は未計測で、採用効果は実データで要検証。
