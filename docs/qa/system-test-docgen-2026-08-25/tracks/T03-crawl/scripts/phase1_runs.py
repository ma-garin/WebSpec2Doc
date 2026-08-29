"""T03 phase1: RUN-G(format/compare初回) → A(selected5) → B(auto max_pages) → B2(depth) → B3(shadow) → C1/C2/C3(parallelism)."""
from __future__ import annotations

import json

from st_lib import MOCK, out_dir, post, report_digest, run_stream, save

results: dict = {}

# RUN-G: 初回 compare=true + format 許可リスト外(C044/C045)。完了後 run_id で cancel(C020)。
g = run_stream("G", {
    "urls": f"{MOCK}/about", "crawl_mode": "selected", "parallelism": "1",
    "format": "exe,../x", "compare": "true",
})
g["report_digest"] = report_digest()
od = out_dir()
g["out_dir_entries"] = sorted(p.name for p in od.iterdir()) if od else None
try:
    g["cancel_after_complete"] = post("/api/cancel", {"run_id": g["run_id"]})
except Exception as exc:  # noqa: BLE001
    g["cancel_after_complete"] = f"EXC:{exc}"
results["G"] = g
print("G:", g["duration_sec"], "s summary=", g["summary"], "cancel_after=", g["cancel_after_complete"])

# RUN-A: selected 5URL (C001-C005)
five = [f"{MOCK}{p}" for p in ("/", "/about", "/products", "/contact", "/form")]
a = run_stream("A", {"urls": ",".join(five), "crawl_mode": "selected",
                     "parallelism": "4", "format": "md,html"})
a["report_digest"] = report_digest()
results["A"] = a
print("A:", a["duration_sec"], "s summary=", a["summary"])

# RUN-B: auto / depth2 max_pages10 (C006-C008)
b = run_stream("B", {"urls": f"{MOCK}/", "crawl_mode": "auto", "depth": "2",
                     "max_pages": "10", "parallelism": "4", "format": "md,html"})
b["report_digest"] = report_digest()
results["B"] = b
print("B:", b["duration_sec"], "s summary=", b["summary"], "pages=", len(b["page_started_urls"]))

# RUN-B2: auto /deep/1 depth2 (C009-C010)
b2 = run_stream("B2", {"urls": f"{MOCK}/deep/1", "crawl_mode": "auto", "depth": "2",
                       "max_pages": "10", "parallelism": "4", "format": "md,html"})
b2["report_digest"] = report_digest()
results["B2"] = b2
print("B2:", b2["duration_sec"], "s crawled=", b2["page_started_urls"])

# RUN-B3: auto /shadow depth2 (C032-C033)
b3 = run_stream("B3", {"urls": f"{MOCK}/shadow", "crawl_mode": "auto", "depth": "2",
                       "max_pages": "10", "parallelism": "4", "format": "md,html"})
b3["report_digest"] = report_digest()
results["B3"] = b3
print("B3:", b3["duration_sec"], "s crawled=", b3["page_started_urls"])

# RUN-C1/C2/C3: parallelism 1/4/8 同一集合 (C011-C013)
six = [f"{MOCK}{p}" for p in ("/", "/about", "/products", "/products/1", "/contact", "/form")]
for tag, par in (("C1", "1"), ("C2", "4"), ("C3", "8")):
    c = run_stream(tag, {"urls": ",".join(six), "crawl_mode": "selected",
                         "parallelism": par, "format": "md,html"})
    c["report_digest"] = report_digest()
    results[tag] = c
    print(f"{tag}: {c['duration_sec']}s summary={c['summary']}")

cmp_keys = ("screens", "forms", "fields", "buttons")
results["_parallelism_compare"] = {
    tag: {k: (results[tag]["summary"] or {}).get(k) for k in cmp_keys} for tag in ("C1", "C2", "C3")
}
save("phase1-analysis.json", results)
print("COMPARE:", json.dumps(results["_parallelism_compare"], ensure_ascii=False))
