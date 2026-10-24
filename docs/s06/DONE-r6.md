# S06 r6 検査未実行→判定不能への追従（2026-10-24）
- 規則: pair_review._judge は assessment 無し／status!=complete を判定不能にする。実装修正は不要
- smoke: 検査前の判定 → analyze → 採否 → 採用は解消済みまで進める → gate 合格。8770 で OK=43 / NG=0
  - 解消済みを足した理由: 採用は未解消扱いで、警告上限(設定 major=3)を超え合格しないため
  - 8770 は WEBSPEC2DOC_DOCVERIFY_SEMANTIC=off で起動（LLM 未設定だと semantic 未実行で assessment が unverified のまま。規則どおり）
- UI: 案件一覧の判定不能(検査未実行)行に副ボタン「検査を実行」→ analyze → 再読込。対検査の判定帯にも同ボタン（主ボタンは「承認へ」のまま）
- 確認: r-dd9e087846 の analyze で 判定不能→不合格（API）。ブラウザ上のクリック操作は未検証
