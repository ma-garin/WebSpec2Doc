"""テストステップの正本（ノーコード編集用）。

コードを書かずにテストを直せるようにするには、編集の正本が「生成された .spec.ts」
であってはならない。生成物を直接編集すると、再生成のたびに編集が消える。
ここでは編集可能なステップ列を正本として持ち、spec.ts は常にここから生成する。

    クローラの候補 → （初回だけ）ステップへ取り込み → 人が編集 → spec.ts を生成

保存先: output/<domain>/qa_process/test_steps.json

ステップの語彙は「画面でやること」に閉じる。CSS セレクタや Playwright API を
知らなくても、動作の種類と対象と値だけで組めるようにする。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

STORE_RELATIVE = "qa_process/test_steps.json"
SCHEMA_VERSION = 1

# 動作の語彙。key: (表示名, 対象が要るか, 値が要るか)
ACTIONS: dict[str, dict[str, Any]] = {
    "goto": {"label": "画面を開く", "needs_target": False, "needs_value": True},
    "click": {"label": "クリックする", "needs_target": True, "needs_value": False},
    "fill": {"label": "入力する", "needs_target": True, "needs_value": True},
    "select": {"label": "選択する", "needs_target": True, "needs_value": True},
    "check": {"label": "チェックを入れる", "needs_target": True, "needs_value": False},
    "uncheck": {"label": "チェックを外す", "needs_target": True, "needs_value": False},
    "press": {"label": "キーを押す", "needs_target": True, "needs_value": True},
    "wait_text": {"label": "文字が出るまで待つ", "needs_target": False, "needs_value": True},
    "expect_text": {"label": "文字があることを確認", "needs_target": False, "needs_value": True},
    "expect_visible": {"label": "表示されていることを確認", "needs_target": True, "needs_value": False},
    "expect_url": {"label": "URL を確認", "needs_target": False, "needs_value": True},
    "expect_screenshot": {"label": "見た目を基準と比較", "needs_target": False, "needs_value": True},
}

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class StepValidationError(ValueError):
    """ステップが保存できない形をしている。どこが悪いかを必ず名指しする。"""


# --------------------------------------------------------------------------
# 保存・読み込み
# --------------------------------------------------------------------------
def store_path(output_root: Path, domain: str) -> Path:
    return output_root / domain / STORE_RELATIVE


def empty_document(domain: str) -> dict[str, Any]:
    return {"version": SCHEMA_VERSION, "domain": domain, "tests": []}


def load(output_root: Path, domain: str) -> dict[str, Any]:
    path = store_path(output_root, domain)
    if not path.is_file():
        return empty_document(domain)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # 壊れたファイルを空として黙って上書きすると、編集内容が消える。
        # 読めないことを呼び出し側へ伝える。
        raise StepValidationError(
            f"{path} を読めません。ファイルが壊れている可能性があります。"
        ) from None
    if not isinstance(data, dict) or "tests" not in data:
        raise StepValidationError(f"{path} の形式が想定と違います。")
    data.setdefault("version", SCHEMA_VERSION)
    data.setdefault("domain", domain)
    return data


def save(output_root: Path, domain: str, document: dict[str, Any]) -> Path:
    normalized = validate(document, domain)
    path = store_path(output_root, domain)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


# --------------------------------------------------------------------------
# 検証
# --------------------------------------------------------------------------
def validate(document: Any, domain: str) -> dict[str, Any]:
    """保存前の検証。壊れた入力はどこが悪いか名指しして落とす。

    黙って既定値へ倒すと、それらしい spec が生成されて利用者が気づけない。
    """
    if not isinstance(document, dict):
        raise StepValidationError("本体がオブジェクトではありません。")
    tests = document.get("tests")
    if not isinstance(tests, list):
        raise StepValidationError("tests は配列である必要があります。")

    seen_ids: set[str] = set()
    normalized_tests: list[dict[str, Any]] = []
    for i, test in enumerate(tests):
        where = f"tests[{i}]"
        if not isinstance(test, dict):
            raise StepValidationError(f"{where} がオブジェクトではありません。")
        test_id = str(test.get("test_id", "")).strip()
        if not _ID_RE.match(test_id):
            raise StepValidationError(
                f"{where}.test_id が不正です（英数字・ハイフン・アンダースコア 1〜64 文字）: {test_id!r}"
            )
        if test_id in seen_ids:
            raise StepValidationError(f"test_id が重複しています: {test_id}")
        seen_ids.add(test_id)

        title = str(test.get("title", "")).strip()
        if not title:
            raise StepValidationError(f"{where}.title が空です。")

        steps = test.get("steps")
        if not isinstance(steps, list) or not steps:
            raise StepValidationError(f"{where}.steps が空です（1 つ以上必要）。")

        normalized_steps = [
            _validate_step(step, f"{where}.steps[{j}]") for j, step in enumerate(steps)
        ]
        normalized_tests.append(
            {
                "test_id": test_id,
                "title": title,
                "enabled": bool(test.get("enabled", True)),
                "note": str(test.get("note", ""))[:500],
                "steps": normalized_steps,
            }
        )

    return {
        "version": SCHEMA_VERSION,
        "domain": domain,
        "tests": normalized_tests,
    }


def _validate_step(step: Any, where: str) -> dict[str, Any]:
    if not isinstance(step, dict):
        raise StepValidationError(f"{where} がオブジェクトではありません。")
    action = str(step.get("action", "")).strip()
    spec = ACTIONS.get(action)
    if spec is None:
        raise StepValidationError(
            f"{where}.action が不明です: {action!r}（使えるのは {', '.join(sorted(ACTIONS))}）"
        )

    targets = step.get("target") or []
    if isinstance(targets, str):
        targets = [targets]
    if not isinstance(targets, list):
        raise StepValidationError(f"{where}.target は文字列か配列である必要があります。")
    targets = [str(x).strip() for x in targets if str(x).strip()]

    value = step.get("value", "")
    value = "" if value is None else str(value)

    if spec["needs_target"] and not targets:
        raise StepValidationError(
            f"{where}: 「{spec['label']}」には対象の指定が要ります。"
        )
    if spec["needs_value"] and not value:
        raise StepValidationError(
            f"{where}: 「{spec['label']}」には値の指定が要ります。"
        )
    if action == "goto" and not re.match(r"^https?://", value):
        raise StepValidationError(
            f"{where}: 「画面を開く」の値は http(s) の URL である必要があります: {value!r}"
        )

    return {
        "id": str(step.get("id", "")).strip() or f"s{abs(hash(where)) % 100000}",
        "action": action,
        "target": targets,
        "value": value,
        "label": str(step.get("label", ""))[:120],
        "note": str(step.get("note", ""))[:300],
    }


# --------------------------------------------------------------------------
# クローラ候補からの取り込み（白紙から始めさせない）
# --------------------------------------------------------------------------
def import_from_candidates(
    candidates: list[dict[str, Any]], domain: str, limit: int = 200
) -> dict[str, Any]:
    """playwright_candidates.json をステップ列へ落とす。

    白紙のエディタを出しても人は書けない。クローラが実測した画面・項目から
    叩き台を作り、そこを直してもらう形にする。
    """
    tests: list[dict[str, Any]] = []
    used: set[str] = set()
    for i, item in enumerate(candidates[:limit]):
        url = _first_goto_url(item)
        if not url:
            continue
        test_id = _unique_id(str(item.get("id") or item.get("trace_id") or f"t{i}"), used)
        steps: list[dict[str, Any]] = [
            {"id": "s1", "action": "goto", "target": [], "value": url, "label": "画面を開く", "note": ""}
        ]
        n = 2
        for field in _fields_of(item):
            action, value = _action_for_field(field)
            if action is None:
                continue
            steps.append(
                {
                    "id": f"s{n}",
                    "action": action,
                    "target": [str(x) for x in (field.get("locators") or []) if str(x).strip()]
                    or [f'[name="{field.get("name", "")}"]'],
                    "value": value,
                    "label": str(field.get("name", "")),
                    "note": "",
                }
            )
            n += 1
        expected = str(item.get("expected", "")).strip()
        if expected:
            steps.append(
                {"id": f"s{n}", "action": "expect_text", "target": [], "value": expected[:120],
                 "label": "期待結果", "note": "クローラの実測から取り込み"}
            )
        tests.append(
            {
                "test_id": test_id,
                "title": str(item.get("title", "")).strip() or f"テスト {i + 1}",
                "enabled": True,
                "note": "クローラの候補から取り込み。必要に応じて編集してください。",
                "steps": steps,
            }
        )
    return {"version": SCHEMA_VERSION, "domain": domain, "tests": tests}


def _unique_id(base: str, used: set[str]) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", base)[:56] or "t"
    candidate = cleaned
    n = 2
    while candidate in used:
        candidate = f"{cleaned}_{n}"
        n += 1
    used.add(candidate)
    return candidate


def _first_goto_url(item: dict[str, Any]) -> str:
    url = str(item.get("url", "")).strip()
    if url.startswith("http"):
        return url
    for step in item.get("steps") or []:
        match = re.search(r"page\.goto\(['\"]([^'\"]+)['\"]\)", str(step))
        if match:
            return match.group(1)
    return ""


def _fields_of(item: dict[str, Any]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for sibling in item.get("required_siblings") or []:
        if isinstance(sibling, dict):
            fields.append(sibling)
    field = item.get("field")
    if isinstance(field, dict):
        fields.append(field)
    return fields


def _action_for_field(field: dict[str, Any]) -> tuple[str | None, str]:
    field_type = str(field.get("field_type", "text"))
    if field_type == "hidden":
        return None, ""
    if field_type == "select":
        options = [str(o) for o in (field.get("options") or []) if str(o).strip()]
        return "select", options[-1] if options else ""
    if field_type in ("checkbox", "radio"):
        return "check", ""
    return "fill", "WebSpec2Doc-QA"


# --------------------------------------------------------------------------
# ステップ → spec.ts
# --------------------------------------------------------------------------
def _esc(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")


def to_spec_ts(
    document: dict[str, Any],
    *,
    self_healing: bool = True,
    egress_gateway: bool = True,
) -> str:
    """ステップ列から Playwright の spec を組み立てる。

    生成物は毎回ここから作り直す。生成物側を直しても次の生成で消えるため、
    「編集の正本はステップ」という関係を崩さない。
    """
    lines: list[str] = [
        "import { test, expect } from "
        + ("'./_autorun_egress';" if egress_gateway else "'@playwright/test';"),
        "",
        f"// ステップ編集（ノーコード）から生成 — {document.get('domain', '')}",
        f"// テスト数: {len([t for t in document.get('tests', []) if t.get('enabled', True)])}",
        "// このファイルは編集しない。編集は test_steps.json（ステップ編集画面）で行う。",
        "",
    ]
    if self_healing:
        lines += _heal_runtime()

    for test in document.get("tests", []):
        if not test.get("enabled", True):
            lines.append(f"// 無効: {test.get('title', '')}")
            continue
        lines.append(f"test('{_esc(test['title'])} [{_esc(test['test_id'])}]', async ({{ page }}) => {{")
        for step in test.get("steps", []):
            lines += _emit_step(step, self_healing)
        lines.append("});")
        lines.append("")
    return "\n".join(lines)


def _heal_runtime() -> list[str]:
    """自己修復ロケータ。候補を順に試し、最初に実在したものを使う。"""
    return [
        "// 候補を順に試す。第1候補が変わってもテストを落とさないため。",
        "async function heal(page, candidates) {",
        "  for (let i = 0; i < candidates.length; i++) {",
        "    const loc = page.locator(candidates[i]).first();",
        "    const found = await loc.count().then((c) => c > 0).catch(() => false);",
        "    if (found) return loc;",
        "  }",
        "  return page.locator(candidates[0]).first();",
        "}",
        "",
    ]


def _emit_step(step: dict[str, Any], self_healing: bool) -> list[str]:
    action = step["action"]
    targets = step.get("target") or []
    value = step.get("value", "")
    label = step.get("label", "")
    out: list[str] = []
    head = f"  // {ACTIONS[action]['label']}"
    if label:
        head += f": {label}"
    out.append(head)

    if action == "goto":
        out.append(f"  await page.goto('{_esc(value)}');")
        out.append("  await page.waitForLoadState('domcontentloaded');")
        return out
    if action == "wait_text":
        out.append(f"  await page.getByText('{_esc(value)}').first().waitFor();")
        return out
    if action == "expect_text":
        out.append(f"  await expect(page.getByText('{_esc(value)}').first()).toBeVisible();")
        return out
    if action == "expect_url":
        out.append(f"  await expect(page).toHaveURL(/{_esc(value)}/);")
        return out
    if action == "expect_screenshot":
        out.append("  await page.waitForLoadState('networkidle').catch(() => {});")
        out.append(
            f"  await expect(page).toHaveScreenshot('{_esc(value)}.png', "
            "{ fullPage: true, animations: 'disabled' });"
        )
        return out

    # 対象を要する動作。候補が複数あるときだけ heal を通す。
    if self_healing and len(targets) > 1:
        arr = ", ".join(f"'{_esc(t)}'" for t in targets)
        out.append("  {")
        out.append(f"    const t = await heal(page, [{arr}]);")
        body, indent = "t", "    "
    else:
        body, indent = f"page.locator('{_esc(targets[0])}').first()", "  "

    if action == "click":
        out.append(f"{indent}await {body}.click();")
    elif action == "fill":
        out.append(f"{indent}await {body}.fill('{_esc(value)}');")
    elif action == "select":
        out.append(f"{indent}await {body}.selectOption('{_esc(value)}');")
    elif action == "check":
        out.append(f"{indent}await {body}.check();")
    elif action == "uncheck":
        out.append(f"{indent}await {body}.uncheck();")
    elif action == "press":
        out.append(f"{indent}await {body}.press('{_esc(value)}');")
    elif action == "expect_visible":
        out.append(f"{indent}await expect({body}).toBeVisible();")

    if indent == "    ":
        out.append("  }")
    return out
