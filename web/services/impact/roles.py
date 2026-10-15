"""役割と操作の可否（DD-003）。"""
from __future__ import annotations

from web.services.impact.repo.errors import ImpactError

ROLES = ("admin", "analyst", "approver", "viewer")
LOCAL_ACTOR = "local"

_TABLE = {
    "view": {"admin", "analyst", "approver", "viewer"},
    "edit_system": {"admin"},
    "members": {"admin"},
    "policy": {"admin"},
    "documents": {"admin", "analyst"},
    "baselines": {"admin", "analyst"},
    "links": {"admin", "analyst"},
    "cr_write": {"admin", "analyst"},
    "analyze": {"admin", "analyst"},
    "resolve": {"admin", "analyst"},
    "override": {"admin", "analyst"},
    "actuals": {"admin", "analyst"},
    "approve": {"admin", "approver"},
    "audit_view": {"admin", "approver"},
}


def auth_off() -> bool:
    from web.auth import effective_auth_mode
    return effective_auth_mode() == "off"


def effective_actor(actor: str | None) -> str:
    """操作者。空なら "local"（認証オフの手元利用者）。"""
    return str(actor) if actor else LOCAL_ACTOR


def is_local(actor: str) -> bool:
    """認証オフの手元利用者か。この利用者だけは全対象システムで管理者として扱う（DD-003）。"""
    return actor == LOCAL_ACTOR and auth_off()


def can(role: str | None, action: str) -> bool:
    return bool(role) and role in _TABLE.get(action, set())


def role_for(conn, sid: str, actor: str) -> str | None:
    """対象システムでの役割。存在しない・メンバー外は None。認証オフは admin。"""
    if conn.execute("SELECT 1 FROM systems WHERE id = ?", (sid,)).fetchone() is None:
        return None
    if is_local(actor):
        return "admin"
    r = conn.execute("SELECT role FROM members WHERE system_id = ? AND actor = ?", (sid, actor)).fetchone()
    return r["role"] if r else None


def require(conn, sid: str, actor: str, action: str) -> str:
    role = role_for(conn, sid, actor)
    if role is None:
        raise ImpactError("対象システムが見つかりません。一覧から選び直してください。", 404)
    if not can(role, action):
        raise ImpactError("この操作の権限がありません。対象システムの管理者に役割の変更を依頼してください。", 403)
    return role
