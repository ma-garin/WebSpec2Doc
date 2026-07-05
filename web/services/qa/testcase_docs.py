"""ローレベルテストケース（前提/手順/期待結果）への決定的変換とHTMLレポート生成。

playwright_candidates.json の各候補（page.goto 等のコード行と日本語プローズが混在した
steps 配列）を、非エンジニアにも読めるレベルへ変換する。変換ルールに一致しない行は
そのまま返す（捏造しない）。
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

_StepRule = tuple[re.Pattern[str], Callable[[re.Match[str]], str]]

_STEP_RULES: tuple[_StepRule, ...] = (
    (
        re.compile(r"^page\.goto\(['\"](.+?)['\"]\)$"),
        lambda m: f"ブラウザで {m.group(1)} を開く",
    ),
    (
        re.compile(r"^page\.waitForLoadState\(['\"](.+?)['\"]\)$"),
        lambda m: "画面の読み込み完了を待つ",
    ),
    (
        re.compile(r"^page\.click\(['\"](.+?)['\"]\)$"),
        lambda m: f"「{m.group(1)}」をクリックする",
    ),
    (
        re.compile(r"^page\.fill\(['\"](.+?)['\"],\s*['\"](.*?)['\"]\)$"),
        lambda m: f"{m.group(1)} に「{m.group(2)}」を入力する",
    ),
    (
        re.compile(r"^page\.check\(['\"](.+?)['\"]\)$"),
        lambda m: f"{m.group(1)} をチェックする",
    ),
    (
        re.compile(r"^page\.selectOption\(['\"](.+?)['\"],\s*['\"](.*?)['\"]\)$"),
        lambda m: f"{m.group(1)} で「{m.group(2)}」を選択する",
    ),
    (
        re.compile(r"^page\.press\(['\"](.+?)['\"],\s*['\"](.*?)['\"]\)$"),
        lambda m: f"{m.group(1)} で {m.group(2)} キーを押す",
    ),
)


def translate_step(step: str) -> str:
    """コード行を決定的な正規表現テーブルで日本語手順文へ変換する。

    一致するルールが無ければ元の文字列をそのまま返す（既に日本語プローズの行はそのまま通す）。
    """
    text = str(step)
    for pattern, template in _STEP_RULES:
        match = pattern.match(text)
        if match:
            return template(match)
    return text


@dataclass(frozen=True)
class LowLevelCase:
    test_id: str
    title: str
    trace_id: str
    automation_status: str
    preconditions: tuple[str, ...]
    steps: tuple[str, ...]
    expected_result: str


def build_low_level_case(candidate: dict[str, Any]) -> LowLevelCase:
    """1件の playwright 候補をローレベルケース（前提/手順/期待結果）へ変換する。"""
    raw_steps = [str(step) for step in (candidate.get("steps") or [])]
    preconditions: list[str] = []
    action_steps: list[str] = []
    for raw in raw_steps:
        translated = translate_step(raw)
        if raw.startswith("page.goto("):
            preconditions.append(translated)
        else:
            action_steps.append(translated)
    return LowLevelCase(
        test_id=str(candidate.get("id", "")),
        title=str(candidate.get("title", "")),
        trace_id=str(candidate.get("trace_id", "")),
        automation_status=str(candidate.get("automation_status", "")),
        preconditions=tuple(preconditions) or ("（記録された前提条件なし）",),
        steps=tuple(action_steps) or ("（記録された手順なし）",),
        expected_result=str(candidate.get("expected", "")),
    )


def build_low_level_cases(candidates: list[dict[str, Any]]) -> list[LowLevelCase]:
    return [build_low_level_case(candidate) for candidate in candidates]


def generate_testcases_html(domain: str, cases: list[LowLevelCase], generated_at: str) -> str:
    """印刷対応・自己完結の日本語テストケースHTMLレポートを生成する。"""
    case_blocks = "".join(_case_block_html(case) for case in cases)
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><title>テストケース一覧 - {html.escape(domain)}</title>
<style>
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:28px;color:#111827;line-height:1.6}}
  .meta{{color:#64748b;margin-bottom:20px}}
  .case{{border:1px solid #e5e7eb;border-radius:8px;padding:16px 20px;margin:16px 0;break-inside:avoid}}
  .case h2{{margin:0 0 4px;font-size:15px}}
  .case .trace{{color:#64748b;font-size:12px;margin:0 0 10px}}
  .case dt{{font-weight:700;margin-top:10px;font-size:13px}}
  .case dd{{margin:4px 0 0}}
  .case ol{{margin:2px 0 0;padding-left:20px;font-size:13px}}
  .case dd p{{margin:2px 0 0;font-size:13px}}
  @media print {{ .case{{ page-break-inside: avoid; }} }}
</style></head>
<body>
<h1>テストケース一覧</h1>
<p class="meta">対象: {html.escape(domain)} / 生成日時: {html.escape(generated_at)} / 件数: {len(cases)}</p>
{case_blocks}
</body></html>"""


def _case_block_html(case: LowLevelCase) -> str:
    preconditions_html = "".join(f"<li>{html.escape(item)}</li>" for item in case.preconditions)
    steps_html = "".join(f"<li>{html.escape(item)}</li>" for item in case.steps)
    return f"""<section class="case">
  <h2>{html.escape(case.test_id)} {html.escape(case.title)}</h2>
  <p class="trace">Trace: {html.escape(case.trace_id)} ／ 状態: {html.escape(case.automation_status)}</p>
  <dl>
    <dt>前提条件</dt><dd><ol>{preconditions_html}</ol></dd>
    <dt>手順</dt><dd><ol>{steps_html}</ol></dd>
    <dt>期待結果</dt><dd><p>{html.escape(case.expected_result or "（記録なし）")}</p></dd>
  </dl>
</section>"""
