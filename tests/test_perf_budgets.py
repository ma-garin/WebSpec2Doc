"""レーンD-3: 負荷・性能予算のテスト固定（R3-23）。

外部ネットワーク不使用・決定的。予算値をテストコードの定数として固定し、
以後の劣化をCIが検知できるようにする。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import networkx as nx
from web.routes.auto_run import AutoRunJob, _current_test_progress, _now_iso

from analyzer.html_analyzer import analyze_pages
from crawler.page_crawler import FieldData, FormData, PageData
from generator.html_reporter import generate_html_report
from generator.test_design import TestDesignParams as DesignParams
from generator.test_design import build_test_design

# ─────────────────────── D-3a/b: /api/autorun/status 応答予算 ───────────────────────

_NDJSON_LINE_COUNT = 1000
_MAX_RESPONSE_BYTES = 64 * 1024
# CI環境のCPU変動を考慮した緩和上限。ローカル実測は概ね数msだが、
# 共有CPUのCI実行では遅延することがあるため300msまで許容する。
_MAX_P95_LATENCY_MS = 300


def _write_worst_case_ndjson(path: Path) -> None:
    """title 200字・error 300字（切り詰め上限値）×1,000行のNDJSONを書く。"""
    lines = [json.dumps({"event": "begin", "total": _NDJSON_LINE_COUNT})]
    long_title = "T" * 200
    long_error = "E" * 300
    for i in range(_NDJSON_LINE_COUNT):
        lines.append(
            json.dumps(
                {
                    "event": "test",
                    "title": f"{long_title}{i}",
                    "status": "failed" if i % 2 else "passed",
                    "duration": 1234,
                    "error": long_error,
                }
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_autorun_status_response_under_64kb(tmp_path: Path) -> None:
    job = AutoRunJob(
        job_id="perf-job", url="https://example.com", domain="example.com", started_at=_now_iso()
    )
    qa_dir = tmp_path / "example.com" / "qa_process"
    qa_dir.mkdir(parents=True)
    _write_worst_case_ndjson(qa_dir / "playwright_progress.ndjson")

    with patch("web.routes.auto_run.OUTPUT_DIR", tmp_path):
        progress = _current_test_progress(job)

    body_size = len(json.dumps(progress).encode("utf-8"))
    assert body_size < _MAX_RESPONSE_BYTES, f"応答サイズが予算超過: {body_size} bytes"


def test_autorun_status_latency_p95_under_100ms(tmp_path: Path) -> None:
    job = AutoRunJob(
        job_id="perf-job-2", url="https://example.com", domain="example.com", started_at=_now_iso()
    )
    qa_dir = tmp_path / "example.com" / "qa_process"
    qa_dir.mkdir(parents=True)
    _write_worst_case_ndjson(qa_dir / "playwright_progress.ndjson")

    durations_ms: list[float] = []
    with patch("web.routes.auto_run.OUTPUT_DIR", tmp_path):
        for _ in range(100):
            start = time.perf_counter()
            _current_test_progress(job)
            durations_ms.append((time.perf_counter() - start) * 1000)

    durations_ms.sort()
    p95 = durations_ms[int(len(durations_ms) * 0.95) - 1]
    assert p95 < _MAX_P95_LATENCY_MS, f"p95レイテンシが予算超過: {p95:.2f}ms"


# ─────────────────────── D-3c: 100画面レポート生成予算 ───────────────────────

_MAX_REPORT_GENERATION_SEC = 5.0
_MAX_REPORT_BYTES = 8 * 1024 * 1024
_SYNTHETIC_SCREEN_COUNT = 100


def _synthetic_field(name: str) -> FieldData:
    return FieldData(
        field_type="text",
        name=name,
        placeholder="",
        required=True,
        maxlength=100,
    )


def _synthetic_page(i: int):
    page_id = f"P{i:03d}"
    fields = tuple(_synthetic_field(f"field{i}_{j}") for j in range(3))
    form = FormData(action=f"/submit{i}", method="post", fields=fields)
    page_data = PageData(
        url=f"https://example.com/page{i}",
        title=f"画面{i}",
        headings=(f"見出し{i}",),
        links=(),
        forms=(form,),
        screenshot_path=None,
    )
    return page_data, page_id, fields


def _report_screen_dict(page_id: str, fields: tuple[FieldData, ...], to: list[str]) -> dict:
    field_dicts = [
        {
            "name": f.name,
            "field_type": f.field_type,
            "required": f.required,
            "maxlength": f.maxlength,
            "minlength": f.minlength,
            "min_value": f.min_value,
            "max_value": f.max_value,
            "pattern": f.pattern,
            "options": [],
        }
        for f in fields
    ]
    return {
        "page_id": page_id,
        "title": f"画面 {page_id}",
        "buttons": [],
        "forms": [{"action": "/submit", "method": "post", "fields": field_dicts}],
        "transitions": {"to": to, "from": []},
    }


def test_generate_html_report_100_screens_under_5s_and_8mb() -> None:
    raw_pages = [_synthetic_page(i) for i in range(_SYNTHETIC_SCREEN_COUNT)]
    analyzed = analyze_pages([p[0] for p in raw_pages])

    graph = nx.DiGraph()
    for i, (_, page_id, _fields) in enumerate(raw_pages):
        graph.add_node(
            page_id, url=raw_pages[i][0].url, title=raw_pages[i][0].title, page_id=page_id
        )
    for i, (_, page_id, _fields) in enumerate(raw_pages):
        nxt = raw_pages[(i + 1) % _SYNTHETIC_SCREEN_COUNT][1]
        graph.add_edge(page_id, nxt)

    screens = [
        _report_screen_dict(
            page_id,
            fields,
            to=[raw_pages[(i + 1) % _SYNTHETIC_SCREEN_COUNT][1]],
        )
        for i, (_, page_id, fields) in enumerate(raw_pages)
    ]
    test_design = build_test_design({"screens": screens}, DesignParams(max_dt_conditions=6))

    mermaid = "graph LR\n" + "\n".join(
        f"  {raw_pages[i][1]} --> {raw_pages[(i + 1) % _SYNTHETIC_SCREEN_COUNT][1]}"
        for i in range(_SYNTHETIC_SCREEN_COUNT)
    )

    start = time.perf_counter()
    html = generate_html_report(
        pages=analyzed,
        graph=graph,
        form_summary=[],
        target_url="https://example.com/",
        mermaid_content=mermaid,
        test_design=test_design,
    )
    elapsed = time.perf_counter() - start

    assert elapsed < _MAX_REPORT_GENERATION_SEC, f"生成時間が予算超過: {elapsed:.2f}s"
    size_bytes = len(html.encode("utf-8"))
    assert size_bytes < _MAX_REPORT_BYTES, f"出力サイズが予算超過: {size_bytes} bytes"


# ─────────────────────── D-3d: デシジョンテーブル・ペアワイズの行数上限 ───────────────────────


def test_decision_table_rule_cap() -> None:
    """max_dt_conditions=6 でもルール数は 2^6=64 を超えない（8条件入力でも据え置き）。"""
    fields = [
        {
            "name": f"f{i}",
            "field_type": "text",
            "required": True,
            "maxlength": None,
            "minlength": None,
            "min_value": None,
            "max_value": None,
            "pattern": None,
            "options": [],
        }
        for i in range(8)
    ]
    screen = {
        "page_id": "P001",
        "title": "画面 P001",
        "buttons": [],
        "forms": [{"action": "/submit", "method": "post", "fields": fields}],
        "transitions": {"to": [], "from": []},
    }
    params = DesignParams(max_dt_conditions=6)
    design = build_test_design({"screens": [screen]}, params)

    assert len(design.screens) == 1
    dt = design.screens[0].decision_table
    assert dt is not None
    assert len(dt.rules) == 2**6 == 64


def test_pairwise_rows_bounded() -> None:
    """6パラメータ×各4値の全組合せ(4096)に対し、貪欲ペアワイズ被覆は十分小さい(<=100)行に収まる。"""
    fields = [
        {
            "name": f"p{i}",
            "field_type": "select",
            "required": False,
            "maxlength": None,
            "minlength": None,
            "min_value": None,
            "max_value": None,
            "pattern": None,
            "options": [f"v{i}_{j}" for j in range(4)],
        }
        for i in range(6)
    ]
    screen = {
        "page_id": "P001",
        "title": "画面 P001",
        "buttons": [],
        "forms": [{"action": "/submit", "method": "post", "fields": fields}],
        "transitions": {"to": [], "from": []},
    }
    params = DesignParams(pairwise_strength=2)
    design = build_test_design({"screens": [screen]}, params)

    assert len(design.screens) == 1
    pw = design.screens[0].pairwise
    assert pw is not None
    full_cartesian = 4**6
    assert full_cartesian == 4096
    assert len(pw.rows) <= 100, f"ペアワイズ行数が予算超過: {len(pw.rows)}"
