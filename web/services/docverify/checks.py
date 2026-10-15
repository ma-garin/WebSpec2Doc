"""自動で出す指摘の候補。reverse_doc の曖昧語と Doc2AI Lint 規則を、文単位・境界規則つきで当てる。

重大度は critical | major | minor。各指摘に ISO/IEC/IEEE 29148 の品質特性（checklist_item）を付ける。
"""
from __future__ import annotations

import re

from web.vendor.reverse_doc.ambiguity import find_ambiguous

_K = "一-龯々〆ヵヶ"
_DIGIT_CH = "0-9０-９一二三四五六七八九十百千万"

# 追加の曖昧語（29148 5.2.7 の避けるべき表現の日本語代表）。語ごとに境界規則を持つ。
_EXTRA: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("速やかに", re.compile(rf"(?<![{_K}])速やかに")),
    ("適宜", re.compile(rf"(?<![{_K}])適宜(?![{_K}])")),
    ("適当な", re.compile(rf"(?<![{_K}不])適当な")),
    ("十分な", re.compile(rf"(?<![{_K}])十分な")),
    ("一定の", re.compile(rf"(?<![{_K}])一定(?:の|周期|間隔|時間)(?![^。]{{0,6}}[0-9０-９])")),
    ("なるべく", re.compile("なるべく")),
    ("できるだけ", re.compile("できるだけ")),
    ("原則として", re.compile(rf"(?<![{_K}])原則として")),
    ("基本的に", re.compile(rf"(?<![{_K}])基本的に")),
    ("場合がある", re.compile("場合が(?:ある|あります)")),
    ("ことがある", re.compile("ことが(?:ある|あります)")),
    ("程度", re.compile(rf"(?<![{_K}{_DIGIT_CH}%％])程度(?![{_K}])")),   # 「10秒程度」は数値あり
    ("およそ", re.compile(rf"およそ(?![{_DIGIT_CH}0-9])")),
    ("約", re.compile(rf"(?<![{_K}])約(?=\s*[{_DIGIT_CH}])")),          # 数値直前のみ（制約・要約は除外）
    ("若干", re.compile(rf"(?<![{_K}])若干")),
    ("しばらく", re.compile("しばらく")),
    ("簡単に", re.compile(rf"(?<![{_K}])簡単に")),
    ("容易に", re.compile(rf"(?<![{_K}])容易に")),
    ("すぐに", re.compile("すぐに")),
    ("直ちに", re.compile(rf"(?<![{_K}])直ちに")),
    ("最適な", re.compile(rf"(?<![{_K}])最適(?:な|に)")),
    ("最大限", re.compile(rf"(?<![{_K}])最大限(?![{_K}])")),
    ("最小限", re.compile(rf"(?<![{_K}])最小限(?![{_K}])")),
    ("効率的", re.compile(rf"(?<![{_K}])効率的")),
    ("ユーザーフレンドリー", re.compile("ユーザーフレンドリー")),
    ("正しく", re.compile("正しく")),
    ("きちんと", re.compile("きちんと")),
    ("確実に", re.compile(rf"(?<![{_K}不])確実に")),
    ("その他", re.compile(rf"(?<![{_K}])その他(?:の|に|を)?(?![{_K}ア-ン])")),
)

_CRITICAL = re.compile(r"安全|停止|異常|エラー|故障|緊急|警報|アラーム|フェイル|過熱|過電流|保護|危険|インターロック", re.I)
_SENT_SPLIT = re.compile(r"(?<=[。！？!?])\s*|\n+")
_REQ_END = re.compile(r"(?:ます|ません|する|とする|できる|しない|ならない|こと|される|られる|行う|shall[^.]*|must[^.]*)[。.]?\s*$", re.I)
_REQ_CORE = re.compile(r"しなければならない|ならない|すること|とする|できる|しない|shall|must", re.I)
_QUANT = re.compile(r"以内|までに|以上|以下(?!の|に示|のとおり|のよう)|未満|超え|速やか|すぐ|直ちに|即時|即座|周期|間隔|頻度|タイムアウト|待機|保持時間")
_NUM = re.compile(r"[0-9０-９]")
_TOC = re.compile(r"\.{3,}|…{2,}|・{3,}|目次|^\s*(?:第?[0-9０-９]+(?:[.．][0-9０-９]+)*[章節.]?)\s*[^。\s]{0,30}\s*$|^\s*[-–]?\s*\d+\s*[-–]?\s*$|^\s*(?:page|p\.)\s*\d+", re.I)
# 29148 5.2.5 完全（未決定のまま残った記述）・INCOSE GtWR の不定な列挙/絶対表現/and-or。
_TBD = re.compile(r"TBD|TBA|TBC|未定|検討中|調整中|別途(?:定める|決定|協議|検討)|後日|要検討|[？?]{2,}|[Xx]{3,}")
_OPEN_END = re.compile(rf"(?:(?<![{_K}])(?:等|他)|など|ほか)(?:の|を|に|で|は|が|、|。)")
_UNIVERSAL = re.compile(rf"(?<![{_K}])(?:すべて|全て|常に|必ず|絶対に|決して|いかなる)")
_AND_OR = re.compile(r"および/または|及び/又は|and/or|又は/及び", re.I)
_MULTI = re.compile(r"(?:し|でき|とし)、.{4,}?(?:する|できる|とする|しない)[。]?$")


def _finding(rule, severity, item, viewpoint, message, passage, quote, certainty):
    return {"rule": rule, "severity": severity, "checklist_item": item, "viewpoint": viewpoint,
            "message": message, "location": passage["location"], "passage_id": passage["id"],
            "quote": quote, "certainty": certainty, "status": "candidate", "answer": None, "origin": "auto"}


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text) if s and s.strip()]


def _is_noise(s: str) -> bool:
    """目次・見出し・頁番号・ドットリーダー・短い断片は対象外。"""
    if _TOC.search(s):
        return True
    if len(s) < 8:
        return True
    return not s.endswith(("。", ".", "こと", "する", "しない", "できる", "ならない", "ます", "ません"))  # 句点の無い見出し・表セル


def _is_req(s: str) -> bool:
    return bool(_REQ_END.search(s))


def _ambiguous(s: str) -> list[tuple[str, str]]:
    out = [("RD.AMBIGUOUS", m.word) for m in find_ambiguous(s)]
    have = {w for _, w in out}
    for word, pat in _EXTRA:
        if word not in have and pat.search(s):
            out.append(("REQ.AMBIGUOUS_TERM", word))
    return out


def _check_sentence(p: dict, s: str) -> list[dict]:
    found = []
    crit = bool(_CRITICAL.search(s))
    amb = _ambiguous(s)
    for rule, word in amb:
        sev = "critical" if crit else "major"
        found.append(_finding(rule, sev, "unambiguous", "曖昧さ",
                              f"「{word}」は解釈が分かれます。具体的な条件や値にしてください。", p, s[:80], "要確認"))
    tbd = _TBD.search(s)
    if tbd:
        found.append(_finding("REQ.INCOMPLETE", "critical" if crit else "major", "complete", "完全性",
                              f"「{tbd.group(0)}」が残っています。決めた内容を書くか、決める人と期限を書いてください。",
                              p, s[:80], "要確認"))
    if not _is_req(s):
        return found
    oe = _OPEN_END.search(s)
    if oe and not any(w in oe.group(0) for _, w in amb):  # 曖昧語として指摘済みの「等」「など」は重ねない
        found.append(_finding("REQ.OPEN_ENDED", "minor", "unambiguous", "曖昧さ",
                              f"「{oe.group(0)[:-1] or oe.group(0)}」で列挙が閉じていません。対象をすべて挙げてください。",
                              p, s[:80], "推定"))
    un = _UNIVERSAL.search(s)
    if un:
        found.append(_finding("REQ.UNIVERSAL", "minor", "verifiable", "検証可能性",
                              f"「{un.group(0)}」は例外の無いことを求めます。例外の有無と範囲を書いてください。",
                              p, s[:80], "推定"))
    if _AND_OR.search(s):
        found.append(_finding("REQ.AND_OR", "minor", "unambiguous", "曖昧さ",
                              "「および/または」はどちらを求めるかが定まりません。片方に決めて書いてください。",
                              p, s[:80], "推定"))
    q = _QUANT.search(s)
    if q and not _NUM.search(s):
        found.append(_finding("REQ.MEASURABILITY", "critical" if crit else "major", "verifiable", "検証可能性",
                              f"「{q.group(0)}」に数値がありません。合否を判定できる値を書いてください。",
                              p, s[:80], "推定"))
    if len(_REQ_CORE.findall(s)) >= 3 or _MULTI.search(s) and len(s) > 60:
        found.append(_finding("REQ.MULTIPLE_REQUIREMENTS", "minor", "singular", "単一性",
                              "1 文に複数の要求があります。要求ごとに分けてください。", p, s[:80], "推定"))
    return found


def _check_passage(p: dict) -> list[dict]:
    found = []
    for s in _sentences(p.get("text") or ""):
        if not _is_noise(s):
            found.extend(_check_sentence(p, s))
    return found


def candidates(passages: list[dict]) -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    result = []
    for p in passages:
        for f in _check_passage(p):
            key = (f["passage_id"], f["rule"] if f["rule"] not in ("RD.AMBIGUOUS", "REQ.AMBIGUOUS_TERM") else "A",
                   f["message"] + f["quote"])
            if key in seen:
                continue
            seen.add(key)
            result.append({"id": f"F{len(result) + 1}", **f})
    return result
