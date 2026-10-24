# S06 r3: 計画・文書を読む・質問票・指摘の検討 ＋ 対検査の不具合 3 件

## 変更
- templates/docverify/_review.html: 各画面に状態帯（data-dvr-state）と下部判定帯（data-dvr-gate）
- static/js/docverify-review.js: 計画（目的・出口基準＝設定の値表示と「設定で変える」・期限・担当 4 役割・対象文書と版）、文書を読む（要件/設計の二面ビューア＋本文選択→「指摘にする」。旧の候補一覧は撤去）、質問票（要確認の指摘から質問を起こす・宛先/期限/回答/状態の編集保存・CSV リンクは既存のまま）。全画面で読込中/0 件/失敗の状態帯と GET pair/gate の判定帯（合格/不合格/判定不能）
- web/routes/doc_verify_pair.py: POST pair/findings（手で起こす指摘 M-nnn）、GET/POST pair/questions（questions.json）
- static/css/docverify.css: 追記のみ（.dvp の部品を .dvr-view へ複製＋r2-* と、旧表 #dvR4-triage の非表示）
- 不具合: docverify-pair.js（①引用へのスクロールをビューア内だけに ②時刻を JST「YYYY-MM-DD HH:MM」表示 ③見出しに状態チップ 準備中/検討中/判定可/承認済み）、docverify-pair.css（対検査表示中は .dv-content を overflow:hidden、チップの色）、_pair.html（チップ要素）

## 確認した経路（8770・seed 済み v1-a-order-payment / 検査 db26053a7dac）
- API: gate 200、POST findings 201（M-001）、空入力は 400「本文を選び…」、POST questions 200（Q-001）、存在しない案件は not_found の文言
- 画面（headless Chrome・1366/1100/900 幅）: 計画・文書を読む・指摘の検討・質問票・対検査 → 横スクロール 0、JS エラー 0、判定帯「全体 不合格…」
- 文書を読む: 基本設計書の本文を選択→「指摘にする」→「M-002 を登録しました。」
- 対検査: 指摘カードのクリック後も .dv-content.scrollTop=0（ページ本体が動かない）、証跡の時刻「2026-10-24 18:22」（JST）、p1-head のチップ「検討中」
- 旧表 #dvR4-triage は display:none（3 幅とも）

## 未検証・要判断
- 修正版の確認（項目 4）は指示により別担当へ移管。旧画面のまま（状態帯・判定帯だけ付く）
- 要判断: ページ上部の共通見出しの「◎ 準備中」チップは docverify-*.js・テンプレートに文字列が見つからず未修正。対検査の見出し p1-head 内に状態チップを新設して対応。上部チップの出所の特定が必要
- 要判断: 旧表 #dvR4-triage は docverify-process.js（担当外）が差し込むため CSS で非表示。DOM からの撤去は process.js 側で
- 要判断: 質問票の CSV 出力は既存（検査の要確認指摘）のまま。新しい質問（pair/questions）は CSV に入らない。回答 CSV 取り込みの導線は外した
- 要判断: 担当は名前の手入力（「、」区切り）。設定の roles（利用者 ID）との結び付けは未実装
- 未検証: 承認済み・判定可のチップ（該当データ無し）、状態帯の「失敗」表示、低い画面高さ、Chrome 拡張タブでの目視（headless Chrome で代替）
- 段の表示（計画/個別レビュー/…）は旧語彙のまま（renderSteps は担当範囲外）
- 文書を読む: 右パネルの「選んだ本文」枠が縦に伸びる（見た目のみ）
- 検証で data/docverify の v1-a-order-payment に M-001・M-002・Q-001 を書き込んだ（追跡外のデータ）
