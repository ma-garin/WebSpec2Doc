# SPEC-6-1 CI 警告一掃（pytest 実行ログの警告ゼロ化と再発防止）

| 項目 | 値 |
|---|---|
| WBS | 6-1 |
| 優先度 / 見積 | P3 / 0.5sp |
| 依存 | なし |
| 背景 | WBS-6 品質・保守（常設）。警告の放置は「本物の警告」を埋もれさせる |

## 1. 目的と背景

CI（.github/workflows/ci.yml の quality ジョブ）と同等の unit テスト実行で警告が出続けている。**2026-07-04 に実測した現状**は以下のとおり:

```bash
venv/bin/python -m pytest tests/ -q --ignore=tests/e2e
# => 1222 passed, 13 warnings in 6.21s（Pillow 12.3.0 導入環境）
```

| # | 種別 | 件数 | 発生源 | 内容（実測メッセージ） |
|---|---|---|---|---|
| W1 | PytestCollectionWarning | 1 | `src/llm/viewpoint_generator.py:42`（tests/test_evidence.py が import） | cannot collect test class 'TestViewpoint' because it has a `__init__` constructor |
| W2 | DeprecationWarning | 12 | `src/diff/screenshot_diff.py:107`（tests/test_screenshot_diff.py の 12 テスト経由） | Image.Image.getdata is deprecated and will be removed in Pillow 14 (2027-10-15). Use get_flattened_data instead. |

補足（実測に基づく現状整理）:

- 計画は collection warning を複数想定していたが、**実測は 1 件のみ**。同構造の `src/analyzer/test_conditions.py:20::TestCondition`（Test 接頭辞の frozen dataclass）は現状どのテストモジュールにも直接 import されていないため未発火 — 将来テストが import した瞬間に再発するので**予防対象に含める**
- Pillow はランタイム依存ではない（requirements.txt に無し・requirements-dev.txt に `Pillow>=11.0.0`、実測導入 12.3.0）。`screenshot_diff.py` は Pillow 不在時にサイズ比較へフォールバックする設計（`_compute_size_diff_ratio`）

## 2. 受け入れ条件（全て自動テストで検証すること）

- **AC-1**: 修正後、同一コマンド（`venv/bin/python -m pytest tests/ -q --ignore=tests/e2e`）で warnings summary が表示されない（0 warnings）こと（Given: 修正済みツリー / When: unit 全件実行 / Then: `1222 passed`（＋本仕様の追加テスト分）で警告 0）
- **AC-2**: `_count_nonzero_pixels` の置き換え実装が旧実装と同一の diff_ratio を返す（Given: 全一致画像・全差分画像・**1 チャンネルだけ僅差の画像**・RGBA 画像 / When: compare_screenshots / Then: 旧実装 `getdata()` + `any(c != 0)` と同値）
- **AC-3**: `TestViewpoint`・`TestCondition` が pytest に収集されないことのテストがある（`__test__ is False` の検証）
- **AC-4**: pyproject.toml の filterwarnings により、対象 2 警告が再発したらテストが **FAIL** する（error 化）
- **AC-5**: 既存 1,222 件が無変更で PASS（診断ロジック・出力スキーマに挙動変更なし）

## 3. スコープ外

- Pillow 14 対応以外の依存バージョン更新（playwright 等は SPEC-6-2）
- tests/e2e 実行時の警告（CI の unit ジョブ対象外。e2e 側は別途 WBS-6 常設で扱う）
- ruff / mypy / bandit の警告・black の差分（既に §3 ゲートで担保済み）
- `filterwarnings = ["error"]` のような全警告 error 化（第三者ライブラリ起因で CI が突然死するため見送り — §8）

## 4. 基本設計

### 4-1. 変更ファイル一覧

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 変更 | `src/llm/viewpoint_generator.py` | `TestViewpoint` に `__test__ = False`（W1 恒久対策） |
| 変更 | `src/analyzer/test_conditions.py` | `TestCondition` に `__test__ = False`（W1 予防） |
| 変更 | `src/diff/screenshot_diff.py` | `_count_nonzero_pixels` を getdata 非依存の実装へ置換（W2） |
| 変更 | `pyproject.toml` | `[tool.pytest.ini_options]` に filterwarnings 追加（再発防止） |
| 変更 | `tests/test_screenshot_diff.py` | 旧実装とのパリティテスト追加（AC-2） |
| 新規 | `tests/test_no_collection_warnings.py` | `__test__ is False` 検証（AC-3） |

### 4-2. 修正方針

**W1**: pytest は「Test 接頭辞のクラスが `__init__` を持つ」場合に収集を諦めて警告する。プロダクトコードのクラス名変更（TestViewpoint は report.json・UI まで波及する公開概念）は行わず、pytest 公式の opt-out である `__test__ = False` をクラス属性として付与する。

**W2**: `getdata()` は Pillow 14（2027-10-15）で削除予定。代替として案内される `get_flattened_data` は新しめの Pillow にしか存在せず、dev 依存の下限（`Pillow>=11.0.0`）では AttributeError になり得るため**採用しない**。バンド分解＋`ImageChops.lighter` 畳み込み＋ヒストグラムという安定 API のみで「いずれかのチャンネルが非ゼロのピクセル数」を厳密に数える。

### 4-3. 処理フロー（W2 置き換え後）

```text
_count_nonzero_pixels(diff_img)
  ├─ bands = diff_img.split()               # L なら 1 帯、RGB(A) なら 3(4) 帯
  ├─ mask = 帯を ImageChops.lighter で畳み込み（ピクセルごとの max）
  └─ return sum(mask.histogram()[1:])       # max > 0 ⇔ いずれかのチャンネルが非ゼロ
```

## 5. 詳細設計

```python
# src/llm/viewpoint_generator.py（src/analyzer/test_conditions.py も同様）
@dataclass(frozen=True)
class TestViewpoint:
    __test__ = False  # pytest 収集対象外（テストクラスではなくドメインモデル）
    category: str
    ...

# src/diff/screenshot_diff.py
def _count_nonzero_pixels(diff_img: Any) -> int:  # PIL.Image instance
    """差分イメージの非ゼロピクセル数を返す（getdata 非依存・Pillow 14 対応）。"""
    from PIL import ImageChops

    bands = diff_img.split()
    mask = bands[0]
    for band in bands[1:]:
        mask = ImageChops.lighter(mask, band)
    return sum(mask.histogram()[1:])
```

```toml
# pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
filterwarnings = [
    "error::pytest.PytestCollectionWarning",
    "error:.*is deprecated and will be removed in Pillow.*:DeprecationWarning",
]
```

### 5-1. エラー処理表

| 事象 | 振る舞い | ユーザー可視 |
|---|---|---|
| Pillow 未導入環境（CI unit ジョブ相当） | 既存フォールバック（サイズ比較）のまま — 本修正は Pillow 経路内のみ | 既存どおり |
| 1 帯（グレースケール）画像 | bands が 1 要素でもループが 0 回で成立 | なし |
| filterwarnings が第三者警告に誤爆 | メッセージ/カテゴリを絞った 2 エントリのみ追加（全 error 化しない） | なし |

### 5-2. 既存コードとの接続点

- `compare_screenshots` / `compare_snapshot_screenshots`（screenshot_diff.py）— シグネチャ・戻り値 `ScreenshotDiff` は不変。diff/impact 系の下流（ドリフト検出）に影響なし
- `tests/test_evidence.py:25` の `from ... import TestViewpoint` — 変更不要（収集警告は import 側でなく定義側で止まる）

## 6. テスト仕様

| テスト名 | 入力 | 期待値 | AC |
|---|---|---|---|
| test_count_nonzero_parity_identical | 全一致 PNG ペア | diff_ratio == 0.0（旧実装と同値） | AC-2 |
| test_count_nonzero_parity_full_diff | 全画素反転ペア | diff_ratio == 1.0 | AC-2 |
| test_count_nonzero_parity_single_channel | 1 画素・1 チャンネルのみ +1 | その 1 画素が数えられる（グレースケール変換系の近似でない証明） | AC-2 |
| test_count_nonzero_parity_rgba | RGBA（alpha のみ差分あり） | alpha 差もカウント（旧 getdata の tuple 比較と同値） | AC-2 |
| test_domain_models_not_collected | TestViewpoint / TestCondition | `__test__ is False` | AC-3 |
| test_getdata_not_used | screenshot_diff.py のソース | `.getdata(` を含まない（再発の静的ガード） | AC-1 |

回帰確認: `venv/bin/python -m pytest tests/ -q --ignore=tests/e2e` を実行し「passed のみ・warnings summary なし」の実測ログを PR に貼る（AC-1/AC-5）。tests/test_screenshot_diff.py 既存 12 件と tests/test_evidence.py が無変更で PASS すること。

## 7. 完了チェックリスト（DoD）

- [ ] AC-1〜5 のテストが全て存在し PASS、警告 0 の実測ログを実装報告に添付
- [ ] CONVENTIONS §3 の全ゲート通過（black/ruff/mypy/bandit/pytest/quality_harness）
- [ ] filterwarnings の error 化で unit 全件が引き続き PASS（誤爆なし）することを CI 相当コマンドで確認
- [ ] 実行パス確認: ドリフト検出（--compare 2 回実行）でスクリーンショット差分が修正前と同じ diff_ratio / is_significant を返すことを DemoMart で目視確認

## 8. このタスク固有の罠

- **`__test__` に型アノテーションを付けない**。`__test__: bool = False` と書くと dataclass の**フィールド**になり、frozen コンストラクタのシグネチャ・等価性・（将来の）シリアライズが変わる。素の `__test__ = False`（アノテーション無しのクラス属性）なら dataclass はフィールド扱いしない
- `get_flattened_data` への単純置換は不可: (1) Pillow 11.0（dev 下限）に存在しない可能性、(2) 戻りが**チャンネル平坦化**であり「ピクセル単位で any(c != 0)」の旧セマンティクスと数え方が変わる
- 「luminance 変換（`convert("L")`）して非ゼロを数える」近似は丸めで**微小なチャンネル差を 0 に潰す**ため、旧実装とパリティが取れない。必ず帯 max（ImageChops.lighter）方式にする
- filterwarnings を `error::DeprecationWarning` と広げると、将来の第三者ライブラリ更新で無関係な CI 突然死を招く（CONVENTIONS §4 罠 3 の類型）。メッセージ正規表現で Pillow 起因に限定する
- 警告カウントはテスト実行数に比例する（W2 の「12 件」は tests/test_screenshot_diff.py の 12 テスト分）。件数でなく**発生源単位**で潰したことを AC-1 の 0 warnings で確認する
