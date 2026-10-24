"""画面骨格の機械判定（PLAN: synthetic-mapping-lobster.md 到達基準 1）。

全 System が templates/layouts/system.html を継承し、同じシェル・同じ部品（c-*）で描かれているかを
描画 HTML とリンクされた System 別 CSS から判定する。1 ルート × 1 観点 = 1 テスト関数。

  a. シェルの部品がちょうど 1 回ずつ（app-shell / app-sidebar / CTA / 折りたたみ / foot / topbar / content-inner）
  b. 本文（main.app-content）に h1 が無い（画面名はトップバー）
  c. サイドバーのブランドが WebSpec2Doc ＋ registry の short_name。「Document Assurance」が 0
  d. app-content-inner の最初の要素が c-page-head
  e. 独自 KPI・独自空状態の class が 0（KPI は c-kpi*、空状態は c-state* のみ）
  f. 3 ペインが無い（app-main 直下に aside / bt-list / ws-list / ws-pane が無い）
  g. System 別 CSS に生の色コードが 0
"""

from __future__ import annotations

import os
import re
from collections import Counter
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path

import pytest

os.environ.setdefault("FLASK_TESTING", "1")
os.environ.setdefault("WEBSPEC2DOC_ALLOW_LOCAL", "1")
os.environ.setdefault("WEBSPEC2DOC_AUTH_MODE", "off")

from web.system_registry import system  # noqa: E402


class Tag:
    """標準ライブラリだけで組む最小の DOM（bs4 は依存に無い）。"""

    def __init__(self, name: str, attrs: dict[str, str], parent: "Tag | None") -> None:
        self.name = name
        self.attrs = attrs
        self.parent = parent
        self.children: list["Tag | str"] = []

    def get(self, key: str, default=None):
        if key == "class":
            return self.attrs.get("class", "").split() or default
        return self.attrs.get(key, default)

    def iter(self):
        for c in self.children:
            if isinstance(c, Tag):
                yield c
                yield from c.iter()

    def find_all(self, name: str | None = None, **kw) -> list["Tag"]:
        out = []
        for t in self.iter():
            if name and name is not True and t.name != name:
                continue
            if kw.get("class_") and not t.get("class"):
                continue
            if "id" in kw and t.get("id") != kw["id"]:
                continue
            if "rel" in kw and kw["rel"] not in (t.get("rel") or "").split():
                continue
            out.append(t)
        return out

    def select_one(self, sel: str) -> "Tag | None":
        name, _, cls = sel.partition(".")
        for t in self.iter():
            if (not name or t.name == name) and (not cls or cls in (t.get("class") or [])):
                return t
        return None

    def get_text(self, sep: str = "", strip: bool = False) -> str:
        parts: list[str] = []

        def walk(node: "Tag") -> None:
            if node.name in ("script", "style"):
                return
            for c in node.children:
                if isinstance(c, Tag):
                    walk(c)
                else:
                    parts.append(c.strip() if strip else c)

        walk(self)
        return sep.join(p for p in parts if p)


_VOID = frozenset("area base br col embed hr img input link meta source track wbr".split())


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Tag("#root", {}, None)
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        node = Tag(tag, {k: (v or "") for k, v in attrs}, self.cur)
        self.cur.children.append(node)
        if tag not in _VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Tag(tag, {k: (v or "") for k, v in attrs}, self.cur))

    def handle_endtag(self, tag):
        node = self.cur
        while node is not self.root and node.name != tag:
            node = node.parent
        if node is not self.root:
            self.cur = node.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def BeautifulSoup(html: str, _parser: str = "") -> Tag:  # noqa: N802  bs4 と同じ呼び方にそろえる
    b = _Builder()
    b.feed(html)
    b.close()
    return b.root


ROOT = Path(__file__).resolve().parents[1]

# ルート → registry の key（/systems は System の選択画面なので key を持たない）
ROUTES: dict[str, str | None] = {
    "/orchestration": "cond",
    "/dashboard": "doc",
    "/test-automation": "test",
    "/auto-run": "autorun",
    "/cli": "cli",
    "/healing": "heal",
    "/docverify": "docverify",
    "/batch-test": "batch",
    "/backend-test": "backend",
    "/impact": "impact",
    "/systems": None,
}

SHELL_PARTS = (
    "app-shell",
    "app-sidebar",
    "sidebar-primary-action",
    "sidebar-toggle-btn",
    "app-sidebar-foot",
    "app-topbar",
    "app-content-inner",
)
# 主操作（CTA）を持たない画面
NO_CTA_ROUTES = frozenset({"/systems"})
_BASELINE = "基準 System 01 の旧実装。撤去は別計画"
_SELECTOR = "選択画面はサイドバー無し"
# (ルート, 観点) → skip の理由。基準画面（01/03）と選択画面（/systems）だけを外す
SKIPS: dict[tuple[str, str], str] = {
    **{(r, k): _BASELINE for r in ("/dashboard", "/auto-run") for k in ("b", "d", "g")},
    **{("/systems", k): _SELECTOR for k in ("a", "d", "e")},
}
# 旧 class（stat-card・.empty 等）を使ってよい画面。System 01 の本文（partials/view-*.html）は基準なので置き換えない
LEGACY_CLASS_ROUTES = frozenset({"/dashboard", "/auto-run"})
# 名指しで禁止する System 独自の部品 class（パターン検出の取りこぼしを防ぐ）
# 契約（C_CONTRACT）にある空状態の部品。e の「c-state 以外の empty」から外す
ALLOWED_CLASSES = frozenset({"c-empty"})
FORBIDDEN_CLASSES = frozenset({"stat-card", "stat-cards", "ch-kpi", "hl-empty", "bt-empty", "im-empty"})
THREE_PANE_CLASSES = frozenset({"bt-list", "ws-list", "ws-pane"})
# 共通 CSS（色コードの判定対象外）
SHARED_CSS = frozenset({"c-hybrid.css", "c-shell.css", "components.css"})
# 生の色コードの許可リスト: (ファイル名, 色) → 許す件数。コード枠の背景だけ
HEX_ALLOWLIST: dict[tuple[str, str], int] = {
    ("cli-mode.css", "#1F2937"): 1,
    # /systems のカードは System ごとのアクセント色で区別する設計（tokens に無い色。2026-10-24 本線判断）
    ("system-select.css", "#6D4AC4"): 3,
    ("system-select.css", "#EDE7FB"): 2,
    ("system-select.css", "#4A2E93"): 4,
    ("system-select.css", "#0E9C7A"): 3,
    ("system-select.css", "#FEF3C7"): 2,
    ("system-select.css", "#0891B2"): 3,
    ("system-select.css", "#CFFAFE"): 2,
    ("system-select.css", "#155E75"): 4,
    ("system-select.css", "#BE185D"): 3,
    ("system-select.css", "#FCE7F3"): 2,
    ("system-select.css", "#9D174D"): 4,
}

HEX_RE = re.compile(r"#[0-9A-Fa-f]{3,8}(?![0-9A-Za-z_-])")
DECL_RE = re.compile(r"[A-Za-z-]+\s*:\s*([^;{}]+)")
COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)


@lru_cache(maxsize=None)
def _html(route: str) -> str:
    from app import app

    resp = app.test_client().get(route)
    assert resp.status_code == 200, f"{route} が {resp.status_code}"
    return resp.get_data(as_text=True)


@lru_cache(maxsize=None)
def _soup(route: str) -> Tag:
    return BeautifulSoup(_html(route), "html.parser")


def _has_class(tag: Tag, name: str) -> bool:
    return name in (tag.get("class") or [])


def _all_classes(soup: Tag) -> Counter:
    counter: Counter = Counter()
    for tag in soup.find_all(class_=True):
        counter.update(tag.get("class") or [])
    return counter


def _element_children(tag: Tag) -> list[Tag]:
    return [c for c in tag.children if isinstance(c, Tag)]


def _hex_in_css(text: str) -> list[str]:
    body = COMMENT_RE.sub("", text)
    found: list[str] = []
    for value in DECL_RE.findall(body):
        found.extend(HEX_RE.findall(value))
    return found


def _system_css_files(soup: Tag) -> list[Path]:
    files: list[Path] = []
    for link in soup.find_all("link", rel="stylesheet"):
        href = (link.get("href") or "").split("?", 1)[0]
        m = re.match(r"^/static/css/([^/]+\.css)$", href)
        if m and m.group(1) not in SHARED_CSS:
            files.append(ROOT / "static" / "css" / m.group(1))
    return files


def _skip_if_listed(route: str, check: str) -> None:
    reason = SKIPS.get((route, check))
    if reason:
        pytest.skip(reason)


PARAMS = list(ROUTES)


@pytest.mark.parametrize("route", PARAMS)
def test_a_shell_parts_exactly_once(route: str) -> None:
    _skip_if_listed(route, "a")
    classes = _all_classes(_soup(route))
    soup = _soup(route)
    counts = {
        part: (len(soup.find_all(id=part)) if part == "sidebar-toggle-btn" and not classes[part] else classes[part])
        for part in SHELL_PARTS
    }
    expected = {p: 1 for p in SHELL_PARTS}
    if route in NO_CTA_ROUTES:
        expected["sidebar-primary-action"] = counts["sidebar-primary-action"] if counts["sidebar-primary-action"] <= 1 else 1
    wrong = {p: n for p, n in counts.items() if n != expected[p]}
    assert not wrong, f"{route}: 1 回でない部品 {wrong}"


@pytest.mark.parametrize("route", PARAMS)
def test_b_no_h1_in_content(route: str) -> None:
    _skip_if_listed(route, "b")
    main = _soup(route).select_one("main.sysselect-stage" if route == "/systems" else "main.app-content")
    assert main is not None, f"{route}: main.app-content が無い"
    h1s = main.find_all("h1")
    assert not h1s, f"{route}: 本文に h1 が {len(h1s)} 件（例: {h1s[0].get_text(strip=True)[:30]}）"


@pytest.mark.parametrize("route", PARAMS)
def test_c_brand(route: str) -> None:
    _skip_if_listed(route, "c")
    html = _html(route)
    assert "Document Assurance" not in html, f"{route}: 別ブランド「Document Assurance」がある"
    sidebar = _soup(route).select_one("header.app-topbar" if route == "/systems" else "aside.app-sidebar")
    assert sidebar is not None, f"{route}: aside.app-sidebar が無い"
    text = sidebar.get_text(" ", strip=True)
    assert "WebSpec2Doc" in text, f"{route}: サイドバーに WebSpec2Doc が無い"
    key = ROUTES[route]
    if key:
        short = system(key).short_name
        assert short in text, f"{route}: サイドバーに registry の short_name「{short}」が無い"


@pytest.mark.parametrize("route", PARAMS)
def test_d_page_head_first(route: str) -> None:
    _skip_if_listed(route, "d")
    inner = _soup(route).select_one(".app-content-inner")
    assert inner is not None, f"{route}: app-content-inner が無い"
    kids = _element_children(inner)
    assert kids, f"{route}: app-content-inner が空"
    first = kids[0]
    assert _has_class(first, "c-page-head"), (
        f"{route}: 先頭が <{first.name} class=\"{' '.join(first.get('class') or [])}\">（c-page-head でない）"
    )


@pytest.mark.parametrize("route", PARAMS)
def test_e_no_custom_kpi_or_empty(route: str) -> None:
    _skip_if_listed(route, "e")
    if route in LEGACY_CLASS_ROUTES:
        pytest.skip("System 01・03 の本文は基準の旧 class を許可")
    classes = _all_classes(_soup(route))
    bad = sorted(
        c
        for c in classes
        if c not in ALLOWED_CLASSES
        and (
            c in FORBIDDEN_CLASSES
        or ("kpi" in c.lower() and not c.startswith("c-kpi"))
        or ("empty" in c.lower() and not c.startswith("c-state"))
        )
    )
    assert not bad, f"{route}: 独自 KPI・独自空状態の class {bad}"


@pytest.mark.parametrize("route", PARAMS)
def test_f_no_three_pane(route: str) -> None:
    _skip_if_listed(route, "f")
    soup = _soup(route)
    main = soup.select_one(".app-main")
    if main is not None:
        scope = _element_children(main)
    else:
        scope = [t for t in soup.find_all(True)]
    bad = [
        f"<{t.name} class=\"{' '.join(t.get('class') or [])}\">"
        for t in scope
        if (t.name == "aside" and not _has_class(t, "app-sidebar"))
        or THREE_PANE_CLASSES & set(t.get("class") or [])
    ]
    assert not bad, f"{route}: 3 ペインの要素 {bad[:5]}"


@pytest.mark.parametrize("route", PARAMS)
def test_g_no_raw_hex_in_system_css(route: str) -> None:
    _skip_if_listed(route, "g")
    problems: list[str] = []
    for path in _system_css_files(_soup(route)):
        if not path.exists():
            continue
        found = Counter(h.upper() for h in _hex_in_css(path.read_text(encoding="utf-8")))
        for (name, color), n in HEX_ALLOWLIST.items():
            if name == path.name and found[color.upper()]:
                found[color.upper()] = max(0, found[color.upper()] - n)
        found = +found
        if found:
            problems.append(f"{path.name}: {sum(found.values())} 件 {dict(found.most_common(3))}")
    assert not problems, f"{route}: System 別 CSS の生の色コード {problems}"
