# P7b 要件品質の評価データと注釈の標準

## 結論（3 行）
- PROMISE NFR（625 件）と ARTA（4,752 件）は規模・内容を確認できたが、PROMISE 系は CC BY-NC-SA 4.0 の非商用で、商用 SaaS の精度公開に使えるかは未確認（要・原典確認と法務判断）。ARTA の Zenodo ページはライセンス名を記載していない。
- ReqEval の規模・ライセンスは今回確認できなかった（ICSE22 論文 PDF は証明書エラーで取得失敗、検索では ReqEval の名称自体がヒットせず）。名称の正否も未確認。
- 要件の曖昧さ注釈の kappa 典型値は、要件工学の一次資料で確認できなかった。ARTA データセットは注釈者数・一致度とも未報告。

## 発見

### 1. ReqEval（Ezzini ら）
- 区分=未確認。規模・ライセンス・注釈者数・kappa いずれも未確認。
- 関連で確認できたこと（検索結果の要約、区分=主張）: ICSE 2022「Automated Handling of Anaphoric Ambiguity in Requirements: A Multi-solution Study」は 6 つの解法を比較。最良の検出は平均 precision 約 60%・recall 100%、最良の解決は成功率約 98%（検索要約の値。本文未確認）。
- 後続ツール TAPHSIR（ML の曖昧さ検出＋照応解決）。Ezzini の博士論文は ORBilu 上で利用ライセンス付き（種類は未確認）。
- URL: https://orbilu.uni.lu/handle/10993/52045 ／ https://orbilu.uni.lu/bitstream/10993/50211/1/icse22-main-1094.pdf（取得失敗）／ https://orbilu.uni.lu/bitstream/10993/52637/1/TAPHSIR.pdf

### 2. PROMISE NFR（Cleland-Huang ら）
- 区分=実証（規模は複数論文の記述）／ライセンスは間接証拠。
- 規模: 625 件（機能 255・非機能 370。非機能は 11 カテゴリ）。拡張版 PROMISE_exp（Lima ら）は 969 件（機能 444・非機能 525。34 の SRS を追加）。出典は arXiv 1707.02358 等の検索要約で、原典は未確認。
- ライセンス: Dalpiaz らの拡張版 Zenodo レコードの LICENSE が「元の PROMISE は CC BY-NC-SA 4.0、派生物も同じ。商用利用不可」と明記（取得済み）。PROMISE_exp 自体のライセンスは未確認。原典の PROMISE リポジトリ記載は未確認。
- 注釈: 原典の注釈者数・kappa は未確認。
- URL: https://zenodo.org/records/14709254/files/LICENSE.txt ／ https://arxiv.org/pdf/1707.02358 ／ https://sol.sbc.org.br/index.php/sbes/article/view/9364

### 3. ARTA データセット（Zakeri-Nasrabadi ら）
- 区分=実証（Zenodo ページ取得済み）。
- 規模: 4,752 件、英語、24 プロジェクト文書（DS1 985／DS2 1,092／DS3 1,522／DS4 1,153）。要件ごとに 9 種の smell を手作業で付与。単語レベルの辞書（4 種）あり。
- ライセンス: ページに明記なし（アクセスは Open 表示のみ）。商用利用可否は未確認。
- 注釈者数・一致度: 未報告。
- ツール ARTA（Automatic Requirement Testability Analyzer）は smell に基づく testability を測る Web アプリ。GitHub とツールのライセンスは未確認。
- URL: https://zenodo.org/records/4266727 ／ https://arxiv.org/pdf/2403.17479

### 4. 注釈者数と kappa の典型値
- 要件の曖昧さ注釈に特化した値は確認できず（区分=未確認）。
- 一般 NLP の曖昧さ研究の一例（区分=実証だが要件ではない）: 3 ラベルの Fleiss kappa が 0.62／0.65／0.44（4 名の検証者が共通 50 例を注釈）。出典 https://arxiv.org/pdf/2304.14399（検索要約の値）。
- 解釈: 0.41〜0.60 を moderate とする慣行（Landis & Koch。検索要約経由）。Artstein & Poesio は kappa の解釈の難しさと Krippendorff alpha を論じる: https://www.cl.cam.ac.uk/teaching/1516/R216/Artstein.pdf

### 5. 商用ツールが精度公開に使える公開データ
- 確認済みの候補は上記 PROMISE 系（非商用ライセンス）と ARTA（ライセンス不明）のみ。いずれも英語。日本語の公開データは今回の調査で確認できず（未確認）。

## 勝つための示唆
- 公開データの精度は英語・非商用が主。日本語要件の自社注釈データ（複数注釈者＋ kappa/alpha 公開）を作れば、それ自体が差別化になる。
- 精度公開は PROMISE 系を「参考指標」に留め、商用利用前にライセンスを確認する。ARTA は著者に照会して明文化を得る。
- 注釈ガイドラインと一致度（kappa に加え alpha）を公開すると、競合が示していない根拠になる。曖昧さは主観が絡み kappa が中程度に落ちる前提で設計する。
- ReqEval を比較対象にする場合は、原論文の規模・ライセンスを一次資料で確認してから。

## 引用してはいけない数値
- ReqEval の規模・ライセンス・kappa（未確認）。
- 「最良検出 precision 約 60%・recall 100%、解決成功率約 98%」は検索要約の二次情報で、本文未確認。引用前に論文本文で確認。
- 0.62／0.65／0.44 は一般 NLP の値で、要件の曖昧さの典型値ではない。
- PROMISE の 625／969 は複数論文の要約経由で、原典未確認。
- 「Landis & Koch の閾値」は検索要約経由。

## 検索方法
- WebSearch 4 回（ReqEval／PROMISE NFR／ARTA／要件曖昧さ kappa）、WebFetch 3 回（ICSE22 PDF は証明書エラーで失敗、ARTA Zenodo、PROMISE 拡張版 LICENSE は成功）。arXiv API・Semantic Scholar API は不使用。ツール呼び出し上限 10 回のため、ReqEval の一次資料確認と PROMISE 原典の確認は未実施。
