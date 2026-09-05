# 市場規模・支払い意欲・$1M への算数（2026-09-05）

## 結論（3 行以内）

- **$1M ARR は「席 $20/月 × 約 4,200 席」または「年 $10K × 100 社」。**席単価は Copilot Business $19 / Cursor Pro $20 に揃うため、席売りなら 4,000 席超が必要。企業契約（年 $10K〜）の方が到達距離が短い。
- **開発者の 84% が AI ツールを利用/利用予定だが、出力の正確さを信頼するのは 33%・不信 46%**（Stack Overflow 2025）。「AI が直して人が判断する」設計は、この信頼ギャップに直接当たる。
- **AI コードツール市場規模の公表値（2025 年 $5.3B〜$7.9B）は全て二次調査会社で定義が未確認のため引用不可。**Gartner / IDC / Grand View の値は今回取得できず。

## 市場規模の公表値

| 市場の定義 | 規模 | 年 | 調査会社 | 出典 URL | 一次確認 | 引用可否 |
|---|---|---|---|---|---|---|
| AI Code Tools（定義未確認） | USD 7.7B（2029 年 18.16B） | 2025 | Research and Markets | https://www.researchandmarkets.com/reports/5951952/artificial-intelligence-ai-code-tools-market | 未確認（検索スニペットのみ） | **不可** |
| AI Code Tools（定義未確認） | USD 7.59B（2035 年 74.25B） | 2025 | SNS Insider | https://www.snsinsider.com/reports/ai-code-tools-market-8422 | 未確認 | **不可** |
| AI Code Tools（定義未確認） | USD 7.37B（2031 年 29.96B） | 2025 | Mordor Intelligence | https://www.mordorintelligence.com/industry-reports/artificial-intelligence-code-tools-market | 未確認 | **不可** |
| AI Code Tools（定義未確認） | USD 5.3B（2033 年 30.61B） | 2025 | SkyQuest | https://www.skyquestt.com/report/ai-code-tools-market | 未確認 | **不可** |
| AI Code Tools（定義未確認） | USD 7.93B（2035 年 91.09B） | 2025 | Precedence Research | https://www.precedenceresearch.com/ai-code-tools-market | 未確認 | **不可** |
| AI Code Tools | 未取得（レポート存在のみ確認） | — | MarketsandMarkets / Technavio | https://www.marketsandmarkets.com/Market-Reports/ai-code-tools-market-239940941.html / https://www.technavio.com/report/ai-code-tools-market-industry-analysis | 未確認 | **不可** |
| Gartner / IDC / Grand View / Statista（AI コーディング支援・テスト自動化） | **取得できず** | — | — | — | — | — |
| テスト自動化ツール市場 | **取得できず** | — | — | — | — | — |

補足: 5 社の 2025 年値が $5.3B〜$7.9B に収れんしている点は「桁の目安」としてのみ使える。計画書に数値として載せない。

## 開発者の利用率と信頼度

| 設問 | 値 | 調査 | 年 | 出典 URL |
|---|---|---|---|---|
| AI ツールを開発プロセスで利用中または利用予定 | **84%**（2024 年は 76%） | Stack Overflow Developer Survey | 2025 | https://survey.stackoverflow.co/2025/ai |
| AI ツールの出力の正確さを **信頼** する | **33%**（「highly trust」は 3%） | Stack Overflow Developer Survey | 2025 | https://survey.stackoverflow.co/2025/ai |
| AI ツールの出力の正確さを **不信** | **46%** | Stack Overflow Developer Survey | 2025 | https://survey.stackoverflow.co/2025/ai |
| AI を信頼する（別集計・プレスリリース表記） | 29%（2024 年比 -11pt） | Stack Overflow プレスリリース | 2025 | https://stackoverflow.co/company/press/archive/stack-overflow-2025-developer-survey/ |
| AI の回答は「ほぼ正しいが完全ではない」 | **66%** | Stack Overflow Developer Survey | 2025 | https://survey.stackoverflow.co/2025/ai |
| AI 生成コードのデバッグにかなりの時間を失う | **45%** | Stack Overflow Developer Survey | 2025 | https://survey.stackoverflow.co/2025/ai |
| AI エージェントを利用中 / 利用予定 / 予定なし | 31% / 17% / 38% | Stack Overflow Developer Survey | 2025 | https://survey.stackoverflow.co/2025/ai |
| AI エージェント利用者のうち生産性向上を実感 | 69% | Stack Overflow Developer Survey | 2025 | https://survey.stackoverflow.co/2025/ai |
| 有料 AI ツールの利用率・支払額 | **取得できず**（設問の有無も未確認） | Stack Overflow | 2024/2025 | — |
| JetBrains State of Developer Ecosystem の AI 関連設問 | **取得できず** | JetBrains | — | — |

注: 「信頼 33%」（survey ページ）と「信頼 29%」（プレスリリース）は設問または集計母数が異なる可能性がある。両方を併記し、計画書では **33% / 46%（正確さへの信頼/不信）** を主として使い、29% は補助扱いにする。上表は検索結果の要約から取得しており、survey ページ本文での一次確認は未実施。

## 価格ベンチマーク

| ツール | 席あたり月額 | 出典 URL |
|---|---|---|
| GitHub Copilot Free / Pro / Pro+ | $0 / $10 / $39（個人） | https://userjot.com/blog/github-copilot-pricing-guide-2025（二次） |
| GitHub Copilot Business | **$19/user/月**（公式ブログで「据え置き」と明記） | https://github.blog/news-insights/company-news/github-copilot-is-moving-to-usage-based-billing/（公式） |
| GitHub Copilot Enterprise | **$39/user/月** | https://techcrunch.com/2024/02/27/githubs-copilot-enterprise-hits-general-availability/embed/（GA 時報道） |
| Cursor Hobby / Pro / Pro+ / Ultra | $0 / **$20** / $60 / $200（個人） | https://www.cloudzero.com/blog/cursor-ai-pricing/（二次・公式 cursor.com/pricing 未確認） |
| Cursor Teams / Enterprise | $40/user/月（一部情報で $120 の上位席）/ 要問合せ | https://www.cloudzero.com/blog/cursor-ai-pricing/（二次） |
| JetBrains AI Pro（個人 / 組織） | $10/月 / **$20/user/月** | https://comparedge.com/tools/jetbrains-ai/pricing（二次・公式未確認） |
| JetBrains AI Ultimate（個人 / 組織） | $30/月（年払い約 $20）/ $60/user/月 | https://altaitools.com/jetbrains-ai-pricing/（二次・公式未確認） |
| エンタープライズ契約の相場（年額・席数レンジ） | **取得できず**（各社「要問合せ」で非公開） | — |

所見: 席単価の相場は **$10〜$20（個人）/ $19〜$40（チーム）/ $39〜（エンタープライズ）**。GitHub は 2026 年に利用量課金へ移行中（公式ブログ）で、席固定から従量への流れがある。Cursor / JetBrains は二次情報のみのため、計画書に載せる前に公式価格ページで 1 回確認する。

## $1M ARR の算数

| 単価 | 必要な席数 or 社数 | 前提 |
|---|---|---|
| $10/席/月（Copilot Pro・JetBrains AI Pro 個人と同額） | **8,334 席** | 年 $120/席。チャーン 0・割引なし |
| $19/席/月（Copilot Business と同額） | **4,386 席** | 年 $228/席 |
| $20/席/月（Cursor Pro と同額） | **4,167 席** | 年 $240/席 |
| $39/席/月（Copilot Enterprise と同額） | **2,137 席** | 年 $468/席 |
| $50/席/月 | **1,667 席** | 年 $600/席 |
| 年 $10K/社（企業契約） | **100 社** | 1 社あたり 20 席 × $500/年 相当。10 席 × $1,000/年 でも同額 |
| 年 $25K/社（企業契約） | **40 社** | 中堅 SIer の部門契約を想定（相場は未確認） |
| 年 $100K/社（エンタープライズ） | **10 社** | 大手 SIer 全社契約を想定（相場は未確認） |

- チャーンを織り込む場合: 年次チャーン c のとき、定常状態で ARR を維持するには年間で `必要席数 × c` の新規獲得が要る。**開発者ツール SaaS の一般的な有料転換率・チャーンは今回の検索で公開データを取得できず「未確認」。**（候補出典: OpenView SaaS Benchmarks、ChartMogul SaaS Benchmarks、Lenny's Newsletter の freemium 転換率調査。いずれも未取得）
- 「84% が利用/利用予定」（上表）を席売りの分母に使う場合、**利用予定を含む値**であり有料化率ではない点に注意。

## 日本市場

- **IPA ソフトウェア開発データ白書**: 公開ページと 2018-2019 情報通信業編 PDF の所在は確認済みだが、**工程別工数比率の具体値は取得できず**（ツール上限）。
  - 白書ページ: https://www.ipa.go.jp/archive/publish/wp-sd/wp-sd.html
  - 情報通信業編 2018-2019 PDF（238 件のプロジェクトデータ）: https://www.ipa.go.jp/archive/publish/wp-sd/ps6vr70000011lad-att/000069383.pdf
  - 白書は「開発 5 工程（基本設計〜総合テスト）の工程別工数比率・工期比率」を収録していることを FAQ ページで確認。**結合テスト＋総合テストの比率を読み取るには上記 PDF の該当表を 1 回参照する必要がある。**
  - 二次情報（個人ブログ）に比率の転記があるが引用しない: https://chaki-study.com/ratio-by-process/ 、https://mitarou.hatenablog.com/entry/2023/10/18/193615
- **JUAS 企業 IT 動向調査（IT 予算・受託開発比率）**: **取得できず**。
- **経産省 特定サービス産業動態統計（情報サービス業 売上高）**: **取得できず**。
- **国内テスト工程の市場規模**: **取得できず**（公表値の存在自体が未確認）。

## 引用してはいけない数値

| 数値 | 理由 |
|---|---|
| AI Code Tools 市場 2025 年 $5.3B〜$7.9B（Research and Markets / SNS Insider / Mordor / SkyQuest / Precedence） | 市場の定義（IDE 補完のみか、テスト自動化・レビューを含むか）が未確認。5 社で 2035 年予測が $30B〜$91B と 3 倍開き、方法論が不透明 |
| MarketsandMarkets / Technavio の AI Code Tools 市場値 | 数値自体を取得しておらず、存在のみ確認 |
| 「AI エージェント利用者の 69% が生産性向上」 | 自己申告・利用者バイアスあり。効果量（何 % 短縮か）が無い。訴求には使わず「認識」としてのみ扱う |
| Cursor Teams $120/席、JetBrains AI 組織価格 $20 / $60 | 二次情報のみ。公式価格ページ未確認 |
| 個人ブログ転記の IPA 工程別比率 | 一次資料（IPA PDF）未参照。転記の版・母数が不明 |
| 「Stack Overflow 2025 で信頼 29%」 | survey ページの 33% と食い違う。設問差の可能性があり、単独で引用しない |
| 開発者ツール SaaS の有料転換率・チャーンの「一般的な値」 | 今回取得しておらず、記憶値は使わない |

## 見つからなかったもの（どう検索したか）

| 項目 | 検索内容 | 結果 |
|---|---|---|
| Gartner / IDC / Grand View / Statista の AI コーディング支援・テスト自動化市場規模 | WebSearch: `AI code tools market size 2025 Grand View Research OR Gartner OR IDC "AI-augmented software engineering" OR "automation testing market" definition` | 二次調査会社（7 社）のみヒット。Gartner / IDC / Grand View は 0 件 |
| テスト自動化ツール市場規模 | 同上クエリに含めた | 0 件（AI Code Tools に吸われた） |
| Stack Overflow 2024 の信頼度設問の値・有料利用設問 | WebSearch: `Stack Overflow Developer Survey 2025 AI trust accuracy percent distrust "AI agents" results` | 2025 の値は取得。2024 は「利用/予定 76%」のみ。有料利用の設問は未取得 |
| JetBrains State of Developer Ecosystem の AI 設問 | 未検索（ツール上限 6 回・検索 4 回で打ち切り） | 未取得 |
| エンタープライズ契約の相場 | 価格クエリに含めた | 各社「要問合せ」。公開レンジ無し |
| 開発者ツール SaaS の有料転換率・チャーン | 未検索（上限） | 未取得 |
| IPA 工程別工数比率の具体値 | WebSearch: `IPA ソフトウェア開発データ白書 工程別工数比率 テスト工程 割合 ...` | 白書ページ・PDF の URL は特定。数値は PDF 未取得 |
| JUAS 企業 IT 動向調査 / 経産省 特定サービス産業動態統計 | 同上クエリに含めた | 0 件（クエリが IPA に吸われた。単独クエリで再検索が必要） |

### 次に 1 回ずつ叩けば埋まるもの（優先順）

1. IPA PDF（上記 URL）の「工程別工数比率」表 → テスト工程比率
2. https://survey.stackoverflow.co/2025/ai 本文 → 33% / 46% の一次確認と有料利用設問の有無
3. https://cursor.com/pricing 、https://www.jetbrains.com/ai-ides/buy/ → 価格の公式確認
4. JetBrains State of Developer Ecosystem 2025 の AI セクション
5. JUAS「企業 IT 動向調査報告 2025」→ IT 予算・外注比率
