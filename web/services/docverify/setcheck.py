"""要求集合の検査（System 06 R3）。重複候補・矛盾候補・用語ゆれ・規則の選択と組織語彙・要求属性の欠落。

すべて決定的（LLM を使わない）。閾値は RD-006 の暫定値（R5 の実測で見直す）。
契約: docs/sdlc/20_design/WS2D-DD-006_詳細設計書_System06_R3.md 3 章。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

DUP_THRESHOLD = 0.9          # FR-06-120（暫定）
NEG_MIN_SIMILARITY = 0.0     # FR-06-121(b) の追加条件。0.0 = RD どおり条件なし（要判断）
MAX_UNITS = 1500             # 比較する文の上限。超えた分は検査しない（scope に出す）
DECISIONS = ("contradiction", "duplicate", "ok")
DECISION_TYPE = {"contradiction": "矛盾", "duplicate": "重複"}
COVERAGE = "網羅性: 未検証"
EMPTY = "確認した範囲では指摘はありません。網羅性は未検証です。"
DEFAULT_R3_SETTINGS = {"disabled_rules": [], "forbidden": [], "allowed": [], "synonyms": []}
RULES = ("INCOMPLETE", "OPEN_ENDED", "UNIVERSAL", "AND_OR", "MEASURABILITY", "MULTIPLE_REQUIREMENTS",
         "AMBIGUOUS_TERM", "AMBIGUOUS")

_SENT = re.compile(r"(?<=[。！？!?])\s*|\n+")
_SPACE = re.compile(r"\s+")
_PUNCT = str.maketrans({"，": "、", ",": "、", "｡": "。", "．": "。", "!": "！", "?": "？"})
_LEAD = re.compile(r"^[\d.)・\-*（(）]+")
_SUBJECT = re.compile(r"^(.{2,40}?)(?:は|が)")
_UNIT = re.compile(r"(\d+(?:\.\d+)?)\s*(ミリ秒|ms|秒|分|時間|日|週間|か月|ヶ月|年|件|回|%|文字|桁|人|円|KB|MB|GB|px|行|ページ|倍)")
_NEG = re.compile(r"しない|しません|してはならない|してはいけない|禁止|不可|できない|できません|させない|ないこと")
_ATTRS = {
    "ID": ("ID", "番号", "NO", "NO."),
    "優先度": ("優先度", "優先順位", "PRIORITY"),
    "根拠": ("根拠", "理由", "出典", "RATIONALE"),
    "検証方法": ("検証方法", "確認方法", "検証", "VERIFICATION"),
}
_REQ_TABLE = re.compile(r"要求|要件|REQ", re.I)


def normalize(text: str) -> str:
    """空白・全角半角・句読点を統一する（FR-06-120）。"""
    t = unicodedata.normalize("NFKC", text or "").translate(_PUNCT)
    return _SPACE.sub("", t).rstrip("。")


def ratio(a: str, b: str) -> float:
    """編集距離の比率による類似度（1 − 距離 / 長い方の長さ）。"""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return 1 - prev[-1] / max(len(a), len(b))


def units(documents: list[dict]) -> list[dict]:
    """文書群を文の単位に分ける。documents: [{"id","name","passages","include_hidden"}]。"""
    out = []
    for d in documents:
        for p in d.get("passages") or []:
            if p.get("hidden") and not d.get("include_hidden", True):
                continue
            for k, s in enumerate(x.strip() for x in _SENT.split(p.get("text") or "") if x and x.strip()):
                out.append({"key": f"{d['id']}:{p.get('id')}:{k}", "doc_id": d["id"], "doc_name": d.get("name", ""),
                            "passage_id": p.get("id"), "location": p.get("location", ""), "text": s, "norm": normalize(s)})
    return out


def subject(norm: str) -> str | None:
    m = _SUBJECT.match(_LEAD.sub("", norm))
    return m.group(1) if m else None


def _values(text: str) -> dict[str, list[str]]:
    vals: dict[str, list[str]] = {}
    for num, unit in _UNIT.findall(unicodedata.normalize("NFKC", text)):
        vals.setdefault(unit, []).append(num)
    return {u: sorted(v) for u, v in vals.items()}


def contradiction_reason(a: dict, b: dict) -> str | None:
    """同じ主語の 2 文で (a) 同じ単位の数値が違う (b) 否定と肯定、なら理由の文（FR-06-121）。"""
    va, vb = _values(a["text"]), _values(b["text"])
    for unit in sorted(set(va) & set(vb)):
        if va[unit] != vb[unit]:
            return f"同じ単位（{unit}）の数値が違います: {'・'.join(va[unit])} と {'・'.join(vb[unit])}"
    na, nb = bool(_NEG.search(a["norm"])), bool(_NEG.search(b["norm"]))
    if na != nb:
        if NEG_MIN_SIMILARITY and ratio(_NEG.sub("", a["norm"]), _NEG.sub("", b["norm"])) < NEG_MIN_SIMILARITY:
            return None
        return "一方が否定・禁止で、他方が肯定です"
    return None


def _side(u: dict) -> dict:
    return {k: u[k] for k in ("doc_id", "doc_name", "passage_id", "location", "text")}


def _pair(kind: str, a: dict, b: dict, sim: float, reason: str) -> dict:
    pid = "S" + hashlib.sha1(f"{a['key']}|{b['key']}".encode()).hexdigest()[:10]
    return {"id": pid, "kind": kind, "similarity": round(sim, 3), "reason": reason, "a": _side(a), "b": _side(b)}


def find_pairs(us: list[dict]) -> list[dict]:
    """重複候補と矛盾候補。1 組には 1 種類（矛盾を優先）。"""
    us = us[:MAX_UNITS]
    pairs: list[dict] = []
    for i, a in enumerate(us):
        sa = subject(a["norm"])
        for b in us[i + 1:]:
            if a["norm"] == "" or b["norm"] == "":
                continue
            sb = subject(b["norm"]) if sa else None
            reason = contradiction_reason(a, b) if sa and sa == sb else None
            short, long_ = sorted((len(a["norm"]), len(b["norm"])))
            sim = ratio(a["norm"], b["norm"]) if reason or short >= DUP_THRESHOLD * long_ else 0.0
            if reason:
                pairs.append(_pair("contradiction", a, b, sim, reason))
            elif sim >= DUP_THRESHOLD:
                pairs.append(_pair("duplicate", a, b, sim, f"類似度 {sim:.2f}（{DUP_THRESHOLD} 以上）"))
    return pairs


def run(documents: list[dict], previous: dict | None = None) -> dict:
    """集合の検査を実行し、新しい set_check を返す。前回の判断は同じ組 ID なら引き継ぐ。"""
    us = units(documents)
    prev = (previous or {}).get("decisions") or {}
    pairs = find_pairs(us)
    ids = {p["id"] for p in pairs}
    return {"pairs": pairs, "decisions": {k: v for k, v in prev.items() if k in ids},
            "units": len(us), "checked_units": min(len(us), MAX_UNITS), "truncated": len(us) > MAX_UNITS,
            "documents": len(documents), "ran_at": datetime.now(timezone.utc).isoformat()}


def view(set_check: dict | None) -> dict:
    """画面へ返す形。網羅性は常に未検証。"""
    sc = set_check or {}
    pairs = [{**p, "decision": (sc.get("decisions") or {}).get(p["id"], {}).get("decision")} for p in sc.get("pairs") or []]
    unchecked = [COVERAGE, "意味の正しさ: 未検証（規則で拾える形の重複・矛盾だけを候補にしています）"]
    if sc.get("truncated"):
        unchecked.append(f"文の数が上限 {MAX_UNITS} を超えたため、超えた分は検査していません。")
    return {"pairs": pairs, "ran": bool(sc.get("ran_at")), "ran_at": sc.get("ran_at"), "units": sc.get("units", 0),
            "coverage": COVERAGE, "empty_message": EMPTY if sc.get("ran_at") and not pairs else None,
            "unchecked": unchecked}


def _next_fid(findings: list[dict]) -> str:
    nums = [int(f["id"][1:]) for f in findings if str(f.get("id", "")).startswith("F") and f["id"][1:].isdigit()]
    return f"F{max(nums, default=0) + 1}"


def _set_finding(fid: str, pair: dict, decision: str, by: str) -> dict:
    a, b = pair["a"], pair["b"]
    word = DECISION_TYPE[decision]
    return {"id": fid, "rule": f"SET.{decision.upper()}", "type": word, "severity": "major", "checklist_item": "consistent",
            "viewpoint": "一貫", "message": f"「{a['text'][:60]}」と「{b['text'][:60]}」が{word}しています。",
            "location": f"{a['doc_name']} {a['location']} ／ {b['doc_name']} {b['location']}",
            "passage_id": a["passage_id"] if a["doc_id"] == "main" else None, "quote": a["text"][:200],
            "certainty": "判断", "status": "adopted", "answer": None, "origin": "set", "raised_by": by,
            "disposition": None, "set_pair": pair["id"]}


def decide(insp: dict, pair_id: str, decision: str, by: str) -> dict:
    """組の判断を記録した新しい検査を返す。矛盾・重複は指摘にする（FR-06-122）。"""
    if decision not in DECISIONS:
        raise ValueError("「矛盾」「重複」「問題なし」のどれかを選んでください。")
    sc = insp.get("set_check") or {}
    pair = next((p for p in sc.get("pairs") or [] if p["id"] == pair_id), None)
    if pair is None:
        raise KeyError(pair_id)
    findings = list(insp.get("findings") or [])
    idx = next((i for i, f in enumerate(findings) if f.get("set_pair") == pair_id), None)
    if idx is not None:
        old = findings[idx]
        findings[idx] = ({**old, "status": "rejected"} if decision == "ok" else
                         {**_set_finding(old["id"], pair, decision, by), "status": "adopted"})
    elif decision != "ok":
        findings.append(_set_finding(_next_fid(findings), pair, decision, by))
    fid = findings[idx]["id"] if idx is not None else (findings[-1]["id"] if decision != "ok" else None)
    rec = {"decision": decision, "by": by, "at": datetime.now(timezone.utc).isoformat(), "finding_id": fid}
    decisions = {**(sc.get("decisions") or {}), pair_id: rec}
    return {**insp, "findings": findings, "set_check": {**sc, "decisions": decisions}}


# ---- 規則の選択・組織語彙・用語ゆれ・要求属性（FR-06-025〜027） ----

def _settings_path() -> Path:
    from web import config
    from web.tenancy import scoped_output_dir
    return scoped_output_dir(config.DATA_DIR) / "docverify" / "_r3_settings.json"


def _words(value) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(w, str) for w in value):
        raise ValueError("語は 1 行に 1 つずつ入力してください。")
    return sorted({w.strip() for w in value if w.strip()})


def load_settings() -> dict:
    path = _settings_path()
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return {**json.loads(json.dumps(DEFAULT_R3_SETTINGS)), **data, "rules": list(RULES)}


def _synonyms(value) -> list[dict]:
    if not isinstance(value, list):
        raise ValueError("同義語は「標準語＝社内語」の形で 1 行に 1 組ずつ入力してください。")
    out = []
    for s in value:
        if not isinstance(s, dict) or not str(s.get("canonical", "")).strip():
            raise ValueError("同義語は「標準語＝社内語」の形で 1 行に 1 組ずつ入力してください。")
        variants = _words(s.get("variants") or [])
        if not variants:
            raise ValueError("同義語は「標準語＝社内語」の形で 1 行に 1 組ずつ入力してください。")
        out.append({"canonical": str(s["canonical"]).strip(), "variants": variants})
    return out


def save_settings(body: dict) -> dict:
    if not isinstance(body, dict):
        raise ValueError("設定の形が正しくありません。画面を再読み込みしてやり直してください。")
    cur = load_settings()
    disabled = _words(body.get("disabled_rules", cur["disabled_rules"]))
    if any(r not in RULES for r in disabled):
        raise ValueError("無効にする規則は一覧から選んでください。")
    data = {"disabled_rules": disabled, "forbidden": _words(body.get("forbidden", cur["forbidden"])),
            "allowed": _words(body.get("allowed", cur["allowed"])), "synonyms": _synonyms(body.get("synonyms", cur["synonyms"]))}
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return {**data, "rules": list(RULES)}


def _cand(rule: str, message: str, passage: dict, quote: str, item: str, viewpoint: str) -> dict:
    return {"rule": rule, "severity": "minor", "checklist_item": item, "viewpoint": viewpoint, "message": message,
            "location": passage.get("location", ""), "passage_id": passage.get("id"), "quote": quote,
            "certainty": "事実", "status": "candidate", "answer": None, "origin": "auto"}


def apply_rules(findings: list[dict], passages: list[dict], cfg: dict) -> list[dict]:
    """無効な規則と許容語に当たる候補を外し、禁止語の候補を足す（FR-06-025）。入力は変えない。"""
    disabled = set(cfg.get("disabled_rules") or [])
    allowed = set(cfg.get("allowed") or [])
    kept = [f for f in findings if str(f.get("rule", "")).split(".")[-1] not in disabled
            and not any(w and w in str(f.get("quote", "")) for w in allowed)]
    extra = [_cand("ORG.FORBIDDEN", f"禁止語「{w}」が使われています。言い換えてください。", p, w, "unambiguous", "曖昧でない")
             for p in passages for w in cfg.get("forbidden") or [] if w in (p.get("text") or "")]
    return [*kept, *extra]


def term_variants(passages: list[dict], synonyms: list[dict]) -> list[dict]:
    """辞書の標準語と社内語が同じ文書に混在していれば用語ゆれ候補にする（FR-06-027）。"""
    out = []
    for s in synonyms or []:
        canon_p = next((p for p in passages if s["canonical"] in (p.get("text") or "")), None)
        for v in s.get("variants") or []:
            var_p = next((p for p in passages if v in (p.get("text") or "")), None)
            if canon_p and var_p:
                out.append(_cand("ORG.TERM_VARIANT", f"用語ゆれ: 「{s['canonical']}」と「{v}」が混在しています。どちらかに揃えてください。",
                                 var_p, v, "consistent", "一貫"))
    return out


def _has(headers: list[str], names: tuple[str, ...]) -> bool:
    hs = [unicodedata.normalize("NFKC", h or "").upper().strip() for h in headers]
    return any(any(n == h or n in h for n in names) for h in hs if h)


def missing_attributes(tables: list[dict]) -> list[dict]:
    """表形式の要求一覧に ID・優先度・根拠・検証方法の列が無ければ候補にする（FR-06-026）。"""
    out = []
    for t in tables or []:
        headers = t.get("headers") or []
        if not any(_REQ_TABLE.search(h or "") for h in headers):
            continue
        for label, names in _ATTRS.items():
            if not _has(headers, names):
                p = {"id": t.get("passage_id"), "location": t.get("location", "")}
                out.append(_cand("REQ.MISSING_ATTRIBUTE", f"{label}がありません。要求一覧に「{label}」の列を足してください。",
                                 p, "｜".join(headers)[:200], "complete", "完全"))
    return out
