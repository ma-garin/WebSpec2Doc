# 第7弾 設計書 — 即効・小粒（C: プライムパス網羅 / F: a11y主張境界 / A: 性能観測）

- 作成日: 2026-07-19 / ステータス: **レビュー待ち**
- 根拠: `docs/research/2026-07-19_先行研究調査.md`（③MBT理論・⑥a11y限界研究・CWV調査）
- 実装担当: Opus 4.8 / 粒度方針: 本書のみで実装再現できるレベル

## 主張境界

| 機能 | 主張してよい | 主張してはならない |
|---|---|---|
| C プライムパス | 選定基準の定義とカバレッジ実測値 | パス網羅が品質を保証すること |
| F a11yスコープ | axe が自動検出した違反の記録 | WCAG準拠・アクセシビリティの十分性 |
| A 性能観測 | この環境での単一試行のラボ観測値 | 実利用者の体感・Google評価値（CrUX） |

---

## C. プライムパス網羅（第4のパス選定基準）

### 目的
現行の頂点網羅・エッジ網羅はループを1周しか踏まない。プライムパス網羅（Ammann & Offutt）は「他の単純パスの部分パスにならない極大単純パス」を全て踏む基準で、**ループの検証を有限パス数で保証**し、エッジ網羅を包含する。

### 定義（実装が従うべき仕様）
- 単純パス: 頂点の重複がないパス。ただし**先頭=末尾の一致のみ許す**（サイクルを1周として扱う）
- プライムパス: 単純パスであり、かつ他のいかなる単純パスの真部分パスでもないもの

### 実装
`src/mbt/document_model.py` に基準 `PRIME_PATH_COVERAGE = "prime_path"` を追加。

```python
def _prime_paths(graph: nx.DiGraph) -> list[tuple[str, ...]]:
    """全プライムパスを列挙する（決定的・辞書順）。"""
def _prime_path_test_paths(graph, entries, primes) -> list[list[str]]:
    """各プライムパスを、entry からの最短プレフィクスで実行可能パスへ延長する。"""
```

- 列挙: 全頂点起点のDFSで単純パスを伸ばし、これ以上伸ばせないもの＋先頭=末尾のサイクルを収集 → 部分パス関係で極大のみ残す
- 実行パス化: プライムパス p の先頭ノードへ entry から `nx.shortest_path` で到達するプレフィクスを付けて tour する。entry から到達不能な p は `unreachable_prime_paths` として**捨てずに記録**
- 打ち切り: 既存の `MAX_PATHS` を適用し、`truncation_reason="max_paths_exceeded"` と `available_path_count`（=全プライムパス数）を summary へ。組合せ爆発対策としてパス長上限 `MAX_PRIME_PATH_LENGTH = 30`、列挙数上限 `MAX_PRIME_ENUMERATION = 5000` を置き、上限到達時は summary に `enumeration_truncated: true` を明示（黙って間引かない）
- coverage: covered = テストパス群の部分パスとして踏まれたプライムパス数 / total = 全プライムパス数

### 配線
- `web/services/document_autorun.py` の `parse_document_autorun_config`: 許容値へ `prime_path` を追加
- UI `templates/partials/view-auto-run.html` のパス選定基準 select へ「全経路パターンを通る（プライムパス）」を追加、`static/js/autorun-document.js` は既存のまま（値渡しのみ）
- OpenAPI docstring・`docs/userguide.md` の基準説明表を更新

### 受け入れ基準
- AC-C1: 教科書例（ダイヤモンド+自己ループのグラフ）でプライムパス集合が手計算と一致
- AC-C2: prime_path のテストパス群はエッジ網羅を満たす（全エッジが踏まれる）
- AC-C3: 同一入力→同一出力（決定的）
- AC-C4: entry 到達不能なプライムパスが `unreachable_prime_paths` に列挙される
- AC-C5: 列挙上限到達時に `enumeration_truncated` が true になり、例外は出ない

---

## F. UXレビューへの自動検査限界の明記

### 目的
自動a11y検査が検出できるのはWCAG基準の一部（業界報告で基準の30–40%、実問題件数ではaxe-coreで約57%）。現行のUXレビュー成果物はこの限界を明示しておらず、evidence-only原則の未適用箇所になっている。

### 実装
- `src/ux/axe_runner.py` の結果ペイロードへ `claim_scope: "automated_detectable_subset_only"` と `claim_notice` を追加:
  > 本結果は自動検出可能な範囲の観測である。自動ツールが検出できるのはWCAG基準の一部であり、キーボード操作・スクリーンリーダー・代替テキストの妥当性など人の判断を要する検査の代替にはならない。
- `src/generator/ux_reporter.py`（HTML/MD出力）の冒頭へ同文を固定表示
- 数値（30-40%等）は**成果物には書かない**（出典の経年変化で嘘になるため）。調査文書への参照のみ

### 受け入れ基準
- AC-F1: ux_review の JSON/HTML/MD すべての先頭に claim_notice が含まれる
- AC-F2: 既存のaxe検出結果の構造は変わらない（追加のみ・後方互換）

---

## A. 性能観測（Core Web Vitals ラボ計測）

### 目的
クロールは既に全画面をブラウザで開いている。ナビゲーション前に PerformanceObserver を登録するだけで、追加巡回コストゼロで「画面別性能一覧」を成果物化できる。

### 計測対象と非対象
- 計測: LCP / CLS / TTFB / DOMContentLoaded / load / transferSize
- **非計測: INP**（実ユーザー入力が必要なフィールド専用指標。ラボでは原理的に不可 — この事実を成果物にも明記する）

### 実装
新規 `src/crawler/performance_probe.py`:

```python
CLAIM_SCOPE = "lab_single_run_this_environment"
PERFORMANCE_INIT_SCRIPT: str  # LCP/CLS の PerformanceObserver を buffered で登録

@dataclass(frozen=True)
class PerformanceSample:
    lcp_ms: float; cls: float; ttfb_ms: float
    dcl_ms: float; load_ms: float; transfer_bytes: int
    claim_scope: str = CLAIM_SCOPE
    def to_dict(self) -> dict: ...

def install_performance_observers(page) -> None   # 失敗してもクロール続行
def collect_performance(page) -> PerformanceSample | None  # 計測不能は None（0で偽装しない）
```

- `PageData` へ `performance: Any | None = None` を追加
- `crawl_page` 冒頭で `install_performance_observers(page)`、`PageData` 構築直前に `collect_performance(page)`
- `src/generator/json_reporter.py`: screen へ `performance` を出力（None は省略）
- `src/generator/html_reporter.py`: サマリー節の下に「性能観測」表（画面 / LCP / CLS / TTFB、`tabular-nums`）＋ claim_notice。参考目安（LCP 2.5s / CLS 0.1）は「Google公表のgood閾値（参考）」として脚注に留め、**合否バッジは付けない**
- Chromium限定の実装（本システムはChromium固定）

### 受け入れ基準
- AC-A1: フェイクpageで observers 登録→回収の往復が検証できる（実ブラウザ不要のユニットテスト）
- AC-A2: evaluate が例外を投げてもクロールは完走し、performance は None
- AC-A3: report.json の screens に数値が現れ、claim_scope が付く
- AC-A4: E2E: デモページのクロールで LCP>0 が観測される
- AC-A5: report.html に合否バッジが**無い**こと

---

## 対象ファイル・テスト計画・実装順序

新規: `src/crawler/performance_probe.py` / `tests/test_performance_probe.py` / `tests/test_prime_path.py`
変更: `src/mbt/document_model.py`, `src/ux/axe_runner.py`, `src/generator/ux_reporter.py`, `src/generator/json_reporter.py`, `src/generator/html_reporter.py`, `src/crawler/page_crawler.py`, `web/services/document_autorun.py`, `templates/partials/view-auto-run.html`, `docs/userguide.md`, `quality/feature_contracts.yml`（`document_mbt` へ prime_path シンボル、`crawl` へ probe、`ux_review` へ claim 追記）

順序: F → C → A（依存なし・個別にコミット可）。各実装後に `make test` → `make verify-ui` → `verify.sh`。

非スコープ: 性能の経時比較（ドリフト検知との統合）は次弾以降。CLS の要素特定・性能改善提案はしない。
