"""用語集の候補生成（決定論のみ）。同義は「候補」であり断定しない。"""
from __future__ import annotations

import re

from .units import nfkc

SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("顧客", "利用者", "ユーザー", "会員", "お客様", "エンドユーザー"),
    ("管理者", "アドミン", "運用管理者", "システム管理者"),
    ("削除", "消去"),
    ("ログイン", "サインイン"),
    ("ログアウト", "サインアウト"),
)
_STOP = {"システム", "データ", "ファイル", "サービス", "ユーザー", "メッセージ", "エラー", "ページ", "ボタン", "リスト", "ログ"}
_DEF_QUOTE = re.compile(r"^[「『]([^」』]{1,20})[」』]\s*(?:とは|は、|を指す)[、,]?\s*(.+)$")
_DEF_TOHA = re.compile(r"^([^\s、。:：|「」]{2,20}?)とは[、,]?\s*(.+)$")
_DEF_TABLE = re.compile(r"^\|\s*([^|]{1,20}?)\s*\|\s*([^|]{2,}?)\s*\|")
_DEF_COLON = re.compile(r"^([^\s、。:：|はがを（(]{2,16})\s*[:：]\s*(.{4,})$")
_ID = re.compile(r"^[A-Z]+-?\d+$")
_ALIAS = re.compile(r"^(.+?)[（(]([^）)]{1,20})[）)]$")
_TERM = re.compile(r"[ァ-ヴー]{3,}|[A-Z][A-Z0-9]{1,}|[一-龥]{3,}")
_HEADER = {"用語", "項目", "名称", "定義", "説明", "---", "term"}


def _units(docs):
    for doc_id, lst in docs.items():
        for u in lst:
            d = u.to_dict() if hasattr(u, "to_dict") else dict(u)
            d.setdefault("document_id", doc_id)
            yield d


def _lines(raw: str):
    for ln in nfkc(raw).splitlines():
        ln = re.sub(r"^\s*(?:[-*・]\s+)", "", ln).strip()
        ln = re.sub(r"^[A-Za-z]+-\d+\s*[:：]\s*", "", ln)
        if ln:
            yield ln


def _extract_def(line: str):
    for rx in (_DEF_QUOTE, _DEF_TOHA, _DEF_TABLE, _DEF_COLON):
        m = rx.match(line)
        if m:
            term, definition = m.group(1).strip(), m.group(2).strip().rstrip("。")
            if term in _HEADER or set(term) <= set("-: ") or _ID.match(term) or definition in _HEADER:
                return None
            return term, definition
    return None


def build(docs: dict[str, list]) -> dict:
    defs: dict[str, dict] = {}
    corpus: list[tuple[str, str]] = []  # (document_id, 本文)
    for u in _units(docs):
        raw = u.get("raw_text", "")
        corpus.append((u["document_id"], nfkc(raw)))
        for line in _lines(raw):
            got = _extract_def(line)
            if not got:
                continue
            term, definition = got
            aliases: list[str] = []
            m = _ALIAS.match(term)
            if m:
                term, aliases = m.group(1).strip(), [m.group(2).strip()]
            loc = u.get("location") or {}
            entry = defs.setdefault(term, {"canonical": term, "aliases": [], "definitions": []})
            entry["aliases"] = sorted(set(entry["aliases"]) | set(aliases))
            entry["definitions"].append({"definition": definition, "document_id": u["document_id"],
                                         "requirement_id": u.get("requirement_id", ""), "location": loc})
    terms = []
    for t in sorted(defs):
        e = defs[t]
        first = e["definitions"][0]
        terms.append({"canonical": t, "aliases": e["aliases"], "definition": first["definition"],
                      "source": {k: first[k] for k in ("document_id", "requirement_id", "location")},
                      "status": "CANDIDATE", "definitions": e["definitions"]})
    multiple = [{"term": t["canonical"], "definitions": t["definitions"], "status": "CANDIDATE",
                 "note": "複数の定義がある。どれが正かは決めない"}
                for t in terms if len({re.sub(r"\s", "", d["definition"]) for d in t["definitions"]}) > 1]
    text_all = "\n".join(t for _, t in corpus)
    synonyms = []
    for grp in SYNONYM_GROUPS:
        usage = {w: text_all.count(w) for w in grp if text_all.count(w)}
        if len(usage) >= 2:
            synonyms.append({"candidates": list(usage), "usage": usage, "status": "CANDIDATE",
                             "note": "同義候補。同義と断定しない。用語集で統一の要否を人が決める"})
    known = set(defs) | {a for e in defs.values() for a in e["aliases"]}
    counts: dict[str, set] = {}
    freq: dict[str, int] = {}
    for doc_id, text in corpus:
        for w in _TERM.findall(text):
            counts.setdefault(w, set()).add(doc_id)
            freq[w] = freq.get(w, 0) + 1
    syn_words = {w for g in SYNONYM_GROUPS for w in g}
    undefined = []
    for w, n in sorted(freq.items()):
        is_kanji = bool(re.fullmatch(r"[一-龥]+", w))
        if w in known or w in _STOP or w in syn_words or n < (3 if is_kanji else 2):
            continue
        if any(w in k or k in w for k in known):
            continue
        undefined.append({"term": w, "count": n, "documents": sorted(counts[w]), "status": "CANDIDATE"})
    return {"terms": terms, "synonym_candidates": synonyms, "undefined_terms": undefined,
            "multiple_definitions": multiple}
