"""ARIA 妥当性ルール（C 表）。snapshot（dict）を入力に Finding を返す純関数。

snapshot["elements"] の各要素:
  id, selector, tag, attrs(dict 小文字名), role(有効ロール: 明示 or 暗黙, 無ければ None),
  visible, focusable, bbox, parent(id|None), children(list[id])
結果の規約: 適用対象が無ければ空リスト（inapplicable）。確信できないものは cant_tell。
"""
from __future__ import annotations

import re
from typing import Callable

from src.ux.a11y.data import aria_spec as S
from src.ux.a11y.models import Finding

_INT = re.compile(r"^[+-]?\d+$")
_NUM = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")


def _index(snapshot: dict) -> dict[int, dict]:
    return {e["id"]: e for e in snapshot.get("elements", [])}


def _f(rule: str, status: str, el: dict, impact: str, message: str, **ev) -> Finding:
    return Finding(rule_id=rule, status=status, selector=el.get("selector", ""),
                   bbox=el.get("bbox"), evidence=ev, impact=impact, message=message)


def _attrs(el: dict) -> dict:
    return el.get("attrs") or {}


def _live(snapshot: dict):
    return (e for e in snapshot.get("elements", []) if e.get("visible", True))


def _role_tokens(el: dict) -> list[str]:
    return _attrs(el).get("role", "").lower().split()


def _all_ids(snapshot: dict) -> set[str]:
    return {a["id"] for e in snapshot.get("elements", []) if (a := _attrs(e)).get("id")}


# ---- aria.roles -------------------------------------------------------------
def check_roles(snapshot: dict) -> list[Finding]:
    out = []
    for el in _live(snapshot):
        toks = _role_tokens(el)
        if not toks:
            continue
        good = [t for t in toks if t in S.VALID_ROLES]
        if good:
            out.append(_f("aria.roles", "pass", el, "critical", "有効なロール", role=" ".join(toks)))
            continue
        abstract = [t for t in toks if t in S.ABSTRACT_ROLES]
        msg = "抽象ロールは使えない" if abstract else "WAI-ARIA に定義の無いロール"
        out.append(_f("aria.roles", "violation", el, "critical", msg, role=" ".join(toks)))
    return out


# ---- aria.valid-attr ----------------------------------------------------------
def check_valid_attr(snapshot: dict) -> list[Finding]:
    out = []
    for el in _live(snapshot):
        names = [n for n in _attrs(el) if n.startswith("aria-")]
        if not names:
            continue
        bad = [n for n in names if n not in S.ATTR_TYPES]
        if bad:
            out.append(_f("aria.valid-attr", "violation", el, "critical",
                          "未定義の aria-* 属性", invalid=sorted(bad)))
        else:
            out.append(_f("aria.valid-attr", "pass", el, "critical", "aria-* 属性名が有効"))
    return out


# ---- aria.valid-attr-value ------------------------------------------------
def _check_value(name: str, raw: str, ids: set[str]) -> tuple[str, str]:
    """('ok'|'bad'|'unsure', 理由)。"""
    typ, extra = S.ATTR_TYPES[name]
    v = raw.strip()
    low = v.lower()
    if typ == "string":
        return "ok", ""
    if typ in ("idref", "idrefs"):
        if not v:
            return "ok", ""  # 空は「参照なし」として扱う
        parts = v.split()
        if typ == "idref" and len(parts) != 1:
            return "bad", "単一の ID が必要"
        if all(p in ids for p in parts):
            return "ok", ""
        return "unsure", "参照先 ID が文書内に見つからない"
    if not v:
        return "bad", "空の値"
    if typ == "bool":
        return ("ok", "") if low in ("true", "false") else ("bad", "true/false のみ")
    if typ == "bool_undef":
        return ("ok", "") if low in ("true", "false", "undefined") else ("bad", "true/false/undefined のみ")
    if typ == "tristate":
        return ("ok", "") if low in ("true", "false", "mixed", "undefined") else ("bad", "true/false/mixed のみ")
    if typ == "token":
        return ("ok", "") if low in extra else ("bad", "許可されたトークンではない")
    if typ == "tokens":
        parts = low.split()
        return ("ok", "") if parts and all(p in extra for p in parts) else ("bad", "許可されたトークンではない")
    if typ == "int":
        if not _INT.match(v):
            return "bad", "整数が必要"
        return ("ok", "") if int(v) >= extra else ("bad", f"{extra} 以上が必要")
    if typ == "number":
        return ("ok", "") if _NUM.match(v) else ("bad", "数値が必要")
    return "unsure", "未知の型"


def check_valid_attr_value(snapshot: dict) -> list[Finding]:
    ids = _all_ids(snapshot)
    out = []
    for el in _live(snapshot):
        bad, unsure, n_ok = [], [], 0
        for name, raw in _attrs(el).items():
            if name not in S.ATTR_TYPES:
                continue
            verdict, why = _check_value(name, raw, ids)
            if verdict == "bad":
                bad.append({"attr": name, "value": raw, "reason": why})
            elif verdict == "unsure":
                unsure.append({"attr": name, "value": raw, "reason": why})
            else:
                n_ok += 1
        if bad:
            out.append(_f("aria.valid-attr-value", "violation", el, "critical",
                          "aria-* の値が不正", invalid=bad))
        elif unsure:
            out.append(_f("aria.valid-attr-value", "cant_tell", el, "critical",
                          "参照先を確認できない", unresolved=unsure))
        elif n_ok:
            out.append(_f("aria.valid-attr-value", "pass", el, "critical", "aria-* の値が有効"))
    return out


# ---- aria.required-attr -------------------------------------------------------
_NATIVE_STATE = {
    ("input", "checkbox"): ("checkbox", "menuitemcheckbox", "switch"),
    ("input", "radio"): ("radio", "menuitemradio"),
}


def check_required_attr(snapshot: dict) -> list[Finding]:
    out = []
    for el in _live(snapshot):
        toks = [t for t in _role_tokens(el) if t in S.VALID_ROLES]
        if not toks:
            continue
        role = toks[0]
        a = _attrs(el)
        tag = el.get("tag", "")
        if role == "heading" and re.fullmatch(r"h[1-6]", tag):
            continue
        native = _NATIVE_STATE.get((tag, a.get("type", "").lower()))
        if native and role in native:
            continue
        need = list(S.ROLE_REQUIRED.get(role, ()))
        if not need:
            continue
        if role == "combobox" and a.get("aria-expanded", "").strip().lower() == "true":
            need.append("aria-controls")
        if role == "combobox" and tag in ("select",):
            continue
        if role == "separator" and not el.get("focusable"):
            continue
        missing = [n for n in need if n not in a]
        if role == "slider" and tag == "input" and a.get("type", "").lower() == "range":
            missing = []
        if missing:
            out.append(_f("aria.required-attr", "violation", el, "critical",
                          "ロールの必須属性が無い", role=role, missing=missing))
        else:
            out.append(_f("aria.required-attr", "pass", el, "critical", "必須属性あり", role=role))
    # focusable な separator は aria-valuenow が必須
    for el in _live(snapshot):
        if _role_tokens(el)[:1] == ["separator"] and el.get("focusable") and el.get("tag") != "hr":
            ok = "aria-valuenow" in _attrs(el)
            out.append(_f("aria.required-attr", "pass" if ok else "violation", el, "critical",
                          "必須属性あり" if ok else "フォーカス可能な separator に aria-valuenow が無い",
                          role="separator", missing=[] if ok else ["aria-valuenow"]))
    return out


# ---- aria.allowed-attr --------------------------------------------------------
def check_allowed_attr(snapshot: dict) -> list[Finding]:
    out = []
    for el in _live(snapshot):
        names = [n for n in _attrs(el) if n in S.ATTR_TYPES]
        if not names:
            continue
        toks = [t for t in _role_tokens(el) if t in S.VALID_ROLES]
        role = toks[0] if toks else el.get("role")
        if role not in S.ROLE_SUPPORTED:
            continue  # DPUB・不明ロール・ロール無しは判定しない
        allowed = S.GLOBAL_ATTRS | S.ROLE_SUPPORTED[role]
        bad = sorted(n for n in names if n not in allowed)
        if bad:
            out.append(_f("aria.allowed-attr", "violation", el, "critical",
                          "このロールでは使えない属性", role=role, disallowed=bad))
        else:
            out.append(_f("aria.allowed-attr", "pass", el, "critical", "属性は許可範囲", role=role))
    return out


# ---- aria.prohibited-attr -----------------------------------------------------
def check_prohibited_attr(snapshot: dict) -> list[Finding]:
    out = []
    for el in _live(snapshot):
        a = _attrs(el)
        used = [n for n in ("aria-label", "aria-labelledby") if a.get(n, "").strip()]
        if not used:
            continue
        toks = [t for t in _role_tokens(el) if t in S.VALID_ROLES]
        if toks:
            role = toks[0]
            if role in S.NAME_PROHIBITED_ROLES:
                out.append(_f("aria.prohibited-attr", "violation", el, "serious",
                              "このロールに名前は付けられない", role=role, prohibited=used))
            else:
                out.append(_f("aria.prohibited-attr", "pass", el, "serious", "名前の付与が許可されたロール", role=role))
        elif el.get("role") == "generic" or el.get("role") in (None, ""):
            # 暗黙の generic（div/span 等）。ブラウザ・支援技術の扱いが分かれるため判定不能
            if el.get("tag") in ("div", "span") or el.get("role") == "generic":
                out.append(_f("aria.prohibited-attr", "cant_tell", el, "serious",
                              "ロールの無い要素の aria-label は要確認", prohibited=used))
    return out


# ---- aria.required-children / required-parent -------------------------------
def _owned_roles(el: dict, idx: dict, cont: str) -> set[str]:
    found: set[str] = set()
    allowed_mid = set(S.ALLOWED_INTERMEDIATE.get(cont, ()))
    stack = list(el.get("children", []))
    while stack:
        c = idx.get(stack.pop())
        if c is None or not c.get("visible", True):
            continue
        r = c.get("role")
        if r in S.REQUIRED_CHILDREN.get(cont, ()):
            found.add(r)
            continue
        if r in S.NEUTRAL_ROLES or r is None or r in allowed_mid:
            stack.extend(c.get("children", []))
    return found


def check_required_children(snapshot: dict) -> list[Finding]:
    idx = _index(snapshot)
    out = []
    for el in _live(snapshot):
        toks = [t for t in _role_tokens(el) if t in S.VALID_ROLES]
        if not toks or toks[0] not in S.REQUIRED_CHILDREN:
            continue
        role = toks[0]
        a = _attrs(el)
        if a.get("aria-owns", "").strip() or a.get("aria-busy", "").lower() == "true":
            out.append(_f("aria.required-children", "cant_tell", el, "critical",
                          "aria-owns / aria-busy があり子を確定できない", role=role))
            continue
        # row は table 内で子セルを持たない行（空行）を許さないが、動的に埋まる前提もある
        found = _owned_roles(el, idx, role)
        if found:
            out.append(_f("aria.required-children", "pass", el, "critical", "必須の子あり", role=role))
        elif not el.get("children") and role in S.REVIEW_EMPTY:
            out.append(_f("aria.required-children", "cant_tell", el, "critical",
                          "子が無い（動的生成の可能性）", role=role))
        else:
            out.append(_f("aria.required-children", "violation", el, "critical",
                          "必須の子ロールが無い", role=role, required_any_of=list(S.REQUIRED_CHILDREN[role])))
    return out


def check_required_parent(snapshot: dict) -> list[Finding]:
    idx = _index(snapshot)
    owned = set()
    for e in snapshot.get("elements", []):
        for ref in _attrs(e).get("aria-owns", "").split():
            owned.add(ref)
    out = []
    for el in _live(snapshot):
        toks = [t for t in _role_tokens(el) if t in S.VALID_ROLES]
        if not toks or toks[0] not in S.REQUIRED_PARENT:
            continue
        role = toks[0]
        need = S.REQUIRED_PARENT[role]
        mid = S.PARENT_INTERMEDIATE.get(role, ())
        if _attrs(el).get("id") and _attrs(el)["id"] in owned:
            out.append(_f("aria.required-parent", "cant_tell", el, "critical",
                          "aria-owns で親子が決まる可能性", role=role))
            continue
        cur, verdict, seen = idx.get(el.get("parent")), None, 0
        while cur is not None and seen < 200:
            seen += 1
            r = cur.get("role")
            if r in need:
                verdict = "pass"
                break
            if r in S.NEUTRAL_ROLES or r is None or r in mid:
                cur = idx.get(cur.get("parent"))
                continue
            verdict = "violation"
            break
        if verdict is None:
            verdict = "violation"
        out.append(_f("aria.required-parent", verdict, el, "critical",
                      "必須の親ロールあり" if verdict == "pass" else "必須の親ロールの内側に無い",
                      role=role, required_any_of=list(need)))
    return out


# ---- aria.hidden-body / aria.hidden-focus ----------------------------------
def check_hidden_body(snapshot: dict) -> list[Finding]:
    out = []
    for el in snapshot.get("elements", []):
        if el.get("tag") != "body":
            continue
        bad = _attrs(el).get("aria-hidden", "").strip().lower() == "true"
        out.append(_f("aria.hidden-body", "violation" if bad else "pass", el, "critical",
                      "body に aria-hidden=true" if bad else "body は非表示扱いでない"))
    return out


def _hidden_roots(snapshot: dict, idx: dict) -> list[dict]:
    roots = []
    for el in snapshot.get("elements", []):
        if _attrs(el).get("aria-hidden", "").strip().lower() != "true" or el.get("tag") == "body":
            continue
        p, nested, n = idx.get(el.get("parent")), False, 0
        while p is not None and n < 200:
            n += 1
            if _attrs(p).get("aria-hidden", "").strip().lower() == "true":
                nested = True
                break
            p = idx.get(p.get("parent"))
        if not nested:
            roots.append(el)
    return roots


def _subtree(el: dict, idx: dict):
    stack = [el["id"]]
    while stack:
        e = idx.get(stack.pop())
        if e is None:
            continue
        yield e
        stack.extend(e.get("children", []))


def _tabbable(e: dict) -> bool:
    a = _attrs(e)
    if "disabled" in a:
        return False
    return a.get("tabindex", "").strip() != "-1"


def check_hidden_focus(snapshot: dict) -> list[Finding]:
    idx = _index(snapshot)
    out = []
    for root in _hidden_roots(snapshot, idx):
        if not root.get("visible", True):
            continue
        bad = [e for e in _subtree(root, idx)
               if e.get("visible", True) and e.get("focusable") and _tabbable(e)]
        if bad:
            out.append(_f("aria.hidden-focus", "violation", root, "serious",
                          "aria-hidden 内にフォーカス可能な要素がある",
                          focusable=[e.get("selector", "") for e in bad]))
        else:
            out.append(_f("aria.hidden-focus", "pass", root, "serious",
                          "aria-hidden 内にタブ到達可能な要素なし"))
    return out


# ---- aria.nested-interactive -------------------------------------------------
def check_nested_interactive(snapshot: dict) -> list[Finding]:
    idx = _index(snapshot)
    out = []
    for el in _live(snapshot):
        if el.get("role") not in S.CHILDREN_PRESENTATIONAL:
            continue
        inner = [e for e in _subtree(el, idx)
                 if e is not el and e.get("visible", True) and e.get("focusable")]
        tabbable = [e for e in inner if _tabbable(e)]
        if tabbable:
            out.append(_f("aria.nested-interactive", "violation", el, "serious",
                          "子孫が presentational のロール内にフォーカス可能な要素",
                          role=el.get("role"), focusable=[e.get("selector", "") for e in tabbable]))
        elif inner:
            out.append(_f("aria.nested-interactive", "cant_tell", el, "serious",
                          "tabindex=-1 / disabled の子孫のみ。要確認", role=el.get("role")))
        else:
            out.append(_f("aria.nested-interactive", "pass", el, "serious",
                          "フォーカス可能な子孫なし", role=el.get("role")))
    return out


ARIA_RULES: dict[str, Callable[[dict], list[Finding]]] = {
    "aria.roles": check_roles,
    "aria.valid-attr": check_valid_attr,
    "aria.valid-attr-value": check_valid_attr_value,
    "aria.required-attr": check_required_attr,
    "aria.allowed-attr": check_allowed_attr,
    "aria.prohibited-attr": check_prohibited_attr,
    "aria.required-children": check_required_children,
    "aria.required-parent": check_required_parent,
    "aria.hidden-body": check_hidden_body,
    "aria.hidden-focus": check_hidden_focus,
    "aria.nested-interactive": check_nested_interactive,
}


def run_aria_rules(snapshot: dict) -> dict[str, list[Finding]]:
    return {rid: fn(snapshot) for rid, fn in ARIA_RULES.items()}
