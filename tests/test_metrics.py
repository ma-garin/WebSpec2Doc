"""可観測性（メトリクス・構造化ログ）の契約。

運用者が知りたいのは「静かに壊れていないか」なので、失敗・遅延・滞留が
必ず観測できることを固定する。
"""

from __future__ import annotations

import json
import logging

import pytest
from prometheus_client import CollectorRegistry
from web.services import metrics as metrics_module


@pytest.fixture(autouse=True)
def fresh_registry(monkeypatch: pytest.MonkeyPatch):
    """テスト間でカウンタが持ち越されないよう、計器を作り直す。"""
    from prometheus_client import Counter, Gauge, Histogram

    registry = CollectorRegistry()
    monkeypatch.setattr(metrics_module, "REGISTRY", registry)
    monkeypatch.setattr(
        metrics_module,
        "crawl_total",
        Counter("webspec2doc_crawl_total", "t", labelnames=("result",), registry=registry),
    )
    monkeypatch.setattr(
        metrics_module,
        "crawl_duration_seconds",
        Histogram("webspec2doc_crawl_duration_seconds", "t", registry=registry),
    )
    monkeypatch.setattr(
        metrics_module,
        "schedule_delay_seconds",
        Gauge("webspec2doc_schedule_delay_seconds", "t", registry=registry),
    )
    monkeypatch.setattr(
        metrics_module,
        "job_queue_depth",
        Gauge("webspec2doc_job_queue_depth", "t", registry=registry),
    )
    monkeypatch.setattr(
        metrics_module,
        "notification_total",
        Counter(
            "webspec2doc_notification_total",
            "t",
            labelnames=("result", "channel"),
            registry=registry,
        ),
    )
    return registry


def _text() -> str:
    body, _ = metrics_module.render_metrics()
    return body.decode("utf-8")


def _value(text: str, needle: str) -> float:
    for line in text.splitlines():
        if line.startswith(needle):
            return float(line.rsplit(" ", 1)[1])
    raise AssertionError(f"{needle} が出力に無い:\n{text}")


# ─────────────────── 公開形式 ───────────────────


def test_metrics_expose_prometheus_content_type() -> None:
    _body, content_type = metrics_module.render_metrics()

    assert "text" in content_type


def test_success_and_failure_are_both_observable() -> None:
    metrics_module.record_crawl(success=True, duration_sec=1.0)
    metrics_module.record_crawl(success=False, duration_sec=2.0)

    text = _text()
    assert _value(text, 'webspec2doc_crawl_total{result="success"}') == 1.0
    assert _value(text, 'webspec2doc_crawl_total{result="failure"}') == 1.0


def test_crawl_duration_is_recorded_as_histogram() -> None:
    metrics_module.record_crawl(success=True, duration_sec=3.5)

    text = _text()
    assert _value(text, "webspec2doc_crawl_duration_seconds_count") == 1.0
    assert _value(text, "webspec2doc_crawl_duration_seconds_sum") == 3.5


def test_notification_failures_are_counted_per_channel() -> None:
    metrics_module.record_notification(success=False, channel="slack")

    assert (
        _value(_text(), 'webspec2doc_notification_total{channel="slack",result="failure"}') == 1.0
    )


def test_unknown_channel_is_labelled_not_dropped() -> None:
    metrics_module.record_notification(success=True, channel="")

    assert (
        _value(_text(), 'webspec2doc_notification_total{channel="unknown",result="success"}') == 1.0
    )


def test_schedule_delay_and_queue_depth_are_gauges() -> None:
    metrics_module.set_schedule_delay(42.5)
    metrics_module.set_job_queue_depth(3)

    text = _text()
    assert _value(text, "webspec2doc_schedule_delay_seconds") == 42.5
    assert _value(text, "webspec2doc_job_queue_depth") == 3.0


def test_negative_values_are_clamped_not_published_as_is() -> None:
    metrics_module.set_schedule_delay(-10)
    metrics_module.set_job_queue_depth(-5)

    text = _text()
    assert _value(text, "webspec2doc_schedule_delay_seconds") == 0.0
    assert _value(text, "webspec2doc_job_queue_depth") == 0.0


# ─────────────────── 計測が本処理を壊さない ───────────────────


def test_measure_crawl_records_failure_and_reraises() -> None:
    with pytest.raises(RuntimeError):
        with metrics_module.measure_crawl():
            raise RuntimeError("boom")

    assert _value(_text(), 'webspec2doc_crawl_total{result="failure"}') == 1.0


def test_measure_crawl_records_success_by_default() -> None:
    with metrics_module.measure_crawl():
        pass

    assert _value(_text(), 'webspec2doc_crawl_total{result="success"}') == 1.0


# ─────────────────── 構造化ログ ───────────────────


def test_json_formatter_emits_one_json_object_per_line() -> None:
    record = logging.LogRecord(
        name="web.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="クロール完了 %s",
        args=("example.com",),
        exc_info=None,
    )

    payload = json.loads(metrics_module.JsonLogFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "web.test"
    assert payload["message"] == "クロール完了 example.com"
    assert payload["time"]


def test_json_formatter_includes_exception_text() -> None:
    try:
        raise ValueError("失敗")
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="web.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="エラー",
            args=(),
            exc_info=sys.exc_info(),
        )

    payload = json.loads(metrics_module.JsonLogFormatter().format(record))

    assert "ValueError" in payload["exception"]


def test_configure_json_logging_replaces_handlers() -> None:
    root = logging.getLogger()
    original = list(root.handlers)
    try:
        metrics_module.configure_json_logging()

        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, metrics_module.JsonLogFormatter)
    finally:
        root.handlers = original
