# C0 DONE（2026-10-24）

## 通した経路
- /docverify・/orchestration・/test-automation・/settings/api・/backend-test・/batch-test → layouts/system.html（css/tokens.css 読込で --fs-13=13px を実測）→ 1920×1080・1366×768・1024×660 で横スクロール 0、サイドバー・上部バーのはみ出し 0、システム切替の折れ 0。
- スロット見本（render_template_string で layout を extends、?case=C-12&tv=v3）→ 3 幅で横スクロール 0。1024 幅: 本文 508px・右パネル 260px・判定帯 69px 高。上部バー「案件 C-12 版 v3」。data-state=error でエラーバナー表示。右パネル「閉じる」→ is-collapsed・localStorage ws2d.rpanel.docverify=collapsed。
- 撮影: scratchpad/c0shots/*.png

## 未検証
- /settings/general は 404（web/routes/pages.py の _SETTINGS_TABS に general が無い）。代わりに /settings/api で確認。
- 「1024 幅でシステム切替が縦に折れる」は HEAD(404123d) で再現せず。全殻変種へ nowrap を広げる防御のみ。
- 状態 9 種のうち実画面での表示は error のみ確認（他 8 種は CSS セレクタのみ）。ui-states.js への 4 関数追加は所有外。
- 案件名・版の表示名解決（§3 API）は未接続。現在は URL の id を表示。
- 1024×660 で既定 nav の長い System はサイドバー foot が下端で切れる（既存挙動。未対応）。
- pytest・verify-ui・check_clipping は未実行。

## 変更要求
- なし（S06 等が ui-states.js に権限不足・未保存・競合・復元の関数を要する場合は所有者へ）。
