# 監査 A: 指揮（/orchestration）と共通部品

対象: 共通シェル（パンくず・サイドバー・EvidenceDrawer・status 記号）、指揮ホーム、個別実行詳細、/systems。
方法: PORT 8772 の実画面。指揮は API 応答を page.route で差し替えて Running / Failed / 人の対応 / 承認待ちを再現。

## 10 軸 Before / After

| 軸 | Before | After | 根拠（After） |
|---|---|---|---|
| 1 IA | 3 | 4 | 保存ビュー 4 本・KPI・一覧・詳細の順で並ぶ |
| 2 Golden Path | 3 | 4 | KPI→絞り込み→行の根拠→各 System の流れが通った |
| 3 states | 3 | 4 | 取得失敗→再読み込みで 4 行復帰。0 件・4 状態を確認 |
| 4 Truth・Evidence | 2 | 4 | 行から 7 節＋「なぜこの状態か」が開く |
| 5 permission・safety | 3 | 4 | 一般ユーザーは操作ボタン・サイト追加が非表示。403 は日本語＋次の行動 |
| 6 accessibility | 3 | 4 | Esc 閉じ・focus 復帰・focus 枠 2px を確認 |
| 7 responsive | 2 | 4 | 816px でシステム名が表示。横スクロール 0 |
| 8 visual consistency | 2 | 3 | パンくず統一。ただし個別 System 側が未修正 |
| 9 performance・feedback | 3 | 3 | 取得失敗は帯で通知。計測は未実施 |
| 10 maintainability | 2 | 4 | 指揮ホームを別ファイル化（308 行／999 行） |

平均 3.8。P0 軸（GP・Truth・permission）は 4。Truth 違反は確認範囲で 0。

## 直したもの
- パンくずを「WebSpec2Doc / 画面 / 子」に統一。`WS2D.crumb.set(trail, links)` を追加。既存 JS が書いた内容は `WS2D.crumb.normalize` が区切り「›」→「/」・先頭 WebSpec2Doc を補う（MutationObserver）。
- 816px の折りたたみサイドバーで、システム名が消えて「切替」だけだった。今のシステム名を 2 行で表示。nav 項目の幅も全幅に。
- status の記号を日本語フォントで化けにくい文字に変更（準備中「…」・未確認「△」・利用不可「－」）。
- EvidenceDrawer を 主張→実測→推論→制限→出典→位置→Provider/version の 7 節に分割。冒頭に「なぜこの状態か」行。旧形式の sources はラベルで自動振り分け。
- 指揮ホームの各行に「根拠」ボタン（ドロワー）。状態名は内部コードでなく日本語。
- 動かない KPI（正常・実行中）のクリックを外した（押しても「すべて」に戻るだけだった）。
- 個別実行詳細: 二重のパンくずを 1 本に（「指揮 / 個別実行詳細」）。戻るリンクは残した。
- orchestration.js を分割: 個別詳細 `orchestration.js`、ホーム `orchestration-home.js`（テンプレートが mode で読み分け）。分割前後で既存 28 テスト通過。

## 確認した実画面
- 保存ビュー: 人の対応待ち 2 件・失敗 1 件・未確認 4 件（差し替えデータ）。
- 個別詳細: running / failed / login（人の対応）/ approve_stage（承認待ち）が JS エラー無しで描画。
- /systems: 11 カード（指揮・01・01 app・02〜09）の名称・番号・遷移先がすべて 200。
- 横スクロール 0・見切れ 0・ネイティブ a11y 違反 0・禁止語 0（816/1024/1280/1440/1920、3 画面）。

## 各担当で呼び替え（個別ファイルは触っていない）
- `static/js/core.js` setHeader（/dashboard・/doc-app・/auto-run）: 「WebSpec2Doc / ダッシュボード / …」になる。`WS2D.crumb.set` への置換が望ましい。
- `static/js/backend-test.js` renderTop: 「WebSpec2Doc / ホーム」。System 名（バックエンドテスト）が入っていない。
- `static/js/ta2/ws-schedule.js:119`: 「◔」が残っている。`WS2D.status` の文字＋形に。
- /doc-app・/auto-run 等は `.vp-breadcrumb`（観点のパンくず）が別にある。混同しないこと。

## 権限の実確認（認証オン・一時 auth.db）
- 一般ユーザー: 個別詳細で操作ボタンなし・「操作は管理者が行います」。ホームの「サイトを追加」を非表示（直した）。API 直叩きは 403「この操作には管理者権限が必要です。」。
- 管理者: 操作ボタン表示。403 を差し替えると「この操作には管理者権限が必要です。　管理者に依頼してください。」（401・5xx も次の行動付きに直した。HTML 応答でも落ちない）。
- ホームの取得失敗: 「再読み込み」で復帰。0 サイト: 空状態（一般ユーザーには管理者へ依頼と案内）。

## 共通の残り 2 件
- `.c-reason[hidden]`: /dashboard・/doc-app・/sites/localhost:8791/spec・/batch-test の 816/1024/1280/1440/1920 で、hidden な理由行の display は none（audit.py 再実行で hiddenReasonShown 0）。共通側 c-hybrid.css の `.c-reason[hidden]{display:none}` が効いている。B1 の検出は更新前の CSS を読んだ可能性があり、現状は再現せず。個別 CSS（doc-app.css）にも同旨の対策あり。
- /batch-test の書き出し済み枠: 状態 preparing の記号「…」が小さく余白だけに見えた。「◎」に変更。11 状態すべての記号が見える（実画面で確認）。

## 未確認・残件
- 実データでの Running は未確認（差し替えで代替）。
- /systems の 00 カードのラベルは「まとめ役」（番号表記なし）。
- vitest は未実行（JS 単体テストは指揮に無し）。pytest 28 件通過。
- スクショ: `docs/research/gui-commercial-v4/screens/A-*.png`（home-mock・drawer・home-816・detail-failed）。
