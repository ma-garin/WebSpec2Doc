"""段階 6: ケース表から pytest コードを生成する（テンプレート方式・LLM 不使用）。

生成物は 3 つ。``bt_runtime.py``（接続・前後スナップショット・差分・results.jsonl・ケース単位の
タイムアウト）、``tests/conftest.py``、``tests/test_cases.py``（ケース 1 行 = テスト 1 件）。
接続情報は実行時に環境変数 ``WS2D_BT_*`` から読み、パスワードはコードに書かない。
期待値が確定していないケースは skip にして「未判定」として残す（合格に数えない）。
"""
from __future__ import annotations

import pprint
import re
import shutil
from pathlib import Path

from web.services.backendtest.codegen_runtime import RUNTIME
from web.services.backendtest.store import StoreError

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
        # test_<ケース ID 小文字>_<slug>。runner は -k "test_<id>_" で選ぶので、ID の直後は必ず "_"
        # （C001 で C0010 を拾う部分一致の取り違えを防ぐ）
        cid = re.sub(r"\W+", "_", str(case["id"]), flags=re.ASCII).strip("_").lower() or "case"
        slug = re.sub(r"\W+", "_", str(case.get("title") or ""), flags=re.ASCII).strip("_").lower()[:40].strip("_")
        base = f"test_{cid}_{slug or 'case'}"
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
        if is_rerun(case):  # 冪等性: 2 回とも正常終了し、2 回目でデータが変わらないこと
            lines.append('assert result["rc"], "対象のジョブを起動できませんでした。対象の起動コマンドを設定してください"')
            lines.append('assert all(rc == 0 for rc in result["rc"]), "ジョブが正常終了しませんでした。終了コードを確認してください"')
        what = "2 回目の実行でデータが変わりました（冪等ではありません）" if is_rerun(case) else "変わってはいけないテーブルが変わりました"
        lines.append(f"assert bt.unexpected_changes(case) == {{}}, {what!r}")
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


def is_rerun(case: dict) -> bool:
    """冪等性（再実行）のケース。同じ手順を 2 回起動し、2 回目の差分 0 を確かめる。"""
    return case.get("check") == "rerun" or str(case.get("variant") or "") == "再実行"


def _targets(job: dict) -> tuple[list[str], list[str]]:
    """対象（ジョブ定義）の起動コマンドと出力テーブル。"""
    targets = [t for t in job.get("targets") or [] if isinstance(t, dict)]
    return ([str(t["command"]) for t in targets if t.get("command")],
            [str(o) for t in targets for o in t.get("outputs") or []])


def _case_literal(case: dict, commands: list[str], outputs: list[str]) -> dict:
    out = {k: case[k] for k in ("id", "title", "data", "expected") if k in case}
    oracle = dict(case.get("oracle") or {})
    hit = [t for t in oracle.get("tables") or [] if t in outputs]
    if hit and not oracle.get("table"):
        oracle["table"] = hit[0]  # 別経路・ゴールデンは出力テーブルの実行後と比べる
    return {**out, "steps_ja": list(case.get("steps") or []), "rerun": is_rerun(case),
            "steps": [{"command": c} for c in commands], "oracle": oracle}


def _test_module(cases: list[dict], names: dict[str, str], summaries: dict[str, str],
                 targets: tuple[list[str], list[str]] = ([], [])) -> str:
    literal = {str(c["id"]): _case_literal(c, *targets) for c in cases}
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
        lines = _assert_lines(case)
        run = [] if lines[0].startswith("pytest.skip") else ["    result = bt.run(case)"]  # 未確定はジョブを起動しない
        out += ["", "", f"@pytest.mark.bt_case({cid!r})", f"def {names[cid]}(bt):",
                f'    """{_doc(summaries[cid])}"""', f"    case = CASES[{cid!r}]", *run]
        out += ["    " + line for line in lines]
    return "\n".join(out) + "\n"


def generate(job: dict) -> dict:
    """job（cases・targets・facts を持つ dict）から生成物を返す。入力は変更しない。"""
    cases = [c for c in (job.get("cases") or []) if isinstance(c, dict) and c.get("id")]
    names = _test_names(cases)
    summaries = {str(c["id"]): summarize(c) for c in cases}
    files = [
        {"path": "bt_runtime.py", "text": RUNTIME},
        {"path": "tests/conftest.py", "text": CONFTEST},
        {"path": "tests/test_cases.py", "text": _test_module(cases, names, summaries, _targets(job))},
    ]
    return {"files": files, "map": names, "summaries": summaries}


def write_files(files: list[dict], dest: Path) -> int:
    """生成物を案件の code/ に書き出す（実行と code.zip の元）。前の版は置き換える。"""
    root = Path(dest).resolve()
    paths = [(root / str(f.get("path") or "")).resolve() for f in files]
    if not files or any(root not in p.parents for p in paths):
        raise StoreError("テストコードが無いか、置き場所が正しくありません。段階 6 でテストコードを生成し直してください。")
    if root.is_dir():
        shutil.rmtree(root)
    for path, f in zip(paths, files):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(f.get("text") or ""), encoding="utf-8")
    return len(files)


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
