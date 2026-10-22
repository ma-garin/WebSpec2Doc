# System06 独立レビュー 2（PR #323 / feat/docassure-pr1）

- 審査者: 実装に関与していない独立レビュアー（読み取り専用。本ファイルの作成以外は変更していない）
- 対象: HEAD 5022001（origin/main...HEAD）
- 実行した確認: `pytest tests/test_docassure_*.py`（perf を除く）→ 266 passed / 31.7s。holdout v1/v2/v3 を現行コードで再採点。下記の再現スクリプト 3 本
- 実行していないもの: test_docassure_perf.py、実ブラウザでの GUI 操作、実 LLM 送信（いずれも未検証）

## BLOCKER（1 件）

### B-1 人の判断を 1 件記録すると、組織ポリシー・System02 のテスト・実行結果が外れたまま再分析・保存される
- 場所: web/routes/doc_assure.py:144-151（`decide`）。`pipeline.analyze(docs, decisions=...)` に `pack_extra`（組織ポリシー）、`profile`、`design_tests`、`execution` を渡していない。`analyze` 側（:68-82）は渡している
- 影響: 判断を 1 件入れるだけで、ポリシーで追加した必須項目・曖昧語の指摘が消え、無効化した規則の指摘が戻る。System02 の verifies 辺と実行結果も消え、Traceability と準備状態が判断と無関係に変わる。finding_edit を持つ利用者なら誰でも、判断操作でポリシーによる指摘を消せる（ゲートの迂回）
- 再現（実測）: 2 文書で `pipeline.analyze(d, pack_extra={'required_items':['監査ログ','バックアップ']})` → 指摘 4 件。`decide` と同じ呼び方の `pipeline.analyze(d)` → 指摘 0 件
- 修正案: 再分析の引数を組み立てる関数を 1 つにまとめ、`analyze` と `decide` の両方で使う。プロファイルは保存しておく。再分析せずに `decisions.apply` だけを適用し直して readiness を再計算する方法でもよい。「判断の前後で、判断対象以外の指摘の集合が変わらない」ことを確かめる回帰テストを追加する

## MAJOR（7 件）

### M-1 holdout v3 が汚染されている（結果を見た後に検出器を調整した）
- 根拠: holdout_v3 は acbb69a で追加され、その result.json の FN/FP 一覧も同じコミットで入っている。その後 9356a46「規則とテスト可能性の汎化」で testability.py と detectors.py を変えた。現行コードで v3 を再採点すると、変化は**ちょうど v3 の 3 件**（h3-ut-02 の FN と h3-fp-23・h3-sg-01 の FP）だけが直るというものだった。h3-ut-02 は「十分な性能」で、9356a46 の「曖昧語の『十分』を 10 分と誤読しない」修正と一致する
- 同じコミットで追加した `FAQ`（known_acronyms）と `RE_CATEGORY_COUNT`（「段階」）は holdout_v2 にしか出てこない語。v2 は「改善に使用」と申告済みなので、申告とは矛盾しない
- 数値の食い違い: QUALITY_REPORT.md:8-11 と holdout_v2/v3 の result.json は調整前の値のまま。現行コードでは v3 が P0.540/R0.491/F1 0.514/critR 0.528、v2 が P0.896/R0.729。v1 の行（0.878）も古く、現行は 0.935
- 修正案: v3 を「改善に使用」に格下げする。検出器を読まず、結果も見ない作者による v4 を封印して作り、1 回だけ測る。3 セットとも現行コードで再生成し、QUALITY_REPORT に「どのコミットで測ったか」を明記する

### M-2 finding_id が文書間で衝突し、人の判断が別文書の指摘にも適用される
- 場所: web/services/docassure/rules/engine.py:92。ID は `{rule}:{requirement_id or L行}:{n}` で document_id を含まない
- 再現（実測）: 文書 A と B に同じ `SR-1 システムは適切に応答すること。` → 両方とも `AMB-001:SR-1:1`。decisions.apply（decisions.py:31）は ID で引くため、A への採否・waiver が B にも効く。要件定義と設計で同じ ID を使うのは普通のことで、実運用で起きる
- 付随: ID の無い要件は `RU-<doc>-<連番>`（requirement_engine.py:195）で、行の挿入で番号がずれる。過去の判断が別の指摘に付け替わる（人の判断の誤適用）
- 修正案: finding_id に document_id と、正規化した抜粋のハッシュを含める（矛盾の conflict_id と同じ方式）。ID の形式を変えるので、既存 decisions の移行も要る

### M-3 判断・再分析・AI レビューの保存が排他されず、判断が消える
- 場所: doc_assure.py:84（analyze の save）、:149（decide の再分析 save）、:194（review の save）はロックの外で読み・書きしている。ロック付きは store.add_decision（store.py:47）だけ
- 再現手順: 判断 2 件をほぼ同時に POST する。または分析中に判断を POST する。後から書いた save が、読み込み時点の decisions で上書きするので、先の判断が消える
- 修正案: 読み込みから保存までを `perm.locked(doc_dir)` で囲む。または decisions を別のサイドカーに分け、分析結果の保存では触れない

### M-4 AI Review Board の送信量に上限が無い（要件数 × 12 観点を同期で送る）
- 場所: review_board.py:83-93。全要件 × REVIEWERS 12 件を、HTTP リクエストの中で直列に送る（timeout 30 秒/件）
- 影響: 要件 1,000 件で 12,000 回送信し、リクエストは終わらない。外部送信の量が同意画面で示されていない（consent は宛先しか示していない。doc_assure.py:184）。_CACHE（:41）は全テナント共通で無制限に増える
- 修正案: 1 回の送信件数に上限を設ける（対象要件を選ばせる、または重大度の上位 N 件）。同意の応答に送信予定の件数と文字数を含める。非同期のジョブにする。キャッシュは LRU にしてテナントを鍵に含める

### M-5 判断 1 件ごとに全文書を同期で再分析する（10,000 行で 1 クリック 40 秒超）
- 場所: doc_assure.py:144-151。PERF_REPORT では 10,000 行の analyze が 43.2 秒
- 修正案: B-1 の修正案（decisions.apply と readiness の再計算だけで済ませる）で同時に解消する

### M-6 計算量: trace_graph の 2 つ目の O(n²) と、比較のたびに 2-gram を作り直す処理
- 既知の trace_graph.py:105-113（要件の総当たり）に加えて、:130-134 で明示 ID の無いテスト 1 件ごとに全要件と dice を取る（O(T×R)）。`dice()` は呼ぶたびに両方の 2-gram を作り直す（:20, :35-36）。glossary.py:103 も語の数 × 定義語の数の部分一致
- 修正案: 要件の gram を 1 回だけ作ってキャッシュする。conflict.py の `_similar_candidates`（転置索引＋prefix filter）を trace でも使う

### M-7 System02 連携が実プロジェクトと往復していない
- 場所: links_sys02.py:18-20, 33-41, 49-67。登録先は合成ドメイン `docassure-<iid>` で、画面・URL・手順（steps=[]）が無い。System02 の公開 API を通さず、私的関数 `_ta2._loaded` `_next_id` `_now` でレコードを直接作っている
- 影響: 利用者の実際の System02 プロジェクトにテスト案が出てこない。実行結果が戻る経路は、誰かがこの合成ドメインで実行した場合に限られ、実質的に往復しない。System02 側の検証も通らない
- 修正案: 登録先を System02 の既存ドメインから選ばせる。ta2_store の公開関数（作成と検証）を使う。往復（登録→実行→as_execution）を 1 本の結合テストで通す

## MINOR（8 件）

- m-1 CSV 注入対策が `= + - @` だけ（report.py:80）。TAB・CR と、先頭の空白の後の `=` が抜けている（OWASP の推奨範囲）。矛盾（conflicts）は CSV に出ない
- m-2 conflict への waiver を受け付けるが効かない: decide（doc_assure.py:127）は conflict を対象に waived を通すのに、decisions._CONFLICT（decisions.py:11）に waived が無いため、黙って無視される。400 で返すか、反映させるか、どちらかにする
- m-3 readiness.py:28 は critical の矛盾で DECIDED を未解決として扱い、:60（high）は _DONE で解決として扱う。重大度によって「人の判断」の意味が変わる。仕様として明文化するか、そろえる
- m-4 GUI に内部語が出る: 理由文の `trace coverage 0.5 < 0.8`、`approved=False`、`high 指摘`、`critical 矛盾` が jp()（docassure.js:37）で訳されない。readiness の理由文は表示用の文と内部用の値に分ける
- m-5 System09 連携: 押すたびに変更要求（CR）を新規作成する（links_sys09.py:148）。差分のハッシュで重複を抑える
- m-6 GET 系の閲覧 API に権限デコレータが無い（doc_assure.py:106-108 ほか）。docverify の既存の慣例と同じで、テナント境界は store が担っているので実害は低い。閲覧の役割が導入されたときに抜けやすい
- m-7 UI 契約テスト（tests/test_docassure_ui_contract.py）は JS のソースを正規表現で探すだけで、描画を見ていない。B-1・M-2・M-3 を捕まえるテストが無い（判断の前後の不変性、文書間の ID 衝突、同時更新）
- m-8 docs の食い違い: QUALITY_REPORT.md:30 の「System01/02/09 連携は JSON を返すだけで未結線（wired:false）」は 96e4a12 で結線した後も残っている。/tests・/alignment は今も `wired:False` を返し、結線済みの system01/02/09 経路と二重になっている

## 観点別の所見（問題が無かったもの）

- テナント分離: store は docverify.doc_dir を通してテナント境界を検査している。System01 の観測元は scoped_output_dir の中に限られ、ドメインも検証している。System09 は roles.require で守られている
- XSS: docassure*.js の innerHTML へ入れる値はすべて esc（`& < > " '`）を通している
- Product Truth: 矛盾は truth=UNKNOWN・status=UNRESOLVED。スコアは評価不能を None にし、100/0 にしない。coverage の実行系は NOT_EVALUATED。AI の指摘は常に CANDIDATE で、根拠ガード・反証で棄却している。System01 の「未観測≠不在」の注記もある
- 監査: analyze・decision・review・sys02 push は記録している。alignment と sys09 analyze の監査は未確認

## 10 軸の採点（0〜4・独立）

| 軸 | 点 |
|---|---|
| Architecture | 2 |
| Requirement Intelligence | 2 |
| Quality Detection | 1 |
| Cross-document | 2 |
| Traceability | 2 |
| AI Review | 2 |
| Product Truth | 2 |
| Security | 3 |
| UX | 2 |
| Maintainability | 2 |

- Architecture: 小さなモジュールに分けている。一方で再分析の経路が 2 系統あり、ずれている（B-1）。保存も排他されていない（M-3）
- Requirement Intelligence: 要件単位への分解と出所（OBSERVED/DERIVED/INFERRED）の区別はある。ID が無い要件は連番 ID で不安定（M-2）
- Quality Detection: 未見データで F1 0.49〜0.51、重大再現率 0.5。その v3 も汚染された（M-1）。目標 0.98 から遠い
- Cross-document: 数値・権限・時系列の矛盾をバケット化している。finding_id の衝突で、文書間の判断が混ざる（M-2）
- Traceability: 明示リンクと推測リンクを区別し、孤立は CANDIDATE。O(n²) が 2 か所残る（M-6）
- AI Review: 根拠ガード・反証・合議・同意・伏せ字はある。送信量の上限と非同期化が無い（M-4）
- Product Truth: 未評価を点数にしない規律は守られている。判断 1 件で指摘が消える（B-1）、判断が別の指摘に付く（M-2）
- Security: テナント境界・XSS・CSRF（既存の guard）・入力長の制限はある。CSV の対策と LLM の送信量に穴がある
- UX: 状態の和訳と「推測」の表示はある。理由文に内部語が残る（m-4）。判断のたびに 40 秒待たされうる（M-5）
- Maintainability: テスト 266 件はすべて PASS。不変性・同時実行・ID 衝突のテストが無く、UI テストはソースの文字列照合（m-7）

## マージ可否

**不可**（BLOCKER 1 件。B-1 を直し、M-1 の数値を現行コードで測り直すまではマージしない）。
