"""テストケース表 → Playwright .spec.ts の変換。

表の各行が持つ actions / assertions（構造化された操作と検証）だけを読む。
日本語の手順文は人が読むためのもので、人が編集しても実行内容は変わらない。

検証は「文言に依存しない観測可能な事実」に絞る:
    - 画面表示 : タイトル・見出しの可視性
    - 遷移     : 遷移後 URL
    - 有効値   : 送信後にエラー表示が出ていないこと
    - 無効値   : 送信されず同じ URL に留まること
エラーメッセージの文面は実装依存のため、一致判定に使わない（誤 FAIL を避ける）。
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from web.services.egress_gateway import EGRESS_FIXTURE_NAME

# エラー表示の検出に使う汎用セレクタ。サイト固有のクラス名には依存しない。
_ERROR_SELECTOR = (
    '[role="alert"], .error, .errors, .is-error, .error-message, '
    ".invalid-feedback, .field-error, .form-error"
)

SPEC_FILE_NAME = "testcases.spec.ts"
METADATA_FILE_NAME = "testcases.spec.meta.json"


class SpecGenerationError(ValueError):
    """実行可能なケースが 1 件も無い等、spec を作れない場合に送出する。"""


def _ts(value: Any) -> str:
    """TypeScript のリテラルとして安全な文字列にする。"""
    return json.dumps(str(value), ensure_ascii=False)


def _title(row: Mapping[str, Any]) -> str:
    return f"{row.get('case_id', '')} {row.get('name', '')}".strip()


def is_executable(row: Mapping[str, Any]) -> bool:
    """自動実行の対象か。自動化判定が「自動化可」で、操作と検証が揃っている行のみ。"""
    if str(row.get("automation") or "") != "自動化可":
        return False
    if not row.get("actions"):
        return False
    return bool(row.get("assertions"))


def _href_suffix(url: str) -> str:
    """リンク特定用に URL の末尾（ファイル名＋クエリ）を取り出す。"""
    path = re.sub(r"^https?://[^/]+", "", str(url))
    return path.split("/")[-1] or path or ""


def _action_lines(action: Mapping[str, Any]) -> list[str]:
    kind = str(action.get("type") or "")
    locator = str(action.get("locator") or "")

    if kind == "goto":
        return [
            f"  await page.goto({_ts(action.get('url'))}, " "{ waitUntil: 'domcontentloaded' });"
        ]
    if kind == "wait_load":
        return ["  await page.waitForLoadState('domcontentloaded');"]
    if kind == "fill" and locator:
        return [f"  await page.locator({_ts(locator)}).fill({_ts(action.get('value'))});"]
    if kind == "clear" and locator:
        return [f"  await page.locator({_ts(locator)}).fill('');"]
    if kind == "select" and locator:
        # value 一致が無い環境ではラベル一致にフォールバックする
        value = _ts(action.get("value"))
        return [
            f"  await selectByValueOrLabel(page, {_ts(locator)}, {value});",
        ]
    if kind == "click_text":
        return [f"  await clickByLabel(page, {_ts(action.get('text'))});"]
    if kind == "click_link_to":
        suffix = _href_suffix(action.get("url") or "")
        return [
            f"  await clickLinkTo(page, {_ts(suffix)}, {_ts(action.get('title') or '')});",
        ]
    # 未対応の操作は実行しない（黙って飛ばさず、記録を残す）
    return [f"  // 未対応の操作のためスキップ: {json.dumps(dict(action), ensure_ascii=False)}"]


def _assertion_lines(assertion: Mapping[str, Any]) -> list[str]:
    kind = str(assertion.get("type") or "")
    if kind == "expect_title":
        return [f"  expect(await page.title()).toContain({_ts(assertion.get('value'))});"]
    if kind == "expect_text":
        return [
            f"  await expect(page.getByText({_ts(assertion.get('value'))}, "
            "{ exact: false }).first()).toBeVisible();"
        ]
    if kind == "expect_url":
        return [f"  await expect(page).toHaveURL({_ts(assertion.get('value'))});"]
    if kind == "expect_no_error":
        return ["  await expectNoErrorShown(page);"]
    if kind == "expect_stay":
        return [f"  await expectNotSubmitted(page, {_ts(assertion.get('url'))});"]
    if kind == "expect_no_server_error":
        return ["  await expectNoServerError(page);"]
    if kind == "expect_value_length":
        return [
            f"  await expectValueLength(page, {_ts(assertion.get('locator'))}, "
            f"{int(assertion.get('max') or 0)});"
        ]
    return [f"  // 未対応の検証のためスキップ: {json.dumps(dict(assertion), ensure_ascii=False)}"]


_HELPERS = f"""
const ERROR_SELECTOR = {_ts(_ERROR_SELECTOR)};

// 値一致で選択できないときはラベル一致で選ぶ（表示文言と value がずれる実装に対応）
async function selectByValueOrLabel(page, selector: string, value: string) {{
  const el = page.locator(selector);
  try {{
    await el.selectOption(value);
  }} catch (e) {{
    await el.selectOption({{ label: value }});
  }}
}}

// ボタン → 同名の submit → テキスト一致の順で押す
async function clickByLabel(page, label: string) {{
  const byRole = page.getByRole('button', {{ name: label }}).first();
  if (await byRole.count()) {{ await byRole.click(); return; }}
  const bySubmit = page.locator(`input[type=submit][value="${{label}}"]`).first();
  if (await bySubmit.count()) {{ await bySubmit.click(); return; }}
  await page.getByText(label, {{ exact: false }}).first().click();
}}

// 遷移先の URL 末尾を持つリンク、無ければ画面名のリンクを押す
async function clickLinkTo(page, hrefSuffix: string, title: string) {{
  if (hrefSuffix) {{
    const byHref = page.locator(`a[href$="${{hrefSuffix}}"]`).first();
    if (await byHref.count()) {{ await byHref.click(); return; }}
  }}
  await page.getByRole('link', {{ name: title }}).first().click();
}}

// エラー表示が出ていないこと（文面は実装依存なので「表示の有無」だけを見る）
async function expectNoErrorShown(page) {{
  const errors = page.locator(ERROR_SELECTOR);
  const total = await errors.count();
  for (let i = 0; i < total; i++) {{
    if (await errors.nth(i).isVisible()) {{
      throw new Error('エラー表示が出ています: ' + (await errors.nth(i).innerText()));
    }}
  }}
}}

// 送信されず同じ画面に留まること（HTML5 バリデーション・サーバ側拒否の両方をカバー）
async function expectNotSubmitted(page, url: string) {{
  const current = page.url().split('#')[0];
  const expected = url.split('#')[0];
  if (current !== expected) {{
    throw new Error('送信されてしまいました（URL が ' + current + ' に変化）');
  }}
}}

// 上限超過の入力が maxlength で切られること（ブラウザ側で入力が制限される仕様）
async function expectValueLength(page, selector: string, max: number) {{
  const value = await page.locator(selector).inputValue();
  if (value.length > max) {{
    throw new Error('入力が制限されていません（' + value.length + ' 文字が入りました。上限 ' + max + '）');
  }}
}}

async function expectNoServerError(page) {{
  const body = (await page.locator('body').innerText()).slice(0, 4000);
  for (const marker of ['Internal Server Error', '500 Internal', 'Traceback (most recent call last)']) {{
    if (body.includes(marker)) throw new Error('サーバエラーが表示されています: ' + marker);
  }}
}}
"""


def generate_spec(rows: Sequence[Mapping[str, Any]], out_dir: Path) -> dict[str, Any]:
    """実行可能な行から spec.ts を生成する。戻り値は spec パスと対応表。"""
    targets = [r for r in rows if is_executable(r)]
    if not targets:
        raise SpecGenerationError(
            "自動実行できるテストケースがありません（自動化判定が『自動化可』の行が必要です）"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    fixture_import = f"./{EGRESS_FIXTURE_NAME.removesuffix('.ts')}"
    lines: list[str] = [
        "// 自動生成 — テストケース表（9列）から生成。手で編集しても再生成で上書きされます。",
        f"import {{ test, expect }} from {_ts(fixture_import)};",
        _HELPERS,
    ]
    mapping: list[dict[str, str]] = []
    for row in targets:
        title = _title(row)
        mapping.append({"test_title": title, "case_id": str(row.get("case_id", ""))})
        lines.append("")
        assertions = list(row.get("assertions") or [])
        after_input = [a for a in assertions if a.get("stage") == "after_input"]
        at_end = [a for a in assertions if a.get("stage") != "after_input"]
        lines.append(f"test({_ts(title)}, async ({{ page }}) => {{")
        emitted_after_input = False
        for action in row.get("actions") or []:
            # 送信を押す前に「入力がどうなったか」を見る検証を差し込む
            if after_input and not emitted_after_input and action.get("type") == "click_text":
                for assertion in after_input:
                    lines.extend(_assertion_lines(assertion))
                emitted_after_input = True
            lines.extend(_action_lines(action))
        if after_input and not emitted_after_input:
            for assertion in after_input:
                lines.extend(_assertion_lines(assertion))
        for assertion in at_end:
            lines.extend(_assertion_lines(assertion))
        lines.append("});")

    spec_path = out_dir / SPEC_FILE_NAME
    spec_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    meta_path = out_dir / METADATA_FILE_NAME
    meta_path.write_text(
        json.dumps({"tests": mapping}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "spec_path": str(spec_path),
        "meta_path": str(meta_path),
        "test_count": len(targets),
        "skipped_count": len(rows) - len(targets),
    }
