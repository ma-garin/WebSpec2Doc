"""System 08: PostgreSQL 接続・接続確認・本番判定・読み取り専用の強制・スナップショット.

契約は WS2D-BD-008 2 章・8 章。秘密情報（password）は引数で受け取りプロセス内だけで使い、
ログ・例外文・戻り値に含めない。本番らしい接続先と書き込み不可の環境には
(1) SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY と (2) guard_sql の両方をかける。
"""
from __future__ import annotations

import logging
import os
import re

import psycopg
from psycopg import sql as pgsql
from psycopg.rows import dict_row

try:  # 利用者に見せてよい失敗は store.StoreError に揃える（store 未配置でも単体で動く）
    from .store import StoreError
except ImportError:  # pragma: no cover - 並列実装中の暫定
    class StoreError(ValueError):
        """利用者に見せてよい理由（日本語の「理由。次の行動。」）."""

log = logging.getLogger(__name__)

CONNECT_TIMEOUT_SEC = 5
STATEMENT_TIMEOUT_MS = 30000
SNAPSHOT_MAX_ROWS = 10000
PROD_SUFFIX_ENV = "WEBSPEC2DOC_BACKENDTEST_PROD_HOST_SUFFIXES"  # 社内の本番帯（カンマ区切り・既定なし）

_PROD_WORD = re.compile(r"prod|prd|production|本番|honban|live", re.IGNORECASE)
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]{0,62}$")

# 先頭語で拒否する書き込み系（8 章の一覧＋同等の副作用を持つ文）
_WRITE_HEAD = frozenset({
    "insert", "update", "delete", "merge", "truncate", "create", "alter", "drop",
    "grant", "revoke", "call", "do", "vacuum", "reindex", "cluster", "comment",
    "lock", "refresh", "security", "import", "reassign", "discard", "listen",
    "notify", "load", "checkpoint", "prepare", "execute", "deallocate",
})
# WITH 句の中に現れたら拒否する語（データ変更 CTE）
_WRITE_INNER = frozenset({"insert", "update", "delete", "merge"})
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")


# ---------------------------------------------------------------- 本番判定

def _prod_suffixes() -> list[str]:
    raw = os.environ.get(PROD_SUFFIX_ENV, "")
    return [s.strip().lower() for s in raw.split(",") if s.strip()]


def classify(env: dict, declared_production: bool, in_recovery: bool = False) -> dict:
    """本番らしさを判定する。いずれか 1 つで production=True（利用者は下げられない）."""
    db = env.get("db") or {}
    reasons: list[str] = []
    for label, value in (("環境名", env.get("name")), ("DB 名", db.get("dbname")),
                         ("ホスト", db.get("host"))):
        m = _PROD_WORD.search(str(value or ""))
        if m:
            reasons.append(f"{label}に「{m.group(0)}」を含みます")
    host = str(db.get("host") or "").lower()
    for suf in _prod_suffixes():
        if host and host.endswith(suf):
            reasons.append(f"ホストが本番帯（{suf}）に一致します")
            break
    if declared_production:
        reasons.append("利用者が本番と申告しました")
    if in_recovery:
        reasons.append("接続先が複製先（リカバリ中）です")
    return {"production": bool(reasons), "reasons": reasons}


def must_read_only(env: dict) -> bool:
    """production=True または writable=False の環境は読み取り専用を強制する."""
    return bool(env.get("production")) or not env.get("writable", False)


# ---------------------------------------------------------------- SQL ガード

def _skip_dollar(text: str, i: int) -> int | None:
    m = re.match(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$", text[i:])
    if not m:
        return None
    tag = m.group(0)
    end = text.find(tag, i + len(tag))
    return -1 if end < 0 else end + len(tag)


def _split_statements(text: str) -> list[str]:
    """コメントと文字列リテラルを除いた上で ; 区切りに分ける（閉じ忘れは拒否）."""
    out, buf, i, n = [], [], 0, len(text)
    while i < n:
        c, nx = text[i], text[i + 1:i + 2]
        if c == "-" and nx == "-":
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif c == "/" and nx == "*":
            j = text.find("*/", i + 2)
            if j < 0:
                raise StoreError("SQL のコメントが閉じていません。/* に対応する */ を書いてください。")
            buf.append(" ")
            i = j + 2
        elif c in ("'", '"'):
            j = i + 1
            while True:
                j = text.find(c, j)
                if j < 0:
                    raise StoreError("SQL の引用符が閉じていません。引用符の対応を直してください。")
                if text[j + 1:j + 2] == c:
                    j += 2
                    continue
                break
            buf.append(" '' " if c == "'" else ' "q" ')
            i = j + 1
        elif c == "$" and (end := _skip_dollar(text, i)) is not None:
            if end < 0:
                raise StoreError("SQL の $ 引用が閉じていません。対応する $ 引用を書いてください。")
            buf.append(" '' ")
            i = end
        elif c == ";":
            out.append("".join(buf))
            buf, i = [], i + 1
        else:
            buf.append(c)
            i += 1
    out.append("".join(buf))
    return [s.strip() for s in out if s.strip()]


def _write_reason(stmt: str) -> str | None:
    words = [w.lower() for w in _WORD.findall(stmt)]
    if not words:
        return None
    head = words[0]
    if head in _WRITE_HEAD:
        return head.upper()
    if head == "copy" and "from" in words:
        return "COPY … FROM"
    if head == "with" and _WRITE_INNER.intersection(words):
        return "WITH 句の中のデータ変更"
    if head in ("select", "with") and "into" in words and "insert" not in words:
        return "SELECT … INTO（表の作成）"
    joined = " ".join(words)
    if "read write" in joined or re.search(r"\b(default_)?transaction_read_only\b", joined) \
            or re.search(r"\bsession_authorization\b|\bset role\b", joined):
        return "読み取り専用の解除"
    return None


def guard_sql(sql: str, read_only: bool) -> None:
    """読み取り専用の接続で書き込み系の文があれば StoreError（全文・; 区切りの各文を見る）."""
    if not read_only:
        return
    if not isinstance(sql, str):
        raise StoreError("SQL が文字列ではありません。SQL を文字で入力してください。")
    for stmt in _split_statements(sql):
        reason = _write_reason(stmt)
        if reason:
            raise StoreError(
                f"この接続先は読み取り専用のため、{reason} を含む SQL は実行できません。"
                "書き込みが必要なら、書き込み可能な検証環境を選んでください。")


# ---------------------------------------------------------------- 接続

def _scrub(text: str, secret: str | None) -> str:
    out = str(text)
    if secret:
        out = out.replace(secret, "***")
    return re.sub(r"(password\s*=\s*)\S+", r"\1***", out, flags=re.IGNORECASE)


def _conn_params(env: dict) -> dict:
    db = env.get("db") or {}
    kind = db.get("kind", "postgresql")
    if kind != "postgresql":
        raise StoreError("この接続先の種類には対応していません。PostgreSQL の接続先を選んでください。")
    host, dbname = str(db.get("host") or "").strip(), str(db.get("dbname") or "").strip()
    if not host or not dbname:
        raise StoreError("接続先のホストまたは DB 名が空です。環境の設定でホストと DB 名を入力してください。")
    try:
        port = int(db.get("port") or 5432)
    except (TypeError, ValueError):
        raise StoreError("ポート番号が数字ではありません。環境の設定でポート番号を直してください。") from None
    if not 0 < port < 65536:
        raise StoreError("ポート番号が範囲外です。1〜65535 の番号を入力してください。")
    return {"host": host, "port": port, "dbname": dbname,
            "user": str(db.get("user") or "").strip() or None,
            "sslmode": str(db.get("sslmode") or "prefer")}


def _user_message(err: Exception) -> tuple[str, bool, bool]:
    """(利用者向けの理由＋次の行動, reachable, auth). 生の例外文は出さない."""
    low = str(err).lower()
    if "password authentication failed" in low or "authentication failed" in low \
            or "no password supplied" in low:
        return ("ユーザー名またはパスワードが違います。入力した認証情報を確かめてください。", True, False)
    if "pg_hba.conf" in low:
        return ("接続先がこの端末からの接続を許可していません。DB 管理者に接続の許可を依頼してください。", True, False)
    if "does not exist" in low and "database" in low:
        return ("指定した DB 名が接続先にありません。環境の設定で DB 名を確かめてください。", True, True)
    if "role" in low and "does not exist" in low:
        return ("指定したユーザーが接続先にありません。環境の設定でユーザー名を確かめてください。", True, False)
    if "ssl" in low:
        return ("SSL の設定が接続先と合いません。環境の設定で SSL の指定を見直してください。", True, False)
    if "timeout" in low or "timed out" in low:
        return ("接続先が時間内に応答しませんでした。ホスト名・ポート・ネットワークを確かめてください。", False, False)
    return ("接続先に到達できませんでした。ホスト名・ポートと DB が起動しているかを確かめてください。", False, False)


def connect(env: dict, secret: str | None, read_only: bool) -> psycopg.Connection:
    """接続を返す。read_only なら接続直後にセッションを読み取り専用にする."""
    params = _conn_params(env)
    try:
        conn = psycopg.connect(password=secret or None, connect_timeout=CONNECT_TIMEOUT_SEC,
                               application_name="webspec2doc-backendtest", **params)
    except psycopg.Error as e:
        log.warning("backendtest connect failed host=%s db=%s: %s", params["host"],
                    params["dbname"], _scrub(e, secret))
        raise StoreError(_user_message(e)[0]) from None
    try:
        with conn.cursor() as cur:
            cur.execute(pgsql.SQL("SET statement_timeout = {}").format(
                pgsql.Literal(STATEMENT_TIMEOUT_MS)))
            if read_only:
                cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        conn.commit()
    except psycopg.Error as e:
        conn.close()
        log.warning("backendtest session setup failed: %s", _scrub(e, secret))
        raise StoreError("接続後の安全設定に失敗しました。接続先の権限を確かめてから、もう一度試してください。") from None
    return conn


def execute(conn: psycopg.Connection, sql: str, read_only: bool, params=None) -> list[dict]:
    """guard_sql を通してから実行する（読み取り専用の二重の守り）."""
    guard_sql(sql, read_only)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return list(cur.fetchall()) if cur.description else []


_PRIV_SQL = """
SELECT pg_is_in_recovery() AS rec,
       (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) AS su,
       has_schema_privilege(current_schema(), 'CREATE') AS can_create,
       EXISTS (SELECT 1 FROM information_schema.table_privileges
               WHERE grantee = current_user
                 AND privilege_type IN ('INSERT','UPDATE','DELETE','TRUNCATE')) AS can_dml
"""


def check(env: dict, secret: str | None) -> dict:
    """接続確認。接続できない理由は例外にせず message で返す（書き込みは一切しない）."""
    result = {"reachable": False, "auth": False, "privilege": None, "in_recovery": False,
              "message": ""}
    try:
        params = _conn_params(env)
    except StoreError as e:
        return {**result, "message": str(e)}
    try:
        conn = psycopg.connect(password=secret or None, connect_timeout=CONNECT_TIMEOUT_SEC,
                               application_name="webspec2doc-backendtest", **params)
    except psycopg.Error as e:
        log.info("backendtest check failed: %s", _scrub(e, secret))
        msg, reachable, auth = _user_message(e)
        return {**result, "reachable": reachable, "auth": auth, "message": msg}
    try:
        conn.read_only = True
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(_PRIV_SQL)
            row = cur.fetchone() or {}
        conn.rollback()
    except psycopg.Error as e:
        log.info("backendtest privilege check failed: %s", _scrub(e, secret))
        return {**result, "reachable": True, "auth": True,
                "message": "接続はできましたが権限を確かめられませんでした。DB 管理者に参照権限を確認してください。"}
    finally:
        conn.close()
    rec = bool(row.get("rec"))
    writable = not rec and bool(row.get("su") or row.get("can_create") or row.get("can_dml"))
    privilege = "write" if writable else "read"
    msg = "接続できました。" + ("このユーザーは書き込みできます。" if writable
                               else "このユーザーは参照だけできます。")
    return {**result, "reachable": True, "auth": True, "privilege": privilege,
            "in_recovery": rec, "message": msg}


# ---------------------------------------------------------------- スナップショット

def _ident(name: str, what: str) -> pgsql.Identifier:
    parts = str(name or "").split(".")
    if not 1 <= len(parts) <= 2 or not all(_IDENT.match(p) for p in parts):
        raise StoreError(f"{what}の名前に使えない文字があります。英数字と _ の名前を指定してください。")
    return pgsql.Identifier(*parts)


def _plain(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def snapshot(conn: psycopg.Connection, table: str, key, limit: int) -> dict:
    """表の行を突合キー順に最大 limit 行取る（読み取りのみ・終了後に巻き戻す）."""
    keys = [key] if isinstance(key, str) else list(key or [])
    if not keys:
        raise StoreError("突合キーが指定されていません。表の突合キーを選んでください。")
    try:
        lim = int(limit)
    except (TypeError, ValueError):
        raise StoreError("取得件数が数字ではありません。取得件数を数字で指定してください。") from None
    lim = max(1, min(lim, SNAPSHOT_MAX_ROWS))
    query = pgsql.SQL("SELECT * FROM {} ORDER BY {} LIMIT {}").format(
        _ident(table, "表"),
        pgsql.SQL(", ").join(_ident(k, "突合キー") for k in keys),
        pgsql.Literal(lim + 1))
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query)
            rows = cur.fetchall()
    except psycopg.Error as e:
        log.warning("backendtest snapshot failed table=%s: %s", table, _scrub(e, None))
        raise StoreError("表の内容を取得できませんでした。表名・突合キーと参照権限を確かめてください。") from None
    finally:
        conn.rollback()
    return {"rows": [{k: _plain(v) for k, v in r.items()} for r in rows[:lim]],
            "truncated": len(rows) > lim}
