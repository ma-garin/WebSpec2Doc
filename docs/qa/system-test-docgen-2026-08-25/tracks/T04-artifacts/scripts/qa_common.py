"""T04 共通ヘルパ。"""
import json, urllib.request, urllib.error, pathlib
BASE = "http://127.0.0.1:8765"
DOM = "127.0.0.1:9104"
QDOM = "127.0.0.1%3A9104"
OUT = pathlib.Path("output/127.0.0.1:9104")
EV = pathlib.Path("docs/qa/system-test-docgen-2026-08-25/tracks/T04-artifacts/evidence")
RESULTS = []

def http(path, method="GET", data=None):
    req = urllib.request.Request(BASE + path, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:  # noqa: BLE001
        return -1, str(e).encode()

def jget(path):
    st, body = http(path)
    try:
        return st, json.loads(body)
    except ValueError:
        return st, {"_raw": body[:300].decode("utf-8", "replace")}

def check(cid, ok, detail):
    RESULTS.append((cid, "PASS" if ok else "FAIL", detail))
    print(f"{cid}: {'PASS' if ok else 'FAIL'} — {detail}")

def report_aggregate(report):
    screens = report.get("screens", [])
    forms = sum(len(s.get("forms", [])) for s in screens)
    fields = sum(len(f.get("fields", [])) for s in screens for f in s.get("forms", []))
    buttons = sum(len(s.get("buttons", [])) for s in screens)
    return {"screens": len(screens), "forms": forms, "fields": fields, "buttons": buttons}

def save(name, obj):
    (EV / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
