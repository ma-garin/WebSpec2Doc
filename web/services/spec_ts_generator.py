from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# タイトルベースのフィルター用定数（auto_run.py からも参照）
SMOKE_TITLES: frozenset[str] = frozenset(["画面表示スモーク"])
TRANSITION_TITLES: frozenset[str] = frozenset(["画面表示スモーク", "画面遷移"])
FORM_TITLES: frozenset[str] = frozenset(["画面表示スモーク", "フォーム入力", "必須入力"])

# _representative_value() が固定リテラルではなく実行時評価の JS 式を返すときの目印。
# 生成時に埋め込んだ固定値だと「実行日により合否が変わる」問題（例: 日付の営業ルール）
# を起こすため、date 系フィールドはこの形で実行時計算にする。
_JS_EXPR_PREFIX = "@@expr:"


def generate_spec_ts(
    domain: str,
    candidates_path: Path,
    output_path: Path,
    filter_mode: str = "all",
    enable_strong_assertions: bool = False,
    enable_self_healing: bool = False,
    generate_page_object: bool = False,
    report_path: Path | None = None,
) -> Path:
    """playwright_candidates.json から Playwright .spec.ts を生成する。

    filter_mode:
      "all"        全候補（manual-review は test.skip）
      "smoke"      画面表示スモークのみ
      "transition" スモーク + 遷移テスト
      "form"       スモーク + フォーム入力 + 必須入力

    enable_strong_assertions: True の場合、expected フィールドに基づく強化アサーションを追加。
    enable_self_healing: True の場合、locators フィールドから resilient ロケータを生成。
    report_path: report.json のパス。省略時は候補ファイルの近傍から探索する。

    生成する各テストに対応する test_id・page_id・fingerprint を含む
    メタデータ JSON（<basename>.meta.json）を併産する。
    """
    data: dict[str, Any] = {}
    try:
        data = json.loads(candidates_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass

    candidates: list[dict[str, Any]] = data.get("candidates", [])
    filtered = _apply_filter(candidates, filter_mode)
    screen_index = _screen_index_from_report(_find_report_path(candidates_path, report_path))

    # K1 送信ゲートウェイ（設計計画 rev.3）を必ず経由させる。
    # `@playwright/test` から直接 test を取らず、auto-use フィクスチャ経由にすることで、
    # テスト側から無効化できない形で SSRF 遮断・予算強制・全件記録を効かせる。
    lines = [
        "import { test, expect } from './_autorun_egress';",
        "",
        f"// AutoRun generated spec — {domain}",
        f"// filter: {filter_mode}  candidates: {len(filtered)}/{len(candidates)}",
        "// 送信は K1 ゲートウェイ（_autorun_egress.ts）を必ず経由する。",
        "",
    ]

    for item in filtered:
        _append_test_block(lines, item, enable_strong_assertions, enable_self_healing, screen_index)

    output_path.write_text("\n".join(lines), encoding="utf-8")
    _write_test_metadata(domain, filtered, candidates_path, output_path, report_path)
    if generate_page_object:
        base_name = output_path.name.removesuffix(".spec.ts")
        page_object_path = output_path.with_name(f"{base_name}.page.ts")
        _generate_page_object(domain, filtered, page_object_path)
    return output_path


def _find_report_path(candidates_path: Path, report_path: Path | None) -> Path | None:
    """report.json のパスを解決する（明示指定 > 候補ファイル近傍の探索）。"""
    if report_path is not None:
        return report_path if report_path.is_file() else None
    for parent in (candidates_path.parent, candidates_path.parent.parent):
        candidate = parent / "report.json"
        if candidate.is_file():
            return candidate
    return None


def _screen_index_from_report(report_path: Path | None) -> dict[str, dict[str, str]]:
    """report.json から page_id → {url, fingerprint} のインデックスを構築する。"""
    if report_path is None:
        return {}
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    index: dict[str, dict[str, str]] = {}
    for screen in report.get("screens", []):
        page_id = str(screen.get("page_id") or "")
        if page_id:
            index[page_id] = {
                "url": str(screen.get("url") or ""),
                "fingerprint": str(screen.get("fingerprint") or ""),
                "title": str(screen.get("title") or ""),
            }
    return index


_PAGE_ID_PATTERN = re.compile(r"^(P\d+)")


def _page_id_from_trace(trace_id: str) -> str:
    """trace_id（例: P001 / P001->P002 / P001-F01-I02）から先頭の page_id を抽出する。"""
    match = _PAGE_ID_PATTERN.match(trace_id)
    return match.group(1) if match else ""


def metadata_file_path(output_path: Path) -> Path:
    """spec.ts の出力パスに対応するメタデータ JSON のパスを返す。"""
    base_name = output_path.name.removesuffix(".spec.ts").removesuffix(".ts")
    return output_path.with_name(f"{base_name}.meta.json")


def _write_test_metadata(
    domain: str,
    candidates: list[dict[str, Any]],
    candidates_path: Path,
    output_path: Path,
    report_path: Path | None,
) -> Path:
    """各テストの test_id・page_id・fingerprint を含むメタデータ JSON を併産する。"""
    screen_index = _screen_index_from_report(_find_report_path(candidates_path, report_path))
    tests: list[dict[str, Any]] = []
    for item in candidates:
        trace_id = _safe_str(item.get("trace_id", ""))
        page_id = _page_id_from_trace(trace_id)
        screen = screen_index.get(page_id, {})
        tests.append(
            {
                "test_id": _safe_str(item.get("id", "")),
                "title": _safe_str(item.get("title", "")),
                "trace_id": trace_id,
                "page_id": page_id,
                "fingerprint": screen.get("fingerprint", ""),
                "url": screen.get("url", ""),
                "has_real_assertion": _has_real_assertion(item, screen_index),
            }
        )
    metadata_path = metadata_file_path(output_path)
    metadata_path.write_text(
        json.dumps({"domain": domain, "tests": tests}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return metadata_path


def _has_real_assertion(item: dict[str, Any], screen_index: dict[str, dict[str, str]]) -> bool:
    """このテストが body 可視性だけでなく、実質的な検証（値の受理／拒否・実在確認）を
    行うかどうかを返す。証跡パックの「検証実行率」表示に使う（spec_ts_generator と
    同じ判定条件を共有し、二重管理を避ける）。"""
    title = _safe_str(item.get("title", ""))
    if _safe_str(item.get("automation_status", "")) == "manual-review":
        return False
    if item.get("field") and title in ("フォーム入力", "必須入力"):
        return True
    trace_id = _safe_str(item.get("trace_id", ""))
    if title == "画面遷移":
        dest_id = trace_id.split("->")[-1] if "->" in trace_id else ""
        return bool(screen_index.get(dest_id, {}).get("url"))
    if title == "画面表示スモーク":
        return bool(screen_index.get(_page_id_from_trace(trace_id), {}).get("title"))
    return False


def _append_test_block(
    lines: list[str],
    item: dict[str, Any],
    enable_strong_assertions: bool,
    enable_self_healing: bool,
    screen_index: dict[str, dict[str, str]] | None = None,
) -> None:
    """単一候補の test ブロックを lines に追記する。"""
    title = _safe_str(item.get("title", "untitled"))
    test_id = _safe_str(item.get("id", ""))
    trace_id = _safe_str(item.get("trace_id", ""))
    steps: list[Any] = item.get("steps") or []
    locators: list[str] = item.get("locators") or []
    expected = _safe_str(item.get("expected", ""))
    automation_status = _safe_str(item.get("automation_status", ""))
    screen_index = screen_index or {}

    label = f"'{_esc(test_id)} {_esc(title)} [{_esc(trace_id)}]'"

    if automation_status == "manual-review":
        lines.append(f"test.skip({label}, async () => {{")
        lines.append("  // manual-review: skip in CI")
        lines.append("});")
        lines.append("")
        return

    lines.append(f"test({label}, async ({{ page }}) => {{")
    url = _extract_url(steps)
    if url:
        lines.append(f"  await page.goto('{_esc(url)}');")
        lines.append("  await page.waitForLoadState('domcontentloaded');")

    # ベースライン（従来どおり）。実データが無い候補（他の生成経路・旧フィクスチャ）
    # でも、コメントと最低限の可視性チェックは常に出力する。
    for step in steps:
        if not str(step).startswith("page.goto("):
            lines.append(f"  // {_esc(str(step))}")
    if expected:
        lines.append(f"  // expected: {_esc(expected)}")
    if enable_self_healing and locators:
        locator_expr = _build_role_based_locator(
            locators,
            field_name=_safe_str(item.get("field_name", "")),
            aria_label=_safe_str(item.get("aria_label", "")),
            field_type=_safe_str(item.get("field_type", "text")),
        )
        lines.append(f"  const targetLocator = {locator_expr};")
        lines.append("  await expect(targetLocator).toBeVisible();")
    else:
        lines.append("  await expect(page.locator('body')).toBeVisible();")
    if enable_strong_assertions and expected:
        for assertion in _generate_strong_assertions(expected):
            lines.append(f"  {assertion}")

    # 追加の実操作・実アサーション。クローラの実測データ（field / screen_index）が
    # 揃っている場合のみ発動し、揃っていない候補（旧フィクスチャ等）には影響しない。
    field = item.get("field")
    if field and title in ("フォーム入力", "必須入力"):
        _append_form_operations(lines, item, title, field)
    elif title == "画面遷移":
        _append_transition_assertion(lines, trace_id, screen_index)
    elif title == "画面表示スモーク":
        _append_smoke_assertion(lines, trace_id, screen_index)

    lines.append("});")
    lines.append("")


# ------------------------------------------------------------------
# 実操作・実アサーション生成
#
# 従来はコメント（"// `date` を空にする" 等）を出力するだけで、実際の
# fill/click/selectOption は一切生成しておらず、アサーションも
# expect(page.locator('body')).toBeVisible() の1種類に固定されていた。
# その結果、対象サイトを完全に破壊してもテストが全件PASSする
# （ミューテーションスコア0%）ことが監査で判明した。
#
# 以下は、クローラが実測した field_type / locators / options / 必須有無
# を使い、実際に値を入力・選択し、ブラウザの Constraint Validation API
# （checkValidity）で合否を判定する。エラーメッセージの文言に依存しない
# ため、サイトの表示文言が変わっても壊れにくい。
# ------------------------------------------------------------------


def _append_form_operations(
    lines: list[str],
    item: dict[str, Any],
    title: str,
    field: dict[str, Any],
) -> None:
    siblings: list[dict[str, Any]] = item.get("required_siblings") or []
    form_action = _safe_str(item.get("form_action", ""))
    form_selector = f'form[action="{_esc(form_action)}"]' if form_action else ""
    # 日付フィールドの表記（MM/DD/YYYY か YYYY/MM/DD か）はサイトのロケールで異なる
    # （実サイト検証で確認：/en-US/ は MM/DD/YYYY、/ja/ は YYYY/MM/DD）。
    # ISO形式で入力すると blur 時にサイト側の customValidity で弾かれるため、
    # 候補が属する画面URLからロケールを推定する。
    page_url = _extract_url(item.get("steps") or [])
    date_format = _date_format_for_url(page_url)

    lines.append(
        "  // 他の必須項目には代表値を入れ、対象項目だけを検証対象にする"
        if siblings
        else "  // このフォームには他に必須項目が無い"
    )
    for sib in siblings:
        _append_fill_statement(lines, sib, _representative_value(sib, date_format), indent="  ")

    field_locator = _field_locator_expr(field)
    if title == "フォーム入力":
        value = _representative_value(field, date_format)
        lines.append(f"  // `{_esc(_field_label(field))}` に代表値を入力")
        _append_fill_statement(lines, field, value, indent="  ")
        if form_selector:
            lines.append(
                f"  const formValid = await page.locator('{form_selector}')"
                ".evaluate((f) => (f as HTMLFormElement).checkValidity());"
            )
            lines.append("  expect(formValid).toBe(true);")
        else:
            lines.append(
                f"  const fieldValid = await {field_locator}"
                ".evaluate((el) => (el as HTMLInputElement).checkValidity());"
            )
            lines.append("  expect(fieldValid).toBe(true);")
    else:  # 必須入力
        lines.append(f"  // `{_esc(_field_label(field))}` を空にする")
        _append_clear_statement(lines, field, indent="  ")
        lines.append(
            f"  const fieldValid = await {field_locator}"
            ".evaluate((el) => (el as HTMLInputElement).checkValidity());"
        )
        lines.append("  expect(fieldValid).toBe(false);")
        if form_selector:
            lines.append(
                f"  const formValid = await page.locator('{form_selector}')"
                ".evaluate((f) => (f as HTMLFormElement).checkValidity());"
            )
            lines.append("  expect(formValid).toBe(false);")


def _append_transition_assertion(
    lines: list[str],
    trace_id: str,
    screen_index: dict[str, dict[str, str]],
) -> None:
    """遷移先へ実際に移動し、実在する画面であることをタイトルで確認する。

    注意（既知の限界）: リンク要素のセレクタをクローラが保存していないため、
    実際にリンクをクリックする経路検証はできない。ここでは遷移先URLへの
    直接遷移＋タイトル確認に留める。壊れたレスポンス（タイトル無し）は検出できる。
    """
    dest_id = trace_id.split("->")[-1] if "->" in trace_id else ""
    dest = screen_index.get(dest_id, {})
    dest_url = dest.get("url", "")
    dest_title = dest.get("title", "")
    if not dest_url:
        return  # 遷移先の実測データが無い場合はベースラインの可視性チェックのみとする
    lines.append(f"  await page.goto('{_esc(dest_url)}');")
    lines.append("  await page.waitForLoadState('domcontentloaded');")
    lines.append("  const title = await page.title();")
    lines.append("  expect(title.length).toBeGreaterThan(0);")
    if dest_title:
        snippet = dest_title[:20]
        lines.append(f"  expect(title).toContain('{_esc(snippet)}');")


def _append_smoke_assertion(
    lines: list[str],
    trace_id: str,
    screen_index: dict[str, dict[str, str]],
) -> None:
    page_id = _page_id_from_trace(trace_id)
    info = screen_index.get(page_id, {})
    expected_title = info.get("title", "")
    if not expected_title:
        return  # 実測タイトルが無い場合はベースラインの可視性チェックのみとする
    lines.append("  const title = await page.title();")
    lines.append("  expect(title.length).toBeGreaterThan(0);")
    snippet = expected_title[:20]
    lines.append(f"  expect(title).toContain('{_esc(snippet)}');")


def _field_label(field: dict[str, Any]) -> str:
    return _safe_str(field.get("name")) or "unnamed"


def _field_locator_expr(field: dict[str, Any]) -> str:
    locators: list[str] = field.get("locators") or []
    primary = locators[0] if locators else f"[name=\"{field.get('name', '')}\"]"
    return f"page.locator('{_esc(primary)}')"


def _date_format_for_url(url: str) -> str:
    """URLのロケールパスから日付表記を推定する（実サイト検証で確認した既知パターン）。"""
    if "/en-US/" in url or "/en/" in url:
        return "mdy_slash"  # MM/DD/YYYY
    if "/ja/" in url:
        return "ymd_slash"  # YYYY/MM/DD
    return "iso"  # YYYY-MM-DD（既定のフォールバック）


def _date_expr(date_format: str) -> str:
    """実行時に「今日+14日」を計算するJS式を、指定表記の文字列として返す。

    固定の未来日付を埋め込むと「予約は3か月以内のみ」等の業務ルールで実行日により
    失敗する（実サイト検証で確認済み）ため、常に実行時計算にする。
    """
    if date_format == "mdy_slash":
        body = (
            "(() => { const d = new Date(Date.now() + 14 * 86400000);"
            " return `${String(d.getMonth() + 1).padStart(2, '0')}/"
            "${String(d.getDate()).padStart(2, '0')}/${d.getFullYear()}`; })()"
        )
    elif date_format == "ymd_slash":
        body = (
            "(() => { const d = new Date(Date.now() + 14 * 86400000);"
            " return `${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, '0')}/"
            "${String(d.getDate()).padStart(2, '0')}`; })()"
        )
    else:
        body = "new Date(Date.now() + 14 * 86400000).toISOString().slice(0, 10)"
    return f"{_JS_EXPR_PREFIX}{body}"


def _representative_value(field: dict[str, Any], date_format: str = "iso") -> str:
    """field_type に応じた、境界を侵さない代表値を返す（select は選択肢そのものを返す）。"""
    field_type = _safe_str(field.get("field_type", "text"))
    if field_type == "email":
        return "webspec2doc-qa@example.com"
    if field_type == "tel":
        return "0312345678"
    if field_type == "number":
        min_v = _safe_str(field.get("min_value"))
        max_v = _safe_str(field.get("max_value"))
        if min_v:
            return min_v
        if max_v:
            return max_v
        return "1"
    if field_type == "date" or (field_type == "text" and _looks_like_date_field(field)):
        return _date_expr(date_format)
    if field_type == "select":
        options: list[str] = [str(o) for o in (field.get("options") or [])]
        for option in options:
            if option and not _looks_like_placeholder(option):
                return option
        return options[0] if options else ""
    if field_type in ("textarea",):
        return "WebSpec2Doc 自動生成テスト入力"
    return "WebSpec2Doc-QA"


def _looks_like_date_field(field: dict[str, Any]) -> bool:
    name = _safe_str(field.get("name")).lower()
    return "date" in name


def _looks_like_placeholder(option: str) -> bool:
    lowered = option.strip().lower()
    return lowered in ("", "choose one", "please select") or "選択" in option


def _append_fill_statement(
    lines: list[str], field: dict[str, Any], value: str, indent: str
) -> None:
    field_type = _safe_str(field.get("field_type", "text"))
    locator_expr = _field_locator_expr(field)
    if field_type == "hidden":
        return
    # 他の項目（例: 連絡方法の選択）に応じて disabled になる条件付きフィールドが
    # 実サイト検証で見つかった（email/tel は contact 選択に連動）。disabled な項目は
    # ブラウザの制約検証からも除外されるため、有効なときだけ操作すれば安全に対応できる。
    guard = f"await {locator_expr}.isEnabled().catch(() => false)"
    lines.append(f"{indent}if ({guard}) {{")
    inner = indent + "  "
    if field_type == "select":
        lines.append(f"{inner}await {locator_expr}.selectOption('{_esc(value)}');")
    elif field_type in ("checkbox", "radio"):
        lines.append(f"{inner}await {locator_expr}.check();")
    elif value.startswith(_JS_EXPR_PREFIX):
        # 実行時に評価する JS 式（例: 相対日付）。固定の未来日付を埋め込むと、
        # 実行日によって「予約可能期間外」等の業務ルールで失敗するため。
        date_expr = value[len(_JS_EXPR_PREFIX) :]
        # jQuery UI 等の datepicker が既定値（例: 今日の日付）を先に入れていることがあり、
        # fill() が新旧の値を連結してしまう競合が実サイト検証で低頻度（335件中3件）に
        # 再現した。先に空にしてから入れることで解消する。
        lines.append(f"{inner}await {locator_expr}.fill('');")
        lines.append(f"{inner}await {locator_expr}.fill({date_expr});")
        # datepicker はフォーカスで開き、以降の要素へのクリックを遮ることも判明した。
        # body への強制クリックでフォーカスを外し、ポップアップを閉じる。
        lines.append(
            f"{inner}await page.locator('body').click({{ position: {{ x: 2, y: 2 }}, force: true }});"
        )
    else:
        lines.append(f"{inner}await {locator_expr}.fill('{_esc(value)}');")
    lines.append(f"{indent}}}")


def _append_clear_statement(lines: list[str], field: dict[str, Any], indent: str) -> None:
    field_type = _safe_str(field.get("field_type", "text"))
    locator_expr = _field_locator_expr(field)
    if field_type == "select":
        options: list[str] = [str(o) for o in (field.get("options") or [])]
        placeholder = next((o for o in options if _looks_like_placeholder(o)), "")
        if placeholder:
            lines.append(f"{indent}await {locator_expr}.selectOption('{_esc(placeholder)}');")
        else:
            lines.append(f"{indent}await {locator_expr}.selectOption({{ index: 0 }});")
    elif field_type in ("checkbox", "radio"):
        lines.append(f"{indent}await {locator_expr}.uncheck().catch(() => {{}});")
    else:
        lines.append(f"{indent}await {locator_expr}.fill('');")


def _generate_strong_assertions(expected: str) -> list[str]:
    """expected フィールドから強化アサーション文字列のリストを返す。"""
    assertions: list[str] = []
    if "エラー" in expected:
        assertions.append(_generate_validation_message_assertion(expected))
    url_like = re.search(r"(https?://[^\s]+|/[^\s]*)", expected)
    if url_like:
        assertions.append(_generate_url_assertion(url_like.group(1)))
    return assertions


def _build_resilient_locator(locators: list[str]) -> str:
    """複数ロケータ候補を Playwright の first() チェーンで表現。
    最も具体的な候補（data-testid, aria-label, type= など）を先頭に並べる。"""
    sorted_locs = _sort_locators_by_reliability(locators)
    combined = ", ".join(sorted_locs)
    return f"page.locator('{_esc(combined)}').first()"


def _build_role_based_locator(
    locators: list[str],
    field_name: str = "",
    aria_label: str = "",
    field_type: str = "text",
) -> str:
    """ラベルと入力種別を使い、保守しやすいロケータを優先生成する。"""
    label = aria_label or field_name
    if aria_label:
        return f"page.getByLabel('{_esc(aria_label)}')"

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
        name_part = f", {{ name: '{_esc(label)}' }}" if label else ""
        return f"page.getByRole('{role}'{name_part})"
    if label:
        return f"page.getByLabel('{_esc(label)}')"
    return _build_resilient_locator(locators)


def _sort_locators_by_reliability(locators: list[str]) -> list[str]:
    """ロケータ候補を信頼度順にソートする。

    優先度:
      1. data-testid を含む
      2. aria-label を含む
      3. type= を含む
      4. # で始まる（ID セレクタ）
      5. その他
    """

    def _priority(loc: str) -> int:
        if "data-testid" in loc:
            return 0
        if "aria-label" in loc:
            return 1
        if "type=" in loc:
            return 2
        if loc.strip().startswith("#"):
            return 3
        return 4

    return sorted(locators, key=_priority)


def _generate_url_assertion(expected_url: str) -> str:
    """URL アサーション文字列を返す。"""
    return f"await expect(page).toHaveURL('{_esc(expected_url)}');"


def _generate_validation_message_assertion(error_text: str) -> str:
    """バリデーションメッセージ表示アサーション文字列を返す。"""
    _ = error_text  # 将来の拡張のため受け取る（現在は固定セレクタ）
    return (
        "await expect("
        'page.locator(\'[role="alert"], .error-message, [aria-live="polite"]\').first()'
        ").toBeVisible();"
    )


def _generate_form_submit_assertion(expected_url_fragment: str) -> str:
    """フォーム送信後の URL パターンアサーション文字列を返す。"""
    return f"await expect(page).toHaveURL(/{_esc(expected_url_fragment)}/);"


def compute_filter_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    """各フィルターモードでの件数を返す。"""
    return {
        "all": len(candidates),
        "smoke": sum(1 for c in candidates if c.get("title") in SMOKE_TITLES),
        "transition": sum(1 for c in candidates if c.get("title") in TRANSITION_TITLES),
        "form": sum(1 for c in candidates if c.get("title") in FORM_TITLES),
    }


def _apply_filter(candidates: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    if mode == "smoke":
        return [c for c in candidates if c.get("title") in SMOKE_TITLES]
    if mode == "transition":
        return [c for c in candidates if c.get("title") in TRANSITION_TITLES]
    if mode == "form":
        return [c for c in candidates if c.get("title") in FORM_TITLES]
    return candidates  # "all"


def _extract_url(steps: list[Any]) -> str:
    for step in steps:
        m = re.search(r"page\.goto\(['\"]([^'\"]+)['\"]\)", str(step))
        if m:
            return m.group(1)
    return ""


def _safe_str(value: object) -> str:
    return str(value) if value is not None else ""


def _esc(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def _generate_page_object(
    domain: str,
    candidates: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """候補をURL単位でまとめたPlaywright Page Objectを生成する。"""
    url_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        steps: list[Any] = candidate.get("steps") or []
        url_groups[_extract_url(steps) or "unknown"].append(candidate)

    lines = [
        "import { Page } from '@playwright/test';",
        "",
        f"// Page Object generated by WebSpec2Doc - {domain}",
        "",
    ]
    for url, items in url_groups.items():
        lines.append(f"export class {_url_to_class_name(url)} {{")
        lines.append("  readonly page: Page;")
        lines.append("  constructor(page: Page) { this.page = page; }")
        lines.append("")
        if url != "unknown":
            lines.append(f"  async goto() {{ await this.page.goto('{_esc(url)}'); }}")
            lines.append("")

        seen_getters: set[str] = set()
        for candidate in items:
            for raw_locator in candidate.get("locators") or []:
                getter_name = _locator_to_getter_name(str(raw_locator))
                if getter_name and getter_name not in seen_getters:
                    seen_getters.add(getter_name)
                    locator = _raw_locator_to_playwright(str(raw_locator))
                    lines.append(f"  get {getter_name}() {{ return {locator}; }}")
        lines.append("}")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def _url_to_class_name(url: str) -> str:
    """URLパス末尾をPage Objectのクラス名に変換する。"""
    if url == "unknown":
        return "UnknownPage"
    path = urlparse(url).path.rstrip("/")
    segment = path.rsplit("/", 1)[-1] if path else "Index"
    words = re.split(r"[-_.]", segment)
    name = "".join(word.capitalize() for word in words if word) or "Index"
    return f"{name}Page"


def _locator_to_getter_name(raw_locator: str) -> str:
    """CSSセレクタからPage Object getter名を生成する。"""
    stripped = raw_locator.strip()
    id_match = re.match(r"^#(.+)$", stripped)
    if id_match:
        return f"{_camel(id_match.group(1))}Input"
    name_match = re.search(r'\[name=["\']([^"\']+)["\']', stripped)
    if name_match:
        return f"{_camel(name_match.group(1))}Input"
    test_id_match = re.search(r'data-testid=["\']([^"\']+)["\']', stripped)
    if test_id_match:
        return f"{_camel(test_id_match.group(1))}Button"
    return ""


def _camel(value: str) -> str:
    """snake-case / kebab-caseをcamelCaseへ変換する。"""
    parts = [part for part in re.split(r"[-_\s]+", value) if part]
    if not parts:
        return ""
    return parts[0].lower() + "".join(part.capitalize() for part in parts[1:])


def _raw_locator_to_playwright(raw_locator: str) -> str:
    """CSSセレクタをPage Object内のPlaywrightロケータ式へ変換する。"""
    aria_match = re.search(r'aria-label=["\']([^"\']+)["\']', raw_locator)
    if aria_match:
        return f"this.page.getByLabel('{_esc(aria_match.group(1))}')"
    test_id_match = re.search(r'data-testid=["\']([^"\']+)["\']', raw_locator)
    if test_id_match:
        return f"this.page.getByTestId('{_esc(test_id_match.group(1))}')"
    return f"this.page.locator('{_esc(raw_locator)}')"
