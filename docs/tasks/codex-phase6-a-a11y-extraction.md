# タスク: Phase 6-A — A11y/デザイン属性の抽出（アクセシビリティ対応）

## ゴール

クローラーが ARIA 属性・ラベル・画像 alt・ランドマーク role を収集し、
JSON レポートに a11y 観点のデータを追加する。

**なぜ必要か**: アクセシビリティ担当・デザイナーが「このサイトはラベルなし入力が何件あるか」を
WebSpec2Doc の出力だけで把握できるようにする。
テスト設計への入力（role-based ロケータ候補・WCAG チェックリスト生成）の基盤にもなる。

---

## 前提チェック（必ず実行してから始める）

```bash
source venv/bin/activate
python --version   # 3.12.x であること

# テスト収集が通ること
python -m pytest tests/ -q --co -q 2>&1 | tail -5

# 既存テストが全 PASS であること
python -m pytest tests/ -q 2>&1 | tail -5
```

---

## 触るファイル（これ以外は変更しない）

| ファイル | 変更内容 |
|---------|---------|
| `src/crawler/page_crawler.py` | `FieldData` に a11y フィールド追加 |
| `src/crawler/link_extractor.py` | `_FORM_SCRIPT` 拡張 + `extract_a11y_issues()` 追加 |
| `src/crawler/page_crawler.py` | `crawl_page()` → `extract_a11y_issues()` 呼び出し追加 |
| `src/generator/json_reporter.py` | `_field_dict()` / `_screen_dict()` に a11y フィールド追加 |
| `tests/test_a11y_extraction.py` | 新規作成（テスト） |

**変更禁止**:
- `src/analyzer/` 以下のファイル
- `src/diff/` 以下のファイル
- `web/` 以下のすべてのファイル
- `static/` 以下のすべてのファイル
- `templates/` 以下のすべてのファイル
- git 操作（commit は Claude が行う）

---

## 既存コードの参照（必ず読んでから実装すること）

```bash
# FieldData / PageData の定義
grep -n "dataclass\|frozen\|FieldData\|PageData" src/crawler/page_crawler.py | head -30

# 現在の _FORM_SCRIPT（JS でフォームフィールドを抽出するスクリプト）
grep -n "_FORM_SCRIPT" src/crawler/link_extractor.py
sed -n '/^_FORM_SCRIPT/,/^"""/p' src/crawler/link_extractor.py

# _to_field_data() — FieldData の構築
grep -n "_to_field_data\|_to_form_data" src/crawler/link_extractor.py

# crawl_page() — PageData を組み立てる関数
grep -n "def crawl_page\|extract_\|PageData(" src/crawler/page_crawler.py | head -20

# json_reporter の _field_dict()
cat src/generator/json_reporter.py
```

---

## 実装指示

### Step 1: `src/crawler/page_crawler.py` — `FieldData` に a11y フィールドを追加

`FieldData` は `frozen=True` の dataclass。既存フィールドの末尾にデフォルト付きフィールドを追加する
（既存コードへの影響ゼロ）。

```python
@dataclass(frozen=True)
class FieldData:
    # ... 既存フィールドはそのまま ...
    element_id: str = ""
    # ↓ 追加（末尾に置くこと）
    aria_label: str = ""          # aria-label 属性の値
    aria_required: bool = False   # aria-required="true" または required 属性
    role: str = ""                # 明示的な role 属性（例: "textbox", "combobox"）
    has_visible_label: bool = False  # <label for="..."> または aria-label が存在するか
```

> `frozen=True` なので追加のみ可（既存フィールドの削除・型変更は禁止）。
> デフォルト値付きフィールドは末尾に配置する必要がある。既存 `element_id` の直後に追加すること。

---

### Step 2: `src/crawler/link_extractor.py` — `_FORM_SCRIPT` を拡張

`_FORM_SCRIPT` のフィールドマッピングに以下を追加する（`default: ...` の行の後に追記）:

```js
aria_label: field.getAttribute('aria-label') || '',
aria_required: field.getAttribute('aria-required') === 'true' || field.required,
role: field.getAttribute('role') || '',
has_visible_label: (() => {
  const id = field.getAttribute('id');
  if (id && document.querySelector('label[for="' + id + '"]')) return true;
  if (field.getAttribute('aria-label')) return true;
  if (field.getAttribute('aria-labelledby')) return true;
  return false;
})(),
```

`_to_field_data()` に追加フィールドのマッピングを追記する:

```python
def _to_field_data(raw_field: dict[str, Any]) -> FieldData:
    return FieldData(
        # ... 既存のフィールドはそのまま ...
        element_id=str(raw_field.get("id") or EMPTY_TEXT),
        # ↓ 追加
        aria_label=str(raw_field.get("aria_label") or EMPTY_TEXT),
        aria_required=bool(raw_field.get("aria_required", False)),
        role=str(raw_field.get("role") or EMPTY_TEXT),
        has_visible_label=bool(raw_field.get("has_visible_label", False)),
    )
```

---

### Step 3: `src/crawler/link_extractor.py` — `extract_a11y_issues()` を追加

ファイル末尾に新関数を追加する。Playwright の `Page` を受け取り、A11y 問題のリスト（文字列）を返す。

```python
def extract_a11y_issues(page: Page) -> list[str]:
    """ページの明白なアクセシビリティ問題を検出して文字列リストで返す。

    検出項目:
      - <img> で alt 属性が空または欠落
      - <input> / <select> / <textarea> で label も aria-label もない
      - landmark role なし（main/nav/header/footer が0件）
    """
    issues: list[str] = []
    try:
        # 1. img の alt チェック
        missing_alt: int = page.eval_on_selector_all(
            "img",
            "(imgs) => imgs.filter(img => !img.getAttribute('alt')).length",
        )
        if missing_alt:
            issues.append(f"img[alt欠落]: {missing_alt}件")

        # 2. ラベルなし入力チェック
        unlabeled: int = page.eval_on_selector_all(
            "input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=reset]), select, textarea",
            """(els) => els.filter(el => {
              const id = el.getAttribute('id');
              if (id && document.querySelector('label[for="' + id + '"]')) return false;
              if (el.getAttribute('aria-label')) return false;
              if (el.getAttribute('aria-labelledby')) return false;
              return true;
            }).length""",
        )
        if unlabeled:
            issues.append(f"ラベルなし入力: {unlabeled}件")

        # 3. landmark なしチェック
        has_landmark: bool = page.eval_on_selector_all(
            "main, [role='main'], nav, [role='navigation'], header, footer",
            "(els) => els.length > 0",
        )
        if not has_landmark:
            issues.append("landmark role なし（main/nav/header/footer が0件）")

    except Exception as exc:
        logger.warning("A11y チェックに失敗しました: %s", exc)

    return issues
```

---

### Step 4: `src/crawler/page_crawler.py` — `PageData` と `crawl_page()` を更新

`PageData` に a11y フィールドを追加（末尾・デフォルト付き）:

```python
@dataclass(frozen=True)
class PageData:
    # ... 既存フィールドはそのまま ...
    stack_info: StackInfo | None = None
    state_id: str = "default"
    # ↓ 追加
    a11y_issues: tuple[str, ...] = ()  # extract_a11y_issues() の結果
```

`crawl_page()` の `PageData(...)` を構築している箇所を探し、`a11y_issues` を渡す:

```python
# crawl_page() の PageData 構築部分を探して修正
from crawler.link_extractor import extract_a11y_issues  # 既存 import がある場所に追記

# PageData(...) に a11y_issues= を追加
a11y_issues_list = extract_a11y_issues(page)

return PageData(
    # ... 既存の引数はそのまま ...
    a11y_issues=tuple(a11y_issues_list),
)
```

> `crawl_page()` は `src/crawler/page_crawler.py:260` 付近にある。
> `extract_a11y_issues` は `link_extractor` からのインポートに追記すること。

---

### Step 5: `src/generator/json_reporter.py` — a11y データを出力

`_field_dict()` に a11y フィールドを追加:

```python
def _field_dict(field: FieldData) -> dict:
    return {
        # ... 既存フィールドはそのまま ...
        "test_conditions": list(derive_conditions(field)),
        # ↓ 追加
        "aria_label": field.aria_label,
        "aria_required": field.aria_required,
        "role": field.role,
        "has_visible_label": field.has_visible_label,
    }
```

`_screen_dict()` に `a11y_issues` を追加:

```python
def _screen_dict(page: AnalyzedPage, graph: nx.DiGraph, canonical: CanonicalInfo) -> dict:
    pd = page.page_data
    return {
        # ... 既存フィールドはそのまま ...
        "variation_urls": list(canonical.variation_urls),
        # ↓ 追加
        "a11y_issues": list(pd.a11y_issues),
    }
```

---

## テストの実装（`tests/test_a11y_extraction.py` を新規作成）

```python
from __future__ import annotations

import pytest

from crawler.page_crawler import FieldData, PageData


def test_fielddata_has_a11y_fields() -> None:
    """FieldData が aria_label / aria_required / role / has_visible_label を持つ。"""
    f = FieldData(
        field_type="text",
        name="email",
        placeholder="",
        required=True,
        aria_label="メールアドレス",
        aria_required=True,
        role="textbox",
        has_visible_label=True,
    )
    assert f.aria_label == "メールアドレス"
    assert f.aria_required is True
    assert f.role == "textbox"
    assert f.has_visible_label is True


def test_fielddata_defaults_backward_compat() -> None:
    """既存コードが省略した場合のデフォルト値を確認（後方互換）。"""
    f = FieldData(field_type="text", name="q", placeholder="", required=False)
    assert f.aria_label == ""
    assert f.aria_required is False
    assert f.role == ""
    assert f.has_visible_label is False


def test_pagedata_has_a11y_issues() -> None:
    """PageData が a11y_issues フィールドを持つ。"""
    p = PageData(
        url="https://example.com/",
        title="Top",
        headings=(),
        links=(),
        forms=(),
        screenshot_path=None,
        a11y_issues=("img[alt欠落]: 3件", "ラベルなし入力: 2件"),
    )
    assert len(p.a11y_issues) == 2
    assert "img[alt欠落]" in p.a11y_issues[0]


def test_pagedata_a11y_issues_default_empty() -> None:
    """a11y_issues のデフォルトは空 tuple（後方互換）。"""
    p = PageData(
        url="https://example.com/",
        title="Top",
        headings=(),
        links=(),
        forms=(),
        screenshot_path=None,
    )
    assert p.a11y_issues == ()


def test_json_report_includes_a11y_fields() -> None:
    """JSON レポートの field 辞書に aria_label / has_visible_label が含まれる。"""
    import json
    import networkx as nx
    from analyzer.html_analyzer import AnalyzedPage
    from crawler.page_crawler import FormData
    from generator.json_reporter import generate_json_report

    field = FieldData(
        field_type="email",
        name="email",
        placeholder="",
        required=True,
        aria_label="メール",
        has_visible_label=True,
    )
    form = FormData(action="/login", method="post", fields=(field,))
    page = PageData(
        url="https://example.com/login",
        title="ログイン",
        headings=("ログイン",),
        links=(),
        forms=(form,),
        screenshot_path=None,
        a11y_issues=("ラベルなし入力: 0件",),
    )
    analyzed = AnalyzedPage(page_data=page, page_id="P001")
    g = nx.DiGraph()
    g.add_node("P001")

    report = json.loads(generate_json_report([analyzed], g, "https://example.com/"))

    screen = report["screens"][0]
    assert "a11y_issues" in screen
    field_dict = screen["forms"][0]["fields"][0]
    assert field_dict["aria_label"] == "メール"
    assert field_dict["has_visible_label"] is True


def test_extract_a11y_issues_import() -> None:
    """extract_a11y_issues が link_extractor からインポートできる。"""
    from crawler.link_extractor import extract_a11y_issues  # noqa: F401
```

---

## 完了条件

- [ ] `FieldData` に `aria_label` / `aria_required` / `role` / `has_visible_label` が追加されている
- [ ] `PageData` に `a11y_issues: tuple[str, ...]` が追加されている
- [ ] `link_extractor.py` に `extract_a11y_issues(page)` 関数が存在する
- [ ] `json_reporter.py` の出力に `aria_label` / `has_visible_label` / `a11y_issues` が含まれる
- [ ] `python -m pytest tests/ -q` が全 PASS（カバレッジ 80%+ を維持）
- [ ] `python -m pytest tests/test_a11y_extraction.py -v` が全 PASS
- [ ] 変更したファイルは上記5件のみ（`web/` / `static/` / `templates/` は触らない）

---

## Claude への報告フォーマット

実装完了後、以下を Claude に報告してください（git 操作は Claude が行う）:

```
## Phase 6-A 完了報告

### テスト結果
- test_fielddata_has_a11y_fields: PASS / FAIL
- test_fielddata_defaults_backward_compat: PASS / FAIL
- test_pagedata_has_a11y_issues: PASS / FAIL
- test_pagedata_a11y_issues_default_empty: PASS / FAIL
- test_json_report_includes_a11y_fields: PASS / FAIL
- test_extract_a11y_issues_import: PASS / FAIL
- 全テスト: X PASS, Y FAIL
- カバレッジ: XX%

### 変更ファイル（git diff --name-only で確認）
（ファイルリスト）

### エラー・問題
（あれば記載）
```

---

## スコープ外（やらないこと）

- GUI（静的ファイル・テンプレート）への表示追加（別タスクで行う）
- WCAG レベルの判定（AAA 準拠チェックなど）
- コントラスト比の計算（CSS 解析が必要なため別タスク）
- git 操作
