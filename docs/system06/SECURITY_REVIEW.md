# System06 DocAssure PR1 セキュリティレビュー（読み取り専用・静的）

対象: web/routes/doc_assure.py, web/services/docassure/{store,pipeline,review_board,evidence_guard}.py, static/js/docassure.js
実行による検証は未実施（静的読解のみ）。件数: CRITICAL 0 / HIGH 2 / MEDIUM 5 / LOW 3

## 確認できた良い点
- テナント分離: store._path は docverify.store.doc_dir（scoped_output_dir + 12桁hex検証）経由。ルート側も _IID で二重検証。他テナントの iid・assurance.json には到達できない（assurance.json は doc_dir 配下で同一テナント境界）。
- パストラバーサル: iid は ^[0-9a-f]{12}$ のみ。固定ファイル名。
- 原子的書き込み（mkstemp + os.replace）。
- JS: 文書由来テキスト（raw_text, snippet, reason, section, quote, document_id, requirement_id, title, rule_id, reasons, list 項目, orphans, conflict_id）は全て esc() 経由。url は encodeURIComponent。

## HIGH

### H1. review が LLM 送信の監査記録・送信先ガードを持たない（doc_assure.py:130-154）
既存の doc_verify_ai.py:196-212 は送信ごとに audit.append("llm_send"/"llm_send_failed") を残すが、/api/docassure/.../review は 12 reviewer x 全要件チャンクを外部 LLM へ送るのに、送信先・送信量・成否を perm.record/audit に一切残さない。
再現: 外部プロバイダ設定で POST /review → 監査ログに行が増えない（verify_log で確認）。
追加確認: doc_verify_ai.py:196-203 は destination=="none" で 409、consent_token（送信内容の事前同意）を要求するが、/review は同意トークンも destination=none 判定も無く、client_for が返せば即送信する（利用者が送信内容を確認していない）。
修正: 送信前に destination!=none と consent_token 検証を必須にし、送信前後に audit.append("llm_send", ..., {provider, model, sends, cache_hits, failures}) を追加。disclosures 同意・テナント設定の送信可否チェック（doc_verify_ai と同じ入口関数）を共有する。

### H2. review がクライアント供給の文書本文を根拠検証に使う（doc_assure.py:147-152）
docs は保存済み文書ではなく body.documents の text を信用して guard.validate/counter_evidence に渡す。finding_edit 権限者が任意テキストを渡せば、LLM の捏造引用が「実在する根拠」として VALID になり、逆に反証（counter_evidence）を消せる。evidence_guard の存在意義（根拠の実在確認）が迂回される。上限サイズも無い（H の DoS にもつながる）。
再現: POST /review {"documents":[{"id":"D1","text":"<任意の偽の文>"}]} → 偽文に含まれる quote が VALID。
修正: 本文は常にサーバ保存の文書（insp.passages / analyze 時の documents）から再構築し、リクエストの text は無視する。保存していない場合は analyze 時に保存。

## MEDIUM

### M1. analyze/review/decisions の監査記録が不足（doc_assure.py:48-70, 130-154）
perm.record は decisions のみ（111行）。analyze（上書き保存・decisions 以外の previous_requirements 世代交代）と review（H1）は記録なし。decide の detail も reason/expiry/by を含まず、waiver の期限・理由が監査から追えない。
修正: analyze/review に perm.record("docassure_analyze"/"docassure_review", iid, {件数, mode}) を追加。decide の detail に reason 長・expiry を含める。

### M2. 入力検証の不足（doc_assure.py:34-45, 100-112, 147-152）
- decide: target/reason に長さ上限なし、expiry は型・日付形式未検証（waived で文字列 "x" が通る。期限切れ判定が壊れる）。decisions 配列も上限なしで無限に増える。
- review: documents の件数・文字数に上限なし（analyze の _MAX_DOCS/_MAX_CHARS が未適用）。
- _documents_from: d["text"] が dict/list でも str() されるだけ（許容）。profile の許容値検証なし。
- body が list の JSON（例 `[]`）だと `request.get_json(silent=True) or {}` は [] → {} だが、`[1]` だと .get で AttributeError → 500（analyze:55-56, decide:100-101, review:148）。
再現: POST /decisions body=[1] → 500。POST /decisions {"decision":"waived","reason":"a","expiry":{"a":1}} → 201。
修正: isinstance(body, dict) を検査、target<=200・reason<=2000、expiry は ISO 日付を strptime で検証、review にも件数・文字数上限、decisions 上限。

### M3. 同時更新の喪失（store.py:41-50, doc_assure.py:61-66）
add_decision と analyze は load→save の read-modify-write。ロックも rev 照合もない。analyze 中に入った人の判断が消え得る（監査対象の「人の判断」の喪失）。perm.locked / check_rev が既に存在する。
修正: perm.locked(dir) で囲み、decisions は追記専用の別ファイルにする（analyze が触らない）。

### M4. GET が役割判定なし（doc_assure.py:73-127）
trace/requirements/findings/conflicts/scores/readiness/diff は @_perm.require なし。認証オン時、同一テナントの非参加者でも要件全文・snippet を読める。docverify 側の閲覧方針（参加者のみか）に合わせる必要がある。テナント越境ではない。
修正: 既存 GET の方針を確認し、参加者または TENANT_ADMIN のみに制限（MATRIX に "view" を追加）。

### M5. LLM 応答キャッシュがプロセス全体で共有・無制限（review_board.py:41, 63-66）
_CACHE はテナント非分離・サイズ無制限。キー=プロバイダ|モデル|role|原文 のハッシュで、別テナントが同一原文を送ると他テナントの LLM 応答（原文由来の指摘）が返る（同一原文を知っている前提のため漏えい度は低いが、キャッシュ汚染・メモリ増大あり）。また key に伏せ字前の ch['text'] を使うため、伏せ字設定が変わってもキャッシュが古い送信内容の結果を返す。
修正: キーにテナント slug を含める、LRU 上限（例 1000）、キーは mask 後テキストで作る。

## LOW

### L1. JS で数値/列挙の未エスケープ連結（docassure.js:~115 sv[1]/tt[1], 125, 138）
SEV[x.severity] || ['?', x.severity] と TEST[t] || ['?', t] のフォールバックで、未知の severity/verdict が未エスケープで innerHTML に入る。現状 severity は規則側が列挙・AI 側は _sev で正規化済みのため悪用経路は確認できないが、assurance.json が改ざん/将来の規則で自由文になると XSS。loc.line_start も未エスケープ（数値前提）。
修正: フォールバック値を esc() に通し、line_start は Number() 化。

### L2. 例外・ログ（doc_assure.py:67-69, 144-146）
log.exception は文書全文を出さない（確認済み）。review_board/evidence_guard/pipeline に print/log 出力なし。LLM 例外は型名のみ（llm_assist._call）。問題なし。ただし review の LLM 設定例外時（144-146）は client=None で黙って DEGRADED になり、利用者に原因が伝わらない。

### L3. review のコスト増幅（review_board.run）
12 reviewer x 全要件 の逐次呼び出し、各 timeout 30 秒、レート制限なし。finding_edit 権限者の連打で LLM 費用・ワーカ占有。修正: 要件数上限、reviewer 指定、同一 iid の同時実行ロック、rate limit。

## LLM 送信範囲の評価（観点4）
- 送信は要件チャンク単位（raw_text）のみで全文は送らない。他 Reviewer の結論は渡さない。送信前に llm_assist.mask() を通す（review_board.py:_prompt）。良好。
- ただし document_id（クライアント供給の任意文字列）がプロンプトに無加工で入る（プロンプトインジェクション/機密混入の経路。M2 と同じ長さ・形式制限で対処）。
- 文書本文中の指示文によるプロンプトインジェクションは出力が CANDIDATE 固定・evidence_guard 検証済みのため影響は限定的（ただし H2 で迂回可）。
