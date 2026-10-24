"""対検査レビューの案件一覧・新規作成・指摘書（Markdown）。保存形式は pair_review と同じ（pair/docs・findings.json）。"""
from __future__ import annotations

import re
import secrets
from pathlib import Path

from web.services.docverify import pair_review as pr

STAGES = ("計画", "対検査", "質問", "判定", "承認")
_MAX_DOC = 2_000_000


def _root() -> Path:
    return pr.pair_dir("probe").parent.parent


def _name(d: Path, meta: dict, iid: str) -> str:
    if meta.get("name"):
        return meta["name"]
    head = next((ln[2:].strip() for ln in pr._doc_text(d, "requirements.md").splitlines() if ln.startswith("# ")), "")
    return head or iid


def _stage(findings: list[dict], gate: dict, trail: list[dict]) -> str:
    if pr.active_approval(trail):
        return "承認"
    if findings and gate["overall"]["pass"] and all(f.get("status") for f in findings):
        return "判定"
    if any(f.get("status") == "要確認" for f in findings):
        return "質問"
    if any(f.get("status") for f in findings):
        return "対検査"
    return "計画"


def verdict(findings: list[dict], gate: dict) -> str:
    """合格・不合格・判定不能。1 件も採否が決まっていない（全件未判定）なら判定不能。"""
    if findings and not any(f.get("status") for f in findings):
        return "判定不能"
    return "合格" if gate["overall"]["pass"] else "不合格"


def summary(iid: str) -> dict:
    d = pr._existing(iid)
    findings, meta, trail = pr._findings(d), pr._read(d / "docs" / "meta.json", {}), pr._read(d / "trail.json", [])
    g = pr.gate(iid)
    who = pr.creator(d)
    return {"iid": iid, "inspection_id": meta.get("inspection_id"), "name": _name(d, meta, iid),
            "req_version": meta.get("req_version", 1), "design_version": meta.get("design_version", 1),
            "stage": _stage(findings, g, trail), "stages": list(STAGES), "due": meta.get("due") or "",
            "critical_open": len(g["overall"]["unresolved_critical"]),
            "unresolved": sum(1 for f in findings if f.get("status") not in pr.RESOLVED),
            "findings": len(findings), "verdict": verdict(findings, g),
            "assignee": who["user"] if who else "", "updated_at": (trail[-1]["at"] if trail else "")}


def cases() -> list[dict]:
    root = _root()
    out = []
    if root.exists():
        for f in sorted(root.glob("*/pair/findings.json")):
            iid = f.parent.parent.name
            try:
                out.append(summary(iid))
            except (pr.PairError, OSError, ValueError, KeyError):
                continue   # 壊れた案件は一覧に出さない（個別に開くと理由が出る）
    return sorted(out, key=lambda c: c["updated_at"], reverse=True)


def _decode(raw: bytes, label: str) -> str:
    if not raw or not raw.strip():
        raise pr.PairError(400, "empty_doc", f"{label}が空です。中身のあるファイルを選んでください。")
    if len(raw) > _MAX_DOC:
        raise pr.PairError(413, "too_large", f"{label}が 2MB を超えています。分けて取り込んでください。")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise pr.PairError(400, "not_utf8", f"{label}を文字として読めません。UTF-8 の Markdown かテキストを選んでください。")


def create(name: str, req: bytes, design: bytes, due: str, by: str) -> dict:
    name = (name or "").strip()
    if not name or len(name) > 100:
        raise pr.PairError(400, "name_required", "レビュー名を 1〜100 文字で入力してください。")
    if due and not re.match(r"^\d{4}-\d{2}-\d{2}$", due):
        raise pr.PairError(400, "bad_due", "期限は日付で選んでください。")
    req_t, design_t = _decode(req, "要件定義書"), _decode(design, "基本設計書")
    iid = "r-" + secrets.token_hex(5)
    d = pr.pair_dir(iid)
    meta = pr._write_docs(d, req_t, design_t, None, None)
    pr._write(d / "docs" / "meta.json", {**meta, "name": name, "due": due or ""})
    pr._write(d / "findings.json", [])
    pr._write(d / "decisions.json", [])
    pr._write(d / "trail.json", [])
    pr._trail(d, "_seed", "review_started", iid, "要件定義書と基本設計書を取り込み")
    res = pr.analyze(iid, by if by not in pr.SYSTEM_USERS else "_seed")
    insp = pr.register_inspection(iid)
    return {"iid": iid, "inspection_id": insp, "added": res["added"], "errors": res["errors"]}


def _q(ref: dict | None, doc: str) -> str:
    ref = ref or {}
    if not ref.get("section") and not ref.get("quote"):
        return f"- {doc}: 該当箇所なし（未確認）"
    return f"- {doc} §{ref.get('section') or '未確認'}: 「{(ref.get('quote') or '引用なし').strip()}」"


def report_md(iid: str) -> str:
    d = pr._existing(iid)
    s = summary(iid)
    g = pr.gate(iid)
    findings, decisions = pr._findings(d), pr._decisions(d)
    last = {}
    for dec in decisions:
        if not dec.get("revoke"):
            last[dec["finding_id"]] = dec
    L = [f"# 指摘書: {s['name']}", "",
         f"- 対象: 要件定義書 第 {s['req_version']} 版 ⇔ 基本設計書 第 {s['design_version']} 版",
         f"- 工程: {s['stage']} ／ 判定（全体）: {s['verdict']} ／ 今回の変更分: {'合格' if g['changed']['pass'] else '不合格'}",
         f"- 指摘: {len(findings)} 件（重大の未解消 {s['critical_open']} 件・未解消 {s['unresolved']} 件）",
         f"- 判定の根拠: {' '.join(g['reasons'])}", "",
         "区分の読み方: 「仕様に書いてある事実」は文書からの引用、「観測」は検査で見つかったこと、「推論」は指摘者の解釈です。", ""]
    for f in findings:
        dec = last.get(f["id"])
        src = "自動検査" if f.get("source") == "ai" else "レビュアー"
        L += [f"## {f['id']} {f.get('title') or ''}", "",
              f"- 種別: {f.get('type')} ／ 重大度: {f.get('severity')} ／ 状態: {f.get('status') or '未判定'}"
              + ("（今回の変更分）" if f.get("changed_in_current") else ""), "",
              "**仕様に書いてある事実**", _q(f.get("req_ref"), "要件定義書"), _q(f.get("design_ref"), "基本設計書"), "",
              "**観測**", f"- {src}が「{f.get('type')}」として検出。", "",
              "**推論**", f"- {f.get('description') or '未確認'}", "",
              "**確認手順**",
              f"1. 要件定義書 §{(f.get('req_ref') or {}).get('section') or '未確認'} を開き、上の引用を読む。",
              f"2. 基本設計書 §{(f.get('design_ref') or {}).get('section') or '未確認'} を開き、同じ事柄の記述と比べる。",
              f"3. 「{f.get('type')}」に当たるかを判断し、対検査画面で採否（採用／不採用／要確認）を記録する。", "",
              "**証跡**",
              (f"- {dec['status']}: {dec.get('by')} が {dec.get('at')} に記録。理由: {dec.get('reason') or '未記入'}"
               if dec else "- 採否: 未確認（まだ誰も判定していません）"), ""]
    if g["overall"]["missing_links"]:
        L += ["## 設計に対応の無い要件", ""] + [f"- {m['req_id']}: {m['reason']}" for m in g["overall"]["missing_links"]] + [""]
    return "\n".join(L) + "\n"
