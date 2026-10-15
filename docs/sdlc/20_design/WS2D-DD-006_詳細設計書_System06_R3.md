# WS2D-DD-006 詳細設計書 System 06「ドキュメント検証」R3

- 文書ID: WS2D-DD-006（R3） / 版数: 0.1（草案・未承認） / 作成日: 2026-10-15 / 作成者: 開発チーム / 承認者: 未承認（保守者が記入する）
- 準拠: IPA 共通フレーム（ソフトウェア詳細設計相当）。テスト観点は ISTQB CTFL のテストレベル（単体・結合）で分け、受入基準（RD-006 の G/W/T）から導く
- 上位文書: WS2D-RD-006 要件定義書 11 章 R3・WS2D-DD-006 R1
- 範囲: FR-06-016〜018・025〜027・120〜123（123 は集合の検査）・130〜135、SCR-06-07

## 1. ファイル一覧

| # | ファイル | 区分 | 依存 | 節 |
|---|---|---|---|---|
| G1 | `web/services/docverify/setcheck.py` | 新規 | なし（`web.config`・`web.tenancy` は設定の保存先だけ） | 3 |
| G2 | `web/services/docverify/trace.py` | 新規 | なし | 4 |
| G3 | `web/services/docverify/ingest_r3.py` | 新規 | `ingest.ingest`・`ingest.IngestError` | 5 |
| G4 | `web/routes/doc_verify_r3.py` | 新規（Blueprint `doc_verify_r3`） | G1〜G3・`store`・`checks`・`settings.current_user` | 6 |
| G5 | `templates/docverify/_r3.html` | 新規 | — | 7.1 |
| G6 | `static/js/docverify-r3.js` | 新規 | `window.DV`（core）・G5 の DOM | 7.2 |
| G7 | `static/css/docverify-r3.css` | 新規 | tokens.css の変数だけ | 7.3 |
| G8 | `tests/test_docverify_r3.py` | 新規 | G1〜G4 | 8 |

既存ファイル（`web/__init__.py`・`templates/doc_verify.html`・`static/js/docverify-core.js`・`web/routes/doc_verify.py`）は本リリースの担当では変えない。結線の行は 9 章。

共通の規約は R1 1 章と同じ（関数 50 行未満・ファイル 400 行以内・入力を変更せず新しい dict を返す・CSS は tokens の変数だけ）。

## 2. データ（inspection.json への追加キー）

| キー | 形 | 内容 |
|---|---|---|
| `documents` | `list[dict]` | R3 で登録した文書。`{"id":"D<8桁16進>","name","format","kind","kind_label","passages":[…],"candidates":[…],"tables":[…],"hidden_passages":int,"include_hidden":bool,"uploaded_at","unread",…}` |
| `set_check` | `dict` | `{"pairs":[…],"decisions":{pair_id:{"decision","by","at","finding_id"}},"units","checked_units","truncated","documents","ran_at"}` |
| `trace_format` | `str` | 追跡に使う ID の書式（既定 `REQ`） |

断片の追加キー: `hidden: bool`（FR-06-017）。指摘の追加キー: `type`（「矛盾」「重複」）・`set_pair`・`origin: "set"`。
テナント設定 `docverify/_r3_settings.json`: `{"disabled_rules":[…],"forbidden":[…],"allowed":[…],"synonyms":[{"canonical","variants":[…]}]}`。

## 3. G1 `setcheck.py`

### 3.1 定数（暫定値。R5 の実測で見直す）

| 名前 | 値 | ID |
|---|---|---|
| `DUP_THRESHOLD` | 0.9 | FR-06-120 |
| `NEG_MIN_SIMILARITY` | 0.0（追加条件なし＝RD どおり） | FR-06-121(b) |
| `MAX_UNITS` | 1500（超えた文は検査せず `unchecked` に出す） | — |
| `COVERAGE` | `網羅性: 未検証` | FR-06-123 |
| `EMPTY` | `確認した範囲では指摘はありません。網羅性は未検証です。` | FR-06-123 |
| `RULES` | `INCOMPLETE, OPEN_ENDED, UNIVERSAL, AND_OR, MEASURABILITY, MULTIPLE_REQUIREMENTS, AMBIGUOUS_TERM, AMBIGUOUS`（checks の rule 名の `.` 以降） | FR-06-025 |

### 3.2 公開関数

| 関数 | 引数 → 戻り値 | 内容 | ID |
|---|---|---|---|
| `normalize(text)` | `str` | NFKC（全角半角）→ `，,`→`、`・`．｡`→`。` → 空白除去 → 末尾の `。` を除く | FR-06-120 |
| `ratio(a, b)` | `float` | `1 − 編集距離 / max(len)` | FR-06-120 |
| `units(documents)` | `list[dict]` | 断片を `。！？!?` と改行で文に分ける。`include_hidden` が偽の文書は `hidden` の断片を除く。`key = 文書ID:断片ID:文番号` | FR-06-120・017 |
| `subject(norm)` | `str\|None` | 先頭の番号・記号を除き、`^(.{2,40}?)(は\|が)` の名詞句 | FR-06-121 |
| `contradiction_reason(a, b)` | `str\|None` | (a) 共通の単位（秒・分・件・% 等）の数値の並びが違う (b) 一方だけが否定・禁止（`しない\|できない\|禁止\|不可\|…`） | FR-06-121 |
| `find_pairs(units)` | `list[pair]` | 全組を比べる。同じ主語で矛盾理由があれば `contradiction`、なければ類似度 ≥ 0.9 で `duplicate`（1 組 1 種類・矛盾を優先）。長さ比が 0.9 未満の組は類似度を計算しない | FR-06-120・121 |
| `run(documents, previous)` | 新しい `set_check` | 前回の判断は同じ組 ID（両文の key の SHA-1 先頭 10 桁に `S`）なら引き継ぐ | FR-06-122 |
| `view(set_check)` | 7.2 の JSON | `pairs` に `decision` を付ける。`coverage` は常に `COVERAGE`、0 件なら `empty_message = EMPTY` | FR-06-123 |
| `decide(insp, pair_id, decision, by)` | 新しい検査 | `decision ∈ {contradiction, duplicate, ok}`。矛盾・重複は指摘（`status: adopted`・`type: 矛盾/重複`・`severity: major`・F 番号は既存の最大＋1）を足す。同じ組を判断し直すと既存の指摘を更新し、`ok` なら `rejected` にする。不正値は `ValueError`、無い組は `KeyError` | FR-06-122 |
| `load_settings()` / `save_settings(body)` | `dict` | テナントの規則・語彙。不正な形は `ValueError`（利用者向けの文） | FR-06-025・027 |
| `apply_rules(findings, passages, cfg)` | `list[dict]` | 無効の規則と許容語を含む候補を外し、禁止語の候補 `ORG.FORBIDDEN` を足す | FR-06-025 |
| `term_variants(passages, synonyms)` | `list[dict]` | 標準語と社内語が同じ文書に両方あれば `ORG.TERM_VARIANT`（「用語ゆれ: 「A」と「B」が混在しています。…」） | FR-06-027 |
| `missing_attributes(tables)` | `list[dict]` | 見出しに「要求・要件・REQ」を含む表で、ID・優先度・根拠・検証方法（同義の見出しを含む）の列が無いものを `REQ.MISSING_ATTRIBUTE`（「{列}がありません。…」） | FR-06-026 |

pair の形（固定）: `{"id":"S…","kind":"duplicate|contradiction","similarity":float,"reason":str,"a":{doc_id,doc_name,passage_id,location,text},"b":{…}}`。

## 4. G2 `trace.py`

| 公開 | 内容 | ID |
|---|---|---|
| `KINDS` | `(("requirement","要件"),("design","設計"),("test","テスト"))` | FR-06-130 |
| `FORMATS` | `REQ・FR・NFR・UC・US・SR` の各 `{"id","label":"X-数字","example":"X-001"}` | FR-06-134 |
| `pattern(fmt)` | `(?<![A-Za-z0-9])X-\d+(?![0-9])`。一覧に無い書式は `ValueError` | FR-06-134 |
| `extract(passages, fmt)` | NFKC・大文字化後に抽出。`[{"id","location"}]`（最初の位置） | FR-06-131 |
| `build(documents, fmt)` | 下の JSON | FR-06-131・132・135 |
| `to_xlsx(table)` | シート「追跡表」（見出し 1 行＋rows。空欄は「（対応なし）」）・「完全率と孤立」（網羅性: 未検証 を含む） | FR-06-133 |

`build` の規則: 行は要件文書の ID（番号順）。列は要件＋登録された下流の種別。**完全率 = 登録された下流の種別すべてに対応がある上流 ID の数 / 上流 ID の数**（四捨五入。上流 0 件は `null`）。孤立 = 下流にあって上流に無い ID。ID が 1 件も無い文書は `unreadable` に「この文書から ID を読み取れませんでした。ID の書式を確かめてください。」で入れ、表から外す。要件文書が無ければ `messages` に案内。

```json
{"format":"REQ","columns":[{"kind":"requirement","label":"要件"},{"kind":"design","label":"設計"}],
 "rows":[{"id":"REQ-001","requirement":["要件.txt 1行目"],"design":["設計.txt 1行目"]}],
 "complete":{"covered":2,"total":3,"rate":67},"orphans":[{"id","kind","kind_label","locations"}],
 "unreadable":[{"doc_id","doc","kind","message"}],"messages":[],"coverage":"網羅性: 未検証"}
```

## 5. G3 `ingest_r3.py`

| 関数 | 内容 | ID |
|---|---|---|
| `is_encrypted_office(data, suffix)` | docx/xlsx の先頭 8 バイトが OLE 複合文書の印なら真 | FR-06-018 |
| `ingest_r3(filename, data, work_dir)` | 暗号化なら `IngestError("この文書はパスワードで保護されています。パスワードを外してから取り込んでください。")`（「破損」と言わない）。それ以外は `ingest.ingest` の検査を通した後、xlsx は openpyxl で読み直し、docx は見出し付きの表を行の断片に置き換える。`document` に `tables`・`hidden_passages` を足す。読み直しに失敗したら通常の断片で続ける（`log.warning`） | FR-06-016〜018 |

表の行: 1 行目が 2 列以上の短い文字列（30 字以内）なら見出しとみなし、各行を `見出し: 値／見出し: 値` の 1 断片にする（空のセルは省く）。非表示: 非表示シート・非表示列・非表示行の断片に `hidden: true`。

## 6. G4 `doc_verify_r3.py`（Blueprint `doc_verify_r3`）

| メソッド・パス | 入力 | 応答 | エラー |
|---|---|---|---|
| `GET /api/docverify/inspections/<iid>/r3` | — | 状態 JSON（下） | 404 検査なし |
| `POST …/r3/documents` | multipart: `file`・`kind`・`include_hidden`（`0` で非表示を検出から外す） | 201 状態 JSON | 400 種別なし・ファイルなし・取り込み不可（IngestError の文）／500 |
| `DELETE …/r3/documents/<did>` | — | 状態 JSON | 404 |
| `POST …/r3/setcheck` | — | 状態 JSON（`set_check` を更新） | 400 文書なし／500 |
| `POST …/r3/setcheck/<pid>` | `{"decision"}` | 状態 JSON | 400 不正値／404 組なし |
| `POST …/r3/trace` | `{"format"}` | 状態 JSON（`trace_format` を保存） | 400 書式なし |
| `GET …/r3/trace.xlsx` | — | xlsx | 500 |
| `GET/PUT /api/docverify/r3/settings` | 3.2 の設定 | 設定＋`rules` | 400 不正な形／500 |

状態 JSON: `{"documents":[passages を除く],"kinds","set_check":view(),"trace":build(),"formats","trace_format","findings":件数,"coverage":"網羅性: 未検証"}`。
集合の検査の対象は「このレビューの文書（`main`）＋登録した文書」。登録時の候補は `checks.candidates` → `apply_rules` → `term_variants` → `missing_attributes` の順で作り、文書の `candidates` に持つ（レビューの指摘一覧には入れない）。

## 7. 画面（SCR-06-07）

### 7.1 G5 `_r3.html`
`<section class="dv-view dvr-view dv3" data-view="setcheck">`。4 枚のカード: 文書の登録（`#dv3Kind`・`#dv3File`・`#dv3Hidden`・`#dv3Docs`）／集合の検査（`#dv3Run`・`#dv3Pairs`）／追跡表（`#dv3Format`・`#dv3Xlsx`・`#dv3TraceSummary`・`#dv3Trace`）／規則と組織の語彙（`#dv3RuleList`・`#dv3Forbidden`・`#dv3Allowed`・`#dv3Synonyms`）。見出しの下と各結果カードに常に「網羅性: 未検証」を出す。

### 7.2 G6 `docverify-r3.js`
`DV.on('setcheck', fn)` で初回だけ結線し、表示のたびに `GET …/r3` と設定を読む。判断ボタン（矛盾・重複・問題なし）は `aria-pressed` で選択を示す。0 件は `EMPTY` の文。追跡表の空欄は「対応なし」。エラー文は `DV.api` が帯に出す。

### 7.3 G7 `docverify-r3.css`
クラス接頭辞 `dv3-`。色・余白・角丸・文字の大きさは tokens の変数だけ。

## 8. テスト（G8。受入基準との対応）

| テスト | 受入基準 |
|---|---|
| `test_120_*` | ほぼ同じ文 2 つ → 重複候補 1 組・正規化・別の文は組にならない |
| `test_121_*` | 「5 秒以内」と「10 秒以内」→ 矛盾候補 1 組・否定と肯定・主語が違えば組にならない |
| `test_122_*` | 「矛盾」を選ぶ → 指摘に種別「矛盾」で 1 件増える・判断し直し・不正値・再実行での引き継ぎ |
| `test_123_*`・`test_120_123_122_api_setcheck_flow` | 候補 0 件で「確認した範囲では指摘はありません。網羅性は未検証です。」 |
| `test_130_*` | 要件と設計の 2 文書 → 種別付きで 2 件 |
| `test_131_132_*`・`test_132_orphan_downstream_id` | REQ-001〜003・設計が 001 と 002 → 3 行・003 の設計欄が空・完全率 67%（2/3）・孤立 0 件 |
| `test_133_*` | xlsx の行数が画面と同じ |
| `test_134_*` | 書式「FR-数字」→ FR-001 形式だけ（NFR-002 は拾わない） |
| `test_135_*` | ID の無い設計書 → 理由の文が出て表から外れる |
| `test_016_*` | 「項目名｜型｜必須」の表 → 「項目名: 氏名／型: 文字列／必須: ○」の 1 断片 |
| `test_017_*` | 非表示シート → 「非表示」の印・検出対象から外せる |
| `test_018_*` | パスワード付き xlsx/docx → 「パスワードを外してから」・「破損」と出ない |
| `test_025_*` | UNIVERSAL を無効 → 「必ず」の候補が出ない・禁止語・許容語 |
| `test_026_*` | 「検証方法」列の無い要求一覧 → 「検証方法がありません」 |
| `test_027_*` | 辞書「顧客＝お客様」・両方を含む文書 → 用語ゆれ候補 |

画面（SCR-06-07 の全状態）は Playwright MCP で確かめる（本書の範囲では未検証）。出口基準「実文書 3 本で追跡表を作る」も未検証。

## 9. 結線（担当外。本線が既存ファイルに入れる）

`scratchpad/wire_R3.txt` に正確な行を置いた。要点: `web/__init__.py` の Blueprint 登録、`templates/doc_verify.html` の link・nav・include・script、`docverify-core.js` の `REVIEW_VIEWS` と `TITLES` に `setcheck` を足す（無いと `DV.show('setcheck')` がホームへ落ちる）。

## 10. 要判断（RD の解釈が分かれる箇所。保守者が決める）

1. FR-06-121(b)「一方が否定・禁止で他方が肯定」は主語が同じだけで候補になり、述語が違う文でも出る。RD どおり追加条件なし（`NEG_MIN_SIMILARITY = 0.0`）で実装した。誤検出が多ければ否定語を除いた類似度の下限を設ける
2. FR-06-132 の完全率は「登録された下流の種別**すべて**に対応がある上流 ID の割合」とした（設計だけ・テストだけの対応は未対応に数える）
3. ID の書式は 1 つを全文書に使う（要件の ID を下流が参照する前提）。設計 ID → テストの 2 段追跡は扱わない
4. FR-06-016〜018・025〜027 は R3 で登録した文書にだけ効く。単一文書（R1 の取り込み）にも効かせるには `doc_verify.py` の変更が要る（wire_R3.txt 4）
5. FR-06-016・017 の追加に伴い新規ファイル `ingest_r3.py` を足した（指定の新規ファイル一覧の外）
