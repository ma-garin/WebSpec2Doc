"""テストケース表 → Python Playwright `testcases_spec.py` の変換（製品内の実行形式）。

`testcase_spec_generator`（TypeScript・エクスポート専用）と同じ行・同じ検証の意味を、
Python（sync API）で表す。実行は web.services.pw_runner。Node は要求しない。
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PY_SPEC_FILE_NAME = "testcases_spec.py"
PY_METADATA_FILE_NAME = "testcases.meta.json"

_ERROR_SELECTOR = (
    '[role="alert"], .error, .errors, .is-error, .error-message, '
    ".invalid-feedback, .field-error, .form-error"
)


def _q(value: Any) -> str:
    """Python のリテラルとして安全な文字列（JSON 文字列は Python 文字列として有効）。"""
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


def _href_suffix(url: str) -> str:
    path = re.sub(r"^https?://[^/]+", "", str(url))
    return path.split("/")[-1] or path or ""


def _action_lines(action: Mapping[str, Any]) -> list[str]:
    kind = str(action.get("type") or "")
    locator = str(action.get("locator") or "")
    if kind == "goto":
        return [f'page.goto({_q(action.get("url"))}, wait_until="domcontentloaded")']
    if kind == "wait_load":
        return ['page.wait_for_load_state("domcontentloaded")']
    if kind == "fill" and locator:
        return [f'page.locator({_q(locator)}).fill({_q(action.get("value"))})']
    if kind == "clear" and locator:
        return [f'page.locator({_q(locator)}).fill("")']
    if kind == "select" and locator:
        return [f'select_by_value_or_label(page, {_q(locator)}, {_q(action.get("value"))})']
    if kind == "click":
        if locator:
            return [f"page.locator({_q(locator)}).first.click()"]
        return [f'click_by_label(page, {_q(action.get("text"))})']
    if kind == "click_text":
        return [f'click_by_label(page, {_q(action.get("text"))})']
    if kind == "click_link_to":
        suffix = _href_suffix(action.get("url") or "")
        return [f'click_link_to(page, {_q(suffix)}, {_q(action.get("title") or "")})']
    note = json.dumps(dict(action), ensure_ascii=False).replace("\n", " ")
    return [f"# 未対応の操作のためスキップ: {note}"]


def _assertion_lines(assertion: Mapping[str, Any]) -> list[str]:
    kind = str(assertion.get("type") or "")
    if kind == "expect_title":
        return [f'assert {_q(assertion.get("value"))} in page.title(), "タイトルが一致しません"']
    if kind == "expect_text":
        return [f'expect(page.get_by_text({_q(assertion.get("value"))}, exact=False).first).to_be_visible()']
    if kind == "expect_url":
        return [f'expect(page).to_have_url({_q(assertion.get("value"))})']
    if kind == "expect_no_error":
        return ["expect_no_error_shown(page)"]
    if kind == "expect_stay":
        return [f'expect_not_submitted(page, {_q(assertion.get("url"))})']
    if kind == "expect_no_server_error":
        return ["expect_no_server_error(page)"]
    if kind == "expect_value_length":
        return [
            f'expect_value_length(page, {_q(assertion.get("locator"))}, {int(assertion.get("max") or 0)})'
        ]
    note = json.dumps(dict(assertion), ensure_ascii=False).replace("\n", " ")
    return [f"# 未対応の検証のためスキップ: {note}"]


def _step_indexes(row: Mapping[str, Any]) -> tuple[list[int | None], list[int | None]]:
    """`ta2_store.steps_from_row` と同じ 0 起点 index（TS 生成器と同一の規則）。"""
    from web.services.ta2_store import _action_to_step, _assertion_to_step

    seq = 0
    actions: list[int | None] = []
    for action in row.get("actions") or []:
        if _action_to_step(action) is None:
            actions.append(None)
            continue
        actions.append(seq)
        seq += 1
    assertions: list[int | None] = []
    for assertion in row.get("assertions") or []:
        if _assertion_to_step(assertion) is None:
            assertions.append(None)
            continue
        assertions.append(seq)
        seq += 1
    return actions, assertions


def _as_step(index: int | None, body: list[str]) -> list[str]:
    """1 手順の直前に現在の手順 ID を記録する（失敗時にどの手順かをランナーが読む）。"""
    if index is None:
        return ["    " + line for line in body]
    return [f'    _api.LAST_STEP = "S{index}"'] + ["    " + line for line in body]


_HEADER = f'''"""自動生成 — テストケース表（9列）から生成。手で編集しても再生成で上書きされます。"""
import web.services.pw_spec_api as _api
from web.services.pw_spec_api import case, expect

ERROR_SELECTOR = {_q(_ERROR_SELECTOR)}


def select_by_value_or_label(page, selector, value):
    """値一致で選べないときはラベル一致で選ぶ。"""
    el = page.locator(selector)
    try:
        el.select_option(value)
    except Exception:
        el.select_option(label=value)


def click_by_label(page, label):
    """ボタン → 同名の submit → テキスト一致の順で押す。"""
    by_role = page.get_by_role("button", name=label).first
    if by_role.count():
        by_role.click()
        return
    by_submit = page.locator('input[type=submit][value="' + label + '"]').first
    if by_submit.count():
        by_submit.click()
        return
    page.get_by_text(label, exact=False).first.click()


def click_link_to(page, href_suffix, title):
    """遷移先 URL 末尾を持つリンク、無ければ画面名のリンクを押す。"""
    if href_suffix:
        by_href = page.locator('a[href$="' + href_suffix + '"]').first
        if by_href.count():
            by_href.click()
            return
    page.get_by_role("link", name=title).first.click()


def expect_no_error_shown(page):
    errors = page.locator(ERROR_SELECTOR)
    for i in range(errors.count()):
        if errors.nth(i).is_visible():
            raise AssertionError("エラー表示が出ています: " + errors.nth(i).inner_text())


def expect_not_submitted(page, url):
    current = page.url.split("#")[0]
    if current != url.split("#")[0]:
        raise AssertionError("送信されてしまいました（URL が " + current + " に変化）")


def expect_value_length(page, selector, max_len):
    value = page.locator(selector).input_value()
    if len(value) > max_len:
        raise AssertionError(
            "入力が制限されていません（" + str(len(value)) + " 文字が入りました。上限 " + str(max_len) + "）"
        )


def expect_no_server_error(page):
    body = page.locator("body").inner_text()[:4000]
    for marker in ("Internal Server Error", "500 Internal", "Traceback (most recent call last)"):
        if marker in body:
            raise AssertionError("サーバエラーが表示されています: " + marker)
'''


def _title(row: Mapping[str, Any]) -> str:
    return f"{row.get('case_id', '')} {row.get('name', '')}".strip()


def generate_py_spec(
    targets: Sequence[Mapping[str, Any]], out_dir: Path
) -> tuple[Path, Path, list[dict[str, str]]]:
    """実行可能な行（呼び出し側が選別済み）から `testcases_spec.py` とメタを書く。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [_HEADER]
    mapping: list[dict[str, str]] = []
    for n, row in enumerate(targets):
        title = _title(row)
        mapping.append({"test_title": title, "case_id": str(row.get("case_id", ""))})
        assertions = list(row.get("assertions") or [])
        action_ix, assertion_ix = _step_indexes(row)
        after_input = [(i, a) for i, a in enumerate(assertions) if a.get("stage") == "after_input"]
        at_end = [(i, a) for i, a in enumerate(assertions) if a.get("stage") != "after_input"]
        lines.append("")
        lines.append(f"@case({_q(title)})")
        lines.append(f"def case_{n}(page):")
        lines.append('    _api.LAST_STEP = ""')
        emitted = False
        for index, action in enumerate(row.get("actions") or []):
            if after_input and not emitted and action.get("type") in {"click_text", "click"}:
                for i, assertion in after_input:
                    lines.extend(_as_step(assertion_ix[i], _assertion_lines(assertion)))
                emitted = True
            lines.extend(_as_step(action_ix[index], _action_lines(action)))
        if after_input and not emitted:
            for i, assertion in after_input:
                lines.extend(_as_step(assertion_ix[i], _assertion_lines(assertion)))
        for i, assertion in at_end:
            lines.extend(_as_step(assertion_ix[i], _assertion_lines(assertion)))
        lines.append("    pass")
    spec_path = out_dir / PY_SPEC_FILE_NAME
    spec_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    meta_path = out_dir / PY_METADATA_FILE_NAME
    meta_path.write_text(json.dumps({"tests": mapping}, ensure_ascii=False, indent=2), encoding="utf-8")
    return spec_path, meta_path, mapping
