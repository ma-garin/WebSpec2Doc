# 境界値・ドメインテスト文献レビュー（技法エンジン更新・R2）

作成日: 2026-07-28 / 対象: BVA・ドメイン分析エンジンの理論的裏付けとギャップ判断

## 結論(3行)

1. 現実装の「境界±1（3値法相当）」は ISTQB CTFL v4.0 の 3-value BVA と一致し、2値法より欠陥検出力が高いことに規格系の根拠がある（一次確認済み）。
2. 現実装の 1×1 行列（1境界だけ外し他はIN）は Jeng & Weyuker 系の簡略化ドメインテストに対応するが、ON/OFF点の厳密な置き方（閉/開境界での区別）は本文未確認のため、実装の点配置を White & Cohen / Jeng & Weyuker の定義と照合する作業が残る。
3. Feldt/Dobslaw の自動境界検出（program derivative）は SUT の実行・探索を前提とする動的手法であり、クロール由来のDOM実測制約から静的に境界を導く現方式とは前提が異なる。不採用が妥当。regex逆生成は Rex（SMT）等で一般解が存在し、現行の「既知4種辞書＋re.fullmatch自己検証」は保守的すぎる可能性がある（オートマトン系生成＋自己検証なら evidence-only に適合）。

## 実証された知見（出典必須）

一次資料（OpenAlex メタデータ＋abstract、および ISTQB シラバス本文）で確認できた内容のみ。

| # | 出典 | 確認レベル | 知見 |
|---|---|---|---|
| P1 | White & Cohen, "A Domain Strategy for Computer Program Testing", IEEE TSE, 1980, DOI 10.1109/tse.1980.234486, 被引用380 | abstract全文 | 制御フローの述語が入力空間を互いに素なドメイン（各ドメイン＝1実行パス）に分割する、という定式化の原典。境界に試験点を置くことで「境界のシフト」または「述語の関係演算子の変化」を検出する。適切な仮定の下で ε より大きいドメイン誤りに対して reliable であることを証明。**必要試験点数は入力空間の次元数とパス上の述語数の両方に対して線形にしか増えない** |
| P2 | Jeng & Weyuker, "A simplified domain-testing strategy", ACM TOSEM 3(3) pp.254–270, 1994, DOI 10.1145/196092.193171, 被引用74 | 書誌のみ（abstractはOpenAlex未収録） | White & Cohen 系のドメインテストを簡略化した戦略（通称 1×1）の原典であること（題名・掲載誌・年）。戦略の中身は本節では主張しない（→主張どまり欄） |
| P3 | ISTQB CTFL Syllabus v4.0 §4.2.2（本文抜粋PDFを直接読解。smartesting.com 掲載の Chapter 4 全文抜粋） | 本文 | **2値法**（出典として Craig 2002, Myers 2011 を挙げる）: カバレッジアイテムは「境界値そのもの＋隣接パーティション側の最近傍1点」。**3値法**（Koomen 2006, O'Regan 2019）: 「境界値＋その両隣」。**3値法は2値法より厳密**で、`if (x ≤ 10)` を `if (x = 10)` と誤実装した場合、2値法の x=10, x=11 では検出できず、3値法の x=9 で検出できる、という具体例つき。BVAは**順序のあるパーティションにのみ適用可**。典型欠陥は「実装された境界が意図位置の上下にずれている、または境界が丸ごと欠落」 |
| P4 | 同 §4.1 | 本文 | 技法とそのカバレッジ測度の詳細は ISO/IEC/IEEE 29119-4 に定められている、と明記（シラバスは29119-4への参照で技法定義を裏付ける構造） |
| P5 | Feldt & Dobslaw, "Towards Automated Boundary Value Testing with Program Derivatives and Search", SSBSE 2019 (LNCS), DOI 10.1007/978-3-030-27455-9_11, 被引用9 | abstract全文 | BVAの形式化として **program derivative**（数学の微分の類推。入力間距離と出力間距離を情報理論的に定量化し、その比を「境界らしさ」とする）を提案。探索ベーステストの適応度関数として使う。**本人らが「research noteであり深い実証は含まない」と明記** |
| P6 | Dobslaw, Feldt, de Oliveira Neto, "Automated black-box boundary value detection", PeerJ Computer Science, 2023, DOI 10.7717/peerj-cs.1625, 被引用10 | abstract全文 | P5 の実装 **AutoBVA**。仕様モデル不要のブラックボックス動的手法で、「入力は近いのに出力が遠いペア」を探索・ランク付けする。Julia 標準ライブラリの613関数で評価し、**調査対象システムの70%超で多様な挙動を示す境界候補を検出**。SUT を大量実行できることが前提 |
| P7 | Veanes, de Halleux, Tillmann, "Rex: Symbolic Regular Expression Explorer", ICST 2010, DOI 10.1109/icst.2010.15, 被引用149 | abstract全文 | 正規表現制約を SMT ソルバ Z3 上で記号的に表現・解析し、正規表現を満たす文字列を系統的に生成する。任意（.NET方言）の正規表現に対する逆生成の一般解が存在することを示す代表研究 |
| P8 | Shahbaz, McMinn, Stevenson, "Automatic generation of valid and invalid test data for string validation routines using web searches and regular expressions", Science of Computer Programming, 2014, DOI 10.1016/j.scico.2014.04.008, 被引用29 | abstract要約 | 文字列バリデーションルーチンに対し、正規表現とWeb検索を組み合わせて **valid と invalid の両方** のテストデータを自動生成する手法 |
| P9 | Zheng et al., "String Generation for Testing Regular Expressions", The Computer Journal, 2018, DOI 10.1093/comjnl/bxy137, 被引用5 | abstract要約 | 正規表現そのものをテストするための文字列生成。正規表現に対するカバレッジ基準を定義し、それを満たす最小文字列集合を生成 |

## 主張どまりの知見

教科書・二次資料で広く流通しているが、今回の調査では一次資料の本文にあたっていない内容。使う場合は「通説」として扱うこと。

- **ON点/OFF点の置き方の通説**: 閉境界（≦等、境界がドメインに属す）では ON点は境界上（＝ドメイン内）、OFF点は境界のわずか外側。開境界（＜等）では ON点は境界上（＝ドメイン外）、OFF点はわずか内側。— White & Cohen (P1) の本文にある定義とされるが、abstract には現れないため本文未確認。
- **N×1 戦略**: 次元 N の線形境界1本につき ON点 N 個＋OFF点1個を置く、とされる。P1 の abstract の「試験点数は次元に線形」はこれと整合するが、「N個＋1個」という具体数は本文未確認。
- **1×1 戦略の中身**: 境界1本につき ON点1個＋OFF点1個で足りることを示した、とされる（Jeng & Weyuker, P2）。書誌は確認済みだが定義の詳細は本文未確認。現実装の 1×1 行列の点配置が原典の ON/OFF 定義と一致しているかは、この本文確認をしてから断定すること。
- **program derivative の静的適用**: P5/P6 は動的（実行ベース）手法であり、「DOM実測制約（maxlength・pattern）から静的に導いた境界」への転用可能性は原著論文の主張範囲外。転用できるという主張は本レビューの推測であり、実証はない。

## 未確認・引用禁止リスト

| 項目 | 理由 |
|---|---|
| ISO/IEC/IEEE 29119-4 の条文番号・条文文言 | 規格本文は有料で未入手。ISTQB シラバス経由の間接確認のみ（P3/P4）。「29119-4 では〜と規定」という直接引用は禁止。「ISTQB CTFL v4.0（29119-4準拠）では」と書くこと |
| Jeng & Weyuker の 1×1 の具体的な点配置・誤り検出能力の数値 | 本文未確認（P2 は書誌のみ） |
| White & Cohen の ON/OFF 点定義の逐語的引用・N×1 の「N+1点」 | abstract に現れず本文未確認 |
| AutoBVA の「70%」を現実装の性能予測に流用すること | 対象は Julia 標準ライブラリの数値系関数613本（P6）。Webフォーム入力とはドメインが全く異なる |
| 「2値法で十分/3値法は過剰」という一般論 | 今回の資料に費用対効果の実証は無い。P3 の関係演算子誤り例は3値法優位の根拠だが、逆方向の実証は未確認 |
| 各論文の被引用数の絶対値 | OpenAlex 2026-07-28 時点の値。Google Scholar とは異なる |

## 現実装とのギャップ

| 現実装 | 文献との照合結果 |
|---|---|
| maxlength/min/max から境界±1（3値法相当） | **整合**。ISTQB v4.0 の 3-value BVA そのもの（P3）。3値法が2値法より厳密という根拠も一次確認済み。ギャップなし |
| pattern は既知4種辞書のみ逆生成、re.fullmatch で自己検証、辞書外は「例生成不能」と明示 | **保守的すぎる可能性**。Rex（P7）が任意regexの逆生成の一般解を示しており、Pythonでも正規表現→オートマトン→文字列列挙は既知技術。fullmatch 自己検証を残せば evidence-only は維持できる。ただし P7 は .NET 方言であり、Python re の方言差（先読み・後方参照等）で生成不能なクラスが残る点は現行の「生成不能と明示」の設計と同じ扱いでよい |
| ドメイン分析: 1境界につき ON/OFF/IN/OUT の4点 | 3値法（境界の前・境界・後）＋代表点に相当し、ISTQB 3-value を包含。ただし ON/OFF の置き方が閉境界/開境界で異なるという通説（White & Cohen 系）に対し、現実装が境界の開閉（≦か＜か、HTMLのmin/maxは閉境界）を区別して点を置いているかは**要照合（未確認）** |
| 1×1 行列（1つの境界だけ外し他はIN点） | Jeng & Weyuker の簡略化戦略の考え方と方向は一致。White & Cohen の「点数は次元・述語数に線形」（P1、一次確認済み）が、多入力フォームで全組合せを取らない現設計の理論的支えになる |
| evidence-only 原則（DOM実測属性が無ければ値を作らない） | Feldt/Dobslaw（P5/P6）は逆に「仕様が無い場所の境界を実行で発見する」手法であり、原則と正面から衝突する（後述の適用判断で不採用） |

## WebSpec2Docへの適用判断

| 項目 | 採用/不採用 | evidence-only適合性 | 理由 |
|---|---|---|---|
| 3値法（境界±1）の維持 | 採用（現状維持） | 適合 | ISTQB v4.0 で3値法の優位に一次根拠あり（P3）。min/max/maxlength は DOM実測で境界が確定するため3値が置ける |
| 2値法への縮退オプション | 不採用 | — | ケース数削減効果はあるが、関係演算子誤り（≤→=）を見逃す反例が規格側に明記されている（P3）。削減が必要になったら再検討 |
| 1×1 行列の維持 | 採用（現状維持、要本文照合） | 適合 | 点数線形性（P1）と簡略化戦略（P2）が方向を支持。ただし ON/OFF 配置の原典照合を1回行い、閉境界（min/max は ≦）で OFF 点が「域外側」に置かれていることを確認してから「Jeng-Weyuker 1×1 準拠」と名乗ること |
| 境界の開閉区別の明示（閉境界前提の文書化） | 採用（小改修） | 適合 | HTML の min/max/maxlength はすべて閉境界。実装が暗黙にそれを前提にしているなら、設計書に「閉境界前提」と1行明記するだけで通説との整合が説明可能になる |
| regex 逆生成のオートマトン化（辞書4種→一般生成＋fullmatch検証） | 条件付き採用（次期候補） | 適合 | 一般解の存在は P7 で確認。生成後に re.fullmatch 検証を通す現行ゲートを残せば「実測 pattern に適合する値しか出さない」原則は保たれる。生成不能な方言機能は現行どおり「例生成不能」と明示。invalid 値（境界外文字列）の生成は P8 が先行例 |
| program derivative / AutoBVA 型の動的境界探索 | 不採用 | 不適合 | SUT への大量入力実行が前提（P5/P6）。クロール対象サイトへ任意値を送信することは非破壊原則に反し、evidence-only（実測属性の無い所に値を作らない）とも衝突。将来ユーザー自身の検証環境で実行する機能ができた場合のみ再検討 |
| AutoBVA の数値（70%等）のドキュメント引用 | 不採用 | — | 対象ドメインが異なる（引用禁止リスト参照） |

## 検索方法（再現手順）

| 項目 | 内容 |
|---|---|
| 一次DB | OpenAlex API（`api.openalex.org/works`） |
| 個別取得 | DOI 直指定 `works/doi:10.1109/tse.1980.234486`（White & Cohen）、`works/doi:10.1109/icst.2010.15`（Rex） |
| 題名検索 | `filter=title.search:simplified domain testing`（Jeng & Weyuker。※DOI 10.1145/174634.174635 は別論文（Forgács 1994）なので注意。正しくは 10.1145/196092.193171）/ `title.search:boundary value testing program derivatives` / `title.search:automated black-box boundary value detection` |
| 不発だったクエリ | `title_and_abstract.search` に OR をインラインで書く形式（数学の boundary value problem 系ノイズに埋没）、`raw_author_name.search:dobslaw`（同姓の地球物理学者 H. Dobslaw が大量ヒット）。再現時は題名の複合語 AND で絞るのが確実 |
| regex系 | `search=string generation regular expressions testing`（Shahbaz 2014・Zheng 2018 がヒット。EGRET・MutRex は今回未ヒット＝未確認のまま） |
| ISTQB | WebSearch で syllabus 抜粋PDFを特定し、smartesting.com 掲載の Chapter 4 全文抜粋（13p）を直接読解。ISO 29119-4 本文は未入手 |
| 被引用数の基準時点 | 2026-07-28 の OpenAlex 値 |
