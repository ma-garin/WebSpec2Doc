# 変更影響分析（Change Impact Analysis）商用調査

調査日: 2026-10-15。WebSearch/WebFetch 24 回。検索結果の要約を一次情報として使った箇所が多く、ベンダー公式ページ本文を直接読めたのは Jama（clear suspect links）と Codebeamer（Associations）のみ。それ以外は「検索スニペット経由」と明記する。ベンダー数値は原データが無いため引用しない。

## 1 製品比較

| 製品 | 単位 | 影響の見せ方 | 承認・監査 | テスト連携 |
|---|---|---|---|---|
| Jama Connect | プロジェクト／アイテム／リレーション | suspect（赤い警告アイコン、「Causing Suspect」表示、Project > Suspect Links 一覧）。変更前に影響を見る Impact Analysis | 管理者が trigger 項目を設定。履歴・監査ログの記述は確認できず（未確認） | 検証アイテムが suspect になる。選定は人が行う |
| Siemens Polarion | Work Item／リンク／ベースライン | リンクの suspect フラグ、Multilevel Traceability ウィジェット | auto-suspect。ワークフローで制御（拡張）。承認・監査の標準仕様は未確認 | suspect テストケースの集計ウィジェット（拡張） |
| PTC Codebeamer | Work Item／アソシエーション | Suspected バッジ、Traceability Report | Propagate suspects（順／逆／双方向）。クリアの履歴は公式文書に記述なし | 追跡レポート上で確認。自動選定は未確認 |
| IBM DOORS Next | モジュール／リンク／構成（GCM） | Links Explorer、suspect 分析 | 構成管理・ベースラインと連動（詳細は未確認） | ELM のテスト管理とのリンク（詳細は未確認） |
| Visure Requirements | 要件／リンク | トレーサビリティ・マトリクス、古い可能性のあるリンクの旗 | 変更管理機能を持つとされる。詳細は未確認 | テスト管理と同一基盤 |
| Tricentis LiveCompare | SAP 変更（transport／ChaRM 変更要求） | 影響を受けるオブジェクトの一覧、テストの抜け（カバレッジ欠落） | 未確認 | Tosca／qTest／Solution Manager と連携して実行するテストを選ぶ（ベンダー説明） |
| Testim／mabl | 未調査 | 未確認 | 未確認 | 未確認 |

- Jama: suspect は「保存後に下流を旗立て」（reactive）、Impact Analysis は「変更前にプレビュー」（proactive）と Jama が区別する [1][2]。クリアは単体と Clear All。比較表示で差分を見て判断する [1][2]。誰がクリアできるかは文書に記述なし。
- Jama: suspect が下流方向のみに伝播するという利用者報告がある（コミュニティの意見で公式仕様ではない）[2]。
- Polarion: 公式 help は検索で取得できず、仕様は拡張・API 経由の間接情報のみ [3][21]。API に isSuspect/setSuspect があり、文書更新時の auto_suspect で変更した項目のリンクが suspect になる。拡張 RoP Cascade は書き込み前に suspect 化される範囲をプレビューし、解析の深さを 1〜5 段で設定できる [3]。ベースラインの扱いは未確認。
- Codebeamer: 順／逆／双方向の suspect 伝播を関連ごとに設定できる。対象は Work Item・ダッシュボード・文書・Wiki [4]。バッジをクリックして差分を確認し、X で解除する [5]。一括クリアはコミュニティ回答のみ（公式未確認）。
- DOORS Next: 公式本文は取得できず、ブログ・資料の記述（トレース＝影響分析の土台、Links Explorer、suspect 分析）のみ [6]。クラシック DOORS ではベースライン作成で suspect 履歴が失われうるというフォーラム報告がある（Next への適用は未確認）。
- Visure: 自社ページ・アカデミーの記述のみ。suspect ロジックの詳細は未確認 [7]。
- Tricentis LiveCompare: 影響オブジェクト特定、テストのギャップ検出、リスク別の優先付け、Tosca での実行までを一連で説明する [8]。削減率はベンダー数値のため引用しない。
- 共通点: suspect は「リンク単位のフラグ＋人が解消」。解消の理由や担当者を残す標準機能を公式に確認できた製品は無い（未確認）。ここが差別化余地。
- Modern Requirements、No Magic 等も suspect 機能を持つ [22]。

## 2 規格が求める手順と成果物

- ISO/IEC/IEEE 14764:2022（保守）: ISO/IEC/IEEE 12207:2017 の保守プロセスに基づく。「保守変更の影響分析（6.1.6）」と「問題・変更分析（6.2）」を持つ。6.2 は分析、実現可能性審査、再現・検証、記録、承認、追加分析、実装、改修後システムのレビュー、最終承認の順 [9]。条文の入力・出力の詳細は有償で未確認（2006 版は入力／作業／統制／支援／出力の形式）。
- IEEE 1219: 未調査（未確認）。14764 に統合・置換された系統という理解は未検証。
- ISTQB 用語集（第三者ミラー経由、公式本文は未確認）[10]:
  - impact analysis: 変更の影響を受ける全ての作業成果物の特定。変更に要する資源の見積を含む。
  - regression testing: 変更していない領域に欠陥が入った／露出したかを検出する変更関連テスト。回帰テスト集合の十分性は対象と変更内容で決まる。
  - risk: 将来の負の結果をもたらしうる要因。影響度と発生可能性で表す。risk-based testing の公式定義は未確認。
- ISO/IEC/IEEE 29119-2: リスクベースのアプローチを取る。リスク関連の活動は「文脈の理解」「リスクの識別と分析」「リスク軽減策の識別」「テスト戦略の設計」[11]。回帰選定そのものの手順は未確認。
- IEEE 828（構成管理）: 検索で取得できず未確認。一般にベースライン・変更管理委員会による承認が構成管理の要素だが、本調査では未検証。
- ISO/IEC 25010: 未調査（未確認）。製品品質モデルを影響の分類軸（機能適合性・互換性・信頼性等）に使えるのは設計上の提案であり、規格の要求ではない。
- 導かれる成果物: 変更要求の記録、影響を受ける成果物一覧、資源見積、承認記録、変更後のレビュー結果。

## 3 研究

| 論文（年） | 手法 | データ・n | 精度 | 区分 |
|---|---|---|---|---|
| ProReFiCIA, Etezadi ら, arXiv 2511.00262（2025） [12] | LLM で変更要件に影響される要件を特定。RAG で領域知識追加 | 産業データ（要件数・変更数は未確認） | 再現率 85.7%（レビュー量は全要件の約 3.0%）、RAG で 95.8%（約 3.4%） | 実証（著者報告。追試なし） |
| Traceability Transformed (T-BERT), Lin ら, ICSE 2021 [13] | BERT による要件／課題とコードのリンク復元、3 段階学習 | OSS 3 プロジェクト | VSM 比 MAP 平均 +60.31%（記述はこの要約のみ） | 実証 |
| NoRBERT, KIT（2020 頃）[14] | BERT 微調整で要件分類。TLR の前処理に利用 | PROMISE NFR | F1 最大 94% は訂正前。訂正後は未見の案件で約 5 pt 低下と著者が訂正 | 実証（訂正版を採る） |
| 要件→コード可観測性: LLM データ拡張＋エンコーダ, arXiv 2509.20149（2025）[16] | LLM でデータ拡張＋長文脈エンコーダ | 公開 4 データセット（n 未確認） | 最大 F1 +28.59%（ベースライン比の改善幅） | 実証 |
| SpecMap, arXiv 2601.11688（2026）[15] | 階層 LLM エージェント（データシート→コード） | OSS 組込みリポジトリ（n 未確認） | ファイル対応精度 最大 73.3% | 実証（プレプリント） |
| GPT-5 によるコード変更影響分析, arXiv 2512.19481（2025）[17] | GPT-5／mini が影響コードを予測 | 新規データセット（n 未確認） | 数値なし。「性能は低い」。diff を与えると僅かに改善 | 実証（予備研究） |
| 意味埋め込み＋多段伝播の影響分析, arXiv 2606.18855（2026）[18] | 埋め込み類似度とグラフ伝播を λ で融合 | 5 シナリオの概念実証 | 数値なし | 主張（ビジョン論文） |
| RippleGUItester, arXiv 2603.03121（2026）[19] | LLM 影響分析から GUI テストを生成し変更前後で差分検出 | 実コード変更数百件（4 アプリ） | 未知のバグ 26 件（16 修正済） | 実証 |
| T-SimCSE, arXiv 2603.11800（2026）[20] | 要件トレース復元の対比学習 | 未確認 | 未確認（タイトルのみ確認） | 未確認 |

- 要点: LLM 影響分析は「高再現率＋少量レビュー」が示された（[12]）が、単一の産業データ・非公開で、追試は未確認。コード側は性能が低い（[17]）。
- 埋め込み単独では取りこぼす（要約より）。グラフ伝播との融合は主張段階 [18]。
- 引用してはいけない数値: ベンダーの削減率（LiveCompare 等の 84%・85%）、NoRBERT 訂正前の 94%、T-BERT の「+60.31%」を他データへ一般化すること。

## 4 商用水準の必須要件

| ID | 要件 | 根拠 |
|---|---|---|
| R-01 | 仕様書の変更を版単位の差分（追加・変更・削除、項目単位）として保持する | [9][10] |
| R-02 | 変更要求（Change Request）を一件ずつ記録し、理由・提出者・日時・対象版を持つ | [9] |
| R-03 | 影響を受ける成果物（項目・テストケース・画面・API）の一覧を生成する | [10] |
| R-04 | 影響の根拠を各件に付ける（リンク・類似度・出力元のどれか） | [1][12] |
| R-05 | 影響をグラフかマトリクスで見せ、深さ（段数）を指定できる | [3][7] |
| R-06 | 影響を suspect（要確認）として項目に残し、解消されるまで消えない | [1][4] |
| R-07 | suspect を引き起こす項目（変更が影響を持つ欄）を設定できる | [1] |
| R-08 | 保存前に影響範囲をプレビューできる（proactive） | [2][3] |
| R-09 | suspect の解消時に理由・担当者・時刻を必須記録し、改ざん不可の監査ログに残す | [1][4]（公式に無い点を補う） |
| R-10 | 解消前に変更前後の差分を並べて確認できる | [1][5] |
| R-11 | 影響分析の結果に人の承認ステップを置き、AI は承認しない | [9] |
| R-12 | 影響した項目に対応するテストを選び、優先度（リスク）を付ける | [8][11] |
| R-13 | 優先度は影響度×発生可能性で、算出式と入力値を画面で確認できる | [10][11] |
| R-14 | 影響を受けるのにテストが無い項目（カバレッジ欠落）を明示する | [8] |
| R-15 | LLM／埋め込みの推定は確定ではなく候補として表示し、信頼度と根拠を併記する | [12][17][18] |
| R-16 | 候補の採用・却下を記録し、再現率・適合率を自社データで継続測定する | [12][13] |
| R-17 | 変更前に確認するレビュー量（候補数／全体）を指標として出す | [12] |
| R-18 | 基準版（ベースライン）を作り、その時点の影響分析結果を固定して比較できる | [3][9] |
| R-19 | 影響分析レポートを出力できる（変更内容・影響一覧・テスト選定・承認記録） | [9][7] |
| R-20 | 影響分析の見積（影響件数、再テスト件数の見込み）を出す | [10][7] |
| R-21 | 変更後に改修結果をレビューし、影響分析の予測と実際を突き合わせる | [9] |
| R-22 | 外部 LLM へ送るデータの範囲を利用者が確認・制限できる | 設計上の提案（出典なし） |

## 出典

1. Jama Software, "Clear suspect links" 2024 頃, https://help.jamasoftware.com/en/manage-content/coverage-and-traceability/relationships/clear-suspect-links.html （本文取得）
2. Jama Software, 検索スニペット経由: https://help.jamasoftware.com/en/manage-content/coverage-and-traceability/relationships.html ／ https://www.jamasoftware.com/?p=11845 （Features in Five: Change Management）／ https://community.jamasoftware.com/discussion/comment/7274/ （コミュニティ）
3. Polarion Extensions, "Advanced Suspect" https://extensions.polarion.com/extensions/51-workflow-extension-advanced-suspect ／ "RoP Cascade" https://extensions.polarion.com/extensions/501-rop-cascade ／ python-polarion https://python-polarion.readthedocs.io/en/latest/document.html （検索スニペット経由）
4. PTC, "Managing Associations", Codebeamer 3.3, https://support.ptc.com/help/codebeamer/r3.3/en/codebeamer/cbx_user_guide/cbx_trackers/cbx_ug_associations.html （本文取得）
5. PTC, "Traceability Report", Codebeamer 2.2, https://support.ptc.com/help/codebeamer/r2.2/en/codebeamer/user_guide/1822415.html （検索スニペット経由）
6. SODIUS WILLERT, "How to Set Up, Create and Use Traceability Links in IBM DOORS Next?" https://www.sodiuswillert.com/en/blog/how-to-set-up-create-and-use-traceability-links-in-ibm-doors-next ；IBM 資料（検索結果）
7. Visure Solutions, "Using the Traceability Matrix for Impact Analysis" https://academy.visuresolutions.com/en/article/using-the-traceability-matrix-for-impact-analysis
8. Tricentis, "Impact Analysis LiveCompare" https://www.tricentis.com/products/impact-analysis-livecompare ；データシート（検索スニペット経由。数値は不採用）
9. ISO/IEC/IEEE 14764:2022 目次プレビュー https://www.vde-verlag.de/iec-normen/preview-pdf/info_isoiecieee14764%7Bed3.0%7Den.pdf ；https://iteh.eu/catalog/standards/iso/70aa2449-ac83-46d7-84c2-fe73a5a2efcc/iso-iec-ieee-14764-2022
10. ISTQB 用語集の第三者ミラー https://softwaretestpilot.com/istqb/glossary/impact-analysis ；imbus https://www.imbus.de/en/glossar/term/regression-testing （公式 glossary.istqb.org は取得失敗）
11. ISO/IEC/IEEE 29119-2:2013 概要 https://ccn-scc.ca/standardsdb/standards/8152821 ；arXiv 1905.10676 https://arxiv.org/pdf/1905.10676
12. Etezadi, Abualhaija, Arora, Briand, "LLM-Driven Cost-Effective Requirements Change Impact Analysis", 2025, https://arxiv.org/abs/2511.00262
13. Lin ら, "Traceability Transformed: Generating more Accurate Links with Pre-Trained BERT Models", ICSE 2021, https://arxiv.org/abs/2102.04411
14. Hey ら (KIT), NoRBERT, 2020, https://publikationen.bibliothek.kit.edu/1000124657
15. "SpecMap", 2026, https://arxiv.org/abs/2601.11688
16. "Synergistic Enhancement of Requirement-to-Code Traceability…", 2025, https://arxiv.org/abs/2509.20149
17. "A Dataset and Preliminary Study of Using GPT-5 for Code-change Impact Analysis", 2025, https://arxiv.org/abs/2512.19481
18. "Toward Semantically-Seeded, Graph-Propagated Impact Analysis Across Software Artifacts: A Vision", 2026, https://arxiv.org/abs/2606.18855
19. "RippleGUItester: Change-Aware Exploratory Testing", 2026, https://arxiv.org/abs/2603.03121
20. "Enhancing Requirements Traceability Link Recovery: A Novel Approach with T-SimCSE", 2026, https://arxiv.org/abs/2603.11800
21. MathWorks, "Polarion ALM" https://ch.mathworks.com/products/connections/product_detail/polarion-alm.html
22. Modern Requirements, "Using the Suspect Link Feature" https://www.modernrequirements.com/?p=14083 ；No Magic docs https://docs.nomagic.com/x/uJ7uB

## 未調査・未確認の一覧
IEEE 1219 本文、IEEE 828、ISO/IEC 25010 の影響分析上の位置づけ、Polarion／DOORS Next／Visure の公式 help 本文、Testim／mabl、ISTQB 公式用語集の本文、ISO 14764 の入出力条文、各 arXiv の n（件数）。
