"""自社 Accessibility チェッカーの実行器（ルール全件を必ず 1 行ずつ結果に出す）。

- カタログの全ルールを走らせ、未実装・実行不能・判定不能のルールは NOT_EVALUATED
  （not_implemented / cant_tell）として結果に含める。PASS には数えない。
- ブラウザ内スナップショット取得の失敗・全体タイムアウトは ``PageA11yResult.error`` に残し、
  空結果が「違反なし」に見えないようにする。
- ルール関数は ``catalog`` のカテゴリからモジュール名で解決する（実装は別ファイル）。
  外部ネットワーク・外部 JS 注入は行わない。
"""

from __future__ import annotations

import importlib
import logging
import time
from collections.abc import Callable, Iterable
from typing import Any

from ux.a11y import catalog as _catalog
from ux.a11y.models import NodeResult, PageA11yResult, RuleResult, RuleSpec

logger = logging.getLogger(__name__)

ENGINE_NAME = "webspec2doc-native-a11y"
DEFAULT_TIMEOUT_S = 20.0

# rule_id 接頭辞 / カテゴリ → ルール実装モジュール（src/ux/a11y/ 配下）
_RULE_MODULES: dict[str, str] = {
    "name": "rules_name",
    "doc": "rules_document",
    "struct": "rules_document",
    "form": "rules_document",
    "bp": "rules_document",
    "aria": "rules_aria",
    "visual": "rules_visual",
    "op": "rules_visual",
}

RuleFn = Callable[[Any, RuleSpec], "Iterable[NodeResult] | RuleResult"]
ResolveFn = Callable[[RuleSpec], "RuleFn | None"]
SnapshotFn = Callable[[Any], Any]


def _s(value: Any) -> str:
    return str(getattr(value, "value", value))


def resolve_rule(spec: RuleSpec) -> RuleFn | None:
    """spec から ``ux.a11y.<rules_*>`` のルール関数を解決する。無ければ None。

    モジュールに ``RULES: dict[rule_id, fn]`` があればそれを優先し、
    無ければ rule_id の ``.``/``-`` を ``_`` にした名前の関数を探す。
    """
    prefix = spec.rule_id.split(".", 1)[0]
    module_name = _RULE_MODULES.get(prefix) or _RULE_MODULES.get(_s(spec.category))
    if not module_name:
        return None
    try:
        module = importlib.import_module(f"ux.a11y.{module_name}")
    except ImportError:
        return None
    table = getattr(module, "RULES", None)
    if isinstance(table, dict) and callable(table.get(spec.rule_id)):
        return table[spec.rule_id]
    func = getattr(module, spec.rule_id.replace(".", "_").replace("-", "_"), None)
    return func if callable(func) else None


def _default_snapshot(page: Any) -> Any:
    module = importlib.import_module("ux.a11y.snapshot")
    func = getattr(module, "take_snapshot", None) or getattr(module, "capture_snapshot")
    return func(page)


def aggregate_status(nodes: Iterable[NodeResult]) -> str:
    """ノード結果 → ルール単位の状態。cant_tell・未判定が pass に化ける経路を作らない。"""
    statuses = [_s(node.status) for node in nodes]
    if any(s == "violation" for s in statuses):
        return "violation"
    if not statuses or all(s == "inapplicable" for s in statuses):
        return "inapplicable"
    if any(s in ("cant_tell", "not_implemented") for s in statuses):
        return "cant_tell"
    return "pass"


def _make_result(rule_id: str, status: str, nodes: tuple[NodeResult, ...] = ()) -> RuleResult:
    counts = {"violation": 0, "pass": 0, "cant_tell": 0}
    for node in nodes:
        key = _s(node.status)
        if key in counts:
            counts[key] += 1
    return RuleResult(rule_id=rule_id, status=status, nodes=nodes, counts=counts)


def _not_evaluated(spec: RuleSpec, status: str, message: str) -> RuleResult:
    node = NodeResult(status=status, message=message)
    return RuleResult(
        rule_id=spec.rule_id,
        status=status,
        nodes=(node,),
        counts={"violation": 0, "pass": 0, "cant_tell": 1 if status == "cant_tell" else 0},
    )


def _run_one(spec: RuleSpec, snapshot: Any, resolver: ResolveFn) -> RuleResult:
    if _s(spec.implementation) == "none":
        return _not_evaluated(spec, "not_implemented", spec.reason_if_unimplemented or "未実装")
    func = resolver(spec)
    if func is None:
        # 実装済みと宣言されたが関数が見つからない → 未評価（PASS にしない）
        return _not_evaluated(spec, "not_implemented", "ルール実装が見つかりません")
    try:
        produced = func(snapshot, spec)
        if isinstance(produced, RuleResult):
            return produced
        nodes = tuple(produced)
    except Exception as exc:  # noqa: BLE001 - 1 ルールの失敗で全体を止めない
        logger.warning("a11y ルール %s の実行に失敗: %s", spec.rule_id, exc)
        return _not_evaluated(spec, "cant_tell", f"実行エラー: {type(exc).__name__}")
    return _make_result(spec.rule_id, aggregate_status(nodes), nodes)


def _all_not_evaluated(specs: Iterable[RuleSpec], message: str) -> tuple[RuleResult, ...]:
    return tuple(
        _not_evaluated(
            spec,
            "not_implemented" if _s(spec.implementation) == "none" else "cant_tell",
            spec.reason_if_unimplemented if _s(spec.implementation) == "none" else message,
        )
        for spec in specs
    )


def run_native_a11y(
    page: Any,
    screenshot_path: str | None = None,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    specs: Iterable[RuleSpec] | None = None,
    snapshot_fn: SnapshotFn | None = None,
    resolver: ResolveFn | None = None,
    url: str | None = None,
) -> PageA11yResult:
    """画面 1 枚をカタログ全ルールで検査し、全ルール 1 行ずつの結果を返す。"""
    del screenshot_path  # 証跡パスはレポート層で画面情報から付与する
    spec_list = tuple(specs if specs is not None else _catalog.RULES)
    catalog_version = str(getattr(_catalog, "CATALOG_VERSION", ""))
    resolve = resolver or resolve_rule
    started = time.monotonic()
    page_url = url if url is not None else str(getattr(page, "url", "") or "")

    def _result(rules: tuple[RuleResult, ...], error: str | None = None) -> PageA11yResult:
        return PageA11yResult(
            url=page_url,
            rules=rules,
            engine=ENGINE_NAME,
            catalog_version=catalog_version,
            error=error,
        )

    try:
        snapshot = (snapshot_fn or _default_snapshot)(page)
    except Exception as exc:  # noqa: BLE001 - 取得失敗は「未検査」として明示する
        message = f"スナップショット取得に失敗: {type(exc).__name__}: {exc}"
        logger.warning("a11y 検査を実施できませんでした: %s", message)
        return _result(_all_not_evaluated(spec_list, "検査を実施できませんでした"), message)

    results: list[RuleResult] = []
    error: str | None = None
    for index, spec in enumerate(spec_list):
        if time.monotonic() - started > timeout_s:
            error = f"タイムアウト（{timeout_s:g} 秒）。残り {len(spec_list) - index} ルールは未評価"
            results.extend(_all_not_evaluated(spec_list[index:], "タイムアウトのため未評価"))
            break
        results.append(_run_one(spec, snapshot, resolve))
    return _result(tuple(results), error)
