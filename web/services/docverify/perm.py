"""役割×操作の権限（NFR-06-22）・版番号の楽観ロック（NFR-06-21）・追記専用の操作記録（FR-06-149）。"""
from __future__ import annotations

import contextlib
import fcntl
import functools
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from web import config
from web.tenancy import scoped_output_dir

TENANT_ADMIN = "tenant_admin"

# 要件定義書 8.2 の表（暫定の既定。テナント管理者が変えられるかは要確認-17）
MATRIX = {
    "plan_edit": {"moderator", TENANT_ADMIN},
    "import_doc": {"author", "moderator"},
    "finding_edit": {"moderator", "reviewer", "scribe"},
    "mark_fixed": {"author", "moderator"},
    "mark_verified": {"moderator"},
    "approve": {"approver"},
    "delete_review": {"author", "moderator", TENANT_ADMIN},
    "tenant_settings": {TENANT_ADMIN},
    "audit_view": {"approver", TENANT_ADMIN},
    "tenant_purge": {TENANT_ADMIN},
}
OP_LABEL = {
    "plan_edit": "計画の編集と工程の前進", "import_doc": "文書の取り込み", "finding_edit": "指摘の追加と採否",
    "mark_fixed": "対応結果の記入", "mark_verified": "確認済みにする操作", "approve": "承認欄の記入",
    "delete_review": "レビューの削除", "tenant_settings": "送信先・規則・プリセット・参考範囲の設定",
    "audit_view": "監査ログの閲覧と出力", "tenant_purge": "テナントの消去",
}
ROLE_NAME = {"author": "作成者", "moderator": "議長", "reviewer": "レビュアー", "scribe": "記録者",
             "approver": "承認者", TENANT_ADMIN: "テナント管理者"}

M_CONFLICT = "他の人が先に更新しました。最新を読み込んでから操作してください。"
M_NO_REV = "画面の情報が古い可能性があります。再読み込みしてから操作してください。"


class Conflict(Exception):
    """版番号が合わない保存（store.save の照合から送出する。wire_R4 4 項）。"""


def _context() -> tuple[str, bool, bool]:
    """(利用者名, テナント管理者か, 認証が有効か)。テストはこの関数を差し替える。"""
    from flask import g
    from web.auth import auth_enabled
    from web.services.docverify.settings import current_user
    user = getattr(g, "auth_user", None)
    is_admin = isinstance(user, dict) and user.get("role") == "admin"
    return current_user(), is_admin, auth_enabled()


def roles_of(insp: dict | None, user: str, is_admin: bool) -> set:
    roles = {p.get("role") for p in (insp or {}).get("participants") or [] if p.get("name") == user}
    return roles | ({TENANT_ADMIN} if is_admin else set())


def can(op: str, roles: set, auth_on: bool = True) -> bool:
    """認証オフ（検証用）は全操作を許可する。"""
    return (not auth_on) or bool(MATRIX.get(op, set()) & set(roles))


def denied_message(op: str) -> str:
    who = "・".join(ROLE_NAME[r] for r in ("author", "moderator", "reviewer", "scribe", "approver", TENANT_ADMIN)
                   if r in MATRIX.get(op, set()))
    return f"{OP_LABEL.get(op, 'この操作')}の権限がありません（行えるのは{who}です）。必要なら議長かテナント管理者に依頼してください。"


def check(op: str, insp: dict | None = None) -> str | None:
    """権限が無ければ利用者向けの文を返す。あれば None。"""
    user, is_admin, auth_on = _context()
    return None if can(op, roles_of(insp, user, is_admin), auth_on) else denied_message(op)


def require(op: str):
    """Flask のルートに付ける。URL に iid があればそのレビューの役割で判定し、無ければ 403。"""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            from flask import jsonify
            insp = None
            if kwargs.get("iid"):
                from web.services.docverify import store
                try:
                    insp = store.load(kwargs["iid"])
                except (KeyError, ValueError, OSError):
                    return fn(*args, **kwargs)  # 404 の判断はルート側に任せる
            msg = check(op, insp)
            if msg:
                return jsonify(error=msg, code="forbidden"), 403
            return fn(*args, **kwargs)
        return wrapper
    return deco


# --- 楽観ロック（NFR-06-21） ----------------------------------------------------------

def rev_of(insp: dict) -> int:
    try:
        return int(insp.get("rev") or 0)
    except (TypeError, ValueError):
        return 0


def check_rev(insp: dict, client_rev, required: bool = True) -> str | None:
    """client_rev が保存中の版と違えば M_CONFLICT。None は required=False のときだけ通す（旧画面との互換）。"""
    if client_rev is None or client_rev == "":
        return M_NO_REV if required else None
    try:
        given = int(client_rev)
    except (TypeError, ValueError):
        return M_NO_REV
    return None if given == rev_of(insp) else M_CONFLICT


def bump(insp: dict) -> dict:
    return {**insp, "rev": rev_of(insp) + 1}


@contextlib.contextmanager
def locked(path: Path):
    """検査ディレクトリ単位の排他。版番号の照合から保存までを 1 つにまとめる。"""
    path.mkdir(parents=True, exist_ok=True)
    with open(path / ".r4.lock", "a+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


# --- 追記専用の操作記録（FR-06-149）: 1 行ごとに前の行のハッシュを含めた連鎖 -----------------

M_TAMPERED = "操作記録に改ざんの疑いがあります（{n} 行目）。テナント管理者に連絡してください。"
_GENESIS = "0" * 64


def _audit_path() -> Path:
    return scoped_output_dir(config.DATA_DIR) / "docverify" / "_r4_audit.jsonl"


def _digest(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _lines(path: Path) -> list[str]:
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()] if path.is_file() else []


def record(op: str, target: str, detail: dict | None = None, actor: str | None = None) -> dict:
    """操作（指摘・採否・承認・送信）を 1 行追記する。既存の行は書き換えない。"""
    path = _audit_path()
    with locked(path.parent):
        lines = _lines(path)
        prev = json.loads(lines[-1]).get("hash", _GENESIS) if lines else _GENESIS
        entry = {"seq": len(lines) + 1, "at": datetime.now(timezone.utc).isoformat(),
                 "actor": actor if actor is not None else _context()[0], "op": op, "target": target,
                 "detail": detail or {}, "prev": prev}
        entry = {**entry, "hash": _digest(entry)}
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def verify_log() -> dict:
    """連鎖を頭から検算する。最初に食い違った行番号を返す。"""
    lines = _lines(_audit_path())
    prev = _GENESIS
    for n, ln in enumerate(lines, start=1):
        try:
            e = json.loads(ln)
        except ValueError:
            return {"ok": False, "line": n, "count": len(lines), "message": M_TAMPERED.format(n=n)}
        if e.get("prev") != prev or e.get("seq") != n or e.get("hash") != _digest(e):
            return {"ok": False, "line": n, "count": len(lines), "message": M_TAMPERED.format(n=n)}
        prev = e["hash"]
    return {"ok": True, "line": None, "count": len(lines), "message": f"操作記録 {len(lines)} 行に食い違いはありません。"}
