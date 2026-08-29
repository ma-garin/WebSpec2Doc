#!/usr/bin/env python3
"""T08 性能計測: POST /run（selected クロール）の RUN_ID -> SUMMARY 時間。

--sample-domain 指定時は RUN_ID 受信の 3 秒後に 1 回だけ、
  - ps によるプロセス CPU/メモリの 1 点サンプリング（app.py / chromium / playwright）
  - /api/live-screenshot のレイテンシ 3 回計測
を実行中クロールに対して行う（サンプリング実行はクロール時間の統計から除外する運用）。
"""
import argparse
import json
import statistics
import subprocess
import threading
import time
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8765"


def sample_resources(domain, out):
    time.sleep(3)
    try:
        ps = subprocess.run(
            ["ps", "-axo", "pid,ppid,%cpu,%mem,rss,etime,command"],
            capture_output=True, text=True, timeout=10,
        ).stdout
        keys = ("app.py", "playwright", "chromium", "headless")
        out["ps_sample"] = [
            l for l in ps.splitlines()
            if any(k in l.lower() for k in keys) and "grep" not in l
        ]
    except Exception as e:  # noqa: BLE001
        out["ps_error"] = repr(e)
    lat = []
    for _ in range(3):
        t0 = time.monotonic()
        try:
            r = urllib.request.urlopen(
                BASE + "/api/live-screenshot?domain=" + urllib.parse.quote(domain),
                timeout=30,
            )
            body = r.read()
            lat.append({"s": round(time.monotonic() - t0, 3), "status": r.status,
                        "bytes": len(body)})
        except urllib.error.HTTPError as e:
            lat.append({"s": round(time.monotonic() - t0, 3), "status": e.code})
        except Exception as e:  # noqa: BLE001
            lat.append({"s": round(time.monotonic() - t0, 3), "error": repr(e)})
    out["live_screenshot"] = lat


def one_run(urls, parallelism, timeout, raw_fh, sample_domain=None):
    form = {
        "urls": ",".join(urls),
        "crawl_mode": "selected",
        "parallelism": str(parallelism),
        "format": "md",
        "depth": "1",
        "max_pages": "50",
        "auth": "",
    }
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(BASE + "/run", data=data)
    t_send = time.monotonic()
    t_runid = t_summary = None
    run_id = report_path = summary_obj = None
    sample_out = {}
    th = None
    resp = urllib.request.urlopen(req, timeout=timeout)
    for raw in resp:
        line = raw.decode("utf-8", "replace").rstrip("\n")
        raw_fh.write(f"{time.monotonic() - t_send:9.3f} {line}\n")
        if line.startswith("RUN_ID:") and t_runid is None:
            t_runid = time.monotonic()
            run_id = line.split(":", 1)[1].strip()
            if sample_domain:
                th = threading.Thread(
                    target=sample_resources, args=(sample_domain, sample_out)
                )
                th.start()
        elif line.startswith("REPORT_PATH:"):
            report_path = line.split(":", 1)[1].strip()
        elif line.startswith("SUMMARY:") and t_summary is None:
            t_summary = time.monotonic()
            try:
                summary_obj = json.loads(line.split(":", 1)[1])
            except (json.JSONDecodeError, IndexError):
                summary_obj = line
    resp.close()
    if th:
        th.join(timeout=60)
    return {
        "run_id": run_id,
        "n_urls": len(urls),
        "t_req_to_runid_s": round(t_runid - t_send, 3) if t_runid else None,
        "dur_runid_to_summary_s": (
            round(t_summary - t_runid, 3) if t_summary and t_runid else None
        ),
        "wall_s": round(time.monotonic() - t_send, 3),
        "summary": summary_obj,
        "report_path": report_path,
        "sample": sample_out or None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--urls", required=True, help="カンマ区切り")
    ap.add_argument("--parallelism", type=int, default=4)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=420)
    ap.add_argument("--label", required=True)
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--sample-domain", default=None)
    a = ap.parse_args()
    urls = [u.strip() for u in a.urls.split(",") if u.strip()]

    results = []
    with open(a.evidence, "a") as fh:
        fh.write(
            f"\n===== label={a.label} n_urls={len(urls)} parallelism={a.parallelism} "
            f"sample={bool(a.sample_domain)} "
            f"started={time.strftime('%Y-%m-%d %H:%M:%S')} =====\n"
        )
        for i in range(a.repeats):
            fh.write(f"--- run {i + 1}/{a.repeats} ---\n")
            try:
                r = one_run(urls, a.parallelism, a.timeout, fh, a.sample_domain)
            except Exception as e:  # noqa: BLE001
                r = {"error": repr(e)}
            r["run_index"] = i + 1
            results.append(r)
            print(f"RUN {a.label} #{i + 1}: {json.dumps(r, ensure_ascii=False)}")

        durs = [
            r["dur_runid_to_summary_s"] for r in results
            if r.get("dur_runid_to_summary_s")
        ]
        summary = {
            "label": a.label,
            "n_ok": len(durs),
            "median_dur_s": round(statistics.median(durs), 3) if durs else None,
            "min_dur_s": min(durs) if durs else None,
            "max_dur_s": max(durs) if durs else None,
        }
        if durs:
            summary["median_throughput_pages_per_s"] = round(
                len(urls) / statistics.median(durs), 3
            )
        fh.write("SUMMARY " + json.dumps(summary, ensure_ascii=False) + "\n")
        print("MEDIAN " + json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
