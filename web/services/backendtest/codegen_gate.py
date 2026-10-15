"""段階 6 の採否関門と修復反復の保護（生成コードの安全ゲート）。

gate: 生成コードの問題一覧を返す（構文エラー・秘密の埋め込み・危険な SQL・日本語要約の欠落・
      期待値方式の欠落・常に真の assert・前版からの assert の弱体化や期待値の変更）。
guard: 前版との差分のうち、修復反復で変えてはいけないもの（assert・期待値・期待値方式・
       ゴールデン参照・skip の追加）を日本語の 1 行ずつで返す。1 件でもあれば承認待ちに戻す。
秘密は文字列リテラルだけを見る（``password=os.environ[...]`` のような環境変数参照は通す）。
"""
from __future__ import annotations

import ast
import re

from web.services.backendtest import redact

_SECRET_NAME = re.compile(r"(?i)pass(?:word|wd)?|pwd|secret|token|api_?key")
_CONN_STR = re.compile(r"\b(?:postgres(?:ql)?|mysql|mssql|oracle|jdbc:[a-z]+)://[^\s:/@]+:[^\s@]+@")
_DANGER_SQL = (
    ("DROP", re.compile(r"(?i)\bdrop\s+(?:table|schema|database|view|index|role|user|function)\b")),
    ("TRUNCATE", re.compile(r"(?i)\btruncate\s+(?:table\s+)?[A-Za-z_\"]")),
    ("条件なし DELETE", re.compile(r"(?i)\bdelete\s+from\s+[\w.\"]+\s*(?:;|$)")),
    ("条件なし UPDATE", re.compile(r"(?i)\bupdate\s+[\w.\"]+\s+set\b(?![\s\S]*\bwhere\b)")),
    ("ALTER", re.compile(r"(?i)\balter\s+(?:table|system|role|user|database|schema)\b")),
    ("権限の変更", re.compile(r"(?i)\b(?:grant\s+[\w, ]+\s+(?:on|to)\b|revoke\s+[\w, ]+\s+(?:on|from)\b)")),
    ("ロール・拡張の作成", re.compile(r"(?i)\bcreate\s+(?:role|user|extension)\b")),
    ("COPY PROGRAM", re.compile(r"(?i)\bcopy\b[\s\S]*\bprogram\b")),
    ("読み取り専用の解除", re.compile(r"(?i)\bread\s+write\b|default_transaction_read_only\s*(?:=|to)\s*(?:off|false)")),
    ("接続の強制切断", re.compile(r"(?i)\bpg_(?:terminate|cancel)_backend\b")),
)
_ORACLE_JA = {"method": "期待値方式", "golden": "ゴールデン参照", "state": "期待値の確定状態"}


def _problem(path, line, rule, reason, case_id=None) -> dict:
    return {"case_id": case_id, "status": "blocked", "path": path, "line": line, "rule": rule, "reason": reason}


def _parse(text: str):
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def _is_py(path: str) -> bool:
    return str(path).endswith(".py")


def _is_test_file(path: str) -> bool:
    return str(path).rsplit("/", 1)[-1].startswith("test_") and _is_py(path)


def _str_value(node) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _secret_problems(path: str, tree: ast.AST) -> list[dict]:
    out = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", None)
        pairs = []
        if isinstance(node, ast.keyword) and node.arg:
            pairs.append((node.arg, node.value))
        elif isinstance(node, ast.Assign):
            pairs += [(t.id, node.value) for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.Dict):
            pairs += [(_str_value(k) or "", v) for k, v in zip(node.keys, node.values) if k is not None]
        for name, value in pairs:
            if _SECRET_NAME.search(name) and _str_value(value):
                out.append(_problem(path, getattr(value, "lineno", line), "secret",
                                    f"password などの秘密を直接書いています（{line} 行目）。環境変数から読む形に直してください。"))
        text = _str_value(node)
        if text and any(h["kind"] == redact.KIND_SECRET for h in redact.scan(text)):
            out.append(_problem(path, line, "secret",
                                f"文字列に接続文字列・password・鍵が入っています（{line} 行目）。コードから消し、実行時の入力に任せてください。"))
    return out


def _sql_problems(path: str, tree: ast.AST) -> list[dict]:
    out = []
    for node in ast.walk(tree):
        text = _str_value(node)
        if not text:
            continue
        for label, pattern in _DANGER_SQL:
            if pattern.search(text):
                out.append(_problem(path, node.lineno, "danger_sql",
                                    f"危険な SQL（{label}）を含みます（{node.lineno} 行目）。テストでは使えない操作なので取り除いてください。"))
    return out


def _marker_case_id(func: ast.FunctionDef) -> str | None:
    for deco in func.decorator_list:
        if isinstance(deco, ast.Call) and getattr(deco.func, "attr", "") == "bt_case" and deco.args:
            return _str_value(deco.args[0])
    return None


def _skip_count(func: ast.FunctionDef) -> int:
    names = {"skip", "xfail", "skipif"}
    calls = [n for n in ast.walk(func) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") in names]
    marks = [d for d in func.decorator_list if getattr(getattr(d, "func", d), "attr", "") in names]
    return len(calls) + len(marks)


def _swallow_count(func: ast.FunctionDef) -> int:
    def broad(h: ast.ExceptHandler) -> bool:
        return h.type is None or getattr(h.type, "id", "") in {"AssertionError", "Exception", "BaseException"}
    return sum(1 for n in ast.walk(func) if isinstance(n, ast.ExceptHandler) and broad(n))


def _tests(tree: ast.AST) -> dict[str, dict]:
    out = {}
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            asserts = [n for n in ast.walk(node) if isinstance(n, ast.Assert)]
            out[node.name] = {"case_id": _marker_case_id(node), "line": node.lineno,
                              "asserts": [ast.unparse(a.test) for a in asserts],
                              "trivial": [a.lineno for a in asserts if isinstance(a.test, ast.Constant) and a.test.value],
                              "skips": _skip_count(node), "swallow": _swallow_count(node),
                              "doc": ast.get_docstring(node) or ""}
    return out


def _cases_literal(tree: ast.AST) -> dict:
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "CASES" for t in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                return {}
            return value if isinstance(value, dict) else {}
    return {}


def _test_problems(path: str, tree: ast.AST, cases: list[dict] | None) -> list[dict]:
    out = []
    for name, t in _tests(tree).items():
        if not t["doc"].strip():
            out.append(_problem(path, t["line"], "no_summary",
                                f"{name} に日本語の要約がありません。生成し直して要約を付けてください。", t["case_id"]))
        for line in t["trivial"]:
            out.append(_problem(path, line, "weakened",
                                f"常に真になる assert です（弱体化・{line} 行目）。期待値を確かめる assert に戻してください。", t["case_id"]))
    literal = _cases_literal(tree)
    for case in cases or []:
        cid = str(case.get("id", ""))
        oracle = (literal.get(cid) or {}).get("oracle") or {}
        if cid and not oracle.get("method"):
            out.append(_problem(path, None, "no_method",
                                f"ケース {cid} に期待値方式がありません。ケース表で期待値方式を選んでから生成してください。", cid))
    return out


def _compare_tests(path: str, old: dict, new: dict) -> list[tuple[str | None, str]]:
    out: list[tuple[str | None, str]] = []
    for name, before in old.items():
        after, cid = new.get(name), before["case_id"]
        if after is None:
            out.append((cid, f"{path}: テスト {name} が消えています（弱体化）。"))
            continue
        for expr in before["asserts"]:
            if expr not in after["asserts"]:
                out.append((cid, f"{path}: {name} の assert が消えたか変わっています（弱体化）: {expr}"))
        if after["skips"] > before["skips"]:
            out.append((cid, f"{path}: {name} に skip・xfail が増えています（弱体化）。"))
        if after["swallow"] > before["swallow"]:
            out.append((cid, f"{path}: {name} で例外を握りつぶしています（弱体化）。"))
    return out


def _compare_cases(path: str, old: dict, new: dict) -> list[tuple[str | None, str]]:
    out: list[tuple[str | None, str]] = []
    for cid, before in old.items():
        after = new.get(cid)
        if not isinstance(after, dict) or not isinstance(before, dict):
            out.append((cid, f"{path}: ケース {cid} が消えています（弱体化）。"))
            continue
        if before.get("expected") != after.get("expected"):
            out.append((cid, f"{path}: ケース {cid} の期待値が変わっています。"))
        b_or, a_or = before.get("oracle") or {}, after.get("oracle") or {}
        for key in sorted(set(b_or) | set(a_or)):
            if b_or.get(key) != a_or.get(key):
                label = _ORACLE_JA.get(key, f"期待値の設定（{key}）")
                out.append((cid, f"{path}: ケース {cid} の{label}が変わっています。"))
    return out


def _diffs(prev_files: list[dict], new_files: list[dict]) -> list[tuple[str | None, str]]:
    prev = {f["path"]: f["text"] for f in prev_files or []}
    out: list[tuple[str | None, str]] = []
    new_by_path = {f["path"]: f["text"] for f in new_files or []}
    for path, old_text in prev.items():
        if not _is_test_file(path):
            continue
        old_tree = _parse(old_text)
        if old_tree is None:
            continue
        new_tree = _parse(new_by_path.get(path, ""))
        if new_tree is None:
            out.append((None, f"{path}: 前の版にあったテストファイルが消えたか読めません（弱体化）。"))
            continue
        out += _compare_tests(path, _tests(old_tree), _tests(new_tree))
        out += _compare_cases(path, _cases_literal(old_tree), _cases_literal(new_tree))
    return out


def guard(prev_files: list[dict], new_files: list[dict]) -> list[str]:
    """修復反復で変えてはいけない差分（assert・期待値・方式・ゴールデン参照）。"""
    return [msg for _, msg in _diffs(prev_files, new_files)]


def gate(files: list[dict], previous_files: list[dict] | None = None, cases: list[dict] | None = None) -> list[dict]:
    """生成コードの問題一覧。各要素は {case_id, status:"blocked", path, line, rule, reason}。空なら通過。"""
    out: list[dict] = []
    for f in files or []:
        path, text = str(f.get("path", "")), str(f.get("text", ""))
        if _CONN_STR.search(text):
            out.append(_problem(path, None, "secret",
                                "接続文字列（password 付き）が入っています。コードから消し、実行時の入力に任せてください。"))
        if not _is_py(path):
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError as err:
            out.append(_problem(path, err.lineno, "syntax",
                                f"構文エラーがあります（{err.lineno} 行目: {err.msg}）。生成し直すか、該当行を直してください。"))
            continue
        out += _secret_problems(path, tree) + _sql_problems(path, tree)
        if _is_test_file(path):
            out += _test_problems(path, tree, cases)
    for cid, msg in _diffs(previous_files or [], files or []):
        rule = "weakened" if "弱体化" in msg else "expected_changed"
        out.append(_problem(None, None, rule, msg + " 承認待ちに戻します。", cid))
    return out
