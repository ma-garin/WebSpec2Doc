"""対検査レビューの版管理: 新版の取り込み・章単位の差分・再レビューが必要な指摘の再計算。

保存先は <docverify>/<iid>/pair/ の docs/（現行版）と docs/history/v<n>/（旧版）。
指摘の状態は decisions.json への追記（by=_system）で戻すので、取消（revoke）の積み上げ規則と矛盾しない。
"""
from __future__ import annotations

import difflib
import re

from web.services.docverify import pair_review as pr

DOCS = (("requirements", "requirements.md", "req_version", "要件定義書"),
        ("design", "design.md", "design_version", "基本設計書"))
MAX_BYTES = 2 * 1024 * 1024
REOPEN_FROM = ("採用", "解消済み")
SYSTEM = "_system"
_HEAD = re.compile(r"^(#{2,3})\s+(.+)$")
_NUM = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+\S")


# ---- 章の分割（表示用。## / ### / 「1.」「1.1」） ----
def split_sections(md: str) -> list[dict]:
    out, cur = [], None
    for line in (md or "").splitlines():
        m = _HEAD.match(line)
        heading = m.group(2).strip() if m else (line.strip() if _NUM.match(line) else None)
        if heading is not None:
            n = _NUM.match(heading)
            key = f"s{n.group(1)}" if n else f"h:{heading}"
            cur = {"id": key, "heading": heading, "lines": []}
            out.append(cur)
        elif cur is not None:
            cur["lines"].append(line)
    return [{"id": s["id"], "heading": s["heading"], "text": "\n".join(s["lines"]).strip()} for s in out]


def _clip(lines: list[str], n: int = 200) -> str:
    s = " / ".join(ln.strip() for ln in lines if ln.strip())
    return s if len(s) <= n else s[:n - 1] + "…"


def _changed_lines(a: str, b: str) -> tuple[str, str]:
    al, bl = a.splitlines(), b.splitlines()
    rm, add = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, al, bl).get_opcodes():
        if tag != "equal":
            rm += al[i1:i2]
            add += bl[j1:j2]
    return _clip(rm), _clip(add)


def section_diff(old: str, new: str) -> list[dict]:
    o = {s["id"]: s for s in split_sections(old)}
    n = split_sections(new)
    out = []
    for s in n:
        p = o.pop(s["id"], None)
        if p is None:
            out.append({"id": s["id"], "heading": s["heading"], "change": "追加", "before_excerpt": "", "after_excerpt": _clip(s["text"].splitlines())})
        elif p["text"] != s["text"] or p["heading"] != s["heading"]:
            before, after = _changed_lines(p["heading"] + "\n" + p["text"], s["heading"] + "\n" + s["text"])
            out.append({"id": s["id"], "heading": s["heading"], "change": "変更", "before_excerpt": before, "after_excerpt": after})
    out += [{"id": p["id"], "heading": p["heading"], "change": "削除", "before_excerpt": _clip(p["text"].splitlines()), "after_excerpt": ""}
            for p in o.values()]
    return out


def top_changed(old: str, new: str) -> list[str]:
    """指摘の req_ref / design_ref と同じ粒度（pair_review.parse_sections の ## 単位）で変わった章。"""
    prev = {s["id"]: (s["heading"], s["text"]) for s in pr.parse_sections(old)}
    cur = pr.parse_sections(new)
    gone = set(prev) - {s["id"] for s in cur}
    return [s["id"] for s in cur if prev.get(s["id"]) != (s["heading"], s["text"])] + sorted(gone)


# ---- 版の読み出し ----
def _version_text(d, name: str, key: str, v: int) -> str | None:
    meta = pr._read(d / "docs" / "meta.json", {})
    cur = int(meta.get(key) or 1)
    p = d / "docs" / name if v == cur else d / "docs" / "history" / f"v{v}" / name
    return p.read_text(encoding="utf-8") if 1 <= v <= cur and p.exists() else None


def _summary(parts: list[dict]) -> str:
    out = []
    for p in parts:
        c = {k: sum(1 for s in p["sections"] if s["change"] == k) for k in ("変更", "追加", "削除")}
        total = sum(c.values())
        if total:
            out.append(f"{p['label']}は v{p['from']}→v{p['to']} で {total} 章が変わりました（変更 {c['変更']}・追加 {c['追加']}・削除 {c['削除']}）。")
        else:
            out.append(f"{p['label']}は v{p['from']}→v{p['to']} で章の変更はありません。")
    return "".join(out[:2]) or "比較できる版がありません。"


def diff(iid: str, frm=None, to=None) -> dict:
    d = pr._existing(iid)
    meta = pr._read(d / "docs" / "meta.json", {})
    try:
        frm = int(frm) if frm not in (None, "") else None
        to = int(to) if to not in (None, "") else None
    except (TypeError, ValueError):
        raise pr.PairError(400, "bad_version", "版の番号は数字で指定してください。")
    parts, sections = [], []
    for doc, name, key, label in DOCS:
        cur = int(meta.get(key) or 1)
        t = to if to is not None else cur
        f = frm if frm is not None else t - 1
        if f >= t:
            continue
        a, b = _version_text(d, name, key, f), _version_text(d, name, key, t)
        if a is None or b is None:
            continue
        secs = [{**s, "doc": doc} for s in section_diff(a, b)]
        parts.append({"doc": doc, "label": label, "from": f, "to": t, "sections": secs})
        sections += secs
    if not parts:
        raise pr.PairError(404, "version_not_found", "比較できる版がありません。新しい版をアップロードしてから開いてください。")
    return {"summary": _summary(parts), "sections": sections,
            "versions": [{k: p[k] for k in ("doc", "label", "from", "to")} for p in parts]}


# ---- 新版の取り込み ----
def _decode(raw: bytes, label: str) -> str:
    if not raw:
        raise pr.PairError(400, "empty_file", f"{label}のファイルが空です。中身のあるファイルを選んでください。")
    if len(raw) > MAX_BYTES:
        raise pr.PairError(400, "too_large", f"{label}が 2MB を超えています。Markdown の本文だけにして選び直してください。")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise pr.PairError(400, "bad_encoding", f"{label}を読めませんでした。UTF-8 の Markdown（.md）で保存して選び直してください。")
    if not pr.parse_sections(text):
        raise pr.PairError(400, "no_sections", f"{label}に「## 1. 見出し」の形の章がありません。章見出しを付けて選び直してください。")
    return text


def _reopen(d, changed: dict, fresh: dict, versions: dict, user: str) -> tuple[list[str], list[str]]:
    """changed = 各文書の最新の版上げで変わった章（今回の変更分の範囲）。fresh = 今回のアップロードで変わった章（要確認へ戻す範囲）。"""
    findings = pr._findings(d)
    decisions = pr._decisions(d)
    marked, hit, reopened = [], [], []
    for f in findings:
        rs, ds = (f.get("req_ref") or {}).get("section"), (f.get("design_ref") or {}).get("section")
        on_req, on_des = rs in changed["requirements"], ds in changed["design"]
        marked.append({**f, "changed_in_current": on_req or on_des})
        if not (on_req or on_des):
            continue
        hit.append(f["id"])
        new_req, new_des = rs in fresh["requirements"], ds in fresh["design"]
        if (new_req or new_des) and f.get("status") in REOPEN_FROM:
            v = versions["req_version"] if new_req else versions["design_version"]
            reason = f"版 v{v} で該当章が変更"
            decisions.append({"finding_id": f["id"], "status": "要確認", "by": SYSTEM, "at": pr._now(), "reason": reason, "auto": True})
            reopened.append((f["id"], f.get("status"), reason))
    pr._write(d / "decisions.json", decisions)
    pr._write(d / "findings.json", pr._replay(marked, decisions))
    for fid, before, reason in reopened:
        pr._trail(d, user, "finding_reopened", fid, f"{reason}（{before}→要確認）")
    return hit, [r[0] for r in reopened]


def upload(iid: str, files: dict, user: str, rev=None) -> dict:
    """files = {"requirements": bytes, "design": bytes}（どちらか片方でよい）。"""
    texts = {doc: _decode(files[doc], label) for doc, _n, _k, label in DOCS if files.get(doc) is not None}
    if not texts:
        raise pr.PairError(400, "files_required", "要件定義書か基本設計書の新しい版を選んでください。")
    d = pr._existing(iid)
    with pr._lock(d):
        pr._check_rev(d, rev)
        meta = pr._read(d / "docs" / "meta.json", {})
        prior = meta.get("changed_sections") or {}
        changed = {doc: list(prior.get(doc) or []) for doc, *_ in DOCS}
        fresh = {doc: [] for doc, *_ in DOCS}
        notes = []
        for doc, name, key, label in DOCS:
            if doc not in texts:
                continue
            cur_p = d / "docs" / name
            old = cur_p.read_text(encoding="utf-8") if cur_p.exists() else ""
            v = int(meta.get(key) or 1)
            hist = d / "docs" / "history" / f"v{v}"
            hist.mkdir(parents=True, exist_ok=True)
            (hist / name).write_text(old, encoding="utf-8")
            cur_p.write_text(texts[doc], encoding="utf-8")
            meta[key] = v + 1
            changed[doc] = fresh[doc] = top_changed(old, texts[doc])
            notes.append(f"{label} v{v}→v{v + 1}（変わった章 {len(changed[doc])}）")
        meta["changed_sections"] = changed
        pr._write(d / "docs" / "meta.json", meta)
        pr._trail(d, user, "version_uploaded", pr.resolve_iid(iid), "、".join(notes))
        hit, reopened = _reopen(d, changed, fresh, meta, user)
    return {"req_version": meta.get("req_version"), "design_version": meta.get("design_version"),
            "changed_sections": changed, "changed_findings": hit, "reopened": reopened,
            "rev": pr.rev_of(d), "diff": diff(iid)}
