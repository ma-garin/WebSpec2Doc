# トレーサビリティ画面 UX 調査の要約（2026-10-18）

8 テーマ・48 製品。各テーマの詳細と出典 URL は 01〜08 の各ファイル。数値・ベンダー主張は各ファイルの「引用してはいけない情報」に従う。

| ファイル | テーマ | 主な製品 |
|---|---|---|
| 01-import | 取り込み・自動分類 | Jama, Polarion, Purview, Box AI, Notion, Drive |
| 02-writing-review | AI 文書レビュー | Grammarly, Acrolinx, Writer, MS Editor, 文賢, Just Right! |
| 03-code-review | AI コードレビュー・ゲート | CodeRabbit, Copilot review, SonarQube, Snyk, DeepSource, Codacy |
| 04-req-trace | 要求トレーサビリティ | Jama, Polarion, Codebeamer, DOORS Next, ReqView, Visure |
| 05-jp-qa | 国内 QA・文書品質 | ConTrack, CoBrain, ClearDoc, QualityForward, MagicPod, Autify |
| 06-graph-lineage | 依存グラフで問題を強調 | dbt, DataHub/Atlan, Datadog, Backstage, Nx, Obsidian |
| 07-report-approve | レポートと承認 | Lighthouse, Chromatic, Percy, GitHub, Vercel, Allure |
| 08-stepped-ai-review | 段階型 AI 文書審査 | LegalOn, Ironclad, Spellbook, Harvey, Luminance, Juro |

## 画面ごとに採る型（根拠の製品）

### ① 文書を登録
- 最初の操作はファイルを渡すだけ（Drive, Notion, Jama）。既存ファイルを変換させない（ConTrack, CoBrain）
- AI の格付けは低確信度だけ目印を付けて人に見せる。確信度の高いものは確認を省く（Box）
- 人の操作は「承認／変更」の少数に絞り、押した結果を状態で残す（Box, Purview）
- 一覧の先頭に集計（自動で決まった n 件・確認が要る n 件）（Purview）
- 制限と失敗時の次の行動を文面で示す（Notion）

### ② AI が検査
- 結論を最上部に 1 語で（Sonar の Passed/Failed, Chromatic, Lighthouse）
- 重大度は 3 段の固定語彙＋規則の分類を色とアイコンで（CodeRabbit, Copilot, Grammarly, CoBrain）。色だけに頼らない（dbt, Atlan）
- 重い順に並べ、見る順番を決めてやる（ClearDoc, Luminance, Snyk）
- 指摘 1 件は「どこ・なぜ（規則の言葉＋AI の理由）・どう直す」で完結し、本文へ移れる（Sonar, Juro, Ironclad, ConTrack）
- 「必ず直す」と「改善」を分ける（MS Editor, 文賢）
- 誤検知の通報・理由付きの無視（Writer, Snyk, Copilot）

### ③ つながりとレポート → 確定
- 結論を最上部に 1 状態と色で。失敗側を先に（Lighthouse, Allure）
- 同じデータを「線」と「表」の 2 ビューで（ConTrack, DataHub）。グラフは理解用、表は網羅用
- 数字は該当集合への入口（Jama の被覆率 → 絞った表）
- 抜けは「描かない」でなく印で示す（Jama の灰線, ReqView）
- 確定前に「何が確定されるか」を見せ、確定後は状態を明示。入力が変わったら確定を失効（Chromatic, GitHub, Vercel）
- 差し戻しはコメント付きで対象を特定して残す（Chromatic, Percy）

### 確定後の常設トレース表示（課題のある文書を強調）
- 全体を最初から描かず、基点の文書から上流/下流へ 1 段ずつ展開（Atlan, DataHub, Backstage, Nx）
- 問題は重ねる層で。複数の異常は最悪値で 1 状態に束ね、それ以外は薄く（dbt, Datadog）
- 線にも根拠を持たせ、押すと原因の記述が出る（Nx）
- ピラミッド図は使わない（保守者決定 2026-10-18）
