# テスト設計仕様書（ISTQB / ISO/IEC/IEEE 29119-4 準拠の技法適用分析）

作成日: 2026-08-23
対象リビジョン: `main` @ 0fdc6e3
分析方法: 静的読み取り（`grep` / `find` / ファイル読解）のみ。**テストは一切実行していない（未実行）。**
準拠基準: ISTQB Certified Tester Foundation Level (v4.0) 第4章、ISO/IEC/IEEE 29119-4:2021（Test techniques）

---

## 0. この文書を読む前提（最重要）

本リポジトリは**テスト設計技法そのものを製品機能として実装している**（`src/autorun/`、`src/mbt/`、`src/techniques/`）。
そのため技法名で `grep` すると大量にヒットするが、その大半は「製品が技法を実装しており、その実装をテストしている」ものであり、
「本製品自身のテスト設計に技法を適用している」ものではない。本文書では両者を分けて判定する。

| 記号 | 意味 |
|---|---|
| **(A) 被テスト対象としての技法** | 製品が技法エンジンを実装し、そのエンジンをテストしている |
| **(B) 適用技法としての技法** | 本製品自身のテストケース設計に、その技法を使っている |

ISO/IEC/IEEE 29119-4 が対象とするのは **(B)** である。(A) は技法の適用ではなく機能テストである。

---

## 1. 適用範囲

### 1.1 テスト資産の規模（実測）

| 項目 | 実測値 | 測定コマンド |
|---|---|---|
| テストモジュール数 | 224 | `find tests -name 'test_*.py' \| wc -l` |
| テスト関数数 | 3,106 | `grep -rc '^def test_\|^    def test_' tests/ --include='*.py'` の総和 |
| E2E テスト関数（`tests/e2e/*.py`） | 85 | `grep -rc 'def test_' tests/e2e/*.py` の総和 |
| E2E システムテスト関数（`tests/e2e/system/`） | 32 | 同上 |
| `@pytest.mark.parametrize` 出現数 | 65（23 ファイル） | `grep -rn '@pytest.mark.parametrize' tests/ src/ web/` |
| プロダクションコード（Python） | `src/` 147 ファイル / `web/` 93 ファイル / `scripts/` 15 ファイル / `app.py` | `find <dir> -name '*.py'` |
| フロントエンド JS | `static/js/` 51 ファイル | `ls static/js \| wc -l` |
| 機能契約（feature contract） | 52 機能 | `grep -c '"feature_id"' quality/feature_contracts.yml` |

### 1.2 収集対象外の紛らわしいファイル（注意）

`pyproject.toml:23` に `testpaths = ["tests"]` が設定されているため、以下 5 件は**テストではなくプロダクションモジュール**であり収集されない。
名前が `test_` で始まるだけである。

- `/Users/fujimagariyuki/dev/active/webspec2doc/src/analyzer/test_conditions.py`
- `/Users/fujimagariyuki/dev/active/webspec2doc/src/generator/test_design.py`
- `/Users/fujimagariyuki/dev/active/webspec2doc/src/generator/test_plan_generator.py`
- `/Users/fujimagariyuki/dev/active/webspec2doc/src/mbt/test_data.py`
- `/Users/fujimagariyuki/dev/active/webspec2doc/web/services/test_design_settings.py`

同様に、`output/**/qa_process/*.spec.ts`（実測 200 件超）は**製品が生成した成果物**であり、本製品のテストではない。
`node_modules/zod/**/*.test.ts`（139 件）は依存ライブラリのテストである。**これらを本製品のテスト資産として数えてはならない。**

---

## 2. 技法別の適用状況

判定は「適用あり(n件)」「限定的(n件)」「該当なし(0件)」の3値。

### 2.1 ブラックボックス技法（ISTQB 4.2 / ISO 29119-4 §5）

| 技法 | (A) 被テスト対象としての実装・テスト | (B) 自テストへの適用 |
|---|---|---|
| 同値分割 | **適用あり** — 実装 `src/autorun/techniques.py`（`equivalence_classes` / `TECHNIQUE_EQUIVALENCE`）、`src/autorun/classification_tree.py:158-161` が再利用。テスト `tests/test_techniques.py`（全 7,432 bytes） | **限定的(2件)** — `tests/test_url_safety.py:12-35` で有効クラス `SAFE_URLS`(4値) / 無効クラス `UNSAFE_URLS`(14値) を宣言し `:37-47` の 2 関数で `parametrize` |
| 境界値分析 | **適用あり** — 実装 `src/analyzer/bva.py`（`_max_length_cases:84` / `_min_length_cases:95` / `_range_cases:108`）、ドメイン分析 `src/autorun/domain_analysis.py`。テスト `tests/test_bva.py`（10,724 bytes）、`tests/test_document_test_data.py:12,90`、`tests/test_techniques_extended.py:189-208`（on/off/in/out point） | **限定的(5件)** — §3 の突合表を参照。定数名をテストから参照しているのは 3 件のみ |
| デシジョンテーブル | **適用あり(3件)** — 実装 `src/autorun/cause_effect.py:236 derive_decision_table`。テスト `tests/test_techniques_extended.py:166,172,180` | **該当なし(0件)** — 条件の組合せを表として網羅列挙したテストは存在しない |
| 状態遷移テスト | **適用あり(37件)** — 実装 `src/graph/transition_graph.py`（`_MAX_2SWITCH_PATHS=50`）。テスト `tests/test_state_table.py`（29 関数。0-switch `:106`、1-switch `:112`、無効遷移列挙 `:85,:231`）、`tests/test_prime_path.py`（8 関数） | **適用あり(7件)** — `tests/e2e/test_autorun_state_matrix_e2e.py`。`_ACTIVE` 6 状態（`:30-37`）と `_TERMINAL` を全走査し、5 つの不変条件を `parametrize` 7 箇所（`:116,126,137,145,162,172,179`）で検査 |
| ユースケーステスト | **適用あり(5件)** — 実装 `src/autorun/use_case_testing.py`。テスト `tests/test_techniques_extended.py:271-309` | **適用あり(32件)** — `tests/e2e/system/test_st1_auth.py` 〜 `test_st6_admin.py`。`test_st001_…` 〜 `test_st032_…` の ID 付きシナリオ 32 件（例: `test_st1_auth.py:18,25,30,43,52,59`） |
| ペアワイズ／直交表 | **適用あり(22件)** — 実装 `src/mbt/pairwise.py`（`MAX_FACTORS=12` / `MIN_FACTORS=2`）、`src/techniques/combinatorial.py`、`src/autorun/orthogonal_array.py`（`MAX_PRIME=7` / `MAX_ROWS=128`）。テスト `tests/test_pairwise.py`(9)、`tests/test_techniques_combinatorial.py`(9: 2-way/3-way/禁則/シード/混合強度)、`tests/test_techniques_extended.py:127-158`(4) | **該当なし(0件)** — 自テストの `parametrize` 65 件はいずれも 1 因子の値列挙であり、因子×水準の組合せ削減を行った箇所はない |
| クラシフィケーションツリー | **適用あり(4件)** — 実装 `src/autorun/classification_tree.py`（`MAX_CLASSES_PER_CLASSIFICATION=8`）。テスト `tests/test_techniques_extended.py:66,84,92,108` | **該当なし(0件)** |

**要点**: 技法エンジンとしては 7 技法すべてが実装・テストされている（(A) は充実）。
一方、**自身のテスト設計に技法を適用しているのは 3 技法のみ**（同値分割・境界値分析・状態遷移・ユースケース）。
デシジョンテーブル・ペアワイズ・クラシフィケーションツリーは (B) がゼロである。

### 2.2 紛らわしい命名（誤判定防止）

- `tests/e2e/test_autorun_decisions_e2e.py` は**デシジョンテーブル技法ではない**。AutoRun の「判断ダイアログ」UI のテスト（`:161-230`、9 関数）。
- `tests/test_failure_hypothesis.py` は Hypothesis（property-based testing ライブラリ）ではない。`web/services/failure_hypothesis.py` の障害仮説モジュールのテスト。
  **property-based testing ライブラリ（hypothesis）は本リポジトリに導入されていない（0件）。**

---

## 3. 境界値の 1 対 1 突合表

`grep -rnE "^[A-Z_]+ *= *[0-9]+|MAX_[A-Z_]*|_LIMIT *= *[0-9]+|TIMEOUT[A-Z_]* *= *[0-9]+" src/ web/ --include='*.py'` の実測ヒット **295 行**。
うち代表 16 定数について `grep -rn "<定数名>" tests/` で 1 対 1 に突合した結果が下表である。

| # | 定数（定義位置） | 値 | tests/ からの定数名参照 | 対応テスト（file:line） | 判定 |
|---|---|---|---|---|---|
| 1 | `src/mbt/document_model.py:12` `MAX_PATHS` | 100 | 0 件 | `tests/test_document_mbt.py:187-202`（100 ノード=ちょうど / 101=超過）。ただし値 `100` をハードコード | 限定的(1件) |
| 2 | `src/mbt/document_model.py:19` `MAX_PRIME_PATH_LENGTH` | 30 | 0 件 | なし | 該当なし(0件) |
| 3 | `src/mbt/document_model.py:20` `MAX_PRIME_ENUMERATION` | 5000 | 0 件 | なし | 該当なし(0件) |
| 4 | `src/mbt/pairwise.py:20` `MAX_FACTORS` | 12 | 0 件 | なし（12/13 因子の境界テストが存在しない） | 該当なし(0件) |
| 5 | `src/mbt/pairwise.py:21` `MIN_FACTORS` | 2 | 0 件 | `tests/test_pairwise.py:65`（1 因子=off point）、`:69`（2 因子=on point）。値ベース | 限定的(2件) |
| 6 | `src/main.py:60` `MAX_PARALLELISM` | 8 | 0 件 | なし。clamp は `src/main.py:804,823,1008` で `max(1, min(n, 8))` | 該当なし(0件) |
| 7 | `src/crawler/page_crawler.py:44` `DEFAULT_MAX_PAGES` | 50 | 0 件 | なし | 該当なし(0件) |
| 8 | `src/crawler/page_crawler.py:45` `DEFAULT_TIMEOUT_MS` | 30,000 | 0 件（`DEFAULT_TIMEOUT_SEC` 系も 0） | なし | 該当なし(0件) |
| 9 | `src/crawler/auto_login.py:19` `SUBMIT_TIMEOUT_MS` | 15,000 | 0 件 | なし | 該当なし(0件) |
| 10 | `src/llm/openai_client.py:37` `DEFAULT_TIMEOUT_SEC` | 30 | 0 件 | なし | 該当なし(0件) |
| 11 | `src/autorun/suggest.py:23` `MAX_SUGGESTIONS` | 5 | **1 件** | `tests/test_autorun_suggest.py:84` `assert len(result.suggestions) == suggest_mod.MAX_SUGGESTIONS` | 適用あり(1件) |
| 12 | `src/mbt/trace_suggestions.py:21` `SUGGESTION_THRESHOLD` | 0.15 | **2 件** | `tests/test_trace_suggestions.py:11`(import), `:90 test_below_threshold_candidates_are_omitted`, `:95` | 適用あり(2件) |
| 13 | `src/viewport/layout_failures.py:26` `PROTRUSION_TOLERANCE_PX` | 2 | 0 件 | `tests/test_layout_failures.py:39 test_two_pixel_overflow_is_tolerated`(on point) / `:24 test_element_overflowing_viewport_is_detected`。値ハードコード | 限定的(2件) |
| 14 | `src/viewport/layout_failures.py:25` `COLLISION_MIN_OVERLAP_PX` | 4 | 0 件 | なし（3px/4px/5px の判別テストなし） | 該当なし(0件) |
| 15 | `src/llm/activity_log.py:26` `_DETAIL_MAX_CHARS` | 500 | 0 件 | なし（`:90` で `detail[:500]` の切り詰めが起きるが未検証） | 該当なし(0件) |
| 16 | `src/capture/finding_reporter.py:37` `_TITLE_MAX_LEN` | 40 | 0 件 | なし（`:148` の切り詰めが未検証） | 該当なし(0件) |
| 17 | `src/autorun/domain_analysis.py:30` `MAX_LITERAL_LENGTH` | 200 | 0 件 | なし（`:84-85` の省略表示分岐が未検証） | 該当なし(0件) |

**（参考）定数名を経由せず値で境界を突いている追加箇所**（`grep -rn '^def test_.*(boundary|limit|max|min|empty|zero|overflow|too_long|oversize|truncat|threshold)' tests/` = 121 件 のうち）:

| 境界 | テスト |
|---|---|
| 文字列長 `maxlength=3` の 2/3/4 文字 | `tests/test_document_test_data.py:12`（`:40-42` で `"ああ"` / `"あああ"` / `"ああああ"`） |
| 数値範囲 `min_value=1` / `max_value=3` の 0/1 | `tests/test_document_test_data.py:90`（`:121-122` で `("0","reject_candidate")` / `("1","accept_candidate")`） |
| ログイン失敗回数 `MAX_FAILED_ATTEMPTS` | `tests/test_auth_store.py:10`(import), `:128 test_lockout_after_max_failures_blocks_correct_password`, `:130,141` |
| API 範囲外値 | `tests/test_api_v1_schedule.py:87 test_put_rejects_out_of_range_diff_summary_limit`（`:90` で `diff_summary_limit: 99`） |
| 空入力（0 件境界） | `tests/test_traceability.py:107`, `tests/test_layout_failures.py:114`, `tests/test_usability_smells.py:125`, `tests/test_form_navigator.py:44`, `tests/test_trace_suggestions.py:98`, `tests/test_techniques_extended.py:352` ほか |

**突合結果の要約**

| 判定 | 件数（代表 17 定数） |
|---|---|
| 適用あり | 2 |
| 限定的（値ハードコードで境界を突いている） | 3 |
| 該当なし（境界テスト不在） | 12 |

未突合の定数が 278 行残る（295 − 17）。**それらについては本文書では「未確認」とし、0 件と断定しない。**

---

## 4. カバレッジ計測の対象と死角（ホワイトボックス技法 / ISTQB 4.3）

### 4.1 設定の実測

`/Users/fujimagariyuki/dev/active/webspec2doc/Makefile:124-133`（`coverage` ターゲット）:

```
$(PYTEST) tests/ --ignore=$(E2E_DIR) \
    --cov=src --cov=web \
    --cov-report=term-missing \
    --cov-fail-under=80 \
```

### 4.2 判定

| 網羅基準 | 設定 | 判定 |
|---|---|---|
| 命令網羅（statement coverage） | `--cov=src --cov=web`、閾値 `--cov-fail-under=80` | 適用あり(1設定) |
| 判定網羅／分岐網羅（branch/decision coverage） | `--cov-branch` の指定が**ない** | 該当なし(0件) |
| 条件網羅・MC/DC | 設定なし | 該当なし(0件) |

### 4.3 死角（計測対象外の実行コード）

**依頼文にあった「`crawler/` が計測対象外」は誤りである。**トップレベルに `crawler/` ディレクトリは存在せず（`ls -d crawler` → not found）、
クローラは `src/crawler/` 配下にあるため `--cov=src` に含まれる。実際の死角は次のとおり。

| 対象 | 規模 | 計測 | 影響 |
|---|---|---|---|
| `src/` | 147 py | 対象 | — |
| `web/` | 93 py | 対象 | — |
| `app.py`（ルート、Flask エントリポイント） | 1 py | **対象外** | 起動・ルート登録・`webbrowser.open` 分岐が未計測 |
| `scripts/` | 15 py | **対象外** | `quality_harness.py`（197 行）・`ui-hash.py` 等の品質ゲート自体が未計測 |
| `static/js/` | 51 js | **対象外** | §7 参照 |
| `templates/` | HTML | **対象外** | 分岐（Jinja 条件）未計測 |

さらに `coverage` ターゲットは `--ignore=$(E2E_DIR)` で E2E を除外する。
つまり **E2E でしか通らない実行経路は「未カバー」として計上される**一方、`make test` 自体はカバレッジを取らない（`Makefile:116-121`）。
80% 閾値は `make coverage` を実行したときのみ効き、`make test` / コミット時には効かない。

---

## 5. 経験ベース技法の資産（ISTQB 4.4 / ISO 29119-4 §6）

| ISTQB 分類 | 本リポジトリの資産 | 実体（file:line） | 判定 |
|---|---|---|---|
| エラー推測（Error Guessing） | 製品実装 + 自テスト両方に存在 | 実装: `src/autorun/error_guessing.py`（`CATALOG_CONFIDENCE=0.9`）。テスト: `tests/test_techniques_extended.py:216,227,233,238,261`（`:238` は「全欠陥カテゴリが外部タクソノミへ写像されること」、`:261` は「公式マッピングではない旨の宣言」を検査） | 適用あり(5件) |
| エラー推測（自テストへの適用） | 異常値カタログによるフジング | `tests/test_viewpoint_csv_import_fuzzing.py:68,79,88,105,126,141,164,182,198`（空 CSV / 制御文字 / 超長値の無言切り詰め禁止 / SQL 風文字列 / 列数過不足 / 重複名）、`tests/test_viewpoint_catalog_fuzzing.py:62,71,81,94` | 適用あり(13件) |
| 探索的テスト（Exploratory Testing） | 製品機能として実装（チャータ提案・セッション記録） | `src/capture/session_recorder.py`、契約 `feature_id: exploration_capture`（`quality/feature_contracts.yml:701`）、テスト `tests/test_state_exploration.py`、`tests/test_charter_proposal.py` | 適用あり（製品機能として） |
| チェックリストベーステスト（Checklist-Based） | 開発プロセス上の必須チェックリスト | `.claude/rules/functional-integrity.md:23-31` の 9 項目: happy path / failure path / timeout / cancellation / auth・login wall / robots・restriction handling / partial result・recovery / logs・evidence / user-visible error・status | 適用あり(9項目) |
| チェックリストベーステスト（機械化） | 機能契約の `failure_modes` / `required_tests` | `quality/feature_contracts.yml` 52 機能。各機能に `failure_modes`（例 `:41-48` の 6 モード）と `required_tests`（`happy_path` / `error_path` / `evidence`） | 適用あり(52機能) |
| 静的テスト（ISTQB 3章。経験ベース技法ではない） | 契約ハーネス | `scripts/quality_harness.py:79-166`。検査内容: risk_level 妥当性 `:86`、UI のみ機能の禁止 `:88-89`、宣言ファイルの実在 `:93-95`、実装機能の実行経路（route/core）保有 `:97-101`、critical/high の failure_modes・required_tests 存在 `:103-106`、宣言シンボルの core_files 内実在 `:108-110`、"UI only"/"not implemented" 等の文字列検出 `:119-134`、未登録モジュール検出 `:136-166`。回帰化: `tests/smoke/test_quality_harness.py:16,29,37,48,54`（5 件） | 適用あり(5件) |
| メタモルフィックテスト（29119-4 対象外の補助） | 製品機能として実装 | `tests/test_metamorphic.py:29,48,60,68,76,95,110`（検索フィルタの部分集合関係、ソート不変性、ページネーション整合） | 適用あり(7件) |

**ISTQB 上の位置づけの注意**: `scripts/quality_harness.py` は動的テストではなく**静的テスト（レビュー・静的解析の自動化）**である。
ISTQB 4.4 の経験ベース技法として数えると分類を誤る。最も近いのはチェックリストベースの**静的解析**であり、
実行経路の検証（動的テスト）を代替しない。この点は `.claude/rules/functional-integrity.md:11-19` の「テストが通った＝十分としない」方針と整合している。

---

## 6. 追跡可能性（テスト条件 → テストケース / ISO 29119-2 §7）

### 6.1 測定方法

`quality/feature_contracts.yml` の 52 機能について、Python スクリプトで次を実測した（読み取りのみ）:

1. `core_files` / `route_files` のモジュール名が `tests/**/*.py` 本文に出現するか
2. `feature_id` を名前に含むテストファイルが存在するか
3. 宣言 `symbols` がテスト本文に出現するか
4. 宣言 `failure_modes`（失敗モード文字列）がテスト本文に出現するか

### 6.2 結果

| 追跡の種類 | 追跡できた機能数 | 判定 |
|---|---|---|
| モジュール名レベル（core/route ファイル名がテストに出現） | 52 / 52 | 適用あり(52件) |
| シンボルレベル（宣言 symbol がテストに出現） | 52 / 52（すべての機能で 1 つ以上一致） | 適用あり(52件) |
| **feature_id 命名によるテストファイル対応** | **15 / 52** | 限定的(15件) |
| **failure_mode 単位の対応（失敗モード文字列がテストに出現）** | **37 / 52** | 限定的(37件) |

### 6.3 追跡できない要求（列挙）

**(a) `failure_modes` を宣言しているのに、その文字列が 1 つもテストコードに現れない機能（15 件）**

| feature_id | risk_level | 契約行 |
|---|---|---|
| `tenant_isolation` | **critical** | `quality/feature_contracts.yml:331` |
| `coverage_gap_report` | medium | `:570` |
| `reverse_assets` | medium | `:752` |
| `finding_ticket` | medium | `:818` |
| `ci_warnings_cleanup` | low | `:902` |
| `ux_review` | medium | `:1002` |
| `diff_severity` | high | `:1303` |
| `api_spec_recovery` | medium | `:1502` |
| `autorun_nonfunctional_judge` | high | `:1843` |
| `ui_visual_complexity` | medium | `:1885` |
| `state_transition_table` | high | `:2051` |
| `zero_wait_sample_report` | medium | `:2155` |
| `cli_mode` | high | `:2199` |
| `condition_to_testcase_link` | medium | `:2297` |
| `condition_run_status` | medium | `:2343` |

うち **critical 1 件（`tenant_isolation`）・high 4 件**（`diff_severity` / `autorun_nonfunctional_judge` / `state_transition_table` / `cli_mode`）。
※ 失敗モード名がテストに文字列として現れないことは「テストしていない」の証明ではない（別名でテストしている可能性がある）。
**この表は「機械的に追跡できない」ことの列挙であり、未テストの断定ではない。**

**(b) `feature_id` 名のテストファイルが無い機能: 37 / 52。**
名前で対応が付くのは `crawl`(5) / `login`(4) / `autorun`(12) / `settings`(3) / `doc_fusion` / `test_plan` / `old_new_comparison` / `ux_review` / `admin_audit` / `document_mbt` / `evidence_pack` / `diff_severity` / `testcase_table` / `cli_mode` / `condition_run_status` の 15 機能のみ。

**(c) ハーネスが追跡を検証していない（構造的原因）**

`scripts/quality_harness.py:103-106`:

```python
    if risk_level in RISK_LEVELS_REQUIRING_FAILURE_TESTS:
        if not feature.get("failure_modes"):
            errors.append(f"{feature_id}: {risk_level} feature lacks failure_modes")
        if not feature.get("required_tests"):
            errors.append(f"{feature_id}: {risk_level} feature lacks required_tests")
```

検査しているのは**リストが空でないこと**だけである。`required_tests: ["happy_path", "error_path", "evidence"]` と宣言されていても、
対応するテスト関数が実在するかは一切照合されない。**追跡可能性は宣言レベルで止まっており、実体との双方向トレースは成立していない。**
一方で `_validate_all_modules_registered:136-166` は「実装モジュール → 契約」の逆方向（登録漏れ）を機械的に塞いでいる。
つまり**「実装 → 契約」は自動化済み、「契約 → テスト」は未自動化**という非対称がある。

---

## 7. フロントエンド（JS）のテスト空白

### 7.1 測定結果

| 項目 | 実測 |
|---|---|
| `static/js/` のファイル数 | 51 |
| JS ユニットテスト（`*.test.js` / `*.spec.js` / `*.test.ts` / `*.spec.ts`、`node_modules` と `output/` を除く） | **0 件** |
| JS テストランナー設定（`package.json` / `jest.config.*` / `vitest.config.*`） | **リポジトリルートに存在しない**（ルートの設定ファイルは `Makefile` と `pyproject.toml` のみ） |
| カバレッジ計測 | 対象外（`--cov=src --cov=web` のみ） |

**判定: フロントエンド JS のユニットテストは該当なし(0件)。テスト実行基盤自体が未導入である。**

### 7.2 E2E による間接的な到達（区別して記載）

E2E テストのソース中にファイル名（拡張子なし）が出現する JS を数えた結果、**22 / 51 ファイル**が何らかの E2E から参照されている。

| JS モジュール | 参照する E2E ファイル数 |
|---|---|
| `autorun` | 8 |
| `history` / `viewpoints` | 各 7 |
| `results` | 6 |
| `autorun-leadbar` / `core` / `settings` | 各 5 |
| `review` | 4 |
| `autorun-decisions` / `file-preview` | 各 3 |
| `events` / `view-run-history` / `wizard` | 各 2 |
| `autorun-report` / `execution` / `markdown-lite` / `onboarding` / `qa-tools` / `recrawl` / `traceability` / `user-admin-view` / `view-run-result` | 各 1 |

**重要な限定**: この 22 件は「E2E のソースコード中にモジュール名の文字列が現れる」という**近似指標**であり、
当該 JS の行が実行された証明ではない（JS カバレッジは計測されていない）。**残り 29 / 51 ファイルは、名前すら E2E に現れない。**

参考: `quality/feature_contracts.yml` の `ui_files` に登録されている `static/js/*.js` は 29 ファイル（`grep -o '"static/js/[a-z0-9_-]*\.js"' | sort -u | wc -l`）。
契約に載っていない JS が 22 ファイル存在する計算になる（51 − 29）。ただし `quality_harness.py` の未登録検出（`FEATURE_SOURCE_ROOTS`）が
`static/js` を走査対象にしているかは**未確認**（`_validate_no_unimplemented_user_paths:120` は `static/js` を走査するが、これは文字列検出であり登録漏れ検出ではない）。

---

## 8. 技法適用のギャップと推奨

### 8.1 ギャップ一覧（影響度順）

| # | ギャップ | 実測根拠 | 影響 |
|---|---|---|---|
| G-1 | 製品が実装している技法を、自身のテスト設計に使っていない | デシジョンテーブル (B)=0、ペアワイズ (B)=0、クラシフィケーションツリー (B)=0 | ドッグフーディング不成立。技法エンジンの実用性が自プロダクトで検証されていない |
| G-2 | 境界値がテストから追跡できない | 定数 295 行中、テストが定数名を参照するのは 3 件（`MAX_SUGGESTIONS` / `SUGGESTION_THRESHOLD` / `MAX_FAILED_ATTEMPTS`）。他は値のハードコードか未テスト | 定数を変更してもテストが赤くならない。`MAX_PARALLELISM=8` / `DEFAULT_MAX_PAGES=50` / 各種 TIMEOUT は境界テスト皆無 |
| G-3 | フロントエンド 51 JS のユニットテストが 0、テスト基盤も無い | §7 | ロジックを持つ JS（`autorun.js` / `wizard.js` 等）の分岐が一切自動検証されない。E2E 失敗まで欠陥が可視化されない |
| G-4 | 判定網羅（branch coverage）が未計測 | `--cov-branch` なし。命令網羅 80% のみ | if/else の片側しか通っていなくても閾値を満たす |
| G-5 | 契約 → テストの追跡が宣言止まり | `quality_harness.py:103-106` は空でないことのみ検査。failure_mode がテストに現れない機能 15/52（critical 1・high 4） | 「required_tests を書いた」が「テストがある」を意味しない |
| G-6 | カバレッジが CI/コミット経路に載っていない | `make test`（`Makefile:116-121`）はカバレッジ無し。80% 閾値は `make coverage` を明示実行した時だけ | 閾値が実質的なゲートになっていない |
| G-7 | タイムアウト・キャンセルのチェックリスト項目に対する体系的テストが不足 | `.claude/rules/functional-integrity.md:25-26` は timeout / cancellation を必須としているが、タイムアウト定数（#8〜#10, TIMEOUT_SEC=120 等）の境界テストは 0 件 | チェックリストが宣言され、実装で満たされていない |

### 8.2 推奨（ISO/IEC/IEEE 29119-4 の技法選択指針に沿った優先順）

| 優先 | 推奨 | 対象 | 期待効果 |
|---|---|---|---|
| 1 | 境界値テストで**定数を import して参照**する規約に変更する。まず G-2 の「該当なし」12 定数へ `n-1 / n / n+1` を適用 | `src/mbt/document_model.py`、`src/mbt/pairwise.py`、`src/main.py`、`src/viewport/layout_failures.py`、`src/capture/finding_reporter.py`、`src/llm/activity_log.py` | 定数変更の回帰検出。ISO 29119-4 §5.2（BVA）準拠 |
| 2 | `--cov-branch` を `Makefile:129` へ追加し、判定網羅を計測開始（閾値は当面据え置き） | Makefile | G-4 解消。1 行変更で効果が出る |
| 3 | 権限×テナント×ロールの組合せへ**ペアワイズ**を適用（自製 `src/mbt/pairwise.py` を使う） | `tenant_isolation` / `tenant_membership` / `admin_audit` の E2E | G-1 と G-5（critical の追跡欠落）を同時に解消。ドッグフーディングにもなる |
| 4 | JS テスト基盤（Vitest）を導入し、まず純ロジック JS（`markdown-lite.js` / `core.js` / `events.js`）から着手 | `static/js/` | G-3 の着手。51 ファイル全部ではなく、E2E に名前すら現れない 29 ファイルを優先 |
| 5 | `quality_harness.py` に「`failure_modes` の各項目が、いずれかのテスト関数名または docstring に現れること」の検査を追加 | `scripts/quality_harness.py:103-106` | G-5 の機械化。「実装 → 契約」と同じ強度を「契約 → テスト」にも与える |
| 6 | タイムアウト系にデシジョンテーブルを適用（条件: 到達可否 × タイムアウト有無 × リトライ残数 → 動作） | `src/crawler/politeness.py`（`BACKOFF_MAX_RETRIES=5`）、`src/crawler/auto_login.py` | G-1・G-7 の同時解消 |

---

## 9. この分析の弱点

1. **静的読み取りのみで、テストを 1 件も実行していない（未実行）。**したがって「テストが存在する」は言えても「テストが通る」「その行が実際に実行される」は本文書では未検証である。特に §7 の E2E 間接カバレッジ 22/51 は文字列一致による近似であり、実行の証明ではない。
2. **境界値の突合は 295 行中 17 定数（約 6%）のサンプルにとどまる。**残り 278 行は「未確認」であり、「該当なし」と読み替えてはならない。同様に §6.3(a) の 15 機能は「失敗モード名で機械追跡できない」ことの列挙であって、未テストの断定ではない（別名でテストされている可能性を排除していない）。
3. **(A) と (B) の切り分けは判定者の解釈に依存する。**例えば `tests/test_state_table.py` の 0-switch / 1-switch テストは「技法エンジンのテスト」だが、その中で状態遷移の考え方を使ってケースを設計している側面もあり、(B) 側に数える立場もありうる。本文書は「被テスト対象が製品の技法モジュールか、製品の一般機能か」で機械的に切っている。
