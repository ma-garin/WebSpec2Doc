# 品質レポートと人による承認（確定）の UI 調査

調査日: 2026-10-18。WebSearch 3 回・WebFetch 13 回（上限 10 回を超過。内 3 回は 404 または転送のみ）。
画面そのものは見ていない。公式ドキュメントの文面と、検索結果の要約に基づく。画面の見た目の記述は「未確認」と明記する。

## 事例（製品ごと）

### Lighthouse（レポート）
- 画面の型: カテゴリ別の 0〜100 点が最上部。下に Opportunities / Diagnostics / Passed audits の順に並ぶ（検索要約より）。
- 良い点: 点数が色で 3 段階に分かれる（0〜49 赤 / 50〜89 橙 / 90〜100 緑）。合格項目は最後に寄り、失敗項目が先に目に入る。JSON 保存と Viewer で共有できる。
- 悪い点: 点数に寄与しない Opportunities / Diagnostics が混在し、点と一覧の関係が間接的（検索要約）。「承認」の概念は無い。第一画面の実際の配置と Passed audits の折りたたみ挙動は「未確認」。
- 出典: https://developer.chrome.com/docs/lighthouse/performance/performance-scoring （色の閾値。実際に見た）／https://developer.chrome.com/docs/lighthouse/overview （実際に見た。第一画面の記述なし）／https://developer.chrome.com/blog/lighthouse-13-0 （検索結果で題名のみ。本文は未確認）

### Chromatic（UI Review）
- 画面の型: PR ごとに Review ができ、Changeset タブで変更を左右比較。変更箇所を蛍光緑で強調するトグルがある。Activity タブ下部にチェックリスト（変更の承認・議論の解決・レビュアーの承認）。
- 良い点: 状態が Pending（黄）／Passed（緑）の 2 つで明快。変更ごとのスレッドで理由を残せ、解決しないとチェックリストが完了しない。既定レビュアー全員の承認が要る設定がある。PR のステータスチェックとして外部に出る。
- 悪い点: 公式の「却下」操作は無く、コメントで修正を求める方式。差し戻しの理由に種類（レベル）は無い。承認後の見た目の細部は「未確認」。
- 出典: https://www.chromatic.com/docs/review/ （実際に見た）

### Percy（Visual review）
- 画面の型: ビルド単位・類似変更グループ単位・スナップショット単位で承認する。ブラウザと幅の組はまとめて 1 件として扱う。
- 良い点: 「変更を要求」を押すと日時付きコメントが自動で作られ、@メンションで相手に通知できる。要求済みの状態は、差分が同じ間は次のビルドへ引き継がれ、差分が変わると「未レビュー」に戻る。main ブランチは既定で自動承認。
- 悪い点: スナップショットの承認は取り消せない。ビルド全体には「変更を要求」を出せない（1 件でも要求があればビルドが追従する）。画面の見た目は「未確認」。
- 出典: https://www.browserstack.com/docs/percy/visual-testing-workflows/view-percy-build-results/approval （検索結果の要約のみ。本文は未取得＝未確認の部分あり）／https://browserstack.com/docs/percy/build-results/change-request （転送ページのみで中身は未確認）／https://docs.percy.io/docs/review-and-approve-builds （404）

### GitHub（PR の Review 送信と merge box）
- 画面の型: Files changed の「Review changes」で、総括コメントを書き Comment / Approve / Request changes の 3 択から選び「Submit review」。送信前の行コメントは自分にだけ見える下書き。
- 良い点: 送信前は下書きで、編集も破棄（Discard review）もできる。承認はサイドバーに集まり、マージ要件に数えるものを上段に分ける。古い承認の自動失効（コード変更の push で承認が消える設定）がある。作成者は自分の PR を承認できない。
- 悪い点: Request changes は既定では情報提供で、保護ルールが無ければマージを止めない。管理者は承認なしでマージできる。総括コメントが必須かは公式ページに記載なし（未確認）。merge box の画面と必須チェックの詳細は未取得（未確認）。
- 出典: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/reviewing-proposed-changes-in-a-pull-request （実際に見た）／https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/about-pull-request-merges （見たが merge box の記載なし）

### Vercel（Preview と Promote）
- 画面の型: Deployments 一覧の「…」メニューから「Promote to Production」。確認ダイアログに、リンクされるドメインが出る。本番の状態は Staged / Promoted / Current の 3 つ。
- 良い点: 確認ダイアログで「何が変わるか」（ドメイン）を先に見せる。Instant Rollback で前の状態へ戻す経路がある。Promoted 済みは再 Promote できず、戻すにはロールバック（状態遷移が一方向で明確）。
- 悪い点: プレビュー用の環境変数が本番用に差し替わる点は、ダイアログではなく注記（公式ページ上は注）にとどまる。理由付きの却下は無い。ダイアログの実画面は「未確認」（画像は取得していない）。
- 出典: https://vercel.com/docs/deployments/promoting-a-deployment （実際に見た）

### Allure Report（Qase / TestRail 以外のテスト報告）
- 画面の型: 概要ページに状態別の集計とチャート（現在の状態・重大度・状態の推移）。状態は 5 つ（Passed 緑 / Failed 赤 / Skipped 灰 / Broken 黄 / Unknown 紫）。失敗は Categories で原因別に分類できる。
- 良い点: 「Failed（製品の不具合）」と「Broken（テスト側の欠陥）」を分ける。色を画面全体で統一。分類ルールを正規表現・状態・不安定さで定義できる。
- 悪い点: 概要の実際の配置と、概要からテスト詳細・手順までの展開の流れは、取得できた文面に記載が無い（未確認）。承認の仕組みは無い（品質ゲートの存在は索引に見えたが本文は未確認）。
- 出典: https://allurereport.org/docs/test-statuses/ （実際に見た）／https://allurereport.org/docs/ （実際に見た）／https://allurereport.org/docs/visual-analytics.md と https://allurereport.org/docs/v3/migrate.md （検索結果の要約のみ）

## 共通する成功パターン
1. 結論を最上部に 1 つの状態と色で出す。Chromatic の Pending/Passed、Lighthouse の 3 色、Allure の状態色。
2. 色と状態語を画面全体で統一する。Allure（フィルタ・一覧・チャートで同じ色）、Lighthouse。
3. 失敗側を先に、合格側を後ろに寄せる。Lighthouse の並び順。
4. 承認の前に「何が変わるか」を見せる。Chromatic の差分と強調トグル、Vercel のドメイン表示。
5. 送信前は下書き、送信で確定する。GitHub の pending review と Discard。
6. 差し戻しは「コメント付き＋対象の特定」で残し、解決を完了条件にする。Chromatic（スレッドの解決）、Percy（日時付き自動コメントと @メンション）。
7. 承認後は状態を明示し、入力が変われば失効または戻す。GitHub の stale 承認の失効、Percy の差分変化で「未レビュー」へ戻る、Vercel の Staged→Promoted→Current。
8. 原因の種類で分類して見せる。Allure の Failed と Broken の区別、Categories。

## 本製品への適用案
1. 第一画面は「確定可否」の 1 状態＋色（確定待ち／要対応あり／確定済み）にし、その下に Tier 別・規則別の件数を置く。課題のある文書は先頭、問題の無い文書は末尾に畳む（Lighthouse/Allure の並びと色統一）。
2. 承認②の確認ダイアログに「確定すると何が変わるか」を出す。強調表示される文書の件数、未解決の課題数、承認①から変わった文書（Vercel のドメイン表示と Chromatic の差分の発想）。
3. 差し戻しは 3 択（見た目／内容／方針）＋理由欄とし、選んだ時点で戻り先（格付け／検査／方針）を画面に明記する。理由コメントは対象文書に紐づけ、解決まで確定を押せなくする（Chromatic/Percy）。Percy 型の自動日時付きコメントも採る。
4. 確定後は状態を一方向（確定待ち→確定済み）で表示し、対象文書や格付けが変わったら「要再確定」に戻す（GitHub の stale 承認、Percy の差分変化）。
5. 確定前の指摘は下書き状態で保持し、確定で一括送信する。確定は取り消せない点を、押す前に 1 行で示す（Percy はスナップショット承認を取り消せない）。

## 引用してはいけない情報
- Lighthouse 第一画面の実際の配置、Passed audits の折りたたみ挙動（検索要約のみ。未確認）。
- Lighthouse 13 の変更内容（検索要約のみ）。
- Percy の承認画面の見た目、ボタン名の細部（検索要約のみ。公式ページ本文は未取得）。
- GitHub の merge box の画面と必須チェックの詳細、総括コメントの必須性（未確認）。
- Vercel のダイアログの実画面（画像は見ていない）。
- Allure の概要ページの配置・展開の流れ・品質ゲートの動作（未確認）。
- Chromatic の承認後の画面の細部（未確認）。
- 本ファイルに数値の効果測定は無い。採用率や離脱率などの根拠にしてはいけない。
