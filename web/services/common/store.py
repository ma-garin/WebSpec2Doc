"""共通ストアの土台。テナント解決・原子的な書込み・冪等キー・共通エラー。

保存先は scoped_output_dir(DATA_DIR/"common") を通して決める（自前でテナントのパスを組まない）。
テナント無し（認証オフ）は data/common/_none/ に置く（§5.4）。"_none" は slug の正規表現
（英小文字・数字・ハイフン）に一致しないため、実テナントと衝突しない。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from web import config
from web.tenancy import _tenant_slug, current_auth_user, scoped_output_dir

NONE_TENANT = "_none"
_JST = timezone(timedelta(hours=9))
_LOCK = threading.RLock()


class CommonError(Exception):
    """共通 API のエラー。code は共通契約 §3.1 の語彙。"""

    STATUS = {"bad_request": 400, "unauthorized": 401, "forbidden": 403, "not_found": 404,
              "conflict": 409, "stale": 409, "too_large": 413, "upstream_failed": 502}

    def __init__(self, code: str, message: str, detail: dict | None = None,
                 retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail
        self.retryable = retryable

    @property
    def status(self) -> int:
        return self.STATUS.get(self.code, 400)

    def body(self) -> dict:
        err: dict[str, Any] = {"code": self.code, "message": self.message,
                               "retryable": self.retryable}
        if self.detail is not None:
            err["detail"] = self.detail
        return {"schema": "common.error/1", "error": err}


def tenant_key() -> str:
    """要求の入口で決まるテナント。本文の tenant 値は使わない。"""
    return _tenant_slug() or NONE_TENANT


def tenant_root() -> Path:
    base = config.DATA_DIR / "common"
    if tenant_key() == NONE_TENANT:
        return base / NONE_TENANT
    return scoped_output_dir(base)


def actor() -> str:
    user = current_auth_user()
    if user and user.get("id") is not None:
        return str(user["id"])
    return "_anonymous"


def now() -> str:
    return datetime.now(_JST).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def check_id(value: str, prefix: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(rf"{prefix}_[0-9a-f]{{12}}", value):
        raise CommonError("not_found", "指定の項目が見つかりません。一覧から選び直してください。")
    return value


def read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def lock() -> threading.RLock:
    return _LOCK


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_obj(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def idempotent(key: str | None, scope: str, fn) -> tuple[dict, int, bool]:
    """同じ Idempotency-Key の再送には最初の結果を返す。戻り値は (本文, 状態, 再送か)。"""
    if not key or not key.strip() or len(key) > 200:
        raise CommonError("bad_request", "Idempotency-Key ヘッダを付けて送信してください。")
    digest = hashlib.sha256(f"{scope}\n{key}".encode()).hexdigest()
    path = tenant_root() / "idem" / f"{digest}.json"
    with _LOCK:
        saved = read_json(path)
        if saved is not None:
            return saved["body"], int(saved["status"]), True
        body, status = fn()
        write_json(path, {"scope": scope, "status": status, "body": body, "at": now()})
        return body, status, False
