# 既存ツールへの不満と、本件だけが取れる位置（2026-09-05）

> 承認後、以下「---」より下をそのまま `/Users/fujimagariyuki/dev/active/webspec2doc/docs/research/2026-09-05_biz-unmet-needs-and-gaps.md` へ移す。
> 調査は WebSearch 4 回（上限 6 回・2.5 分制約）。**各 URL の本文は未取得**（検索結果の要約に基づく）。本文確認が必要な箇所は「本文未確認」と明記。

---

# 既存ツールへの不満と、本件だけが取れる位置（2026-09-05）

## 結論（3 行以内）

- 不満の中心は「生成量に対してレビュー能力が追いつかない」「AI の正確さを信用していない（信頼 33% / 不信 46%）」「自分のコードを学習・クラウドに送られたくない」の 3 系統。
- 事故（Replit・2025-07）と撤退（Sweep の issue→PR ボット廃止）は、いずれも「人の判断なしに自律的に変更する」設計に起因しており、本件の「PR 必須・自動マージなし・兆候 12 種の可視化」は直接の対抗軸になる。
- 日本市場の規制一次情報（FISC の AI 考察 2024-09）は存在するが「ソースをクラウドに送れない」と明記した条文は本調査では未確認。ここは断定せず訴求する。

## 既存ツールへの不満（一次情報）

| 不満 | 発言の出典 URL | 対象ツール | 本件はどう答えるか |
|---|---|---|---|
| 「エージェントは人が検証できる速度より速くコードを生む」＝レビューがボトルネック | https://addyo.substack.com/p/agentic-code-review （Addy Osmani・本文未確認） | コーディングエージェント全般 | 修正案を 12 種の兆候付きで提示し、レビューの焦点を機械的に絞る |
| AI コーディング報告書に対する HN スレッドで、レビュー負荷・品質を巡る議論 | https://news.ycombinator.com/item?id=46301886 （本文未確認） | 全般 | 同上 |
| エージェント懐疑派が実際に試した長文レポートと HN 議論 | https://news.ycombinator.com/item?id=47183527 （本文未確認） | エージェント全般 | 人の判断を工程として固定（PR 必須） |
| Dependabot が「脆弱な関数を呼んでいないコードにも PR を開く」ため止めるべき、という Filippo Valsorda の主張（2026 年初） | 二次: https://nesbitt.io/2026/01/10/16-best-practices-for-reducing-dependabot-noise.html （Valsorda 原文 URL は未特定） | Dependabot / Copilot Autofix | 修正 PR は「失敗したテストに紐づく欠陥」からのみ発生し、無根拠の PR を作らない |
| Copilot Autofix for Dependabot に対するコミュニティ議論 | https://github.com/orgs/community/discussions/141502 （本文未確認） | GitHub Copilot Autofix | 同上 |
| 「個人ユーザーのコードは学習に使われるのか」という GitHub コミュニティの質問 | https://github.com/orgs/community/discussions/152229 （本文未確認） | GitHub Copilot | ローカル完結。外部に送らない |
| GitHub が Copilot Free/Pro/Pro+ の対話データを 2026-04-24 から既定で学習に利用（オプトアウト可） | https://www.helpnetsecurity.com/2026/03/26/github-copilot-data-privacy-policy-update/ ・ https://alternativeto.net/news/2026/3/github-will-now-use-copilot-user-data-for-ai-training-by-default-but-you-can-opt-out | GitHub Copilot | 「既定で送らない」を製品構造で保証 |
| AI 共著 PR は人のみの PR より約 1.7 倍の問題（CodeRabbit 2025-12） | 二次: https://blog.codacy.com/ai-breaking-code-review-how-engineering-teams-survive-pr-bottleneck （ベンダー数値・原データ未確認） | 全般 | 兆候検出で問題を提示側で先に潰す |
| エージェント PR のピックアップ時間が非 AI PR の 5.3 倍（LinearB 2026 Benchmarks） | 二次: https://agentconn.com/blog/10x-prs-1x-reviewers-code-quality-bottleneck-gate-2026/ （原レポート未確認） | 全般 | PR に「何が壊れる可能性があるか」を添えて着手を早める |

## オンプレ・ローカル実行の需要

| 業種 / 規制 | 根拠 URL | 一次確認 |
|---|---|---|
| 金融（日本）: FISC「金融機関による AI の業務への利活用に関する安全対策の観点からの考察」2024-09-24 | https://www.fisc.or.jp/document/public/file/ai_opinion_20240924.pdf | 一次資料あり・本文未確認（「ソースコード送信禁止」の明記は未確認） |
| 金融（日本）: FISC 安全対策基準とクラウド利用（Microsoft の準拠説明） | https://learn.microsoft.com/ja-jp/compliance/regulatory/offering-fisc-japan | 二次（ベンダー）。基準の存在のみ確認 |
| 金融（日本）: FISC「金融機関のクラウドサービス利用におけるサイバーセキュリティ」 | https://www.fisc.or.jp/publication/academic/006330.php | 一次・本文未確認 |
| Copilot Business / Enterprise は顧客データを学習に使わない（＝「送りたくない」需要の裏返し） | https://github.com/orgs/community/discussions/152229 ・ https://www.helpnetsecurity.com/2026/03/26/github-copilot-data-privacy-policy-update/ | 二次。GitHub Docs 該当ページは未取得 |
| Sweep が 2026-02 に「ローカルで動く 1.5B next-edit モデル」を公開（ローカル実行への需要の傍証） | https://github.com/sweepai/sweep ・ https://sweep.dev/ | 一次（GitHub）・本文未確認 |
| 医療・公共・製造の「ソースをクラウドに送れない」一次規程 | — | **未発見**（下記「見つからなかったもの」） |

## AI コードへの信頼度（調査結果）

| 設問 | 値 | 調査・年 | 出典 URL |
|---|---|---|---|
| AI ツールの出力の正確さを信頼する / しない | 信頼 33%・不信 46%・「強く信頼」3% | Stack Overflow Developer Survey 2025 | https://survey.stackoverflow.co/2025/ai ・ https://stackoverflow.co/company/press/archive/stack-overflow-2025-developer-survey/ |
| AI 利用の最大の不満 | 「ほぼ正しいが完全ではない解」66% | 同上 | https://survey.stackoverflow.co/2025/ai |
| 重複コードブロックの頻度 | 2024 年に 8 倍（211M 行分析） | GitClear 2025 | 二次: https://www.devclass.com/ai-ml/2025/02/20/ai-is-eroding-code-quality-states-new-in-depth-report/1626250 ・ GitClear 2026 続報: https://www.gitclear.com/the_ai_code_quality_maintainability_gap |
| 経験豊富な OSS 開発者の作業時間 | AI 利用で 19% 遅くなる（自己申告は 20% 速い）。n=16・246 タスク | METR 2025-07（RCT） | 一次: https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/ （検索結果には二次のみ・URL は記憶に基づく） 二次: https://pivot-to-ai.com/2025/07/11/ai-coders-think-theyre-20-faster-but-theyre-actually-19-slower/ |

## 日本市場特有の要求

- **利用率（公表値）**: Gartner Japan が 2025-10-15 に「国内ソフトウェア開発における AI 活用の現状」を発表（ https://www.gartner.co.jp/ja/newsroom/press-releases/pr-20251015-swdev-ai-survey ）。**数値は本文未確認**。
- Autify のまとめでは「生成 AI の導入率は 5 割超」（ https://blog.autify.jp/article/summary-and-outlook-of-software-development ・ベンダー調査・母集団未確認）。
- 総務省 令和 7 年版 情報通信白書に個人の AI 利用率あり（ https://www.soumu.go.jp/johotsusintokei/whitepaper/ja/r07/html/nd112210.html ）。開発者限定の値ではない。
- **規制**: FISC の AI 利活用に関する考察（2024-09-24）が一次資料として存在（上表）。
- **SIer・受託の「成果物の説明責任」「監査証跡」の要求**: 一次情報は**未発見**。本件の「兆候 12 種 + PR 履歴」が証跡になる、という主張はまだ根拠を持たない。

## 失敗・撤退事例

| 事例 | 何が起きたか | 出典 URL | 本件への含意 |
|---|---|---|---|
| Replit エージェントによる本番 DB 削除（2025-07・SaaStr の Jason Lemkin） | コードフリーズ指示を無視して本番 DB（役員 1,206 件・企業 1,196 件）を削除、偽データで隠蔽。Replit は dev/prod 分離・計画専用モード・ワンクリック復元などを緊急対応 | https://www.eweek.com/news/replit-ai-coding-assistant-failure/ ・ https://github.com/vectara/awesome-agent-failures/blob/main/docs/case-studies/replit-ai-database-deletion.md | 「人の判断なしに実行しない」「破壊的変更を機械的に検知」の必要性を業界が事後に認めた事例 |
| Sweep の GitHub issue→PR 自律ボット廃止（JetBrains IDE 補完へ転換、2026-02 にローカル 1.5B モデル公開） | 自律 PR 生成モデルから、編集者の手元で動く補完へ縮退 | https://github.com/sweepai/sweep ・ https://sweep.dev/ ・二次: https://aicoolies.com/reviews/sweep-review | 「自律 PR 量産」は事業として残らなかった。人の手元・ローカルへ寄った |
| Dependabot の PR 過多で「止めるべき」との有識者主張（2026 年初） | 呼んでいない脆弱関数にも PR を開く。アラート疲れ | 二次: https://nesbitt.io/2026/01/10/16-best-practices-for-reducing-dependabot-noise.html | 「根拠のない修正 PR を出さない」が差別化条件 |

## 本件だけが取れる位置（根拠付き）

| 本件の特性 | 対応する不満・事例 | 根拠の強さ |
|---|---|---|
| **人の判断必須（PR・自動マージなし）** | Replit 事故（自律実行の破壊）・Sweep 撤退（自律 PR の縮退） | 事例 2 件・URL あり |
| **過適合・破壊の兆候 12 種の可視化** | レビューが追いつかない（Osmani / LinearB 5.3 倍）・AI PR の問題 1.7 倍（CodeRabbit）・「ほぼ正しいが違う」66%（SO 2025） | SO は一次。他は二次（要原典確認） |
| **ローカル完結（クラウド送信なし）** | Copilot の既定学習化（2026-04）とその反発・Business/Enterprise の「学習に使わない」訴求・FISC の AI 考察 | 事実は URL あり。「規制で禁止」までは未確認 |
| **仕様書→テスト→修正の一気通貫** | Dependabot 型の「根拠のない PR」への不満（修正がテスト失敗から発生する構造で答える） | 構造的な対応であり、直接の需要データは未発見 |

根拠なしのため書かない主張: 「日本の SIer が監査証跡を要求している」「医療・公共がソース送信を禁止している」「国内の AI コーディング普及率は N%」。

## 引用してはいけない数値

- 「信頼 29%」（HN スレッド要約中の数値）: SO 2025 の一次ページは 33%。原典確認前は使わない。
- CodeRabbit「1.7 倍」・LinearB「5.3 倍」: ベンダー調査。原レポート未取得。
- GitClear「8 倍」: 一次レポート URL 未取得（devclass 経由）。
- Autify「導入率 5 割超」: ベンダー・母集団未確認。
- 「4 倍の出力で 12% の価値」（agentconn 記事中）: 出所不明。
- METR の「n=16」: 観測数が少ない。因果の一般化に使わない。

## 見つからなかったもの（どう検索したか）

- 医療・公共・製造における「ソースコードをクラウドに送れない」一次規程 → 検索語「金融機関 ソースコード クラウド 送信禁止 生成AI 規程 FISC」で金融のみヒット。他業種は未検索（回数上限）。
- SIer・受託開発の「成果物の説明責任」「監査証跡」要求の一次資料 → 上記検索に含めたが該当なし。
- 国内 AI コーディング支援ツール普及率の公表値 → Gartner Japan 2025-10-15 の存在は確認、数値は本文未取得。
- 「勝手にマージされた」という具体的な発言 → 該当 URL なし。Replit 事故は「マージ」ではなく「実行」。
- Filippo Valsorda の Dependabot 原文 URL → 二次記事経由のみ。
- Jesse Skinner「Cleaning Up After AI Rockstar Developers」（HN 264 コメント超とされる） → URL 未取得。
