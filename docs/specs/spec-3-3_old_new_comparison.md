# SPEC-3-3 現新比較モード（Sprint B: 移行検証支援）

| 項目 | 値 |
|---|---|
| WBS | 3-3（docs/0703-01_plan.md） |
| 優先度 / 見積 | P2 / 2sp |
| 依存 | 3-1（iframe/Shadow DOM — レガシー側の抽出精度） |
| 背景 | docs/11 §3 Sprint B・§1-1/1-2（画像差分は誤検知との戦い） |

## 1. 目的と背景

OS 移行・リプレイス時の現新比較検証を自動化する。現行 URL と新 URL のペアを 2 ターゲットクロールし、画面を対応付けて三層比較（仕様差分・画像差分・リンク切れ）を行い、想定不具合 4 分類（表示崩れ / 文字化け・意味消失 / 理解不可能 / 操作不可）で報告する。既存の画像比較ツールと違い**復元済み仕様書が同時に手に入り**、「ピクセルは違うが仕様は同じ」と「ピクセルは同じだが仕様が壊れた」を区別できる。

**現状の実装状態（実装前に必ず確認すること）:**

- 済: `src/diff/differ.py::compute_diff` — フォーム/リンク/タイトル/API の差分と `FieldAttributeDiff`（severity: breaking/warning/info）。**ただし突合キーが完全一致 URL** のため現新（ドメインが違う）にはそのまま使えない
- 済: `src/diff/screenshot_diff.py::compare_screenshots` — ピクセル差分比率＋閾値（DEFAULT_THRESHOLD=0.05）。**マスク・ゆらぎ許容なし**（誤検知対策未実装）
- 済: `src/ingest/matcher.py::_match_screens` — スコア降順貪欲法の 1 対 1 画面対応（URL パス正規化一致 > 名称類似 ≥0.6）。**文書×実測用なので現新（実測×実測）へ一般化が必要**。`crawl_urls`（page_crawler.py:357）・`save_snapshot`・`screen_fingerprint` も既存
- 未: 2 ターゲット実行の CLI・画面ペアの仕様/画像比較・リンク切れ検査・4 分類レポート・出力

## 2. 受け入れ条件（全て自動テストで検証すること）

- **AC-1**: 2 ターゲットクロールが動く（Given: `--compare-old-urls` と `--compare-new-urls` / When: 実行 / Then: 両ターゲットの PageData が取得され、それぞれ `old/`・`new/` サブディレクトリにスナップショット・スクリーンショットが保存される）
- **AC-2**: 画面対応付け（Given: パスが同じ・タイトルが類似する現新画面 / When: マッチング / Then: 1 対 1 のペアが生成され、未対応画面は「新規追加」「削除」として報告される）
- **AC-3**: 仕様差分（Given: 新側で required 属性が消えたフォーム / When: 比較 / Then: `FieldAttributeDiff(severity=breaking)` が検出される — ピクセルが同じでも検出）
- **AC-4**: 画像差分の誤検知抑制（Given: 時刻表示だけが異なる同一画面 / When: 動的領域マスク適用で比較 / Then: `is_significant=False`。閾値・ゆらぎ許容は環境変数で調整可能）
- **AC-5**: リンク切れ検査（Given: 新側に 404 を返すリンク / When: 検査 / Then: 「操作不可」分類で URL・リンク元画面・HTTP ステータスが記録される）
- **AC-6**: 4 分類レポート（Then: 全指摘に現新両方のスクリーンショット・セレクタの evidence が付く。規則で分類できない差分は「未分類（要確認）」と明示し断定しない）
- **AC-7**: 比較モード未使用時、report.json のスキーマ・report_hash・既存テストが変化しない
- **AC-8**: 実ブラウザ E2E がデモサイト新旧ペアで AC-1〜5 を検証する

## 3. スコープ外

- Web UI からの比較起動（CLI 起点。UI 統合は Sprint D 以降）・帳票比較（docs/11 §5 A3。Phase 2）
- 動的領域の意味理解（AI による「意味のある差分」抽出）— マスクと閾値による機械的抑制のみ
- 3 つ以上のターゲット比較・履歴間比較（既存 `--compare` のドリフト検出はそのまま）

## 4. 基本設計

### 4-1. 変更ファイル一覧

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 新規 | `src/diff/pair_matcher.py` | 実測×実測の画面対応付け（ingest/matcher の貪欲法を一般化） |
| 新規 | `src/diff/comparison.py` | オーケストレータ（2 クロール→対応付け→三層比較→分類） |
| 新規 | `src/diff/link_checker.py` | 新側リンクの HTTP 検査（politeness 準拠） |
| 変更 | `src/diff/screenshot_diff.py` | マスク・ゆらぎ許容の追加（既存関数のシグネチャ互換） |
| 変更 | `src/diff/differ.py` | ページペア単位の比較関数追加（既存 `compute_diff` は不変） |
| 新規 | `src/generator/comparison_reporter.py` | comparison.json / comparison.html（4 分類×画面マトリクス） |
| 変更 | `src/main.py` | `--compare-old-urls` / `--compare-new-urls` / `--compare-mask-selector` |
| 新規 | `demo/site_v2/`（index/contact/products） | 新バージョン相当（required 消失・リンク切れ・時計・文字化けを仕込む） |
| 新規 | `tests/test_pair_matcher.py`・`tests/test_comparison.py`・`tests/e2e/test_comparison_e2e.py` | §6 |
| 変更 | `quality/feature_contracts.yml` | old_new_comparison 契約を新設 |

### 4-2. データモデル

```python
# src/diff/pair_matcher.py
@dataclass(frozen=True)
class ScreenPair:
    old_page_id: str
    new_page_id: str
    score: float          # 1.0 = パス一致、それ以外は名称類似度
    method: str           # "path" / "title" / "fingerprint"

# src/diff/comparison.py
@dataclass(frozen=True)
class ComparisonFinding:
    """1 指摘。category は不具合 4 分類 + "unclassified"。"""
    category: str         # "layout_broken" / "text_garbled" / "incomprehensible" / "inoperable" / "unclassified"
    page_pair: ScreenPair | None          # 対応画面（リンク切れ等はペア起点）
    detail: str                           # 日本語の説明（例:「必須属性が消失: name」）
    old_evidence: SourceEvidence | None   # 現行側（screenshot_path 必須）
    new_evidence: SourceEvidence | None   # 新側
    severity: str                         # differ の SEVERITY_* を共用
    confidence: float = 1.0               # 実測由来は 1.0 固定

@dataclass(frozen=True)
class ComparisonResult:
    pairs: tuple[ScreenPair, ...]
    added_page_ids: tuple[str, ...]       # 新のみ
    removed_page_ids: tuple[str, ...]     # 現行のみ
    findings: tuple[ComparisonFinding, ...]
    screenshot_diffs: tuple[ScreenshotDiff, ...]  # 既存 dataclass を共用
```

### 4-3. 処理フロー

```text
run_old_new_comparison(old_urls, new_urls, output_dir, auth_old, auth_new)
  ├─ crawl_urls(old_urls, output_dir/"old", auth_old)   # 既存関数を 2 回。礼儀・audit は既存のまま
  ├─ crawl_urls(new_urls, output_dir/"new", auth_new)
  ├─ analyze_pages() → match_page_pairs()               # 画面対応付け（5-1）
  ├─ 三層比較（ペアごと）
  │   ├─ compare_page_pair()          # 仕様差分（differ の項目/属性/リンク/API 比較を転用）
  │   ├─ compare_screenshots_masked() # 画像差分（動的マスク＋ゆらぎ許容、5-2）
  │   └─ check_links()                # 新側リンクの HTTP 検査
  ├─ classify_findings()              # 4 分類（5-3）
  └─ comparison_reporter → comparison.json / comparison.html（Excel シートは既存 xlsx に追記）
```

## 5. 詳細設計

### 5-1. 画面対応付け（pair_matcher）

```python
def match_page_pairs(
    old_pages: list[AnalyzedPage], new_pages: list[AnalyzedPage], threshold: float = 0.6
) -> tuple[list[ScreenPair], list[str], list[str]]:
    """スコア降順貪欲法（ingest/matcher.py::_match_screens と同一方式）。
    スコア: (1) 正規化 URL パス一致（matcher._normalize_path 相当）= 1.0
            (2) title / headings の SequenceMatcher 類似（matcher._name_similarity 共用）
            (3) 同点時は _structure_signature（canonicalizer）の一致をタイブレークに使う
    戻り値: (pairs, removed_page_ids, added_page_ids)。"""
```

- `_name_similarity` / `_normalize_path` は ingest/matcher.py から**共通ヘルパーとして切り出して共用**する（Doc Fusion と現新比較で実装共有 — docs/11 §6-4 の設計指針）。matcher.py 側は import 置換のみで挙動不変にする
- fingerprint 全体（URL 込み）はドメインが違うため一致しない。**構造署名部分のみ**を比較に使う

### 5-2. 画像差分の誤検知抑制（screenshot_diff 拡張）

```python
def compare_screenshots_masked(
    before_path: Path, after_path: Path, page_id: str = "",
    threshold: float = DEFAULT_THRESHOLD,          # 既存 0.05。WEBSPEC2DOC_COMPARE_DIFF_THRESHOLD で上書き
    masks: tuple[tuple[int, int, int, int], ...] = (),  # (x, y, w, h) 群。塗り潰して比較
    channel_tolerance: int = 24,                   # 画素値差 ≤ tolerance は同一扱い（アンチエイリアスゆらぎ吸収）
) -> ScreenshotDiff: ...

def detect_dynamic_regions(page: Page, interval_sec: float = 1.0) -> tuple[tuple[int, int, int, int], ...]:
    """同一ページを間隔をおいて 2 枚撮影し、16px グリッドで差分が出たブロックを動的領域として返す。
    時計・カルーセル等を自動マスク化する。撮影は現行側クロール中に行う（追加 1 枚）。"""
```

- 加えて `--compare-mask-selector`（CSS セレクタ列）指定時は該当要素の bounding_box をマスクに追加（広告枠など人が知っている動的領域）
- サイズ不一致は既存どおり縮小合わせ。既存 `compare_screenshots` のシグネチャ・戻り値は不変（AC-7）

### 5-3. 不具合 4 分類（ルールベース・confidence 1.0）

| 分類 | 判定規則（実測差分由来のみ） |
|---|---|
| 操作不可 inoperable | リンク切れ（status ≥400/接続失敗）・フォーム action の消失・submit ボタン消失・field_type/required の breaking 差分 |
| 文字化け・意味消失 text_garbled | title/headings に U+FFFD 等の化け文字を検出・現行にあった見出しテキストの消失 |
| 理解不可能 incomprehensible | `has_visible_label` true→false・aria_label 消失・a11y_issues の増加 |
| 表示崩れ layout_broken | 仕様差分なし かつ 画像差分 is_significant（構造は同じで見た目だけ大きく違う） |

上記に該当しない差分は `unclassified` として「分類できない差分（要人手確認）」と明示する（evidence-only 原則: 無理に分類しない）。

### 5-4. エラー処理表

| 事象 | 振る舞い | ユーザー可視 |
|---|---|---|
| 片側クロールが 0 件 | 比較を中止しエラー終了（部分レポートを出さない） | 「現行/新の取得に失敗しました」 |
| 対応画面が 1 組もない | pairs=() で完走・added/removed のみ報告 | 「対応画面が見つかりません」 |
| リンク検査のタイムアウト | 「未確認」として記録（切れと断定しない） | 一覧に「未確認（タイムアウト）」 |
| スクリーンショット欠落 | 画像差分をスキップし仕様差分のみ | 「画像未取得」表示 |
| キャンセル（stop_requested） | 既存クロールと同じ checkpoint 保存で停止 | 「停止しました」 |

### 5-5. 既存コードとの接続点

- `crawl_urls`（output_dir を old/new で分ける。auth_state は現新で別指定可）・`save_snapshot`
- `differ.py` の `_fields_by_name`・`_attribute_diffs_for_field`・`_ATTRIBUTE_SEVERITY` をペア比較関数から再利用（URL キー突合の `compute_diff` 自体は触らない）
- リンク検査は `OriginRateLimiter`＋`backoff_delays`（politeness.py）を使い、`append_audit_log` に検査対象と結果を記録する（比較の網羅性証明 — Sprint D で表示）
- 出力は `comparison.json` / `comparison.html` の**別ファイル**とし、report.json にはキーを追加しない（AC-7。official_name 前例よりさらに安全側）

## 6. テスト仕様

### 6-1. 単体テスト

| テスト名 | 入力 | 期待値 | AC |
|---|---|---|---|
| test_pair_match_by_path | 同一パス・別ドメインの 2 ページ | score=1.0, method="path" | AC-2 |
| test_pair_match_unmatched_reported | 片側にしかない画面 | added/removed に載る | AC-2 |
| test_required_loss_is_breaking_inoperable | required True→False の FieldData | breaking かつ「操作不可」 | AC-3, 6 |
| test_masked_and_tolerance_not_significant | 時刻領域＋画素値差 ≤24 のみの 2 画像（fixture 生成） | is_significant=False・tolerance 内は diff_ratio 0.0 | AC-4 |
| test_link_checker_records_404 | フェイク HTTP（404 応答） | inoperable・status=404・evidence 付き | AC-5 |
| test_link_timeout_marked_unconfirmed | タイムアウトするフェイク | 「未確認」・切れと断定しない | 5-4 |
| test_garbled_title_classified | title に U+FFFD | text_garbled | AC-6 |
| test_report_json_unchanged_without_compare | 通常クロール相当 | comparison.* が出ずスキーマ不変 | AC-7 |

### 6-2. 実ブラウザ E2E（tests/e2e/test_comparison_e2e.py・専用スレッドパターン必須）

- `demo/site`（現行）をポート 8902、`demo/site_v2`（新）をポート 8903 で配信（demo/demo_site.py の `--site-dir` 引数を追加）。site_v2 の contact.html は required 消失＋存在しないリンク＋時刻表示 `<span id="clock">` を持つ
- 検証: ペア生成（AC-2）・required 消失検出（AC-3）・clock マスクで画像差分非有意（AC-4）・リンク切れ（AC-5）・comparison.html 生成（AC-1）

### 6-3. 回帰確認

- 既存 `tests/test_diff.py`・`test_screenshot_diff.py`・`test_doc_fusion.py`（matcher ヘルパー切り出しの影響確認）が無変更で PASS
- `docs/demo/sample_output/report.json` とのスキーマ差分がないこと（AC-7）

## 7. 完了チェックリスト（DoD）

- [ ] AC-1〜8 のテストが全て存在し PASS
- [ ] CONVENTIONS §3 の全ゲート通過
- [ ] feature_contracts.yml に old_new_comparison 契約（core_files・failure_modes: one_side_empty / no_pairs / link_timeout / screenshot_missing・required_tests）
- [ ] 実行パス確認: CLI で demo/site × demo/site_v2 を比較し、comparison.html の 4 分類と evidence（現新スクリーンショット）を目視確認
- [ ] 動的マスクなしで実行した場合との誤検知件数差をデモ台本用に記録（Sprint D の入力）

## 8. このタスク固有の罠

- **compute_diff を現新に流用しない**。突合キーが完全一致 URL のため、ドメインが違う現新では全画面が added/removed になる。必ず ScreenPair 経由でペア単位比較する
- ピクセル差分の全画素走査（`_count_nonzero_pixels` は getdata() の Python ループ）はフルページ 2 枚×画面数で遅い。マスク適用後は既存実装を踏襲しつつ、**画像を RGB のまま比較し numpy を新規依存に追加しない**（requirements 追加は仕様外判断になる）
- 動的領域の自動検出（2 枚撮影）は**現行側クロール中**にしか行えない。スナップショットからの再比較時はマスク情報を `old/dynamic_masks.json` に永続化しておくこと
- demo/site_v2 のページに `login.html` を含めない（ログインウォール検出でスキップされ E2E が空振り — CONVENTIONS §4-5）
- ローカル 2 ポート配信のため e2e fixture で `WEBSPEC2DOC_ALLOW_LOCAL=1` 設定（CONVENTIONS §4-6）とポート衝突回避（8902/8903 を新規予約）
