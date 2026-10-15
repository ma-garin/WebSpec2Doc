# A 担当（DD-001/002/003/009/010）
- 作成: web/services/impact/{db,roles,report,migrate}.py、repo/{__init__,errors,systems,documents,baselines,links,crs,impacts,approvals,actuals,audit}.py、tests/test_impact_repo.py（追加契約 db_path・links.list・audit の cr_code・systems.get の members/counts・items の document_name/kind・crs.get の changes・impacts の JSON 展開を反映）
- テスト: 13 passed in 0.47s（tests/test_impact_repo.py）
- 補った関数: documents.item・baselines.get・crs.set_status（approvals/移行から使う）・impacts.priority_of・roles.effective_actor/role_for/auth_off
- 設計に無い決め: 項目コードは略号（REQ/DSN/SCR/TC/DOC）ごとに対象内で通し番号。文書を差し替えたとき、本文が同じ項目は ID とコードを引き継ぐ（つながりが残る）。CR がレビュー待ち以降なら resolve/override は 409。p1_min/p2_min は 1〜12、段数は 1〜3。actuals.record は承認済み以降だけ。つながり候補は類似度 0.35 以上・上位 3・別の文書どうし、加えて本文中の項目 ID 一致。移行した影響の発生可能性は旧データに無いので 2 固定
- 要判断: 認証オフでは actor が常に "local" なので起票者＝承認者になり、本人不可の規則で承認できない（現状は規則を優先して 403 にしている）
