"""性能観測（第7弾 A）の契約。

守るべきは「計測不能を0で偽装しないこと」「観測がクロールを止めないこと」
「合否判定をしないこと」。実ブラウザ不要（page を差し替える）。
"""

from __future__ import annotations

from crawler.performance_probe import (
    CLAIM_SCOPE,
    PerformanceSample,
    collect_performance,
    install_performance_observers,
)


class _FakePage:
    def __init__(self, raw=None, raise_on=None):
        self._raw = raw
        self._raise_on = raise_on or set()
        self.init_scripts: list[str] = []

    def add_init_script(self, script: str) -> None:
        if "init" in self._raise_on:
            raise RuntimeError("init failed")
        self.init_scripts.append(script)

    def evaluate(self, _script: str):
        if "evaluate" in self._raise_on:
            raise RuntimeError("evaluate failed")
        return self._raw


_GOOD = {
    "lcp_ms": 1234.5,
    "cls": 0.0123,
    "ttfb_ms": 88.0,
    "dcl_ms": 900.0,
    "load_ms": 1500.0,
    "transfer_bytes": 40960,
}


def test_observers_are_registered_before_navigation() -> None:
    page = _FakePage()

    install_performance_observers(page)

    assert page.init_scripts
    assert "PerformanceObserver" in page.init_scripts[0]


def test_registration_failure_does_not_raise() -> None:
    install_performance_observers(_FakePage(raise_on={"init"}))  # 例外にならない


def test_collect_returns_sample_with_claim_scope() -> None:
    sample = collect_performance(_FakePage(_GOOD))

    assert isinstance(sample, PerformanceSample)
    assert sample.lcp_ms == 1234.5
    assert sample.to_dict()["claim_scope"] == CLAIM_SCOPE


def test_collect_returns_none_when_evaluate_raises() -> None:
    """計測不能は None（0 で偽装しない）。クロールは止めない。"""
    assert collect_performance(_FakePage(raise_on={"evaluate"})) is None


def test_collect_returns_none_for_non_dict() -> None:
    assert collect_performance(_FakePage("not-a-dict")) is None


def test_to_dict_rounds_but_keeps_zero_as_measured() -> None:
    sample = collect_performance(
        _FakePage(
            {"lcp_ms": 0, "cls": 0, "ttfb_ms": 0, "dcl_ms": 0, "load_ms": 0, "transfer_bytes": 0}
        )
    )

    assert sample is not None
    assert sample.to_dict()["lcp_ms"] == 0.0


def test_sample_has_no_pass_fail_field() -> None:
    """合否判定はしない設計。判定系のキーが存在しないこと。"""
    keys = collect_performance(_FakePage(_GOOD)).to_dict().keys()

    assert not any(k in keys for k in ("passed", "is_good", "grade", "verdict"))
