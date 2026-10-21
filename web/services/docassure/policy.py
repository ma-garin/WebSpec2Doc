"""組織固有ルール。rules.engine.load_pack(extra) に渡せる dict として保存・検証する。"""
from __future__ import annotations

from . import _sidecar

_NAME = "assurance_policy.json"
LIST_KEYS = ("required_terms", "ambiguous_terms", "project_terms", "disabled_rules")
MAX_ITEMS, MAX_LEN = 200, 100


def validate(p) -> dict:
    if not isinstance(p, dict):
        raise ValueError("policy はオブジェクトで指定してください")
    unknown = set(p) - set(LIST_KEYS)
    if unknown:
        raise ValueError("未知のキーがあります: " + ",".join(sorted(map(str, unknown))))
    out = {}
    for k, v in p.items():
        if not isinstance(v, list) or len(v) > MAX_ITEMS:
            raise ValueError(f"{k} は {MAX_ITEMS} 件以内のリストで指定してください")
        if any(not isinstance(t, str) or not t.strip() or len(t) > MAX_LEN for t in v):
            raise ValueError(f"{k} の各語は 1〜{MAX_LEN} 字の文字列で指定してください")
        out[k] = [t.strip() for t in v]
    return out


def load(iid: str) -> dict:
    return _sidecar.load(iid, _NAME, {})


def save(iid: str, p) -> dict:
    v = validate(p)
    _sidecar.update(iid, _NAME, {}, lambda _old: v)
    return v


def as_pack_extra(p: dict) -> dict:
    """load_pack(extra) 用。required_terms/project_terms は params へ追記する形に写す。"""
    extra = {k: p[k] for k in ("ambiguous_terms", "disabled_rules") if p.get(k)}
    if p.get("required_terms"):
        extra["required_items"] = list(p["required_terms"])
    return extra
