# C3 DONE

## 通した経路
- /dev/states?state=<9種> → web/routes/dev_states.py states_demo → templates/_states_demo.html（partials/states/* を include）→ UIStates.set → data-state 切替（保存なし・表示のみ）→ 認証オン時は 404
- 競合→「自分の変更を保持」→ data-state=dirty・帯「自分の変更を保持しています。」→ 画面内リンク押下で確認ダイアログ「保存していない変更があります。破棄してこの画面を離れますか？」→ キャンセルで留まる（URL 不変を確認）
- トースト: 成功は 4.3 秒後に消え、失敗は残る（実測）
- 起動は CR-C3-001 未取込のため、scratchpad の起動スクリプトで blueprint を登録して 8784 で確認

## 確認した状態と幅
- 9 状態 × 1366/1920/1024 = 27 枚。横スクロール 0（scrollWidth−clientWidth=0 が 27/27）、ページエラー 0
- 各状態で対象パネルだけ表示、置換系 6 状態で表を非表示、帯系 2 状態で表を表示のまま（computed style で確認）

## 未検証
- 実 System 画面（layouts/system.html の殻）への組込み。各 System の取込待ち
- 実 API の 403/409 応答からの fromResponse（関数単体のみ・実応答では未実行）
- beforeunload（タブを閉じる・再読込）のダイアログ。ヘッドレスでは未確認
- 768 幅未満・印刷。pytest/lint は指示により未実行

## 変更要求
- CR-C3-001（web/__init__.py に dev_states 登録）
