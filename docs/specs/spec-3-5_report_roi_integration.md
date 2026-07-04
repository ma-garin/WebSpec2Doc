# SPEC-3-5 レポート/ROI 統合（Sprint D: 実績計上・監査・網羅性証明・デモ）

| 項目 | 値 |
|---|---|
| WBS | 3-5（docs/0703-01_plan.md） |
| 優先度 / 見積 | P3 / 1sp |
| 依存 | 3-3（現新比較）・3-4（UX レビュー） |
| 背景 | docs/11 §3 Sprint D・§2（遮断ログとカバレッジギャップは「比較の網羅性証明」に昇格） |

## 1. 目的と背景

Sprint B/C で増えた成果（現新比較・UX レビュー）を ROI ダッシュボードの実績に計上し、残バックログ 2 件 — MutationBlocker 遮断の監査ログ化・カバレッジギャップ（未探索領域）のレポート表示 — を消化して「どこまで見た / 見ていない」を利用者に明示する。あわせてデモ台本に「移行検証デモ」「UX 診断デモ」を追加する。

**現状の実装状態（実装前に必ず確認すること）:**

- 済: `web/services/usage_tracker.py` — usage_log.jsonl への追記・係数ベース集計（`SavingCoefficients`・環境変数上書き・免責文言）。**event は "crawl" のみ**、比較/UX の係数なし
- 済: `src/crawler/network_interceptor.py::MutationBlocker` — 遮断はするが記録は `self.blocked`（メモリ）と警告ログのみ。**audit.jsonl に残らない**（crawl_page:550 付近で attach、blocked は捨てられている）
- 済: `src/crawler/politeness.py::append_audit_log` — audit.jsonl の追記基盤（crawl_started 等で使用中、page_crawler.py:255/382）
- 済: `src/capture/coverage.py::compute_exploration_coverage` — 未探索画面・地図にない足跡の集計と `exploration_heatmap.html`（別ファイル）。**report.html 本体には未探索情報が出ない**
- 済: `docs/demo/DEMO_SCRIPT.md`（5 分版/10 分版/早見表/トラブル切替）・`demo/demo_site.py`（ポート 8766）
- 未: comparison / ux_review イベントの実績記録・係数・ダッシュボード表示、遮断の監査ログ、report.html のカバレッジギャップ節、現新比較レポートの網羅性サマリ、デモ台本 2 本

## 2. 受け入れ条件（全て自動テストで検証すること）

- **AC-1**: 現新比較の実績計上（Given: 比較実行が完了 / When: 記録 / Then: usage_log.jsonl に `event="comparison"`・比較画面ペア数・検出指摘数が追記され、`/api/usage` の集計に比較由来の推定削減工数が係数とともに現れる）
- **AC-2**: UX レビューの実績計上（同様に `event="ux_review"`・対象画面数・指摘数が計上される）
- **AC-3**: 後方互換（Given: 新キーを持たない既存 usage_log 行が混在 / When: summarize / Then: 例外なく集計され、既存イベントの集計値は係数既定値のまま従来と一致する）
- **AC-4**: 遮断の監査ログ化（Given: クロール中に POST が遮断される / When: crawl_page 完了 / Then: audit.jsonl に `event="mutation_blocked"`・method・URL・発生ページ URL が記録される。遮断ゼロのページではレコードを追加しない）
- **AC-5**: カバレッジギャップ表示（Given: robots スキップ・未読 iframe・ログインウォール・未探索画面のいずれかが存在 / When: report.html 生成 / Then: 「カバレッジと未確認領域」節に理由付きで列挙され、**「未確認」と表現し「問題なし」と断定しない**）
- **AC-6**: 網羅性サマリ（Given: 現新比較実行 / When: comparison.html 生成 / Then: 「対応付け n 組 / 現行のみ m / 新のみ k / 検査できなかったリンク j 件」の網羅性サマリが表示される）
- **AC-7**: デモ台本に「移行検証デモ」「UX 診断デモ」の手順が追加され、`make demo` 起動のデモサイト（新旧 2 バージョン・ux_bad.html）で台本どおり再現できる
- **AC-8**: ギャップ・監査の追加によって report.json のスキーマ・report_hash・既存テストが変化しない（ギャップ節はデータ存在時のみ描画）

## 3. スコープ外

- ヒートマップの report.html タブ統合・チャーター自動提案（WBS 2-2 の領域。本タスクは「未探索の明示」まで）
- 削減工数係数の実測校正（係数は従来どおり想定値＋免責。実測化は将来）
- 通知・スケジュール実行との連携（WBS 4-4/D1）
- 台本の英語化・動画化

## 4. 基本設計

### 4-1. 変更ファイル一覧

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 変更 | `web/services/usage_tracker.py` | comparison / ux_review イベント・係数 2 種・summarize 拡張 |
| 変更 | `templates/partials/view-usage.html` | ダッシュボードに比較・UX の行を追加 |
| 変更 | `src/crawler/page_crawler.py` | crawl_page 終了時に blocker.blocked を append_audit_log へ |
| 新規 | `src/generator/coverage_gap.py` | ギャップ集計（audit.jsonl・embedded_frames・coverage.py の統合） |
| 変更 | `src/generator/html_reporter.py` | 「カバレッジと未確認領域」節（データ存在時のみ） |
| 変更 | `src/generator/comparison_reporter.py` | 網羅性サマリ節（SPEC-3-3 の成果物へ追記） |
| 変更 | `src/diff/comparison.py`・`src/main.py` | 完了時の実績記録呼び出し（--ux-review 側も同様） |
| 変更 | `docs/demo/DEMO_SCRIPT.md`・`scripts/demo.sh` | 台本 2 本追加・site_v2 併走起動 |
| 変更 | `tests/test_usage_tracker.py`・`tests/test_network_interceptor.py`・新規 `tests/test_coverage_gap.py` | §6 |
| 変更 | `quality/feature_contracts.yml` | usage_roi / crawl 契約の更新 |

### 4-2. データモデル

```python
# usage_tracker.py へ追加（既存 dataclass を拡張・既定値付きで後方互換）
@dataclass(frozen=True)
class SavingCoefficients:
    ...  # 既存 4 係数はそのまま
    minutes_per_compare_screen: float = 20.0   # 画面ペア 1 組の手動突き合わせ想定
    minutes_per_ux_finding: float = 15.0       # UX 指摘 1 件の手動レビュー想定
# 環境変数: WEBSPEC2DOC_MIN_PER_COMPARE_SCREEN / WEBSPEC2DOC_MIN_PER_UX_FINDING

# coverage_gap.py
@dataclass(frozen=True)
class CoverageGap:
    kind: str      # "robots_skipped" / "unreadable_frame" / "login_wall" / "unexplored_screen" / "unchecked_link"
    subject: str   # URL・フレーム src・page_id 等
    reason: str    # 日本語（例:「robots.txt により対象外」「クロスオリジンのため未読」）
```

### 4-3. 処理フロー

```text
[実績] comparison / ux_review 完了
  → record_usage(output_root, event="comparison", compare_screen_count=n, finding_count=m)
  → summarize_usage が係数を掛けて /api/usage・view-usage.html に反映
[監査] crawl_page finally 節
  → blocker.blocked が非空なら append_audit_log(output_dir,
       {"event": "mutation_blocked", "page_url": url, "blocked": [{"method": .., "url": ..}, ...]})
[網羅性] レポート生成時
  → collect_coverage_gaps(output_dir, pages, coverage) が
     audit.jsonl（robots_skipped_urls・login wall）＋ PageData.embedded_frames（readable=False, SPEC-3-1）
     ＋ compute_exploration_coverage の未探索画面 ＋ link_checker の「未確認」リンク（SPEC-3-3）を統合
  → html_reporter の「カバレッジと未確認領域」節 / comparison_reporter の網羅性サマリ
```

## 5. 詳細設計

### 5-1. usage_tracker 拡張

```python
def record_usage(
    output_root: Path, *, event: str, domain: str,
    screen_count: int = 0, test_condition_count: int = 0,
    document_count: int = 0, diff_run: bool = False,
    compare_screen_count: int = 0,   # 新規（既定 0 = 旧呼び出し互換）
    finding_count: int = 0,          # 新規（comparison の指摘数 / ux_review の指摘数を共用）
) -> Path | None: ...
```

- JSONL 行への新キー追加は**該当イベントの時のみ**書く（event が comparison/ux_review 以外なら旧 6 キーのまま — CONVENTIONS §2 のオプトイン方針を usage_log にも適用し、既存行と diff しやすく保つ）
- `summarize_usage` に `total_compare_screens`・`total_findings`・`estimated_saved_hours` への加算（`compare_screens × minutes_per_compare_screen ＋ findings × minutes_per_ux_finding`）と `coefficients` への 2 キー追加。**免責文言は既存のまま維持**（推定値であることの明示）
- 呼び出し箇所: `src/main.py` の比較/UX 完了後（web 層の関数を src から import しない — 層分離。CLI 完了後の記録は `web/routes/crawl.py::_record_usage_safely` と同様に**呼び出し側（route / main の出力フェーズ）**で行う。main.py は `web.services` を import できないため、CLI 実行分は route 経由実行時に記録し、CLI 単独実行分は記録対象外と明記する）

### 5-2. MutationBlocker 遮断の監査ログ化

- `crawl_page` の finally 節（blocker.detach の直後）で `blocker.blocked` を読み、非空時のみ `append_audit_log`。audit.jsonl は追記型でスナップショット・report_hash と無関係（AC-8 に影響しない）
- 遮断 URL にクエリが含まれる場合は**クエリを落として記録**する（トークン等の秘匿情報をログへ残さない。politeness の監査ログにない新しい配慮なので単体テストを付ける）
- parallel_crawler 経由でも crawl_page 単位で記録されるため追加対応不要（確認テストを書く）

### 5-3. カバレッジギャップ集計（coverage_gap.py）

```python
def collect_coverage_gaps(
    output_dir: Path,
    pages: list[PageData],
    coverage: dict[str, Any] | None = None,   # compute_exploration_coverage の出力（セッション無しなら None）
) -> tuple[CoverageGap, ...]:
    """audit.jsonl の crawl_started.robots_skipped_urls / login wall 記録、
    PageData.embedded_frames（readable=False — SPEC-3-1）、coverage の explored=False 画面、
    comparison の未確認リンク（comparison.json があれば）を CoverageGap に正規化する。"""
```

- audit.jsonl のパース失敗行は警告してスキップ（usage_tracker.load_usage と同じ耐性）
- html_reporter には `_section("カバレッジと未確認領域", ...)` を追加（既存 `_section` / anchor 機構・282 行付近を使用）。**ギャップ 0 件かつ coverage なしの場合は節ごと出さない**（AC-8）
- 表示文言は evidence-only 原則に従い「未確認（robots により対象外）」等、**検査しなかった事実**のみを述べる

### 5-4. デモ台本・デモサイト

- `scripts/demo.sh` に site_v2（ポート 8767）の併走起動を追加（demo_site.py は SPEC-3-3 で `--site-dir` 対応済みの前提。8766=現行 site は不変）
- DEMO_SCRIPT.md に追記: 「移行検証デモ」= 8766×8767 の現新比較 → 4 分類と網羅性サマリを見せる、「UX 診断デモ」= ux_bad.html（SPEC-3-4）を `--ux-review` → UX タブと免責を見せる。既存の 5 分版/10 分版/早見表の章構成に節を追加し、所要時間・見せ場・想定質問を既存書式で書く

### 5-5. エラー処理表

| 事象 | 振る舞い | ユーザー可視 |
|---|---|---|
| usage_log 書き込み失敗 | None を返し本体処理は継続（既存方針） | なし（警告ログのみ） |
| 係数の環境変数が不正値 | 既定値へフォールバック（既存 `_env_float`） | /api/usage の coefficients に既定値 |
| audit.jsonl 読み込み失敗・不正行 | 該当行スキップ・ギャップ節は残りで描画 | 「監査ログの一部が読めませんでした」注記 |
| coverage / comparison.json 不在 | その情報源だけ省略して集計 | 該当項目が節に出ない |
| 遮断記録の書き込み失敗 | クロール継続（append_audit_log の既存保証） | なし（警告ログのみ） |

## 6. テスト仕様

### 6-1. 単体テスト

| テスト名 | 入力 | 期待値 | AC |
|---|---|---|---|
| test_record_comparison_event | event="comparison", pairs=5, findings=12 | JSONL に新キー付き 1 行 | AC-1 |
| test_record_crawl_has_no_new_keys | event="crawl" | 行に compare_screen_count キーが無い | AC-3 |
| test_summarize_mixed_old_and_new_lines | 旧形式行＋新形式行 | 例外なし・旧集計値不変・比較分が加算 | AC-3 |
| test_ux_coefficient_env_override | WEBSPEC2DOC_MIN_PER_UX_FINDING=30 | 係数反映・不正値は既定 15.0 | AC-2 |
| test_blocked_mutation_written_to_audit | blocked=[("POST", url?token=x)] のフェイク | audit に event=mutation_blocked・クエリ除去済み URL | AC-4 |
| test_no_audit_record_when_nothing_blocked | blocked=[] | mutation_blocked 行なし | AC-4 |
| test_gaps_from_all_sources | audit＋embedded_frames＋coverage の fixture | 4 種の CoverageGap が正規化される | AC-5 |
| test_gap_section_absent_when_empty | ギャップ 0 件 | report.html に節が無い・既存出力と同一 | AC-8 |

### 6-2. 結合テスト（実ファイル I/O・tmp_path）

- `/api/usage` route（tests/test_usage_route.py 拡張）: comparison/ux_review 記録後の JSON に新集計キー・係数・免責が含まれる（AC-1, 2）
- comparison_reporter: 網羅性サマリの数値（n/m/k/j）が ComparisonResult と一致する（AC-6）
- 実ブラウザ E2E は新設不要（遮断はフェイク route で単体検証可能。デモ再現は DoD の目視確認とし、実行できない場合「未確認」と報告する）

### 6-3. 回帰確認

- `tests/test_usage_tracker.py`・`test_usage_route.py`・`test_network_interceptor.py`・`test_html_reporter.py`・`test_politeness.py` の既存ケースが無変更で PASS
- `docs/demo/sample_output/report.json` とのスキーマ差分なし・report_hash 不変（AC-8）

## 7. 完了チェックリスト（DoD）

- [ ] AC-1〜8 のテストが全て存在し PASS
- [ ] CONVENTIONS §3 の全ゲート通過（view-usage.html 変更のため make verify-ui 必須）
- [ ] feature_contracts.yml 更新（usage_roi に comparison/ux_review 実績、crawl の failure_modes に mutation_blocked_audit）
- [ ] 実行パス確認: 現新比較→/usage に実績反映、POST を含むページのクロール→audit.jsonl の mutation_blocked、robots スキップ入りクロール→report.html のギャップ節、を通しで目視確認
- [ ] `make demo` で新旧サイトが併走起動し、DEMO_SCRIPT.md の新 2 台本が最後まで再現できる

## 8. このタスク固有の罠

- **層分離**: usage_tracker は `web/services/` にあり、`src/` から import してはならない（CONVENTIONS §1-1 の依存方向違反）。実績記録は route / 出力フェーズ側に置く。逆に coverage_gap は `src/generator/` に置き web に依存しない
- usage_log.jsonl は**全ドメイン共通の 1 ファイル**（output 直下）。ドメイン別ディレクトリに書かないこと（record_crawl_from_report の実装を参照）
- summarize_usage の戻り値キーは view-usage.html と `/api/usage` の契約。**既存キーの改名・削除は UI を静かに壊す** — 追加のみ行い、test_usage_route.py で新旧キー両方を検証する
- 遮断 URL の記録は秘匿情報（クエリ内トークン・パスワードリセット URL 等）を含み得る。**クエリ除去を必ずテストで固定**する。bandit ではなくレビューでしか捕まらない類の漏洩なので仕様で明示した
- audit.jsonl は追記専用で crawl_started が複数回分混在する。ギャップ集計は**最新の crawl_started 以降**の行だけを対象にしないと、過去実行のスキップ URL が再表示される（タイムスタンプでの絞り込みを単体テストで固定する）
