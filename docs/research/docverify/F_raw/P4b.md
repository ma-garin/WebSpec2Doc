# P4b LLM によるトレーサビリティ回復（TLR）の中核論文と精度

## 結論（3 行）
- LLM-TLR は「候補の順位付け・不足検出」で有望だが、確認できた範囲では本文の数値を取れた一次資料が少なく、精度の断定はできない（多くが未確認）。
- 人が候補リンクを確認する半自動 TLR は、精度が高い候補ほど人が悪化させる傾向を示す古い研究（Hayes/Dekhtyar 系）があり、UI で人の誤りを抑える設計が要る。
- 要件→下位要件・テストの「抜け」検出は LLM が得意（再現率 99.7% の主張あり）だが、適合率は未確認。出力は検出支援であり最終判定にしない設計が妥当。

## 発見
1. Rodriguez, Dearstyne, Cleland-Huang／2023（arXiv 投稿 2023-08。IEEE REW 2023 pp.455-464 と検索結果に記載）／"Prompts Matter: Insights and Strategies for Prompt Engineering in Automated Software Traceability"／LLM にリンク予測を出させるプロンプト設計の知見。従来のゼロショットの候補ランク付けを改善と主張／区分=主張（abstract のみ。データ・モデル・指標値は未確認）／https://arxiv.org/abs/2308.00229
2. Fuchß, Hey, Keim, Liu, Ewald, Thirolf, Koziolek（KIT）／2025／ICSE 2025 研究トラック／"LiSSA: Toward Generic Traceability Link Recovery through RAG"／要件→コード、文書→コード、アーキ文書→アーキモデルの 3 タスク。コード系で従来最先端を有意に上回ると主張、実用には追加研究が必要と自己申告／区分=主張（数値は取得ページに無し）／https://conf.researchr.org/details/icse-2025/icse-2025-research-track/192/LiSSA-Toward-Generic-Traceability-Link-Recovery-through-Retrieval-Augmented-Generati ／プレプリント https://publikationen.bibliothek.kit.edu/1000178348
3. Ewald（KIT 修士論文）／年は未確認／RAG 付き LLM の要件→コード。F1 は SMOS 0.388、eTour 0.478、iTrust 0.313（検索要約の転載）／区分=未確認（論文本文を未開封）／https://mcse.kastel.kit.edu/downloads/theses/ma-ewald.pdf
4. Niu, Pan, Briand, Hu／2025（v1 2025-04、v5 2026-07）／arXiv プレプリント／"TVR: Automotive System Requirement Traceability Validation and Recovery Through RAG"／ステークホルダ要件とシステム要件の既存リンクの検証と欠落リンクの回復。産業データで有効と主張／区分=主張（abstract に数値なし）。検索要約に「検証精度 98.87%、回復の正答 85.50%」とあるが原文未確認／https://arxiv.org/abs/2504.15427
5. Hartl, Mayr-Dorn, Mashkoor, Egyed（JKU Linz）／2024／MSR 2024／"Supporting High Level to Low Level Requirements Coverage Reviewing with LLMs"／5 つの公開データセット、GPT-3.5・GPT-4。ゼロショット＋説明プロンプトの GPT-3.5 が、下位要件を 1 件削除して作った不完全カバレッジを再現率 99.7% で検出（データセット全体）。適合率・件数は未記載／区分=実証（ただし適合率が無く片側のみ）／https://2024.msrconf.org/details/msr-2024-technical-papers/27/Supporting-High-Level-to-Low-Level-Requirements-Coverage-Reviewing-with-Large-Languag
6. Chitre, Hayes, Dekhtyar／2018／arXiv プレプリント（掲載先は未確認）／"Second-Guessing in Tracing Tasks Considered Harmful?"／人の確認時に精度を下げる行動を UI で抑えられるかを RETRO.NET 改修で予備検証。被験者数・数値は取得ページに無し／区分=主張（予備研究）／https://arxiv.org/abs/1804.02968
7. Cuddeback, Dekhtyar ほか（年は未確認）／高精度の候補行列を渡された分析者は精度を下げ、低精度なら改善しやすいという所見（検索要約。Hayes らの引用）／区分=未確認（原論文を未開封）／検索結果経由 https://arxiv.org/pdf/1804.02968
8. Trotta（Alstom）2026 ワークショップ資料: LLM で要件文とテスト文を意味比較しカバー判定／区分=未確認（資料の本文未開封。数値なし）／https://www.disia.unifi.it/upload/sub/ricerca/StEering/Workshop%202026/ScientificProgramme/S1_2_Trotta-LLM-basedCoverageAnalysisofTests_andRequirements.pdf
9. 2026 サーベイ "AI-Driven Test Case Generation from Natural Language Requirements"：完全自動かつ形式的トレーサビリティを両立する既存システムは無いと主張／区分=主張（検索要約のみ）／https://arxiv.org/pdf/2606.06563

## 勝つための示唆
- 製品の中核を「リンク確定」でなく「抜け・不整合の候補提示＋人の確認」に置く。適合率が未検証の以上、再現率訴求（抜けを見逃さない）が根拠を持ちやすい（発見 5）。
- 候補は精度が高いほど人が崩しやすい。確認 UI は理由（根拠文）と確信度を併記し、「迷ったら保留」を用意して人の過修正を抑える（発見 6・7。ただし古い研究で LLM 時代は未検証）。
- 日本語での公開評価は今回の範囲で確認できず。日本語要件・設計書での自前ベンチ（要件→設計→テストの抜け再現率・適合率）を公開できれば差別化になる（空白領域）。
- 既存リンクの検証＋欠落回復の二本立て（TVR 型）と RAG 検索の併用が研究の主流。検索で候補を絞り LLM で判定する構成を採る（発見 2・4）。
- 要件→テストの「テスト網羅の抜け」を自動出力する機能は産業でも需要がある（Alstom 発表）が、実証値は未確認なので自社データで先に測る。

## 引用してはいけない数値
- TVR の 98.87%／85.50%：検索要約の転載のみ。abstract に数値なく、評価条件（n・基準）未確認。
- Ewald 論文の F1 0.388／0.478／0.313：本文未開封。
- 99.7% 再現率：単一削除という人工的な欠落での値で、適合率なし。実運用の抜け検出精度として引用しない。
- Hayes 系の「人が高精度候補を悪化させる」：原論文未開封。年・n 不明。
- Rodriguez 2023 の F2・MAP 等の値：取得できておらず、一切引用できない。

## 検索方法
- WebSearch 4 本（Rodriguez 論文、RAG 型 TLR、人による候補確認、要件→テストのカバレッジ）と WebFetch 5 回（arXiv abs 3 件、MSR 2024、ICSE 2025 ページ）。計 10 回弱（ToolSearch 含む）。arXiv/Semantic Scholar の API は不使用。
- WebFetch は小型モデルによる要約であり、PDF 本文は未読。ResearchGate・dblp・出版社本文は回数制限で未取得。2026 年の新しい RAG 型 TLR 論文（2025 後半〜2026）は網羅できていない。
- 人が確認する効果の LLM 時代の実験（2023 年以降）は見つけられなかった（否定的結果＝検索では未発見）。
