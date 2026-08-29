#!/usr/bin/env python3
"""T01 evidence 解析: SSE/JSON 証跡から判定材料を集計して表示する（再現用・納品物）。"""
import json
from pathlib import Path

EV = Path(__file__).resolve().parent.parent / "evidence"


def sse_events(name):
    p = EV / f"{name}.log"
    evs = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("data: "):
            try:
                evs.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                evs.append({"_raw": line})
    return evs


def sse_summary(name, show_events=False):
    evs = sse_events(name)
    kinds = [next((k for k in ("run_id", "crawl_event", "page", "done", "error", "cancelled") if k in e), "?") for e in evs]
    pages = [e["page"] for e in evs if "page" in e]
    done = next((e for e in evs if "done" in e), None)
    err = next((e for e in evs if "error" in e), None)
    print(f"{name}: pages={len(pages)} total={(done or {}).get('total')} first={kinds[0] if kinds else '-'} last={kinds[-1] if kinds else '-'} error={err}")
    print(f"  seq={'>'.join(kinds)}")
    lw = [(p.get("url"), p.get("login_reasons"), p.get("login_url")) for p in pages if p.get("login_required")]
    if lw:
        print(f"  login_wall={lw}")
    print(f"  urls={[p.get('url') for p in pages]}")
    if show_events:
        for e in evs:
            if "crawl_event" in e:
                print(f"  crawl_event={e['crawl_event']}")
    return pages


def sync_summary(name):
    raw = (EV / f"{name}.json").read_text(encoding="utf-8")
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        print(f"{name}: NON-JSON raw={raw[:120]!r}")
        return []
    pages = d.get("pages", [])
    print(f"{name}: pages={len(pages)} error={d.get('error')!r}")
    print(f"  urls={[p.get('url') for p in pages]}")
    return pages


print("== SSE 正常系 ==")
sse_summary("C001")
sse_summary("C002")
print("== 同期正常系・境界値 ==")
u = {}
for n in ("C003", "C004a", "C004b", "C004c", "C004d", "C005a", "C005b", "C005c", "C005d"):
    u[n] = {p.get("url") for p in sync_summary(n)}
print(f"CMP depth0==depth1: {u['C004a'] == u['C004b']}")
print(f"CMP depth11==depth10: {u['C004c'] == u['C004d']} deep8_in_11={any('/deep/8' in x for x in u['C004c'])}")
print(f"CMP mp501==mp500: {u['C005c'] == u['C005d']}")
print("== parallelism 境界 ==")
pa = {p.get("url") for p in sse_summary("C006a")}
pb = {p.get("url") for p in sse_summary("C006b")}
print(f"CMP para0==para9: {pa == pb}")
print("== invalid_url ==")
for n in ("C007", "C008", "C009", "C010"):
    raw = (EV / f"{n}.json").read_text(encoding="utf-8")
    print(f"{n}: raw={raw[:160]!r}")
print(f"C007s: raw={(EV / 'C007s.log').read_text(encoding='utf-8')[:160]!r}")
sse_summary("C008s")
print("== login_wall ==")
c011 = sse_summary("C011")
sse_summary("C012", show_events=True)
print("== restricted_url ==")
sse_summary("C013", show_events=True)
priv = [p.get("url") for p in c011 if "/private" in (p.get("url") or "")]
print(f"C011 private_in_pages={priv}")
secret_hits = [f.name for f in sorted(EV.iterdir()) if f.suffix in (".log", ".json") and "SECRET-DO-NOT-CRAWL" in f.read_text(encoding="utf-8", errors="replace")]
print(f"SECRET-DO-NOT-CRAWL in evidence: {secret_hits}")
print("== timeout 系 ==")
sse_summary("C015a")
sse_summary("C015b")
print("== Intellectual Tour ==")
for n in ("C016", "C017", "C018"):
    for p in sync_summary(n):
        print(f"  {n} title={p.get('title')!r}")
