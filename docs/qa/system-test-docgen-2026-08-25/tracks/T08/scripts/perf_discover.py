#!/usr/bin/env python3
"""T08 性能計測: /api/discover-stream の応答時間・SSE 遅延計測。

計測点:
  - t_req_to_runid_s      : リクエスト送信 -> run_id 受信
  - ttfe_runid_to_first_page_s : run_id 受信 -> 最初の page イベント（SSE time-to-first-event）
  - dur_runid_to_done_s   : run_id 受信 -> done イベント（主指標）
n>=3 で実行し中央値を出す。生ストリームは evidence ファイルへ相対時刻付きで追記する。
"""
import argparse
import json
import statistics
import time
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8765"


def one_run(url, depth, max_pages, parallelism, timeout, raw_fh):
    form = {
        "url": url,
        "depth": str(depth),
        "max_pages": str(max_pages),
        "parallelism": str(parallelism),
        "auth": "",
    }
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(BASE + "/api/discover-stream", data=data)
    t_send = time.monotonic()
    t_runid = t_first_page = t_done = None
    run_id = None
    pages = 0
    total = None
    resp = urllib.request.urlopen(req, timeout=timeout)
    status = resp.status
    for raw in resp:
        line = raw.decode("utf-8", "replace").rstrip("\n")
        raw_fh.write(f"{time.monotonic() - t_send:9.3f} {line}\n")
        if not line.startswith("data: "):
            continue
        try:
            obj = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        if "run_id" in obj and t_runid is None:
            t_runid = time.monotonic()
            run_id = obj["run_id"]
        elif "page" in obj:
            pages += 1
            if t_first_page is None:
                t_first_page = time.monotonic()
        elif obj.get("done"):
            t_done = time.monotonic()
            total = obj.get("total")
            break
    resp.close()
    wall = time.monotonic() - t_send
    return {
        "status": status,
        "run_id": run_id,
        "pages_events": pages,
        "done_total": total,
        "t_req_to_runid_s": round(t_runid - t_send, 3) if t_runid else None,
        "ttfe_runid_to_first_page_s": (
            round(t_first_page - t_runid, 3) if t_first_page and t_runid else None
        ),
        "dur_runid_to_done_s": (
            round(t_done - t_runid, 3) if t_done and t_runid else None
        ),
        "wall_s": round(wall, 3),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--depth", type=int, default=1)
    ap.add_argument("--max-pages", type=int, default=5)
    ap.add_argument("--parallelism", type=int, default=4)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=200)
    ap.add_argument("--label", required=True)
    ap.add_argument("--evidence", required=True)
    a = ap.parse_args()

    results = []
    with open(a.evidence, "a") as fh:
        fh.write(
            f"\n===== label={a.label} url={a.url} depth={a.depth} "
            f"max_pages={a.max_pages} parallelism={a.parallelism} "
            f"started={time.strftime('%Y-%m-%d %H:%M:%S')} =====\n"
        )
        for i in range(a.repeats):
            fh.write(f"--- run {i + 1}/{a.repeats} ---\n")
            try:
                r = one_run(a.url, a.depth, a.max_pages, a.parallelism, a.timeout, fh)
            except Exception as e:  # noqa: BLE001 - 計測は継続する
                r = {"error": repr(e)}
            r["run_index"] = i + 1
            results.append(r)
            print(f"RUN {a.label} #{i + 1}: {json.dumps(r, ensure_ascii=False)}")

        durs = [r["dur_runid_to_done_s"] for r in results if r.get("dur_runid_to_done_s")]
        ttfes = [
            r["ttfe_runid_to_first_page_s"]
            for r in results
            if r.get("ttfe_runid_to_first_page_s")
        ]
        summary = {
            "label": a.label,
            "n_ok": len(durs),
            "median_dur_s": round(statistics.median(durs), 3) if durs else None,
            "min_dur_s": min(durs) if durs else None,
            "max_dur_s": max(durs) if durs else None,
            "median_ttfe_s": round(statistics.median(ttfes), 3) if ttfes else None,
        }
        pairs = [
            (r["dur_runid_to_done_s"], r.get("done_total") or r.get("pages_events"))
            for r in results
            if r.get("dur_runid_to_done_s")
        ]
        per_page = [d / p for d, p in pairs if p]
        if per_page:
            summary["median_s_per_page"] = round(statistics.median(per_page), 3)
        fh.write("SUMMARY " + json.dumps(summary, ensure_ascii=False) + "\n")
        print("MEDIAN " + json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
