"""実 REA 6.7.0 で Before（変更前コード）と After（変更後コード）を同条件で測る。

使い方（リポジトリ root で 1 回だけ実行する。CI では使わない）::

    venv/bin/python tests/fixtures/reverse_analysis/real/measure_value.py \
        --before-src <変更前 src の退避先> --rea <rea 実行ファイル> --work <空の作業 dir>

入力は自己所有の real/app と固定 snapshot（runtime_snapshot.json）。質問集は下の QUESTIONS で固定し、
正解は real/app のソース本文から機械的に確かめる（推測で正解を作らない）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = Path(__file__).resolve().parent
APP = FIXTURE / "app"
SNAPSHOT = FIXTURE.parent / "runtime_snapshot.json"
OUTPUT = ROOT / "docs" / "research" / "reverse-analysis" / "REAL_REA_VALUE_MEASUREMENT.json"

RUNNER = """
import json, sys, threading
from reverse_analysis.service import ReverseAnalysisRequest, run_reverse_analysis
kwargs = dict(js_input=sys.argv[1], runtime_snapshot=sys.argv[2], rea_command=sys.argv[3], output_dir=sys.argv[4])
if sys.argv[5] == "1":
    kwargs["include_provider_evidence"] = True
outcome = run_reverse_analysis(ReverseAnalysisRequest(**kwargs))
print(json.dumps({"status": outcome.status, "exit_code": outcome.exit_code}))
"""

ROUTES = (
    ("/users", "routes/app.js"),
    ("/settings", "routes/app.js"),
    ("/users/:id", "routes/app.js"),
    ("/items", "mapped/app.js"),
)


def _run(src: Path, rea: str, out: Path, opt_in: bool) -> tuple[dict[str, Any], float]:
    start = time.perf_counter()
    proc = subprocess.run(  # noqa: S603 - 固定 argv・shell 不使用
        [sys.executable, "-I", "-c", f"import sys; sys.path[:0] = [{str(src)!r}, {str(ROOT / 'src')!r}]\n" + RUNNER,
         str(APP), str(SNAPSHOT), rea, str(out), "1" if opt_in else "0"],
        capture_output=True, text=True, check=True, timeout=300,
    )  # fmt: skip
    wall = time.perf_counter() - start
    json.loads(proc.stdout)
    return json.loads((out / "reverse_analysis.json").read_text(encoding="utf-8")), wall


def _source_line(rel: str, line: int) -> str:
    return (APP / rel).read_text(encoding="utf-8").splitlines()[line - 1]


def _route_answer(doc: dict[str, Any], path: str, rel: str) -> dict[str, Any]:
    hits = [c for c in doc["static_candidates"] if c["kind"] == "route" and c["path"] == path]
    if len(hits) != 1:
        return {"answered": False, "reason": f"route 候補 {len(hits)} 件"}
    loc = hits[0]["location"]
    ok = loc["artifact_path"] == rel and path in _source_line(rel, loc["start_line"])
    return {
        "answered": ok,
        "evidence": f"{loc['artifact_path']}:{loc['start_line']}:{loc['start_column']}",
    }


def _misclassified_routes(doc: dict[str, Any]) -> int:
    return sum(
        1
        for c in doc["static_candidates"]
        if c["kind"] == "api" and c["path"] in {p for p, _ in ROUTES}
    )


def _imports_answer(doc: dict[str, Any]) -> dict[str, Any]:
    edges = doc.get("provider_evidence", {}).get("dependency_edges", [])
    text = (APP / "modules/main.js").read_text(encoding="utf-8")
    mine = [
        e for e in edges if (e["location"].get("value") or {}).get("source") == "modules/main.js"
    ]
    specs = sorted(
        {e["properties"].get("specifier") for e in mine if e["properties"].get("specifier")}
    )
    if not specs:
        return {
            "answered": False,
            "reason": "modules/main.js を起点とする imports edge が出力に無い",
        }
    return {"answered": all(s in text for s in specs), "evidence": specs}


def _method_answer(doc: dict[str, Any]) -> dict[str, Any]:
    hits = [
        c for c in doc["static_candidates"] if c["kind"] == "api" and c["path"] == "/api/explicit"
    ]
    methods = sorted({str(c["method"]) for c in hits})
    return {
        "answered": methods == ["POST"],
        "evidence": methods,
        "ground_truth": "POST（routes/app.js の fetch 第 2 引数）",
    }


def _source_name_answer(doc: dict[str, Any]) -> dict[str, Any]:
    names = sorted(
        {c["path"] for c in doc["static_candidates"] if c["kind"] == "source" and c["path"]}
    )
    return {"answered": names == ["src/app.ts"], "evidence": names}


def _api_answer(doc: dict[str, Any]) -> dict[str, Any]:
    hits = [c for c in doc["static_candidates"] if c["kind"] == "api" and c["path"] == "/api/items"]
    ok = len(hits) == 1 and "/api/items" in _source_line(
        hits[0]["artifact_path"], hits[0]["location"]["start_line"]
    )
    return {
        "answered": ok,
        "evidence": [f"{h['artifact_path']}:{h['location']['start_line']}" for h in hits],
    }


def _answers(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    answers = {
        f"Q{i}_route_{p}": _route_answer(doc, p, rel) for i, (p, rel) in enumerate(ROUTES, 1)
    }
    answers["Q5_main_js_imports"] = _imports_answer(doc)
    answers["Q6_api_explicit_http_method"] = _method_answer(doc)
    answers["Q7_source_map_original_name"] = _source_name_answer(doc)
    answers["Q8_api_items_call_site"] = _api_answer(doc)
    return answers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before-src", required=True)
    parser.add_argument("--rea", required=True)
    parser.add_argument("--work", required=True)
    args = parser.parse_args()
    work = Path(args.work)
    before, before_wall = _run(Path(args.before_src), args.rea, work / "before", False)
    after, after_wall = _run(ROOT / "src", args.rea, work / "after", True)
    qa_before, qa_after = _answers(before), _answers(after)
    n_before = sum(a["answered"] for a in qa_before.values())
    n_after = sum(a["answered"] for a in qa_after.values())
    useful_new = sorted(
        q for q in qa_after if qa_after[q]["answered"] and not qa_before[q]["answered"]
    )
    record = {
        "schema": "webspec2doc-real-rea-value-measurement/1",
        "provider": {
            "kind": "real",
            "name": "rea-agents",
            "version": after["producer"]["provider_version"],
        },
        "inputs": {
            "js_input": "tests/fixtures/reverse_analysis/real/app（自己所有 controlled fixture）",
            "runtime_snapshot": "tests/fixtures/reverse_analysis/runtime_snapshot.json",
            "runtime_snapshot_sha256": after["inputs"]["runtime_snapshot_sha256"],
        },
        "evaluation_set": {
            "description": "real/app に対する固定 QA 質問 8 問。正解は real/app のソース本文で機械照合。製品全体の能力点ではない",
            "questions": sorted(qa_after),
        },
        "before": {
            "code": "変更前の src/reverse_analysis（退避コピー）",
            "status": before["status"],
            "wall_seconds": round(before_wall, 2),
            "answered": n_before,
            "answers": qa_before,
            "candidate_kinds": _kinds(before),
            "routes_misclassified_as_api": _misclassified_routes(before),
        },
        "after": {
            "code": "変更後の src/reverse_analysis（--reverse-provider-evidence）",
            "status": after["status"],
            "wall_seconds": round(after_wall, 2),
            "answered": n_after,
            "answers": qa_after,
            "candidate_kinds": _kinds(after),
            "routes_misclassified_as_api": _misclassified_routes(after),
            "dependency_edges": len(after["provider_evidence"]["dependency_edges"]),
        },
        "useful_new_evidence": useful_new,
        "relative_score": {
            "basis": "同じ 8 問・同じ分母での正答数比。Before=100",
            "before": 100 if n_before else None,
            "after": round(n_after / n_before * 100, 1) if n_before else None,
        },
        "added_wall_seconds": round(after_wall - before_wall, 2),
        "unverified": [
            "HTTP method（Q6）は REA の Evidence に値が無く、Before/After とも未回答（捏造しない）",
            "source map の鮮度（stale）と generated→original の行対応は REA が返さず未確認",
            "wall time は 1 回の実測で、REA 実行時間の揺れ（Wave A1 は 9.69s）を含む。性能の比較値ではない",
        ],
        "ac10": "PASS" if useful_new else "FAIL",
    }
    OUTPUT.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "before": n_before,
                "after": n_after,
                "useful_new": len(useful_new),
                "ac10": record["ac10"],
            }
        )
    )
    return 0


def _kinds(doc: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for c in doc["static_candidates"]:
        counts[c["kind"]] = counts.get(c["kind"], 0) + 1
    return dict(sorted(counts.items()))


if __name__ == "__main__":
    raise SystemExit(main())
