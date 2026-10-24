# S06 目視欠点 3 件の修正（R4）

## 変更箇所
1. 判定と記録の時刻を JST に統一
   - static/js/docverify-core.js:17 `fmtJst`（共通の整形関数。UTC → 「2026-10-24 18:17」）。DV に公開（:369）
   - static/js/docverify-pair.js:24 / static/js/docverify-cases.js:15 の `when` を `DV.fmtJst` 呼び出しに置換（独自整形を削除）
2. 上部見出しの状態チップを対検査の状態で描画
   - static/js/docverify-core.js:156 見出し（#dv-ph-state）にチップ 1 個＋レビュー名。旧 PHASE_STATUS（工程名）表示を削除
   - static/js/docverify-core.js:169 `setPairChip`／:175 `loadPairChip`（openReview 時 :222 に GET pair/findings ＋ pair/trail から判定）
   - static/js/docverify-pair.js:183 renderChip は DV.setPairChip を呼ぶだけ
   - templates/docverify/_pair.html:6 の対検査見出し内チップを削除（チップは 1 か所）
   - static/css/docverify-pair.css:107-110 チップのスタイルを #dv-ph-state にも適用
3. 旧サブタブ列（● 計画 / 個別レビュー …）を描画しない
   - templates/docverify/_review.html:4 の `data-dvr-steps` 要素を削除
   - static/js/docverify-review.js の renderSteps と呼び出し 2 か所を削除
- 付随: static/css/docverify.css:261 上部タブの左右余白 14px→8px（1366 幅でタブ列が横スクロールしていたため）

## 確認（8770・Chrome headless・1366x800・レビュー db26053a7dac）
- 対検査 / 文書を読む / 判定と記録: JS エラー 0、ページ横スクロール 0（scrollWidth 1366 = 幅 1366）
- 上部タブ列の横スクロール: 3 画面とも 0（余白変更後）
- 判定と記録の証跡時刻: 「2026-10-24 18:23」等 JST で表示（UTC 09:23 の保存値）
- 状態チップ: 3 画面とも見出しに 1 個だけ「検討中」（採否記録あり・全体不合格）。.steps 要素 0 件
- 未検証: 判定可・承認済みの表示（該当データなし）。pytest 未実行（指示により）
