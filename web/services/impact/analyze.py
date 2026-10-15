"""影響度分析の本体。変更箇所の抽出 → クエリ生成 → 文書検索 → 統合 → 影響度 → 優先度。

LLM は使わず規則で判定する（同じ入力なら同じ結果になり、根拠を文書の一致語で説明できる）。
"""
from __future__ import annotations

import math
import re
import unicodedata

from web.services.docverify.diff import compare

# 壊れたときの害が大きい語。当たったら影響度を「致命」に上げる候補にする。
HARM = ("金額", "料金", "決済", "支払", "請求", "課金", "税", "ポイント", "個人情報", "パスワード", "認証",
        "ログイン", "権限", "削除", "消失", "一括", "取込", "取り込み", "バッチ", "移行", "連携", "停止", "排他",
        "セキュリティ", "暗号", "在庫", "締め")
# 同じ部品・同じ規則を使い回していることを示す語。間接の影響を拾う。
SHARED = ("共通", "共用", "流用", "同じ", "同一", "参照", "準拠", "準ずる", "引き継", "連動")
STOP = {"こと", "もの", "ため", "場合", "とき", "これ", "それ", "以下", "以上", "未満", "について", "および",
        "または", "する", "される", "できる", "ある", "なる", "行う", "変更", "追加", "削除", "修正", "対応",
        "画面", "項目", "機能", "処理", "表示", "入力", "仕様", "設計", "概要", "備考", "なし", "あり"}
LEVELS = {4: "致命", 3: "大", 2: "中", 1: "小"}
# 変わった語と同じ規則を別の言い方で書いた語。仕様書は同じことを別の語で書くので、差分の語を広げて探す。
SYN = {"必須": ("未入力", "空欄", "省略", "入力必須"), "任意": ("未入力", "空欄", "省略"),
       "桁": ("桁数", "文字数", "長さ"), "文字": ("文字数", "桁数", "長さ"), "上限": ("最大", "以内", "超え"),
       "下限": ("最小", "以上", "未満"), "表示": ("非表示", "表記"), "削除": ("論理削除", "物理削除")}

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{1,}|[ァ-ヶー]{2,}|[一-龥々]{2,}|[0-9]+ ?(?:桁|文字|件|円|日|%)")
_SENT = re.compile(r"[。\n]+")


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "")


def tokens(text: str) -> list[str]:
    seen, out = set(), []
    for t in _TOKEN.findall(_norm(text)):
        t = t.strip(".").replace(" ", "")
        if len(t) < 2 or t in STOP or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _clip(text: str, n: int = 120) -> str:
    text = re.sub(r"\s+", " ", _norm(text)).strip()
    text = re.sub(r"^(?:[-*・●#]+\s*)+", "", text)
    return text if len(text) <= n else text[:n] + "…"


# ---- 変更箇所の抽出 ----
def _doc(p: dict) -> str:
    return str(p.get("id") or "").split("#")[0]


def extract_changes(order: str, old: list[dict], new: list[dict]) -> list[dict]:
    """変更前と変更後の断片を比べる。変更前が無ければ、利用者の指示を 1 文 = 1 変更として扱う。"""
    changes = []
    if old and new:
        d = compare(old, new)
        for c in d["changed"]:
            changes.append({"kind": "変更", "location": f"{_doc(c['new'])} {c['new']['location']}".strip(),
                            "before": c["old"]["text"], "after": c["new"]["text"]})
        for p in d["added"]:
            changes.append({"kind": "追加", "location": f"{_doc(p)} {p['location']}".strip(), "before": "", "after": p["text"]})
        for p in d["removed"]:
            changes.append({"kind": "削除", "location": f"{_doc(p)} {p['location']}".strip(), "before": p["text"], "after": ""})
    if not changes:
        for s in _SENT.split(_norm(order)):
            if len(s.strip()) >= 4:
                changes.append({"kind": "指示", "location": "変更の指示", "before": "", "after": s.strip()})
    changes = changes[:40]
    return [{**c, "id": f"C{i}", "before": _clip(c["before"], 300), "after": _clip(c["after"], 300)}
            for i, c in enumerate(changes, start=1)]


# ---- クエリ生成 ----
def make_queries(changes: list[dict], order: str) -> list[dict]:
    """変更 1 件につき、主題の語（変わっていない語）と差分の語（変わった語と言い換え）で検索語を作る。"""
    order_terms = set(tokens(order))
    queries = []
    for c in changes:
        before, after = tokens(c["before"]), tokens(c["after"])
        diff = list(dict.fromkeys([t for t in after if t not in before] + [t for t in before if t not in after]))
        subject = [t for t in dict.fromkeys(after + before) if t not in diff]
        subject.sort(key=lambda t: (t not in order_terms, -len(t)))
        if not subject:
            subject, diff = diff[:2], diff[2:]
        expanded = list(diff)
        for t in diff:
            for key, words in SYN.items():
                if key in t:
                    expanded += [w for w in words if w not in expanded]
        subject = subject[:3]
        if not subject:
            continue
        queries.append({"id": f"Q{len(queries) + 1}", "from": c["id"], "subject": subject, "diff": expanded[:10],
                        "terms": subject + expanded[:10], "must": subject[:1]})
    return queries


# ---- 文書検索 ----
def search(queries: list[dict], corpus: list[dict], exclude: set[str]) -> list[dict]:
    """断片ごとに一致語の IDF 合計で採点する。主題の語（must）を含まない断片は落とす。"""
    n = max(len(corpus), 1)
    df: dict[str, int] = {}
    texts = [re.sub(r"\s+", "", _norm(p["text"])) for p in corpus]
    for q in queries:
        for t in q["terms"]:
            if t not in df:
                df[t] = sum(1 for x in texts if t in x)
    hits = []
    for q in queries:
        for p, text in zip(corpus, texts):
            key = f"{p['doc']}|{p['location']}"
            if key in exclude or not any(m in text for m in q["must"]):
                continue
            matched = [t for t in q["terms"] if t in text]
            diff_hit = [t for t in q["diff"] if t in text]
            score = sum(math.log(1 + n / (1 + df[t])) for t in matched)
            hits.append({"query": q["id"], "from": q["from"], "key": key, "doc": p["doc"], "store": p["store"],
                         "location": p["location"], "section": p.get("section", ""), "text": p["text"], "matched": matched,
                         "ratio": 1.0 if diff_hit else 0.0, "diff_hit": diff_hit, "score": round(score, 2)})
    for q in queries:
        mine = sorted((h for h in hits if h["query"] == q["id"]), key=lambda h: -h["score"])
        q["hit"] = len(mine)
        q["stores"] = sorted({h["store"] for h in mine})
    return hits


# ---- 統合・影響度・優先度 ----
def _level(direct: bool, text: str, store: str) -> tuple[int, list[str]]:
    """主題の語だけ一致 = 小、変わった規則の語も一致 = 大。共有の語で +1、害の大きい語で致命。"""
    reasons = []
    level = 3 if direct else 1
    if direct:
        reasons.append("変わった規則そのもの（値・条件）に触れている")
    shared = [w for w in SHARED if w in text]
    if shared:
        level = min(level + 1, 3)
        reasons.append(f"「{shared[0]}」とあり、同じ規則・部品を使っている")
    harm = [w for w in HARM if w in text]
    if harm and level >= 2:
        level = 4
        reasons.append(f"「{harm[0]}」に関わり、壊れると業務への害が大きい")
    if store == "テストケース":
        level = min(level, 3)
    return level, reasons


def _test_for(store: str, where: str, change: dict) -> str:
    after = _clip(change["after"] or change["before"], 40)
    if store == "テストケース":
        return "期待値を変更後の仕様（" + after + "）に直してから再実行する"
    if store == "画面仕様書":
        return f"{where} で、変更後の条件（{after}）の入力・表示・エラーを確かめる"
    return f"{where} の処理を変更後の条件（{after}）で通し、前後の処理への受け渡しを確かめる"


def judge(changes: list[dict], hits: list[dict]) -> list[dict]:
    by_change = {c["id"]: c for c in changes}
    merged: dict[str, dict] = {}
    for h in hits:
        m = merged.setdefault(h["key"], {**h, "queries": [], "changes": [], "matched_all": []})
        m["queries"] = sorted(set(m["queries"]) | {h["query"]})
        m["changes"] = sorted(set(m["changes"]) | {h["from"]}, key=lambda x: int(x[1:]))
        m["matched_all"] = list(dict.fromkeys(m["matched_all"] + h["matched"]))
        if h["ratio"] > m["ratio"]:
            m.update(ratio=h["ratio"], score=h["score"], matched=h["matched"])
    rows = []
    for m in merged.values():
        change = by_change[m["changes"][0]]
        level, reasons = _level(m["ratio"] > 0, _norm(m["text"]), m["store"])
        place = f"{m['section']}（{m['location']}）" if m.get("section") else m["location"]
        where = f"{m['doc']} {place}"
        why = (f"変更 {'・'.join(m['changes'])} と同じ語（{'・'.join(m['matched_all'][:4])}）を含む。"
               + ("".join(r + "。" for r in reasons)))
        if m["store"] == "テストケース":
            why += ("既存のテストが変更前の仕様を期待値にしている。" if level >= 3
                    else "既存のテストの期待値が変更前の仕様のままか確かめる。")
        rows.append({"level": level, "level_name": LEVELS[level], "priority": 1 if level == 4 else 2 if level == 3 else 3,
                     "where": where, "doc": m["doc"], "store": m["store"], "location": m["location"],
                     "changes": m["changes"], "queries": m["queries"], "why": why,
                     "quote": _clip(m["text"], 160), "test": _test_for(m["store"], m.get("section") or m["location"], change), "place": place,
                     "score": m["score"], "confirmed": True, "method": "rule"})
    found = {c for r in rows for c in r["changes"]}
    for c in changes:
        if c["id"] not in found:
            rows.append({"level": 0, "level_name": "未確認", "priority": 2, "where": c["location"], "doc": "", "store": "",
                         "location": c["location"], "place": c["location"], "changes": [c["id"]], "queries": [],
                         "why": "検索先の文書に関係する記述が見つからない。影響なしとは言えないため、担当者に確かめる。",
                         "quote": "", "test": "影響範囲を担当者に確かめ、検索先に足りない文書があれば取り込んで再分析する",
                         "score": 0, "confirmed": False, "method": "rule"})
    rows.sort(key=lambda r: (r["priority"], -r["level"], -r["score"]))
    return [{**r, "id": f"I{i}"} for i, r in enumerate(rows, start=1)]


def _apply_llm(changes: list[dict], hits: list[dict], impacts: list[dict], llm_judge) -> tuple[list[dict], dict]:
    """規則の候補を LLM に判定させ、関係なしは落とし、影響度・理由・テストを置き換える。"""
    by_key: dict[str, dict] = {}
    for h in sorted(hits, key=lambda h: -h["score"]):
        if h["key"] not in by_key:
            place = f"{h['section']}（{h['location']}）" if h.get("section") else h["location"]
            by_key[h["key"]] = {"key": h["key"], "doc": h["doc"], "place": place, "text": h["text"]}
    verdicts = llm_judge(changes, list(by_key.values()))
    if verdicts is None:
        return impacts, {"mode": "rule", "reason": "LLM に接続できないため、語の一致による規則で判定しました。"}
    v = {x["key"]: x for x in verdicts}
    out = []
    for r in impacts:
        key = f"{r['doc']}|{r['location']}"
        x = v.get(key)
        if not r["confirmed"] or x is None:
            out.append({**r, "method": "rule"})
            continue
        if not x["related"]:
            continue
        lv = int(x["level"])
        if r["store"] == "テストケース":
            lv = min(lv, 3)
        out.append({**r, "level": lv, "level_name": LEVELS[lv], "priority": 1 if lv == 4 else 2 if lv == 3 else 3,
                    "why": x["why"].strip() or r["why"], "test": x["test"].strip() or r["test"], "method": "llm"})
    out.sort(key=lambda r: (r["priority"], -r["level"], -r["score"]))
    return [{**r, "id": f"I{i}"} for i, r in enumerate(out, start=1)], {"mode": "llm", "reason": ""}


def run(order: str, docs: list[dict], read, llm_judge=None) -> dict:
    """docs は job["docs"]（文書庫の文書を含む）、read(name) は断片の一覧を返す関数。
    llm_judge を渡すと、規則の候補を LLM で判定し直す（失敗時は規則のまま）。"""
    def tagged(d):
        out, section = [], ""
        for p in read(d["name"]):
            text = _norm(p["text"]).strip()
            if text.startswith("#") or (len(text) <= 24 and not re.search(r"[。、:：]", text)):
                section = _clip(text, 30)
            out.append({**p, "id": f"{d['name']}#{p.get('id')}", "doc": d["name"], "store": d["store"], "section": section})
        return out
    old = [p for d in docs if d["role"] == "old" for p in tagged(d)]
    new = [p for d in docs if d["role"] == "new" for p in tagged(d)]
    corpus = [p for d in docs if d["role"] in ("new", "store") for p in tagged(d)]
    notes = []
    if not new:
        notes.append("変更後の文書がありません。変更の指示だけで分析しました。")
    elif not old:
        notes.append("変更前の文書がありません。差分は取らず、変更の指示から変更箇所を作りました。")
    if not any(d["role"] == "store" for d in docs):
        notes.append("検索先の文書（設計書・画面仕様書・既存テストケース）がありません。変更後の文書の中だけを検索しました。")
    changes = extract_changes(order, old, new)
    if not changes:
        return {"changes": [], "queries": [], "impacts": [], "engine": {"mode": "rule", "reason": ""},
                "notes": notes + ["変更箇所を見つけられませんでした。変更前の文書か、変更の指示を入れてください。"]}
    queries = make_queries(changes, order)
    exclude = {f"{p['doc']}|{p['location']}" for p in new
               if any(_norm(c["after"])[:60] and _norm(c["after"])[:60] in _norm(p["text"]) for c in changes)}
    hits = search(queries, corpus, exclude)
    impacts = judge(changes, hits)
    engine = {"mode": "rule", "reason": "語の一致による規則で判定しました。"}
    if llm_judge is not None:
        impacts, engine = _apply_llm(changes, hits, impacts, llm_judge)
    for q in queries:
        q["merged"] = len({r["id"] for r in impacts if q["id"] in r["queries"]})
    return {"changes": changes, "queries": queries, "impacts": impacts, "notes": notes, "engine": engine}
