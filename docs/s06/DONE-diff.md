# S06 版差分と再レビュー（修正版の確認）DONE

## 変更
- web/services/docverify/pair_versions.py（新規）: 新版の取り込み・章差分・指摘の再計算
- web/routes/doc_verify_pair.py: `POST /versions`・`GET /diff` を _RULES に追加
- templates/docverify/_followup.html（新規）・static/js/docverify-followup.js（新規）・static/css/docverify-followup.css（新規）
- templates/doc_verify.html: 上記 partial の include と css/js の読み込みだけ（3 行）

## API
- `POST /api/docverify/<iid>/pair/versions`（multipart `requirements` / `design` のどちらか・両方、任意 `rev`）
  - 旧版を `pair/docs/history/v<旧版>/<name>` に退避 → 新版を `pair/docs/` → meta の `req_version`/`design_version` +1
  - Trail `version_uploaded`（例「要件定義書 v1→v2（変わった章 1）」）
  - 変わった章（## 単位。指摘の req_ref/design_ref と同じ粒度、見出しの変更も含む）で `changed_in_current` を全件再計算し、
    今回変わった章に紐づく 採用／解消済み を decisions.json への追記（by=_system, auto=true）で 要確認 に戻す。Trail `finding_reopened`「版 v<n> で該当章が変更（採用→要確認）」
  - 失敗: 400 files_required / empty_file / too_large(2MB) / bad_encoding / no_sections、409 conflict（rev 不一致）
- `GET /api/docverify/<iid>/pair/diff?from=<n>&to=<m>` → `{summary, sections:[{id, heading, change, before_excerpt, after_excerpt, doc}], versions}`
  - 章は ## / ### / 「1.」「1.1」の行で分割。省略時は各文書の 現行版−1 → 現行版。比較できる版が無ければ 404 version_not_found
  - before/after_excerpt は章内の変わった行だけ（difflib、200 字で切る）

## 実データでの確認（8772・A_order_payment を seed）
1. seed → V1-A-01 を 採用 → 要件書の 5 章（REQ-A-008 24→48 時間、REQ-A-010 30→60 秒）を書き換えた v2 を curl で投入
2. 応答: req_version 2・changed_sections.requirements=["s5"]・reopened=["V1-A-01"]・差分は s5「変更」1 件、要約「要件定義書は v1→v2 で 1 章が変わりました（変更 1・追加 0・削除 0）。」
3. findings: V1-A-01=要確認（changed_in_current）。gate: changed.pass=false・needs_review=["V1-A-01"]
4. Trail: finding_decided → version_uploaded → finding_reopened（理由「版 v2 で該当章が変更（採用→要確認）」）
5. 画面（Chrome headless・Playwright）: 1440/1180/1024 で横スクロール 0・内部のはみ出し 0、旧 followup 節は display:none、表示中の dv-view は新節のみ。
   壊れたファイル（非 UTF-8）でエラー文表示 → 正しい設計書を画面から投入して「取り込みました」・版表示更新 →
   「対検査で今回の変更分を開く」で対検査の changed チップ aria-pressed=true・2 件表示・判定帯「今回の変更分 不合格」

## 要判断
- 検証手順の「今回の変更分 1」は実データでは 2 になる。V1-A-05 も要件 s5（REQ-A-008/009）を参照するため（未判定なので要確認には戻さず、変更分には入る）。要確認へ戻るのは V1-A-01 の 1 件だけ
- 「要件書の 5 章」は「第 5 章 1 つ」と解釈した（5 章ぶんの変更ではない）
- 「今回の変更分」の範囲: 片方の文書だけ上げたとき、もう一方の前回の変更章は保持する（上書きすると設計書だけ直した時点で要件側の変更分が消えて合格になるため）。要確認へ戻すのは今回上げた文書の変更章だけ
- 同じ内容を再投入しても版は上がる（変わった章 0 として記録）
- 「1.」「1.1」形式の見出し判定は行頭の番号で行う。本文中の番号付き箇条書きも章として数える

## 未検証
- pytest・make test・verify-ui・check_clipping.py は未実行（指示により pytest 禁止）
- 認証オン時の取り込み、rev 409 の画面表示、2MB 超・章なしファイルの画面表示
- 旧 _review.html の followup 節の描画（docverify-review.js）は非表示のまま裏で走る。無駄な API 呼び出しの有無は未確認
- 旧版の履歴一覧 UI は無い（diff の from/to を API で指定すれば比較できる）
