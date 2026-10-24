"""対検査レビュー（要件定義書 ⇔ 基本設計書）の保存・判定・証跡・承認規則。

契約: docs/s06/CONTRACT.md。保存先は <docverify>/<iid>/pair/ 配下の新規ファイルだけ（既存 JSON は触らない）。
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

_IID = re.compile(r"^[a-z0-9-]{3,64}$")
_FID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
TYPES = ("矛盾", "欠落", "曖昧", "不整合ID", "重複", "用語揺れ")
SEVERITIES = ("重大", "警告", "提案")
STATUSES = ("採用", "不採用", "要確認", "解消済み")
RESOLVED = ("不採用", "解消済み")
NONE_USER = "_none"
SYSTEM_USERS = ("_none", "_seed")
_REQ_ID = re.compile(r"REQ-[A-Z]+-\d{3}")
_RANGE = re.compile(r"(REQ-[A-Z]+-)(\d{3})〜(?:REQ-[A-Z]+-)?(\d{3})")
_ENGINE_TYPE = {"MISSING_IN_DESIGN": "欠落", "EXTRA_IN_DESIGN": "不整合ID", "CONTRADICTION": "矛盾",
                "TABLE_MISMATCH": "不整合ID", "TERM_INCONSISTENCY": "用語揺れ"}


class PairError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def check_iid(iid: str) -> str:
    """対検査用の iid 検証（既存 store の 12 桁 16 進とは別。2026-10-24 指揮官決定）。"""
    if not isinstance(iid, str) or not _IID.match(iid):
        raise PairError(404, "not_found", "レビューが見つかりません。レビュー一覧から開き直してください。")
    return iid


def pair_dir(iid: str) -> Path:
    """保存先は自前で解決する。テナント有効時は data/tenants/<t>/docverify/<iid>/pair/。"""
    from web import config
    from web.tenancy import scoped_output_dir
    return scoped_output_dir(config.DATA_DIR) / "docverify" / check_iid(iid) / "pair"


def resolve_iid(iid: str) -> str:
    """一覧の inspection ID で開かれたときは、pair/docs/meta.json の inspection_id から対検査の iid へ読み替える。"""
    d = pair_dir(iid)
    if (d / "findings.json").exists():
        return iid
    root = d.parent.parent
    if root.exists():
        for meta in root.glob("*/pair/docs/meta.json"):
            try:
                if json.loads(meta.read_text(encoding="utf-8")).get("inspection_id") == iid:
                    return meta.parent.parent.parent.name
            except (OSError, ValueError):
                continue
    return iid


def _existing(iid: str) -> Path:
    d = pair_dir(resolve_iid(iid))
    if not (d / "findings.json").exists():
        raise PairError(404, "not_found", "レビューが見つかりません。レビュー一覧から開き直してください。")
    return d


def _read(path: Path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


@contextmanager
def _lock(d: Path):
    d.mkdir(parents=True, exist_ok=True)
    with (d / ".lock").open("w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def current_user() -> str:
    """認証オフは "_none"。オンは web.auth の auth_guard が g.auth_user に入れた利用者名。"""
    from web.auth import auth_enabled
    from web.services.docverify.settings import current_user as _name
    if not auth_enabled():
        return NONE_USER
    name = _name()
    return NONE_USER if name == "ゲスト" else name


# ---- 文書 ----
def parse_sections(md: str) -> list[dict]:
    sections, cur = [], None
    for line in md.splitlines():
        if line.startswith("## "):
            heading = line[3:].strip()
            m = re.match(r"(\d+)\.", heading)
            cur = {"id": f"s{m.group(1)}" if m else f"s{len(sections) + 1}", "heading": heading, "text": ""}
            sections.append(cur)
        elif cur is not None:
            cur["text"] += line + "\n"
    return [{**s, "text": s["text"].strip()} for s in sections]


def _doc_text(d: Path, name: str) -> str:
    p = d / "docs" / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def docs(iid: str) -> dict:
    d = _existing(iid)
    meta = _read(d / "docs" / "meta.json", {})
    return {"requirements": {"version": meta.get("req_version"), "sections": parse_sections(_doc_text(d, "requirements.md"))},
            "design": {"version": meta.get("design_version"), "sections": parse_sections(_doc_text(d, "design.md"))}}


def _ref(sections: list[dict], label: str) -> dict:
    """「4. API（API-A-02 与信タイムアウト60秒）」→ 該当節と、その節の中の引用 1 行。"""
    m = re.match(r"\s*(\d+)\.", label or "")
    sec = next((s for s in sections if m and s["id"] == f"s{m.group(1)}"), None)
    if sec is None:
        return {"section": None, "quote": ""}
    hints = re.findall(r"[A-Z]+-[A-Z]+-\d+|\d+(?:日|秒|分|円|%)", label)
    lines = [ln.strip() for ln in sec["text"].splitlines() if ln.strip()]
    quote = next((ln for h in hints for ln in lines if h in ln), lines[0] if lines else "")
    return {"section": sec["id"], "quote": quote}


# ---- 指摘・採否 ----
def _findings(d: Path) -> list[dict]:
    return _read(d / "findings.json", [])


def _decisions(d: Path) -> list[dict]:
    return _read(d / "decisions.json", [])


def rev_of(d: Path) -> int:
    return len(_decisions(d))


def _replay(findings: list[dict], decisions: list[dict]) -> list[dict]:
    stacks: dict[str, list[dict]] = {}
    for dec in decisions:
        st = stacks.setdefault(dec["finding_id"], [])
        if dec.get("revoke"):
            if st:
                st.pop()
        else:
            st.append(dec)
    out = []
    for f in findings:
        base = {**f, "initial_status": f.get("initial_status", f.get("status"))}
        last = (stacks.get(f["id"]) or [None])[-1]
        out.append({**base, "status": last["status"] if last else base["initial_status"],
                    "decided_by": last["by"] if last else None, "decided_at": last["at"] if last else None})
    return out


def _active(d: Path, fid: str) -> bool:
    depth = 0
    for dec in _decisions(d):
        if dec["finding_id"] == fid:
            depth = max(depth - 1, 0) if dec.get("revoke") else depth + 1
    return depth > 0


def _trail(d: Path, user: str, action: str, target: str, reason: str = "") -> dict:
    entry = {"at": _now(), "user": user, "action": action, "target": target, "reason": reason}
    _write(d / "trail.json", [*_read(d / "trail.json", []), entry])
    return entry


def trail(iid: str) -> list[dict]:
    return _read(_existing(iid) / "trail.json", [])


def _check_rev(d: Path, rev) -> None:
    if rev is not None and str(rev) != str(rev_of(d)):
        raise PairError(409, "conflict", "他の人が先に更新しました。再読み込みしてから操作し直してください。")


def _target(d: Path, fid: str) -> None:
    if not _FID.match(fid or "") or all(f["id"] != fid for f in _findings(d)):
        raise PairError(404, "finding_not_found", "指摘が見つかりません。一覧を再読み込みしてください。")


def decide(iid: str, fid: str, status: str, reason: str, user: str, rev=None) -> dict:
    if status not in STATUSES:
        raise PairError(400, "bad_status", "採否は「採用」「不採用」「要確認」「解消済み」から選んでください。")
    if status == "解消済み" and not (reason or "").strip():
        raise PairError(400, "reason_required", "解消済みにするには、文書のどこを直したかを理由に書いてください。")
    d = _existing(iid)
    with _lock(d):
        _check_rev(d, rev)
        _target(d, fid)
        cur = next(f for f in _findings(d) if f["id"] == fid).get("status")
        if status == "解消済み" and cur != "採用":
            raise PairError(409, "bad_transition", f"「{cur or '未判定'}」から解消済みにはできません。先に採用してから解消済みにしてください。")
        dec = {"finding_id": fid, "status": status, "by": user, "at": _now(), "reason": (reason or "").strip()}
        decisions = [*_decisions(d), dec]
        _write(d / "decisions.json", decisions)
        _write(d / "findings.json", _replay(_findings(d), decisions))
        action = "finding_resolved" if status == "解消済み" else "finding_decided"
        _trail(d, user, action, fid, f"{status}: {dec['reason']}".rstrip(": "))
    return dec


def revoke(iid: str, fid: str, user: str, reason: str = "", rev=None) -> dict:
    d = _existing(iid)
    with _lock(d):
        _check_rev(d, rev)
        _target(d, fid)
        if not _active(d, fid):
            raise PairError(400, "nothing_to_revoke", "取り消す採否がありません。先に採否を選んでください。")
        dec = {"finding_id": fid, "status": None, "by": user, "at": _now(), "reason": (reason or "").strip(), "revoke": True}
        decisions = [*_decisions(d), dec]
        _write(d / "decisions.json", decisions)
        _write(d / "findings.json", _replay(_findings(d), decisions))
        _trail(d, user, "decision_revoked", fid, dec["reason"])
    return dec


# ---- 判定 ----
def _req_ids(text: str) -> list[str]:
    ids = set(_REQ_ID.findall(text))
    for pre, a, b in _RANGE.findall(text):
        ids |= {f"{pre}{n:03d}" for n in range(int(a), int(b) + 1)}
    return sorted(ids)


def _missing_links(d: Path, changed_req: set | None) -> list[dict]:
    design = set(_req_ids(_doc_text(d, "design.md")))
    out = []
    for s in parse_sections(_doc_text(d, "requirements.md")):
        if changed_req is not None and s["id"] not in changed_req:
            continue
        out += [{"req_id": r, "reason": "基本設計書に対応する記述が見つからない"}
                for r in _req_ids(s["heading"] + "\n" + s["text"]) if r not in design]
    seen, uniq = set(), []
    for m in out:
        if m["req_id"] not in seen:
            seen.add(m["req_id"])
            uniq.append(m)
    return uniq


def _judge(findings: list[dict], missing: list[dict]) -> dict:
    crit = [f["id"] for f in findings if f["severity"] == "重大" and f.get("status") not in RESOLVED]
    review = [f["id"] for f in findings if f.get("status") == "要確認"]
    unverified = [f["id"] for f in findings if f.get("status") is None]
    return {"pass": not crit and not review and not missing, "unresolved_critical": crit,
            "missing_links": missing, "unverified": unverified, "needs_review": review}


def _reasons(o: dict) -> list[str]:
    if o["pass"]:
        tail = f"未判定の指摘が {len(o['unverified'])} 件残っていますが、合否には影響しません。" if o["unverified"] else "未判定の指摘はありません。"
        return ["重大な未解決の指摘・要確認・対応の抜けはありません。", tail, "承認できます。"]
    parts = []
    if o["unresolved_critical"]:
        parts.append(f"重大な指摘が {len(o['unresolved_critical'])} 件未解決です")
    if o["needs_review"]:
        parts.append(f"要確認が {len(o['needs_review'])} 件あります")
    if o["missing_links"]:
        parts.append(f"設計に対応の無い要件が {len(o['missing_links'])} 件あります")
    return ["、".join(parts) + "。", "これらを解消するまで承認できません。", "該当の指摘を開いて採否を決めてください。"]


def gate(iid: str) -> dict:
    d = _existing(iid)
    findings = _findings(d)
    meta = _read(d / "docs" / "meta.json", {})
    overall = _judge(findings, _missing_links(d, None))
    changed_req = set((meta.get("changed_sections") or {}).get("requirements") or [])
    changed = _judge([f for f in findings if f.get("changed_in_current")], _missing_links(d, changed_req))
    return {"overall": overall, "changed": changed, "reasons": _reasons(overall)}


def creator(d: Path) -> dict | None:
    """起票者 = 最初に findings を読んだ認証済み利用者の review_started（取り込み用の _seed は除く）。"""
    return next((t for t in _read(d / "trail.json", [])
                 if t["action"] == "review_started" and t["user"] not in SYSTEM_USERS), None)


def listing(iid: str, user: str = NONE_USER) -> dict:
    d = _existing(iid)
    if user not in SYSTEM_USERS:
        with _lock(d):
            if creator(d) is None:
                _trail(d, user, "review_started", iid, "レビューを開始")
    meta = {**_read(d / "docs" / "meta.json", {}), "rev": rev_of(d)}
    return {"findings": _findings(d), "gate": gate(iid), "meta": meta}


# ---- 承認 ----
def approve(iid: str, reason: str, user: str, rev=None) -> dict:
    d = _existing(iid)
    if user == NONE_USER:
        raise PairError(403, "auth_required", "承認にはログインが必要です。ログインしてから承認してください。")
    if not (reason or "").strip():
        raise PairError(400, "reason_required", "承認の理由を入力してください。")
    with _lock(d):
        _check_rev(d, rev)
        g = gate(iid)
        if not g["overall"]["pass"]:
            raise PairError(403, "gate_not_passed", "判定が不合格のため承認できません。" + g["reasons"][-1])
        started = creator(d)
        if started and started["user"] == user:
            from web.services.approval_policy import self_approval_note
            if self_approval_note() is None:
                raise PairError(403, "same_person", "起票者は自分のレビューを承認できません。別の承認者に依頼してください。")
        if started is None:
            raise PairError(403, "no_author", "起票者が記録されていません。起票者がレビューを開いてから承認してください。")
        return _trail(d, user, "approved", iid, reason.strip())


# ---- 取り込み・既存の対検査ロジックへの接続 ----
def _write_docs(d: Path, req: str, design: str, prev_req: str | None, prev_design: str | None) -> dict:
    def changed(cur: str, prev: str | None) -> list[str]:
        if prev is None:
            return []
        old = {s["id"]: s["text"] for s in parse_sections(prev)}
        return [s["id"] for s in parse_sections(cur) if old.get(s["id"]) != s["text"]]
    (d / "docs").mkdir(parents=True, exist_ok=True)
    (d / "docs" / "requirements.md").write_text(req, encoding="utf-8")
    (d / "docs" / "design.md").write_text(design, encoding="utf-8")
    meta = {"req_version": 2 if prev_req is not None else 1, "design_version": 2 if prev_design is not None else 1,
            "changed_sections": {"requirements": changed(req, prev_req), "design": changed(design, prev_design)}}
    _write(d / "docs" / "meta.json", meta)
    return meta


def _is_changed(f: dict, meta: dict) -> bool:
    cs = meta["changed_sections"]
    return f["req_ref"]["section"] in cs["requirements"] or f["design_ref"]["section"] in cs["design"]


def seed(iid: str, src: Path, by: str, prev: Path | None = None) -> dict:
    """src の spec_requirements.md・spec_design.md・known_defects.jsonl を取り込む。prev があれば前版として差分を取る。"""
    d = pair_dir(iid)
    if (d / "findings.json").exists():
        raise PairError(409, "exists", "同じレビューがすでにあります。別の名前で取り込んでください。")
    req, design = (src / "spec_requirements.md").read_text(encoding="utf-8"), (src / "spec_design.md").read_text(encoding="utf-8")
    pv = (lambda n: (prev / n).read_text(encoding="utf-8") if prev and (prev / n).exists() else None)
    meta = _write_docs(d, req, design, pv("spec_requirements.md"), pv("spec_design.md"))
    rs, ds = parse_sections(req), parse_sections(design)
    findings = []
    for line in (src / "known_defects.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line) if line.strip() else {}
        if "id" not in row:
            continue
        refs = {row["location"].get("doc"): row["location"], row["counterpart"].get("doc"): row["counterpart"]}
        f = {"id": row["id"], "type": row["type"] if row["type"] in TYPES else "曖昧",
             "severity": row.get("severity") if row.get("severity") in SEVERITIES else "警告", "source": "ai",
             "title": row["description"].split("。")[0][:40], "description": row["description"],
             "req_ref": _ref(rs, (refs.get("spec_requirements.md") or {}).get("section", "")),
             "design_ref": _ref(ds, (refs.get("spec_design.md") or {}).get("section", "")),
             "status": None, "decided_by": None, "decided_at": None}
        findings.append({**f, "changed_in_current": _is_changed(f, meta)})
    _write(d / "findings.json", findings)
    _write(d / "decisions.json", [])
    _write(d / "trail.json", [])
    _trail(d, by, "review_started", iid, f"指摘 {len(findings)} 件を取り込み")
    inspection_id = register_inspection(iid)
    return {"iid": iid, "findings": len(findings), "meta": meta, "inspection_id": inspection_id}


def register_inspection(iid: str) -> str:
    """既存のレビュー一覧に出すため、既存の形（store.new）のままの検査を 1 件だけ作る。

    対応は pair/docs/meta.json の inspection_id に持つ（既存 inspection.json にキーを足さない）。2 回目以降は作らない。
    """
    from web.services.docverify import store
    d = _existing(iid)
    meta_path = d / "docs" / "meta.json"
    meta = _read(meta_path, {})
    try:
        store.load(meta.get("inspection_id") or "")
        return meta["inspection_id"]
    except KeyError:
        pass
    head = next((ln[2:].strip() for ln in _doc_text(d, "requirements.md").splitlines() if ln.startswith("# ")), iid)
    insp = store.save(store.new(f"{head}（要件定義書 ⇔ 基本設計書）"))
    _write(meta_path, {**meta, "inspection_id": insp["id"]})
    return insp["id"]


def _section_of_line(md: str, line_no: int) -> str | None:
    sid = None
    for i, line in enumerate(md.splitlines(), 1):
        if i > line_no:
            break
        m = re.match(r"## (\d+)\.", line)
        if m:
            sid = f"s{m.group(1)}"
    return sid


def analyze(iid: str, user: str) -> dict:
    """既存の対検査エンジン（pair.engine.inspect）を保存済みの 2 文書に掛け、未登録の指摘を AI 指摘として足す。"""
    from web.services.docverify.pair import engine
    d = _existing(iid)
    req, design = _doc_text(d, "requirements.md"), _doc_text(d, "design.md")
    result = engine.inspect(req, design)
    meta = _read(d / "docs" / "meta.json", {"changed_sections": {"requirements": [], "design": []}})
    rl, dl = req.splitlines(), design.splitlines()
    with _lock(d):
        findings = _findings(d)
        added = []
        for i, df in enumerate(result["defects"], 1):
            r, s = (df.get("req_lines") or [None])[0], (df.get("design_lines") or [None])[0]
            f = {"id": f"AI-{i:02d}", "type": _ENGINE_TYPE.get(df.get("type"), "曖昧"), "severity": "警告", "source": "ai",
                 "title": df.get("reason", "")[:40], "description": df.get("reason", ""),
                 "req_ref": {"section": _section_of_line(req, r) if r else None, "quote": rl[r - 1].strip() if r and r <= len(rl) else ""},
                 "design_ref": {"section": _section_of_line(design, s) if s else None, "quote": dl[s - 1].strip() if s and s <= len(dl) else ""},
                 "status": None, "decided_by": None, "decided_at": None}
            if all(x["id"] != f["id"] for x in findings):
                added.append({**f, "changed_in_current": _is_changed(f, meta)})
        _write(d / "findings.json", [*findings, *added])
        _trail(d, user, "finding_decided", iid, f"自動検査で {len(added)} 件追加")
    return {"added": len(added), "errors": result["errors"]}
