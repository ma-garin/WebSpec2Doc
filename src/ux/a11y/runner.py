"""自社 Accessibility チェッカーの実行器（カタログ全ルールを必ず 1 行ずつ結果に出す）。

- 未実装・解決できないルール・実行失敗・タイムアウトは NOT_EVALUATED（not_implemented）。PASS に数えない。
- スナップショット取得の失敗は PageA11yResult.error に残し、空結果が「違反なし」に見えないようにする。
- ルール関数は rules_* モジュールの ``*RULES: dict[rule_id, fn]`` から解決する。
  fn の形は ``fn(view)``（rules_aria / rules_visual）または ``fn(view, spec)``。
  view は ``to_rule_view(snapshot)`` の dict（``view["snapshot"]`` に Snapshot 本体）。
- 外部ネットワーク・外部 JS 注入は行わない。
"""

from __future__ import annotations

import importlib
import inspect
import logging
import time
from dataclasses import replace
from collections.abc import Callable, Iterable
from typing import Any

from .catalog import CATALOG
from .models import (
    ENGINE_NAME,
    CATALOG_VERSION,
    Finding,
    PageA11yResult,
    RuleResult,
    RuleSpec,
    aggregate_rule,
)
from .snapshot import Snapshot, take_snapshot

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 20.0
RULE_MODULES = ("rules_name", "rules_document", "rules_aria", "rules_visual")

RuleFn = Callable[..., "Iterable[Finding]"]
ResolveFn = Callable[[RuleSpec], "RuleFn | None"]


_NAME_TAGS = frozenset({
    "img", "input", "select", "textarea", "button", "a", "area", "iframe", "frame", "svg", "object",
    "summary", "meter", "progress", "h1", "h2", "h3", "h4", "h5", "h6", "fieldset", "table", "figure",
})
_FULL_NAME_LIMIT = 4000


def to_rule_view(snap: Snapshot) -> dict[str, Any]:
    """Snapshot をルール層の入力 dict（id/selector/tag/attrs/role/bbox/parent/children/text/style/scroll）へ。"""
    from .accname import compute_name, effective_role
    from .data import aria_spec

    elements = []
    full = len(snap.elements) <= _FULL_NAME_LIMIT
    for e in snap.elements:
        wants_name = full or e.tag in _NAME_TAGS or e.has("role") or e.has("aria-label") or e.has("aria-labelledby")
        text = "".join(k for k in e.kids if isinstance(k, str))
        elements.append({
            "id": e.i, "idx": e.i, "selector": e.selector, "tag": e.tag, "attrs": dict(e.attrs),
            "role": effective_role(snap, e, aria_spec.VALID_ROLES),
            "visible": e.rendered and e.visible, "focusable": e.focusable, "tab_stop": e.tab_stop,
            "bbox": {"x": e.box[0], "y": e.box[1], "width": e.box[2], "height": e.box[3]},
            "parent": e.parent if e.parent >= 0 else None,
            "children": [k for k in e.kids if isinstance(k, int)],
            "labels": list(e.labels), "accname": compute_name(snap, e.i).name if wants_name else None,
            "text": text, "style": dict(e.style),
            "scroll": {"scrollWidth": e.scroll[0], "clientWidth": e.scroll[1],
                       "scrollHeight": e.scroll[2], "clientHeight": e.scroll[3]},
        })
    return {"url": snap.url, "doc": snap.doc, "elements": elements, "title": snap.doc.title,
            "truncated": snap.truncated, "snapshot": snap}


def _wrap(fn: RuleFn) -> RuleFn:
    params = [p for p in inspect.signature(fn).parameters.values()
              if p.default is inspect.Parameter.empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    return fn if len(params) >= 2 else (lambda view, spec, _f=fn: _f(view))


def resolve_rule(spec: RuleSpec) -> RuleFn | None:
    """rule_id に対応する関数を rules_* モジュールの *RULES 辞書から探す。無ければ None。"""
    for name in RULE_MODULES:
        try:
            module = importlib.import_module(f"ux.a11y.{name}")
        except ImportError:
            continue
        for attr, table in vars(module).items():
            if attr.endswith("RULES") and isinstance(table, dict) and callable(table.get(spec.rule_id)):
                return _wrap(table[spec.rule_id])
    return None


def _default_snapshot(page: Any) -> dict[str, Any]:
    return to_rule_view(take_snapshot(page))


def run_native_a11y(
    page: Any,
    screenshot_path: str | None = None,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    specs: Iterable[RuleSpec] | None = None,
    snapshot_fn: Callable[[Any], Any] | None = None,
    resolver: ResolveFn | None = None,
    url: str | None = None,
) -> PageA11yResult:
    """画面 1 枚をカタログ全ルールで検査し、全ルール 1 行ずつの結果を返す。"""
    del screenshot_path  # 証跡パスはレポート層で画面情報から付与する
    spec_list = tuple(specs if specs is not None else CATALOG)
    resolve = resolver or resolve_rule
    page_url = url if url is not None else str(getattr(page, "url", "") or "")
    started = time.monotonic()
    try:
        view = (snapshot_fn or _default_snapshot)(page)
    except Exception as exc:  # noqa: BLE001 - 取得失敗は「未検査」として明示する
        message = f"スナップショット取得に失敗: {type(exc).__name__}: {exc}"
        logger.warning("a11y 検査を実施できませんでした: %s", message)
        rules = tuple(aggregate_rule(s, (), executed=False, message="検査を実施できませんでした") for s in spec_list)
        return PageA11yResult(page_url, rules, ENGINE_NAME, CATALOG_VERSION, message)

    rules: list[RuleResult] = []
    error: str | None = None
    for index, spec in enumerate(spec_list):
        if time.monotonic() - started > timeout_s:
            error = f"タイムアウト（{timeout_s:g} 秒）。残り {len(spec_list) - index} ルールは未評価"
            rules.extend(aggregate_rule(s, (), executed=False, message="タイムアウトのため未評価") for s in spec_list[index:])
            break
        fn = None if not spec.declared else resolve(spec)
        if fn is None:
            msg = "" if not spec.declared else "ルール実装が見つかりません（未結線）"
            rules.append(aggregate_rule(spec, (), executed=False, message=msg))
            continue
        try:
            produced = fn(view, spec)
            if isinstance(produced, RuleResult):  # 集約済みを返す実装（rules_name / rules_document）
                nodes = tuple(n if n.rule_id else replace(n, rule_id=spec.rule_id) for n in produced.nodes)
                rules.append(aggregate_rule(spec, nodes, message=produced.message))
                continue
            found = tuple(produced)
        except Exception as exc:  # noqa: BLE001 - 1 ルールの失敗で全体を止めない
            logger.warning("a11y ルール %s の実行に失敗: %s", spec.rule_id, exc)
            rules.append(aggregate_rule(spec, (), executed=False, message=f"実行エラー: {type(exc).__name__}"))
            continue
        rules.append(aggregate_rule(spec, found))
    return PageA11yResult(page_url, tuple(rules), ENGINE_NAME, CATALOG_VERSION, error)
