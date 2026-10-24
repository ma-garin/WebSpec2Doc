# S06 設定画面 DONE（2026-10-24・ポート 8768・認証オフ）

## 通した経路（実データ）
- /docverify#settings → GET /api/docverify/settings → settings_store.load → 既定値＋出典（全項目「既定値」）
- 画面で主要の上限 3 → 保存 → PUT（rev 一致）→ settings.json rev+1 → 再読込で 3・出典「利用者設定」
- 他者更新を模擬（API で rev を進める）→ 画面で保存 → 409 → 状態帯「別の人が先に設定を更新しました…」→「自分の変更を保持して保存」で最新 rev に上書き保存
- curl: rev=0 の古い PUT → 409 {code:conflict, latest}
- curl: 認証オフで役割を送る → 400 no_users「利用者名の記録がないため役割を割り当てられません…」
- 接続を確認: 届かない URL → 状態帯 b-error「接続先に届きませんでした。」＋次の行動 1 行／モック /api/tags → ok「接続できました（モデル 1 件）」／モデル名違い → 「モデル「llama9」が見つかりません」＋次の行動
- API キー: 保存後の応答は「••••5678」のみ。settings.json に平文なし（grep 0 件）・secret.json は 0600
- 判定反映: /api/docverify/v1-a-order-payment/pair/gate → limits {critical:0, major:2}・changed は rule=zero で全 0・理由文に「未対応の警告が 9 件で上限 2 件を超えています」
- 未保存ガード: 未保存のままサイドバー「レビュー一覧」→ 確認ダイアログ → 取消で設定画面に留まる。beforeunload も設定

## 確認した幅（ヘッドレス Chrome）
- 1366×768・1920×1080・1024×660: document と form の横スクロール 0。区分ナビはスクロール後も top 79px で固定。JS 例外 0

## 未検証
- 認証オン時の役割割当（利用者一覧の取得・保存）と tenant 別保存先
- S10 承認規則の実ファイル読込（このツリーには instance/approval_policy.json が無く「既定値」表示のみ確認）
- 実 OpenAI への疎通（キー未所持）。Ollama 実機（使用しない方針）
- pytest・make test・verify-ui・check_clipping は未実行

## 要判断
- 重大度の内部値: 対検査は 重大/警告/提案。設定のキー critical/major/minor に対応づけ、既定表示名は 重大/主要/軽微（対検査画面の表示はまだ旧語のまま）
- 無効にした種別の指摘は判定の件数から除外する扱いにした（一覧からは消さない）
- S10 の設定画面への導線を /admin#approval-policy と仮置き（S10 側の URL 未確定）
- API キーは settings.json でなく同階層 secret.json（0600）に分離

## 変更要求
なし
