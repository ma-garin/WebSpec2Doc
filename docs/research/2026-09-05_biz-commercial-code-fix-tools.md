# 汎用コード自動修正の商用ツール — 価格と位置づけ（2026-09-05）

> 注: プランモードのため指定先 `docs/research/2026-09-05_biz-commercial-code-fix-tools.md` へは書けず、本ファイルに退避。内容はそのまま移送可。
> 調査手段: WebSearch 4 回（公式ページ本文の WebFetch は未実施）。「一次確認」列は、数値の出所が公式ドメインのスニペットか第三者集計かを区別する。

## 結論（3 行以内）

- 席あたり月額は $19〜$60、中央値 $30。2026 年に入り Bugbot / Greptile / Copilot が**席課金から従量（$1〜1.5/run、AI Credits）へ移行**しており、価格軸は「席」から「実行回数」へ動いている。
- 14 ツール中、ローカル実行を標準で提供するものは確認できず（Sweep の JetBrains プラグインのみ例外候補・未確認）。オンプレはエンタープライズ枠のみ（CodeRabbit・Qodo・Greptile、いずれも本パスでは未確認）。
- 全ツールの修正起点は「静的解析アラート / エラー監視 / PR レビュー」であり、**「Web 画面の E2E 検証失敗」を起点に修正 PR を出すものは見当たらない**。ここが本件の位置づけ。

## 一覧

| ツール | 提供元 | 価格 | 対象 | 自動 PR | 人の承認位置 | 実行場所 | 出典 URL | 一次確認 |
|---|---|---|---|---|---|---|---|---|
| Copilot Autofix（Code Security） | GitHub | $30/アクティブコミッター/月（Code Security に同梱）。公開リポは無料 | チーム〜エンタープライズ | あり（2026-07 公開プレビューの Agentic autofix は「Assign to Copilot」→ PR。AI Credits 消費） | PR レビュー・マージ | クラウド必須（GitHub） | https://github.blog/changelog/2025-03-04-introducing-github-secret-protection-and-github-code-security/ / https://github.blog/changelog/2026-07-10-agentic-autofix-for-code-scanning-alerts-in-public-preview/ | 公式 changelog スニペット |
| Copilot coding agent | GitHub | Pro $10 / Pro+ $39 / Max $100（個人）、Business $19 / Enterprise $39（席）。2026-06-01 以降は AI Credits の従量 | 個人〜エンタープライズ | あり（Issue 割当 → PR） | PR レビュー・マージ | クラウド必須 | https://github.com/features/copilot/plans | 公式 URL 取得・数値は第三者スニペット照合。AI Credits 移行は第三者記事のみ（未確認） |
| Sentry Seer | Sentry | $40/アクティブコントリビューター/月（2026-01-21〜。PR 2 件以上/月で課金対象）。旧 Seer は $20/月 + $25 クレジット | チーム〜エンタープライズ | あり（Issue Fix → PR。※本パス未確認） | PR レビュー・マージ | クラウド必須（自己ホスト Sentry での提供は未確認） | https://sentry.zendesk.com/hc/en-us/articles/45551407771931 | 公式ヘルプセンター スニペット |
| Cursor Bugbot | Anysphere | 従量 ≈ $1.00〜1.50/run（2026-06-08 更新分から。旧 $40/席/月・年払 $32） | 個人・チーム | なし（PR レビューコメント。※本パス未確認） | PR 上の指摘を人が採否 | クラウド必須 | https://cursor.com/blog/may-2026-bugbot-changes | 公式ブログ スニペット |
| CodeRabbit | CodeRabbit | Essentials $30/開発者/月（年払 $24）、Team $60（年払 $48）。Lite/Pro 旧プランは 2026-06-08 廃止 | 個人〜エンタープライズ | 部分（レビューコメント＋ワンクリック修正提案。※本パス未確認） | PR 上で人が採否 | クラウド。セルフホストはエンタープライズ（未確認） | https://kb.coderabbit.ai/articles/2508018126-sunset-of-lite-and-pro-legacy-subscription-plans / https://www.coderabbit.ai/pricing | 公式 KB スニペット |
| Devin | Cognition | Core $20〜（従量 $2.25/ACU）、Team $500/月（250 ACU・$2.00/ACU）、Enterprise 非公開 | 個人〜エンタープライズ | あり（タスク → PR。※本パス未確認） | PR レビュー・マージ | クラウド必須（Enterprise の VPC は未確認） | https://pensero.ai/blog/devin-pricing （第三者） | **未確認**（公式ページ未取得） |
| Qodo | Qodo | Teams $30/ユーザー/月（年払。月払 $38）、Enterprise $45〜。ただし現行ページは「Pro Team + Enterprise」構成で無料枠廃止との記述もあり | 個人〜エンタープライズ | 部分（レビュー＋修正提案。※本パス未確認） | PR 上で人が採否 | クラウド。オンプレはエンタープライズ（未確認） | https://docs.qodo.ai/pricing-and-usage | **未確認**（数値は第三者。情報が割れている） |
| Snyk Agent Fix | Snyk | Agent Fix 単体は非公開。Snyk プランは無料 / $25/月〜（Team）/ Enterprise 見積 | 個人〜エンタープライズ | 部分（Snyk Code の脆弱性に修正案。PR 化は未確認） | 開発者が IDE/PR で採否 | クラウド必須 | https://snyk.io/plans/ / https://docs.snyk.io/scan-with-snyk/snyk-code/manage-code-vulnerabilities/fix-code-vulnerabilities-automatically | 公式ページタイトル（$25/月〜）のみ |
| Amazon Q Developer | AWS | 無料枠 / Pro $19/ユーザー/月 | 個人〜エンタープライズ | あり（/dev エージェント → PR。※本パス未確認） | PR レビュー・マージ | クラウド必須（AWS） | https://aws.amazon.com/q/pricing | 公式 URL 取得・数値は第三者スニペット |
| Google Jules | Google | 無料 15 タスク/日、AI Pro $19.99/月 100 タスク/日、Ultra 300 タスク/日（Ultra 価格は第三者間で不一致・未確認） | 個人 | あり（タスク → PR） | PR レビュー・マージ | クラウド必須（Google Cloud VM） | https://gemini.google/subscriptions/ | 公式 URL 取得・数値は第三者スニペット |
| Sweep | Sweep | $10/月〜（JetBrains プラグイン） | 個人 | 旧来の GitHub Issue→PR ボットから IDE プラグインへ転換（未確認） | IDE 内で人が採否 | IDE ローカル（LLM 呼び出し先は未確認） | https://docs.sweep.dev/pricing | 公式 URL 取得・数値は第三者スニペット |
| Ellipsis | Ellipsis | $20/開発者/月 | チーム | 部分（レビュー＋修正提案。※本パス未確認） | PR 上で人が採否 | クラウド必須 | https://pricingpagehub.com/company/ellipsis/ （第三者） | **未確認** |
| Tembo | Tembo | Free 10 クレジット/週、Pro $60/月 100 クレジット、Max $200/月 400 クレジット（超過は従量） | 個人・チーム | あり（Issue/監視アラート → PR。※本パス未確認） | PR レビュー・マージ | クラウド必須 | https://docs.tembo.io/resources/pricing | 公式 URL 取得・数値はスニペット |
| Graphite（Agent/Diamond） | Graphite | Hobby 無料、Starter $20/ユーザー/月、Team $40/ユーザー/月 | 個人〜エンタープライズ | 部分（レビューコメント。※本パス未確認） | PR 上で人が採否 | クラウド必須 | https://graphite.com/pricing | 公式 URL 取得・数値は第三者スニペット |
| Greptile | Greptile | $30/席/月（50 レビュー/月込み）、超過 $1/レビュー | 個人〜エンタープライズ | 部分（レビューコメント。※本パス未確認） | PR 上で人が採否 | クラウド。セルフホストはエンタープライズ（未確認） | https://www.greptile.com/pricing / https://docs.greptile.com/pricing | 公式 URL 取得・数値は第三者スニペット |

「※本パス未確認」= 機能の有無は一般知識で記載。本調査の検索結果では裏取りしていない。

## 価格帯の分布

| 指標 | 値 | 根拠 |
|---|---|---|
| 席あたり月額 最低 | $19（Copilot Business / Amazon Q Pro） | 上表。Sweep $10 は IDE プラグインで同列扱いしない |
| 席あたり月額 最高 | $60（CodeRabbit Team 月払） | 上表 |
| 中央値（席課金 10 プラン） | ≈ $30（Greptile / CodeRabbit Essentials / Qodo Teams / GitHub Code Security が $30 に集中） | 上表 |
| 従量課金の有無 | あり。2026 年に Bugbot（$1〜1.5/run）・Greptile（$1/超過レビュー）・Copilot（AI Credits）が席→従量へ移行。Devin（ACU $2〜2.25）・Tembo（クレジット）は当初から従量 | 上表 |
| $1M ARR に必要な席数（参考） | $30/席/月 → 約 2,780 席、$40 → 約 2,080 席、$60 → 約 1,390 席 | 単純計算 |

## 本件（ローカル PC・Docker 不可・Flask）が入り込める隙間

1. **実行場所**: 上表 14 ツール中、標準プランでローカル/オンプレ実行を提供するものは確認できず（Sweep のみ IDE プラグインだが LLM 呼び出し先は未確認）。オンプレはエンタープライズ枠限定（CodeRabbit・Qodo・Greptile、本パス未確認）。→ 「コードも画面も PC の外へ出さない」自動修正は、中小チーム向けに空白。Ollama 対応（メモリ: `constraint-openai-other-env.md`）はこの訴求の根拠になる。
2. **修正の起点**: 各社の起点は静的解析アラート（Copilot Autofix / Snyk）、エラー監視（Sentry / Tembo）、PR 差分（Bugbot / CodeRabbit / Greptile / Graphite / Ellipsis / Qodo）、Issue（Devin / Jules / Copilot agent）。**「実画面の E2E 検証が落ちた」を起点に修正 PR を出す製品は一覧に無い**。WebSpec2Doc は仕様書→テスト→実行→修正の閉ループを同一製品で持つため、起点の差別化が成立する。
3. **人の承認位置**: 全社共通で「PR レビュー・マージ」に置く。本件の「PR で人が判断」は業界標準と一致しており、ここで差別化しない（差別化するなら承認前の**再検証エビデンス**＝修正後の E2E 再実行結果を PR に添付する点）。
4. **価格の置き方**: 中央値 $30/席/月が相場。従量移行の流れを踏まえ、「席」ではなく「修正 PR 1 件あたり」または「検証実行あたり」の従量を主軸にすると比較されやすい（Bugbot $1〜1.5/run が参照点）。
5. **制約の裏返しに注意**: Docker 不可・Flask・単一 PC は「GitHub 上のクラウドエージェントと同じ SLA を出せない」ことを意味する。隙間は「セキュリティ/データ持ち出し制約のある社内 Web システムの保守チーム」に絞るのが根拠と整合する。

## 引用してはいけない数値

- Greptile「82% bug catch rate」（dev.to 記事タイトル。ベンダー訴求由来・一次資料未確認）
- Copilot Autofix「脆弱性の 2/3 以上を修正」「3 倍速く修正」等（GitHub の訴求値。本パスで一次確認なし）
- Sentry Seer の根本原因特定精度（ベンダー訴求値。本パスで一次確認なし）
- Devin の全価格（第三者ブログのみ。公式ページ本文未取得）
- Google AI Ultra の月額（第三者間で $124.99 と $249.99 が混在。未確認）
- Qodo Enterprise「$45〜」（第三者のみ。現行公式ページは構成が変わっている可能性）
- Ellipsis「$20/開発者/月」（第三者のみ）
- Copilot「2026-06-01 に AI Credits 従量へ移行」（第三者ニュースのみ）

## 見つからなかったもの（どう検索したか）

- **採用率・修正受容率の一次データ**: 4 クエリ（ツール名＋pricing 中心）では価格情報しか得られず、受容率（accept rate / merge rate）の公式公開値はどのツールも取得できなかった。→ 次回は `"<tool>" "acceptance rate" OR "merged" site:<公式ドメイン>` で別途 1 パス必要。
- **Snyk Agent Fix の単体価格**: `snyk.io/plans` タイトルに「$25/月〜」のみ。Agent Fix は Snyk Code 同梱で単体価格なし。
- **各ツールのオンプレ/セルフホスト可否の公式記述**: 価格クエリでは出てこず。全て「未確認」扱い。
- **Sweep の現行製品形態**（GitHub ボット継続か JetBrains 専業か）: `docs.sweep.dev/pricing` の存在のみ確認。本文未取得。
