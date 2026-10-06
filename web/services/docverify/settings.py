"""共通設定と観点チェックリスト（<base>/docverify/_settings.json・_checklists.json）。"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from web import config
from web.tenancy import scoped_output_dir

SEVERITIES = ("critical", "major", "minor")
_LEGACY = {"warning": "major", "info": "minor"}

DEFAULT_SETTINGS = {
    "severities": list(SEVERITIES),
    "types": ["曖昧", "欠落", "不整合", "誤り", "検証不能", "その他"],
    "exit_criteria": {"max_open_critical": 0, "max_open_major": 5},
}

DEFAULT_CHECKLISTS = [{
    "id": "req-29148",
    "name": "要求仕様書（ISO/IEC/IEEE 29148 の品質特性: 必要・曖昧でない・完全・一貫・実現可能・検証可能・追跡可能）",
    "items": [
        {"id": "necessary", "text": "必要: 各要求は目的の達成に必要か"},
        {"id": "unambiguous", "text": "曖昧でない: 解釈が 1 通りに定まるか"},
        {"id": "complete", "text": "完全: 条件・例外・入出力に抜けが無いか"},
        {"id": "consistent", "text": "一貫: 他の要求や用語と矛盾しないか"},
        {"id": "feasible", "text": "実現可能: 制約の中で実現できるか"},
        {"id": "verifiable", "text": "検証可能: 合否を判定できる基準があるか"},
        {"id": "traceable", "text": "追跡可能: 出所と下流への対応が辿れるか"},
    ],
}]


def normalize_severity(value):
    """v1 の warning/info を major/minor に読み替える。"""
    return _LEGACY.get(value, value)


def _root() -> Path:
    return scoped_output_dir(config.DATA_DIR) / "docverify"


def _read(name: str, default):
    path = _root() / name
    if not path.is_file():
        return json.loads(json.dumps(default))
    return json.loads(path.read_text(encoding="utf-8"))


def _write(name: str, data) -> None:
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=root, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, root / name)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def current_user() -> str:
    """認証オフ時は「ゲスト」、オン時は g.auth_user の名前。"""
    try:
        from flask import g
        user = getattr(g, "auth_user", None)
    except RuntimeError:
        user = None
    if not user:
        return "ゲスト"
    if isinstance(user, dict):
        return str(user.get("name") or user.get("username") or "ゲスト")
    return str(getattr(user, "name", None) or getattr(user, "username", None) or user)


def load_settings() -> dict:
    data = {**DEFAULT_SETTINGS, **_read("_settings.json", DEFAULT_SETTINGS)}
    data["severities"] = list(SEVERITIES)
    return {**data, "me": current_user()}


def save_settings(body: dict) -> dict:
    if not isinstance(body, dict):
        raise ValueError("設定の形が正しくありません。画面を再読み込みしてやり直してください。")
    current = load_settings()
    types = body.get("types", current["types"])
    ec = body.get("exit_criteria", current["exit_criteria"])
    if not isinstance(types, list) or not all(isinstance(t, str) and t.strip() for t in types):
        raise ValueError("指摘の種類を 1 行に 1 つずつ入力してください。")
    if not isinstance(ec, dict) or not all(isinstance(v, int) and v >= 0 for v in ec.values()):
        raise ValueError("終了条件の件数は 0 以上の整数で入力してください。")
    data = {"severities": list(SEVERITIES), "types": [t.strip() for t in types], "exit_criteria": ec}
    _write("_settings.json", data)
    return {**data, "me": current_user()}


def load_checklists() -> list:
    return _read("_checklists.json", DEFAULT_CHECKLISTS)


def save_checklists(body) -> list:
    if not isinstance(body, list):
        raise ValueError("チェックリストの形が正しくありません。画面を再読み込みしてやり直してください。")
    out = []
    for cl in body:
        if not isinstance(cl, dict) or not str(cl.get("id") or "").strip() or not str(cl.get("name") or "").strip():
            raise ValueError("チェックリストの名前を入力してください。")
        items = cl.get("items") or []
        if not isinstance(items, list) or not all(isinstance(i, dict) and i.get("id") and str(i.get("text") or "").strip() for i in items):
            raise ValueError("観点の文を入力してください。")
        out.append({"id": str(cl["id"]), "name": str(cl["name"]).strip(),
                    "items": [{"id": str(i["id"]), "text": str(i["text"]).strip()} for i in items]})
    _write("_checklists.json", out)
    return out
