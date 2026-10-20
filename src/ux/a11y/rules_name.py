"""名前（accessible name）系ルール（設計 E1 W2・A 表）。

入力は snapshot（dict）、出力は ``RuleResult``。純関数で、DOM・ブラウザには触れない。

snapshot の前提（E1a が所有。ここで使うキーだけ）:
    elements: list[dict]  文書順。各要素は
        idx(int, 省略時は位置) / parent(int|None) / tag / attrs(dict, 小文字名)
        / accname(str|None, None=計算不能) / visible(bool|None) / selector / bbox
    truncated: bool  要素列挙が打ち切られた場合 True（全ルールが cant_tell になる）

方針: 確信できないものは違反にしない。``visible`` や ``accname`` が None なら cant_tell。
alt の内容の妥当性は判定しない（空かどうかだけ）。
"""
from __future__ import annotations

from typing import Callable, Iterable

from .models import NodeResult, RuleResult

VIOLATION = "violation"
PASS = "pass"
INAPPLICABLE = "inapplicable"
CANT_TELL = "cant_tell"

BUTTON_INPUT_TYPES = {"button", "submit", "reset"}
NON_FIELD_INPUT_TYPES = {"hidden", "submit", "reset", "button", "image"}

# aria-*-name 系（旧 axe: aria-command/input-field/toggle-field/tooltip/tab/meter/progressbar-name）
ARIA_NAME_ROLES = {
    "menuitem": "aria-command-name",
    "button": "aria-command-name",
    "link": "aria-command-name",
    "combobox": "aria-input-field-name",
    "listbox": "aria-input-field-name",
    "searchbox": "aria-input-field-name",
    "slider": "aria-input-field-name",
    "spinbutton": "aria-input-field-name",
    "textbox": "aria-input-field-name",
    "checkbox": "aria-toggle-field-name",
    "menuitemcheckbox": "aria-toggle-field-name",
    "menuitemradio": "aria-toggle-field-name",
    "radio": "aria-toggle-field-name",
    "switch": "aria-toggle-field-name",
    "option": "aria-toggle-field-name",
    "tooltip": "aria-tooltip-name",
    "tab": "aria-tab-name",
    "meter": "aria-meter-name",
    "progressbar": "aria-progressbar-name",
}


# ---------------------------------------------------------------- helpers
def attrs(el: dict) -> dict:
    return el.get("attrs") or {}


def tag(el: dict) -> str:
    return (el.get("tag") or "").lower()


def explicit_role(el: dict) -> str | None:
    raw = attrs(el).get("role")
    if not raw or not str(raw).strip():
        return None
    return str(raw).strip().split()[0].lower()


def input_type(el: dict) -> str:
    return (str(attrs(el).get("type") or "text")).strip().lower()


def has_attr(el: dict, name: str) -> bool:
    return name in attrs(el)


def attr_text(el: dict, name: str) -> str:
    v = attrs(el).get(name)
    return "" if v is None else str(v).strip()


def is_disabled(el: dict) -> bool:
    return has_attr(el, "disabled") or attr_text(el, "aria-disabled").lower() == "true"


def index_of(elements: list[dict]) -> dict:
    return {e.get("idx", i): e for i, e in enumerate(elements)}


def elements_of(snapshot: dict) -> list[dict] | None:
    """要素列を返す。取得できない・打ち切りなら None（呼び出し側が cant_tell にする）。"""
    if not isinstance(snapshot, dict) or snapshot.get("truncated"):
        return None
    els = snapshot.get("elements")
    return els if isinstance(els, list) else None


def exposed(el: dict, by_idx: dict) -> bool | None:
    """支援技術に公開されているか。True/False、判定材料が無ければ None。"""
    vis = el.get("visible")
    if vis is None:
        return None
    if not vis:
        return False
    cur, seen = el, 0
    while cur is not None and seen < 200:
        if attr_text(cur, "aria-hidden").lower() == "true":
            return False
        p = cur.get("parent")
        cur = by_idx.get(p) if p is not None else None
        seen += 1
    return True


def make_node(status: str, el: dict | None, impact: str | None, message: str, **evidence) -> NodeResult:
    el = el or {}
    return NodeResult(
        status=status,
        selector=el.get("selector") or "",
        bbox=el.get("bbox"),
        evidence=evidence,
        impact=impact if status == VIOLATION else None,
        message=message,
    )


def aggregate(nodes: Iterable[NodeResult]) -> str:
    st = [n.status for n in nodes]
    if VIOLATION in st:
        return VIOLATION
    if CANT_TELL in st:
        return CANT_TELL
    if PASS in st:
        return PASS
    return INAPPLICABLE


def make_result(rule_id: str, nodes: Iterable[NodeResult]) -> RuleResult:
    nodes = tuple(nodes)
    counts = {
        "violation": sum(n.status == VIOLATION for n in nodes),
        "pass": sum(n.status == PASS for n in nodes),
        "cant_tell": sum(n.status == CANT_TELL for n in nodes),
    }
    return RuleResult(rule_id=rule_id, status=aggregate(nodes), nodes=nodes, counts=counts)


def undecidable(rule_id: str, reason: str) -> RuleResult:
    """入力 snapshot が使えない場合。合格にも違反にもしない。"""
    return make_result(rule_id, [NodeResult(status=CANT_TELL, message=reason)])


# ---------------------------------------------------------------- generic engine
def _check_names(
    snapshot: dict,
    rule_id: str,
    impact: str,
    applies: Callable[[dict], bool],
    label: str,
    *,
    skip: Callable[[dict], bool] | None = None,
    name_override: Callable[[dict, str], str | None] | None = None,
    default_name: Callable[[dict], bool] | None = None,
) -> RuleResult:
    els = elements_of(snapshot)
    if els is None:
        return undecidable(rule_id, "snapshot が利用できない（要素列なし／打ち切り）")
    by_idx = index_of(els)
    nodes: list[NodeResult] = []
    for el in els:
        if not applies(el) or (skip and skip(el)):
            continue
        ex = exposed(el, by_idx)
        if ex is False:
            continue
        if ex is None:
            nodes.append(make_node(CANT_TELL, el, impact, "可視性が不明", reason="visible=None"))
            continue
        name = el.get("accname")
        if name is None:
            nodes.append(make_node(CANT_TELL, el, impact, "アクセシブル名を計算できない", reason="accname=None"))
            continue
        name = str(name)
        if name_override:
            forced = name_override(el, name)
            if forced:
                nodes.append(make_node(VIOLATION, el, impact, forced, accname=name))
                continue
        if name.strip():
            nodes.append(make_node(PASS, el, impact, f"{label}に名前がある", accname=name))
        elif default_name and default_name(el):
            nodes.append(make_node(PASS, el, impact, "ブラウザ既定の表示名がある", accname=name))
        else:
            nodes.append(make_node(VIOLATION, el, impact, f"{label}にアクセシブル名がない", accname=name))
    return make_result(rule_id, nodes)


# ---------------------------------------------------------------- rules
def _is_decorative_img(el: dict) -> bool:
    a = attrs(el)
    role = explicit_role(el)
    named = any(attr_text(el, k) for k in ("aria-label", "aria-labelledby", "title"))
    if role in ("none", "presentation") and not named:
        return True
    if tag(el) == "img" and "alt" in a and str(a.get("alt")) == "" and not named and role is None:
        return True
    return False


def _image_applies(el: dict) -> bool:
    t = tag(el)
    if t == "img":
        return explicit_role(el) in (None, "img", "none", "presentation")
    if t == "area":
        return has_attr(el, "href")
    if t == "input":
        return False
    return explicit_role(el) == "img"


def check_image(snapshot: dict) -> RuleResult:
    """name.image（旧 image-alt / ACT 23a2a8 / WCAG 1.1.1）。装飾画像は適用外。内容の妥当性は見ない。"""
    return _check_names(
        snapshot, "name.image", "critical", _image_applies, "画像",
        skip=_is_decorative_img,
    )


def check_input_image(snapshot: dict) -> RuleResult:
    """name.input-image（旧 input-image-alt / WCAG 1.1.1, 4.1.2）。"""
    return _check_names(
        snapshot, "name.input-image", "critical",
        lambda e: tag(e) == "input" and input_type(e) == "image", "画像ボタン",
        skip=is_disabled,
    )


def _placeholder_only(el: dict, name: str) -> str | None:
    ph = attr_text(el, "placeholder")
    if not ph or name.strip() != ph:
        return None
    if any(attr_text(el, k) for k in ("aria-label", "aria-labelledby", "title")):
        return None
    if el.get("labels"):
        return None
    return "placeholder だけが名前になっている（ラベルがない）"


def check_form_field(snapshot: dict) -> RuleResult:
    """name.form-field（旧 label / ACT e086e5 / WCAG 4.1.2）。placeholder 単独は不合格。"""
    def applies(e: dict) -> bool:
        t = tag(e)
        if t == "textarea":
            return explicit_role(e) in (None, "textbox")
        return t == "input" and input_type(e) not in NON_FIELD_INPUT_TYPES and explicit_role(e) in (
            None, "textbox", "searchbox", "combobox", "spinbutton", "slider", "checkbox", "radio", "switch")
    return _check_names(
        snapshot, "name.form-field", "critical", applies, "入力欄",
        skip=is_disabled, name_override=_placeholder_only,
    )


def check_select(snapshot: dict) -> RuleResult:
    """name.select（旧 select-name / ACT e086e5 / WCAG 4.1.2）。"""
    return _check_names(
        snapshot, "name.select", "critical",
        lambda e: tag(e) == "select" and explicit_role(e) in (None, "combobox", "listbox"), "選択欄",
        skip=is_disabled,
    )


def check_button(snapshot: dict) -> RuleResult:
    """name.button（旧 button-name / ACT 97a4e1 / WCAG 4.1.2）。

    input[type=submit/reset] は value が無くてもブラウザ既定の表示名があるため違反にしない。
    """
    def applies(e: dict) -> bool:
        t, role = tag(e), explicit_role(e)
        if role == "button":
            return True
        if role is not None:
            return False
        if t == "button":
            return True
        return t == "input" and input_type(e) in BUTTON_INPUT_TYPES

    def default_label(e: dict) -> bool:
        return tag(e) == "input" and input_type(e) in ("submit", "reset") and not has_attr(e, "value")

    return _check_names(
        snapshot, "name.button", "critical", applies, "ボタン",
        skip=is_disabled, default_name=default_label,
    )


def check_link(snapshot: dict) -> RuleResult:
    """name.link（旧 link-name / ACT c487ae / WCAG 2.4.4, 4.1.2）。画像だけのリンクは子の名前で判定済み。"""
    def applies(e: dict) -> bool:
        role = explicit_role(e)
        if role == "link":
            return True
        return tag(e) == "a" and has_attr(e, "href") and role is None
    return _check_names(snapshot, "name.link", "serious", applies, "リンク")


def check_frame(snapshot: dict) -> RuleResult:
    """name.frame（旧 frame-title / ACT cae760 / WCAG 4.1.2）。"""
    return _check_names(
        snapshot, "name.frame", "serious",
        lambda e: tag(e) in ("iframe", "frame"), "フレーム",
        skip=lambda e: explicit_role(e) in ("none", "presentation"),
    )


def check_aria_role_required(snapshot: dict) -> RuleResult:
    """name.aria-role-required（旧 aria-*-name 7 種）。native 要素は他ルールが扱うため除外。"""
    def applies(e: dict) -> bool:
        role = explicit_role(e)
        if role not in ARIA_NAME_ROLES:
            return False
        t = tag(e)
        if t in ("input", "textarea", "select", "button"):
            return False
        return not (t in ("a", "area") and has_attr(e, "href"))
    return _check_names(snapshot, "name.aria-role-required", "serious", applies, "ARIA ウィジェット")


def check_heading(snapshot: dict) -> RuleResult:
    """name.heading（旧 empty-heading。best-practice / ACT ffd0e9）。"""
    def applies(e: dict) -> bool:
        role = explicit_role(e)
        if role is not None:
            return role == "heading"
        return tag(e) in ("h1", "h2", "h3", "h4", "h5", "h6")
    return _check_names(snapshot, "name.heading", "minor", applies, "見出し")


RULES: dict[str, Callable[[dict], RuleResult]] = {
    "name.image": check_image,
    "name.input-image": check_input_image,
    "name.form-field": check_form_field,
    "name.select": check_select,
    "name.button": check_button,
    "name.link": check_link,
    "name.frame": check_frame,
    "name.aria-role-required": check_aria_role_required,
    "name.heading": check_heading,
}
