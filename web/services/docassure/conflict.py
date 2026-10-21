"""文書内・文書間の矛盾「候補」の検出（決定論のみ・LLM 不使用）。

真実規律: 矛盾は CANDIDATE。どちらが正しいかは決めない（truth=UNKNOWN, status=UNRESOLVED）。
newer version / majority / authority は hints としてのみ付与する。
誤検出を避けるため、ロール・条件・スコープ・以上以下・種別が違う数値は比較しない。
"""
from __future__ import annotations

import hashlib
import re
from itertools import combinations

from .units import nfkc, normalize_quantity

# --- ロール語彙（定数テーブル 1 か所）---
ROLES: dict[str, tuple[str, ...]] = {
    "admin": ("システム管理者", "運用管理者", "管理者", "アドミン", "admin"),
    "general": ("一般ユーザー", "通常ユーザー", "一般会員", "一般"),
    "guest": ("ゲスト", "未ログインユーザー", "未ログイン"),
    "operator": ("オペレーター", "運用者"),
    "all": ("全ユーザー", "すべてのユーザー", "全員", "全ロール"),
}
_ROLE_ALIASES = sorted(((a, r) for r, al in ROLES.items() for a in al), key=lambda x: -len(x[0]))
SCOPE_WORDS = ("初回", "再試行", "夜間", "日中", "本番", "検証環境", "テスト環境", "モバイル", "API", "管理画面",
               "バッチ", "外部", "社内", "海外", "休日", "平日")
ACTIONS = {"閲覧": "view", "参照": "view", "表示": "view", "編集": "edit", "更新": "edit", "変更": "edit",
           "削除": "delete", "作成": "create", "登録": "create", "承認": "approve", "実行": "execute",
           "ダウンロード": "download", "出力": "download"}
_NEG = re.compile(r"不可|できない|できません|禁止|不許可|不可能|してはならない")
_POS = re.compile(r"可能|可|できる|できます|許可|とする")
_EXCL = re.compile(r"のみ|だけ|に限る|に限り|限定")
_COND = re.compile(r"([^、。,，]{1,20}?)(?:場合|とき|際|時(?=[はに、,]))")
_STOP = re.compile(r"とする|である|です|ます|するものとする|ものとする|すること|できる|する|こと|とし|べき")
_PARTICLES = re.compile(r"[はがをにでとものへやか、。,，\s「」()（）・:：*|_\-]")
_SEVERITY = {"numeric": "high", "permission": "high", "temporal": "medium", "semantic_candidate": "medium"}
_AUTH_RANK = (("requirement", 3), ("要件", 3), ("spec", 2), ("基本設計", 2), ("design", 2), ("設計", 2),
              ("test", 1), ("テスト", 1))
QUESTION = "どちらが正しいですか？根拠となる決定事項・承認者を確認し、文書を揃えてください。"
_MIN_DICE = 0.5


# --- 共通ヘルパ ---
def _as_dict(u) -> dict:
    return u.to_dict() if hasattr(u, "to_dict") else dict(u)


def _grams(s: str) -> set[str]:
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _dice(a: set, b: set) -> float:
    return 2 * len(a & b) / (len(a) + len(b)) if a and b else 0.0


def _sentences(raw: str) -> list[str]:
    out = []
    for part in re.split(r"[。\n]", nfkc(raw)):
        part = re.sub(r"^\s*(?:[-*・]\s+|\|\s*)", "", part).strip()
        if part:
            out.append(part)
    return out


def _roles_in(text: str) -> tuple[set[str], str]:
    found, rest = set(), text
    for alias, role in _ROLE_ALIASES:
        if alias in rest:
            found.add(role)
            rest = rest.replace(alias, "")
    return found, rest


def _clean(text: str) -> str:
    return _PARTICLES.sub("", _STOP.sub("", text))


def _conditions(text: str) -> tuple[frozenset[str], str]:
    conds = frozenset(_clean(m.group(1)) for m in _COND.finditer(text))
    return conds, _COND.sub("", text)


def _scope(sentence: str) -> tuple[frozenset[str], str]:
    """スコープ（ロール・条件・環境語）と、それらを除いたトピック用テキスト。"""
    conds, rest = _conditions(sentence)
    roles, rest = _roles_in(rest)
    words = {w for w in SCOPE_WORDS if w in rest}
    for w in words:
        rest = rest.replace(w, "")
    return frozenset(roles | conds | words), rest


class _Item:
    __slots__ = ("unit", "sentence", "sid", "qty", "grams", "scope", "bound")

    def __init__(self, unit, sentence, sid, qty, grams, scope, bound):
        self.unit, self.sentence, self.sid, self.qty = unit, sentence, sid, qty
        self.grams, self.scope, self.bound = grams, scope, bound


def _evidence(unit: dict, quote: str, value=None) -> dict:
    loc = dict(unit.get("location") or {})
    return {"document_id": unit.get("document_id") or loc.get("document_id", ""),
            "requirement_id": unit.get("requirement_id", ""), "location": loc,
            "quote": quote[:120], "canonical_value": value}


def _version_key(doc_id: str):
    m = re.search(r"v?(\d+(?:\.\d+)*)", doc_id)
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def _hints(evidence: list[dict], values: list | None = None) -> dict:
    h: dict = {"note": "ヒントであり正誤の判定ではない"}
    docs = sorted({e["document_id"] for e in evidence})
    versions = {d: _version_key(d) for d in docs if _version_key(d)}
    if len(set(versions.values())) > 1:
        h["newer_version"] = max(versions, key=lambda d: versions[d])
    ranks = {d: max((r for k, r in _AUTH_RANK if k in d.lower()), default=0) for d in docs}
    if len(set(ranks.values())) > 1:
        h["higher_authority"] = max(ranks, key=lambda d: ranks[d])
    if values:
        counts: dict = {}
        for v in values:
            counts[v] = counts.get(v, 0) + 1
        top = sorted(counts.items(), key=lambda kv: -kv[1])
        if len(top) > 1 and top[0][1] > top[1][1]:
            h["majority"] = top[0][0]
    return h


def _make(kind, topic, evidence, confidence, basis, values=None, key_extra="") -> dict:
    key = f"{kind}|{topic}|{key_extra}|" + "|".join(sorted(f"{e['requirement_id']}:{e['quote']}" for e in evidence))
    return {"conflict_id": "CF-" + hashlib.sha1(key.encode()).hexdigest()[:10], "topic": topic, "kind": kind,
            "evidence": evidence, "status": "UNRESOLVED", "truth": "UNKNOWN",
            "hints": _hints(evidence, values), "severity": _SEVERITY[kind],
            "confidence": round(confidence, 2), "confidence_basis": basis, "question": QUESTION}


# --- 数値 ---
def _label(it) -> str:
    return re.sub(r"[\d.,\s一二三四五六七八九十百千万〇]", "", it.qty["raw"])


def _numeric(units: list[dict]) -> list[dict]:
    items: list[_Item] = []
    sid = 0
    for u in units:
        for sent in _sentences(u.get("raw_text", "")):
            sid += 1
            scope, rest = _scope(sent)
            offset = len(sent) - len(rest)  # スコープ除去で位置がずれるため、トピックは qty 周辺語から作る
            qtys = normalize_quantity(sent)
            prev_end = 0
            for q in qtys:
                s, e = q["span"]
                head = sent[prev_end:s]
                head = head[max(head.rfind("、"), head.rfind(","), head.rfind("，")) + 1:]
                tail = sent[e:e + 12]
                tail = re.split(r"[、,，]", tail)[0]
                _, head = _conditions(head)
                _, head = _roles_in(head)
                for w in SCOPE_WORDS:
                    head = head.replace(w, "")
                g = _grams(_clean(head + tail))
                bound = {"gt": "ge", "lt": "le"}.get(q["bound"], q["bound"])
                items.append(_Item(u, sent, sid, q, g, scope, bound))
                prev_end = e
            del offset
    link: dict[tuple[int, int], float] = {}
    nbr: dict[int, set[int]] = {i: {i} for i in range(len(items))}
    for i, j in combinations(range(len(items)), 2):
        a, b = items[i], items[j]
        if a.qty["unit_kind"] == "count" and _label(a) != _label(b):
            continue  # 文字数と回数のように、同じ count でも単位語が違えば別物
        if a.sid == b.sid or a.qty["unit_kind"] != b.qty["unit_kind"] or a.bound != b.bound or a.scope != b.scope:
            continue
        d = _dice(a.grams, b.grams)
        if d >= _MIN_DICE:
            link[(i, j)] = d
            nbr[i].add(j)
            nbr[j].add(i)
    # 推移的に連結せず、各項目に直接つながる集合（星形）だけを候補にする（総称語での連鎖を防ぐ）
    groups = {frozenset(v) for v in nbr.values() if len(v) > 1}
    groups = [g for g in groups if not any(g < h for h in groups)]
    out = []
    for idx in (sorted(g) for g in sorted(groups, key=sorted)):
        vals = {round(items[i].qty["canonical_value"], 6) for i in idx}
        if len(vals) < 2:
            continue
        ev, seen = [], set()
        for i in idx:
            it = items[i]
            k = (it.unit.get("requirement_id"), it.sentence)
            if k not in seen:
                seen.add(k)
                ev.append(_evidence(it.unit, it.sentence, it.qty["canonical_value"]))
        ds = [d for (i, j), d in link.items() if i in idx and j in idx]
        topic = _clean(re.sub(r"\d.*", "", items[idx[0]].sentence)) or items[idx[0]].sentence[:20]
        basis = [f"同種の単位({items[idx[0]].qty['unit_kind']})", f"トピック重なり dice={min(ds):.2f}以上" if ds else "トピック重なり",
                 "ロール・条件・スコープ一致", f"異なる値 {sorted(vals)}"]
        out.append(_make("numeric", topic, ev, 0.85 if ds and min(ds) >= 0.7 else 0.65, basis,
                         [round(items[i].qty["canonical_value"], 6) for i in idx], str(sorted(vals))))
    return out


# --- 権限 ---
def _perm_statements(units: list[dict]) -> list[dict]:
    out = []
    for u in units:
        for sent in _sentences(u.get("raw_text", "")):
            action = next((ACTIONS[a] for a in ACTIONS if a in sent), None)
            conds, rest = _conditions(sent)
            roles, rest = _roles_in(rest)
            if not roles or not action:
                continue
            neg = bool(_NEG.search(sent))
            if not (neg or _POS.search(sent)):
                continue
            kind = "deny" if neg else ("exclusive" if _EXCL.search(sent) else "allow")
            obj = rest
            for a in ACTIONS:
                obj = obj.replace(a, "")
            obj = _clean(_EXCL.sub("", _NEG.sub("", _POS.sub("", obj))))
            out.append({"unit": u, "sent": sent, "roles": roles, "action": action, "kind": kind,
                        "conds": conds, "grams": _grams(obj)})
    return out


def _perm_clash(a: dict, b: dict) -> bool:
    ra, rb = a["roles"], b["roles"]
    pair = {a["kind"], b["kind"]}
    if pair == {"exclusive", "allow"}:
        ex, al = (a, b) if a["kind"] == "exclusive" else (b, a)
        return bool(al["roles"] - ex["roles"]) and "all" not in ex["roles"]
    if pair == {"exclusive"}:
        return ra != rb
    if pair == {"allow", "deny"} or pair == {"exclusive", "deny"}:
        return bool(ra & rb) if pair == {"allow", "deny"} else bool(ra & rb)
    return False


def _permission(units: list[dict]) -> list[dict]:
    st = _perm_statements(units)
    out = []
    for a, b in combinations(st, 2):
        if a["action"] != b["action"] or a["conds"] != b["conds"] or a["sent"] == b["sent"]:
            continue
        d = _dice(a["grams"], b["grams"])
        if d < _MIN_DICE or not _perm_clash(a, b):
            continue
        ev = [_evidence(a["unit"], a["sent"]), _evidence(b["unit"], b["sent"])]
        topic = f"{a['action']}権限"
        out.append(_make("permission", topic, ev, 0.8,
                         [f"対象ロール集合が食い違う {sorted(a['roles'])} / {sorted(b['roles'])}", f"対象 dice={d:.2f}"],
                         key_extra=str(sorted(a["roles"] | b["roles"]))))
    return out


# --- 時系列 ---
_PRED = re.compile(r"(?:を|が|は)?(?:行う|行い|実施|する|受け付ける|送る|実行|おこなう|行って)$")
_PAIR = re.compile(r"^(.*?)(?:した後(?:に|で)?|の後(?:に|で)?|後に|てから|次に)(.+)$")


def _step(s: str) -> str:
    s = re.sub(r"^.*[:：]", "", s) if re.search(r"[:：]", s) and "→" not in s.split("：")[0] else s
    return _PRED.sub("", _clean(s)).strip()


def _sequences(units: list[dict]) -> list[dict]:
    seqs = []
    for u in units:
        for sent in _sentences(u.get("raw_text", "")):
            if "→" in sent or "->" in sent or "⇒" in sent:
                parts = re.split(r"→|->|⇒", sent)
                parts[0] = re.sub(r"^.*(?:は|を|:|：)\s*", "", parts[0]) if len(parts[0]) > 8 else parts[0]
                steps = [_step(p) for p in parts]
            else:
                m = _PAIR.match(sent)
                if not m:
                    continue
                head = re.split(r"[、,，]", m.group(1))[-1]
                steps = [_step(head), _step(re.split(r"[、,，]", m.group(2))[0])]
            steps = [s for s in steps if len(s) >= 2]
            if len(steps) >= 2:
                seqs.append({"unit": u, "sent": sent, "steps": steps})
    return seqs


def _same_step(a: str, b: str) -> bool:
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return (len(short) >= 3 and short in long_ and len(short) / len(long_) >= 0.6) or _dice(_grams(a), _grams(b)) >= 0.7


def _temporal(units: list[dict]) -> list[dict]:
    out = []
    for a, b in combinations(_sequences(units), 2):
        if a["sent"] == b["sent"]:
            continue
        common = [(i, j) for i, x in enumerate(a["steps"]) for j, y in enumerate(b["steps"]) if _same_step(x, y)]
        if len({i for i, _ in common}) < 2:
            continue
        common.sort()
        js = [j for _, j in common]
        if all(js[k] < js[k + 1] for k in range(len(js) - 1)):
            continue
        ev = [_evidence(a["unit"], a["sent"]), _evidence(b["unit"], b["sent"])]
        names = [a["steps"][i] for i, _ in common]
        out.append(_make("temporal", "→".join(names), ev, 0.75,
                         ["共通する手順が 2 つ以上", "手順の前後関係が逆", f"共通手順 {names}"], key_extra="→".join(a["steps"])))
    return out


# --- 意味（キーワード対のみ・候補）---
_IMMEDIATE_DEL = re.compile(r"(?:即時|即座|直ちに|ただちに|すぐ|速やかに)[^。]{0,12}?(?:削除|消去|破棄)|(?:削除|消去|破棄)[^。]{0,4}(?:即時|即座)")
_RETAIN = re.compile(r"保持|保存|保管")
_PERPETUAL = re.compile(r"無期限|永久")
_ENC_NO = re.compile(r"暗号化(?:しない|不要)|平文")
_ENC_YES = re.compile(r"暗号化(?:する|される|を行う)|暗号化し")
_KW = re.compile(r"即時|即座|直ちに|ただちに|すぐ|速やかに|削除|消去|破棄|保持|保存|保管|無期限|永久|暗号化|平文|\d+\s*(?:日間|日|年|か月|週間|時間)間?")


def _semantic(units: list[dict]) -> list[dict]:
    tagged = []
    for u in units:
        for sent in _sentences(u.get("raw_text", "")):
            tags = set()
            if _IMMEDIATE_DEL.search(sent):
                tags.add("immediate_delete")
            if _RETAIN.search(sent) and (any(q["unit_kind"] == "time" for q in normalize_quantity(sent)) or _PERPETUAL.search(sent)):
                tags.add("retention")
            if _ENC_NO.search(sent):
                tags.add("enc_no")
            elif _ENC_YES.search(sent):
                tags.add("enc_yes")
            if tags:
                _, rest = _roles_in(_KW.sub("", sent))
                tagged.append((u, sent, tags, _grams(_clean(rest))))
    pairs = (("immediate_delete", "retention"), ("enc_no", "enc_yes"))
    out = []
    for (ua, sa, ta, ga), (ub, sb, tb, gb) in combinations(tagged, 2):
        if sa == sb:
            continue
        hit = next(((x, y) for x, y in pairs if (x in ta and y in tb) or (y in ta and x in tb)), None)
        d = _dice(ga, gb)
        if not hit or d < 0.3:
            continue
        ev = [_evidence(ua, sa), _evidence(ub, sb)]
        out.append(_make("semantic_candidate", "/".join(hit), ev, 0.4,
                         [f"キーワード対 {hit[0]} と {hit[1]}（ルール判定・AI 無し）", f"対象語 dice={d:.2f}"], key_extra="/".join(hit)))
    return out


def detect(docs: dict[str, list]) -> list[dict]:
    """docs = {document_id: [RequirementUnit | to_dict 形]}。矛盾候補のリストを返す。"""
    units: list[dict] = []
    for doc_id, lst in docs.items():
        for u in lst:
            d = _as_dict(u)
            d.setdefault("document_id", doc_id)
            units.append(d)
    result = _numeric(units) + _permission(units) + _temporal(units) + _semantic(units)
    uniq = {c["conflict_id"]: c for c in result}
    return sorted(uniq.values(), key=lambda c: (c["kind"], c["conflict_id"]))
