# 競合ツールと先行研究の調査（トレーサビリティ・要求品質）2026-10-18

調査方法: サブエージェント 5 本（各 WebSearch/WebFetch 15 回目安）。出典は各節。未確認は明記。

## 1. 国内ツール

調査: WebSearch/WebFetch 15 回（2026-10-18）。ベリサーブ公式サイトは 404（URL 推測が外れた）で一次情報に到達できず、第三者掲載・ニュース記事が根拠。「未確認」は裏取りできていない事項。
注意: 正式名は「Contrack」ではなく **ConTrack**（コントラック）。SCSK の別製品・契約管理 AI とは別物。

### 1-1. ConTrack（ベリサーブ）

| 項目 | 内容 |
|---|---|
| 正式名 | ConTrack |
| 提供元 | 株式会社ベリサーブ |
| URL | 公式は未確認（veriserve.co.jp 配下）。掲載: https://saas.imitsu.jp/cate-document-management/service/3482 |
| トレース | 上位/下位成果物の関連管理。ラインビュー・マトリクスビュー。トレース設定 3 パターン |
| 取込形式 | Office・ReqIF・テキスト・PDF。Word/Excel を変換せず利用、ファイルジャンプで直接編集 |
| 曖昧表現検出 | 該当記載なし（未確認）。「文書解析エンジン」は取込・構造解析の位置づけ |
| AI/LLM | 2023-04 SGSジャパンの AI エンジン連携。トレース先候補の推薦・学習（LLM と明記はなし） |
| レビュー支援 | 変更時の影響範囲把握。曖昧性レビューは未確認 |
| 出力 | ビュー表示。レポート出力は未確認 |
| 価格 | 非公開（要問合せ）。トライアルあり |
| 提供形態 | クラウド/オンプレとも記載なし（未確認） |
| 想定ユーザー | 既存成果物が大量にある長寿命の大規模システムの開発組織 |

- 機能: 要求管理・変更管理・構成管理・文書解析（imitsu 掲載）。2024-10 版で公開 API と複数リポジトリ接続（構成管理への登録・更新を契機に分析・タスク依頼を自動化）。出典: https://cloud.watch.impress.co.jp/docs/news/1494808.html ほか検索要約
- AI 連携は学習のために成果物本文とトレース情報を AI エンジンへ送る仕組み（検索要約。機密文書の扱いは導入時の論点。未確認）
- 強み: 既存 Word/Excel 資産をそのまま使える。導入の早さを訴求（ベンダー主張）。利用者評判「要件情報の一元化・漏れ減少」は strate.biz 掲載（実証ではない）
- 弱点・不明点: 全文検索・版履歴・OCR 等は非対応と掲載ページが示す。曖昧表現検出なし（未確認）。価格非公開。Web 画面の撮影や実画面からの仕様書生成機能は確認できず
- ベリサーブは別に生成 AI の品質保証サービス・QA4AIDD を展開するが ConTrack の機能ではない

### 1-2. CoBrain（エクスモーション）

| 項目 | 内容 |
|---|---|
| 正式名 | CoBrain（コブレイン） |
| 提供元 | 株式会社エクスモーション |
| URL | https://www.aspicjapan.org/asu/service/99540（公式 URL は未確認） |
| トレース | 記載なし（未確認） |
| 取込形式 | 提案書・議事録・設計書等をアップロード。自由書式から USDM へ変換 |
| 曖昧表現検出 | 自動レビュー 5 種: 曖昧表現・抜け・矛盾・校正・仕様の穴（ベンダー主張） |
| AI/LLM | 生成 AI。要件特化チャット。基盤モデルは非公表。入力データは学習に使わない |
| レビュー支援 | 添削、変更前後の差分表示、版履歴 |
| 出力 | USDM 要件定義書、Excel、UML 図 |
| 価格 | 非公開（要問合せ） |
| 提供形態 | Web アプリ + Word アドイン |
| 想定ユーザー | 自社・受託・派生開発のチーム |

- 強み: 日本の要件記述手法 USDM に直結。セキュリティ認証（ISO27001/27017・Pマーク・SSO・MFA）を明示
- 弱点・不明点: 検出精度の第三者検証なし（ベンダー主張のみ）。トレーサビリティ管理・実画面連携は記載なし

### 1-3. ClearDoc（シーイーシー）

| 項目 | 内容 |
|---|---|
| 正式名 | ClearDoc |
| 提供元 | 株式会社シーイーシー（PROVEQ サービス事業部） |
| URL | 公式は未確認。解説: https://codezine.jp/article/detail/5470（取得は 403、検索要約のみ） |
| トレース | なし（未確認） |
| 取込形式 | Word・Excel・PowerPoint・XML・テキスト。図表・画像は対象外 |
| 曖昧表現検出 | 日本語 1 文ごとにあいまい度を算出、高い順に表示、原因推定と対策案 |
| AI/LLM | 独自開発の計測。LLM かは未確認 |
| レビュー支援 | 優先して直す文の絞り込み |
| 出力 | Excel |
| 価格 | 非公開。体験版 15 日（検索要約） |
| 提供形態 | 第三者検証サービスの一部。単体提供の可否は未確認 |
| 想定ユーザー | 要件定義・基本設計のレビュー担当 |

- 強み: 日本語文書の曖昧さに特化し、定量スコアで優先順位を付ける
- 弱点・不明点: 最新版・価格・導入実績は未確認。学術では曖昧文判定の適合率が低い報告がある（南山大 2023 卒論等。一般論で本製品の実測ではない）

### 1-4. 周辺の国産候補（要件定義支援 AI。出典: https://www.aspicjapan.org/asu/article/82833）

| 製品 | 提供元 | 主な機能 | 価格 |
|---|---|---|---|
| Acsim | ROUTE06 | 会話で業務フロー生成、設計書・RFP 出力 | 要問合せ |
| SolvifAI | ソルビファイ | 資料からドラフト、レビュー・PM 自動化 | 要問合せ |
| Kakusill | Atsumell | 既存資料から案、不足論点を AI が質問 | 要問合せ |
| Seiko Futureworks | セイコーソリューションズ | 要件定義書の AI レビュー、知見の形式知化 | 要問合せ |
| XupperⅡ | JBCC | 設計情報のリポジトリ一元管理、図の作成 | 要問合せ |

- いずれも「作る・レビューする」側で、実運用中 Web の実画面から仕様書を起こす・ドリフトを検出する製品は今回の調査範囲で確認できず（未確認。網羅調査ではない）
- 国産の要求管理（DOORS 相当）を網羅した一覧は取得できなかった（検索に国内製品が出ず）。「国内に他に無い」とは言えない

### 勝つための示唆

1. 差別化軸は「実画面から起こした仕様」と「文書との差分（ドリフト）」。ConTrack は文書間トレース、CoBrain/ClearDoc は文書内の品質で、実際の Web との突合は確認できなかった。
2. ConTrack の弱点は曖昧表現検出が見当たらない点と、AI が推薦中心で LLM 生成ではない点。トレース先の提案を理由付きで出せれば優位に立てる。
3. CoBrain は USDM と ISMS 認証で信頼を取りに来ている。対抗するなら出力に USDM・Excel を揃え、データ外部送信の有無を明示する。
4. ClearDoc 型のあいまい度スコアは決定的で説明可能。当方の決定的エンジン（LLM 不使用）は同じ土俵で「なぜ曖昧か」を根拠付きで示せる。精度は自前で測り公開する（競合は主張のみ）。
5. 価格は全社が非公開。公開価格と無料トライアルは、問合せ前提の国内市場で購入判断を早められる手段になる。
## 2. 海外の要求管理・トレーサビリティツール

調査日 2026-10-18。WebSearch/WebFetch 15 回の上限内。PTC・Capterra への直接取得は 403 で失敗。以下の「未確認」は一次資料で確認できなかった事項。ベンダー主張は「(V)」、第三者は「(T)」、実証（実機・独立ベンチ）は本調査では 0 件。

### 比較表

| ツール | 提供元 | AI機能 | トレース自動提案 | 価格 |
|---|---|---|---|---|
| Jama Connect | Jama Software | Advisor(品質採点) | 未確認 | 要見積 |
| Polarion X | Siemens | Copilot系(V) | 主張あり(V) | $42/人月〜 |
| DOORS Next | IBM | Watson品質評価 | 未確認 | 要見積 |
| Codebeamer | PTC | 要件/テスト補助 | 主張あり(V) | 要見積 |
| Visure | Visure | 品質分析 | 未確認 | 要見積 |
| ReqView | Eccam | 未確認 | なし(未確認) | €430/人年〜 |
| Modern Req. | Modern Req. | Copilot4DevOps | 未確認 | $30/人月〜 |
| Innoslate | SPEC Innovations | NLP取込 | 未確認 | 未確認 |
| SpiraTeam | Inflectra | 「AI」(詳細不明) | 未確認 | $57/人月 |

- SodiusWillert は検索で情報が得られず未確認（Modern Requirements・Innoslate と同様、一次資料の取得に至らず）。
- 「Not stated / 未確認」は「機能が無い」ではなく「確認できなかった」の意味。

### ツール別

**Jama Connect**（Jama Software / https://www.jamasoftware.com/platform/jama-connect/jama-connect-advisor/）
- トレース: Live Trace Explorer を v9.28.1 で導入(V) https://support.jamasoftware.com/hc/en-us/articles/41244920807437-Jama-Connect-v9-28-x-V3 。Trace Score で完全性を測る(V、スポンサー記事 https://thenextweb.com/news/best-ai-requirements-management-software-2026 )。カバレッジの詳細指標を拡充(V)。
- AI: Advisor は INCOSE/EARS 規則で要件を採点（緑81-100%・黄61-80%・赤0-60%、規則別の修正提案）(V) https://help.jamasoftware.com/ah/en/jama-connect-advisor-/interpreting-the-results.html 。「AI 検索エンジンは無い」と自社サポートが明言(2026-04-09) https://support.jamasoftware.com/hc/en-us/articles/44976305392653-Does-Jama-Connect-Have-an-AI-Based-Search-Engine 。トレースリンク自動提案は確認できず（Advisor が関係の特定を助けるという記述のみ(V)）。
- 画面: 色分け採点、トレース探索ビュー。マトリクス/グラフの詳細は未確認。
- 価格: 要見積。第三者の $57.33/人月(同時接続・クラウド)は TrustRadius の推定で公式ではない https://www.g2.com/products/jama-connect/pricing 。
- 弱点: G2 は強み/弱みの集計データ不足。要件・コンプライアンス寄りでライフサイクル全体ではない、との指摘はスポンサー記事内の主張(T、未検証)。

**Siemens Polarion（Polarion X）**（Siemens / https://blogs.sw.siemens.com/polarion/siemens-and-microsoft-team-up-to-deliver-polarion-x-on-azure/）
- AI: Azure OpenAI 基盤の Copilot で要件分析・トレースリンク自動化・リスク検知を提供と発表(V、2025-11-18)。詳細仕様・精度は未確認。
- トレース: ライフサイクル全体のトレーサビリティ、変更・構成管理。suspect link の記述は確認できず。
- 価格: Polarion X Base が $42/人月〜、他は要見積 https://www.g2.com/compare/jama-connect-vs-polarion (T)。
- 弱点: G2 の主な不満は学習コスト(4件)と複雑さ(3件)（件数が少なく参考値）。スポンサー記事は「習得に数週間」と主張(未検証)。

**IBM DOORS Next**（IBM / https://www.ibm.com/products/requirements-management.html）
- AI: 要件の品質スコアと言い換え提案、自然言語での問い合わせ・要約・翻訳(V)。Watson 系で INCOSE 由来の 10 種の品質問題を検出と第三者ブログは記述（T、ベンダー系）。トレースリンク自動提案は確認できず。
- トレース: ベースライン、多段トレース、OSLC で Rhapsody/ETM/EWM と連携。
- 価格: 要見積。Capterra で「高コストで小規模には不向き」の声 https://www.capterra.com/p/238454/IBM-Engineering-Requirements-Management-DOORS-Next/reviews/ （検索結果の要約。本文は 403 で未確認）。
- 弱点: G2 4.0/5(136件)、不満は機能不足・非効率が各1件のみ。Classic からの移行経路が単純でない、管理負荷が高い(スポンサー記事の主張、未検証)。

**PTC Codebeamer**（PTC / https://www.ptc.com/en/products/codebeamer/codebeamer-ai ※直接取得は 403）
- AI: Codebeamer AI に Requirements Assistant(品質問題の指摘)、Test Case Assistant(要件からテスト条件・ケースを提案し関係を維持)、Search Assistant https://support.ptc.com/help/codebeamer_ai/en/codebeamer.html 。Test Case Assistant は上位要件で最も良く動く、と公式ヘルプ。
- トレース: マトリクス・影響分析ビュー（T、FitGap 系で出典が弱い）。リンクの継続維持を AI が支援と PTC は主張(V)。
- 価格: 要見積。
- 弱点: G2 比較では AI トレース系項目が「データ不足」。スポンサー記事は RM 向け AI は成熟途上と主張(未検証)。

**Visure Requirements ALM**（Visure Solutions / https://visuresolutions.com/pricing/new）
- AI: Quality Analyzer(要件品質評価)などアドオン。トレースリンク提案は確認できず。
- トレース: 要件-テスト-FMEA の連携(V)。
- 価格: 見積制。$2,990 買い切りの参考値が第三者に出るが公式でなく不確実 https://www.capterra.co.uk/software/146581/visure-requirements 。14 日トライアル。
- 弱点: スポンサー記事は連携エコシステムが小さく AI は発展途上と主張(未検証)。

**ReqView**（Eccam / https://www.capterra.com/p/145388/ReqView/pricing/）
- トレース: PRO にエンドツーエンドのトレース分析と Word/Excel/PDF/HTML 出力。TEAM は Jira Cloud 連携。
- AI: 確認できず。
- 価格: PRO €430/人年、TEAM €580/人年、ENTERPRISE €1,740/年(Capterra)。TrustRadius は $510/$690/$2,060 でオンプレ。出典間で食い違い。
- 弱点: 未確認（レビューの不満は取得できず）。

**Modern Requirements4DevOps / Copilot4DevOps**（Modern Requirements / https://www.softwareadvice.com/product/520634-Copilot4DevOps/）
- AI: Azure DevOps 上の AI チャット、要件生成、テストケース生成、ギャップ分析、影響評価、図の生成（掲載サイトの説明、T）。
- 価格: Copilot4DevOps が $30/人月〜(アグリゲータ)。4DevOps 本体は未確認。
- 弱点: Azure DevOps への強い依存(スポンサー記事、未検証)。

**Innoslate**（SPEC Innovations）
- 自然言語文書を構造化要件に取り込む NLP、MBSE(SysML/DoDAF)との連携(スポンサー記事 T)。価格・トレース提案・画面は未確認。

**SpiraTeam**（Inflectra / https://www.capterra.com/p/85434/SpiraTeam/pricing/）
- 要件・テスト・課題を一体で追跡。AI 自動化を謳うが詳細不明(V)。
- 価格: クラウド約 $57.33/人月、買い切り $558/人(Capterra)。
- 弱点: Capterra 4.2/5(98件)。レポートのカスタマイズが難しいという声あり。

**SodiusWillert**: 未確認（検索で該当情報を得られなかった）。

### 横断所見
- トレースリンク自動提案を「出荷済み」と独立に確認できた製品は 0。Polarion X と Codebeamer がベンダー主張として掲げるのみ。AI の中心は要件文の品質採点（Jama・IBM・Visure）とテストケース生成（Codebeamer・Modern Req.）。
- 価格は大半が見積制。公開値は ReqView・SpiraTeam・Polarion X Base・Copilot4DevOps のみ。
- 不満の独立情報は少なく、学習コスト・複雑さ・高コストが目立つ。件数は 1〜4 件で弱い根拠。

### 勝つための示唆
1. 要件⇔設計⇔テストのリンク候補を根拠付きで提案する機能は、海外大手でも実証が薄い。候補の根拠（どの語が一致したか）を画面に出し、採否を1操作で記録する形で差別化する。
2. 競合の AI は文章品質の採点が主。文書間の矛盾・欠落の「対検査」（決定的ルールで再現可能）を前面に出し、LLM に頼らない説明可能性を売る。
3. カバレッジはマトリクスとスコア1つに集約する流れ（Jama Trace Score）。件数でなく「未割当の要件」「孤立した設計項目」を一覧で直行できる導線にする。
4. 学習コスト・複雑さ・高額が不満の中心。見積制ではなく、初日から使える画面と公開価格で対抗する。
5. 影響分析は Codebeamer・Jama で言及はあるが詳細未確認。変更した項目から下流（設計・テスト）の影響範囲を1画面で見せ、差分と再レビュー対象を示す機能を優先して実機検証で上回る。
## 3. 要求品質の自動検査ツール

調査方法: WebSearch 13 回 + WebFetch 3 回(上限 15 回のうち 14 回使用)。検索要約と抜粋ベースで、ベンダー本文の全読はしていない。取得できなかった項目は「未確認」。

### 比較表

| ツール | 規則の根拠 | 日本語 | 精度の公開値 | 修正提案 |
|---|---|---|---|---|
| QVscribe (QRA) | INCOSE GtWR, NASA, EARS | 未確認 | 無し | 無し(指摘のみ) |
| Visure Quality Analyzer | QVscribe 技術, 8 指標 | 未確認 | 無し | 未確認 |
| IBM RQA | INCOSE 準拠(Watson NLP) | 未確認 | 無し | 未確認 |
| Jama Connect Advisor | INCOSE + EARS | 未確認 | 無し | 書き直し誘導(スコア) |
| ReqSuite RM | 独自(曖昧・重複・矛盾) | 未確認 | 無し | 未確認 |
| Copilot4DevOps | 6C, INVEST 等 + OpenAI | 未確認(LLM依存) | 無し | あり(生成) |
| Valispace/Altium | INCOSE 規則 | 未確認 | 無し | コメント列に改善文 |
| Paska(研究) | Rimay CNL | 無し(英語想定) | 89%/89% | あり(パターン推薦) |
| Smella(研究/OSS) | Requirements Smells | 無し(英語) | 59%/82% | 無し |
| Smarter Requirements / Requirements Scout / ARSENAL | - | - | - | 今回の検索で実体を確認できず(未確認) |

### ツール別

- **QVscribe**: https://qracorp.com/qvscribe/ ・ https://qracorp.com/?p=539
  - 根拠: 2019 ベンダーリリースで「INCOSE ガイドのほとんど」(定量化不能・受動態・余剰不定詞・逃げ句)。既定値は INCOSE と NASA 標準由来(ベンダー主張)。EARS 適合判定あり(NLP4RE 2020 論文 https://ceur-ws.org/Vol-2584/NLP4RE-paper3.pdf)。
  - 連携: Word, Excel, Polarion, DOORS Next, Jama。ISO 29148 への言及は検索結果に無し(未確認)。
  - 弱点: 「報告のみで要求を変更しない」(ベンダー記述)。規則数・精度は非公開。ReqWriter という別製品が書き換え担当(https://qracorp.com/guides_checklists/automating-the-incose-guide-for-writing-requirements/)。
- **Visure Quality Analyzer**: https://visuresolutions.com/tool-suite/quality-analyzer
  - 8 つの品質指標のスコアカード。QVscribe 技術がベース。ISO/IEEE 29148 は製品全体の対応標準として列挙されるが、本機能への適用方法は未確認。AI アシスタント Vivia は EARS/IREB/INCOSE のスコアリングを謳う。
  - 弱点: 規則の詳細・精度は非公開。
- **IBM RQA**: https://jazz.net/blog/index.php/tag/watson-ai/
  - Watson NLP を INCOSE ガイドで事前学習、要求ごとにスコア。DOORS / DOORS Next 連携。SaaS 版は終了、REQUISIS が代替提供(https://requisis.com/en/saas-doors-dng/rqa-saas.html)。
  - 弱点: 定量的な精度の公開値は見つからず。製品の継続性に不安。
- **Jama Connect Advisor**: https://www.jamasoftware.com/datasheet/jama-connect-advisor
  - 利用者が INCOSE / EARS の規則を選んでスコア化。単体・一括、スコア推移の追跡。
  - 弱点: スコア算出方法・精度は非公開。「手戻りの 85%」はベンダー引用の数字で原データ未確認。AI テストケース生成等はロードマップ段階。
- **ReqSuite RM (OSSENO)**: https://makingofsoftware.com/2022/03/reqsuite-rm-intro/
  - 構造(トレース欠落)と言語(曖昧・重複・矛盾・未定義語/略語)の自動チェック。規則根拠は未確認。
- **Copilot4DevOps (Modern Requirements)**: https://modernrequirements.com/copilot4devops
  - Azure DevOps 用。6C(明確・完全・簡潔・一貫・正確・文脈)で 0〜100% 評価。Plus は INVEST / PABLO / MoSCoW / SWOT。OpenAI API 利用。
  - 弱点: INCOSE 規則の網羅ではなく LLM の一般判断。再現性・精度は非公開。
- **Valispace / Altium ValiAssistant**: https://docs.valispace.com/vhd/quality-assessment
  - INCOSE 規則でスコア(50 未満 Low、50〜70 Medium、70 超 High)と改善コメントを列に出力。
- **Paska**: https://arxiv.org/abs/2305.07097 (TSE 2024)
  - Rimay(制御自然言語)パターンでスメル検出と修正案推薦。金融 13 システム・2,725 件の産業ケーススタディで検出 適合率/再現率 89%/89%、推薦 96%/94%。INCOSE / ISO 29148 の言及は無し。
  - 弱点: 1 業種のみ。対応言語と公開状況は未確認。
- **Smella**: https://arxiv.org/pdf/1611.08847 (Femmer ら)
  - POS タグ・辞書・見出し語化による要求スメル検出。平均 適合率 59%/再現率 82%(元論文、測定条件は未確認)。2024 の別研究では後続ツールに劣後と報告。
  - 弱点: 偽陽性が多い。英語中心。
- **Smarter Requirements / Requirements Scout / ARSENAL**: 検索で製品・文献の実体を確認できず。未確認。

### 日本語の状況
- 製品として日本語対応が確認できたものは無し(全ベンダー未確認)。
- 学術側: 曖昧語辞書の拡張(南山大 2023 卒論)、表記ゆれ・定義漏れ検出ツール(工学院大 位野木 2019 https://shingi.jst.go.jp/pdf/2019/2019_kogakuin_2.pdf)、LLM による要求インスペクション再現性の分析(デンソー、言語処理学会 2025 https://anlp.jp/proceedings/annual_meeting/2025/pdf_dir/Q9-5.pdf)。いずれも公開ツールとしては未確認。

### LLM 利用の実証値
- INCOSE 基準の専門家正解に対し、OpenAI/Anthropic 計 10 モデルを評価: 最良の Anthropic モデルで検出 中央値 47%、誤指摘 11%。必要性・正確性の欠陥はほぼ見逃し。世代が新しくても改善は一貫せず。著者結論「自律評価者としては未信頼」(https://arxiv.org/pdf/2609.03230)。
- ISO 29148 に基づく LLM 品質保証研究では、独立評価で適合率が低く偽陽性が多いと報告(https://arxiv.org/pdf/2408.10886、詳細は本文を読めず未確認)。
- 矛盾検出: NLI(自然言語推論)方式、SAT+LLM(著者報告 F1 0.91 対 ChatGPT 単独 0.46、自己実験)、アラビア語 2.7 万ペアのデータセット AraREQ(https://aclanthology.org/2026.lrec-1.553/)。重複検出に特化した研究は今回見つからず。
- 古典ツールは再現率 0.85〜0.98 だが適合率は最良 0.68(上記検索要約の引用、一次出典は未確認)。

### 勝つための示唆
1. **日本語の専用検査は空白市場**: 商用の日本語対応は未確認。形態素解析 + 曖昧語辞書 + 日本語特有の係り受け曖昧性を規則として持てば直接競合が見えない。
2. **ルール根拠を表示**: 指摘ごとに INCOSE GtWR の規則番号 / ISO 29148 の特性名を付ける。競合は根拠の粒度や規則数を非公開で、差別化点になる。
3. **決定的ルールで検出、LLM は修正案と説明に限定**: LLM の検出は取りこぼし約半分・非再現。検出は決定的に、LLM は書き換え案生成に使い、人が採否を決める。
4. **精度を自前で公開**: 競合は精度の公開値が無い。注釈済み日本語コーパスで適合率/再現率を規則別に出せば信頼性で勝てる。ただし Smella の適合率 59% 級の偽陽性を避ける設計(規則別に重大度と抑止設定)が前提。
5. **要求間の矛盾・重複を同一画面に**: 単体検査(QVscribe 型)は成熟、ペア検査は ReqSuite 以外ほぼ未確認。当リポジトリの docverify(要件⇔基本設計の対検査)と接続し、トレーサビリティ欠落 + 矛盾 + 重複を一括で出す。
## 4. トレーサビリティリンク回復の研究

調査方法: arXiv API 3 回（キーワード検索）・arXiv id_list 1 回・WebSearch 4 回・WebFetch（arXiv abs/html、LiSSA 著者ページ）5 回。計 15 回。Semantic Scholar API は 429 で不可。
区分: 【実証】=本文または abstract で数値を確認／【主張】=abstract の定性的主張のみ／【未確認】=本文を読めていない。
制約: 本文を読めたのは TVR のみ。他は abstract またはメタデータ。arXiv 検索は網羅ではない（LLM×TLR の全数調査ではない）。

### 最新論文（2023〜2026）

| 論文 | 年・媒体 | 対象 | 区分 |
|---|---|---|---|
| Rodriguez, Dearstyne, Cleland-Huang "Prompts Matter" | 2023 / arXiv 2308.00229 | 汎用 | 主張 |
| Fuchß ほか LiSSA | ICSE 2025 pp.1396-1408 | 要件→コード他 | 主張 |
| Niu, Pan, Briand, Hu TVR | arXiv 2504.15427 (v5 2026-07) | 要件→要件 | 実証 |
| Alor, Khatoonabadi, Shihab | arXiv 2506.16440 (2025-06) | 文書→コード | 実証(abstract) |
| Zhang ほか(Niu N.) LLM 増強+エンコーダ | arXiv 2509.20149 (2025-09) | 要件→コード | 実証(abstract) |
| Fuchß ほか "Who's Who?" ArTEMiS | arXiv 2511.02434 / DOI 10.1145/3807453 | 文書→設計モデル | 実証(abstract) |
| Nipane ほか SpecMap | arXiv 2601.11688 (2026-01) | データシート→コード | 実証(abstract) |
| Alturayeif, Ahmad, Hassine TraceLLM | arXiv 2602.01253 / Requirements Engineering 31(6) 2026 | 要件・設計・テスト・規制 | 主張 |
| Essam ほか Trust-Aware Multi-Agent | arXiv 2606.17203 (2026-06) | 自動車 | 主張 |
| Akarsu ほか Triple-Robustness RAG | arXiv 2608.00705 (2026-08) | 多段要件追跡 | 実証(abstract) |
| Shi ほか 正規化ユースケース | arXiv 2608.15726 (2026-08) | 要件→コード | 主張 |

各論文の詳細（手法／データ／結果／示唆／参照先）:

**TVR** (Niu, Pan, Briand, Hu。https://arxiv.org/abs/2504.15427) 【実証・本文確認】
- 手法: 既存リンクの妥当性検証 + 欠落リンクの回復。LLM + RAG（埋め込みは Amazon Titan、コサイン類似、K=3）。
- データ: 自動車 1 案件。ステークホルダ要求 1,320・システム要求 48・リンク 2,132（有効 1,913／無効 219）。注釈者 2 名、κ≈0.962。LLM 13 種を比較（Amazon Bedrock 経由）。
- 結果（最良: Claude 3.5 Sonnet + RAG、leave-one-out、温度 0）: Accuracy 98.87%、macro-F1 96.72%。無効リンク検出 P 95.00／R 93.14／F1 94.06。
- 同条件の比較: LiSSA-KISS macro-F1 53.81、LiSSA-CoT 52.89、TF-IDF 49.40、SBERT 57.82（無効リンクの F1 は 10〜24%）。論文は F2 を報告していない。
- 未知バリエーション: Accuracy 97.13%／macro-F1 90.86%。欠落回復: 候補 1,919 組のうち 502 を有効と予測、正しさ 85.50%（人手検証、κ≈0.92）。
- 示唆: 「リンクがある前提で探す」より「既存リンクの無効を検出する」方が実務価値が高い。単一案件・単一ドメインの結果。
- 参照: Hey 2021、Rodriguez 2023、Fuchß 2025、Cleland-Huang 2005 ほか（関連研究が後半で読めず、一部のみ確認）。

**LiSSA** (Fuchß, Hey, Keim, Liu, Ewald, Thirolf, Koziolek。ICSE 2025、DOI 10.1109/ICSE55347.2025.00186。https://fuchss.org/conferences/icse25/) 【主張】
- 手法: 検索で候補を絞り LLM に判定させる RAG の汎用枠組み。プロンプト長制限を回避。
- データ: 要件→コード、文書→コード、アーキテクチャ文書→アーキテクチャモデルの 3 課題。n と F1 は著者ページに無く未確認（再現パッケージ: https://doi.org/10.5281/zenodo.14714706）。
- 結果: コード関連 2 課題で SOTA を有意に上回ると主張。著者自身が「実用には更なる研究が要る」と述べる。
- 示唆: TVR の自動車データでは LiSSA は無効リンク検出が弱く（上記）、汎用手法はドメイン固有の検証に劣る可能性がある。

**Prompts Matter** (Rodriguez, Dearstyne, Cleland-Huang。arXiv 2308.00229、2023-08-01) 【主張】
- 手法: LLM でリンク予測を引き出すプロンプト設計の知見。候補リンクのランキングで従来のゼロショットを上回ると主張。
- 数値: abstract に無し。未確認。

**Alor ほか "Evaluating the Use of LLMs for Documentation to Code Traceability"** (arXiv 2506.16440、2025-06。査読先は不明) 【実証(abstract)】
- データ: Unity Catalog と Crawl4AI の 2 新規データセット。n 不明。Claude 3.5 Sonnet・GPT-4o・o3-mini。ベースライン TF-IDF／BM25／CodeBERT。
- 結果: 最良 LLM の F1 が 79.4% と 80.4%（モデル名の対応は未確認）。関係の説明が完全に正しい割合は 42.9〜71.1%。
- 示唆: 「1 対多で当てる」課題設定が性能に効く。説明の正しさは F1 より低い。

**Zhang, Zhou, Niu, Hua, Liu** (arXiv 2509.20149、2025-09) 【実証(abstract)】
- 手法: LLM によるデータ増強 + 強いエンコーダで要件→コードの教師データ不足を補う。
- データ: 公開 4 データセット。結果: ベースライン比で F1 最大 +28.59%、F2 最大 +28.9%（相対か絶対かは abstract から不明）。増強単独で最大 +26.66%、エンコーダで +2.21〜11.25%。10 ベースラインを上回る。LLM の種類は有意な要因でない。

**Fuchß ほか "Who's Who?"** (arXiv 2511.02434、DOI 10.1145/3807453) 【実証(abstract)】
- 手法: 文書中のアーキテクチャ要素を LLM で認識（ArTEMiS）。文書とコードからモデルを自動構築（ExArch）。ICSA 2025 論文の拡張。
- 結果: F1 は TransArC 0.87（手作業モデルが前提）、ExArch 0.86（文書とコードのみ）、ArTEMiS 0.81（SWATTR と同等）。データセット名と n は未確認。

**SpecMap** (Nipane, Agrawal, Singh。arXiv 2601.11688) 【実証(abstract)】
- 手法: リポジトリ構造 → ファイル関連 → シンボルの階層的 LLM エージェント。組込みのデータシート→C/C++。
- 結果: ファイル対応の正解率 最大 73.3%。IR ベースラインより LLM トークン 84% 減、実行時間 約 80% 減。n は未確認。

**TraceLLM** (Alturayeif, Ahmad, Hassine。arXiv 2602.01253、Requirements Engineering 31(6) 2026) 【主張】
- 手法: プロンプト工学。ラベルを考慮した多様性ベースの例示選択が有効。
- データ: 4 データセット（航空宇宙・医療。要件・設計・テスト・規制）。LLM 8 種。名称・n・数値は未確認。
- 主張: F2 で SOTA。ゼロショットでも先行 LLM 手法を 3/4 で上回る。ランダム 2 例の few-shot は一貫して改善しない（検索結果の要約による。本文未確認）。

**Triple-Robustness** (Akarsu ほか。arXiv 2608.00705) 【実証(abstract)】
- 手法: GraphRAG とベクトル RAG を 5 パイプラインで比較。多段（マルチホップ）要件追跡。DO-178C コーパス。
- 結果: GraphRAG の文脈適合率 0.12〜0.23、引用の選択性 0.48〜0.65。ホップ距離が増えると忠実度が低下。単一 LLM ジャッジの忠実度は不安定（GPT-5.4 の自己 κ=0.137、同日再試験の下限 0.76）。ホップ分類の学習済みルータ macro-F1 0.86。
- 示唆: 評価を LLM ジャッジ 1 つに頼ると再現しない。

**その他（abstract のみ・数値なし）**
- Trust-Aware Multi-Agent Traceability（arXiv 2606.17203）: 埋め込み検索 → LLM の 2 段 + 信頼度校正付き知識グラフ。自動車事例。校正が必須とのアブレーションを主張。
- 正規化ユースケース（arXiv 2608.15726）: 要件を LLM でユースケース仕様に整形すると曖昧な要件で改善。品質の高い要件では逆に悪化しうる。数値は未確認。
- REST-at（Chalmers）: 要件⇔手動システムテストのリンク生成。5 LLM を比較し、オープン重みモデルが同等以上の適合率・再現率になりうる、プロンプト感度が高いと主張（検索要約のみ。論文は未取得）。
- Hassine, EASE 2024: セキュリティ要件→ゴールモデル、GPT-3.5-turbo ゼロショット、要件 42 件、P=100%／R=78.5%／F1=87.9%（検索要約のみ。小規模で一般化は弱い）。

### 先行研究

| 論文 | 年・媒体 | 手法 | 確認度 |
|---|---|---|---|
| Cleland-Huang ほか "Software Traceability: Trends and Future Directions" | FOSE 2014, pp.55-69, DOI 10.1145/2593882.2593891 | 展望 | 書誌のみ |
| Guo, Cheng, Cleland-Huang | ICSE 2017, DOI 10.1109/icse.2017.9, arXiv 1804.02438 | 単語埋め込み+RNN | abstract |
| Lin, Liu, Zeng, Jiang, Cleland-Huang T-BERT | arXiv 2102.04411 (2021-02) | 事前学習 BERT | abstract |
| Hey, Chen, Weigelt, Tichy FTLR | ICSME 2021, DOI 10.1109/ICSME52107.2021.00008 | 細粒度類似度+WMD | abstract |
| 古典 IR（Antoniol 2002・Marcus & Maletic 2003） | TVR が引用 | VSM・LSI | 引用のみ |

- Cleland-Huang FOSE 2014: 著者は Cleland-Huang, Gotel, Huffman Hayes, Mäder, Zisman。トレーサビリティの動向と今後の研究領域を整理。「grand challenges」という語は今回の検索で確認できず【未確認】。別資料 "The Quest for Ubiquity: A Roadmap for Software and Systems Traceability Research"（uky.edu の一覧に存在）は未精読。
- Guo ほか 2017: 双方向 GRU が最良。VSM と LSI を有意に上回る。データセットと数値は未確認。
- T-BERT: 3 段階の転移学習。Single-BERT が最も正確、Siamese-BERT は同程度で高速。3 OSS の issue→commit で MAP が VSM 比 平均 +60.31%。RNN は教師不足で不良。ICSE 2021 の発表と記憶するが、取得した arXiv ページには会議名が無く【未確認】。
- FTLR: 要件の文とコードのメソッド単位の類似度。unsupervised の SOTA を上回る。後続の KIT 学位論文が NoRBERT フィルタで MAP・F1 向上を報告。数値は未確認。
- TVR の関連研究は "Guo et al., 2024" も引用するが、2017 年の Guo と同一かは不明【未確認】。

### 製品に取り込むべき手法

1. 「リンク検出」より先に「既存リンクの妥当性検査」を作る（TVR）。WebSpec2Doc の要件定義書⇔基本設計書の対検査と整合する。無効リンクは検出が難しく、TF-IDF／SBERT／LiSSA でも F1 が約 10〜24% だった点が、LLM+RAG 化の根拠になる。
2. 2 段構成: 埋め込み（または TF-IDF）で候補を絞り、LLM が判定する（LiSSA・TVR・Trust-Aware 共通）。全組を LLM に流さないのでトークンも抑えられる。
3. 判定は理由と確信度を付けて人が確認する。自動確定しない。LLM の説明が完全に正しい割合は 42.9〜71.1%（Alor）。確信度の校正が必須とのアブレーションも出ている（Trust-Aware、主張）。
4. プロンプトとモデルをデータで選ぶ。ゼロショット／CoT／few-shot の効果は一貫せず、プロンプト感度が高い（Rodriguez、TraceLLM、REST-at）。few-shot を入れるなら、ランダムでなく多様性ベースで選ぶ（TraceLLM、主張）。ローカルの小型モデルでも同等になりうる（REST-at、主張）。
5. 評価は固定の正解セットで再現可能にする。LLM ジャッジ 1 つに依存しない（Triple-Robustness: 自己 κ=0.137）。指標は適合率・再現率・F1 に加え、見落としを重く見る F2 も出す。曖昧な要件は LLM で整形してから照合する手もあるが、高品質な要件では逆効果なので適用条件を付ける（Shi、数値未確認）。

### 引用してはいけない数値

- TVR の macro-F1 96.72%／Accuracy 98.87%: 単一の自動車案件・単一ドメイン・leave-one-out の値。他のドメインや日本語文書の性能として引用しない。
- 「LiSSA の F1 が 50% 台」: TVR 著者が自社データの「有効／無効」分類に適用した値で、LiSSA 論文本来の課題（要件→コード）の値ではない。LiSSA の性能として引用しない。
- 「F1 +28.59%／F2 +28.9%」（2509.20149）: 相対か絶対か、どのデータセットかが abstract から不明。
- 「T-BERT が MAP +60.31%」: VSM 比の平均で、3 OSS の issue→commit のみ。要件→設計・テストに外挿しない。
- 「F1 79.4%／80.4%」（Alor）: 2 つの OSS の文書→コード。モデル名との対応が不明で n も未確認。
- 「TraceLLM は SOTA」「LiSSA は SOTA を有意に上回る」: abstract の主張のみ。本文の数値は未取得。
- Hassine 87.9%（要件 42 件）: 件数が小さく、検索要約の再掲。
- SpecMap の 73.3%・84%・80%: 組込みデータシート→C/C++ の値で、設計書・テストには当てはまらない。
- ArTEMiS／ExArch／TransArC の F1（0.81／0.86／0.87）: アーキテクチャ文書→モデルの課題の値。要件⇔テストの値として使わない。
- 本調査では 2023〜2026 の要件⇔テスト専用の査読済み定量結果を本文で確認できていない（REST-at は要約のみ）。この領域の「精度」は断定しない。
## 5. 要求品質の自動検出の研究

調査方法: arXiv API 3 回（キーワード検索）、WebSearch 4 回、WebFetch で個別ページ 4 回、ローカルで PDF 1 件をテキスト化。Semantic Scholar API は HTTP 429 で取得できず。計 14 回。
区分: 【実証】=本文/概要で数値を確認 ／【主張】=概要の記述のみ ／【未確認】=存在は確認、数値・詳細は未取得。
注意: 2026 年 9〜10 月の arXiv ID（26xx.xxxxx）は検索結果の表示どおりに転記。arXiv 検索の関連度順は不安定で、網羅的な系統的レビューではない（取りこぼしあり）。LLM による要約を経由した取得が多く、引用前に原典で再確認すること。

### 5.1 最新論文（2023〜2026）

| 著者・年・発表先 | 手法 | データ・n | 主要結果（条件） | 示唆 |
|---|---|---|---|---|
| Shefa, Salado, Wach, Topcu 2026 / arXiv 2609.03230 https://arxiv.org/abs/2609.03230 | 市販 LLM 10 モデル（OpenAI・Anthropic 各 5 世代）を INCOSE 品質基準由来の専門家正解で採点 | 要求 2 セット、100 run、温度 5 水準。件数は未取得 | 【実証・概要】最良の Anthropic モデルで専門家指摘の中央値 47% を検出、誤検知率 11%。必要性・正しさの欠陥はほぼ見逃す。世代間で単調改善せず | LLM 単独の自律判定は不可。人間確認前提の支援に限る |
| Bashir, Ferrari ほか 2025 / ICSME 2025 pp.620-631 DOI 10.1109/ICSME64153.2025.00063 | LLM の in-context learning で曖昧性の分類と説明 | 産業データ 3 件（件数は未取得）、専門家 8 名 | 【実証・概要】10-shot は 0-shot より平均 20.2% 性能向上。説明の平均評価 3.84/5 | 自社の過去指摘を few-shot に入れる設計が有効 |
| 鈴木ほか（デンソー）2025 / 言語処理学会第31回年次大会 Q9-5 https://anlp.jp/proceedings/annual_meeting/2025/pdf_dir/Q9-5.pdf | GPT-4o で SRS 記述ガイドの 6 検査ルール（簡潔な文・係り受け・誤字脱字・完全な場合分け・誤った記載場所・単一要求）を検査。前処理に GiNZA 形態素解析・正規表現・書式推定 | 車載駆動系 SRS 1 件（73 頁中 52 頁に要求）。人手インスペクション結果を正解。別製品 1 件（111 頁中 85 頁）は適合率のみ | 【実証・本文】生文を LLM に直接入れると適合率・再現率とも低い（専門用語を誤字と判定）。前処理（形態素解析・書式推定）付与で大きく向上。表 1 の数値は PDF から抽出できず【未確認】 | 日本語要求に直接関係。LLM とルール処理の併用が結論。n=1 文書 |
| Broccia ほか 2026 / arXiv 2608.21298 | 要求インスペクションの交差実験（LLM 支援 vs なし） | 34 名 | 【実証・概要】LLM 支援は smell 検出精度を下げた。分類・所要時間に有意差なし | LLM 提示が人の検出を悪化させ得る。提示順・根拠表示の設計が要る |
| Villamizar, Fischbach ほか 2026 / arXiv 2609.29208 | 要求 smell 密度とコード生成の正しさの関係 | 4 アプリ | 【主張・概要】smell 密度が高いほどテスト基準の正しさが低い傾向。数値は概要になし | smell 検出は LLM 下流（コード生成）の品質ゲートにもなる |
| Vogelsang ほか 2025 / ICSE 2025 NIER, arXiv 2501.04810 | プロンプト中の smell がトレースリンク予測に与える影響 | LLM 2 種 | 【実証・概要】リンク有無の予測に小だが有意な影響、行レベルでは有意差なし | 影響はタスク依存 |
| Cheng ほか 2026 / arXiv 2603.11890 (QUARE) | マルチエージェントの弁証的交渉による品質認識の要求分析 | 5 ベンチマークシステム | 【主張・概要】準拠網羅 98.2%、意味保存 94.9%、検証可能性 4.96/5.0（採点者・基準は未確認） | 自己評価系の高スコアは鵜呑みにしない |
| Zakeri-Nasrabadi, Parsa 2024 / arXiv 2403.17479 | 9 種の smell で要求のテスト容易性を測定 | 10 ドメイン、約 1000 要求（985） | 【実証・概要】Smella 比で適合率 +0.03、再現率 +0.33。テスト容易性モデル MAE 0.12 / MSE 0.03 | smell をテスト容易性スコアに写す発想は製品に直結 |
| Gentili ほか 2024 / arXiv 2404.11106 | 実務者インタビュー | 10 名（MBDA Italy）、12 smell | 【実証・概要】重大度は曖昧性・検証可能性が上位、頻度は曖昧性・複雑性が上位 | 優先順位付けの根拠 |
| Femmer ほか 2025 / arXiv 2508.08868 (QuRE) | 産業要求データセット公開 | 2,111 要求（実レビュー由来） | 【実証・概要】データセット提供 | 評価用データの候補 |
| Yang ほか 2026 / arXiv 2604.21505 (Orchid) | 曖昧要求下の LLM コード生成ベンチ | 1,304 タスク、曖昧性 4 種 | 【実証・概要】曖昧性は生成品質を一貫して下げる | 曖昧性検出の価値を下流側から支持 |
| Frattini ほか 2023〜2024 / arXiv 2309.10355, 2402.00594, 2401.01154 | 要求品質の理論整理・産業事例・統制実験 | 事例で 17 要因・11 交互作用、実験 25 名 | 【実証・概要】曖昧な代名詞は強い影響、受動態の影響は小 | 全 smell を同じ重みで扱わない |
| Mahbub ほか 2024（2609.03230 の引用経由） | GPT-4 による曖昧性・矛盾・不整合の検出 | 未確認 | 【未確認・孫引き】適合率が約 41〜61% | 原典未確認のため引用不可 |
| Guo ほか 2021 / arXiv 2103.02255 | 意味解析による要求間矛盾検出 (FSARC) | 4 データセット | 【実証・概要】再現率ほぼ 100%、平均適合率 83.88% | 矛盾検出の LLM 以前のベースライン |

日本語の他の研究（概要のみ確認、検索結果の要約経由）:
- 信学技報 KBSE2022 の RQBV（語彙質問に基づく要求確認と曖昧性指標）【主張】
- 信学技報 KBSE2017-52（日本語要求仕様を状態遷移モデルへ変換し曖昧さ・矛盾を検出。電気ポット例のみ）【主張】
- 柏原ほか: Domain Word Modeling（SS2020）、形態素ベースドレビュー（SS2021）。デンソー論文の参考文献として存在を確認、本文は未取得

### 5.2 主要先行研究（後方スノーボール 1 段）

| 著者・年・発表先 | 手法 | データ・n | 主要結果（条件） | 示唆 |
|---|---|---|---|---|
| Femmer, Méndez Fernández, Wagner, Eder 2016/2017 "Rapid quality assurance with Requirements Smells" / arXiv 1611.08847（JSS 掲載。巻号・DOI は未確認） | ISO 29148 の悪い表現を smell 化し Smella で自動検出 | 産業 3 文脈＋大学 1 文脈 | 【実証・概要】平均適合率 59%・平均再現率 82%、ばらつき大 | smell 検出の原点。適合率の低さが誤検知問題の出発点 |
| Zhao, Alhoshan ほか 2020/2021 "NLP for RE: A Systematic Mapping Study" / arXiv 2004.01099（ACM Computing Surveys 掲載は記憶ベース・未確認） | 系統的マッピング | 404 件の一次研究 | 【実証・概要】130 ツール・140 技法を整理 | 分類の外部基準として使える |
| Ezzini, Abualhaija, Arora, Sabetzadeh 2022 "Automated Handling of Anaphoric Ambiguity in Requirements: A Multi-solution Study" / ICSE 2022 | 6 解法（教師あり ML・SpanBERT・共参照解析器）の比較 | 約 1,350 産業要求 | 【実証・検索要約】検出は教師あり ML が最良で適合率約 60%・再現率 100%、解決は SpanBERT 約 98% | 照応曖昧性は検出より解決が容易 |
| Ezzini ほか 2022 TAPHSIR / ESEC/FSE 2022 | 上記最良解法のツール化 | 同上 | 【主張】ツール化の存在のみ確認 | 実装参考 |
| Fischbach, Frattini ほか 2021 "Automatic Detection of Causality in Requirement Artifacts: the CiRA Approach" / arXiv 2101.10766（REFSQ 2021） | 因果文の検出 | 14,983 文・53 文書・18 ドメイン | 【実証・検索要約】macro-F1 82%、関連手法比 macro-Recall +11.06%・macro-Precision +11.43% | 条件文・因果文からテスト観点を作る基盤 |
| Fischbach ほか 2021 / arXiv 2103.06768 | CiRA の受入基準向けツール | 受入基準 61 件 | 【実証・検索要約】macro-F1 83% | 同上、n は小さい |
| Fantechi, Gnesi, Semini 2017 "Ambiguity defects as variation points in requirements" / VaMoS 2017 | QuARS 系の曖昧性検出結果を変動点として分類 | 未取得 | 【主張・検索要約】曖昧性が可変性の手がかりになり得る | 「曖昧＝欠陥」とは限らない。誤検知分類の発想 |
| Gervasi 2005 "Reasoning about inconsistencies in natural language requirements"（共著 Zowghi、TOSEM 掲載は検索で確認できず【未確認】） | 自然言語解析＋既定推論で多利害関係者要求の不整合を検出 | 未取得 | 【主張・検索要約】定理証明・モデル検査を併用 | 矛盾検出の古典。形式化が前提でコストが高い |
| Berry, Kamsties, Krieger 2003 "From Contract Drafting to Software Specification: Linguistic Sources of Ambiguity" ハンドブック https://cs.uwaterloo.ca/~dberry/handbook/ambiguityHandbook.pdf | 曖昧性の言語学的分類（語彙・構文・意味・語用） | 手引き | 【実証・実在確認】分類体系。年は引用上 2003 | 曖昧性の分類軸の外部基準 |
| Frattini ほか 2023〜2024 NLP4RE Tools / arXiv 2403.06685 | NLP4RE ツールの分類・管理 | 126 ツール（2019年4月〜2023年6月） | 【実証・概要】ツール棚卸し | 既存ツールとの差別化確認に使える |

未取得（実在は記憶にあるが今回確認せず、引用不可）: Fantechi 単独の別論文、Gervasi の矛盾検出の他論文、Zhao 論文の ACM CSUR 掲載情報、Femmer 論文の DOI。

### ISO/IEC/IEEE 29148 と INCOSE Guide の関係
【記憶ベースで今回の検索では未検証。引用前に原典確認】ISO/IEC/IEEE 29148 は要求工学プロセスと、個々の要求および要求セットが満たすべき特性（必要・実装非依存・曖昧でない・完全・単一・実現可能・検証可能・正しい・適合 など）を定める国際規格。INCOSE Guide to Writing Requirements は、その特性を実務者が文章に落とすための規則集（規則の番号付き一覧）で、29148 の特性と整合するよう作られ、Femmer の smell 検出や Shefa らの評価正解が INCOSE 基準を使うように、機械検査の根拠として参照される。つまり 29148 が「何を満たすか」、INCOSE が「どう書くか」。デンソー論文も 29148 系の品質特性を SRS 記述ガイドの土台にしている（本文で確認）。

### 製品に取り込むべき手法
1. ルール（形態素解析・正規表現）で候補を絞り、LLM は候補の判定と説明に限る。根拠: デンソー 2025（生文の直投入は低精度、前処理で向上）、Femmer の適合率 59% の教訓。
2. 欠陥種別ごとに検査ルールと適合基準＋違反例の few-shot を持たせる。顧客の過去指摘を例にする。根拠: Bashir 2025（10-shot で平均 +20.2%）。
3. LLM が苦手な「必要性・正しさ」は自動判定せず、人間への確認項目として出す。根拠: Shefa 2026（必要性・正しさをほぼ見逃す）。
4. LLM の指摘を先に見せると人の検出が悪化し得るので、人の判断の後または根拠付きで提示し、誤検知を却下できる UI にする。根拠: Broccia 2026（34 名交差実験）。
5. smell を重大度で重み付けし、検証可能性（テスト容易性スコア）に写す。曖昧な代名詞など影響の大きいものを優先。根拠: Gentili 2024、Frattini 2024、Zakeri-Nasrabadi 2024。

### 引用してはいけない数値
- 「GPT-4 の適合率 41〜61%」: 孫引き（Mahbub 2024 を 2609.03230 経由）。原典未確認。
- QUARE の「98.2% / 94.9% / 4.96/5.0」: 概要のみ、採点者・基準が未確認の自己評価系。
- Bashir 2025 の「+20.2%」「3.84/5」: データ件数・モデル名が未取得。モデルや指標（F1 か精度か）が不明なため条件なしで一般化しない。
- Shefa 2026 の「47% / 11%」: 最良 Anthropic モデルの中央値で、モデル名・要求セット規模が未取得。「LLM 全般の性能」として引用しない。
- デンソー 2025: 表 1 の数値は抽出できていない。n=1 文書（1 製品）で、一般化しない。
- Ezzini 2022 の「適合率約 60%・再現率 100%・約 98%」: 検索要約経由で、タスクが照応曖昧性に限られる。
- Femmer の「59% / 82%」: 2016 年の初期プロトタイプ、4 文脈の平均。現行ツールや LLM の性能の代表値としない。
- arXiv 検索結果にある 2026 年の論文群は、査読済みか未確認。会議採択は確認していない。
