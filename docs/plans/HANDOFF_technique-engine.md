# 引き継ぎ — テスト技法エンジンの研究ベース更新（Wave R / Wave 1 完了、Wave 2 以降が未着手）

対象読者: 本作業を引き継ぐエージェント（Codex / 別セッションの Claude）。
このファイルだけ読めば文脈ゼロから再開できるように書いてある。

- 作成: 2026-07-28
- 完了済みコミット: `14abfc4`（main にマージ済み）
- 元の計画書: `~/.claude/plans/floating-brewing-quiche.md`（このリポジトリ外）。
  必要な内容は本ファイルへ転記済みなので、無くても再開できる。

---

## 1. なぜこの作業をしているか

WebSpec2Doc のテスト技法生成（BVA・デシジョンテーブル・ペアワイズ・状態遷移ほか）は、
実測データからの決定的生成という設計は良いが、アルゴリズム自体が自前初版のままで
先行研究と突合されていなかった。加えて、同じ技法が複数箇所に重複実装され、
そのうち 1 つは**アルゴリズムとして誤っていた**（後述）。

目的は 2 つ:

1. 各技法を先行研究・標準（ISTQB / ISO 29119-4 / NIST SP 800-142 等）に照らして正す
2. 重複実装を単一の正準実装（`src/techniques/`）へ統合し、更新が 1 箇所で効くようにする

## 2. 守るべき設計原則（これを破る変更は入れない）

- **evidence-only**: 実測にない値を捏造しない。実測由来の confidence は 1.0、
  カタログ・一般知識由来は 0.9 とし、混ぜない。値が作れない場合は
  「例生成不能・手動作成要」と明示して空にする
- **決定的純関数**: 乱数・時刻を使わない。同一入力から必ず同一出力（差分比較のため）
- **打ち切りを黙って行わない**: 上限で切った場合は件数だけでなく**内容**を出力へ残す
- frozen dataclass / ファイル 800 行上限 / 日本語 docstring
- 各技法の docstring に**一次出典**（著者・年・タイトル）を書く
- import は `src` をルートとした平坦名（`from generator.test_design import ...`）

## 3. 完了済み（Wave R + Wave 1）

### Wave R — 先行研究調査

`docs/research/2026-07-28_lit-review-*.md` に 6 本。**後続ウェーブの根拠なので着手前に該当分を読むこと。**

| ファイル | 後続で使う主な結論 |
|---|---|
| `-combinatorial.md` | 現行の決定的貪欲は Bryce–Colbourn 系譜で裏付けあり。IPOG は優位性の一次データ無しで**不採用**。NIST SP 800-142 本文で相互作用ルールを一次確認（2-way で 93%、4〜6-way で 100%）。制約は「生成段階で除外」が正解 |
| `-boundary-domain.md` | 3値法（境界±1）維持が妥当（ISTQB CTFL v4.0 本文で確認）。AutoBVA 系は SUT 大量実行前提で evidence-only と衝突→**不採用**。正規表現逆生成は Rex(ICST 2010) に一般解があり、現行の辞書4種は保守的→**条件付き採用** |
| `-fsm-testing.md` | **0-switch = 全遷移 / 1-switch = 連続2遷移で確定**（Rechtberger et al. 2022 全文）。ノード訪問は Node Coverage で n-switch 系列外。W 法は状態が URL/DOM で直接観測可能なら W={ε} に退化→**不採用（根拠は文書化済み）**。Binder N+ は prime path 実装が包含済みで追加不要。Crawljax の DOM 同値判定（Levenshtein + 閾値）は `page_states` 深化の候補 |
| `-metamorphic.md` | 現行 3MR は標準パターンに正対応。「3〜6 個の多様な MR でオラクル検出可能欠陥の 90% 以上」の実証あり。追加推奨: URL 正規化・冪等性・invertive（絞込解除）・viewport 実装化 |
| `-defect-taxonomy.md` | OWASP WSTG **v4.2 の実 ID を一次確認**（INPV-01〜19 / SESS-01〜09 / BUSL-01〜09）。19 分類中 8 分類に実 ID 割当可。ODC・Beizer・Whittaker は一次入手不可→**引用禁止リスト入り**（現実装の「IEEE 1044: Data」等の記述も未検証と指摘されている） |
| `-partition-decision.md` | 現行の n+1 規則は **unique-cause MC/DC と同型**（NASA/TM-2001-210876 で一次裏付け）。TSL の error/single は属性ラベル付与のみ採用。トレースバック規則は見送り |

各レポート末尾に「引用禁止リスト」と「WebSpec2Doc への適用判断」表がある。**引用禁止リストの項目を根拠として使わないこと。**

### Wave 1 — 技法エンジン新設 + 組合せ統合 + 偽ペアワイズ修正

**修正した欠陥**: `src/analyzer/test_conditions.py::generate_pairwise_cases` は
「先頭フィールドの各値 × 残りのラウンドロビン」という近似で、2-way 被覆を保証しないのに
「ペアワイズ」を名乗っていた。デシジョンテーブルの 5 項目以上の縮退にも使われていた。

**新設**: `src/techniques/`

| ファイル | 内容 |
|---|---|
| `combinatorial.py` | t-way 被覆配列の正準実装。決定的な貪欲 AETG 系（Cohen et al. IEEE TSE 1997）。**forbidden tuples / seeding / mixed-strength** に対応。制約で被覆できなかった t-tuple は `uncoverable` に全件記録 |
| `verify.py` | 性質検証器。`verify_t_way_coverage` が全数え上げで被覆率を検査。**アルゴリズムを信用せず出力を検査する**方針で、テスト期待値の更新根拠にもこれを使う |
| `__init__.py` | facade |

**委譲へ変更（本体削除・出力形状は不変）**:
- `src/generator/test_design.py`: `_greedy_cover` ほか 4 関数を削除し委譲
- `src/mbt/pairwise.py`: 貪欲実装本体を削除し委譲
- `src/analyzer/test_conditions.py`: 偽実装を削除し委譲

**テスト**: `tests/test_techniques_combinatorial.py`（水準2-5 × 因子2-8 の格子で property test）、
`tests/test_techniques_verify.py`（検証器自体の正しさ + 各アダプタの被覆）。計 47 件。

**検証結果**: 全 2798 テスト pass / `quality_harness.py` PASS（validated_features 45）/ ruff clean。
デモサイト `output/127.0.0.1:8767/report.json` での前後比較でケース数・決定性とも同一
（採取スクリプトは §6 参照）。

---

## 4. 未着手（Wave 2 以降）— ここから再開する

### Wave 2: 状態遷移統合 + N-switch ラベル修正 ★次にやる

**既知バグ**: `src/graph/transition_graph.py::generate_transition_tests` の
0/1/2-switch ラベルが Chow の定義から 1 つずれている（0-switch がノード訪問になっている）。
同ファイルの `compute_switch_coverage` と `src/graph/state_table.py` は**正しい定義**。
そのため `generate_transition_tests(coverage="1-switch")` の出力を
`compute_switch_coverage` に渡すと 1-switch 率が常に 0 になる。

やること:
1. `src/techniques/state_machine.py` を新設（正しい Chow N-switch。transition tour も。
   W 法は `-fsm-testing.md` の退化根拠を docstring に書いた上で**不採用**とする）
2. `transition_graph.generate_transition_tests` の `coverage` 引数を
   `"node"` / `"0-switch"`（= 全遷移）/ `"1-switch"`（= 連続 2 遷移）へ再定義。
   呼び出し元 `src/main.py`・`src/generator/html_reporter.py` の表示文言・
   `tests/test_transition_graph.py` を**同時に**更新する
3. `state_table.py` の 0/1-switch 算出を state_machine へ委譲（定義が既に正しいので出力不変）
4. `mbt/document_model.py` は prime_path 等をそのままにし、switch 系のみ委譲

**注意**: レポート表示文言が変わる = UI 変更扱い。**`make verify-ui` が必須**（§5 参照）。

### Wave 3: 境界値 7 箇所統合

`src/techniques/boundary.py` を新設し、以下を委譲へ:
`analyzer/bva.py`（本体をここへ移設し shim 化）/ `generator/test_design._bva_cases` /
`autorun/techniques.boundary_values` / `autorun/domain_analysis.py` /
`mbt/test_data.py` / `analyzer/rule_injector.py` / `analyzer/test_conditions` の代表値導出。

**最多の呼び出し箇所なので 1 コミット = 1 箇所の委譲**にし、毎回 pre-commit を通す。
`-boundary-domain.md` の「正規表現逆生成の条件付き採用」もここで判断する。

### Wave 4: メタモルフィック拡充

`src/techniques/metamorphic.py` 新設。`mbt/metamorphic.py` の既存 3MR を委譲し、
**未実装のまま定数だけ存在する `MR_VIEWPORT_CONSISTENCY` を実装**する
（`src/viewport/` の実測比較結果を入力に使う。viewport 実測が無いサイトでは
evidence-only に従い「適用不能」と明示出力）。`-metamorphic.md` の追加推奨 MR も検討。

### Wave 5: タクソノミ・決定表強化

- `autorun/error_guessing.py`: `-defect-taxonomy.md` で**一次確認済みの** WSTG 実 ID へ更新。
  一次確認できなかった ODC/IEEE 1044 の記述は「未確認」扱いへ直す
- `autorun/cause_effect.py`: n+1 規則が unique-cause MC/DC と同型である旨を docstring に明記。
  M 制約でマスクされた原因を「未検証」と扱えているかの実装確認（`-partition-decision.md` 表#4）
- `autorun/classification_tree.py`: `MAX_CLASSES_PER_CLASSIFICATION` の切り捨て内容を記録（未対応の残弱点）
- `autorun/orthogonal_array.py`: `verify_orthogonality` を `techniques/verify.py` へ移設参照

### Wave 6: クリーンアップ

shim 削除可否（grep 全数確認後）/ 全技法 docstring の出典最終監査 / 前後比較レポート。

---

## 5. 作業のルール（このリポジトリ固有・省略不可）

```bash
# 使う venv は venv/（.venv/ も存在するが未使用。run.sh と揃える）
venv/bin/python -m pytest tests/ -q --ignore=tests/e2e   # L1/L2
venv/bin/python scripts/quality_harness.py               # 機能契約ゲート
make verify-ui                                           # L3 E2E（UI変更時のみ・必須）
```

- **新しい `src/**.py` を追加したら `quality/feature_contracts.yml` へ登録が必須。**
  未登録だと `quality_harness.py` が FAIL し、pre-commit がコミットを止める。
  Wave 1 では `technique_engine` という feature を追加した。同じ要領で追記する
- **UI（HTML/JS/CSS）を変更したら `make verify-ui` が必須。** 成功時に `.ui-verified`
  マーカーが更新され、これが 2 時間以内でないと pre-commit がコミットを拒否する
- `make verify-ui` は**自前でアプリを起動する**。事前に 8765 番で別のアプリ
  （`scripts/demo.sh` 等）を動かしていると、それを再利用してしまい
  初回ツアーの overlay でクリックが遮られて落ちる。**E2E 前にポートを空けること**
- 静的アセット（JS/CSS）のキャッシュバスターはアプリ**起動時刻**で固定される。
  JS/CSS を編集したら**サーバー再起動が必要**（ブラウザリロードだけでは反映されない）
- pre-commit は全テストを実行する。コミットに 20 秒ほどかかるのは正常
- 区切りごとに branch → commit → `git merge --no-ff` で main へ。main は保護なし
- `tests/test_auto_run.py::TestPhaseDiscoverLoginConsolidation` の 2 件は
  **全体実行時に稀に落ちるフレーキー**（単体では常に pass、ベースラインでも再現）。
  Wave 1 の変更とは無関係であることを確認済み

## 6. 前後比較の採取方法（各ウェーブで実施）

ウェーブ着手前と完了後に同じスクリプトを流し、ケース数・被覆・決定性を diff する。
**被覆が下がったらマージしない。**

スクリプトはセッションのスクラッチパッドに置いていたため残っていない。
以下の内容で再作成すること（`output/127.0.0.1:8767/report.json` が入力）。

```python
import json, sys
sys.path.insert(0, "src")
from generator.test_design import TestDesignParams, build_test_design
from generator.testcase_table import build_testcase_table
from autorun.techniques import apply_all, apply_cross_screen
from graph.state_table import build_state_transition_report

report = json.load(open("output/127.0.0.1:8767/report.json"))
screens = report["screens"]
td = build_test_design(report, TestDesignParams())
out = {
    "test_design": {
        s.page_id: {
            "bva": sum(len(t.cases) for t in s.bva),
            "dt": len(s.decision_table.rules) if s.decision_table else 0,
            "pw": len(s.pairwise.rows) if s.pairwise else 0,
            "st": len(s.state_transitions.sequences) if s.state_transitions else 0,
        }
        for s in td.screens
    },
    "testcase_rows": len(build_testcase_table(report, td)),
    "autorun": {apply_all(sc)["page_id"]: apply_all(sc)["technique_case_counts"] for sc in screens},
    "state_table": build_state_transition_report(screens)["summary"],
    # 決定性: 同一入力で 2 回生成して完全一致するか
    "deterministic": td == build_test_design(report, TestDesignParams()),
}
print(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True))
```

Wave 1 完了時点の値（Wave 2 のベースライン）:
`P001{bva:0,dt:0,pw:0,st:2} / P002{bva:2,dt:0,pw:0,st:2} / P003{bva:6,dt:4,pw:6,st:3}`、
testcase_rows=36、state_table の valid_transition_count=9 / 0-switch=9 / 1-switch=25、
deterministic=True。

## 7. 未解決・注意している点

- **Wave 1 の弱点**: `combinatorial` の制約処理は SAT/CSP ではなく貪欲充填の近似。
  制約が強いと本来被覆可能な組を `uncoverable` に誤分類しうる（安全側に倒しているが最適ではない）。
  docstring に明記済み
- mixed-strength の `_gain` は強度間の重み付けをしていない（小強度の組が早く尽きるため
  実質大強度が支配する、という前提。実測での検証はしていない）
- 文献レビュー 6 本とも**論文本文の精読は限定的**。一次確認できた範囲は各レポートの
  「引用禁止リスト」で明示されている。ここに載っている項目を根拠に実装判断をしないこと
- `src/mbt/` パッケージは CLI（`src/main.py`）から呼ばれず
  `web/services/document_autorun.py` 経由でのみ使われる。CLI 利用者には
  ペアワイズ・メタモルフィック・テストデータ生成が届いていない（設計判断が必要な既知の穴）
