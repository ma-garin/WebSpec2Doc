# WS2D-DD-006 詳細設計書 System 06「ドキュメント検証」R2

- 文書ID: WS2D-DD-006 / 版数: 0.1（草案・未承認） / 作成日: 2026-10-15 / 作成者: 開発チーム / 承認者: 未承認（保守者が記入する）
- 準拠: IPA 共通フレーム（ソフトウェア詳細設計相当）。テスト観点は ISTQB CTFL のテストレベル（単体・結合・システム）で分け、受入基準（RD-006 の G/W/T）から導く
- 上位文書: WS2D-RD-006 要件定義書（R2 の範囲は 12 章のリリース表）。BD-006 の R2 版は未作成（要判断 1）
- 範囲: FR-06-110〜118、SCR-06-05・09・11（SCR-06-12 監査ログ画面を設定画面内に含む）、NFR-06-01〜04・11・13・20・23・25。FR-06-077・078（削除・テナント消去）と NFR-06-21・22 の全面適用は含めない

## 1. ファイル一覧

**ファイル間の契約（関数名・JSON キー・DOM の id）は本書で固定する。**既存の共有ファイルは編集せず、結線は 7 章の 3 行だけ。

| # | ファイル | 区分 | 依存 | 節 |
|---|---|---|---|---|
| G1 | `web/services/docverify/llm_assist.py` | 新規 | なし | 2 |
| G2 | `web/services/docverify/llm_settings.py` | 新規 | `src/llm/openai_client.request_structured_json` | 3 |
| G3 | `web/services/docverify/audit.py` | 新規 | なし | 4 |
| G4 | `web/routes/doc_verify_r2.py` | 新規 | G1〜G3・既存 `store`・`metrics`・`settings.current_user` | 5 |
| G5 | `static/js/docverify-r2.js` | 新規 | `window.DV` の公開物・既存 `#dv-modal`・`#dvgSettings` | 6 |
| G6 | `tests/test_docverify_r2.py` | 新規 | G1〜G4 | 8 |
| — | `templates/docverify/_r2.html` | 作らない | DOM は G5 が挿入する | — |

共通の規約は R1 1 章と同じ（関数 50 行未満・ファイル 400 行以内・入力を変更せず新しい dict を返す・利用者向けの文は 9 章の文だけ）。

## 2. G1 `llm_assist.py` — 伏せ字・説明・揺れ・時間切れ

| 公開 | 引数 → 戻り値 | 内容 | ID |
|---|---|---|---|
| `KINDS` | `tuple[str]` | `email, phone, postal, url_query, api_key, my_number, card, ip` | FR-06-113 |
| `find(text, extra=None) -> list[dict]` | `[{kind,start,end}]`（元の文の位置） | 利用者の範囲（`manual`）を先に取り、残りを優先順 `url_query → email → api_key → card → my_number → phone → postal → ip` で重ならないように取る | FR-06-113 |
| `word_ranges(text, words) -> list[[s,e]]` | 送信前確認で足す語 → 範囲 | 同じ語は全出現を伏せる | FR-06-113 |
| `mask(text, extra=None) -> dict` | `{"text","spans":[{kind,start,end}],"counts":{kind:n}}` | 伏せ字は `［メール］` 等（`LABELS`）。`spans` は伏せ字後の位置（画面で強調する） | FR-06-112・113 |
| `luhn(digits) -> bool` | 13〜19 桁で判定 | カード番号は Luhn が通るものだけ | FR-06-113 |
| `source_text(insp, finding) -> str` | 規則・候補の文・引用・断片の全文 | 送る元の文 | FR-06-110 |
| `explain(client, masked, *, with_wobble=False, timeout=None, cancel=None) -> dict` | 9 章 JSON `ai` | 理由は `three_sentences` で 3 文まで。指摘の状態は変えない | FR-06-110・116 |
| `judge_wobble(list[str]) -> dict` | `{"interpretations","max_similarity","split"}` | NFKC・小文字化・空白と句読点を除いて `difflib.SequenceMatcher.ratio`。どの組も 0.8 未満なら `split: true` | FR-06-116 |
| `run_with_timeout(fn, timeout, cancel) ` | 値 / `AssistTimeout` / `AssistCancelled` | 別スレッドで実行し 0.1 秒ごとにキャンセルを見る | NFR-06-11 |
| `TIMEOUT_SEC = 60.0`・`SIMILARITY = 0.8`・`WOBBLE_RUNS = 3` | 定数 | 暫定（要確認-7・R5 で見直す） | NFR-06-11・FR-06-116 |
| 例外 `AssistError` ⊃ `AssistTimeout`・`AssistCancelled` | — | 接続不可・応答不正・HTTP エラーはすべて `AssistError` に包む | FR-06-115 |

伏せ字の検出規則:

| 種類 | 規則 |
|---|---|
| email | `local@domain.tld` |
| phone | `0` 始まりのハイフン区切り・`0[5789]0` の 11 桁・`0` 始まり 10 桁・`+81` 形式 |
| postal | `〒`（任意）＋ `NNN-NNNN` |
| url_query | URL の `?`・`&` の後の `名前=値` の値の部分だけ |
| api_key | 接頭辞 `sk-`・`sk-proj-`・`ghp_`・`github_pat_`・`AKIA`・`AIza`・`xox?-`、または 32 字以上の英数字列 |
| my_number | 12 桁（4 桁ずつの空白・ハイフン区切りを含む） |
| card | 13〜19 桁（空白・ハイフン区切り可）で Luhn が通るもの |
| ip | IPv4（各 0〜255） |

LLM の呼び出し口（Protocol `LLMClient`）: `name: str`・`model: str`・`request(prompt, schema_name, schema, timeout_sec) -> dict`。スキーマは `EXPLAIN_SCHEMA`（`reason`・`rewrite`・`open_questions`）と `INTERPRET_SCHEMA`（`interpretation`）。温度 0 は既存 `request_structured_json` の既定（payload の `temperature: 0`）に依る。

## 3. G2 `llm_settings.py` — 送信先・接続先・説明文

| 公開 | 内容 | ID |
|---|---|---|
| `DESTINATIONS` | `("none","openai","ollama")`。`load()` の初期値は `none` | FR-06-111 |
| `load() -> dict` | `{"destination","openai_model","ollama_url","ollama_model"}`。保存先 `<DATA_DIR>/(tenant)/docverify/_llm_settings.json` | FR-06-111 |
| `save(body, probe=None) -> dict` | 送信先を検証して保存。Ollama は `validate_ollama_url` → `check_ollama`（`/api/tags`、3 秒）。届かなければ `ConnectionError(OLLAMA_DOWN)` で保存しない | FR-06-111・NFR-06-23 |
| `validate_ollama_url(url) -> str` | http/https・利用者情報なし・ホストは `localhost` か IPv4 の 127/8・10/8・172.16/12・192.168/16。169.254/16 と製品自身のポート（8765・`WEBSPEC2DOC_PORT`・`PORT`）は拒否。ホスト名は `localhost` 以外を拒否（DNS で社外へ向く経路を作らない） | NFR-06-23 |
| `disclosures() -> dict` | 送信先ごと `{name,location,training,retention,source,retrieved}`。`_llm_disclosures.json` で上書きできるが、`source` と `retrieved` が両方ある上書きだけ使う。初期値は E4 §2.6（取得日 2026-10-15） | NFR-06-01・02 |
| `client_for(cfg)` | `none` と API キーの無い OpenAI は `None`。Ollama は `<url>/v1` へ、OpenAI は `https://api.openai.com/v1` へ送る `OpenAICompatClient` | FR-06-111・NFR-06-20 |
| `OpenAICompatClient.request` | 既存 `request_structured_json(..., base_url=..., purpose="docverify_explain")` を呼ぶ（アクティビティログにも残る） | NFR-06-20 |

## 4. G3 `audit.py` — 監査ログ

- 保存先 `<DATA_DIR>/(tenant)/docverify/_audit.jsonl`。1 行 `{"at","user","action","target","detail"}`。追記のみ
- `ACTIONS`: `llm_send`（AI へ送信）・`llm_send_failed`（失敗）・`ai_adopt`・`ai_reject`・`ai_question`（質問票へ送る）・`llm_settings`（送信先の変更）
- `append(action, user, target, detail)`・`read_all()`・`query(since, until, user, action)`（日付は両端を含む・新しい順）・`count(action)`・`describe(row)`・`to_csv(rows)`（BOM 付き、見出し `日時,利用者,操作,対象,内容`、`= + - @` 始まりは `'` を前置）
- 保持期間は要確認-5 のため本版は自動で消さない（NFR-06-03 の削除は FR-06-077・078 の担当）

## 5. G4 `doc_verify_r2.py` — API（Blueprint `doc_verify_r2`）

| メソッド・パス | 入力 | 出力（成功） | 失敗 |
|---|---|---|---|
| GET `/api/docverify/r2/llm-settings` | — | `{settings, destination, disclosures, can_edit}` | — |
| POST `/api/docverify/r2/llm-settings` | `{destination, ollama_url?, ollama_model?, openai_model?}` | 同上 | 403 M-R2-12・400 検証文・500 M-R2-13 |
| POST `.../inspections/<iid>/findings/<fid>/ai/preview` | `{extra_masks?: [[s,e]], extra_words?: [str], with_wobble?: bool}` | `{destination, masked, sends, with_wobble, consent_token, expires_in, timeout_sec}`。**送らない** | 404・409 M-R2-01・400 |
| POST `.../ai/explain` | `{consent_token}` | `{inspection, summary, ai}` | 400 M-R2-06・503 M-R2-02/03・504 M-R2-04・409 M-R2-05 |
| POST `/api/docverify/r2/ai/cancel` | `{consent_token}` | `{cancelled: bool}` | — |
| POST `.../ai/decision` | `{decision: "adopt"\|"reject"}` | `{inspection, summary}` | 400 M-R2-08・M-R2-09 |
| POST `.../ai/questions` | `{indexes: [int]}` | 201 `{inspection, summary, added}` | 400 M-R2-08・M-R2-10 |
| GET `/api/docverify/r2/audit` | `?since&until&user&action` | `{rows:[…, action_label, summary], users, actions}` | 403 M-R2-11・400 |
| GET `/api/docverify/r2/audit.csv` | 同上 | CSV（画面と同じ行） | 403 M-R2-11 |

同意トークン: `preview` が発行（`secrets.token_urlsafe(24)`、10 分で失効、プロセス内メモリ）。`iid`・`fid`・伏せ字後の文・送信先・揺れの有無・利用者に結びつけ、`explain` で 1 回だけ使える。送信先が変わっていたら無効。`explain` は承諾済みの文だけを送る（承諾までは送信 0 件）。

権限: 認証オフ（`g.auth_user` なし）は全許可（RD-006 8.2 注記）。送信先の変更はテナント管理者（`role == "admin"`）。監査ログはテナント管理者か、いずれかの検査で承認者（`participants[].role == "approver"`）の利用者。

採否: 採用は `finding.disposition = "AI 提案を採用: <書き換え案>"` と `ai.adopted = true`。`status`・`passages`・`document` は変えない（FR-06-114・118）。
質問票へ送る: 選んだ未決定事項ごとに `certainty: "要確認"`・`status: "candidate"`・`origin: "ai"`・`rule: "AI_QUESTION"` の指摘を足す。既存 `questions.build` がそのまま質問票に載せる。送り済みの番号は `ai.sent_questions` に残し、二重に足さない。

## 6. G5 `docverify-r2.js` — 画面

| 部品 | 内容 | ID |
|---|---|---|
| 「AI の説明を見る」 | `[data-fa="ask"][data-fid]` の並び（指摘カード）と `tr[data-fid]`（指摘の表）に `button[data-r2="explain"]` を足す。`MutationObserver` で描き直し後も足す | SCR-06-05 |
| 送信前確認 | 既存 `DV.modal`（`#dv-modal`）。送信先・所在・学習利用・保持期間・出典と取得日・送信回数・実際に送る文（`<mark>` で伏せ字を強調）。伏せる語の追加と揺れの有無は「伏せ字と送信回数を反映」で preview を取り直す。「取りやめる」でトークンを破棄 | SCR-06-11・FR-06-112 |
| 作成中 | 「AI の説明を作っています」モーダル。「取りやめる」で `/ai/cancel` | NFR-06-11 |
| AI の提案 | `AI の提案` の札・送信先とモデル・理由・書き換え案・「解釈が分かれます」・未決定事項の選択。「採用する」「不採用にする」「選んだ事項を質問票へ送る」 | FR-06-114・116・117 |
| 設定画面 | `#dvgSettings` の直後に `section#dv-r2-settings`（`#dv-r2-llm`・`#dv-r2-audit`）。送信先の選択・Ollama の接続先とモデル・所在・学習利用・保持・出典。管理者以外は入力不可 | SCR-06-09・NFR-06-01・02 |
| 監査ログ | 期間・利用者・操作の絞り込み、表、「CSV で出す」（`DV.download`）。403 は権限の文を表示 | SCR-06-12・NFR-06-25 |

公開: `DV.r2 = {decorate, explain, renderSettings}`。

## 7. 結線（共有ファイルの担当が足す）

`scratchpad/wire_R2.txt` に正確な行を記載: ①`web/__init__.py` に import と `app.register_blueprint(doc_verify_r2.bp)` ②`templates/doc_verify.html` の review.js の次に `docverify-r2.js` の script ③`web/routes/doc_verify.py` の `dv_ver` 対象に `js/docverify-r2.js`。

## 9. JSON と文言

`finding.ai`（RD-006 データ表「指摘の AI 提案」）: `{"label":"AI の提案","provider","model","explanation","rewrite","open_questions":[],"generated_at","input_sha256","adopted":null|true|false,"wobble":null|{…},"decided_by?","decided_at?","sent_questions?"}`

| ID | 文 |
|---|---|
| M-R2-01 | AI の説明は使わない設定です。テナント管理者が設定で送信先を選ぶと使えます。 |
| M-R2-02 | OpenAI のキーが設定されていません。管理者にキーの設定を依頼してください。規則の指摘はそのまま使えます。 |
| M-R2-03 | AI の説明を作れませんでした。規則の指摘はそのまま使えます。時間をおいてもう一度試してください。 |
| M-R2-04 | AI の説明を作れませんでした（60 秒以内に返りませんでした）。規則の指摘はそのまま使えます。時間をおいてもう一度試してください。 |
| M-R2-05 | AI の説明を取りやめました。規則の指摘はそのまま使えます。 |
| M-R2-06 | 送信の確認が切れました。「AI の説明を見る」からやり直してください。 |
| M-R2-07 | 指摘が見つかりません。画面を再読み込みしてください。 |
| M-R2-08 | AI の提案がまだありません。先に「AI の説明を見る」を押してください。 |
| M-R2-09 | 採用か不採用を選んでください。 |
| M-R2-10 | 質問票に送る事項を選んでください。 |
| M-R2-11 | 監査ログを見る権限がありません。テナント管理者か承認者に依頼してください。 |
| M-R2-12 | 送信先を変えられるのはテナント管理者です。テナント管理者に依頼してください。 |
| M-R2-13 | 設定を保存できませんでした。もう一度保存してください。 |
| M-R2-14 | Ollama に接続できません。起動とアドレスを確かめてください。 |
| M-R2-15 | この接続先は使えません。使える接続先は localhost・127.0.0.1・10.0.0.0/8・172.16.0.0/12・192.168.0.0/16 です（169.254.0.0/16 と本製品のポートは使えません）。アドレスを直してください。 |

## 8. テスト（`tests/test_docverify_r2.py`。LLM は `OpenAICompatClient.request` のスタブ）

| ID | テスト関数 | 受入基準 |
|---|---|---|
| UT-06R2-01 | `test_mask_recall_per_kind`（8 種×評価セット） | FR-06-113 再現率 0.95 以上 |
| UT-06R2-02 | `test_mask_removes_email_and_marks_span` | FR-06-113 アドレスが無く伏せ字がある |
| UT-06R2-03 | `test_card_requires_luhn_and_manual_range` | FR-06-113 Luhn・利用者の追加 |
| UT-06R2-04 | `test_wobble_split_and_not_split` | FR-06-116 |
| UT-06R2-05 | `test_three_sentences_and_timeout_cancel` | FR-06-110 3 文・NFR-06-11 |
| UT-06R2-06 | `test_ollama_url_rejected` / `test_ollama_url_allowed` | NFR-06-23 |
| UT-06R2-07 | `test_disclosure_override_needs_source` | NFR-06-02 |
| UT-06R2-08 | `test_audit_csv_formula_guard` | NFR-06-25 |
| IT-06R2-01 | `test_default_none_and_zero_sends` | FR-06-111 初期値・NFR-06-20 |
| IT-06R2-02 | `test_settings_show_location_and_training_per_destination` | NFR-06-01・02 |
| IT-06R2-03 | `test_ollama_down_is_not_saved` | FR-06-111 停止中の Ollama |
| IT-06R2-04 | `test_link_local_rejected_and_loopback_saved` | NFR-06-23 |
| IT-06R2-05 | `test_only_admin_can_change_destination` | RD-006 8.2 |
| IT-06R2-06 | `test_preview_has_five_items_and_sends_nothing` | FR-06-112・NFR-06-01 |
| IT-06R2-07 | `test_explain_with_ollama_only_and_state_unchanged` | FR-06-110・111・113 |
| IT-06R2-08 | `test_consent_token_is_single_use` | FR-06-112 |
| IT-06R2-09 | `test_failure_degrades_and_other_ops_continue` | FR-06-115・NFR-06-13 |
| IT-06R2-10 | `test_timeout_is_user_readable` | NFR-06-11 |
| IT-06R2-11 | `test_wobble_flag` | FR-06-116 |
| IT-06R2-12 | `test_adopt_records_and_keeps_original` | FR-06-114・118・NFR-06-04 |
| IT-06R2-13 | `test_decision_without_ai_is_rejected` | FR-06-114 |
| IT-06R2-14 | `test_send_one_question_adds_one_row` | FR-06-117 |
| IT-06R2-15 | `test_audit_filter_csv_and_permission` | NFR-06-25 |
| ST-06R2-01 | 画面（送信前確認・作成中・提案・設定・監査ログ）を Playwright で全状態を開く | SCR-06-05・09・11・12。**未実行** |

## 10. トレース表

| 要件 ID | DD の節 | 実装 | テスト |
|---|---|---|---|
| FR-06-110 | 2・5・6 | G1・G4・G5 | UT-05・IT-07 |
| FR-06-111 | 3・5・6 | G2・G4・G5 | IT-01・03・05・07 |
| FR-06-112 | 5・6 | G4・G5 | IT-06・08 |
| FR-06-113 | 2 | G1・G4・G5 | UT-01〜03・IT-07 |
| FR-06-114 | 5・6 | G4・G5 | IT-12・13 |
| FR-06-115 | 2・5・9 | G1・G4・G5 | IT-09 |
| FR-06-116 | 2・6 | G1・G5 | UT-04・IT-11 |
| FR-06-117 | 5・6 | G4・G5 | IT-14 |
| FR-06-118 | 5 | G4 | IT-12 |
| SCR-06-05・09・11・12 | 6 | G5 | ST-01（未実行） |
| NFR-06-01・02 | 3・6 | G2・G5 | UT-07・IT-02・06 |
| NFR-06-03 | 4 | G3（保持は要確認-5） | — |
| NFR-06-04 | 4・5 | G3・G4 | IT-12 |
| NFR-06-11 | 2・5・6 | G1・G4・G5 | UT-05・IT-10 |
| NFR-06-13 | 5 | G4 | IT-09 |
| NFR-06-20 | 3・5 | G2・G4 | IT-01・07 |
| NFR-06-23 | 3 | G2 | UT-06・IT-04 |
| NFR-06-25 | 4・5・6 | G3・G4・G5 | UT-08・IT-15 |

## 11. 要判断

1. BD-006 の R2 版が無いまま DD を書いた（上位の基本設計を後から作るか、本書で代えるか）
2. 未決定事項を質問票へ送る方式: `questions.py` を変えず、要確認の候補指摘（`origin: "ai"`）として足した。指摘一覧にも候補として出る。別の欄で持つなら `questions.build` の変更が要る
3. 承認者の判定: 「いずれかの検査で承認者として登録された利用者」とした。テナント単位の承認者役割は現行に無い
4. 揺れの検出は説明と同じ承諾で追加 3 回送る（送信前確認に回数を出す）。既定はオフ
5. 同意トークンはプロセス内メモリ。複数プロセスで動かす構成では共有されない
6. 監査ログの保持期間・自動削除は要確認-5 待ちで未実装
