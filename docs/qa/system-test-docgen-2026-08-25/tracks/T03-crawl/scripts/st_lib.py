"""T03 共通ライブラリ: /run ストリーム実行・解析・report.json ダイジェスト。stdlib のみ。"""
from __future__ import annotations

import json
import pathlib
import time
import urllib.parse
import urllib.request

APP = "http://127.0.0.1:8765"
MOCK = "http://127.0.0.1:9103"
DOMAIN = "127.0.0.1:9103"
TRACK = pathlib.Path(__file__).resolve().parents[1]
EV = TRACK / "evidence"
REPO = pathlib.Path(__file__).resolve().parents[6]


def out_dir() -> pathlib.Path | None:
    cand = REPO / "output" / DOMAIN
    if cand.exists():
        return cand
    hits = list((REPO / "output").glob(f"**/{DOMAIN}"))
    return hits[0] if hits else None


def post(path: str, form: dict, timeout: int = 30) -> str:
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(APP + path, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def run_stream(name: str, form: dict, lines_sink: list | None = None, timeout: int = 420) -> dict:
    """POST /run し、全行を evidence へ保存して解析を返す。lines_sink 指定時は逐次共有。"""
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(APP + "/run", data=data)
    t0 = time.time()
    lines: list = lines_sink if lines_sink is not None else []
    with urllib.request.urlopen(req, timeout=timeout) as r:
        while True:
            raw = r.readline()
            if not raw:
                break
            lines.append(raw.decode("utf-8", "replace").rstrip("\n"))
    dur = round(time.time() - t0, 1)
    (EV / f"run-{name}-stream.txt").write_text("\n".join(lines), encoding="utf-8")
    return analyze(name, lines, dur)


def analyze(name: str, lines: list, dur: float) -> dict:
    events = []
    run_id = report_path = ""
    summary = None
    idx = {"RUN_ID": -1, "crawl_started": -1, "first_page_started": -1,
           "crawl_completed": -1, "REPORT_PATH": -1, "SUMMARY": -1, "stopped": -1, "error_line": -1}
    for i, ln in enumerate(lines):
        if ln.startswith("RUN_ID:"):
            run_id = ln[7:].strip()
            idx["RUN_ID"] = i
        elif ln.startswith("REPORT_PATH:"):
            report_path = ln[12:].strip()
            idx["REPORT_PATH"] = i
        elif ln.startswith("SUMMARY:"):
            try:
                summary = json.loads(ln[8:])
            except ValueError:
                summary = {"unparseable": ln[:200]}
            idx["SUMMARY"] = i
        elif ln.strip() == "停止しました。":
            idx["stopped"] = i
        elif "エラーが発生しました" in ln:
            idx["error_line"] = i
        elif ln.startswith("CRAWL_EVENT:"):
            try:
                ev = json.loads(ln[12:])
            except ValueError:
                ev = {"event": "_unparseable", "raw": ln[:200]}
            ev["_i"] = i
            events.append(ev)
            e = ev.get("event")
            if e == "crawl_started" and idx["crawl_started"] < 0:
                idx["crawl_started"] = i
            if e == "page_started" and idx["first_page_started"] < 0:
                idx["first_page_started"] = i
            if e == "crawl_completed":
                idx["crawl_completed"] = i
    counts: dict = {}
    for ev in events:
        counts[ev.get("event", "?")] = counts.get(ev.get("event", "?"), 0) + 1
    return {
        "name": name,
        "duration_sec": dur,
        "run_id": run_id,
        "report_path": report_path,
        "report_exists": bool(report_path) and pathlib.Path(report_path).exists(),
        "summary": summary,
        "line_count": len(lines),
        "idx": idx,
        "event_counts": counts,
        "page_started_urls": [e.get("url") for e in events if e.get("event") == "page_started"],
        "page_skipped": [{"url": e.get("url"), "reason": e.get("reason")}
                         for e in events if e.get("event") == "page_skipped"],
        "checkpoints": [{"saved": e.get("saved_count"), "i": e["_i"]}
                        for e in events if e.get("event") == "checkpoint_saved"],
        "login_walls": [e for e in events if e.get("event") == "login_wall_detected"],
        "mutation_events": [e for e in events if e.get("event") == "mutation_blocked"],
        "crawl_started_payloads": [e for e in events if e.get("event") == "crawl_started"],
    }


def report_digest() -> dict:
    od = out_dir()
    if od is None:
        return {"error": "output dir not found"}
    rp = od / "report.json"
    if not rp.exists():
        return {"error": f"report.json not found in {od}"}
    try:
        rep = json.loads(rp.read_text(encoding="utf-8"))
    except ValueError as exc:
        return {"error": f"report.json unparseable: {exc}", "path": str(rp)}
    pages = rep.get("pages") or rep.get("screens") or []
    digest = {"path": str(rp), "mtime": rp.stat().st_mtime, "top_keys": sorted(rep.keys()),
              "page_count": len(pages), "pages": []}
    for p in pages:
        if not isinstance(p, dict):
            continue
        shot = p.get("screenshot_path") or ""
        digest["pages"].append({
            "url": p.get("url"), "title": p.get("title"),
            "http_status": p.get("http_status"),
            "forms": len(p.get("forms") or []),
            "screenshot_path": shot,
            "screenshot_exists": bool(shot) and (pathlib.Path(shot).exists()
                                                 or (od / shot).exists()
                                                 or (REPO / shot).exists()),
            "embedded_frames": p.get("embedded_frames"),
        })
    return digest


def save(name: str, payload: dict) -> None:
    (EV / name).write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str),
                           encoding="utf-8")
    print(f"saved evidence/{name}")
