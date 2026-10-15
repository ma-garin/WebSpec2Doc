"""段階 6 の生成物 bt_runtime.py のテンプレート（codegen から使う。生成コードの実行時に読まれる側）。"""

RUNTIME = r'''"""自動生成: テスト実行の土台（接続・前後スナップショット・差分・結果の記録・タイムアウト）。

results.jsonl は 1 ケース 1 行: {"case": ID, "state": pass|fail|undetermined|not_run, "facts": {...}}。

接続情報は実行時に環境変数 WS2D_BT_DB_HOST / _PORT / _NAME / _USER / _PASSWORD / _SSLMODE から読みます。接続の秘密をこのファイルに書かないでください。
pytest には -p bt_runtime で読み込まれます（tests/conftest.py からも読み込みます）。
"""
import json
import os
import re
import shlex
import signal
import subprocess
from pathlib import Path

import pytest

ENV_PREFIX = "WS2D_BT_"
SNAPSHOT_LIMIT = 100000
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*(\.[A-Za-z_][A-Za-z0-9_$]*)?$")
_WRITE_WORDS = frozenset(("insert", "update", "delete", "merge", "truncate", "create", "alter", "drop",
                          "grant", "revoke", "copy", "call", "do", "vacuum", "lock"))
_PROD_REFUSED = "本番と判定された接続先では書き込みを実行できません。検証環境を選び直してください。"


class CaseTimeout(Exception):
    """ケースの制限時間を超えた。"""


def env(name, default=""):
    return os.environ.get(ENV_PREFIX + name, default)


def is_production():
    return env("PRODUCTION", "0").lower() in ("1", "true", "yes")


def case_timeout():
    try:
        return max(1, int(env("CASE_TIMEOUT", "300")))
    except ValueError:
        return 300


def evidence_dir():
    return Path(env("EVIDENCE_DIR", "evidence"))


def connect():
    import psycopg
    conn = psycopg.connect(host=env("DB_HOST", "127.0.0.1"), port=int(env("DB_PORT", "5432")),
                           dbname=env("DB_NAME"), user=env("DB_USER"),
                           password=os.environ.get(ENV_PREFIX + "DB_PASSWORD"),
                           sslmode=env("DB_SSLMODE", "prefer"), connect_timeout=5, autocommit=True)
    if is_production():
        conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    return conn


def guard(sql, read_only=False):
    if not (read_only or is_production()):
        return
    for stmt in sql.split(";"):
        words = stmt.strip().split(None, 1)
        head = words[0].lower() if words else ""
        inner = head == "with" and re.search(r"\b(insert|update|delete|merge)\b", stmt, re.I)
        if head in _WRITE_WORDS or inner or re.search(r"read\s+write", stmt, re.I):
            raise PermissionError(_PROD_REFUSED)


def _ident(name):
    if not _IDENT.match(str(name)):
        raise ValueError("テーブル名・列名に使えない文字があります。ケース表の対象テーブルを直してください。")
    return str(name)


def _plain(value):
    return json.loads(json.dumps(value, default=str))


def execute(conn, sql, params=None, read_only=False):
    guard(sql, read_only)
    cur = conn.execute(sql, params)
    if cur.description is None:
        return []
    cols = [d.name for d in cur.description]
    return _plain([dict(zip(cols, row)) for row in cur.fetchall()])


def snapshot(conn, table, key, limit=SNAPSHOT_LIMIT):
    order = ", ".join(_ident(k) for k in key) or "1"
    rows = execute(conn, f"SELECT * FROM {_ident(table)} ORDER BY {order} LIMIT {int(limit) + 1}", read_only=True)
    return {"rows": rows[:limit], "truncated": len(rows) > limit}


def _close(before, after, tol):
    if before == after:
        return True
    try:
        return tol is not None and abs(float(before) - float(after)) <= float(tol)
    except (TypeError, ValueError):
        return False


def _index(rows, key):
    out, dup = {}, False
    for row in rows:
        k = json.dumps([row.get(c) for c in key] if key else row, sort_keys=True, default=str)
        if not key:  # キーなしは行全体で比べる。同じ行が複数あれば別の行として数える
            n = 1
            while f"{k}#{n}" in out:
                n += 1
            k = f"{k}#{n}"
        dup = dup or k in out
        out[k] = row
    return out, dup


def diff(before, after, key, exclude=(), tolerance=None):
    tol, skip = tolerance or {}, set(exclude or ())
    b, dup_b = _index(before, key)
    a, dup_a = _index(after, key)
    updated = []
    for k in sorted(b.keys() & a.keys()):
        cols = {c: [b[k].get(c), a[k].get(c)] for c in sorted(set(b[k]) | set(a[k]))
                if c not in skip and not _close(b[k].get(c), a[k].get(c), tol.get(c))}
        if cols:
            updated.append({"key": json.loads(k), "cols": cols})
    return {"added": [a[k] for k in sorted(a.keys() - b.keys())],
            "removed": [b[k] for k in sorted(b.keys() - a.keys())],
            "updated": updated, "unchanged": len(b.keys() & a.keys()) - len(updated),
            "warnings": ["突合キーが一意でないため未判定です。"] if dup_b or dup_a else []}


def seed(conn, data):
    for table, rows in (data or {}).items():
        for row in rows:
            cols = [_ident(c) for c in row]
            marks = ", ".join(["%s"] * len(cols))
            execute(conn, f"INSERT INTO {_ident(table)} ({', '.join(cols)}) VALUES ({marks})", list(row.values()))


def run_step(conn, step, out_dir):
    if not isinstance(step, dict):
        return None
    if step.get("sql"):
        execute(conn, step["sql"])
        return None
    if not step.get("command"):
        return None
    if is_production():
        raise PermissionError(_PROD_REFUSED)
    argv = shlex.split(str(step["command"]).replace("{business_date}", env("BUSINESS_DATE")))
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=step.get("timeout") or case_timeout())
    with open(out_dir / "stdout.txt", "a", encoding="utf-8") as fh:
        fh.write(proc.stdout)
    with open(out_dir / "stderr.txt", "a", encoding="utf-8") as fh:
        fh.write(proc.stderr)
    (out_dir / "rc.txt").write_text(str(proc.returncode), encoding="utf-8")
    return proc.returncode


def _key_for(oracle, table):
    key = oracle.get("key") or []
    return list(key.get(table, [])) if isinstance(key, dict) else list(key)


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


class CaseRun:
    """1 ケースの実行: データ投入 → 前スナップショット → 手順 → 後スナップショット → 差分 → 証跡。"""

    def __init__(self, conn, node):
        self.conn, self.node, self.result = conn, node, {}

    def run(self, case):
        oracle = case.get("oracle") or {}
        tables = list(oracle.get("tables") or [])
        out_dir = evidence_dir() / re.sub(r"[^A-Za-z0-9_\-]", "_", str(case.get("id", "case")))
        out_dir.mkdir(parents=True, exist_ok=True)
        self.node.bt_evidence = str(out_dir)
        seed(self.conn, case.get("data"))
        before = {t: snapshot(self.conn, t, _key_for(oracle, t)) for t in tables}
        rcs = [run_step(self.conn, s, out_dir) for s in case.get("steps") or []]
        if case.get("rerun"):  # 冪等性: 1 回目の後を「前」とし、同じ手順の 2 回目で変わらないことを見る
            before = {t: snapshot(self.conn, t, _key_for(oracle, t)) for t in tables}
            rcs += [run_step(self.conn, s, out_dir) for s in case.get("steps") or []]
        after = {t: snapshot(self.conn, t, _key_for(oracle, t)) for t in tables}
        diffs = {t: diff(before[t]["rows"], after[t]["rows"], _key_for(oracle, t),
                         oracle.get("exclude"), oracle.get("tolerance")) for t in tables}
        for name, value in (("before.json", before), ("after.json", after), ("diff.json", diffs)):
            _write(out_dir / name, value)
        self.result = {"diff": diffs, "after": {t: after[t]["rows"] for t in tables},
                       "rc": [rc for rc in rcs if rc is not None], "evidence": str(out_dir),
                       "truncated": any(s["truncated"] for s in list(before.values()) + list(after.values()))}
        return self.result

    def count(self, table, kind):
        return len(self.result.get("diff", {}).get(table, {}).get(kind, []))

    def unexpected_changes(self, case):
        changes = set((case.get("oracle") or {}).get("changes") or [])
        return {t: d for t, d in self.result.get("diff", {}).items()
                if t not in changes and (d["added"] or d["removed"] or d["updated"] or d["warnings"])}

    def _mismatch(self, case, expected_rows):
        oracle = case.get("oracle") or {}
        table = oracle.get("table") or (list(oracle.get("tables") or []) or [""])[0]
        d = diff(self.result.get("after", {}).get(table, []), _plain(expected_rows),
                 _key_for(oracle, table), oracle.get("exclude"), oracle.get("tolerance"))
        return d["added"] + d["removed"] + d["updated"] + d["warnings"]

    def alt_sql_mismatch(self, case):
        rows = execute(self.conn, case["oracle"]["alt_sql"], read_only=True)
        return self._mismatch(case, rows)

    def golden_mismatch(self, case):
        name = Path(str((case["oracle"].get("golden") or {}).get("file", ""))).name
        rows = json.loads((Path(__file__).resolve().parent / "golden" / name).read_text(encoding="utf-8"))
        return self._mismatch(case, rows)

    def schema_violations(self, case):
        out = []
        for table, cols in ((case.get("oracle") or {}).get("schema") or {}).items():
            for i, row in enumerate(self.result.get("after", {}).get(table, [])):
                out += [{"table": table, "row": i, "column": c} for c, rule in cols.items()
                        if rule.get("nullable") is False and row.get(c) is None]
        return out


@pytest.fixture
def bt(request):
    conn = connect()
    try:
        yield CaseRun(conn, request.node)
    finally:
        conn.close()


def pytest_configure(config):
    config.addinivalue_line("markers", "bt_case(case_id): ケース表のケース ID")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    if not hasattr(signal, "SIGALRM"):
        yield
        return

    def _raise(signum, frame):
        raise CaseTimeout(f"ケースの制限時間（{case_timeout()} 秒）を超えました。")

    old = signal.signal(signal.SIGALRM, _raise)
    signal.alarm(case_timeout())
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def _state(rep, call):
    """(state, 理由)。state は pass / fail / undetermined / not_run。"""
    if rep.skipped:
        return "undetermined", "期待値が未確定"
    if rep.passed:
        return "pass", ""
    exc = call.excinfo.value if call.excinfo else None
    if isinstance(exc, (CaseTimeout, subprocess.TimeoutExpired)):
        return "not_run", "タイムアウト"
    if rep.when == "setup" or not isinstance(exc, AssertionError):
        return "not_run", "実行できませんでした"
    return "fail", "期待と違う結果"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when != "call" and not (rep.when == "setup" and not rep.passed):
        return
    marker = item.get_closest_marker("bt_case")
    state, reason = _state(rep, call)
    facts = {"test": item.name, "reason": reason, "outcome": rep.outcome, "duration": round(rep.duration, 3),
             "run_id": env("RUN_ID"), "business_date": env("BUSINESS_DATE"),
             "message": "" if rep.passed else str(rep.longrepr)[-1000:],
             "evidence": getattr(item, "bt_evidence", "")}
    line = {"case": marker.args[0] if marker and marker.args else item.name, "state": state, "facts": facts}
    path = evidence_dir() / "results.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
'''
