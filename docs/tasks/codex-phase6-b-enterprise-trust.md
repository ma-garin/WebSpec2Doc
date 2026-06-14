# タスク: Phase 6-B — エンタープライズ信頼性（レポートハッシュ＋PII警告）

## ゴール

JSON レポートの `meta` に以下を追加する:

1. **`report_hash`**: screens データの SHA-256 ハッシュ — レポートが改ざんされていないことを監査者が確認できる
2. **`pii_risk_screens`**: スクリーンショットに個人情報が映り込む可能性がある画面 ID のリスト

**なぜ必要か**: 監査・コンプライアンス担当・エンタープライズ前提の顧客が
「このレポートが提出後に書き換えられていないか」を検証できるようにする。
また、スクリーンショット添付時に PII 警告を出すことで情報漏洩リスクを事前に伝える。

---

## 前提チェック（必ず実行してから始める）

```bash
source venv/bin/activate
python --version   # 3.12.x であること
python -m pytest tests/ -q 2>&1 | tail -5   # 全 PASS であること
```

---

## 触るファイル（これ以外は変更しない）

| ファイル | 変更内容 |
|---------|---------|
| `src/generator/json_reporter.py` | `generate_json_report()` に hash + PII 警告を追加 |
| `tests/test_enterprise_meta.py` | 新規作成（テスト） |

**変更禁止**:
- `src/crawler/` 以下のファイル
- `src/analyzer/` 以下のファイル
- `src/diff/` 以下のファイル
- `src/generator/html_reporter.py` / `pdf_reporter.py` / `markdown_generator.py` 等（json 以外）
- `web/` 以下のすべてのファイル
- `static/` / `templates/` 以下のすべてのファイル
- git 操作（commit は Claude が行う）

---

## 既存コードの参照（必ず読んでから実装すること）

```bash
# json_reporter.py の全体（変更対象）
cat src/generator/json_reporter.py

# _is_sensitive_form() — PII フォーム判定のロジック（参考）
grep -n "_is_sensitive_form\|_SENSITIVE\|SENSITIVE" src/crawler/page_crawler.py

# AnalyzedPage の構造確認
grep -n "class AnalyzedPage\|page_data\|page_id" src/analyzer/html_analyzer.py | head -20
```

---

## 実装指示

### Step 1: `src/generator/json_reporter.py` に以下を追加

#### インポートを追加（ファイル先頭の import 群に追記）

```python
import hashlib
import json as _json  # 標準ライブラリ json（すでに import json があればそれを使う）
```

> **注意**: ファイルに既に `import json` があるので重複 import しないこと。
> `hashlib` だけを追加する。

#### `generate_json_report()` の末尾ロジックを変更

現在の実装:

```python
def generate_json_report(pages, graph, target_url, ...):
    canonical_screens = group_canonical_screens(pages)
    return json.dumps(
        {
            "meta": { ... },
            "screens": [...],
        },
        ensure_ascii=False,
        indent=JSON_INDENT,
    )
```

変更後（screens を先に構築し、そのハッシュを meta に埋め込む）:

```python
def generate_json_report(
    pages: list[AnalyzedPage],
    graph: nx.DiGraph,
    target_url: str,
    crawl_depth: int = DEFAULT_DEPTH,
    crawl_max_pages: int = DEFAULT_MAX_PAGES,
    crawled_at: str = "",
) -> str:
    canonical_screens = group_canonical_screens(pages)
    screens_data = [_screen_dict(p, graph, canonical_screens[p.page_id]) for p in pages]

    # レポートハッシュ: screens データを deterministic JSON にして SHA-256 を計算
    screens_canonical = json.dumps(screens_data, ensure_ascii=False, sort_keys=True)
    report_hash = hashlib.sha256(screens_canonical.encode("utf-8")).hexdigest()

    # PII リスク画面: フォームの action に機密キーワードを含む画面の page_id を収集
    pii_risk_screens = _find_pii_risk_screens(pages)

    return json.dumps(
        {
            "meta": {
                "target_url": target_url,
                "crawl_depth": crawl_depth,
                "max_pages": crawl_max_pages,
                "crawled_at": crawled_at,
                "page_count": len(pages),
                "screen_count": sum(
                    1 for info in canonical_screens.values() if info.is_canonical
                ),
                "report_hash": report_hash,          # ← 追加
                "pii_risk_screens": pii_risk_screens, # ← 追加
            },
            "screens": screens_data,
        },
        ensure_ascii=False,
        indent=JSON_INDENT,
    )
```

#### `_find_pii_risk_screens()` を追加（ファイル末尾に）

```python
_PII_KEYWORDS: frozenset[str] = frozenset(
    ("payment", "checkout", "billing", "personal", "private", "credit", "card", "ssn", "passport")
)


def _find_pii_risk_screens(pages: list[AnalyzedPage]) -> list[str]:
    """フォーム action に機密キーワードを含む画面の page_id を返す。

    スクリーンショット添付時に個人情報が映り込む可能性があることを警告するための情報。
    URL のパスに PII キーワードを含む画面も対象とする。
    """
    risk_ids: list[str] = []
    for p in pages:
        pd = p.page_data
        url_lower = pd.url.lower()
        # URL 自体に PII キーワードが含まれるか
        url_has_pii = any(kw in url_lower for kw in _PII_KEYWORDS)
        # フォーム action に PII キーワードが含まれるか
        form_has_pii = any(
            any(kw in (f.action or "").lower() for kw in _PII_KEYWORDS)
            for f in pd.forms
        )
        if url_has_pii or form_has_pii:
            risk_ids.append(p.page_id)
    return risk_ids
```

---

## テストの実装（`tests/test_enterprise_meta.py` を新規作成）

```python
from __future__ import annotations

import hashlib
import json

import networkx as nx
import pytest

from analyzer.html_analyzer import AnalyzedPage
from crawler.page_crawler import FieldData, FormData, PageData
from generator.json_reporter import generate_json_report


def _page(url: str, title: str, forms: tuple = ()) -> PageData:
    return PageData(
        url=url,
        title=title,
        headings=(title,),
        links=(),
        forms=forms,
        screenshot_path=None,
    )


def _analyzed(page: PageData, page_id: str) -> AnalyzedPage:
    return AnalyzedPage(page_data=page, page_id=page_id)


def _graph(*ids: str) -> nx.DiGraph:
    g = nx.DiGraph()
    for pid in ids:
        g.add_node(pid)
    return g


def test_report_hash_exists_in_meta() -> None:
    """meta に report_hash が含まれる。"""
    p = _analyzed(_page("https://example.com/", "Top"), "P001")
    g = _graph("P001")
    report = json.loads(generate_json_report([p], g, "https://example.com/"))
    assert "report_hash" in report["meta"]
    h = report["meta"]["report_hash"]
    assert isinstance(h, str) and len(h) == 64, "SHA-256 は 64 文字の hex 文字列"


def test_report_hash_is_sha256_of_screens() -> None:
    """report_hash が screens データの SHA-256 と一致する。"""
    p = _analyzed(_page("https://example.com/", "Top"), "P001")
    g = _graph("P001")
    report = json.loads(generate_json_report([p], g, "https://example.com/"))
    screens_canonical = json.dumps(report["screens"], ensure_ascii=False, sort_keys=True)
    expected = hashlib.sha256(screens_canonical.encode("utf-8")).hexdigest()
    assert report["meta"]["report_hash"] == expected


def test_report_hash_changes_when_screens_change() -> None:
    """screens の内容が変わると report_hash も変わる。"""
    p1 = _analyzed(_page("https://example.com/", "Top"), "P001")
    p2 = _analyzed(_page("https://example.com/about", "About"), "P001")
    g = _graph("P001")
    hash1 = json.loads(generate_json_report([p1], g, "https://example.com/"))["meta"]["report_hash"]
    hash2 = json.loads(generate_json_report([p2], g, "https://example.com/"))["meta"]["report_hash"]
    assert hash1 != hash2, "コンテンツが異なれば hash は異なる"


def test_pii_risk_screens_empty_for_safe_pages() -> None:
    """PII キーワードのない URL のページは pii_risk_screens に含まれない。"""
    p = _analyzed(_page("https://example.com/search", "検索"), "P001")
    g = _graph("P001")
    report = json.loads(generate_json_report([p], g, "https://example.com/"))
    assert report["meta"]["pii_risk_screens"] == []


def test_pii_risk_screens_detects_payment_url() -> None:
    """payment を含む URL のページが pii_risk_screens に含まれる。"""
    p = _analyzed(_page("https://example.com/payment/confirm", "決済確認"), "P001")
    g = _graph("P001")
    report = json.loads(generate_json_report([p], g, "https://example.com/"))
    assert "P001" in report["meta"]["pii_risk_screens"]


def test_pii_risk_screens_detects_sensitive_form_action() -> None:
    """form action に checkout を含む画面が pii_risk_screens に含まれる。"""
    field = FieldData(field_type="text", name="card_number", placeholder="", required=True)
    form = FormData(action="/checkout/payment", method="post", fields=(field,))
    page = _page("https://example.com/cart", "カート", forms=(form,))
    p = _analyzed(page, "P001")
    g = _graph("P001")
    report = json.loads(generate_json_report([p], g, "https://example.com/"))
    assert "P001" in report["meta"]["pii_risk_screens"]


def test_pii_risk_screens_is_list_in_meta() -> None:
    """pii_risk_screens は meta に list として含まれる。"""
    p = _analyzed(_page("https://example.com/", "Top"), "P001")
    g = _graph("P001")
    report = json.loads(generate_json_report([p], g, "https://example.com/"))
    assert isinstance(report["meta"]["pii_risk_screens"], list)
```

---

## 完了条件

- [ ] `meta.report_hash` が 64 文字の hex 文字列として JSON に含まれる
- [ ] `meta.pii_risk_screens` が list として JSON に含まれる
- [ ] `python -m pytest tests/test_enterprise_meta.py -v` が全 PASS
- [ ] `python -m pytest tests/ -q` が全 PASS（カバレッジ 80%+ を維持）
- [ ] 変更したファイルは `src/generator/json_reporter.py` と `tests/test_enterprise_meta.py` の2件のみ

---

## Claude への報告フォーマット

実装完了後、以下を Claude に報告してください（git 操作は Claude が行う）:

```
## Phase 6-B 完了報告

### テスト結果
- test_report_hash_exists_in_meta: PASS / FAIL
- test_report_hash_is_sha256_of_screens: PASS / FAIL
- test_report_hash_changes_when_screens_change: PASS / FAIL
- test_pii_risk_screens_empty_for_safe_pages: PASS / FAIL
- test_pii_risk_screens_detects_payment_url: PASS / FAIL
- test_pii_risk_screens_detects_sensitive_form_action: PASS / FAIL
- test_pii_risk_screens_is_list_in_meta: PASS / FAIL
- 全テスト: X PASS, Y FAIL
- カバレッジ: XX%

### 変更ファイル（git diff --name-only で確認）
（ファイルリスト）

### エラー・問題
（あれば記載）
```

---

## スコープ外（やらないこと）

- GUI でのハッシュ表示（別タスクで行う）
- PII 画像の自動マスキング（実装コストが高いため対象外）
- HTML / PDF / Markdown レポーターへのハッシュ追加
- git 操作
