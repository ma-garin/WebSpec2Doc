# S06 AI 検査の範囲外扱い (feat/s06-ai-scope)
- AI 送信先「使わない」: semantic 検査を実行せず assessment.scope={"ai":"out_of_scope"}。未検証に数えない。openai/ollama で失敗は従来どおり未検証→判定不能。
- 根拠・判定帯・案件一覧・指摘書(md/docx/xlsx)に「AI 検査は設定により範囲外（ルール検査のみで判定）」。
- D-25: 判定と記録の証跡に絞り込みチップ（すべて/採否/承認・差し戻し）。_cases.html の隠し h2 を削除。
- 契約テスト 2 件追加、unittest 9 件 OK。8773 で seed→analyze→全不採用→gate 合格＋範囲外行を確認。smoke 再 seed 後の結果は下記。
- 未検証: 画面の目視（チップ・案件一覧の注記）、docx/xlsx の実出力。
