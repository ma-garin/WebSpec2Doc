# System06 docassure 独立レビュー（読み取り専用・実装者以外の目）

対象: web/services/docassure/ 全体、web/routes/doc_assure.py、tests/test_docassure_*.py。
実測確認は python -I で 2 文書を `pipeline.analyze` に通した結果。未確認の項目は「未検証」と明記。

## 高

H-1 Traceability が常に 100 点になる（実測確認済み）
- web/services/docassure/pipeline.py:105-111
- `linked` を全 edge の端点から作るため、Document/Section からの `contains` edge で全要件が「つながっている」扱いになる。設計・テストが 0 件でも「つながりが無い要件 0 / 2 件」「value=100.0 coverage=1.0」と出る。「指摘 0 件を 100 にしない」規律の違反。
- 修正案: 対象 kind を `mentions`(Screen/API)・`verifies`・`references` に限定。EXPLICIT と INFERRED を分けて数える。`coverage.compute` の design/test_designed を使う。テスト実行が未取込なら value=None。

H-2 readiness の trace 判定が実際の trace coverage を見ていない
- web/services/docassure/readiness.py:57-63 と pipeline.py:108-111
- `tr.get("coverage")` は Score の coverage（H-1 で常に 1.0）。そのため `min_trace_coverage=0.8` の条件は実質無効で、設計が無い文書も READY の条件を通る。`trace["coverage"]` (coverage.py) を gate に渡していない。
- 修正案: gate に trace coverage の実比率を渡す。None（未評価）なら READY にしない。

H-3 人の decision（waived/accepted/resolved/conflict_decided）が判定に一切反映されない
- web/routes/doc_assure.py:93-112, web/services/docassure/readiness.py:21-74, pipeline.py:114
- decisions は store に保存されるだけで、gate・矛盾の status・指摘の status のどこにも適用されない（services 配下に decision/waiv の参照なし）。人が「解決済み」とした矛盾が再分析後も UNRESOLVED のまま Consistency を減点し続ける。逆に waiver の expiry も検証・失効されない。AI 結果が人の判断を上書きしているのと同じ結果になる。
- 修正案: 分析結果と decisions を `target` で結合する層を作り、expiry 超過の waiver は無効とする。confirmed は人由来のみ。

H-4 Consistency が「比較していない」のに 100 点（実測確認済み）
- pipeline.py:95-102
- 文書 1 本・矛盾 0 件で value=100.0（coverage=0.5）。coverage 0.5 は MIN_COVERAGE(quality.py:13) ちょうどで、Overall に 100 点として加重(重み 3.0)される。「文書間の比較は未実施」が not_evaluated にしか出ず、数値は満点。
- 修正案: 文書が 1 本なら文書内の矛盾だけが対象と明記し value=None、または coverage < MIN_COVERAGE にする。conflicts ステージ失敗時（pipeline.py:70）も conflicts=[] のため同じく 100 になる。errors があっても Consistency は満点のまま。

H-5 クリティカル矛盾の BLOCKED が発火しない（死んだゲート）
- readiness.py:27-31 と conflict.py:38 `_SEVERITY`
- conflict の severity は high/medium のみで critical を出さない。「未解決 critical 矛盾で BLOCKED」は到達不能。数値・権限の矛盾（high）が未解決でも gate は high 指摘 FAIL を数えるだけで、conflicts の high は見ない（readiness.py:56 は findings のみ）。未解決の高重大矛盾があっても CONDITIONALLY_READY や READY になり得る。
- 修正案: 未解決の high 以上の矛盾を CONDITIONALLY_READY の条件に入れる。

H-6 trace の Screen 抽出が過広で OBSERVED として誤ノード化（実測確認済み）
- trace_graph.py:16, 87-91
- `([^\s、。,.（）()「」]{1,14}?画面)` は「REQ-002 REQ-001 を参照し検索画面で表示する」から `SCR:を参照し検索画面` を作り、provenance=OBSERVED・confidence 1.0 で `mentions` edge を張る。助詞・動詞を含む断片が「画面」として観測済み扱いになり、coverage の `design`（coverage.py:24）が過大になる。
- 修正案: 画面名は助詞(は/が/を/に/で/の)を含まない連続文字に限定する、または INFERRED にする。

## 中

M-1 Finding ID が文書をまたいで衝突しうる
- rules/engine.py:87
- `finding_id = f"{rid}:{req or 'L'+line}:{n}"`。n は rule 内の連番で文書ごとにリセットされる（pipeline.py:52-56 が文書ごとに run_rules）。同じ rule・同じ requirement_id（REQ-001 が複数文書にある）で衝突する。decision の `target` が曖昧になる。document_id を含めること。
- 併せて requirement_id そのものも文書名前空間を持たない（requirement_engine.py:195 は原文 ID をそのまま採用）。trace_graph.build の `reqs[rid]`(trace_graph.py:78) と quality の fdim/fmap(quality.py:127) は requirement_id キーのため、複数文書で同じ REQ-001 があると後勝ちで上書き・指摘が混ざる。pipeline.py:65 の `tests[u.requirement_id]` も同様に上書き。※実測では 2 文書で `A:REQ-001`/`B:REQ-001` のキーが出ており別処理で修飾されている可能性があるが、原因箇所は未検証。単一箇所で一貫して修飾されているか確認が必要。

M-2 ルールエンジンの例外が全文書分の結果を落とす
- pipeline.py:50-57 と rules/engine.py:80
- 検出器 1 つの例外で `run_rules` ステージ全体が失敗し、それまでに溜めた findings は残るが残りの文書は未実行。errors には型名のみ（pipeline.py:22）で原因が追えない。`log.exception` も無い。検出器・文書単位で隔離し、スタックはログへ。
- 付随: `except Exception` で ステージ名と型名のみ。デバッグ不能（pipeline.py:21）。

M-3 Quality の Completeness が分母を誤る
- quality.py:66-74
- `total` はトリガーに当たった全テンプレートの全項目数。`cands` は不足候補なので `1 - len(cands)/total` は成立するが、`cands or total` の条件(74行)は total>0 で常に真。トリガー語（文字列 in 判定）の部分一致が広く、たとえば「ログ」が「ログイン」に当たる等、低品質の根拠で数値が出る。未検証（TEMPLATES の中身は未読）。

M-4 conflict の正規表現が広い
- conflict.py:33 `_POS` に `可`（1 文字）。「可能性」「不可欠」「許可」にも当たる。`_NEG` の「不可」は先に判定されるが「不可欠」は deny に分類される。
- conflict.py:29 `ACTIONS` の「出力」を download、「書き込」を edit。「出力」は画面出力や帳票でも download 扱い。`next(... for a in ACTIONS if a in sent)` は辞書順の最初の語のみ採用。複数動作の文で誤分類。
- conflict.py:39 `_AUTH_RANK` は文書 ID の部分文字列（"test", "spec", "design"）。ID が "latest_v2" で test=1 と判定される。hints のみだが higher_authority を誤って出す。
- conflict.py:32 `_NEG` が evidence_guard.py:70 の `_NEG` と別定義で「ない」「なし」を含むため、「〜がない場合は」等の条件文が反証探索を無効にする。

M-5 evidence_guard の反証探索が緩い
- evidence_guard.py:89 `re.search(r"\d|[をがはにで]", line)` はほぼ全行に当たる。トピック語（「ログ」「上限」「桁」「同時」）の部分一致のみで反証と判定し、counter_evidence が付くと指摘が dismissed（review_board.py:128）に落ちる。AI の真の指摘が低品質な反証で握りつぶされる。
- 付随: `_TOPICS` の「ログ」は「ログイン」に当たる。

M-6 review_board の中立性
- review_board.py:100-102 `except AssistError` のみ。失敗を件数で数えるが、どの要件・role かを残さない。一部失敗で mode="AI" を返す（105行は全滅時のみ DEGRADED）。部分欠落が利用者に見えない。
- review_board.py:41 `_CACHE` はモジュールグローバルでロック無し・上限無し（メモリ増加、スレッド競合）。キーに document 全文でなく chunk text のみのため、同じ文が別文書にあると他文書の根拠で再利用される。
- review_board.py:127 `status: CANDIDATE` は固定で正しいが、`_adjudicate`(137-150) は `out[i].update` で新 dict を作り元は不変（良い）。

M-7 store の競合
- store.py:46-50 `add_decision` は load→save の read-modify-write でロックが無い。同時に 2 人が decision を入れると後者が前者を消す（原子的な置換は `os.replace` で守っているが更新の排他はない）。
- routes/doc_assure.py:63-66 analyze も同様に prev を読んで保存するため、分析中に入った decision が失われる。

M-8 decide ルートの入力検証
- routes/doc_assure.py:101-110
- `target` が実在する finding/conflict か検証しない。`expiry` の形式・過去日を検証しない。`reason` 長さ無制限。`_perm.record` に reason を渡さない点は良いが、waived 以外は reason 不要で accepted/rejected の根拠が残らない。

M-9 pipeline の戻りの不変性・None 処理
- pipeline.py:97-112 `scores["Consistency"] = ...` で scores を直接置換（ローカルなので問題は小さい）。
- pipeline.py:118-119 `gate["state"] in (M.DRAFT, "BLOCKED")` はリテラル混在。errors があるときの READY→DRAFT 降格は意図どおりだが、CONDITIONALLY_READY/REVIEWABLE も DRAFT に落ちる（情報量の低下）。
- pipeline.py:33-36 `d.get("id")` が重複した場合（ID 重複）を検証しない。`texts`/`units_by_doc` が上書きされ、1 文書分が消える。

M-10 巨大関数（50 行超）
- pipeline.py:26-136 `analyze` 約 110 行（クロージャ内に副作用が散在）
- semantic_diff.py:53-125 `diff` 約 73 行
- trace_graph.py:64-144 `build` 約 81 行
- conflict.py:148-207 `_numeric` 約 63 行
- requirement_engine.py:71-136 `_fields` 約 68 行
- state_transition.py `records` 約 61 行
- quality.py:36-75 `_intrinsic` 約 40 行だが分岐 7 つ（循環的複雑度高）
- 800 行超のファイルは無し。ただし rules/detectors.py は 480 行で境界に近い。

## 低

L-1 pipeline.py:13 `_d` 他の型注釈なし（公開関数 `analyze` 以外）。review_board.py:48 `_get`、89 `run` に戻り型/引数型なし。
L-2 conflict.py:172 `del offset` は未使用変数の消去。155 行の `offset` 計算ごと削除する。
L-3 conflict.py:242 `bool(ra & rb) if pair == ... else bool(ra & rb)` は両分岐が同一。
L-4 hashlib.sha1 を ID/指紋に使用（pipeline.py:35, evidence_guard.py:18）。セキュリティ用途ではないため低。`usedforsecurity=False` を付ける。
L-5 rules/engine.py:44-46 `_esc` が関数内 import。トップレベル import で足りる。
L-6 coverage.py:13 `v.get("status") or v.get("result") or "" if isinstance(v, dict) else v` は優先順位が読みにくく、dict でない v が None だと "NONE" になる（`str(s or "")` で救済されるが `str(None)` ではなく "" になる点は OK）。括弧で明示する。
L-7 versioning.py:29-30 MOVED 時 `d["before"]` が無いと KeyError（diff の出力に常にあるため通常は問題なし）。
L-8 review_board.py:153-154 `SimpleNamespace` で debate/counter_evidence を作る間接層は不要で、テストの差し替え口以外に利点がない。

## テストの弱さ

T-1 tests/test_docassure_pipeline.py:55-62
- `value is None or value < 100`、`value is None or coverage >= 0.5` は、すべて None でも通る（空結果で通る）。H-1/H-4 の 100 点バグはこのテストでは検出できない（実測で 2 文書・設計無しで Traceability=100 が出るのに全テスト緑）。2 文書・設計無しの Traceability が None か 100 未満であることを直接 assert する。
T-2 tests/test_docassure_requirement_engine.py:59
- `assert [...][:2] == [...][:2] or plain` は `plain` が空でなければ常に真。恒真アサーション。
T-3 tests/test_docassure_rules.py:42
- `assert fs` は件数・内容を見ない。
T-4 tests/test_docassure_pipeline.py:68
- `x["result"] in (4 値)` は全値を許す。NOT_EVALUATED が PASS に化けていないことの検証になっておらず、checked==0 で PASS になるケース（rules/engine.py:95）を見ていない。
T-5 tests/test_docassure_benchmark.py:33
- トラップ FP=0 のみで再現率・適合率の下限が無く、検出が全部 0 件でも緑（コメントにも「目標未達では落とさない」）。`B.run(write=True)` は実リポジトリの `docs/.../result.json` を書き換える副作用つき。
T-6 readiness/decision 連携のテストが無い（H-3 のとおり、decisions が gate に効くテスト自体が存在しない）。複数文書で同一 requirement_id（M-1）のテストも無い。

## 良い点（確認できたもの）
- 矛盾は常に status=UNRESOLVED・truth=UNKNOWN（conflict.py:138）で、hints は「正誤の判定ではない」と明記。
- review_board の AI 結果は status=CANDIDATE 固定、引用実在検証を通らない指摘は unsupported に隔離。
- rules/engine.py は評価材料が無い検出器を NOT_EVALUATED にする（skip）。ただし checked=0 かつ skip なしの場合の PASS は M-3 系で要確認（未検証）。
- store.save はテンポラリ→`os.replace` の原子的書き込み。
