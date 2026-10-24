"""System 06 設定（出口基準・語彙・役割・AI 送信先）の保存と読み出し。

保存先: data/docverify/_settings/<tenant または _none>/settings.json（新規）。秘密値は同じ場所の secret.json（0600）に分け、応答では返さない。
rev で楽観ロックし、古い rev の PUT は 409。
"""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SEV_KEYS = ("critical", "major", "minor")
SEV_DEFAULT = {"critical": "重大", "major": "主要", "minor": "軽微"}
PAIR_SEV = {"重大": "critical", "警告": "major", "提案": "minor"}  # 対検査の内部値 → 設定のキー
TYPES = ("矛盾", "欠落", "曖昧", "不整合ID", "重複", "用語揺れ")
ROLES = ("author", "moderator", "reviewer", "approver")
PROVIDERS = ("none", "openai", "ollama")
CHANGED_RULES = ("same", "zero")
DEFAULTS = {
    "exit": {"max_open": {"critical": 0, "major": None, "minor": None}, "changed_rule": "same"},
    "labels": dict(SEV_DEFAULT),
    "types": {t: True for t in TYPES},
    "roles": {r: "" for r in ROLES},
    "ai": {"provider": "none", "endpoint": "", "model": ""},
}


class SettingsError(Exception):
    def __init__(self, status: int, code: str, message: str, extra: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra or {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def tenant_key() -> str:
    from web.tenancy import _tenant_slug
    return _tenant_slug() or "_none"


def _dir() -> Path:
    from web import config
    return Path(config.DATA_DIR) / "docverify" / "_settings" / tenant_key()


def _read(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return json.loads(json.dumps(default))


def _write(p: Path, data, mode: int = 0o644) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.chmod(tmp, mode)
        os.replace(tmp, p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


@contextmanager
def _lock():
    d = _dir()
    d.mkdir(parents=True, exist_ok=True)
    with open(d / ".lock", "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _raw() -> dict:
    return _read(_dir() / "settings.json", {"rev": 0, "values": {}, "updated_at": None, "updated_by": None})


def effective(raw: dict | None = None) -> dict:
    """既定値に利用者設定を重ねた値（判定計算が使う）。"""
    v = (raw or _raw()).get("values") or {}
    out = json.loads(json.dumps(DEFAULTS))
    for sec in out:
        if isinstance(v.get(sec), dict):
            for k, val in v[sec].items():
                if isinstance(out[sec].get(k), dict) and isinstance(val, dict):
                    out[sec][k].update(val)
                else:
                    out[sec][k] = val
    return out


def _sources(raw: dict) -> dict:
    v = raw.get("values") or {}
    src = {}
    for sec, items in DEFAULTS.items():
        for k, dv in items.items():
            if isinstance(dv, dict):
                for kk in dv:
                    src[f"{sec}.{k}.{kk}"] = "user" if kk in ((v.get(sec) or {}).get(k) or {}) else "default"
            else:
                src[f"{sec}.{k}"] = "user" if k in (v.get(sec) or {}) else "default"
    return src


def _mask(key: str) -> str:
    return ("••••" + key[-4:]) if len(key) >= 8 else ("••••" if key else "")


def _approval_policy() -> dict:
    from web.tenancy import scoped_instance_path
    p = scoped_instance_path(Path("instance") / "approval_policy.json")
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return {"source": "s10", "forbid_self_approval": bool(d.get("forbid_self_approval", True)),
                "exception": bool(d.get("small_tenant_exception")), "max_members": d.get("small_tenant_max_members"),
                "reason": d.get("exception_reason") or "", "updated_at": d.get("updated_at"), "updated_by": d.get("updated_by")}
    except FileNotFoundError:
        return {"source": "default", "forbid_self_approval": True, "exception": False, "max_members": None, "reason": ""}
    except (ValueError, OSError):
        return {"source": "broken", "forbid_self_approval": True, "exception": False, "max_members": None, "reason": ""}


def _users() -> dict:
    from web.auth import auth_enabled
    if not auth_enabled():
        return {"enabled": False, "list": []}
    from web.tenancy import current_tenant
    from web.services.auth_store import get_auth_store
    t = current_tenant()
    rows = get_auth_store().list_users(t["id"]) if t and t.get("id") else []
    return {"enabled": True, "list": [{"id": u.get("id"), "name": u.get("name") or u.get("email") or u.get("id")} for u in rows]}


def load() -> dict:
    raw = _raw()
    secret = _read(_dir() / "secret.json", {})
    return {"rev": raw.get("rev", 0), "values": effective(raw), "defaults": DEFAULTS, "sources": _sources(raw),
            "updated_at": raw.get("updated_at"), "updated_by": raw.get("updated_by"),
            "api_key_masked": _mask(secret.get("api_key", "")), "users": _users(), "approval_policy": _approval_policy(),
            "fixed": {"unverified_counts_as_pass": False}}


def _int_or_none(v, name: str):
    if v is None or v == "":
        return None
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 999:
        raise SettingsError(400, "invalid", f"{name}の上限は 0〜999 の整数か空欄（上限なし）で入力してください。")
    return v


def _validate(body: dict, users: dict) -> dict:
    v = body.get("values")
    if not isinstance(v, dict):
        raise SettingsError(400, "invalid", "設定の形が正しくありません。画面を再読み込みしてやり直してください。")
    out = {}
    ex = v.get("exit") or {}
    mo = ex.get("max_open") or {}
    out["exit"] = {"max_open": {k: _int_or_none(mo.get(k), SEV_DEFAULT[k]) for k in SEV_KEYS if k in mo},
                   "changed_rule": ex.get("changed_rule", "same")}
    if out["exit"]["changed_rule"] not in CHANGED_RULES:
        raise SettingsError(400, "invalid", "「今回の変更分」の合格条件を選び直してください。")
    labels = v.get("labels") or {}
    out["labels"] = {}
    for k in SEV_KEYS:
        if k in labels:
            s = str(labels[k] or "").strip()
            if not 1 <= len(s) <= 8:
                raise SettingsError(400, "invalid", f"重大度「{SEV_DEFAULT[k]}」の表示名は 1〜8 文字で入力してください。")
            out["labels"][k] = s
    if len(set(out["labels"].values())) != len(out["labels"]):
        raise SettingsError(400, "invalid", "重大度の表示名が重複しています。別の名前にしてください。")
    types = v.get("types") or {}
    out["types"] = {t: bool(types[t]) for t in TYPES if t in types}
    if not any({**DEFAULTS["types"], **out["types"]}.values()):
        raise SettingsError(400, "invalid", "指摘の種別を 1 つ以上有効にしてください。")
    roles = v.get("roles") or {}
    if any(roles.get(r) for r in ROLES) and not users["enabled"]:
        raise SettingsError(400, "no_users", "利用者名の記録がないため役割を割り当てられません。ログインを有効にしてから割り当ててください。")
    ids = {u["id"] for u in users["list"]}
    out["roles"] = {}
    for r in ROLES:
        if r in roles:
            uid = str(roles[r] or "")
            if uid and uid not in ids:
                raise SettingsError(400, "invalid", "割り当てた利用者が見つかりません。一覧から選び直してください。")
            out["roles"][r] = uid
    ai = v.get("ai") or {}
    out["ai"] = {}
    if "provider" in ai:
        if ai["provider"] not in PROVIDERS:
            raise SettingsError(400, "invalid", "AI の送信先を選び直してください。")
        out["ai"]["provider"] = ai["provider"]
    for k in ("endpoint", "model"):
        if k in ai:
            s = str(ai[k] or "").strip()
            if len(s) > 200 or (k == "endpoint" and s and not s.startswith(("http://", "https://"))):
                raise SettingsError(400, "invalid", "接続先は http:// か https:// で始まる URL を入力してください。")
            out["ai"][k] = s
    return {k: val for k, val in out.items() if val}


def save(body: dict, user: str) -> dict:
    if not isinstance(body, dict):
        raise SettingsError(400, "invalid", "設定の形が正しくありません。画面を再読み込みしてやり直してください。")
    users = _users()
    values = _validate(body, users)
    with _lock():
        raw = _raw()
        if body.get("rev") != raw.get("rev", 0):
            raise SettingsError(409, "conflict", "別の人が先に設定を更新しました。最新を読み直すか、自分の変更を保持して保存し直してください。",
                                {"latest": load()})
        key = body.get("api_key")
        if isinstance(key, str) and key.strip():
            _write(_dir() / "secret.json", {"api_key": key.strip()}, 0o600)
        elif body.get("clear_api_key"):
            _write(_dir() / "secret.json", {}, 0o600)
        _write(_dir() / "settings.json", {"rev": raw.get("rev", 0) + 1, "values": values, "updated_at": _now(), "updated_by": user})
    return load()


def ai_check(body: dict) -> dict:
    """保存済みまたは画面入力中の送信先へ実際に問い合わせる（5 秒で打ち切り）。"""
    import urllib.error
    import urllib.request
    cur = effective()["ai"]
    prov = body.get("provider", cur["provider"])
    endpoint = str(body.get("endpoint", cur["endpoint"]) or "").strip().rstrip("/")
    model = str(body.get("model", cur["model"]) or "").strip()
    if prov == "none":
        return {"ok": False, "message": "AI を使わない設定です。", "next": "送信先を選んでから確認してください。"}
    if prov not in PROVIDERS:
        raise SettingsError(400, "invalid", "AI の送信先を選び直してください。")
    if endpoint and not endpoint.startswith(("http://", "https://")):
        raise SettingsError(400, "invalid", "接続先は http:// か https:// で始まる URL を入力してください。")
    headers = {}
    if prov == "openai":
        url = (endpoint or "https://api.openai.com/v1") + "/models"
        key = str(body.get("api_key") or "").strip() or _read(_dir() / "secret.json", {}).get("api_key", "")
        if not key:
            return {"ok": False, "message": "API キーが未入力です。", "next": "API キーを入力して保存してから確認してください。"}
        headers["Authorization"] = "Bearer " + key
    else:
        url = (endpoint or "http://127.0.0.1:11434") + "/api/tags"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=5) as res:
            data = json.loads(res.read(2_000_000).decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        nxt = "API キーが正しいか確かめてください。" if e.code in (401, 403) else "接続先の URL が正しいか確かめてください。"
        return {"ok": False, "message": f"接続先が {e.code} を返しました。", "next": nxt}
    except (urllib.error.URLError, OSError, ValueError):
        return {"ok": False, "message": "接続先に届きませんでした。", "next": "接続先の URL と、相手のサーバが起動しているかを確かめてください。"}
    names = [m.get("id") or m.get("name") or "" for m in (data.get("data") or data.get("models") or []) if isinstance(m, dict)]
    if model and not any(n == model or n.split(":")[0] == model for n in names):
        return {"ok": False, "message": f"接続はできましたが、モデル「{model}」が見つかりません。", "next": "モデル名を一覧にある名前に直してください。",
                "models": names[:20]}
    return {"ok": True, "message": f"接続できました（モデル {len(names)} 件）。", "models": names[:20]}
