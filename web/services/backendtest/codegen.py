"""段階 6: ケース表から pytest コードを生成する（テンプレート方式・LLM 不使用）。

生成物は 3 つ。``bt_runtime.py``（接続・前後スナップショット・差分・results.jsonl・ケース単位の
タイムアウト）、``tests/conftest.py``、``tests/test_cases.py``（ケース 1 行 = テスト 1 件）。
接続情報は実行時に環境変数 ``WS2D_BT_*`` から読み、パスワードはコードに書かない。
期待値が確定していないケースは skip にして「未判定」として残す（合格に数えない）。
"""
from __future__ import annotations

import pprint
import re

from web.services.backendtest.codegen_runtime import RUNTIME

CONFIRMED_STATES = frozenset({"auto", "human"})
METHOD_JA = {
    "db_diff": "DB 前後比較",
    "alt_sql": "別経路計算",
    "golden": "ゴールデン（承認済み期待値）",
    "schema": "スキーマ検査",
}
UNDECIDED = "未判定: 期待値が確定していません。期待値の確定はシニア QA が行います。"

CONFTEST = '''"""自動生成: 実行の土台（bt_runtime）を必ず読み込む。"""


def pytest_configure(config):
    if not config.pluginmanager.has_plugin("bt_runtime"):
        config.pluginmanager.import_plugin("bt_runtime")
'''


def _first(text: str, limit: int = 60) -> str:
    head = re.split(r"[。\n]", str(text).strip(), maxsplit=1)[0].strip()
    return head[:limit].rstrip("、。 ")


def summarize(case: dict) -> str:
    """ケースの日本語要約（3 文以内。FR-08-106）。"""
    oracle = case.get("oracle") or {}
    what = _first(case.get("title") or case.get("name") or case.get("expected") or "")
    first = f"{what}を確かめます。" if what else "ケース表の手順を実行し、結果を記録します。"
    tables = "・".join(str(t) for t in oracle.get("tables") or [])
    method = METHOD_JA.get(oracle.get("method"), "方式が未設定のまま")
    second = f"判定は{method}で行います" + (f"（対象: {tables}）。" if tables else "。")
    if oracle.get("state") in CONFIRMED_STATES and oracle.get("method") in METHOD_JA:
        third = "期待値は確定済みで、自動で合否を出します。"
    else:
        third = "期待値が未確定のため、結果は「未判定」として残します。"
    return first + second + third


def summarize_sql(case: dict) -> str:
    """別経路 SQL の日本語要約（段階 4 で使う）。SQL が無ければ空文字。"""
    sql = str((case.get("oracle") or {}).get("alt_sql") or "").strip()
    if not sql:
        return ""
    tables = list(dict.fromkeys(re.findall(r"\b(?:from|join)\s+([A-Za-z_][\w.]*)", sql, re.I)))
    parts = [f"{'・'.join(tables) or '対象'} テーブルを読み"]
    if re.search(r"\bwhere\b", sql, re.I):
        parts.append("条件で絞り込み")
    if re.search(r"\bgroup\s+by\b", sql, re.I):
        parts.append("グループごとにまとめ")
    for word, ja in (("count", "件数を数え"), ("sum", "合計し"), ("avg", "平均し"), ("max", "最大値を取り"), ("min", "最小値を取り")):
        if re.search(rf"\b{word}\s*\(", sql, re.I):
            parts.append(ja)
    return "、".join(parts) + "ます。読み取りだけで、データは変えません。"


def _test_names(cases: list[dict]) -> dict[str, str]:
    names: dict[str, str] = {}
    used: set[str] = set()
    for case in cases:
        base = "test_" + (re.sub(r"\W+", "_", str(case["id"]), flags=re.ASCII).strip("_").lower() or "case")
        name, n = base, 2
        while name in used:
            name, n = f"{base}_{n}", n + 1
        used.add(name)
        names[str(case["id"])] = name
    return names


def _assert_lines(case: dict) -> list[str]:
    oracle = case.get("oracle") or {}
    method = oracle.get("method")
    if oracle.get("state") not in CONFIRMED_STATES or method not in METHOD_JA:
        return [f"pytest.skip({UNDECIDED!r})"]
    lines: list[str] = []
    if method == "db_diff":
        lines.append('assert not result["truncated"], "スナップショットが行上限を超えたため前後比較できません"')
        lines.append('assert bt.unexpected_changes(case) == {}, "変わってはいけないテーブルが変わりました"')
        for table, expect in sorted((oracle.get("expect") or {}).items()):
            for kind in ("added", "removed", "updated"):
                if kind in expect:
                    lines.append(f'assert bt.count({table!r}, {kind!r}) == {int(expect[kind])}, "件数が期待と違います"')
    elif method == "alt_sql":
        lines.append('assert bt.alt_sql_mismatch(case) == [], "別経路の計算結果と一致しません"')
    elif method == "golden":
        lines.append('assert bt.golden_mismatch(case) == [], "承認済み期待値と一致しません"')
    else:
        lines.append('assert bt.schema_violations(case) == [], "定義に合わない値があります"')
    if "expect_rc" in oracle:
        lines.append('assert all(rc == case["oracle"]["expect_rc"] for rc in result["rc"]), "終了コードが期待と違います"')
    return lines


def _doc(text: str) -> str:
    return str(text).replace("\\", "＼").replace('"', "”").replace("\n", " ")


def _case_literal(case: dict) -> dict:
    keys = ("id", "title", "steps", "data", "expected", "oracle")
    return {k: case[k] for k in keys if k in case}


def _test_module(cases: list[dict], names: dict[str, str], summaries: dict[str, str]) -> str:
    literal = {str(c["id"]): _case_literal(c) for c in cases}
    out = [
        f'"""自動生成: ケース表から作ったテスト（{len(cases)} 件）。',
        "",
        "実行は製品の実行画面から行います。期待値・assert を変えるにはシニア QA の承認が要ります。",
        '"""',
        "import pytest",
        "",
        "CASES = " + pprint.pformat(literal, width=100, sort_dicts=False),
    ]
    for case in cases:
        cid = str(case["id"])
        out += ["", "", f"@pytest.mark.bt_case({cid!r})", f"def {names[cid]}(bt):",
                f'    """{_doc(summaries[cid])}"""', f"    case = CASES[{cid!r}]", "    result = bt.run(case)"]
        out += ["    " + line for line in _assert_lines(case)]
    return "\n".join(out) + "\n"


def generate(job: dict) -> dict:
    """job（cases・targets・facts を持つ dict）から生成物を返す。入力は変更しない。"""
    cases = [c for c in (job.get("cases") or []) if isinstance(c, dict) and c.get("id")]
    names = _test_names(cases)
    summaries = {str(c["id"]): summarize(c) for c in cases}
    files = [
        {"path": "bt_runtime.py", "text": RUNTIME},
        {"path": "tests/conftest.py", "text": CONFTEST},
        {"path": "tests/test_cases.py", "text": _test_module(cases, names, summaries)},
    ]
    return {"files": files, "map": names, "summaries": summaries}


def merge_edits(prev_files: list[dict], edited_files: list[dict], fresh_files: list[dict]) -> dict:
    """人の編集を残し、生成し直した版との差分は提案に回す。"""
    prev = {f["path"]: f["text"] for f in prev_files}
    edited = {f["path"]: f["text"] for f in edited_files}
    fresh = {f["path"]: f["text"] for f in fresh_files}
    files, proposals = [], []
    for path in sorted(set(prev) | set(edited) | set(fresh)):
        mine, new, old = edited.get(path, prev.get(path)), fresh.get(path), prev.get(path)
        if mine is not None and mine != old:
            files.append({"path": path, "text": mine})
            if new is not None and new != old:
                proposals.append({"path": path, "text": new,
                                  "reason": "人が直したファイルと、生成し直した版に差分があります。採用するか確認してください。"})
        elif new is not None or mine is not None:
            files.append({"path": path, "text": new if new is not None else mine})
    return {"files": files, "proposals": proposals}
