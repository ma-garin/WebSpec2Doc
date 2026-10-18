# P3b 要件・設計文書間の矛盾検出の定量評価（LLM／知識グラフ・オントロジー／日本語）
調査日 2026-10-18。WebSearch 5 回＋WebFetch 4 回（うち 2 回は取得失敗/本文不可）。多くは検索要約ベースで、本文未確認が多い。

## 結論（3 行）
- LLM 単体は「適合率は高いが再現率が低い」報告が多く（ChatGPT 適合率0.85/再現率0.31、GPT-3併用でも再現率60%）、形式手法・ルール・クラスタリングとの併用が主流。
- 知識グラフ・オントロジー系は要件矛盾での標準ベンチマークが見つからず、定量評価は小規模・専門データに限られる。
- 日本語は評価論文自体が少なく（デンソー言語処理学会2025、FOSE2025）、数値は本文未確認。日本語の矛盾検出の公開ベンチマークは見つからなかった。ここが空白＝差別化余地。

## 発見
### 1. Fazelnia, Mirakhorli, Bagheri／2024／ASE 2024 NIER／SAT-LLM（SMTソルバ＋LLM）
- 手法: LLM が自然言語を理解、SMT ソルバが形式推論。純LLM（ChatGPT）と比較。
- 数値（二次情報: 2025年サーベイ経由）: SAT-LLM 適合率1.00／再現率0.83／F1 0.91。ChatGPT 単体 適合率0.85／再現率0.31（NSF PAR 検索要約）。データセット・n は未確認。
- 区分: 主張（一次の本文表は未確認）
- URL: https://par.nsf.gov/servlets/purl/10574434 ／ https://conf.researchr.org/details/ase-2024/ase-2024-nier-track/20/Translation-Titans-Reasoning-Challenges-Satisfiability-Aided-Language-Models-for-De ／ サーベイ https://arxiv.org/pdf/2506.11874
- 注: WebFetch は接続拒否で本文取得できず。

### 2. Gärtner, Göhlich／2024／Proceedings of the Design Society vol.4 pp.2049-2058／形式論理＋GPT-3 の3段階ハイブリッド
- 実バス（電気バス）プロジェクトで accuracy 99%、recall 60%（要旨の記載）。n は未記載。矛盾が希少なため accuracy は誤解を招く。
- 区分: 主張（要旨のみ確認）
- URL: https://depositonce.tu-berlin.de/items/a50b7d72-5556-4b21-ac38-2af3e3e0063c/full

### 3. Fantechi, Gnesi, Passaro, Semini／2023／RE 2023 RE@Next!／ChatGPT(GPT-3.5)による自然言語要件の不整合検出（予備研究）
- 学生（RE知識あり）の専門家判断と比較。少数の要求文書。データ（原文・注入変異・ChatGPT/手動結果）は Zenodo 公開。数値は未確認。
- 2026年論文（arXiv 2608.21298）は、不整合タイプ・書き方で検出精度にばらつきがあると引用。
- 区分: 実証（小規模・予備）／数値は未確認
- URL: https://conf.researchr.org/details/RE-2023/RE-2023-re-next--papers/12/Inconsistency-Detection-in-Natural-Language-Requirements-using-ChatGPT-a-Preliminary ／ https://zenodo.org/records/8089810

### 4. Fantechi, Gnesi, Semini／2025／RE 2025 RE@Next!／LLM＋ルールベースクラスタリング
- RE Open Data Initiative の大規模セキュリティ要件文書に矛盾を注入して評価。適合率・再現率とも向上と要旨に記載、具体値なし（WebFetch で確認済み）。
- 区分: 主張（数値なし）
- URL: https://conf.researchr.org/details/RE-2025/RE-2025-re-next--papers/19/Combining-Established-and-Emerging-Techniques-to-Detect-Inconsistencies-in-Requireme

### 5. Mahbub ら（GPT-4）／年・会議未確認
- GPT-4 は不整合・曖昧性検出より不完全性検出が得意（arXiv 2608.21298 の引用経由。二次）。区分: 未確認
- URL: https://arxiv.org/pdf/2608.21298

### 6. AraREQ（Hamad ら）／2026／LREC 2026／アラビア語要件矛盾検出・解消
- 27K 要件ペア、4 LLM を zero/few-shot で評価。プロジェクトサイトの平均 micro-F1 約93%（zero-shot）／94%（few-shot）。少数クラス（矛盾）では few-shot が有効。micro-F1 は多数派クラスに引きずられうる。
- 区分: 実証（サイト記載。論文本文未確認）
- URL: https://preview.aclanthology.org/ingest-lrec/2026.lrec-main.553/ ／ https://sina.birzeit.edu/ArReqConflicts/

### 7. ConInstruct（AAAI）／LLM への指示内の矛盾検出
- DeepSeek-R1 平均F1 91.5%、Claude-4.5-Sonnet 87.3%。要件文書ではなく指示文の矛盾で対象が違う。モデルは矛盾をユーザに告げないことが多い。
- 区分: 実証（要約のみ）／参考扱い
- URL: https://ojs.aaai.org/index.php/AAAI/article/view/40356/44317

### 8. 知識グラフ・オントロジー系
- OntReq: 固定テンプレートの機能要件＋制約＋用語集を入力に3種の矛盾（要件間・要件と制約・要件と形式ガイドライン）を検出。定量値は未確認。区分: 未確認。
- 意味的競合の分類（Data & Knowledge Eng. 2010、OWL/SWRL）、Resglass（Semantic Web 2019、検査優先順位が専門家と80%重複）、PaTeCon（AAAI 2023、KG の時間制約マイニング。採掘制約は86%/96%が有用）は要件文書の矛盾検出ではない。区分: 周辺。
- 要件の Action+Object+Resource 構造化による矛盾検出: https://arxiv.org/pdf/2103.02255
- URL: https://arxiv.org/pdf/2304.09015 ／ https://content.iospress.com/articles/semantic-web/sw190358

### 9. 日本語
- デンソーグループ／言語処理学会 2025（Q9-5）／車載ソフト要求仕様書のLLMインスペクション。LLM単独は精度不足、正規表現・形態素解析など規則処理併用で向上、人手の見逃しも指摘（検索要約）。PDF は本文を読めず数値未確認。区分: 主張。
  URL: https://anlp.jp/proceedings/annual_meeting/2025/pdf_dir/Q9-5.pdf
- FOSE 2025（J-STAGE 32_153）／ユースケース図と記述の整合性評価。単純な不整合には成果、複雑なフロー・ユースケース間依存は限界。数値未確認。区分: 主張。
  URL: https://www.jstage.jst.go.jp/article/fose/32/0/32_153/_article/-char/ja
- 日本語に特化した矛盾検出ベンチマーク・公開データは見つからなかった（未確認＝存在しないとは断定しない）。

## 勝つための示唆
1. 「LLM だけ」は再現率が壊滅的（0.31 / 60%）。LLM の抽出＋ルール／ソルバ／クラスタリングの併用を製品の中核に置き、再現率を主指標として公開する。
2. 日本語の矛盾検出の公開ベンチマークが見当たらない。矛盾注入（Fantechi 方式）の日本語データセットと評価結果を自社で公表すれば、信頼性の差別化になる。
3. 設計文書間（要件↔基本設計↔詳細設計）の矛盾に特化した定量評価は今回見つからなかった。要件内矛盾が中心で、文書間は空白領域。
4. 評価は accuracy でなく矛盾クラスの適合率・再現率・F1 で示す。希少クラスでは accuracy・micro-F1 が高く見える。
5. オントロジー系は固定テンプレート前提で現場文書に不向き。用語集・制約の半自動抽出を LLM に任せ、検査は決定的ルールにする構成が有望（私見・未検証）。

## 引用してはいけない数値
- SAT-LLM の P=1.00/R=0.83/F1 0.91 と ChatGPT の 0.85/0.31: 一次論文の表を未確認。n・データ不明。
- Gärtner の accuracy 99%: 希少クラスで意味が薄く、n 不明。
- AraREQ の micro-F1 93/94%: サイト記載のみ・言語が異なる。
- ConInstruct の F1: 要件文書の矛盾ではない。
- 「F1 79〜94%（GPT-4/Claude 3.5 のシステム仕様検証）」: promptlayer の二次要約のみ。引用不可。
- PaTeCon・Resglass の数値: 要件矛盾ではない。

## 検索方法
- WebSearch 5 回（英語 3・日本語 1・SAT-LLM 特定 1）、WebFetch 4 回。arXiv API・Semantic Scholar API は不使用。
- WebFetch: par.nsf.gov は接続拒否、anlp.jp PDF は本文抽出不可、researchr と depositonce は取得成功。残りは検索要約に依存し、本文未確認。
- 否定的結果: 日本語の矛盾検出ベンチマーク、文書間矛盾の定量評価、オントロジー系の要件矛盾の標準ベンチマークは見つからなかった。ツール呼び出し上限（10回）に到達。
