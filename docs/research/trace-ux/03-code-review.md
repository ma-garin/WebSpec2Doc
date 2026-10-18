# 03 AI コードレビュー・静的解析の指摘とゲートの UI

調査日: 2026-10-18。方法: 公式ドキュメントを WebFetch（9 回）と WebSearch（3 回）で確認。実画面のスクリーンショットは見ていない。
「画面の型」は文書の記述からの推定を含む。画面の見た目に関する記述は全て「未確認」。

## 事例（製品ごと）

### 1. CodeRabbit
- 画面の型: PR の先頭に「ウォークスルー」コメント（変更の要約・シーケンス図・レビュー工数の見積）。行ごとの指摘コメントが続く。
- 良い点: 指摘の先頭にカテゴリ（Security & Privacy / Stability & Availability / Maintainability & Code Quality）と重大度（Critical / Major / Minor / Trivial / Info）が付く。提案を PR に直接適用する 1 クリック修正がある。
- 悪い点: 却下の方法はこのページに記載なし。解決は `@coderabbitai resolve` というコマンド入力で、非エンジニアには敷居が高い（推定）。修正案・AI 向けプロンプトの構成は記載なし（未確認）。
- 出典: https://docs.coderabbit.ai/guides/code-review-overview （確認済み）

### 2. GitHub Copilot code review
- 画面の型: PR 上のレビューコメント。人のコメントと同じ扱いで、返信・解決・非表示ができる。概要コメントに承認の見立てが付く。
- 良い点: High / Medium / Low の 3 段階。提案は数クリックで適用でき、複数提案を 1 コミットにまとめられる。「Fix with Copilot」で別 PR か同 PR のコミットとして直せる。各コメントに親指評価。
- 悪い点: 既定では「Comment」レビューで承認にも差し戻しにも数えない。解決した指摘が再レビューで繰り返されることがある。返信は人にだけ見え、Copilot は読まない。
- 出典: https://docs.github.com/en/copilot/using-github-copilot/code-review/using-copilot-code-review （確認済み）

### 3. SonarQube / SonarCloud
- 画面の型: プロジェクト概要に Quality Gate の Passed / Failed。条件は「指標・比較・しきい値」で、新規コード用と全体用に分かれる。指摘詳細は「Where is the issue?」「Why is this an issue?」のタブ構成。
- 良い点: PR と短命ブランチでは新規コードの条件だけ判定する（既存の負債で PR が落ちない）。既定の「Sonar way」は読み取り専用で、新規バグなし・新規脆弱性なし・保守性 A・ホットスポット確認済み・カバレッジ 80% 以上・重複 3% 以下。関連箇所や source→sink の経路を段階的にたどれる。履歴とコメントの Activity タブ。
- 悪い点: 状態遷移（承認・誤検知・確認）、フィルタ、「How can I fix it」の中身は取得できず未確認。Issues 画面の実物も未確認。
- 出典: https://docs.sonarsource.com/sonarqube-cloud/improving/quality-gates/ ／ https://docs.sonarsource.com/sonarqube-server/user-guide/issues/reviewing.md （確認済み）。最初に試した reviewing-issues の URL は 404。

### 4. Snyk
- 画面の型: 課題カードを Priority Score（0〜1000）の降順に並べ、サイドバーでスコア範囲で絞る。Issues タブ・レポート・API にも同じスコアが出る。
- 良い点: 重大度（CVSS）に加え、悪用の成熟度・到達可能性・修正可能性・古さを合成して「先に直す順」を 1 つの数にする。無視は理由と期限を付ける。「修正が出るまで」の無視があり、組織で理由を必須にできる。無視は以後の PR チェックにも引き継がれる。
- 悪い点: スコアは読み取り専用で、算出を変えられない。スコアの内訳の見せ方は未確認。修正 PR の画面は、確認できた範囲では記載なし（パッチ用 `.snyk` ファイルの話のみ）。
- 出典: https://docs.snyk.io/manage-risk/prioritize-issues-for-fixing/priority-score （確認済み）。無視の情報は WebSearch の要約で、ページ本文は未取得: https://docs.snyk.io/scan-fix-and-prevent/fix/prioritize-issues-for-fixing/ignore-issues

### 5. DeepSource
- 画面の型: リポジトリの Issues 画面。直近 PR の一覧に「修正した数・持ち込んだ数」が出る。
- 良い点: PR では、既定ブランチに存在しない新規の指摘だけを出す（Community analyzers の記述）。ゲートはカテゴリと重大度で絞れる。Autofix は、PR の解析なら PR のブランチに直接コミットし、既定ブランチの解析なら新規 PR を作る。
- 悪い点: ゲートが新規だけを数えるかは明記が見つからない。Autofix が PR 持ち込み分だけかも不明。Transformers のページは 404。実画面は未確認。
- 出典: WebSearch の要約のみ。https://docs.deepsource.com/docs/platform/dashboard/repository/history ／ https://docs.deepsource.com/docs/platform/dashboard/team/home （ページ本文は未取得）

### 6. Codacy
- 画面の型: リポジトリ設定の Gates タブ。PR とコミットの品質概要に指標の色を出し、Git プロバイダに PR のステータスを返す。
- 良い点: ゲートは「持ち込んだもの」を評価する（新規指摘が重大度しきい値以上で N 件超、新規セキュリティ指摘、複雑度、重複、カバレッジ変動、差分カバレッジ）。組織の方針で既定ゲートを揃えられる。
- 悪い点: 重大度の段階名は記載なし。マージを止めるには Git 側の連携が別途必要。既存の指摘を扱うゲートは記載なし。
- 出典: https://docs.codacy.com/repositories-configure/adjusting-quality-gates/ （確認済み）

## 共通する成功パターン
1. 結論を最上部に 1 語で出す: Passed / Failed（Sonar）、PR 状態（Codacy）、承認の見立て（Copilot）、ウォークスルー（CodeRabbit）。
2. ゲートは「今回持ち込んだもの」だけで判定する。既存の負債で今回の人を落とさない（Sonar の PR は新規コード条件のみ、Codacy、DeepSource）。
3. 重大度は 3〜5 段階の固定語彙で、各指摘に必ず付く（CodeRabbit の 5 段階、Copilot の 3 段階）。重大度に加えて分類も付ける（CodeRabbit のカテゴリ）。
4. 並び順を決める 1 本の指標を持つ。Snyk は複数要因を合成した 0〜1000 を、降順と範囲絞り込みに使う。
5. 指摘 1 件は「場所・理由・直し方」を同じ画面で完結させる（Sonar のタブ、Copilot の提案）。直しは 1 クリックで適用でき、直前に差分を見られる（Copilot、CodeRabbit）。
6. 却下は理由を必須にでき、期限を付けられ、履歴が残る（Snyk の無視、Sonar の Activity）。
7. 機械の判定と人の承認を分ける。Copilot は既定では承認に数えず、新規 push で承認が失効する。
8. 指摘に対する評価（親指）を取り、誤検知を学習に回す（Copilot）。

## 本製品への適用案
本製品の流れ: Tier1〜4 に格付けして登録 → 6 規則で検査 → つながりとレポート → 人がレポート確定 → 確定後に課題文書を強調表示。
1. レポート最上部に「確定可 / 要対応」を 1 語で出し、条件は「指標・比較・しきい値」の形で並べる（Sonar 型）。判定対象は今回の登録・更新で増えた課題だけにし、前回からある課題は別の欄に分ける（Codacy 型）。
2. 課題の重大度は 3 段階の固定語彙にして、規則の名前（6 規則）をカテゴリとして併記する（Copilot の 3 段階と CodeRabbit のカテゴリ）。並び順は「格付けの高さ（Tier1 方針ほど重い）× 重大度」の 1 本の順序にし、絞り込みを付ける（Snyk の考え方。式は未検証の設計案）。
3. 課題 1 件は「どの文書の・どこが」「どの規則に反するか（理由）」「直し方の案」の 3 点を同じ画面に置く。文書を書かない QA でも読める日本語にし、直しは「案を採用 / 却下」の 2 択ボタンにする（Copilot 型。自動で本文を書き換えるかは別途判断）。
4. 人の操作は「採用 / 却下（理由必須）/ 保留」とし、却下には理由と期限を付けて履歴に残す（Snyk 型）。レポート確定は人だけが押し、AI は確定しない。確定後に文書が更新されたら確定が失効して再確認になる（Copilot の承認失効）。
5. 確定後の強調表示は、全課題ではなく「却下されていない課題がある文書」だけに絞り、文書側に重大度の最大値だけを出す。レポートへ戻るリンクを付ける。

## 引用してはいけない情報
- 6 製品の画面の見た目（配色・配置・アイコン）: 実画面を見ていないので述べられない。
- CodeRabbit の修正案・「AI エージェント向けプロンプト」の有無: 取得ページに記載がなく未確認。
- Sonar の Issues 画面のフィルタ項目、状態遷移名、「How can I fix it」の構成: 未取得。
- Snyk の Priority Score の内訳の画面表示、修正 PR の UI: 未確認。無視の期限・理由の記述は検索要約のため、デフォルト期限は資料間で食い違っており（30 日の記載あり）引用不可。
- DeepSource の Quality Gate が新規指摘のみを対象にするか、Autofix の対象範囲: 明記なし。「新規のみ」は Community analyzers の記述で、他の解析器への一般化は未検証。
- Sonar way の条件数: 原文が「4 つ」と書き実際は 6 項目。数は引用せず項目名で書く。
- 3 章の適用案の式（格付け × 重大度）は設計案で、効果は未検証。
