"""ux.a11y.runner: 全ルール 1 行出力・NOT_EVALUATED の扱い（スタブのルールで検証）。"""

from __future__ import annotations

from ux.a11y.models import NodeResult, RuleSpec
from ux.a11y.runner import aggregate_status, run_native_a11y


def _spec(rule_id: str, impl: str = "full") -> RuleSpec:
    return RuleSpec(
        rule_id=rule_id,
        implementation=impl,
        category=rule_id.split(".")[0],
        reason_if_unimplemented="対象外" if impl == "none" else "",
    )


def _status(result, rule_id: str) -> str:
    return next(str(r.status) for r in result.rules if r.rule_id == rule_id)


def _stub_resolver(table):
    return lambda spec: table.get(spec.rule_id)


def test_every_catalog_rule_appears_once_and_none_is_not_implemented() -> None:
    specs = [_spec("name.a"), _spec("name.b"), _spec("bp.c", "none"), _spec("aria.d")]
    table = {
        "name.a": lambda snap, spec: [NodeResult(status="violation", selector="img", impact="serious")],
        "name.b": lambda snap, spec: [NodeResult(status="pass", selector="a")],
        # aria.d: 関数なし（実装宣言済みだが未解決）
    }
    result = run_native_a11y(
        object(), specs=specs, snapshot_fn=lambda p: {}, resolver=_stub_resolver(table), url="u"
    )
    assert [r.rule_id for r in result.rules] == ["name.a", "name.b", "bp.c", "aria.d"]
    assert _status(result, "name.a") == "violation"
    assert _status(result, "name.b") == "pass"
    assert _status(result, "bp.c") == "not_implemented"
    assert _status(result, "aria.d") == "not_implemented"
    assert result.error is None


def test_rule_exception_becomes_cant_tell_not_pass() -> None:
    def boom(snap, spec):
        raise ValueError("x")

    result = run_native_a11y(
        object(),
        specs=[_spec("name.a"), _spec("name.b")],
        snapshot_fn=lambda p: {},
        resolver=_stub_resolver({"name.a": boom, "name.b": lambda s, sp: []}),
    )
    assert _status(result, "name.a") == "cant_tell"
    assert _status(result, "name.b") == "inapplicable"


def test_snapshot_failure_sets_error_and_no_pass() -> None:
    def fail(page):
        raise RuntimeError("detached")

    result = run_native_a11y(
        object(), specs=[_spec("name.a"), _spec("bp.c", "none")], snapshot_fn=fail
    )
    assert result.error and "detached" in result.error
    assert {str(r.status) for r in result.rules} == {"cant_tell", "not_implemented"}


def test_timeout_marks_remaining_rules_not_evaluated() -> None:
    result = run_native_a11y(
        object(),
        specs=[_spec("name.a"), _spec("name.b")],
        snapshot_fn=lambda p: {},
        resolver=_stub_resolver({}),
        timeout_s=-1.0,
    )
    assert result.error and "タイムアウト" in result.error
    assert len(result.rules) == 2
    assert all(str(r.status) != "pass" for r in result.rules)


def test_default_resolver_returns_none_for_unimplemented_module() -> None:
    # 実装モジュールが無い／関数が無い full ルールでも全件 1 行で出る（pass にならない）
    result = run_native_a11y(object(), specs=[_spec("zzz.unknown")], snapshot_fn=lambda p: {})
    assert [str(r.status) for r in result.rules] == ["not_implemented"]


def test_aggregate_never_turns_cant_tell_into_pass() -> None:
    mixed = [NodeResult(status="pass"), NodeResult(status="cant_tell")]
    assert aggregate_status(mixed) == "cant_tell"
    assert aggregate_status([]) == "inapplicable"
    assert aggregate_status([NodeResult(status="pass"), NodeResult(status="violation")]) == "violation"
