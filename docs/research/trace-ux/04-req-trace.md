# 04 要求管理ツールのトレーサビリティ表示と抜け・問題の強調

調査日 2026-10-18。WebSearch 10 回・WebFetch 10 回（うち本文取得に成功したもの 6 件）。
凡例: [確認] = ページ本文を取得して確認 / [検索要約のみ] = 検索結果の要約で見たのみ / [未確認]。

## 事例

### 1. Jama Connect（Live Trace Explorer・Trace View）
- 画面の型: 図。プロジェクトツリーから生成し、仕様のタイルとテストケースのタイルを線（トレースパス）でつなぐ。
- 抜けは灰色の線、有効は緑・疑わしい（suspect）は赤で、線ごとに割合を出す。ホバーで件数。
- 総合は Trace Score（0〜100%）。電卓ボタンで算出根拠と設定を開く。ルールごとの被覆率を選ぶと、その集合に絞った Trace View（表）へ飛ぶ。
- 良い点: 完全性（被覆）と品質（suspect）を別の軸で 1 画面に出す。数字から該当集合の表へ 1 クリックで降りる。draft 等を除外するフィルタ（9.28.1）。
- 悪い点: 図の既定の配置・選択時の強調はヘルプに記載なし（未確認）。G2 レビューに「家系図のような視覚的な全体像が無い」との指摘が 1 件ある。
- 評判: Capterra 4.3（15 件）・使いやすさ 4.0。G2 4.3（184 件）。個別レビューは「トレース表の更新が早い」「直感的」と「エディタが初心者に難しい」「絞り込みが不便」「高価」。
- 出典: https://help.jamasoftware.com/ah/en/manage-content/coverage-and-traceability/live-trace-explorer.html [確認] / https://help.jamasoftware.com/ah/en/manage-content/coverage-and-traceability/live-trace-explorer/what-s-included-in-the-diagram.html [確認] / https://www.capterra.com/p/80432/Jama/reviews [検索要約のみ]

### 2. Siemens Polarion（Matrix view・Impact）
- 画面の型: 行列。縦軸と横軸の Work Item を検索式で指定し、交点で実際のリンクまたは潜在リンクを示す。
- suspect は変更検知で自動付与され、メール通知する（MathWorks の製品紹介が根拠）。
- 良い点: 軸を検索式で自由に決められる。サードパーティ拡張が、選択項目の上流・下流の鎖を可視化し、suspect を書き込む前に結果を試算する。
- 悪い点: 公式 Matrix view 本文は取得できず（リダイレクト先が空）、抜け・suspect の具体的な色や記号は未確認。
- 評判: Capterra / GetApp に「学習に相当な訓練が要る」「古く分かりにくい設計」「遅い（2018 年の 1 件）」「組込みレポートが基本的」。件数は未確認。
- 出典: https://docs.plm.automation.siemens.com/content/polarion/20/help/en_US/user_and_administration_help/user_guide/work_items/matrix_view.html [検索要約のみ。本文は取得失敗] / https://extensions.polarion.com/extensions/501-rop-cascade [検索要約のみ] / https://www.capterra.co.uk/reviews/192715/polarion-alm [検索要約のみ]

### 3. PTC Codebeamer（Traceability Browser）
- 画面の型: 左から右へ列が段階になった表。1 列目が起点トラッカーの項目、以降の列が各段のリンク先。列の間に関連の種類を示す小アイコン。
- 左パネルで「次に足す候補トラッカー」を 1 クリックで追加。設定はパーマリンクとプリセットで保存。Excel / Word に出力。
- suspect は項目名の後ろのアイコン（「copy of」「depends on」の関連で発生）。レポートでは「suspected」バッジから解除できる。
- 良い点: 段を足すだけで鎖を伸ばせる。構成を URL で共有できる。
- 悪い点: 抜け（リンク無し）の表示方法は公式本文に記載なし（未確認）。被覆の確認は別画面の Test Coverage Browser。
- 評判: Capterra 4.1（31 件）・使いやすさ 3.8。個別コメントは未確認。
- 出典: https://support.ptc.com/help/codebeamer/r2.1/en/codebeamer/user_guide/555740.html [確認] / https://support.ptc.com/help/codebeamer/r2.2/en/codebeamer/user_guide/1822415.html [検索要約のみ] / https://www.capterra.com/p/92177/codebeamer/ [検索要約のみ]

### 4. IBM DOORS Next（Traceability views）
- 画面の型: 表（モジュールの列に関連先の属性を出す）と、図（Link Explorer。複数段のリンクを関係名つきで描く）。
- suspect は「Link Validity」へ発展。利用者が有効・無効を指定でき、判断が無ければ既定で suspect。状態は共有テーブルに保存。ReqIF 再取り込みで該当リンクが suspect になる。
- 悪い点: 有効性の状態でモジュールの表を絞り込む・並べ替える要望が IBM Ideas に出ている（機能が無い証拠。実装済みかは未確認）。
- 評判: Capterra 4.4（8 件）・使いやすさ 3.8。件数が少ない。
- 出典: https://jazz.net/forum/questions/277872/suspect-links-for-doors-7 [検索要約のみ] / https://ibm-ai-apps.ideas.ibm.com/ideas/ENGRMDN-I-1176 [検索要約のみ] / https://www.capterra.com/p/238454/IBM-Engineering-Requirements-Management-DOORS-Next/reviews/ [検索要約のみ]

### 5. ReqView
- 画面の型: 構造化文書の表。要求の行に Links 列があり、リンクがその場に出る。専用のマトリクス画面は確認できず（未確認）。
- 抜けは「ある関連が無い」という条件（例: NOT Is satisfied by）で絞り込んで一覧化。印刷・Excel 出力で保存。多段の抜けは HTML 出力テンプレートで「Missing satisfaction links!」等の文を出す。
- 良い点: 文書と同じ画面で見える。抜けの抽出が条件 1 本で足りる。
- 悪い点: 1 段ずつの抜けしか画面で出せない（公式ブログ自身が「単一レベルのみ」と記載）。suspect の表示は記載なし（未確認）。
- 評判: G2 ページは 403 で取得できず、件数・コメントは未確認。
- 出典: https://www.reqview.com/blog/2017-09-13-tips-requirements-coverage-gaps/ [確認。2017 年の記事で現行 UI と差がある可能性]

### 6. Visure Requirements
- 画面の型: ライブのマトリクスと関係ビュー（上流・下流の双方向）。図・木の有無は本文で確認できず（未確認）。
- 抜けは自動検出し、レビュー前に Coverage Alert を出す。suspect は変更後に要レビューを通知。ダッシュボードで追跡済み割合を表示（例は 97%）。AI が提案したリンクは承認してから登録。
- 良い点: 抜け・suspect・被覆を 1 つのダッシュボードに集約。AI 提案を人の承認の後ろに置く。
- 悪い点: 具体的な強調の色・記号は本文に無く未確認。
- 評判: 比較サイトで 7.7/10 の記載のみ。G2・Capterra の件数は未確認。
- 出典: https://visuresolutions.com/features/requirements-traceability-management-software/ [確認。ただし画面の細部は記載なし] / https://academy.visuresolutions.com/en/article/using-the-traceability-matrix-for-impact-analysis [検索要約のみ。直接取得は 404]

## 共通する成功パターン
1. 被覆（完全性）と疑わしさ（品質）を別の軸で出す。Jama は緑・赤・灰の線と Trace Score、Visure は抜け・suspect・割合を同じダッシュボードに置く。
2. 抜けは「何も描かない」でなく、抜けと分かる印を出す。Jama は灰色の線、ReqView は「Missing ... links!」。
3. 数字は該当集合の表への入口にする。Jama は被覆率を選ぶと絞った Trace View に降りる。
4. suspect は項目の横の小さな印で出し、利用者が解除・判断できる。Codebeamer（アイコンと解除ボタン）、DOORS Next（有効・無効の指定、判断が無ければ suspect）。
5. 段を足して鎖を伸ばす構成。Codebeamer の列追加、DOORS Next の Link Explorer、ReqView の NEEDS ← SRS ← TESTS。
6. 構成を保存・共有できる（Codebeamer のパーマリンクとプリセット）。Jama は診断図の既定設定を保存できる。
7. 算出根拠を開ける。Jama の電卓ボタン（Trace Score の式と設定を表示）。
8. 計算から外すものを利用者が決められる。Jama のフィルタ（draft・却下を被覆から除外）。Polarion は suspect を付ける項目を限定する要望が出ている（PTC コミュニティ）。

## 本製品への適用案
1. 常設の鎖表示は Tier1 → 4 を左から右の列にする（Codebeamer 型）。問題のある文書は行末にアイコン、グループ全体は Jama 型の「緑・赤・灰」の割合で出す。理由: パターン 1・2・5。
2. 「確定後に課題を強調」を 2 軸にする。検査の指摘が未解決の文書は赤、上位とのつながりが無い文書は灰、問題なしは緑。数字（赤 N 件）を押すと、その集合だけの文書一覧に降りる。理由: パターン 1・3。
3. 指摘は QA が「確認済み／要対応」と判断して解除できる（DOORS Next の有効・無効型）。判断が無いものは既定で要確認。AI は解除しない。理由: パターン 4。Visure の AI 提案は人の承認の後に登録する。
4. 件数や点数には必ず「内訳を見る」ボタンを付け、6 つの規則のどれで何件かを出す（Jama の電卓型）。除外条件（メモ層 Tier4 を被覆から外す等）は利用者が切り替えられる。理由: パターン 7・8。
5. 文書を選んだとき上流・下流の鎖を強調する機能は、今回調べた製品の公式本文では確認できなかった。独自の設計判断として別途試作で確かめる（根拠なしの採用はしない）。

## 引用してはいけない情報
- G2 の「AI Generated Summary」比較ページは自動生成で、個別レビューと矛盾する。数値・評価を引用しない。
- 比較・ランキング系サイト（gitnux・wifitalents・worldmetrics 等）の点数（Visure 7.7/10 を含む）。算出根拠が不明。
- Polarion の「遅い」は 2018 年の GetApp の 1 件。現行版の評価として引用しない。
- Capterra の DOORS Next（8 件）は少数。傾向として扱わない。件数は国別サイトでも差がある。
- ReqView の 2017 年のブログは現行 UI と違う可能性がある。ReqView・Polarion の suspect 表示、Visure の画面の細部は未確認。
- ReqView の G2 レビューは取得できなかった（403）。評判は未確認。
- Polarion の「suspect を付ける項目を限定したい」は PTC コミュニティの質問の要約で、回答は未確認。
