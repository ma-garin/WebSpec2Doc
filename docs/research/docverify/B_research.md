# B. 要求仕様の品質欠陥の自動検出と LLM による仕様レビュー（調査）

調査日 2026-10-15 / 調達: WebFetch/WebSearch 15 回（arXiv API 4、arXiv abs 9、Semantic Scholar 1 回=HTTP 429 で失敗、WebSearch 1）。
**根拠の水準**: 全件「abstract / メタデータのみ」確認。本文（表・データセット詳細・限界）は未確認。取得は小モデルによる要約経由のため、数値は一次資料で再確認するまで「主張」扱い。
区分: 【実証】=abstract に数値あり（本文未検証）/ 【主張】=数値なし・定性的 / 【未確認】=記憶由来・今回未取得。

## 1. 研究別まとめ

| # | 研究（年）出典 | 検出対象 | 手法 | データ / n | 精度 | 限界 | 区分 |
|---|---|---|---|---|---|---|---|
| 1 | Femmer ら "Rapid quality assurance with Requirements Smells"（2016, JSS）https://arxiv.org/abs/1611.08847 | 要求の smell（ISO 29148 由来の曖昧語・主観語等） | ルール/辞書の静的解析（Smella） | 産業 3 + 大学 1 文脈。n は abstract に無し | 平均 precision 59% / recall 82%（ケース間のばらつき大） | 一部 smell は区別困難・定義が曖昧と著者自身が記述 | 実証（abstract） |
| 2 | Veizaga, Shin, Briand "Paska"（2023, arXiv）https://arxiv.org/abs/2305.07097 | 13 smell 相当 + 修正パターン推薦 | NLP + 制御自然言語 Rimay | 金融 13 システム / 2,725 件（人手注釈） | smell 検出 89%/89%、パターン推薦 96%/94% | 単一企業ドメイン・英語・査読会場不明（preprint）。ルール設計と評価が同一ドメインで楽観の可能性 | 実証（abstract） |
| 3 | Zakeri-Nasrabadi, Parsa "Testability Measurement Based on Requirement Smells"（2024）https://arxiv.org/abs/2403.17479 | 9 smell からテスト容易性を数値化 | smell 検出 + 回帰 | 約 985 件 / 6 プロジェクト / 10 ドメイン | MAE 0.12, MSE 0.03（検出 P/R の改善 +0.03/+0.33 は基準不明） | 基準線不明。数値の意味は本文確認要 | 実証（abstract・要再確認） |
| 4 | Gentili, Falessi "Characterizing Requirements Smells"（2024）https://arxiv.org/abs/2404.11106 | 12 smell の実務者評価 | 実務者 10 名のインタビュー系 | 10 名 | なし（6 つの教訓） | 定性。smell の実害は一様でない | 主張 |
| 5 | Ezzini ら "TAPHSIR"（2022）https://arxiv.org/abs/2206.10227 | 照応（代名詞）曖昧さの検出と解決 | ML + BERT 変種 | abstract に無し | abstract に無し | 数値未取得。公開ツールあり（Zenodo） | 主張 |
| 6 | Luitel, Hassani, Sabetzadeh "Improving Requirements Completeness"（2023, REJ）https://arxiv.org/abs/2308.03784 | 不完全性（欠落語彙） | BERT の masked LM で伏せた語を予測 + ML フィルタ | PURE 40 仕様書 | 数値なし（「ベースライン超え」） | 生成 LLM でなく BERT。人工的に伏せた語で評価＝実際の欠落とは別 | 主張 |
| 7 | Lubos ら "Leveraging LLMs for QA of Software Requirements"（2024, RE@Next!）https://arxiv.org/abs/2408.10886 | ISO 29148 品質特性の評価 + 改善案 | LLM が評価・理由・修正案を出す | 数値 abstract に無し（技術者調査あり、n 不明） | なし | 規模・基準不明。定性的な有望性の主張 | 主張 |
| 8 | Krishna ら "Using LLMs in SRS"（2024, RE@Next!）https://arxiv.org/abs/2404.17842 | SRS 起草 + 既存要求の問題発見/修正 | GPT-4 / CodeLlama | 大学クラブ管理 1 例 + 4 ユースケース、n 不明 | なし。GPT-4 は問題指摘・修正案可、CodeLlama は劣る | 単一ドメイン・2 モデル・n 不明 | 主張 |
| 9 | Saleem ら "PassionNet"（2024）https://arxiv.org/abs/2412.01657 | 重複・矛盾要求の同定 | LM / 類似度 / ハイブリッド 760 パイプライン | 公開 6 データセット | 最良が既存比 F1 +13%（絶対値不明） | 絶対 F1 不明。矛盾の定義は「要求ペアのラベル」依存 | 実証（相対のみ） |
| 10 | Malik ら "Transfer learning for conflict/duplicate detection"（2023）https://arxiv.org/abs/2301.03709 | 矛盾・重複ペア | 転移学習 | 4 データセット | abstract 取得できず | 未確認 | 未確認 |
| 11 | Darif ら "LEREDD"（2026）https://arxiv.org/abs/2602.22456 | 要求間依存（Requires 等） | LLM + RAG + ICL | 813 ペア / 3 システム（注釈データ公開） | accuracy 0.93, F1 0.84, 非依存 F1 0.96, Requires は相対 +94.87%/+105.41% | 高 accuracy は非依存クラス優位の影響。依存型別の F1 は低い可能性 | 実証（abstract） |
| 12 | Hall, Eiers "Neurosymbolic Auditing of NL Requirements / VERIMED"（2026 preprint）https://arxiv.org/abs/2605.13817 | 曖昧・矛盾・空虚（vacuous）・安全違反 | LLM が形式論理へ翻訳 → SMT。複数回翻訳の不一致を曖昧性シグナルに | 血液透析の公開要求、n 不明 | 修復実験で verified accuracy 55.4%→98.5%（定義は abstract に無い。曖昧性検出の P/R ではない） | 医療機器 1 領域。数値は検出精度でなく修復後 QA 精度。preprint | 実証（abstract・文脈限定） |
| 13 | Vogelsang ら "Requirements Smells in Prompts"（2025）https://arxiv.org/abs/2501.04810 | smell がトレーサビリティ生成に与える影響 | LLM 2 種で比較 | 不明 | 影響は「小さいが有意」（数値なし） | 数値未取得 | 主張 |
| 14 | Villamizar ら "Requirement Smells in LLM-Based Code Generation"（2026）https://arxiv.org/abs/2609.29208 | smell がコード生成に与える影響 | 4 アプリ + システムテスト | 4 アプリ | 数値なし | 小規模 | 主張 |
| 15 | BRQGen（2026, 参考: バグ報告）https://arxiv.org/abs/2610.15903 | バグ報告の不完全性と追質問生成 | LLM | 429 件 / 正解質問 1,073 | 質問カバレッジ 35.4–51.8%、最良 macro-F1 49.3% | 要求ではなくバグ報告だが、「LLM による欠落指摘」の精度水準の参考。約半分は取りこぼす | 実証（類推） |
| 16 | ClarifyCodeBench（2026）https://arxiv.org/abs/2607.00711 / Orchid（2026）https://arxiv.org/abs/2604.21505 | 曖昧な要求下でのコード生成・確認質問 | ベンチマーク（Orchid は 1,304 タスク・4 曖昧型） | 上記 | abstract に数値なし | 要求レビューではなく下流影響の測定 | 主張 |

## 2. 日本語仕様への適用（WebSearch 1 回、一次資料は未取得）
出典検索結果（URL は検索結果由来。内容は検索要約のみ・原文未確認）:
- 有賀ら（情報処理学会研究報告 SE）文章構造・構文構造から IEEE 830 の品質特性（非曖昧性・検証可能性・追跡可能性）の問題点を検出 https://ipsj.ixsq.nii.ac.jp/record/90471/files/IPSJ-SE13179004.pdf 【主張・数値未取得】
- ReqQA（SES2015）Word 要求仕様→中間言語→品質解析 https://cir.nii.ac.jp/crid/1050855522051582720 【主張】
- 富山県立大 格解析による曖昧性（省略格成分）修正支援（電子情報通信学会 ISS 2021 ポスター）https://www.ieice.org/~iss/jpn/Publications/issposter_2021/data/pdf/ISS-P-038.pdf 【主張】
- デンソー「LLM による要求仕様書の品質評価」言語処理学会 2025 年次大会 Q9-5。LLM が人手インスペクション結果をどこまで再現するかを分析 https://anlp.jp/proceedings/annual_meeting/2025/pdf_dir/Q9-5.pdf 【主張・数値未取得。本件に最も近い。要本文確認】
- 和文要求仕様→状態遷移モデル変換で曖昧さ・矛盾検出（電子情報通信学会 KBSE 2017）https://www.ieice.org/ken/paper/20180301J1CM/ （予備的結果、電気ポット例題のみ）【主張】
- 佐野町ら 日本語要求仕様記述ルールデータセット（語彙・構文・構文パターン、ICOSE ガイド準拠）【主張】
- IPA/SEC・JaSST は今回の検索でヒットなし。「無い」とは断定しない（**未確認**）。

## 3. 古典手法（記憶由来、今回未取得 = 未確認）
- NASA ARM（Wilson ら 1997）: 弱語・命令語（shall/must）・継続語等の語彙カウント指標。QuARS（Gnesi/Fabbrini 2001）: 曖昧語辞書+構文パターン。EARS（Mavin 2009）: 5 つの書式パターンで曖昧さを予防。Paska は Rimay（Veizaga 2021）で同発想。これらは「検出」より「書式制約で予防」と「辞書で警告」。いずれも本調査では原典の数値を取得していない。

## 4. 製品機能に落とすと効く手法
1. **辞書/ルール型 smell 検出（曖昧語、主観語、否定、受動態、比較級、未定義の代名詞、「等」「など」「適切に」）**: 説明可能・決定的・低コスト。再現率が高め（Smella 82%）で、出力は「候補指摘」として出す。日本語版は語彙リストを自前で作る必要（日本語での精度は未確認）。
2. **書式パターン強制（EARS/Rimay 型）+ 修正テンプレ提示**: Paska の検出 89% と推薦 94–96% が実証水準（単一領域・abstract）。UI は「どのパターンに当てはまらないか」と書き換え案。
3. **LLM は指摘の説明と書き換え案の生成に使い、検出は決定的ルールと併用**: Lubos・Krishna は理由+修正案の有望性を主張（数値なし）。単独検出の根拠は弱いので、ルール検出結果を LLM に渡す二段構成が安全。
4. **同一要求を複数回形式化/言い換えさせ、不一致を曖昧性シグナルにする**（VERIMED の発想）。再現性のため温度・回数を固定し、不一致箇所だけ人に出す。精度は未実証（P/R 未取得）。
5. **要求ペアの矛盾/重複/依存の候補抽出**（LEREDD, PassionNet）。確定でなく「確認候補リスト」として出す。
6. **トレース**: 要求→テストの欠落（孤立要求）は決定的にチェックできる（LLM 不要）。

## 5. 精度が出ず人の判断が要る領域
- **不完全性（書かれていない要求）**: BERT 予測は人工マスク評価のみ、BRQGen（類推）でも追質問の網羅は約 35–52%。「抜けていない」は証明できない → 常に「未検証」扱い。
- **矛盾**: 意味理解が必要で、数値は相対値のみ（+13% F1）。業務知識・暗黙前提依存。
- **Smell の実害判定**: 定義が曖昧で人間間でも区別困難（Femmer 自身の限界記述）。重大度は人が決める。
- **ドメイン固有の曖昧さ・用語の同一性**: 組織の用語集がないと判断不能。
- **日本語**: 主語・格の省略が常態。検出器の汎化性能は未確認。
- **LLM の再現性**: 同じ入力で指摘が揺れる（VERIMED はこの揺れを曖昧性シグナルとして逆用）。単独の合否判定には使わない。

## 6. 引用してはいけない数値
- Paska 89%/89%・96%/94%: 単一金融企業ドメイン・英語・preprint・abstract のみ。一般化して「89% 検出できる」と言わない。
- Smella 59%/82%: 2016 年・ルール型・文脈間で大きくばらつく。LLM 時代の精度として使わない。
- VERIMED 55.4%→98.5%: 検出精度ではなく修復後の「verified accuracy」（定義不明）。曖昧性検出精度として引用しない。
- LEREDD accuracy 0.93: クラス不均衡（非依存 F1 0.96）で押し上がっている。依存検出の精度として引用しない（F1 0.84 でも型別は未確認）。
- PassionNet「+13%」: 絶対値なしの相対差。
- BRQGen 数値: バグ報告であり要求ではない。類推としてのみ。
- 日本語研究（有賀・デンソー等）: 数値未取得のため一切引用しない。
- NASA ARM / QuARS / EARS: 記憶由来。原典を確認するまで数値・主張を書かない。
- 全表の数値は小モデルによる abstract 要約経由。製品説明・営業資料に使う前に原文で再確認。

## 7. 検索方法・限界
arXiv API は 4 クエリ（relevance / submittedDate）。Semantic Scholar は 429 で取得失敗（再試行せず、15 回上限のため）。DBLP/IEEE/ACM/J-STAGE/IPSJ 原文は未取得。否定的結果: IPA/SEC・JaSST 該当資料は未発見、LLM による要求欠陥検出の P/R を直接報告した 2023–26 論文は今回の検索では abstract レベルで確認できず（LEREDD と BRQGen のみ数値あり）。
