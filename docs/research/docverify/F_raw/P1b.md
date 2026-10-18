# P1b LLM による要件の曖昧さ・欠陥検出の P/R/F1 と規則ベース比較（2023〜2026）

## 結論（3 行）
- 1 つの論文で「LLM vs 規則ベース」を同一データで P/R/F1 比較したものは今回の検索では確認できなかった（未確認）。比較が出ている二次情報は LMAdetect（F1 が規則ベース比 +34.4%、相対値のみ）。
- LLM 単独は再現率が高く適合率が低い傾向（Unterbusch 2026: ゼロショット P0.573/R0.997）。別研究では専門家指摘の 47% しか検出できない（Shefa 2026）。単独の網羅性は信頼できない。
- 人が LLM 支援で検査すると検出精度がむしろ下がった（Broccia 2026, n=34）。「LLM の指摘をそのまま信用させない UI」と根拠提示が差別化点になりうる。

## 発見
1. Ezzini, Abualhaija, Arora, Sabetzadeh ／ 2022（ICSE 2022・FSE 2022 デモ。対象期間外だが基準線）／ TAPHSIR 照応曖昧性
   - 手法: 教師あり ML 検出器 + SpanBERT 解決。比較: 既製の共参照解決 NLP 群。検出は教師あり ML が SpanBERT・既製 NLP 群を上回る。最良検出の平均 P 約 60%、R 100%、解決の成功率約 98%（F1 の記載なし、n 未確認）。区分=実証（検索結果要約からの二次確認）。LLM との比較なし。
   - https://arxiv.org/pdf/2206.10227 , https://pure.kfupm.edu.sa/en/publications/taphsir-towards-anaphoric-ambiguity-detection-and-resolution-in-r/
2. Unterbusch, Vogelsang ／ 2026 ／ ICSE-NIER 2026 ／ 欠陥予測（人と LLM の協働）
   - モデル gpt-4.1-mini、データ QuRE（Mercedes-Benz 要件 2,111 件、均衡化後 1,266、各クラス 633）。ゼロショット+CoT: P0.573 R0.997 F1 0.728。CoT なし: P0.553 R0.986 F1 0.709。事例 12 件（プール 40）+CoT: P0.686 R0.967 F1 0.803。BERT 微調整（プール 320）: P0.635 R0.804 F1 0.709。規則ベースの基線なし。区分=実証（HTML 本文から取得）。
   - https://arxiv.org/html/2601.01952v1
3. Shefa, Salado, Wach, Topcu ／ 2026 ／ arXiv 2609.03230（査読未確認）／ 市販 LLM 10 種（OpenAI・Anthropic 各 5 世代）の要件品質評価
   - 正解は INCOSE 品質基準に基づく専門家作成。最良の Anthropic モデルが専門家指摘の中央値 47% を検出、誤警報 11%。必要性・正確性の問題はほぼ見逃す。新しいモデルほど良いとは限らない。データの名前・n、P/R/F1、規則ベース比較は未確認（PDF は取得したが本文を解析できず）。区分=主張（要旨のみ）。
   - https://arxiv.org/abs/2609.03230
4. Bashir, Ferrari, Khan, Strandberg ほか ／ 2025 ／ ICSME 2025 産業トラック ／ 曖昧要件の検出と説明
   - 産業データ 3 件。10 事例の文脈内学習でゼロショット比 +20.2%（平均性能。指標の種類は未確認）。専門家 8 名の説明評価は平均 3.84/5。モデル名・n・P/R/F1・基線は未確認。区分=主張（要旨のみ）。
   - https://conf.researchr.org/details/icsme-2025/icsme-2025-industry-track/8/Requirements-Ambiguity-Detection-and-Explanation-with-LLMs-An-Industrial-Study
5. Broccia, Frattini, Arora, ter Beek, Fantechi, Vogelsang, Ferrari ／ 2026 ／ arXiv 2608.21298（査読未確認）／ 要件スメル検査
   - クロスオーバー実験 n=34。LLM 支援で検出精度が低下、分類と所要時間に有意差なし。P/R/F1 は報告なし（本文未確認）。区分=実証（要旨）。
   - https://arxiv.org/abs/2608.21298
6. Lubos, Felfernig ほか ／ 2024 ／ RE 2024（RE@Next!）／ ISO 29148 の 9 特性で LLM が要件を判定・説明・改善
   - 検索要約では Llama 2 70B、技術者調査あり。P/R/F1・n は報告なし（要旨）。区分=主張。
   - https://arxiv.org/abs/2408.10886
7. Mahbub ほか ／ 2024 ／ 会議名未確認 ／ GPT-4 による曖昧・矛盾・不完全の検出（二次引用のみ）
   - 適合率が事例により 41%〜61%。一次資料は未入手のため区分=未確認（Shefa 2026 の引用経由）。
   - https://arxiv.org/pdf/2609.03230
8. LMAdetect ／ 2025 ／ 計算機研究与発展 ／ 規則ベース比 F1 +34.4%、LLM 手法比 +31.6%（相対値のみ。著者・絶対値・n 未確認）。区分=主張。
   - https://crad.ict.ac.cn/en/article/doi/10.7544/issn1000-1239.202550700
9. 周辺: ClarifySTL（arXiv 2605.01209）の AmbiEval 曖昧性検出で GPT-4o F1 64.8、Claude-4-Sonnet 69.2、自作検出器 91.0（ただし STL 変換向けの曖昧性。区分=主張、表は検索要約のみ）。https://arxiv.org/pdf/2605.01209

## 勝つための示唆
1. 「LLM のみ」は再現率寄り・適合率低め（P 0.55〜0.69）と分かる。誤検知を抑える層（事例追加、確信度、規則との併用）の効果を自社データで P/R/F1 として出せば差別化になる。
2. 事例 12 件の追加で F1 が 0.73 から 0.80 に上がる（Unterbusch）。顧客文書の過去指摘を事例として使う仕組みは裏付けがある。
3. 見逃しは必要性・正確性に偏る（Shefa）。LLM 任せにせず、検査観点ごとに手法を分け、弱い観点はチェックリストや人に回すと説明できる。
4. LLM 支援で人の検出精度が下がる実験がある（Broccia）。指摘の根拠箇所・修正案・非採用の記録を UI で必須にし、鵜呑みを防ぐ設計が要る。
5. 日本語要件の P/R/F1 を公開した研究は今回確認できなかった。日本語の公開ベンチを自社で作れば空白を取れる（未検証）。

## 引用してはいけない数値
- Mahbub の 41〜61%: 一次資料未入手、二次引用のみ。
- LMAdetect の +34.4%・+31.6%: 絶対値・データ未確認。
- Shefa の 47%・11%: 要旨のみ、データと n が不明。プレプリントで査読未確認。
- Bashir の +20.2%: 指標の種類不明。
- TAPHSIR の P60%・R100%: 検索要約。LLM 比較ではなく 2022 年の古典 ML。
- ClarifySTL の F1: 別タスク（STL 変換向けの曖昧性）。
- arXiv 番号 2608/2609/2605 は取得時に存在したが、査読前の可能性がある。

## 検索方法
- WebSearch 3 回（TAPHSIR、LLM 曖昧性 P/R/F1 規則ベース比較、LLM 要件品質欠陥 ISO 29148）、追加 WebSearch 1 回（Mahbub）、WebFetch 6 回（arxiv abs/html 4、researchr 1、arxiv pdf 1 は解析失敗）。計 10 回。arXiv API・Semantic Scholar API は未使用。
- 未実施: dblp、ResearchGate、Ezzini の本文、Fazelnia の論文、Bashir の mdu.se プレプリント、Lubos の本文。ツール回数上限のため。
