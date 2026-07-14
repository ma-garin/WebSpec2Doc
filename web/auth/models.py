"""認証ドメインモデル（すべてイミュータブル）。"""

from __future__ import annotations

from dataclasses import dataclass

Role = str  # "owner" | "admin" | "member"

VALID_ROLES: frozenset[str] = frozenset({"owner", "admin", "member"})


@dataclass(frozen=True)
class User:
    email: str
    created_at: str
    last_login_at: str

    def with_last_login(self, at: str) -> "User":
        """last_login_at を更新した新インスタンスを返す（非破壊）。"""
        return User(email=self.email, created_at=self.created_at, last_login_at=at)

    def to_dict(self) -> dict[str, str]:
        return {
            "email": self.email,
            "created_at": self.created_at,
            "last_login_at": self.last_login_at,
        }

    @staticmethod
    def from_dict(data: dict[str, str]) -> "User":
        return User(
            email=data["email"],
            created_at=data["created_at"],
            last_login_at=data.get("last_login_at", data["created_at"]),
        )


@dataclass(frozen=True)
class Tenant:
    id: str
    name: str
    created_at: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name, "created_at": self.created_at}

    @staticmethod
    def from_dict(data: dict[str, str]) -> "Tenant":
        return Tenant(id=data["id"], name=data["name"], created_at=data["created_at"])


@dataclass(frozen=True)
class Membership:
    user_email: str
    tenant_id: str
    role: Role

    def to_dict(self) -> dict[str, str]:
        return {
            "user_email": self.user_email,
            "tenant_id": self.tenant_id,
            "role": self.role,
        }

    @staticmethod
    def from_dict(data: dict[str, str]) -> "Membership":
        role = data.get("role", "member")
        return Membership(
            user_email=data["user_email"],
            tenant_id=data["tenant_id"],
            role=role if role in VALID_ROLES else "member",
        )
