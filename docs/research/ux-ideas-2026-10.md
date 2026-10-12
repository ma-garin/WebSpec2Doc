# System 01 UX 案の調査（2026-10）

調査範囲: WebSearch 5 回・WebFetch 6 回（うち 3 回が 404/403 で本文未取得）。本文を確認できたのは NN/g の 1 件のみ。他は検索スニペット由来で「主張」扱い。数値は出典に書かれたものだけを引用し、未確認は「未確認」と明記。

## 1. 初回のサイト登録〜最初の成果物の導線（MagicPod / mabl / Autify / Testim / Katalon）

### 主張（ベンダー資料・検索スニペット。本文未確認）
- 練習用アプリの提供 / mabl / 自分のアプリが無くても公式サンドボックスサイトで最初のテストを作れる / mabl Docs「Getting started」(https://help.mabl.com/docs/getting-started) 年未確認
- 最初のテストを軽い題材に限定 / mabl / スモーク・ログイン・サインアップから始めるよう案内し初回成功までを短くする / 同上
- 文章から概要を生成 / mabl Test Creation Agent / 記述から開始アウトラインを作り白紙画面を避ける / https://help.mabl.com/hc/en-us/articles/38362436631316（403 で本文未取得、年未確認）
- 手順を固定した導入 / MagicPod / 組織作成→プロジェクト作成→ログインテストを録画、の一本道 + 14 日トライアル / Udemy「No-code test automation for QA web with MagicPod」(https://www.udemy.com/course/no-code-test-automation-for-qa-web-with-magicpod/) 年未確認、第三者講座
- 動画ガイド / mabl / クイックスタート動画で導線を補う / https://help.mabl.com/docs/quick-start-video-guide 年未確認

### 未確認
- Autify・Testim・Katalon の初回導線、進捗表示、途中結果表示、ログイン壁の案内、所要時間提示、空状態は一次情報に到達できず「未確認」。

## 2. AI 生成結果の見せ方・編集・信頼度・差分

### 主張（ベンダー資料）
- 下書き→選別→取り込み / Qase AI / 生成物を「下書き」として見せ、採用するものだけをリポジトリに追加させる / Qase Docs「AI Test Case Generator」(https://docs.qase.io/qase-ai) 年未確認（Beta・Business 以上）
- 責任の明示 / Qase AI / 精度は保証されず利用者判断と明記し、盲信を防ぐ / 同上
- 作成者・状態での絞り込み / Qase / AI 作成物を作者や状態でフィルタ・監査できる / https://www.qase.io/blog/qase-mcp-bringing-ai-generated-testing-into-the-real-sdlc/ 年未確認
- 自動修復の差分レビュー / Momentic / AI が足した・変えた手順を専用状態で示し、YAML 差分ダイアログで 1 クリック承認 / https://momentic.ai/docs/platform/auto-healing/managing-proposals（検索スニペットのみ。fetch は 404）。ベータ、7 日以内に成功したテストのみ対象
- 既存網羅の考慮 / テスト管理系生成器 / 既存スイートを読み、カバー済みを飛ばしてギャップだけ提案 / https://testomat.io/?p=32972 年未確認、第三者ガイド

### 未確認 / 注意
- 信頼度スコア表示の実例は確認できず「未確認」。Checksum の承認 UI も未確認。
- Octomind は 2026-05 に提供終了と報じられた（第三者記事、未確認）。参考にしない。

## 3. 長時間処理の UX

### 実証・一次資料
- 1 秒超は進捗表示、2〜10 秒はスピナー、10 秒以上は完了率表示 / 待ちの途中離脱を防ぐ / NN/g「Progress Indicators Make a Slow System Less Insufferable」(https://www.nngroup.com/articles/progress-indicators/) 2014
- 手順数を出す（「3 / 50」）/ 残りが見え待つかを自分で決められる / 同上
- 序盤を遅く・終盤を速く見せ、余裕を持たせた目安を出す / 同上
- 中止ボタンを置く / 閉じ込められた感覚を避ける / 同上
- 静的な「Loading…」と「二度押さないで」を避け、最初の操作が受理されたことを示す / 同上
- 進捗バーありは満足度が高く、待てる時間が平均 3 倍（ネブラスカ大リンカーン校の研究、方法の詳細は同記事に無く未確認）/ 同上
- 見積が不確かなら完了率表示の閾値を下げる / 同上

### 主張（二次資料）
- 見積残り時間は経過時間と進捗の線形補間 / QGIS 3.4 変更履歴 (https://changelog.qgis.org/en/entry/995) 年未確認
- バックグラウンド実行は画面を塞がず、完了を通知 / Pimcore Portal Docs (https://pimcore.com/docs/portal-engine/2.5/User_Documentation_for_Portals/General_Features/Background_Tasks.html)
- 前景処理は待ち時間を示し、バックグラウンド処理は完了通知を必須にしない / Microsoft 旧ガイドライン (https://learn.microsoft.com/en-us/previous-versions/dd356072(v=vs.85)) 年未確認
- NN/g のバックグラウンド実行・完了通知に関する一次資料は未確認（検索で到達せず）。

## WebSpec2Doc に適用できそうな案 10 件（効果の大きい順）
1. 巡回中は「ページ n / 推定 N」の完了率と手順名を出す（NN/g。実証。見積が不確かな間は幅を持たせた時間表記）
2. 巡回開始と同時に「受け付けました」を即表示し、二重送信を防ぐ（NN/g）
3. 巡回中も発見済みの画面から順に成果物を閲覧可能にする（途中結果。主張ベースの発想、未検証）
4. 中止ボタンと「中止時に保存される途中結果」を明記する（NN/g）
5. 画面を閉じても巡回を続け、完了時にアプリ内通知で知らせる（Pimcore 等の主張、未検証）
6. 生成物は「下書き」ラベルで出し、採用・除外を選別して確定させる（Qase 型）
7. 再生成時は前回との差分を並べ、1 クリックで採用/却下する（Momentic 型の差分承認）
8. 要素ごとの根拠（取得元 URL・画面）を併記し、AI 推定と実測を区別して表示する（信頼度スコアの実例は未確認のため、区別表示のみ）
9. ログイン壁に当たったら巡回を止めず「未取得の画面」として一覧化し、認証情報の入力を促す（mabl 等の事例は未確認。自前設計）
10. 空状態に練習用サンプルサイトでの試行ボタンを置く（mabl の練習アプリ型）と、初回は 1 URL・1 クリックで開始できる最短導線にする
