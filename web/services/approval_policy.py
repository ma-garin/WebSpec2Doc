"""承認規則（職務分離）の設定を保存・検証する。

保存先はテナント別 instance ディレクトリの approval_policy.json（新規キー）。
既存の設定キーには触れない。rev による楽観ロックで同時編集の競合を 409 にする。
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MIN_REASON_LENGTH = 10
MAX_REASON_LENGTH = 500
SMALL_TENANT_MIN = 1
SMALL_TENANT_MAX = 5
_LOCK = threading.Lock()


class ApprovalPolicyError(ValueError):
    """入力が規則に合わない。field と利用者向けの文言を持つ。"""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


class ApprovalPolicyConflict(RuntimeError):
    """保存時の rev が現在値と一致しない（他の人が先に保存した）。"""

    def __init__(self, current: "ApprovalPolicy") -> None:
        super().__init__("他の管理者が先に保存しました。")
        self.current = current


@dataclass(frozen=True)
class ApprovalPolicy:
    rev: int = 0
    forbid_self_approval: bool = True
    small_tenant_exception: bool = False
    small_tenant_max_members: int = 2
    exception_reason: str = ""
    updated_at: str = ""
    updated_by: str = ""


def load_approval_policy(path: Path) -> ApprovalPolicy:
    if not path.is_file():
        return ApprovalPolicy()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ApprovalPolicy()
    if not isinstance(data, dict):
        return ApprovalPolicy()
    known = {key: data[key] for key in asdict(ApprovalPolicy()) if key in data}
    try:
        return _validate(ApprovalPolicy(**known))
    except (TypeError, ApprovalPolicyError):
        return ApprovalPolicy()


def save_approval_policy(
    path: Path, payload: dict[str, Any], *, updated_by: str, now: datetime | None = None
) -> tuple[ApprovalPolicy, ApprovalPolicy]:
    """検証して保存し、(変更前, 変更後) を返す。"""
    with _LOCK:
        before = load_approval_policy(path)
        rev = payload.get("rev")
        if not isinstance(rev, int) or isinstance(rev, bool):
            raise ApprovalPolicyError("rev", "画面を再読み込みしてから保存してください。")
        if rev != before.rev:
            raise ApprovalPolicyConflict(before)
        candidate = ApprovalPolicy(
            rev=before.rev + 1,
            forbid_self_approval=_bool(payload, "forbid_self_approval", before),
            small_tenant_exception=_bool(payload, "small_tenant_exception", before),
            small_tenant_max_members=_int(payload, "small_tenant_max_members", before),
            exception_reason=str(payload.get("exception_reason", before.exception_reason)).strip(),
            updated_at=(now or datetime.now(UTC)).replace(microsecond=0).isoformat(),
            updated_by=updated_by[:200],
        )
        after = _validate(candidate)
        _atomic_write(path, asdict(after))
        return before, after


def changed_fields(before: ApprovalPolicy, after: ApprovalPolicy) -> list[str]:
    skip = {"rev", "updated_at", "updated_by"}
    old, new = asdict(before), asdict(after)
    return sorted(key for key in new if key not in skip and old[key] != new[key])


def _validate(policy: ApprovalPolicy) -> ApprovalPolicy:
    if not isinstance(policy.forbid_self_approval, bool):
        raise ApprovalPolicyError("forbid_self_approval", "職務分離の設定が不正です。")
    if not isinstance(policy.small_tenant_exception, bool):
        raise ApprovalPolicyError("small_tenant_exception", "例外の設定が不正です。")
    members = policy.small_tenant_max_members
    if not isinstance(members, int) or not SMALL_TENANT_MIN <= members <= SMALL_TENANT_MAX:
        raise ApprovalPolicyError(
            "small_tenant_max_members",
            f"人数は {SMALL_TENANT_MIN}〜{SMALL_TENANT_MAX} 人の整数で入力してください。",
        )
    reason = policy.exception_reason
    if len(reason) > MAX_REASON_LENGTH:
        raise ApprovalPolicyError(
            "exception_reason", f"理由は {MAX_REASON_LENGTH} 文字以内で入力してください。"
        )
    if policy.small_tenant_exception and len(reason) < MIN_REASON_LENGTH:
        raise ApprovalPolicyError(
            "exception_reason",
            f"例外を有効にするには理由を {MIN_REASON_LENGTH} 文字以上で入力してください。",
        )
    if policy.small_tenant_exception and not policy.forbid_self_approval:
        raise ApprovalPolicyError(
            "small_tenant_exception",
            "職務分離を無効にしている場合、少人数の例外は不要です。どちらかを選び直してください。",
        )
    return policy


def _bool(payload: dict[str, Any], key: str, before: ApprovalPolicy) -> bool:
    value = payload.get(key, getattr(before, key))
    if not isinstance(value, bool):
        raise ApprovalPolicyError(key, "はい／いいえで選んでください。")
    return value


def _int(payload: dict[str, Any], key: str, before: ApprovalPolicy) -> int:
    value = payload.get(key, getattr(before, key))
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApprovalPolicyError(
            key, f"人数は {SMALL_TENANT_MIN}〜{SMALL_TENANT_MAX} 人の整数で入力してください。"
        )
    return value


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".approval_policy.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError:
        Path(tmp).unlink(missing_ok=True)
        raise


def self_approval_note(members: int | None = None) -> str | None:
    """本人承認を許すなら監査に残す注記、許さないなら None（CR-10-2・既定は禁止）。

    人数が分からない（members=None）ときは小規模テナントの例外を適用しない。
    """
    from web.routes.admin import _approval_policy_path

    policy = load_approval_policy(_approval_policy_path())
    if not policy.forbid_self_approval:
        return "本人承認（規則で許可）"
    if policy.small_tenant_exception and members is not None and members <= policy.small_tenant_max_members:
        return f"本人承認の例外: {policy.exception_reason}"
    return None
