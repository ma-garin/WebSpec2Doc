# WS2D-DD-006 詳細設計書 System 06「ドキュメント検証」R5（規則別の精度）

- 文書ID: WS2D-DD-006-R5 / 版数: 0.1（草案・未承認） / 作成日: 2026-10-15 / 作成者: 開発チーム / 承認者: 未承認（保守者が記入する）
- 準拠: IPA 共通フレーム（ソフトウェア詳細設計相当）。テスト観点は ISTQB CTFL のテストレベルで分け、RD-006 の G/W/T から導く
- 上位文書: WS2D-RD-006 要件定義書 11 章 R5、`docs/research/docverify/E1_datasets.md`
- 範囲: FR-06-170〜174、SCR-06-10、NFR-06-08（精度ページへの案内）。FR-06-175（LLM の比較）は含めない

## 1. ファイル一覧

| # | ファイル | 区分 | 節 |
|---|---|---|---|
| F1 | `quality/docverify_eval/ja_v1.jsonl` | 新規 | 2 |
| F2 | `quality/docverify_eval/README.md` | 新規 | 2 |
| F3 | `scripts/docverify_eval.py` | 新規 | 3 |
| F4 | `quality/docverify_eval/result.json` | 新規（F3 の出力） | 3・7 |
| F5 | `web/services/docverify/accuracy.py` | 新規 | 4 |
| F6 | `web/routes/doc_verify_r5.py` | 新規（Blueprint `doc_verify_r5`） | 5 |
| F7 | `templates/docverify/_r5.html` | 新規 | 6 |
| F8 | `static/js/docverify-r5.js` | 新規 | 6 |
| F9 | `tests/test_docverify_r5.py` | 新規 | 8 |

共有ファイル（`web/__init__.py`・`templates/doc_verify.html`・`static/js/docverify-core.js`・`docverify-review.js`・`_review.html`・`doc_verify.py`）は本リリースで編集しない。結線の行は別紙（結線指示）にまとめ、統合担当が入れる。

## 2. 評価セット（FR-06-171）

- 1 行 1 文の JSON Lines。キー: `id`（`JA-001`〜）・`text`・`labels`（評価単位 ID の配列。空配列＝欠陥なし）・`method`（`injected` | `authored` | `real`）・`role`（`base` | `variant` | `authored`）・`base`（注入元の基準文 ID または null）
- 自作 99 文（injected 65：基準文 14・注入文 51、authored 34）。第三者の文を含まない
- 注釈方針は F2。ラベルは人の判断で付け、検出器の挙動に合わせない
- 注釈者 1 名（AI）・裁定なし・kappa 未計測。**FR-06-171 の受入（2 名独立注釈・kappa 0.6 以上）は未達**

## 3. 測定スクリプト（FR-06-170・173・174）

`scripts/docverify_eval.py [--dataset PATH] [--out PATH] [--date YYYY-MM-DD]`

| 関数 | 契約 |
|---|---|
| `load_dataset(path) -> list[dict]` | 未知のラベル・不正な method・空の text は `ValueError`（行番号つき） |
| `predict(text) -> set[str]` | `checks.candidates([{"id":"p1","location":"eval","text":text}])` の rule を評価単位へ読み替える |
| `score(rows) -> dict` | 規則ごとに `n`（文数）・`n_gold`・`n_predicted`・`tp`・`fp`・`fn`・`precision`・`recall`（小数 3 桁。分母 0 は null） |
| `build(rows, dataset, date, old) -> dict` | 全体・method 別・前回値・差・限界をまとめる |
| `main(argv) -> int` | `result.json` を書き、規則ごとの値を標準出力に 1 行ずつ出す |

- 評価単位: `AMBIGUOUS`（= `RD.AMBIGUOUS` ∪ `REQ.AMBIGUOUS_TERM`）、`REQ.INCOMPLETE`・`REQ.OPEN_ENDED`・`REQ.UNIVERSAL`・`REQ.AND_OR`・`REQ.MEASURABILITY`・`REQ.MULTIPLE_REQUIREMENTS`
- 判定は文単位（その文にその規則の指摘が 1 件以上出たか）。指摘の位置は照合しない
- 対象は規則ベースのみ。**LLM は対象外**（`scope` に明記）
- 決定的: 入力（規則のソース・評価セット・`--date`）が同じなら出力は同じ
- 規則の版 `rules_version` = `checks.py` と `web/vendor/reverse_doc/ambiguity.py` の SHA-256 先頭 12 桁。評価セットも SHA-256 先頭 12 桁
- 回帰（FR-06-173）: 既存の `result.json` と版または評価セットが違えば、旧 `measured_on`・`rules_version`・`rules` を `previous` に移し、`delta` に規則ごとの差（今回 − 前回）を書く。同じなら `previous` を引き継ぐ
- method 別（FR-06-174）: `by_method.injected`・`authored`・`real`。該当文が無い method は null

## 4. 表示データ `web/services/docverify/accuracy.py`（FR-06-170・172）

| 名前 | 契約 |
|---|---|
| `RESULT_PATH` | `quality/docverify_eval/result.json` |
| `MIN_PRECISION = 0.7` | これ未満の規則は既定で無効（暫定） |
| `load(path=None)` | 無ければ None。読めない・形が違えば `ValueError(MSG_BROKEN)` |
| `page(path=None) -> dict` | 下記の JSON。値の無い所は文字列「未測定」 |
| `disabled_rules(path=None) -> frozenset[str]` | 既定で無効にする checks の rule ID。記録が無い・壊れていれば空集合 |

規則の状態: 適合率 < 0.7 → 無効・理由「適合率 X が基準 0.7 未満のため、既定で無効にしています。」／検出 0 件で適合率が出ない → 有効・理由「検出が 0 件のため適合率を出せません（無効にする根拠がありません）。」／それ以外 → 有効。

評価セットの無い検査（重複候補・矛盾候補）は行として出し、全欄「未測定」。

## 5. API（SCR-06-10）

`GET /api/docverify/accuracy` → 200 で `page()` の JSON。キー: `measured`・`message`・`measured_on`・`rules_version`・`dataset{name,language,n,license,annotators}`・`kappa`・`scope`・`methods[{key,label}]`・`rules[{rule,label,measured,precision,recall,n,n_gold,n_predicted,enabled_by_default,reason,by_method{injected,authored,real},previous{precision,recall},delta{precision,recall}}]`・`previous_measured_on`・`limits[]`・`min_precision`。
記録が壊れていれば 500 `{"error": "精度の記録を読めませんでした。測定をやり直すと表示されます。"}`、それ以外の例外は 500 `{"error": "精度を読めませんでした。時間をおいて再読み込みしてください。"}`（詳細はログのみ）。

## 6. 画面（SCR-06-10）

- `_r5.html`: `<section class="dv-view" data-view="accuracy">`。DOM の id: `dvAccReload`・`dvAccMeta`（測定日・データセット・注釈者数・kappa・規則の版・前回の測定日・対象・無効の基準）・`dvAccTable`（規則・適合率・再現率・n・正解の件数・検出の件数・前回・差・状態・理由）・`dvAccMethods`（欠陥を注入した文／自作の文／実文書の列）・`dvAccLimits`
- `docverify-r5.js`: `location.hash === '#accuracy'` のとき（読み込み時・hashchange・再読み込みボタン）に API を読む。値はすべて `esc` してから表に入れる。失敗時は `role="alert"` で API の `error` を出す。`window.DVAccuracy.load` を公開
- 報告と判定画面から `#accuracy` への案内は結線指示の 5)・6)

## 7. 測定結果（2026-10-15 実行。`result.json` の値をそのまま転記）

規則の版 `7be8dab6efa6`・評価セット `ja_v1`（sha256 先頭 `dd858576b51b`）・n = 99 文。

| 評価単位 | 適合率 | 再現率 | n | 正解 | 検出 | TP | FP | FN |
|---|---|---|---|---|---|---|---|---|
| AMBIGUOUS | 0.867 | 0.703 | 99 | 37 | 30 | 26 | 4 | 11 |
| REQ.INCOMPLETE | 1.000 | 0.889 | 99 | 9 | 8 | 8 | 0 | 1 |
| REQ.OPEN_ENDED | 1.000 | 0.143 | 99 | 7 | 1 | 1 | 0 | 6 |
| REQ.UNIVERSAL | 0.833 | 1.000 | 99 | 5 | 6 | 5 | 1 | 0 |
| REQ.AND_OR | 1.000 | 1.000 | 99 | 2 | 2 | 2 | 0 | 0 |
| REQ.MEASURABILITY | 0.750 | 0.333 | 99 | 18 | 8 | 6 | 2 | 12 |
| REQ.MULTIPLE_REQUIREMENTS | 未算出（検出 0） | 0.000 | 99 | 9 | 0 | 0 | 0 | 9 |

method 別: injected（65 文）では AMBIGUOUS 0.810/0.630・REQ.MEASURABILITY 0.714/0.312・REQ.UNIVERSAL 0.750/1.000、authored（34 文）では AMBIGUOUS 1.000/0.900・REQ.MEASURABILITY 1.000/0.500。real は未測定。

読み方: 適合率 0.7 未満の規則は無く、既定で無効になる規則は無い。再現率が低いのは REQ.MULTIPLE_REQUIREMENTS（0）・REQ.OPEN_ENDED（0.143）・REQ.MEASURABILITY（0.333）。n が小さい（正解 2〜37 件）ため、規則間の差を断定しない。

## 8. テスト（`tests/test_docverify_r5.py`、14 件）

| 観点 | 受入 |
|---|---|
| 評価セット 80 文以上・空集合あり・全評価単位が出る／未知ラベルを拒否 | FR-06-171 |
| tp/fp/fn と適合率・再現率・n、検出 0 件は null | FR-06-170 |
| 2 回実行で同一出力（決定的）、版を変えると前回値と差が並ぶ | FR-06-173 |
| venv の python で CLI が終了コード 0 | — |
| 適合率 0.6 の規則が既定で無効になり理由が出る | FR-06-170 |
| 3 規則測定済み・未測定の行は「未測定」 | FR-06-172 |
| method が 3 列に分かれ、実文書は「未測定」 | FR-06-174 |
| 記録なし → 全欄「未測定」、壊れた記録 → 利用者向けの文（内部情報なし） | FR-06-172・エラー処理 |
| 登録済みの result.json が評価セットと一致 | — |
| 部分テンプレートの DOM 契約 | SCR-06-10 |

画面の実機確認（Playwright）は結線後に行う。本書の時点では**未実行**。

## 9. 未達・要判断

- FR-06-171: 2 名独立注釈・裁定・kappa は未実施（注釈者 1 名・AI）
- FR-06-170 の「既定で無効」は `disabled_rules()` まで。`checks.candidates` への適用は共有ファイルの変更になるため結線指示 7) に分けた
- FR-06-172 の報告・判定画面からの案内は結線指示 5)・6) に依存（結線前は未実装）
