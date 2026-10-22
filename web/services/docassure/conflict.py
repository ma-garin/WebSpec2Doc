"""文書内・文書間の矛盾「候補」の検出（決定論のみ・LLM 不使用）。

真実規律: 矛盾は CANDIDATE。どちらが正しいかは決めない（truth=UNKNOWN, status=UNRESOLVED）。
newer version / majority / authority は hints としてのみ付与する。
誤検出を避けるため、ロール・条件・スコープ・以上以下・種別が違う数値は比較しない。
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
from collections import Counter

from .units import nfkc, normalize_quantity

# --- ロール語彙（定数テーブル 1 か所）---
ROLES: dict[str, tuple[str, ...]] = {
    "admin": ("システム管理者", "運用管理者", "管理者", "アドミン", "admin"),
    "general": ("一般ユーザー", "通常ユーザー", "一般会員", "一般"),
    "guest": ("ゲスト", "未ログインユーザー", "未ログイン"),
    "operator": ("オペレーター", "運用者"),
    "viewer": ("閲覧者", "閲覧ユーザー", "ビューア", "ビューワー", "読み取り専用ユーザー"),
    "manager": ("部長", "課長", "マネージャー", "上長"),
    "employee": ("一般社員", "社員", "従業員"),
    "all": ("全ユーザー", "すべてのユーザー", "全員", "全ロール"),
}
_ROLE_ALIASES = sorted(((a, r) for r, al in ROLES.items() for a in al), key=lambda x: -len(x[0]))
SCOPE_WORDS = ("初回", "再試行", "夜間", "日中", "本番", "検証環境", "テスト環境", "モバイル", "API", "管理画面",
               "バッチ", "外部", "社内", "海外", "休日", "平日")
ACTIONS = {"閲覧": "view", "参照": "view", "表示": "view", "編集": "edit", "更新": "edit", "変更": "edit",
           "削除": "delete", "作成": "create", "登録": "create", "承認": "approve", "実行": "execute",
           "ダウンロード": "download", "出力": "download", "投稿": "create", "書き込": "edit",
           "修正": "edit", "設定": "edit", "入力": "edit"}
_NEG = re.compile(r"不可|できない|できません|行えない|行えません|禁止|不許可|不可能|してはならない")
_POS = re.compile(r"可能|可|できる|できます|行える|行えます|許可|とする|に限る|に限り|に限られる")
_EXCL = re.compile(r"のみ|だけ|に限る|に限り|限定")
_COND = re.compile(r"([^、。,，]{1,20}?)(?:場合|とき|際|時(?=[はに、,]))")
_STOP = re.compile(r"とする|である|です|ます|するものとする|ものとする|すること|できる|する|こと|とし|べき")
_PARTICLES = re.compile(r"[はがをにでとものへやか、。,，\s「」()（）・:：*|_\-]")
_SEVERITY = {"numeric": "high", "permission": "high", "temporal": "medium", "semantic_candidate": "medium"}
_AUTH_RANK = (("requirement", 3), ("要件", 3), ("spec", 2), ("基本設計", 2), ("design", 2), ("設計", 2),
              ("test", 1), ("テスト", 1))
QUESTION = "どちらが正しいですか？根拠となる決定事項・承認者を確認し、文書を揃えてください。"
_MIN_DICE = 0.5
MAX_BUCKET = 200  # 転置索引の 1 バケット（同じ gram を持つ項目の並び）の比較窓。超えたら件数だけログに出す
_log = logging.getLogger(__name__)
STATS: dict[str, int] = {}  # detect() ごとのカウンタ（項目数・候補ペア数・実比較回数）。計測用


def _bump(key: str, n: int = 1) -> None:
    STATS[key] = STATS.get(key, 0) + n


def _prefix_len(size: int, t: float) -> int:
    """dice>=t を満たしうる相手との最小重なりから決まる prefix 長（prefix filtering。取りこぼし無し）。"""
    partner = max(1, math.ceil(size * t / (2 - t) - 1e-9))
    need = min(size, max(1, math.ceil(t * (size + partner) / 2 - 1e-9)))
    return size - need + 1


def _similar_candidates(grams: list[set], t: float, label: str) -> list[tuple[int, int]]:
    """dice>=t になりうる (i<j) だけを転置索引で返す。全ペアは作らない。希少 gram を prefix にして索引する。"""
    freq = Counter(g for s in grams for g in s)
    post: dict[str, list[int]] = {}
    for i, s in enumerate(grams):
        if s:
            for g in sorted(s, key=lambda x: (freq[x], x))[:_prefix_len(len(s), t)]:
                post.setdefault(g, []).append(i)
    pairs: set[tuple[int, int]] = set()
    for lst in post.values():
        n = len(lst)
        if n < 2:
            continue
        if n > MAX_BUCKET:
            _log.info("docassure conflict: bucket 上限超過 kind=%s size=%d limit=%d", label, n, MAX_BUCKET)
            _bump("oversize_buckets")
        for a in range(n):
            for b in range(a + 1, min(n, a + 1 + MAX_BUCKET)):
                pairs.add((lst[a], lst[b]))
    _bump(f"{label}_candidates", len(pairs))
    return sorted(pairs)


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
        part = re.sub(r"^[A-Za-z]+-?\d+(?:\.\d+)*[:：]?\s+", "", part)  # 先頭の要件 ID は比較対象の語ではない
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
    words = {w for w in SCOPE_WORDS if w in rest} | set(re.findall(r"「([^」]+)」", sentence))
    for w in words:
        rest = rest.replace(w, "")
    return frozenset(roles | conds | words), rest


class _Item:
    __slots__ = ("unit", "sentence", "sid", "qty", "grams", "scope", "bound", "qual")

    def __init__(self, unit, sentence, sid, qty, grams, scope, bound, qual=""):
        self.unit, self.sentence, self.sid, self.qty = unit, sentence, sid, qty
        self.grams, self.scope, self.bound, self.qual = grams, scope, bound, qual


def _qualifier_differs(a: str, b: str) -> bool:
    """「X の保持時間」の X（対象の限定句）が双方にあり、包含関係もなく異なるなら別対象。片方にしか無ければ判定しない。"""
    return bool(a and b and a != b and a not in b and b not in a)


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
                seg = head[max(head.rfind("、"), head.rfind(","), head.rfind("，")) + 1:]
                # 「…検査数は、50個」のように読点の直後が数値だと節が空になる。語が足りないときは直前の節まで遡る
                head = seg if len(_clean(seg)) >= 2 else head
                tail = sent[e:e + 12]
                tail = re.split(r"[、,，]", tail)[0]
                _, head = _conditions(head)
                _, head = _roles_in(head)
                for w in SCOPE_WORDS:
                    head = head.replace(w, "")
                g = _grams(_clean(head + tail))
                bound = {"gt": "ge", "lt": "le"}.get(q["bound"], q["bound"])
                qual = _clean(head.rsplit("の", 1)[0]) if "の" in head else ""
                items.append(_Item(u, sent, sid, q, g, scope, bound, qual))
                prev_end = e
            del offset
    _bump("numeric_items", len(items))
    link: dict[tuple[int, int], float] = {}
    nbr: dict[int, set[int]] = {i: {i} for i in range(len(items))}
    # 単位種別・境界・スコープ（count は単位語も）が同じ項目だけを同じバケットに入れ、その中だけ gram の転置索引で絞る
    buckets: dict[tuple, list[int]] = {}
    for i, it in enumerate(items):
        key = (it.qty["unit_kind"], it.bound, it.scope, _label(it) if it.qty["unit_kind"] == "count" else "")
        buckets.setdefault(key, []).append(i)
    for members in buckets.values():
        if len(members) < 2:
            continue
        for x, y in _similar_candidates([items[i].grams for i in members], _MIN_DICE, "numeric"):
            i, j = members[x], members[y]
            a, b = items[i], items[j]
            if a.sid == b.sid or _qualifier_differs(a.qual, b.qual):
                continue
            _bump("numeric_comparisons")
            d = _dice(a.grams, b.grams)
            if d >= _MIN_DICE:
                link[(i, j)] = d
                nbr[i].add(j)
                nbr[j].add(i)
    # 推移的に連結せず、各項目に直接つながる集合（星形）だけを候補にする（総称語での連鎖を防ぐ）
    groups = {frozenset(v) for v in nbr.values() if len(v) > 1}
    by_elem: dict[int, list[frozenset]] = {}
    for g in groups:
        for e in g:
            by_elem.setdefault(e, []).append(g)
    groups = [g for g in groups if not any(g < h for h in by_elem[min(g)])]
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
        iset = set(idx)
        ds = [link[(i, j)] for i in idx for j in nbr[i] if j > i and j in iset]
        topic = _clean(re.sub(r"\d.*", "", items[idx[0]].sentence)) or items[idx[0]].sentence[:20]
        basis = [f"同種の単位({items[idx[0]].qty['unit_kind']})", f"トピック重なり dice={min(ds):.2f}以上" if ds else "トピック重なり",
                 "ロール・条件・スコープ一致", f"異なる値 {sorted(vals)}"]
        out.append(_make("numeric", topic, ev, 0.85 if ds and min(ds) >= 0.7 else 0.65, basis,
                         [round(items[i].qty["canonical_value"], 6) for i in idx], str(sorted(vals))))
    return out


# --- 権限 ---
_ROLE_BY_ALIAS = {a: r for a, r in _ROLE_ALIASES}
_ROLE_CHUNK = re.compile(r"(.+?)(のみが|のみに|のみは|のみ|だけが|だけ|に限られる|に限る|に限り|が|も|は)")
_ROLE_EXCL = ("のみ", "だけ", "に限")


def _role_phrase(text: str) -> tuple[str, str] | None:
    """主語（権限の主体）を語彙に頼らず助詞の並びから取る。返り値は (句, 区切り)。動作語を含む句は対象なので除く。"""
    cands = [(m.group(1).strip(), m.group(2)) for m in _ROLE_CHUNK.finditer(text)]
    cands = [(p, k) for p, k in cands if 2 <= len(p) <= 12 and not any(a in p for a in ACTIONS) and not re.search(r"\d", p)]
    excl = [c for c in cands if c[1].startswith(_ROLE_EXCL)]
    return (excl or cands or [None])[-1]


def _perm_statements(units: list[dict]) -> list[dict]:
    out = []
    for u in units:
        for sent in _sentences(u.get("raw_text", "")):
            action = next((ACTIONS[a] for a in ACTIONS if a in sent), None)
            conds, rest = _conditions(sent)
            ph = _role_phrase(rest)
            if ph and ph[0] not in _ROLE_BY_ALIAS:
                roles, rest = {ph[0]}, rest.replace(ph[0], "", 1)
            elif ph and ph[0] in _ROLE_BY_ALIAS:
                roles, rest = {_ROLE_BY_ALIAS[ph[0]]}, rest.replace(ph[0], "", 1)
            else:
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
    _bump("permission_items", len(st))
    out = []
    # 同じ (action, 条件) のバケットだけ。対象語が空の文どうしは種別の組で絞り、他は gram 転置索引で絞る
    buckets: dict[tuple, list[int]] = {}
    for i, s in enumerate(st):
        buckets.setdefault((s["action"], s["conds"]), []).append(i)
    cands: set[tuple[int, int]] = set()
    for members in buckets.values():
        if len(members) < 2:
            continue
        full = [i for i in members if st[i]["grams"]]
        cands.update((full[x], full[y]) for x, y in _similar_candidates([st[i]["grams"] for i in full], _MIN_DICE, "permission"))
        empty: dict[str, list[int]] = {}
        for i in members:
            if not st[i]["grams"]:
                empty.setdefault(st[i]["kind"], []).append(i)
        for ka, kb in (("allow", "deny"), ("exclusive", "allow"), ("exclusive", "deny"), ("exclusive", "exclusive")):
            la, lb = empty.get(ka, []), empty.get(kb, [])
            if len(la) * len(lb) > MAX_BUCKET * MAX_BUCKET:
                _log.info("docassure conflict: bucket 上限超過 kind=permission_empty size=%d limit=%d", len(la) * len(lb), MAX_BUCKET)
                _bump("oversize_buckets")
                la, lb = la[:MAX_BUCKET], lb[:MAX_BUCKET]
            for i in la:
                for j in lb:
                    if i != j:
                        cands.add((min(i, j), max(i, j)))
    for i, j in sorted(cands):
        a, b = st[i], st[j]
        if a["sent"] == b["sent"]:
            continue
        _bump("permission_comparisons")
        d = 1.0 if not a["grams"] and not b["grams"] else _dice(a["grams"], b["grams"])  # 対象語が動作だけの文どうし
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
_REL = re.compile(r"^(?P<subj>.+?)は、?(?P<ref>[^、]+?)(?:より(?:も)?|の|した|する|し)(?P<rel>前|後|先|あと)に(?P<pred>.+)$")
_PAIR_BEFORE = re.compile(r"^(.*?)(?:する前に|より前に|の前に|前に)(.+)$")
_PHASE = (("開始", 0), ("着手", 0), ("完了", 1), ("終了", 1), ("締切", 1), ("確定", 1))
_PAIR = re.compile(r"^(.*?)(?:した後(?:に|で)?|の後(?:に|で)?|後に|てから|次に)(.+)$")


def _step(s: str) -> str:
    s = re.sub(r"^.*[:：]", "", s) if re.search(r"[:：]", s) and "→" not in s.split("：")[0] else s
    return _PRED.sub("", _clean(s)).strip()


def _meta(raw: str) -> tuple[str, int | None]:
    """手順の (対象語, 開始/完了の相)。「検品が完了」「検品を開始」は同じ対象の別の相。"""
    m = re.match(r"([^がをは]{2,}?)[がをは](.+)$", nfkc(raw).strip())
    if not m:
        return "", None
    return m.group(1), next((ph for w, ph in _PHASE if w in m.group(2)), None)


def _steps(raws: list[str]) -> tuple[list[str], list[tuple[str, int | None]]]:
    pairs = [(_step(r), _meta(r)) for r in raws]
    pairs = [p for p in pairs if len(p[0]) >= 2]
    return [p[0] for p in pairs], [p[1] for p in pairs]


def _sequences(units: list[dict]) -> list[dict]:
    seqs = []
    for u in units:
        for sent in _sentences(u.get("raw_text", "")):
            rel = _REL.match(sent)
            if rel and not re.search(r"→|->|⇒", sent):
                ev_raw, ref_raw = rel["subj"] + rel["pred"], rel["ref"]
                raws = [ev_raw, ref_raw] if rel["rel"] in ("前", "先") else [ref_raw, ev_raw]
                steps, metas = _steps(raws)
                if len(steps) == 2 and len(_step(ev_raw)) >= 2 and len(_step(ref_raw)) >= 2:
                    seqs.append({"unit": u, "sent": sent, "steps": steps, "metas": metas})
                continue
            if "→" in sent or "->" in sent or "⇒" in sent:
                parts = re.split(r"→|->|⇒", sent)
                parts[0] = re.sub(r"^.*(?:は|を|:|：)\s*", "", parts[0]) if len(parts[0]) > 8 else parts[0]
                raws = parts
            else:
                m = _PAIR.match(sent)
                before = _PAIR_BEFORE.match(sent) if not m else None
                if not m and not before:
                    continue
                if m:
                    raws = [re.split(r"[、,，]", m.group(1))[-1], re.split(r"[、,，]", m.group(2).lstrip("、,， "))[0]]
                else:  # 「X は、Y する前に Z」: Z → Y の順
                    raws = [re.split(r"[、,，]", before.group(2))[0], re.split(r"[、,，]", before.group(1))[-1]]
                    topic = re.match(r"^([^、]+?)は、", before.group(1))
                    if topic:
                        raws[0] = topic.group(1) + raws[0]
            steps, metas = _steps(raws)
            if len(steps) >= 2:
                seqs.append({"unit": u, "sent": sent, "steps": steps, "metas": metas})
    return seqs


def _same_step(a: str, b: str) -> bool:
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return (len(short) >= 3 and short in long_ and len(short) / len(long_) >= 0.6) or _dice(_grams(a), _grams(b)) >= 0.7


def _phase_match(ma: tuple, mb: tuple) -> bool:
    return bool(ma[0] and ma[0] == mb[0] and ma[1] is not None and mb[1] is not None and ma[1] != mb[1])


def _temporal_candidates(seqs: list[dict]) -> list[tuple[int, int]]:
    """共通手順が 2 つ以上ありうる手順列のペアだけ返す。手順の gram 転置索引（dice 0.6 以上＝同一・包含・dice0.7 を覆う）と対象語の索引で絞る。"""
    flat = [(si, k) for si, q in enumerate(seqs) for k in range(len(q["steps"]))]
    steps = [seqs[si]["steps"][k] for si, k in flat]
    touched: dict[tuple[int, int], set[int]] = {}
    pairs = [(p, q) for p, q in _similar_candidates([_grams(s) for s in steps], 0.6, "temporal")]
    subj: dict[str, list[int]] = {}
    for p, (si, k) in enumerate(flat):
        m = seqs[si]["metas"][k]
        if m[0] and m[1] is not None:
            subj.setdefault(m[0], []).append(p)
    for lst in subj.values():
        n = len(lst)
        if n > MAX_BUCKET:
            _log.info("docassure conflict: bucket 上限超過 kind=temporal_subject size=%d limit=%d", n, MAX_BUCKET)
            _bump("oversize_buckets")
        pairs += [(lst[x], lst[y]) for x in range(n) for y in range(x + 1, min(n, x + 1 + MAX_BUCKET))]
    for p, q in pairs:
        (sp, kp), (sq, _) = flat[p], flat[q]
        if sp != sq:
            touched.setdefault((min(sp, sq), max(sp, sq)), set()).add(kp if sp < sq else flat[q][1])
    return sorted(k for k, v in touched.items() if len(v) >= 2)


def _temporal(units: list[dict]) -> list[dict]:
    out = []
    seqs = _sequences(units)
    _bump("temporal_items", len(seqs))
    for si, sj in _temporal_candidates(seqs):
        a, b = seqs[si], seqs[sj]
        if a["sent"] == b["sent"]:
            continue
        _bump("temporal_comparisons")
        common, phased = [], {}
        for i, x in enumerate(a["steps"]):
            for j, y in enumerate(b["steps"]):
                if _same_step(x, y):
                    common.append((i, j))
                elif _phase_match(a["metas"][i], b["metas"][j]):
                    common.append((i, j))
                    phased[(i, j)] = (a["metas"][i][1], b["metas"][j][1])
        if len({i for i, _ in common}) < 2:
            continue
        common.sort()
        js = [j for _, j in common]
        if all(js[k] < js[k + 1] for k in range(len(js) - 1)):
            continue
        # 開始 < 完了 の関係で両立する並び（A: 開始後に X / B: 完了前に X）は矛盾にしない
        first_i = common[0][0]
        if any((pa >= pb) is False if i == first_i else (pb >= pa) is False for (i, _), (pa, pb) in phased.items()):
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
_DEL_NO = re.compile(r"(?:削除|消去|破棄)(?:しない|されない|しません|不可|禁止)")
_ENC_NO = re.compile(r"暗号化(?:しない|不要)|平文")
_FREE = re.compile(r"無料|無償|免除")
_CHARGE_ALWAYS = re.compile(r"(?:請求|課金|徴収|有料)")
_ALWAYS = re.compile(r"常に|時期を問わず|いかなる場合も|必ず|無条件")
_ENC_YES = re.compile(r"暗号化(?:する|される|を行う)|暗号化し")
_KW = re.compile(r"即時|即座|直ちに|ただちに|すぐ|速やかに|削除|消去|破棄|保持|保存|保管|無期限|永久|暗号化|平文|無料|無償|免除|常に|時期を問わず|いかなる場合も|必ず|無条件|請求|課金|徴収|有料|しない|されない|しません|\d+\s*(?:日間|日|年|か月|週間|時間)間?")


def _semantic(units: list[dict]) -> list[dict]:
    tagged = []
    for u in units:
        for sent in _sentences(u.get("raw_text", "")):
            tags = set()
            if _IMMEDIATE_DEL.search(sent):
                tags.add("immediate_delete")
            if _DEL_NO.search(sent):
                tags.add("delete_no")
            if _RETAIN.search(sent) and (any(q["unit_kind"] == "time" for q in normalize_quantity(sent)) or _PERPETUAL.search(sent)):
                tags.add("retention")
            if _FREE.search(sent):
                tags.add("free")
            if _CHARGE_ALWAYS.search(sent) and _ALWAYS.search(sent) and not _FREE.search(sent):
                tags.add("charge_always")
            if _ENC_NO.search(sent):
                tags.add("enc_no")
            elif _ENC_YES.search(sent):
                tags.add("enc_yes")
            if tags:
                _, rest = _roles_in(_KW.sub("", sent))
                tagged.append((u, sent, tags, _grams(_clean(rest))))
    pairs = (("immediate_delete", "retention"), ("immediate_delete", "delete_no"), ("enc_no", "enc_yes"), ("free", "charge_always"))
    out = []
    _bump("semantic_items", len(tagged))
    cands: set[tuple[int, int]] = set()
    for x, y in pairs:  # タグ別の転置索引: 対応するタグ対を持つ項目だけ集めて gram で絞る
        members = [i for i, t in enumerate(tagged) if x in t[2] or y in t[2]]
        for p, q in _similar_candidates([tagged[i][3] for i in members], 0.3, "semantic"):
            i, j = members[p], members[q]
            ta, tb = tagged[i][2], tagged[j][2]
            if (x in ta and y in tb) or (y in ta and x in tb):
                cands.add((i, j))
    for i, j in sorted(cands):
        (ua, sa, ta, ga), (ub, sb, tb, gb) = tagged[i], tagged[j]
        if sa == sb:
            continue
        _bump("semantic_comparisons")
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
    STATS.clear()
    units: list[dict] = []
    for doc_id, lst in docs.items():
        for u in lst:
            d = _as_dict(u)
            d.setdefault("document_id", doc_id)
            units.append(d)
    result = _numeric(units) + _permission(units) + _temporal(units) + _semantic(units)
    uniq = {c["conflict_id"]: c for c in result}
    return sorted(uniq.values(), key=lambda c: (c["kind"], c["conflict_id"]))
