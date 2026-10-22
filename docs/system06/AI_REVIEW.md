# System06 AI レビュー（Review Board）

対象: `review_board.py`・`evidence_guard.py`・`confidence.py`、`POST .../review`。
AI は候補を出すだけ。人の判断も決定論の結果も上書きしない。

## 独立 Reviewer

- 12 の専門役: Requirements・QA-Testability・Architecture・Security・Performance・Reliability・UX・Accessibility・Operations・Data・Integration・Observability。
- 役 × 要件 1 件ごとに別々に LLM を呼ぶ。他の役の結論はプロンプトに入れない。
- API は役を指定しない（全 12 役）。`run(reviewers=...)` で絞る口はコードにある。
- 回答は JSON スキーマで受ける。指摘は引用（document_id・行範囲・quote）を持つ必要がある。
- 同じ内容（クライアント名・モデル・役・本文が同一）はプロセス内キャッシュで再送しない。

## 証拠検証（evidence_guard）

| 結果 | 条件 |
|---|---|
| VALID | 全引用が実在する |
| UNSUPPORTED | 引用が 1 件も無い |
| INVALID_EVIDENCE | 文書が無い・行範囲外・quote が指定行に無い |

- 検証は保存済みの原文（`source_texts`）だけで行う。クライアントが渡す本文は使わない。
- 空白を無視して照合する。伏せ字後の文を引用した場合も実在とみなす。
- VALID 以外は一覧から隔離し `unsupported` に入れる（画面は「根拠を確認できないため一覧から除外」）。
- VALID の引用には snippet_hash を付ける。

## 反証探索と却下候補

- 指摘が「未定義・記載なし」系の主張をするとき、対象話題（タイムアウト・認証・ログ等 20 語）を他の行が肯定的に述べていないか探す。
- 反証が見つかった指摘は `dismissed`（dismissed_candidate=true）に分け、本一覧に出さない。

## 確度（confidence）

- 基底 0.05。自己申告は重み 0.15 まで。
- 加点: 直接の引用 +0.35、文書数 +0.08/件（3 まで）、ルール検証 +0.25、他役の同意 +0.07/役（3 まで）。
- 減点: 反証 -0.2/件（3 まで）。直接の引用が無ければ上限 0.4。
- 根拠は confidence_basis に文字列で残る。Review Board では rule_verified は常に False。

## DISPUTED

- 同じ対象（文書・開始行・終了行）に 2 役以上が指摘し、主張（stance）が違うか重大度が 2 段以上離れると DISPUTED。
- 該当する指摘は両方保持し dispute_group を付ける。status は CANDIDATE のまま。

## DEGRADED

| 状況 | 結果 |
|---|---|
| クライアントが無い（送信先 none・設定エラー） | `mode=DEGRADED`、findings 空 |
| 送信がすべて失敗 | `mode=DEGRADED`、findings 空 |
| 成功あり | `mode=AI` |

- DEGRADED でも決定論の分析結果は変わらない。画面は「AI レビューは使えません（決定論の分析のみ）」と出す。
- AI の結果は `review` として保存するだけで、品質スコア・準備状態には入らない（pipeline は `DETERMINISTIC_ONLY`）。

## 送信範囲と同意

- 送るのは要件 1 件の原文（チャンク）だけ。文書全体は送らない。
- 送信前に docverify の `mask` で個人情報等を伏せ字にする。
- 送信先 openai のときは `confirm_send: true` が無いと 409（code `consent_required`）で止まる。画面は同意ダイアログ「文書の一部を外部へ送ります」を出し、「同意して送信」で再実行する。
- 送信先 ollama は社内・ローカル扱いで同意確認は無い。
- 実行は監査ログに記録する（送信先・mode）。
- 権限 op は `finding_edit`。

## OpenAI / Ollama の共通口

- `llm_settings.client_for` が `OpenAICompatClient`（名前・モデル・base URL・キー）を返す。呼び出しは `llm_assist._call` に共通。
- ollama は `<url>/v1`、openai は `https://api.openai.com/v1`。ollama の URL は検証関数を通る。
- 既定モデルは openai が gpt-4o-mini、ollama が qwen2.5:3b。

## 検証状況

- 実 API（OpenAI・Ollama）での検証記録は無い。確認できたのは stub クライアントを想定したコード経路のみ。**実 API は未検証**。
- 12 役 × 要件数の呼び出しになるため、要件が多いと送信回数・時間が増える。件数上限・進捗表示はコードに無い。

関連: [API_CONTRACT.md](API_CONTRACT.md) / [SECURITY_REVIEW.md](SECURITY_REVIEW.md) / [README.md](README.md)
