"""サイドメニュー定義の正本。見出し・パンくず・<title> も同じ定義から出す（仕様 §5.3）。

項目は {key, label, href, icon, disabled}。icon は <svg> の内側の線パス。
各システムの定義は s_*.py の ITEMS。定義が無いシステムは空リスト。
"""

from __future__ import annotations

from . import (
    s_app,
    s_autorun,
    s_backend,
    s_batch,
    s_cli,
    s_common,
    s_cond,
    s_doc,
    s_docverify,
    s_heal,
    s_impact,
    s_test,
)

NAV: dict[str, list[dict]] = {
    "doc": s_doc.ITEMS,
    "app": s_app.ITEMS,
    "common": s_common.ITEMS,
    "test": s_test.ITEMS,
    "autorun": s_autorun.ITEMS,
    "cli": s_cli.ITEMS,
    "heal": s_heal.ITEMS,
    "docverify": s_docverify.ITEMS,
    "cond": s_cond.ITEMS,
    "batch": s_batch.ITEMS,
    "backend": s_backend.ITEMS,
    "impact": s_impact.ITEMS,
}


def nav_items(system_key: str) -> list[dict]:
    """サイドに並べる項目。未登録の system_key は空。"""
    return list(NAV.get(system_key, []))


def current_item(system_key: str, key: str) -> dict | None:
    for item in NAV.get(system_key, []):
        if item["key"] == key:
            return item
    return None


def _system_name(system_key: str) -> str:
    if system_key == "common":
        return "共通"
    from web.system_registry import system

    try:
        return system(system_key).name
    except KeyError:
        return ""


def _label(system_key: str, key: str) -> str:
    item = current_item(system_key, key)
    return item["label"] if item else ""


def page_title(system_key: str, key: str) -> str:
    """<title>＝「項目名 - システム名 - WebSpec2Doc」。"""
    return " - ".join(p for p in (_label(system_key, key), _system_name(system_key), "WebSpec2Doc") if p)


def crumb(system_key: str, key: str) -> str:
    """パンくず＝「システム名 / 項目名」（共通は「共通 / 項目名」）。"""
    return " / ".join(p for p in (_system_name(system_key), _label(system_key, key)) if p)
