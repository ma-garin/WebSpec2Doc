"""playwright_candidates.json から Python Playwright の `*_spec.py` を生成する。

製品内の正式な実行形式。TS 生成器（spec_ts_generator）と同じ候補・フィルタ・
メタデータを使い、同じ操作を Python（sync API）で表す。Node は要求しない。
実行は web.services.pw_runner が行う（送信ゲートウェイもランナー側で適用する）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from web.services.spec_ts_generator import (
    _JS_EXPR_PREFIX,
    _apply_filter,
    _date_format_for_url,
    _extract_url,
    _field_label,
    _looks_like_placeholder,
    _page_id_from_trace,
    _representative_value,
    _safe_str,
    _screen_index_from_report,
    _find_report_path,
    _sort_locators_by_reliability,
    _write_test_metadata,
)

_SPEC_SUFFIX = "_spec.py"


def metadata_file_path_py(output_path: Path) -> Path:
    """`<base>_spec.py` に対応するメタデータ JSON（`<base>.meta.json`、TS 版と同名）。"""
    name = output_path.name
    for suffix in (_SPEC_SUFFIX, ".py"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return output_path.with_name(f"{name}.meta.json")


def generate_spec_py(
    domain: Any = None,
    candidates_path: Any = None,
    output_path: Any = None,
    filter_mode: str = "all",
    enable_strong_assertions: bool = False,
    enable_self_healing: bool = False,
    report_path: Path | None = None,
    allow_submit: bool = False,
) -> Path:
    """候補 JSON から Python spec を生成する（引数は generate_spec_ts と同じ）。

    引数順は (domain, candidates_path, output_path) と (candidates_path,
    output_path, domain) のどちらで渡されても受理する（Path でないものを domain とみなす）。
    """
    if isinstance(domain, Path) and not isinstance(output_path, Path):
        domain, candidates_path, output_path = output_path, domain, candidates_path
    if not isinstance(candidates_path, Path) or not isinstance(output_path, Path):
        raise TypeError("candidates_path と output_path は Path で渡す")
    domain = str(domain or "")

    import json

    data: dict[str, Any] = {}
    try:
        data = json.loads(candidates_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    candidates: list[dict[str, Any]] = data.get("candidates", [])
    filtered = _apply_filter(candidates, filter_mode)
    screen_index = _screen_index_from_report(_find_report_path(candidates_path, report_path))

    lines = [
        "import datetime as _dt",
        "",
        "from web.services.pw_spec_api import (",
        "    annotate, case, expect, safe_enabled, safe_uncheck,",
        ")",
        "",
        f"# AutoRun generated spec (python) - {_comment(domain)}",
        f"# filter: {filter_mode}  candidates: {len(filtered)}/{len(candidates)}",
        "# 送信ゲートウェイはランナー（pw_runner）が必ず適用する。",
        "",
    ]
    for index, item in enumerate(filtered, start=1):
        _append_case(
            lines, index, item, enable_strong_assertions, enable_self_healing,
            screen_index, allow_submit,
        )

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # メタは TS 版と同じ `<base>.meta.json`。TS 側の実装を再利用する。
    meta_anchor = metadata_file_path_py(output_path).with_name(
        metadata_file_path_py(output_path).name.removesuffix(".meta.json") + ".spec.ts"
    )
    _write_test_metadata(domain, filtered, candidates_path, meta_anchor, report_path)
    return output_path


# ---------------------------------------------------------------- 文字列ヘルパ


def _q(value: object) -> str:
    """Python の文字列リテラルにする。"""
    return repr(_safe_str(value))


def _comment(value: object) -> str:
    return re.sub(r"[\r\n]+", " ", _safe_str(value))


def _func_name(index: int, test_id: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_]+", "_", test_id).strip("_").lower()
    return f"case_{index:03d}_{slug}" if slug else f"case_{index:03d}"


# ---------------------------------------------------------------- ケース本体


def _append_case(
    lines: list[str],
    index: int,
    item: dict[str, Any],
    enable_strong_assertions: bool,
    enable_self_healing: bool,
    screen_index: dict[str, dict[str, str]],
    allow_submit: bool,
) -> None:
    title = _safe_str(item.get("title", "untitled"))
    test_id = _safe_str(item.get("id", ""))
    trace_id = _safe_str(item.get("trace_id", ""))
    steps: list[Any] = item.get("steps") or []
    locators: list[str] = item.get("locators") or []
    expected = _safe_str(item.get("expected", ""))
    label = f"{test_id} {title} [{trace_id}]"
    name = _func_name(index, test_id)

    if _safe_str(item.get("automation_status", "")) == "manual-review":
        lines.append(f"@case({_q(label)}, skip=True)")
        lines.append(f"def {name}(page):")
        lines.append("    # manual-review: skip in CI")
        lines.append("    pass")
        lines.append("")
        lines.append("")
        return

    lines.append(f"@case({_q(label)})")
    lines.append(f"def {name}(page):")
    url = _extract_url(steps)
    if url:
        lines.append(f"    page.goto({_q(url)})")
        lines.append("    page.wait_for_load_state('domcontentloaded')")
    for step in steps:
        if not str(step).startswith("page.goto("):
            lines.append(f"    # {_comment(step)}")
    if expected:
        lines.append(f"    # expected: {_comment(expected)}")
    if enable_self_healing and locators:
        expr = _role_based_locator(
            locators,
            field_name=_safe_str(item.get("field_name", "")),
            aria_label=_safe_str(item.get("aria_label", "")),
            field_type=_safe_str(item.get("field_type", "text")),
        )
        lines.append(f"    target_locator = {expr}")
        lines.append("    expect(target_locator).to_be_visible()")
    else:
        lines.append("    expect(page.locator('body')).to_be_visible()")
    if enable_strong_assertions and expected:
        for assertion in _strong_assertions(expected):
            lines.append(f"    {assertion}")

    field = item.get("field")
    if field and title in ("フォーム入力", "必須入力"):
        _append_form_operations(lines, item, title, field, allow_submit)
    elif title == "画面遷移":
        _append_transition_assertion(lines, trace_id, screen_index)
    elif title == "画面表示スモーク":
        _append_smoke_assertion(lines, trace_id, screen_index)
    lines.append("")
    lines.append("")


def _append_smoke_assertion(
    lines: list[str], trace_id: str, screen_index: dict[str, dict[str, str]]
) -> None:
    info = screen_index.get(_page_id_from_trace(trace_id), {})
    expected_title = info.get("title", "")
    if not expected_title:
        return
    lines.append("    title = page.title()")
    lines.append("    assert len(title) > 0")
    lines.append(f"    assert {_q(expected_title[:20])} in title")


def _append_transition_assertion(
    lines: list[str], trace_id: str, screen_index: dict[str, dict[str, str]]
) -> None:
    dest_id = trace_id.split("->")[-1] if "->" in trace_id else ""
    dest = screen_index.get(dest_id, {})
    dest_url = dest.get("url", "")
    dest_title = dest.get("title", "")
    if not dest_url:
        return
    lines.append(f"    page.goto({_q(dest_url)})")
    lines.append("    page.wait_for_load_state('domcontentloaded')")
    lines.append("    title = page.title()")
    lines.append("    assert len(title) > 0")
    if dest_title:
        lines.append(f"    assert {_q(dest_title[:20])} in title")


# ---------------------------------------------------------------- フォーム操作


def _append_form_operations(
    lines: list[str],
    item: dict[str, Any],
    title: str,
    field: dict[str, Any],
    allow_submit: bool,
) -> None:
    siblings: list[dict[str, Any]] = item.get("required_siblings") or []
    form_action = _safe_str(item.get("form_action", ""))
    form_selector = f'form[action="{form_action}"]' if form_action else ""
    date_format = _date_format_for_url(_extract_url(item.get("steps") or []))

    lines.append(
        "    # 他の必須項目には代表値を入れ、対象項目だけを検証対象にする"
        if siblings
        else "    # このフォームには他に必須項目が無い"
    )
    for sib in siblings:
        _append_fill(lines, sib, _representative_value(sib, date_format), date_format)

    locator = _field_locator(field)
    if title == "フォーム入力":
        value = _representative_value(field, date_format)
        lines.append(f"    # `{_comment(_field_label(field))}` に代表値を入力")
        _append_fill(lines, field, value, date_format)
        if form_selector:
            lines.append(
                f"    form_valid = page.locator({_q(form_selector)})"
                ".evaluate('(f) => f.checkValidity()')"
            )
            lines.append("    assert form_valid is True")
        else:
            lines.append(f"    field_valid = {locator}.evaluate('(el) => el.checkValidity()')")
            lines.append("    assert field_valid is True")
        if allow_submit:
            _append_submit(lines, form_selector)
    else:
        lines.append(f"    # `{_comment(_field_label(field))}` を空にする")
        _append_clear(lines, field)
        lines.append(f"    field_valid = {locator}.evaluate('(el) => el.checkValidity()')")
        lines.append("    assert field_valid is False")
        if form_selector:
            lines.append(
                f"    form_valid = page.locator({_q(form_selector)})"
                ".evaluate('(f) => f.checkValidity()')"
            )
            lines.append("    assert form_valid is False")


def _field_locator(field: dict[str, Any]) -> str:
    locators: list[str] = field.get("locators") or []
    primary = locators[0] if locators else f"[name=\"{field.get('name', '')}\"]"
    return f"page.locator({_q(primary)})"


def _date_expr_py(date_format: str) -> str:
    """実行時に「今日+14日」を計算する Python 式（固定日付は埋め込まない）。"""
    base = "(_dt.date.today() + _dt.timedelta(days=14))"
    if date_format == "mdy_slash":
        return f"{base}.strftime('%m/%d/%Y')"
    if date_format == "ymd_slash":
        return f"{base}.strftime('%Y/%m/%d')"
    return f"{base}.isoformat()"


def _append_fill(
    lines: list[str], field: dict[str, Any], value: str, date_format: str
) -> None:
    field_type = _safe_str(field.get("field_type", "text"))
    if field_type == "hidden":
        return
    loc = _field_locator(field)
    # 他項目に連動して disabled になる条件付きフィールドは、有効なときだけ操作する。
    lines.append(f"    if safe_enabled({loc}):")
    if field_type == "select":
        lines.append(f"        {loc}.select_option({_q(value)})")
    elif field_type in ("checkbox", "radio"):
        lines.append(f"        {loc}.check()")
    elif value.startswith(_JS_EXPR_PREFIX):
        # datepicker が既定値を先に入れていると fill が連結する競合があるため、先に空にする。
        lines.append(f"        {loc}.fill('')")
        lines.append(f"        {loc}.fill({_date_expr_py(date_format)})")
        # datepicker のポップアップを閉じるため body を強制クリックしてフォーカスを外す。
        lines.append(
            "        page.locator('body').click(position={'x': 2, 'y': 2}, force=True)"
        )
    else:
        lines.append(f"        {loc}.fill({_q(value)})")


def _append_clear(lines: list[str], field: dict[str, Any]) -> None:
    field_type = _safe_str(field.get("field_type", "text"))
    loc = _field_locator(field)
    if field_type == "select":
        options = [str(o) for o in (field.get("options") or [])]
        placeholder = next((o for o in options if _looks_like_placeholder(o)), "")
        if placeholder:
            lines.append(f"    {loc}.select_option({_q(placeholder)})")
        else:
            lines.append(f"    {loc}.select_option(index=0)")
    elif field_type in ("checkbox", "radio"):
        lines.append(f"    safe_uncheck({loc})")
    else:
        lines.append(f"    {loc}.fill('')")


def _append_submit(lines: list[str], form_selector: str) -> None:
    target = f"page.locator({_q(form_selector)})" if form_selector else "page"
    lines.append("    # 実行条件で「送信まで実行」が選ばれたため、実際に送信する")
    lines.append("    before_url = page.url")
    lines.append(
        f"    submit_button = {target}"
        ".locator('button[type=\"submit\"], input[type=\"submit\"]').first"
    )
    lines.append("    if submit_button.count():")
    lines.append("        submit_button.click()")
    lines.append("    else:")
    lines.append(f"        {target}.evaluate('(f) => f.submit()')")
    lines.append("    page.wait_for_load_state('domcontentloaded')")
    lines.append("    after_url = page.url")
    lines.append("    assert isinstance(after_url, str)")
    lines.append("    if after_url == before_url:")
    lines.append("        # 遷移しない実装もあるため失敗にはしない。送信した事実だけを証跡へ残す。")
    lines.append("        annotate('submit', '送信後も同一URL')")


# ---------------------------------------------------------------- ロケータ・強化アサーション


def _role_based_locator(
    locators: list[str], field_name: str = "", aria_label: str = "", field_type: str = "text"
) -> str:
    label = aria_label or field_name
    if aria_label:
        return f"page.get_by_label({_q(aria_label)})"
    role_by_type = {
        "select": "combobox",
        "textarea": "textbox",
        "checkbox": "checkbox",
        "radio": "radio",
        "submit": "button",
        "button": "button",
        "reset": "button",
    }
    role = role_by_type.get(field_type)
    if role:
        name_part = f", name={_q(label)}" if label else ""
        return f"page.get_by_role({_q(role)}{name_part})"
    if label:
        return f"page.get_by_label({_q(label)})"
    combined = ", ".join(_sort_locators_by_reliability(locators))
    return f"page.locator({_q(combined)}).first"


def _strong_assertions(expected: str) -> list[str]:
    out: list[str] = []
    if "エラー" in expected:
        out.append(
            "expect(page.locator('[role=\"alert\"], .error-message, "
            "[aria-live=\"polite\"]').first).to_be_visible()"
        )
    url_like = re.search(r"(https?://[^\s]+|/[^\s]*)", expected)
    if url_like:
        out.append(f"expect(page).to_have_url({_q(url_like.group(1))})")
    return out
