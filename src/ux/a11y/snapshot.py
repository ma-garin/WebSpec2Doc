"""ページのスナップショット取得（Playwright の page から 1 回の evaluate で素材を取る）。

評価スクリプト（snapshot.js）は同梱ファイルで、外部 JS・ネットワークを使わない。
Python 側は結果を不変の Element/Snapshot にし、ルール層が参照する走査ヘルパーを提供する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping

DEFAULT_MAX_ELEMENTS = 20000
_JS_PATH = Path(__file__).with_name("snapshot.js")


@dataclass(frozen=True)
class Element:
    i: int
    parent: int
    tag: str
    ns: str
    attrs: Mapping[str, str]
    selector: str
    kids: tuple[str | int, ...]
    before: str
    after: str
    style: Mapping[str, str]
    box: tuple[int, int, int, int]
    rendered: bool
    visible: bool
    focusable: bool
    tab_stop: bool
    tabindex: int | None
    inert: bool
    disabled: bool
    scroll: tuple[int, int, int, int]
    refs: Mapping[str, tuple[int, ...]]
    labels: tuple[int, ...]
    value: str | None
    in_shadow: bool

    def attr(self, name: str) -> str | None:
        return self.attrs.get(name)

    def has(self, name: str) -> bool:
        return name in self.attrs


@dataclass(frozen=True)
class Document:
    title: str
    lang: str | None
    viewport: str | None
    doctype: bool
    width: int
    height: int


@dataclass(frozen=True)
class Snapshot:
    url: str
    doc: Document
    elements: tuple[Element, ...]
    truncated: bool = False
    _ids: Mapping[str, tuple[int, ...]] = field(default_factory=dict, repr=False, compare=False)

    def __getitem__(self, i: int) -> Element:
        return self.elements[i]

    def parent(self, i: int) -> Element | None:
        p = self.elements[i].parent
        return self.elements[p] if p >= 0 else None

    def ancestors(self, i: int) -> Iterator[Element]:
        p = self.elements[i].parent
        while p >= 0:
            yield self.elements[p]
            p = self.elements[p].parent

    def children(self, i: int) -> tuple[Element, ...]:
        return tuple(self.elements[k] for k in self.elements[i].kids if isinstance(k, int))

    def by_tag(self, *tags: str) -> tuple[Element, ...]:
        wanted = set(tags)
        return tuple(e for e in self.elements if e.tag in wanted)

    def by_id(self, value: str) -> tuple[Element, ...]:
        return tuple(self.elements[k] for k in self._ids.get(value, ()))

    def duplicate_ids(self) -> dict[str, tuple[int, ...]]:
        return {k: v for k, v in self._ids.items() if len(v) > 1}

    def aria_hidden(self, i: int) -> bool:
        """自身または祖先に aria-hidden=true があるか。"""
        for e in (self.elements[i], *self.ancestors(i)):
            if (e.attr("aria-hidden") or "").strip().lower() == "true":
                return True
        return False

    def hidden_from_all(self, i: int) -> bool:
        """レンダリングされない、または visibility:hidden のとき True（支援技術にも見えない）。"""
        e = self.elements[i]
        return not e.rendered or not e.visible


def _element(raw: Mapping[str, Any]) -> Element:
    box = raw.get("box") or [0, 0, 0, 0]
    sc = raw.get("sc") or [0, 0, 0, 0]
    return Element(
        i=int(raw["i"]), parent=int(raw["p"]), tag=str(raw["tag"]), ns=str(raw.get("ns", "html")),
        attrs=dict(raw.get("attrs") or {}), selector=str(raw.get("sel", "")),
        kids=tuple(raw.get("kids") or ()), before=str(raw.get("pb", "")), after=str(raw.get("pa", "")),
        style=dict(raw.get("st") or {}), box=(int(box[0]), int(box[1]), int(box[2]), int(box[3])),
        rendered=bool(raw.get("rendered", True)), visible=bool(raw.get("visible", True)),
        focusable=bool(raw.get("focusable", False)), tab_stop=bool(raw.get("tabStop", False)),
        tabindex=raw.get("tab"), inert=bool(raw.get("inert", False)),
        disabled=bool(raw.get("disabled", False)),
        scroll=(int(sc[0]), int(sc[1]), int(sc[2]), int(sc[3])),
        refs={k: tuple(v) for k, v in (raw.get("refs") or {}).items()},
        labels=tuple(raw.get("labels") or ()), value=raw.get("val"), in_shadow=bool(raw.get("shadow", False)),
    )


def parse_snapshot(raw: Mapping[str, Any]) -> Snapshot:
    """snapshot.js の戻り値（dict）から Snapshot を作る。ブラウザ無しのテストでも使う。"""
    elements = tuple(_element(e) for e in raw["elements"])
    d = raw.get("doc") or {}
    doc = Document(
        title=str(d.get("title", "")), lang=d.get("lang"), viewport=d.get("viewport"),
        doctype=bool(d.get("doctype", False)), width=int(d.get("width", 0)), height=int(d.get("height", 0)),
    )
    ids: dict[str, list[int]] = {}
    for e in elements:
        v = e.attrs.get("id")
        if v:
            ids.setdefault(v, []).append(e.i)
    return Snapshot(
        url=str(raw.get("url", "")), doc=doc, elements=elements, truncated=bool(raw.get("truncated", False)),
        _ids={k: tuple(v) for k, v in ids.items()},
    )


def take_snapshot(page: Any, *, max_elements: int = DEFAULT_MAX_ELEMENTS) -> Snapshot:
    """Playwright の page から 1 回の evaluate でスナップショットを取得する。"""
    script = _JS_PATH.read_text(encoding="utf-8")
    return parse_snapshot(page.evaluate(script, max_elements))
