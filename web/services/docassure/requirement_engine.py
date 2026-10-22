"""要件定義書（Markdown）から RequirementUnit を決定論で取り出す。LLM は使わない。

出所の規則: 原文にある語は OBSERVED、換算・分割は DERIVED。推測で補わない
（語が無い項目は fields に入れない）。
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

from web.services.docassure.model import DERIVED, OBSERVED, Field, Location, RequirementUnit
from web.services.docverify.pair.segment import Unit, segment

_HEAD = re.compile(r"^(#{1,6})\s+(.*)$")
_ITEM = re.compile(r"^(?:[-*+]|\d+[.)])\s+")
_ID = re.compile(r"\b(?:REQ|NFR|FR|SR|BR|SEC)-\d{1,5}\b")
_END = re.compile(
    r"(?:こと|する|できる|できない|ならない|しない|される|れる|ます|とする|行う|持つ|有する|可能|必須|不可)$"
    r"|\b(?:shall|must|should)\b", re.I)
_COND = re.compile(r"(場合|とき|際)(?:は|には)?[、,]")
_QTY = re.compile(r"\d+\s*(?:回|件|文字|桁|個|人|%|％|MB|GB)")
_TIMING = re.compile(r"\d+(?:\.\d+)?\s*(?:ミリ秒|ms|秒|分|時間|日|週間)(?:間|以内|ごと|毎)?")
_UNIT_SEC = {"ミリ秒": 0.001, "ms": 0.001, "秒": 1, "分": 60, "時間": 3600, "日": 86400, "週間": 604800}
_PRIORITY = re.compile(r"必須|任意|MUST|SHOULD|MAY|望ましい|推奨")
_RUN = re.compile(r"[一-龥ァ-ヴー]{1,8}(?:・[一-龥ァ-ヴー]{1,8})+")
_SECURITY = re.compile(r"認証|権限|認可|暗号|パスワード|ログイン|トークン|セッション")
_NFR = re.compile(r"\d+(?:\.\d+)?\s*(?:秒|ms|ミリ秒)|\d+\s*件|可用性|性能|稼働率|応答|同時|ログ(?!イン)")
_BUSINESS = re.compile(r"不可|歳以上|歳未満|禁止|できない|のみ可")


def _sha(text: str, n: int = 12) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:n]


def sections(document_id: str, markdown: str) -> list[dict]:
    """見出しごとの節。text は見出し行の次から次の見出しの前まで（子節は含めない）。"""
    lines = markdown.splitlines()
    heads = [(i, m) for i, l in enumerate(lines) if (m := _HEAD.match(l.rstrip()))]
    out = []
    for ordinal, (i, m) in enumerate(heads, start=1):
        end = heads[ordinal][0] if ordinal < len(heads) else len(lines)
        text = "\n".join(lines[i + 1:end]).strip("\n")
        out.append({
            "section_id": f"SEC-{document_id}-{ordinal:03d}", "heading": m.group(2).strip(),
            "level": len(m.group(1)), "ordinal": ordinal,
            "line_start": i + 1, "line_end": max(end, i + 1), "text": text, "hash": _sha(text)})
    return out


def _fingerprint(text: str) -> str:
    t = unicodedata.normalize("NFKC", _ID.sub("", text)).lower()
    t = "".join(c for c in t if unicodedata.category(c)[0] not in "ZPSC")
    return _sha(t)


def _kind(t: str) -> str:
    if _SECURITY.search(t):
        return "security_rule"
    if _NFR.search(t):
        return "nfr"
    if _BUSINESS.search(t):
        return "business_rule"
    return "functional"


def _num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else str(x)


def _fields(text: str, priority: str = "") -> dict[str, Field]:
    t = _ID.sub("", text).strip().strip("：:").strip().rstrip("。.")
    f: dict[str, str] = {}
    m = _COND.search(t)
    cond, main = (t[:m.start()], t[m.end():]) if m else ("", t)
    actor_re = re.compile(r"^([^、がはをにで]{1,15}?)(?:が|は)")
    am = actor_re.match(cond or main)
    rest = cond
    if am:
        f["actor"] = am.group(1)
        if cond:
            rest = cond[am.end():]
        else:
            main = main[am.end():]
    if cond:
        q = _QTY.search(rest)
        if q:
            end = q.end() + (2 if rest[q.end():].startswith("連続") else 0)
            f["condition"] = rest[q.start():end]
            rest = rest[:q.start()] + rest[end:]
            rest = re.sub(r"^(?:して|し|で|て)", "", rest)
            trig = re.sub(r"(?:した|する|され?た|れた)$", "", rest).strip()
            if trig:
                f["trigger"] = trig
        else:
            trig = re.sub(r"(?:した|する|され?た|れた)$", "", rest).strip()
            if m.group(1) == "場合":
                if trig:
                    f["condition"] = rest.strip()
            elif trig:
                f["trigger"] = trig
    tm = _TIMING.search(main) or _TIMING.search(t)
    if tm:
        f["timing"] = tm.group()
        nm = re.match(r"\d+(?:\.\d+)?", tm.group())
        unit = next((u for u in _UNIT_SEC if u in tm.group()[nm.end():]), "")
        derived = _num(float(nm.group()) * _UNIT_SEC[unit]) if unit else ""
    else:
        derived = ""
    act = main.replace(tm.group(), "", 1) if tm and tm.group() in main else main
    act = re.sub(r"^(?:は|が)", "", act.strip("、, ")).strip()
    act = re.sub(r"こと$", "", act)
    if act:
        f["action"] = act
        om = re.match(r"([^をはがに、]+)を", act)
        if om:
            f["object"] = om.group(1)
        if re.search(r"表示|通知|返却|返す|出力|応答", act):
            f["expected_result"] = act
    em = re.search(r"(?:ただし|但し)[、,]?(.+)$", t)
    em2 = re.search(r"[^、]*を除く", t)
    if em or em2:
        f["exception"] = em.group(1) if em else em2.group()
    cm = re.search(r"[^、。]{0,15}?(?:以上|以下|未満|のみ)", t)
    if cm:
        f["constraint"] = cm.group()
    qm = _QTY.search(t)
    if qm:
        f["quantity"] = qm.group()
    pm = priority.strip() or (_PRIORITY.search(t).group() if _PRIORITY.search(t) else "")
    if pm:
        f["priority"] = pm
    out = {k: Field(v, OBSERVED) for k, v in f.items() if v}
    if derived:
        out["timing_seconds"] = Field(derived, DERIVED)
    return out


def _split_atomic(sent: str) -> list[str]:
    """複数動作の文を動作ごとの文にする。分けられなければ空リスト。"""
    t = re.sub(r"こと$", "", sent.rstrip("。."))
    m = _COND.search(t)
    pre, body = (t[:m.end()], t[m.end():]) if m else ("", t)
    run = _RUN.search(body)
    if run and re.match(r"(?:を|が)?(?:行え|でき|する|可能)", body[run.end():]):
        suf = body[run.end():]
        return [pre + body[:run.start()] + tok + suf for tok in run.group().split("・")]
    parts = re.split(r"(?<=でき)、|(?<=し)、(?=[^、]*(?:を|に|が))", body)
    if len(parts) >= 2 and all(re.search(r"[をにが]", p) for p in parts):
        fix = [p.strip() + "る" if p.strip().endswith("でき") else
               p.strip()[:-1] + "する" if p.strip().endswith("し") else p.strip() for p in parts]
        return [pre + p for p in fix]
    return []


def _make(doc: str, rid: str, loc: Location, text: str, fields: dict, parent: str = "", split: bool = False):
    return RequirementUnit(
        requirement_id=rid, document_id=doc, location=loc, raw_text=text, fields=fields,
        kind=_kind(text), parent_id=parent, split=split, fingerprint=_fingerprint(text))


def _candidates(u: Unit) -> list[tuple[str, int, int, str]]:
    """(文, 行開始, 行終了, 優先度) を返す。"""
    if u.kind == "row":
        ids = [c for c in u.cells if _ID.fullmatch(c)]
        prio = next((c for h, c in zip(u.headers, u.cells) if "優先" in h and c), "")
        body = " ".join(c for c in u.cells if c and c not in ids and c != prio)
        ok = bool(ids) or any(_END.search(c) for c in u.cells)
        text = (" ".join(ids) + " " + body).strip() if ids else body
        return [(text, u.start, u.end, prio)] if ok and body else []
    out = []
    for m in re.finditer(r"[^。]+。?", u.text):
        raw = m.group()
        sent = raw.strip()
        if not sent:
            continue
        pos = m.start() + len(raw) - len(raw.lstrip())
        if u.kind == "item" and m.start() == 0:
            sent = _ITEM.sub("", sent, 1)
        s = sent.rstrip("。.").strip()
        ls = u.start + u.text[:pos].count("\n")
        has_head = any("要件" in h for h in u.heading)
        if _ID.search(s) or _END.search(s) or (u.kind == "item" and has_head):
            out.append((sent, ls, ls + sent.count("\n"), ""))
    return out


def extract(document_id: str, markdown: str) -> list[RequirementUnit]:
    out: list[RequirementUnit] = []
    seq, seen = 0, {}
    for u in segment(markdown):
        for sent, ls, le, prio in _candidates(u):
            seq += 1
            ids = _ID.findall(sent)
            rid = ids[0] if ids else f"RU-{document_id}-{seq:03d}"
            seen[rid] = seen.get(rid, 0) + 1
            if seen[rid] > 1:
                rid = f"{rid}#{seen[rid]}"
            text = sent.strip()
            snip = (u.text.splitlines()[0].strip() if u.kind == "row" else text.split("\n")[0])[:120]
            loc = Location(document_id, " > ".join(u.heading), ls, le, snip, _sha(snip))
            out.append(_make(document_id, rid, loc, text, _fields(text, prio)))
            if u.kind == "row":
                continue
            for n, child in enumerate(_split_atomic(_ID.sub("", text).strip()), start=1):
                fl = {k: Field(v.value, DERIVED) for k, v in _fields(child).items()}
                out.append(_make(document_id, f"{rid}.{n}", loc, child, fl, parent=rid, split=True))
    return out
