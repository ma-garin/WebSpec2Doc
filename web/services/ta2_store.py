"""テスト自動化（System 02 / TA2）の永続化と導出ロジック。

ルートはこのモジュールを呼ぶだけで、ロジックを持たない（契約 §1）。

    output/<domain>/ta2/tests.json   テスト定義（契約 §2）
    output/<domain>/ta2/drift.json   変更の対応状態（applied / dismissed）

保存はテナントスコープ（`scoped_output_dir`）配下。書き込みは tmp + replace の
アトミック更新で、途中終了しても壊れた JSON を残さない。

内部は不変スタイル。受け取った dict は書き換えず、常に新しい dict を返す。
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from web.tenancy import scoped_output_dir

VERSION = 1
HISTORY_LIMIT = 10
RUNS_LIMIT = 30
MAX_WAIT_MS = 60_000
DEFAULT_WAIT_MS = 5_000

# 契約 §2 の action 語彙。これ以外を作らない。
ACT_OPEN = "開く"
ACT_FILL = "入力する"
ACT_CLEAR = "入力欄を空のままにする"
ACT_CLICK = "押す"
ACT_SELECT = "選ぶ"
ACT_SHOWN = "表示される"
ACT_CONTAINS = "含む"
ACT_DISABLED = "無効になっている"
ACT_URL = "URL が"

ACTION_VOCABULARY: frozenset[str] = frozenset(
    {
        ACT_OPEN,
        ACT_FILL,
        ACT_CLEAR,
        ACT_CLICK,
        ACT_SELECT,
        ACT_SHOWN,
        ACT_CONTAINS,
        ACT_DISABLED,
        ACT_URL,
    }
)

ALERT_LOCATOR = '[role="alert"]'
NO_BASELINE_REASON = "比較の基準となる前回のクロールがありません"

_PAGE_ID_RE = re.compile(r"\bP\d{3,}\b")
_SNAPSHOT_STAMP_RE = re.compile(r"^(\d{8})-(\d{6})")


class Ta2StoreError(ValueError):
    """入力が不正で操作を適用できない場合に送出する（ルートは 4xx に写像する）。"""


# =========================================================================
# パスと入出力
# =========================================================================
def _root() -> Path:
    """出力ルート。テナントがあれば output/tenants/<slug>。

    既存テストが `web.routes.qa_process.OUTPUT_DIR` を monkeypatch する運用に
    合わせ、そのモジュール属性を優先して解決する（web.services.qa.helpers と同じ）。
    """
    import web.config as config

    route_mod = sys.modules.get("web.routes.qa_process")
    value = getattr(route_mod, "OUTPUT_DIR", None)
    if value is None:
        value = config.OUTPUT_DIR
    base = value if isinstance(value, Path) else Path(value)
    return scoped_output_dir(base)


def base_dir(domain: str) -> Path:
    return _root() / domain / "ta2"


def tests_path(domain: str) -> Path:
    return base_dir(domain) / "tests.json"


def drift_path(domain: str) -> Path:
    return base_dir(domain) / "drift.json"


def report_path(domain: str) -> Path:
    return _root() / domain / "report.json"


def snapshots_dir(domain: str) -> Path:
    return _root() / domain / "snapshots"


def run_dir(domain: str) -> Path:
    """spec.ts と実行証跡の置き場。"""
    return base_dir(domain) / "runs"


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_report(domain: str) -> dict[str, Any]:
    """report.json。無ければ空 dict（呼び出し側で「基準なし」と扱う）。"""
    data = _read_json(report_path(domain))
    return data if isinstance(data, dict) else {}


# =========================================================================
# ロケータの安定度（契約 §2 stab）
# =========================================================================
def locator_stability(locator: str | None) -> str:
    """high = data-testid / #id / [role] ・ mid = [name] / text= ・ それ以外 low。"""
    loc = str(locator or "").strip()
    if not loc:
        return "low"
    if "data-testid" in loc or "[role=" in loc or loc.startswith("#"):
        return "high"
    if "[name=" in loc or loc.startswith("text=") or loc.startswith("page."):
        return "mid"
    return "low"


# =========================================================================
# 読み書き（契約 §8: load / save）
# =========================================================================
def _empty(domain: str) -> dict[str, Any]:
    return {"version": VERSION, "domain": domain, "next_seq": 1, "tests": []}


def _normalize(domain: str, data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return _empty(domain)
    tests = [dict(t) for t in (data.get("tests") or []) if isinstance(t, dict)]
    try:
        next_seq = int(data.get("next_seq") or 1)
    except (TypeError, ValueError):
        next_seq = 1
    return {
        "version": int(data.get("version") or VERSION),
        "domain": str(data.get("domain") or domain),
        "next_seq": max(next_seq, 1),
        "tests": tests,
    }


def load(domain: str) -> dict[str, Any]:
    """tests.json を読む。ファイルが無ければ空 dict（呼び出し側が導出を判断する）。"""
    data = _read_json(tests_path(domain))
    if data is None:
        return {}
    return _normalize(domain, data)


def save(domain: str, data: Mapping[str, Any]) -> dict[str, Any]:
    """tests.json を保存し、正規化後のデータを返す。"""
    payload = _normalize(domain, data)
    _write_json(tests_path(domain), payload)
    return payload


def _loaded(domain: str) -> dict[str, Any]:
    """内部用: 無ければ空の骨組みを返す（load は {} を返すので使い分ける）。"""
    data = load(domain)
    return data if data else _empty(domain)


def _find(data: Mapping[str, Any], test_id: str) -> dict[str, Any]:
    for test in data.get("tests") or []:
        if str(test.get("id")) == str(test_id):
            return dict(test)
    raise Ta2StoreError(f"テストが見つかりません: {test_id}")


def _replace(data: Mapping[str, Any], test: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(data)
    out["tests"] = [
        dict(test) if str(t.get("id")) == str(test.get("id")) else dict(t)
        for t in data.get("tests") or []
    ]
    return out


def _next_id(data: dict[str, Any]) -> str:
    used = {str(t.get("id")) for t in data.get("tests") or []}
    seq = int(data.get("next_seq") or 1)
    while f"PW-{seq:04d}" in used:
        seq += 1
    data["next_seq"] = seq + 1
    return f"PW-{seq:04d}"


# =========================================================================
# 画面と要素辞書（契約 §2.2）
# =========================================================================
def _screen_name(screen: Mapping[str, Any]) -> str:
    title = str(screen.get("title") or "")
    return title.split("|")[0].strip() or str(screen.get("page_id") or "")


def _url_path(url: str) -> str:
    path = re.sub(r"^https?://[^/]*", "", str(url or ""))
    return path or "/"


def screens_of(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """画面一覧 `[{id, name, path, url}]`。"""
    out: list[dict[str, Any]] = []
    for screen in report.get("screens") or []:
        if not isinstance(screen, Mapping):
            continue
        out.append(
            {
                "id": str(screen.get("page_id") or ""),
                "name": _screen_name(screen),
                "path": _url_path(str(screen.get("url") or "")),
                "url": str(screen.get("url") or ""),
            }
        )
    return out


def _field_key(field: Mapping[str, Any]) -> str:
    return str(field.get("name") or field.get("element_id") or "")


def _field_locator(field: Mapping[str, Any]) -> str:
    locators = [str(x) for x in (field.get("locators") or []) if str(x).strip()]
    if locators:
        return locators[0]
    element_id = str(field.get("element_id") or "")
    if element_id:
        return f"#{element_id}"
    name = str(field.get("name") or "")
    return f'[name="{name}"]' if name else ""


_LABEL_KEYS = ("label", "label_text", "aria_label", "title", "text")


def _field_label(field: Mapping[str, Any]) -> str:
    """項目名。明示ラベル → name → element_id の順。placeholder は名前に使わない。"""
    for key in _LABEL_KEYS:
        value = str(field.get(key) or "").strip()
        if value:
            return value
    name = str(field.get("name") or "").strip()
    if name:
        return name
    return str(field.get("element_id") or "").strip()


def _element(
    key: str, label: str, kind: str, locator: str, placeholder: str = ""
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "type": kind,
        "loc": locator,
        "stab": locator_stability(locator),
        "placeholder": placeholder,
    }


def elements_of(report: Mapping[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    """`{page_id: {key: {key,label,type,loc,stab}}}`。alert は常に含める。"""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for screen in report.get("screens") or []:
        if not isinstance(screen, Mapping):
            continue
        page_id = str(screen.get("page_id") or "")
        elements: dict[str, dict[str, Any]] = {}
        for form in screen.get("forms") or []:
            for field in form.get("fields") or []:
                key = _field_key(field)
                if not key:
                    continue
                elements[key] = _element(
                    key,
                    _field_label(field) or key,
                    str(field.get("field_type") or "text"),
                    _field_locator(field),
                    str(field.get("placeholder") or "").strip(),
                )
        for index, button in enumerate(screen.get("buttons") or []):
            label = str(button).strip()
            if not label:
                continue
            elements[f"btn_{index}"] = _element(f"btn_{index}", label, "button", f"text={label}")
        headings = [str(h).strip() for h in (screen.get("headings") or []) if str(h).strip()]
        if headings:
            elements["hero"] = _element("hero", headings[0], "heading", "h1")
        elements["alert"] = _element("alert", "エラー表示", "alert", ALERT_LOCATOR)
        out[page_id] = elements
    return out


def _screen_by_id(report: Mapping[str, Any], page_id: str) -> dict[str, Any]:
    for screen in report.get("screens") or []:
        if str(screen.get("page_id") or "") == str(page_id):
            return dict(screen)
    return {}


def _submit_label(screen: Mapping[str, Any]) -> str:
    buttons = [str(b).strip() for b in (screen.get("buttons") or []) if str(b).strip()]
    return buttons[0] if buttons else "送信"


# =========================================================================
# テストケース表の行 ⇄ steps（契約 §2.1 と §3.1 は互いの逆）
# =========================================================================
def _step(kind: str, action: str, **rest: Any) -> dict[str, Any]:
    step: dict[str, Any] = {"kind": kind, "action": action}
    step.update({k: v for k, v in rest.items() if v is not None})
    step.setdefault("target", "")
    step.setdefault("arg", "")
    step.setdefault("loc", "")
    if kind != "pre":
        step["stab"] = locator_stability(step.get("loc"))
    return step


def _action_to_step(action: Mapping[str, Any]) -> dict[str, Any] | None:
    """テストケース表の action → step。未対応（wait_load 等）は None。"""
    kind = str(action.get("type") or "")
    locator = str(action.get("locator") or "")
    field = str(action.get("field") or "")
    if kind == "goto":
        return _step(
            "pre",
            ACT_OPEN,
            target="page",
            arg=str(action.get("url") or ""),
            loc="page.goto",
            op="goto",
        )
    if kind == "fill":
        return _step(
            "act",
            ACT_FILL,
            target=field or locator,
            arg=str(action.get("value") or ""),
            loc=locator,
            op="fill",
        )
    if kind == "clear":
        return _step("act", ACT_CLEAR, target=field or locator, arg=field, loc=locator, op="clear")
    if kind == "select":
        return _step(
            "act",
            ACT_SELECT,
            target=field or locator,
            arg=str(action.get("value") or ""),
            loc=locator,
            op="select",
        )
    if kind == "click_text":
        text = str(action.get("text") or "")
        return _step(
            "act", ACT_CLICK, target="submit", arg=text, loc=f"text={text}", op="click_text"
        )
    if kind == "click_link_to":
        title = str(action.get("title") or "")
        return _step(
            "act",
            ACT_CLICK,
            target="link",
            arg=title,
            loc=f"text={title}",
            op="click_link_to",
            href=str(action.get("url") or ""),
        )
    return None


def _assertion_to_step(assertion: Mapping[str, Any]) -> dict[str, Any] | None:
    kind = str(assertion.get("type") or "")
    value = str(assertion.get("value") or "")
    stage = assertion.get("stage")
    common: dict[str, Any] = {"check": kind}
    if stage:
        common["stage"] = str(stage)
    if kind == "expect_title":
        return _step("ver", ACT_CONTAINS, target="title", arg=value, loc="title", **common)
    if kind == "expect_text":
        return _step("ver", ACT_SHOWN, target="text", arg=value, loc=f"text={value}", **common)
    if kind == "expect_url":
        return _step("ver", ACT_URL, target="url", arg=value, loc="page.url", **common)
    if kind == "expect_no_error":
        return _step(
            "ver", ACT_SHOWN, target="alert", arg="エラー表示なし", loc=ALERT_LOCATOR, **common
        )
    if kind == "expect_stay":
        return _step(
            "ver",
            ACT_URL,
            target="url",
            arg=str(assertion.get("url") or ""),
            loc="page.url",
            **common,
        )
    if kind == "expect_no_server_error":
        return _step("ver", ACT_SHOWN, target="page", arg="サーバエラーなし", loc="body", **common)
    if kind == "expect_value_length":
        locator = str(assertion.get("locator") or "")
        return _step(
            "ver",
            ACT_DISABLED,
            target=locator,
            arg=f"{assertion.get('max')}文字まで",
            loc=locator,
            max=int(assertion.get("max") or 0),
            **common,
        )
    return None


def _step_to_action(step: Mapping[str, Any]) -> dict[str, Any] | None:
    op = str(step.get("op") or "")
    action = str(step.get("action") or "")
    locator = str(step.get("loc") or "")
    if op == "goto" or action == ACT_OPEN:
        return {"type": "goto", "url": str(step.get("arg") or "")}
    if op == "fill" or action == ACT_FILL:
        return {
            "type": "fill",
            "locator": locator,
            "value": str(step.get("arg") or ""),
            "field": str(step.get("target") or ""),
        }
    if op == "clear" or action == ACT_CLEAR:
        return {"type": "clear", "locator": locator, "field": str(step.get("target") or "")}
    if op == "select" or action == ACT_SELECT:
        return {
            "type": "select",
            "locator": locator,
            "value": str(step.get("arg") or ""),
            "field": str(step.get("target") or ""),
        }
    if op in {"click", "click_text", "click_link_to"} or action == ACT_CLICK:
        arg = str(step.get("arg") or "")
        # 編集されたロケータは必ず実行に使う。既定（text=<ラベル>）のままのときだけ
        # 従来どおりラベル一致・リンク先一致で探す。
        if locator and locator != f"text={arg}":
            return {"type": "click", "locator": locator, "text": arg}
        if op == "click_link_to":
            return {"type": "click_link_to", "url": str(step.get("href") or ""), "title": arg}
        return {"type": "click_text", "text": arg}
    return None


def _step_to_assertion(step: Mapping[str, Any]) -> dict[str, Any] | None:
    check = str(step.get("check") or "")
    action = str(step.get("action") or "")
    arg = str(step.get("arg") or "")
    out: dict[str, Any]
    if check == "expect_stay" or (not check and action == ACT_URL and step.get("stay")):
        out = {"type": "expect_stay", "url": arg}
    elif check == "expect_no_error":
        out = {"type": "expect_no_error"}
    elif check == "expect_no_server_error":
        out = {"type": "expect_no_server_error"}
    elif check == "expect_value_length":
        out = {
            "type": "expect_value_length",
            "locator": str(step.get("loc") or ""),
            "max": int(step.get("max") or 0),
        }
    elif check == "expect_title" or action == ACT_CONTAINS:
        out = {"type": "expect_title", "value": arg}
    elif check == "expect_url" or action == ACT_URL:
        out = {"type": "expect_url", "value": arg}
    elif check == "expect_text" or action == ACT_SHOWN:
        out = {"type": "expect_text", "value": arg}
    else:
        return None
    if step.get("stage"):
        out["stage"] = str(step.get("stage"))
    return out


def steps_from_row(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    """テストケース表の 1 行 → steps（契約 §2.1）。"""
    steps: list[dict[str, Any]] = []
    for action in row.get("actions") or []:
        step = _action_to_step(action)
        if step is not None:
            steps.append(step)
    for assertion in row.get("assertions") or []:
        step = _assertion_to_step(assertion)
        if step is not None:
            steps.append(step)
    return steps


IMPLICIT_ASSERTION = {"type": "expect_no_error"}
IMPLICIT_ASSERTION_LABEL = "ページにエラーが表示されていない"
NO_ACTION_REASON = "実行できる操作手順がありません（『開く』などの操作を追加してください）"


def to_table_rows(
    tests: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """steps → `generate_spec()` が受ける行 と 実行できないテストの一覧。

    戻り値は `(rows, skipped)`。`skipped` は `{"id","name","reason"}` で、
    **実行対象から外れたテストを黙って捨てない**（除外理由を必ず返す）。

    検証手順が 1 つも無いテストは、暗黙の検証（`ページにエラーが表示されていない`）を
    補って実行可能にする。操作手順が無いものだけが `skipped` に入る。

    `case_id` にはテスト ID（PW-xxxx）を入れる。実行結果はテスト単位で戻るため、
    由来のテストケース ID ではなくテスト ID で対応付ける必要がある。
    """
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for test in tests:
        actions: list[dict[str, Any]] = []
        assertions: list[dict[str, Any]] = []
        for step in test.get("steps") or []:
            if str(step.get("kind")) == "ver":
                assertion = _step_to_assertion(step)
                if assertion is not None:
                    assertions.append(assertion)
                continue
            action = _step_to_action(step)
            if action is not None:
                actions.append(action)
        if not actions:
            skipped.append(
                {
                    "id": str(test.get("id") or ""),
                    "name": str(test.get("name") or ""),
                    "reason": NO_ACTION_REASON,
                }
            )
            continue
        implicit = not assertions
        if implicit:
            assertions = [dict(IMPLICIT_ASSERTION)]
        rows.append(
            {
                "case_id": str(test.get("id") or ""),
                "name": str(test.get("name") or ""),
                "automation": "自動化可",
                "actions": actions,
                "assertions": assertions,
                "implicit_assertion": implicit,
                "source_case_id": str(test.get("case_id") or ""),
                "screen": str(test.get("screen") or ""),
            }
        )
    return rows, skipped


def table_rows_only(tests: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """`to_table_rows` の行だけが欲しい呼び出し向けの後方互換ヘルパ。"""
    return to_table_rows(tests)[0]


# =========================================================================
# 初期導出（契約 §2.1）
# =========================================================================
def _page_id_of_row(row: Mapping[str, Any], report: Mapping[str, Any]) -> str:
    """表の `screen` 列（"P004 お支払い"）から page_id を取り出す。"""
    raw = str(row.get("screen") or "")
    match = _PAGE_ID_RE.search(raw)
    if match:
        return match.group(0)
    for screen in report.get("screens") or []:
        if _screen_name(screen) and _screen_name(screen) in raw:
            return str(screen.get("page_id") or "")
    return ""


def _technique_of_row(row: Mapping[str, Any]) -> str:
    viewpoint = str(row.get("viewpoint") or "").strip()
    if not viewpoint:
        return "生成"
    return viewpoint.split("／")[0].split("（")[0].strip() or "生成"


_STATUS_BY_RESULT = {
    "PASS": "pass",
    "FAIL": "fail",
    "TIMEOUT": "fail",
    "SKIP": "new",
}


def derive_initial(domain: str, report: Mapping[str, Any]) -> dict[str, Any]:
    """テストケース表からテスト定義を導出して保存する（tests.json が無いとき）。"""
    from web.services.testcase_table_store import compose, load_run_result

    rows = compose(domain, report).get("rows") or []
    run_cases = (load_run_result(domain) or {}).get("cases") or {}
    ran_at = (load_run_result(domain) or {}).get("ran_at") or ""

    data = _empty(domain)
    tests: list[dict[str, Any]] = []
    for row in rows:
        test_id = _next_id(data)
        case_id = str(row.get("case_id") or "")
        status = "new"
        history: list[int] = []
        last: dict[str, Any] = {}
        entry = run_cases.get(case_id)
        if isinstance(entry, Mapping):
            status = _run_status(str(entry.get("status") or ""))
            history = [_history_mark(status)] if status in {"pass", "fail", "flaky"} else []
            last = {
                "dur_ms": int(entry.get("duration_ms") or 0),
                "at": ran_at,
                "step": None,
                "run_id": "",
                "error": str(entry.get("error") or ""),
            }
        elif str(row.get("result") or "") in _STATUS_BY_RESULT:
            status = _STATUS_BY_RESULT[str(row.get("result"))]
        tests.append(
            {
                "id": test_id,
                "case_id": case_id,
                "screen": _page_id_of_row(row, report),
                "name": str(row.get("name") or ""),
                "technique": _technique_of_row(row),
                "source": "table",
                "steps": steps_from_row(row),
                "status": status,
                "history": history,
                "last": last,
                "updated_at": _now(),
            }
        )
    data["tests"] = tests
    return save(domain, data)


# =========================================================================
# 実行結果の反映（契約 §3.1）
# =========================================================================
def _run_status(raw: str) -> str:
    value = str(raw or "").lower()
    if value in {"passed", "pass", "ok"}:
        return "pass"
    if value in {"flaky", "unstable"}:
        return "flaky"
    if value in {"failed", "fail", "timedout", "timeout", "interrupted"}:
        return "fail"
    if value in {"skipped", "skip"}:
        return "new"
    return "fail"


def _history_mark(status: str) -> int:
    return {"pass": 1, "flaky": 2}.get(status, 0)


def _cases_of(result: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """`{cases:{}}` 形式と Playwright の生結果（`tests:[]`）の両方を受ける。"""
    cases = result.get("cases")
    if isinstance(cases, Mapping):
        return {str(k): dict(v) for k, v in cases.items() if isinstance(v, Mapping)}
    out: dict[str, dict[str, Any]] = {}
    for test in result.get("tests") or []:
        title = str(test.get("title") or "")
        key = title.split(" ", 1)[0]
        if not key:
            continue
        out[key] = {
            "status": str(test.get("status") or ""),
            "duration_ms": int(test.get("duration_ms") or 0),
            "error": str(test.get("error") or ""),
        }
    return out


_GENERIC_LOCS = {"page.goto", "page.url", "title", "body"}


def _failed_step_index(steps: Sequence[Mapping[str, Any]], error: str) -> int | None:
    """error 文中のロケータ・ラベルと steps[] の一致で失敗ステップを特定する。"""
    if not error:
        return None
    for index, step in enumerate(steps):
        loc = str(step.get("loc") or "")
        if loc and loc not in _GENERIC_LOCS and loc in error:
            return index
    # ラベル一致で探すクリック（getByText('…') / name: '…'）は loc が error に出ない
    for index, step in enumerate(steps):
        if str(step.get("kind")) == "pre":
            continue
        arg = str(step.get("arg") or "").strip()
        if len(arg) >= 2 and (f"'{arg}'" in error or f'"{arg}"' in error):
            return index
    return None


# 「要素が見つからない」と読み取れる印。ラベル一致で探す操作は locator 文言が出ない。
_ELEMENT_MARKERS = ("locator", "getBy", "waiting for element")

_EXPECT_RE = re.compile(r"Expected[^\n]*?[:\s]+(.+?)\n.*?Received[^\n]*?[:\s]+(.+?)\n", re.S)


def _issue_for(
    step: Mapping[str, Any], error: str, elements: Mapping[str, Any]
) -> dict[str, Any] | None:
    """失敗内容から issue を作る。判定できないものは None（捏造しない）。"""
    if "Timeout" in error and any(marker in error for marker in _ELEMENT_MARKERS):
        label = str(step.get("arg") or "")
        fix = None
        for element in elements.values():
            if str(element.get("label") or "") == label and str(element.get("loc")) != str(
                step.get("loc")
            ):
                fix = str(element.get("loc"))
                break
        return {
            "type": "missing",
            "msg": "要素が見つからない",
            "detail": error[:500],
            "fix": fix,
            "fix_stab": locator_stability(fix) if fix else None,
            "key": str(step.get("target") or ""),
        }
    match = _EXPECT_RE.search(error)
    if match:
        return {
            "type": "expect",
            "msg": "期待値が一致しない",
            "detail": error[:500],
            "fix": match.group(2).strip().strip('"'),
            "fix_stab": None,
            "key": str(step.get("target") or ""),
        }
    if "Timeout" in error:
        return {
            "type": "timeout",
            "msg": "待機時間内に完了しない",
            "detail": error[:500],
            "fix": None,
            "fix_stab": None,
            "key": str(step.get("target") or ""),
        }
    return None


def apply_run_result(
    domain: str, result: Mapping[str, Any], run_id: str = "", at: str = ""
) -> dict[str, Any]:
    """実行結果を tests.json の status / history / last / issue に反映する。"""
    data = _loaded(domain)
    cases = _cases_of(result)
    if not cases:
        return data
    ran_at = at or _now()
    elements = elements_of(load_report(domain))

    tests: list[dict[str, Any]] = []
    for raw in data.get("tests") or []:
        test = dict(raw)
        entry = cases.get(str(test.get("id"))) or cases.get(str(test.get("case_id") or ""))
        if not isinstance(entry, Mapping):
            tests.append(test)
            continue
        status = _run_status(str(entry.get("status") or ""))
        error = str(entry.get("error") or "")
        steps = [dict(s) for s in test.get("steps") or []]
        failed_index = _failed_step_index(steps, error) if status == "fail" else None
        issue_index: int | None = None
        if status == "fail":
            screen_elements = elements.get(str(test.get("screen") or "")) or {}
            target_index = failed_index if failed_index is not None else _first_act_index(steps)
            if target_index is not None:
                issue = _issue_for(steps[target_index], error, screen_elements)
                if issue is not None:
                    steps[target_index] = {**steps[target_index], "issue": issue, "fixed": False}
                    issue_index = target_index
        else:
            steps = [_without_issue(s) for s in steps]
        history = [int(x) for x in (test.get("history") or []) if isinstance(x, int)]
        history = (history + [_history_mark(status)])[-HISTORY_LIMIT:]
        test.update(
            {
                "steps": steps,
                "status": status,
                "history": history,
                "last": {
                    "dur_ms": int(entry.get("duration_ms") or 0),
                    "at": ran_at,
                    "step": failed_index if failed_index is not None else issue_index,
                    "run_id": str(run_id or ""),
                    "error": error[:2000],
                },
                "updated_at": _now(),
            }
        )
        tests.append(test)
    return save(domain, {**data, "tests": tests})


def _first_act_index(steps: Sequence[Mapping[str, Any]]) -> int | None:
    for index, step in enumerate(steps):
        if str(step.get("kind")) == "act":
            return index
    return 0 if steps else None


def _without_issue(step: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(step)
    out.pop("issue", None)
    out.pop("fixed", None)
    return out


# =========================================================================
# 修正の適用（契約 §2 issue.type）
# =========================================================================
NO_ISSUE_REASON = "このステップには修正できる問題がありません"
NO_FIX_MISSING_REASON = "修正案がありません（要素辞書に同じラベルの要素が見つかりません）"
NO_FIX_EXPECT_REASON = "修正案がありません（期待値を判定できませんでした）"


def apply_fix(
    domain: str, test_id: str, step_index: int
) -> tuple[dict[str, Any], str | None]:
    """issue.type に応じて loc / arg / wait_ms を書き換える。

    戻り値は `(test, reason)`。修正案が無い等で**適用しなかった場合も例外にせず**、
    変更していないテストと日本語の理由を返す（修正案なしは正常系。契約 §3.1）。
    `Ta2StoreError` は不正な ID / ステップ番号のときだけ送出する。
    """
    data = _loaded(domain)
    test = _find(data, test_id)
    steps = [dict(s) for s in test.get("steps") or []]
    try:
        index = int(step_index)
        if index < 0:
            raise IndexError(index)
        step = dict(steps[index])
    except (TypeError, ValueError, IndexError) as exc:
        raise Ta2StoreError(f"ステップが見つかりません: {step_index}") from exc

    issue = step.get("issue")
    if not isinstance(issue, Mapping):
        return test, NO_ISSUE_REASON

    kind = str(issue.get("type") or "")
    if kind not in {"missing", "timeout", "expect", "flaky"}:
        return test, f"未知の問題の種類です: {kind or '不明'}"

    fix = issue.get("fix")
    changed = False
    if kind in {"missing", "flaky"} and fix:
        step["loc"] = str(fix)
        step["stab"] = str(issue.get("fix_stab") or locator_stability(str(fix)))
        changed = True
    if kind == "missing" and not fix:
        return test, NO_FIX_MISSING_REASON
    if kind in {"timeout", "flaky"}:
        step["wait_ms"] = min(int(step.get("wait_ms") or DEFAULT_WAIT_MS) * 2, MAX_WAIT_MS)
        changed = True
    if kind == "expect":
        if fix is None:
            return test, NO_FIX_EXPECT_REASON
        step["arg"] = str(fix)
        changed = True
    if not changed:
        return test, "適用できる修正がありません"

    step["fixed"] = True
    steps[index] = step
    updated = {**test, "steps": steps, "status": "fixed", "updated_at": _now()}
    save(domain, _replace(data, updated))
    return updated, None


# =========================================================================
# 穴（gaps）と生成（契約 §4）
# =========================================================================
def _covered_targets(tests: Sequence[Mapping[str, Any]], page_id: str) -> set[str]:
    covered: set[str] = set()
    for test in tests:
        if str(test.get("screen") or "") != str(page_id):
            continue
        for step in test.get("steps") or []:
            target = str(step.get("target") or "").strip()
            if target:
                covered.add(target)
            loc = str(step.get("loc") or "").strip()
            if loc:
                covered.add(loc)
    return covered


def condition_mode(condition: str) -> str:
    """テスト条件の種別。未入力・未選択を確かめる条件か、値を入れる条件か。"""
    text = str(condition or "")
    if "未入力" in text or "未選択" in text or "空" in text:
        return "empty"
    return "value"


_MODE_BY_ACTION = {ACT_CLEAR: "empty", ACT_FILL: "value", ACT_SELECT: "value"}


def _covered_field_modes(
    tests: Sequence[Mapping[str, Any]], page_id: str
) -> set[tuple[str, str]]:
    """`(項目の識別子, mode)`。項目単位ではなく**条件の種別まで**見て網羅を数える。"""
    covered: set[tuple[str, str]] = set()
    for test in tests:
        if str(test.get("screen") or "") != str(page_id):
            continue
        for step in test.get("steps") or []:
            mode = _MODE_BY_ACTION.get(str(step.get("action") or ""))
            if mode is None:
                continue
            for ident in (str(step.get("target") or ""), str(step.get("loc") or "")):
                if ident.strip():
                    covered.add((ident.strip(), mode))
    return covered


def _covered_buttons(tests: Sequence[Mapping[str, Any]], page_id: str) -> set[str]:
    """その画面で「押す」対象になっているラベル・ロケータ。"""
    covered: set[str] = set()
    for test in tests:
        if str(test.get("screen") or "") != str(page_id):
            continue
        for step in test.get("steps") or []:
            if str(step.get("action") or "") != ACT_CLICK:
                continue
            for ident in (str(step.get("arg") or ""), str(step.get("loc") or "")):
                if ident.strip():
                    covered.add(ident.strip())
    return covered


def _button_gap_steps(screen: Mapping[str, Any], label: str) -> list[dict[str, Any]]:
    """開く → 押す → エラー表示なし（契約 §4 の生成ステップに合わせる）。"""
    return [
        _step(
            "pre",
            ACT_OPEN,
            target="page",
            arg=str(screen.get("url") or ""),
            loc="page.goto",
            op="goto",
        ),
        _step("act", ACT_CLICK, target="button", arg=label, loc=f"text={label}", op="click_text"),
        _step(
            "ver",
            ACT_SHOWN,
            target="alert",
            arg="エラー表示なし",
            loc=ALERT_LOCATOR,
            check="expect_no_error",
        ),
    ]


def _covered_urls(tests: Sequence[Mapping[str, Any]], page_id: str) -> set[str]:
    covered: set[str] = set()
    for test in tests:
        if str(test.get("screen") or "") != str(page_id):
            continue
        for step in test.get("steps") or []:
            if str(step.get("action")) == ACT_URL:
                covered.add(_url_path(str(step.get("arg") or "")))
    return covered


def _gap_steps(
    screen: Mapping[str, Any], field: Mapping[str, Any] | None, condition: str
) -> list[dict[str, Any]]:
    """開く → 入力/空のまま → 押す → 表示される（契約 §4）。"""
    url = str(screen.get("url") or "")
    label = _submit_label(screen)
    steps = [_step("pre", ACT_OPEN, target="page", arg=url, loc="page.goto", op="goto")]
    if field is not None:
        key = _field_key(field)
        locator = _field_locator(field)
        empty = "未入力" in condition or "空" in condition
        if empty:
            steps.append(_step("act", ACT_CLEAR, target=key, arg=key, loc=locator, op="clear"))
        else:
            value = _sample_value(field)
            steps.append(_step("act", ACT_FILL, target=key, arg=value, loc=locator, op="fill"))
    steps.append(
        _step("act", ACT_CLICK, target="submit", arg=label, loc=f"text={label}", op="click_text")
    )
    steps.append(
        _step(
            "ver",
            ACT_SHOWN,
            target="alert",
            arg="エラー表示なし",
            loc=ALERT_LOCATOR,
            check="expect_no_error",
        )
    )
    return steps


def _transition_gap_steps(
    screen: Mapping[str, Any], target_url: str, title: str
) -> list[dict[str, Any]]:
    return [
        _step(
            "pre",
            ACT_OPEN,
            target="page",
            arg=str(screen.get("url") or ""),
            loc="page.goto",
            op="goto",
        ),
        _step(
            "act",
            ACT_CLICK,
            target="link",
            arg=title,
            loc=f"text={title}",
            op="click_link_to",
            href=target_url,
        ),
        _step("ver", ACT_URL, target="url", arg=target_url, loc="page.url", check="expect_url"),
    ]


def _sample_value(field: Mapping[str, Any]) -> str:
    """具体値。既定値 → placeholder → 型ごとの固定値（曖昧語を使わない）。"""
    default = str(field.get("default") or "").strip()
    if default:
        return default
    options = [str(o) for o in (field.get("options") or []) if str(o).strip()]
    if options:
        return options[-1]
    placeholder = str(field.get("placeholder") or "").strip()
    kind = str(field.get("field_type") or "text")
    if kind == "email":
        return "user@example.com"
    if kind == "number":
        return str(field.get("min_value") or "1")
    if placeholder:
        return placeholder
    return "テスト入力"


def gaps_of(
    domain: str, report: Mapping[str, Any], tests: Sequence[Mapping[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """未カバーのテスト条件と遷移を列挙する（契約 §4）。"""
    if tests is None:
        tests = _loaded(domain).get("tests") or []
    screens = {str(s.get("page_id") or ""): dict(s) for s in report.get("screens") or []}
    gaps: list[dict[str, Any]] = []
    for page_id, screen in screens.items():
        covered_modes = _covered_field_modes(tests, page_id)
        for form in screen.get("forms") or []:
            for field in form.get("fields") or []:
                key = _field_key(field)
                if not key:
                    continue
                locator = _field_locator(field)
                label = _field_label(field) or key
                for index, condition in enumerate(field.get("test_conditions") or []):
                    mode = condition_mode(str(condition))
                    if (key, mode) in covered_modes or (locator, mode) in covered_modes:
                        continue
                    gaps.append(
                        {
                            "id": f"{page_id}:{key}:{index}",
                            "screen": page_id,
                            "field": key,
                            "kind": "condition",
                            "title": f"{label}: {condition}",
                            "detail": f"{_screen_name(screen)} の「{label}」に {condition} のテストがありません",
                            "steps": _gap_steps(screen, field, str(condition)),
                        }
                    )
        covered_buttons = _covered_buttons(tests, page_id)
        for index, button in enumerate(screen.get("buttons") or []):
            label = str(button).strip()
            if not label or label in covered_buttons or f"text={label}" in covered_buttons:
                continue
            gaps.append(
                {
                    "id": f"{page_id}:button:{index}",
                    "screen": page_id,
                    "field": f"btn_{index}",
                    "kind": "button",
                    "title": f"「{label}」を押す",
                    "detail": (
                        f"{_screen_name(screen)} の「{label}」を押すテストがありません"
                    ),
                    "steps": _button_gap_steps(screen, label),
                }
            )
        covered_urls = _covered_urls(tests, page_id)
        for index, target_id in enumerate((screen.get("transitions") or {}).get("to") or []):
            target = screens.get(str(target_id)) or {}
            target_url = str(target.get("url") or "")
            if not target_url or _url_path(target_url) in covered_urls:
                continue
            title = _screen_name(target) or str(target_id)
            gaps.append(
                {
                    "id": f"{page_id}:transition:{index}",
                    "screen": page_id,
                    "field": "transition",
                    "kind": "transition",
                    "title": f"{title} への遷移",
                    "detail": (
                        f"{_screen_name(screen)} から {title}"
                        f"（{_url_path(target_url)}）への遷移を確かめるテストがありません"
                    ),
                    "steps": _transition_gap_steps(screen, target_url, title),
                }
            )
    return gaps


def generate_from_gaps(
    domain: str,
    report: Mapping[str, Any],
    screen: str = "",
    gap_ids: Sequence[str] | None = None,
    name: str = "",
) -> list[dict[str, Any]]:
    """gap からテストを生成する。gap_ids が無ければ `開く` 1 ステップの手動テスト。"""
    data = _loaded(domain)
    created: list[dict[str, Any]] = []

    if gap_ids:
        by_id = {g["id"]: g for g in gaps_of(domain, report, data.get("tests") or [])}
        missing = [gid for gid in gap_ids if gid not in by_id]
        if missing:
            raise Ta2StoreError(f"指定された穴が見つかりません: {', '.join(missing)}")
        for gap_id in gap_ids:
            gap = by_id[gap_id]
            created.append(
                {
                    "id": _next_id(data),
                    "case_id": "",
                    "screen": str(gap.get("screen") or screen),
                    "name": str(gap.get("title") or ""),
                    "technique": "生成",
                    "source": "gap",
                    "steps": [dict(s) for s in gap.get("steps") or []],
                    "status": "new",
                    "history": [],
                    "last": {},
                    "gap_id": gap_id,
                    "updated_at": _now(),
                }
            )
    else:
        if not str(name or "").strip():
            raise Ta2StoreError("テスト名を入力してください")
        target = _screen_by_id(report, screen)
        url = str(target.get("url") or "")
        created.append(
            {
                "id": _next_id(data),
                "case_id": "",
                "screen": str(screen or ""),
                "name": str(name).strip(),
                "technique": "手動",
                "source": "manual",
                "steps": [
                    _step("pre", ACT_OPEN, target="page", arg=url, loc="page.goto", op="goto")
                ],
                "status": "new",
                "history": [],
                "last": {},
                "updated_at": _now(),
            }
        )

    data["tests"] = [dict(t) for t in data.get("tests") or []] + created
    save(domain, data)
    return created


# =========================================================================
# 変更検知（契約 §3 drift）
# =========================================================================
def _load_drift_state(domain: str) -> dict[str, str]:
    data = _read_json(drift_path(domain))
    if not isinstance(data, dict):
        return {}
    items = data.get("items")
    if isinstance(items, dict):
        return {str(k): str(v) for k, v in items.items()}
    return {}


def _save_drift_state(domain: str, state: Mapping[str, str]) -> None:
    _write_json(drift_path(domain), {"version": VERSION, "items": dict(state)})


def _snapshot_paths(domain: str) -> list[Path]:
    directory = snapshots_dir(domain)
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.json") if p.is_file())


def _snapshot_at(path: Path) -> str:
    match = _SNAPSHOT_STAMP_RE.match(path.stem)
    if not match:
        return ""
    day, clock = match.groups()
    return f"{day[:4]}-{day[4:6]}-{day[6:]}T{clock[:2]}:{clock[2:4]}:{clock[4:]}"


def _pages_of(path: Path) -> dict[str, dict[str, Any]]:
    """スナップショットを `{url: ページ dict}` にする。"""
    from dataclasses import asdict

    src = str((Path(__file__).resolve().parents[2] / "src").resolve())
    if src not in sys.path:
        sys.path.insert(0, src)
    from diff.snapshot import load_snapshot

    out: dict[str, dict[str, Any]] = {}
    for page in load_snapshot(path):
        data = asdict(page)
        out[str(data.get("url") or "")] = data
    return out


def _fields_of(page: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for form in page.get("forms") or []:
        for field in form.get("fields") or []:
            key = _field_key(field)
            if key:
                out[key] = dict(field)
    return out


def _impacted(
    tests: Sequence[Mapping[str, Any]], page_id: str, locator: str, key: str
) -> list[str]:
    hit: list[str] = []
    for test in tests:
        if page_id and str(test.get("screen") or "") != page_id:
            continue
        for step in test.get("steps") or []:
            if (locator and str(step.get("loc") or "") == locator) or (
                key and str(step.get("target") or "") == key
            ):
                hit.append(str(test.get("id")))
                break
    return hit


def drift_items(domain: str) -> dict[str, Any]:
    """直近 2 世代のクロールを比べ、テストに効く変更を列挙する（契約 §3）。"""
    snapshots = _snapshot_paths(domain)
    if len(snapshots) < 2:
        return {"baseline_at": "", "current_at": "", "items": [], "reason": NO_BASELINE_REASON}

    baseline_path, current_path = snapshots[-2], snapshots[-1]
    try:
        old_pages = _pages_of(baseline_path)
        new_pages = _pages_of(current_path)
    except (OSError, ValueError, ImportError, json.JSONDecodeError):
        return {"baseline_at": "", "current_at": "", "items": [], "reason": NO_BASELINE_REASON}

    report = load_report(domain)
    page_id_by_url = {
        str(s.get("url") or ""): str(s.get("page_id") or "") for s in report.get("screens") or []
    }
    tests = _loaded(domain).get("tests") or []
    state = _load_drift_state(domain)

    items: list[dict[str, Any]] = []
    for url, new_page in new_pages.items():
        old_page = old_pages.get(url)
        if old_page is None:
            continue
        page_id = page_id_by_url.get(url, "")
        title = str(new_page.get("title") or url)
        old_fields = _fields_of(old_page)
        new_fields = _fields_of(new_page)

        for key, old_field in old_fields.items():
            old_loc = _field_locator(old_field)
            new_field = new_fields.get(key)
            if new_field is None:
                items.append(
                    _drift_item(
                        "removed",
                        page_id,
                        title,
                        key,
                        old_loc,
                        "",
                        tests,
                        state,
                        f"「{key}」が無くなりました",
                    )
                )
                continue
            new_loc = _field_locator(new_field)
            if new_loc != old_loc:
                items.append(
                    _drift_item(
                        "locator",
                        page_id,
                        title,
                        key,
                        old_loc,
                        new_loc,
                        tests,
                        state,
                        f"「{key}」のロケータが変わりました",
                    )
                )
        for key, new_field in new_fields.items():
            if key not in old_fields:
                items.append(
                    _drift_item(
                        "added",
                        page_id,
                        title,
                        key,
                        "",
                        _field_locator(new_field),
                        tests,
                        state,
                        f"「{key}」が増えました",
                    )
                )

        old_buttons = [str(b) for b in (old_page.get("buttons") or [])]
        new_buttons = [str(b) for b in (new_page.get("buttons") or [])]
        for index, old_label in enumerate(old_buttons):
            if index < len(new_buttons) and new_buttons[index] != old_label:
                items.append(
                    _drift_item(
                        "text",
                        page_id,
                        title,
                        f"btn_{index}",
                        f"text={old_label}",
                        f"text={new_buttons[index]}",
                        tests,
                        state,
                        "ボタンの文言が変わりました",
                    )
                )
            elif index >= len(new_buttons):
                items.append(
                    _drift_item(
                        "removed",
                        page_id,
                        title,
                        f"btn_{index}",
                        f"text={old_label}",
                        "",
                        tests,
                        state,
                        "ボタンが無くなりました",
                    )
                )

    return {
        "baseline_at": _snapshot_at(baseline_path),
        "current_at": _snapshot_at(current_path),
        "items": items,
    }


def _drift_item(
    kind: str,
    page_id: str,
    screen_title: str,
    key: str,
    old: str,
    now: str,
    tests: Sequence[Mapping[str, Any]],
    state: Mapping[str, str],
    title: str,
) -> dict[str, Any]:
    item_id = f"{page_id or screen_title}:{key}:{kind}"
    return {
        "id": item_id,
        "kind": kind,
        "screen": page_id,
        "screen_title": screen_title,
        "key": key,
        "title": title,
        "old": old,
        "now": now,
        "impact": _impacted(tests, page_id, old, key),
        "fix": {"loc": now, "stab": locator_stability(now)} if now else {"loc": "", "stab": "low"},
        "state": state.get(item_id, "open"),
    }


def drift_apply(domain: str, item_id: str) -> dict[str, Any]:
    """影響テストの該当 loc を fix に差し替え、fixed=true にする（契約 §3）。"""
    payload = drift_items(domain)
    item = next((x for x in payload.get("items") or [] if x["id"] == str(item_id)), None)
    if item is None:
        raise Ta2StoreError(f"変更が見つかりません: {item_id}")
    new_loc = str((item.get("fix") or {}).get("loc") or "")
    if not new_loc:
        raise Ta2StoreError(
            "差し替え先のロケータがありません（要素が無くなった変更は手で直してください）"
        )

    data = _loaded(domain)
    old_loc = str(item.get("old") or "")
    applied: list[str] = []
    tests: list[dict[str, Any]] = []
    for raw in data.get("tests") or []:
        test = dict(raw)
        if str(test.get("id")) not in (item.get("impact") or []):
            tests.append(test)
            continue
        steps: list[dict[str, Any]] = []
        changed = False
        for step in test.get("steps") or []:
            if str(step.get("loc") or "") == old_loc:
                steps.append(
                    {**step, "loc": new_loc, "stab": locator_stability(new_loc), "fixed": True}
                )
                changed = True
            else:
                steps.append(dict(step))
        if changed:
            applied.append(str(test.get("id")))
            test.update({"steps": steps, "status": "fixed", "updated_at": _now()})
        else:
            test["steps"] = steps
        tests.append(test)

    save(domain, {**data, "tests": tests})
    _save_drift_state(domain, {**_load_drift_state(domain), str(item_id): "applied"})
    return {"applied": applied}


def drift_dismiss(domain: str, item_id: str) -> dict[str, Any]:
    """変更を「対応不要」として記録する。"""
    _save_drift_state(domain, {**_load_drift_state(domain), str(item_id): "dismissed"})
    return {"ok": True}


# =========================================================================
# テスト単体の操作（契約 §3）
# =========================================================================
def duplicate(domain: str, test_id: str) -> dict[str, Any]:
    data = _loaded(domain)
    source = _find(data, test_id)
    copied = {
        **source,
        "id": _next_id(data),
        "name": f"{source.get('name', '')}（複製）",
        "source": "manual",
        "steps": [dict(s) for s in source.get("steps") or []],
        "status": "new",
        "history": [],
        "last": {},
        "updated_at": _now(),
    }
    data["tests"] = [dict(t) for t in data.get("tests") or []] + [copied]
    save(domain, data)
    return copied


_UPDATABLE = ("name", "steps", "screen", "technique")


def update_test(domain: str, test_id: str, patch: Mapping[str, Any]) -> dict[str, Any]:
    """name / steps を保存する。status が pass/fail/flaky なら `fixed` に変える。"""
    data = _loaded(domain)
    test = _find(data, test_id)
    updated = dict(test)
    for key in _UPDATABLE:
        if key not in patch:
            continue
        if key == "steps":
            updated["steps"] = _validated_steps(patch["steps"])
        else:
            updated[key] = str(patch[key])
    if str(updated.get("status")) in {"pass", "fail", "flaky"}:
        updated["status"] = "fixed"
    updated["updated_at"] = _now()
    save(domain, _replace(data, updated))
    return updated


def _validated_steps(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise Ta2StoreError("手順は配列で指定してください")
    steps: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise Ta2StoreError(f"{index + 1} 番目の手順の形式が不正です")
        action = str(item.get("action") or "")
        if action not in ACTION_VOCABULARY:
            raise Ta2StoreError(f"{index + 1} 番目の手順の操作が不正です: {action or '(空)'}")
        step = dict(item)
        step["kind"] = str(item.get("kind") or ("pre" if action == ACT_OPEN else "act"))
        step["stab"] = locator_stability(step.get("loc"))
        steps.append(step)
    return steps


def delete_test(domain: str, test_id: str) -> dict[str, Any]:
    data = _loaded(domain)
    _find(data, test_id)  # 存在しなければ Ta2StoreError
    remaining = [dict(t) for t in data.get("tests") or [] if str(t.get("id")) != str(test_id)]
    save(domain, {**data, "tests": remaining})
    return {"ok": True, "id": str(test_id)}
