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
_REQ_END = re.compile(r"(?:ます|ません|する|とする|できる|しない|ならない|こと|される|られる|行う|shall[^.]*|must[^.]*"
                      r"|[^た][うくぐすつぬぶむる](?<!である)(?<!ている))[。.]?\s*$", re.I)  # 「である」「ている」は説明文
_REQ_CORE = re.compile(r"しなければならない|ならない|すること|とする|できる|しない|shall|must", re.I)
_QUANT = re.compile(r"以内|までに|以上|以下(?!の|に示|のとおり|のよう)|未満|超え|速やか|すぐ|直ちに|即時|即座|周期|間隔|頻度|タイムアウト|待機|保持時間")
_NUM = re.compile(r"[0-9０-９]")
_TOC = re.compile(r"\.{3,}|…{2,}|・{3,}|目次|^\s*(?:第?[0-9０-９]+(?:[.．][0-9０-９]+)*[章節.]?)\s*[^。\s]{0,30}\s*$|^\s*[-–]?\s*\d+\s*[-–]?\s*$|^\s*(?:page|p\.)\s*\d+", re.I)
# 29148 5.2.5 完全（未決定のまま残った記述）・INCOSE GtWR の不定な列挙/絶対表現/and-or。
_TBD = re.compile(r"TBD|TBA|TBC|未定(?!義|の(?:場合|とき))|未確定|未決定|検討中|調整中|別途(?:定める|決定|協議|検討)|後日|要検討"
                  r"|今後(?:決める|決定|検討|確定)|協議の上で?決定|[〇○□]{2,}|[？?]{2,}|[Xx]{3,}")
# 「項目：値」の表の行（句点が無い）は、値が未決定なら完全性の指摘の対象にする
_KV_TBD = re.compile(r"^[^：:。]{2,20}[：:]\s*\S")
# 「状態が「未定」の場合」のように、状態の値として括弧で引いた語は未決定の記述ではない
_QUOTED_WORD = re.compile(r"「([^「」]{1,8})」")
_OPEN_END = re.compile(r"(?:(?<![平同均対上高初中劣優特一二三何])等(?![級価号分])|など|ほか|その他)(?:の|を|に|で|は|が|と|、|。|）|\))"
                       r"|をはじめ(?:とする)?|といった|を含む(?:各種|情報|項目|もの)")
_UNIVERSAL = re.compile(rf"(?<![{_K}])(?:すべて|全て|常に|必ず(?!しも)|絶対に|決して|いかなる|一切|あらゆる|例外なく|常時|いつでも)"
                        rf"|どんな(?:場合|とき)も|どの[^、。]{{1,6}}(?:からでも|でも)|24時間365日|(?<![{_K}])全(?![体角額部般国])(?=[{_K}]{{2}})")
_AND_OR = re.compile(r"(?:および|及び|かつ|もしくは|または|又は|と|\band|\bor)\s*[/／]\s*(?:または|又は|もしくは|および|及び|or\b|and\b)"
                     r"|(?<![A-Za-z0-9])[一-龯ァ-ヶー]{2,}\s*[/／]\s*[一-龯ァ-ヶー]{2,}(?![/／])", re.I)
_MULTI = re.compile(r"(?:し|でき|とし)、.{4,}?(?:する|できる|とする|しない)[。]?$")
# 「〜し、〜を…する」型の連用形の連結。短い文でも要求が 2 つ以上並ぶ（ja_v1 の FN 9 件はすべてこの型）
_MULTI_CLAUSE = re.compile(r"(?:[をにへ][^、。]{0,12}?(?:し|け|い|り|み|め|せ|べ|ち)|でき|とし)、[^。]{1,}?[をにへもは][^。]{1,}?"
                           r"(?:する|できる|とする|しない|[うくぐすつぬぶむる]|ます)[。]?$"
                           r"|[うくぐすつぬぶむる]とともに、?[^。]{2,}?(?:する|できる|とする|しない|[うくぐすつぬぶむる])[。]?$")
# 「ボタンを押下し、〜を表示する」は操作（手段）と 1 つの要求であり、要求の並列ではない
_MEANS = re.compile(r"(?:押下|押|クリック|タップ|選択|入力|指定|かざ)し、")
# 数字の有無に関係なく合否を決められない量・時間の言い方（29148 5.2.5 verifiable）
_VAGUE_QUANT = re.compile(r"十分な|一定(?:期間|時間|回数|の)|当面|高速に|最小限|数(?:か月|ヶ月|カ月|日|時間|分|秒|回|件)|できるだけ|可能な限り|定期的に|しばらく|若干|長い期間|夜間|ある程度|多数の|素早く|頻繁に|大量の|長時間|短時間|適当な|適切な間隔"
                          r"|十分に|迅速|短く|長期間|低く|高い(?:信頼性|性能|可用性|精度)|高画質|余裕|安定して|一定(?:サイズ|量)"
                          r"|長め|短め|短縮|なるべく|少なく|多く|[秒分]単位"
                          r"|(?:時間|期間|容量|サイズ|速度|間隔)[はを][0-9０-９.]+(?:と|に)")  # 単位の無い数値


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
    if _KV_TBD.match(s) and _TBD.search(s):
        return False  # 「項目：未定」の表の行
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
    tbd = next((m for m in _TBD.finditer(s)
                if not any(q.start() < m.start() and m.end() < q.end() and q.group(1) == m.group(0)
                           for q in _QUOTED_WORD.finditer(s))), None)
    if tbd:
        found.append(_finding("REQ.INCOMPLETE", "critical" if crit else "major", "complete", "完全性",
                              f"「{tbd.group(0)}」が残っています。決めた内容を書くか、決める人と期限を書いてください。",
                              p, s[:80], "要確認"))
    oe = _OPEN_END.search(s)
    if oe and (_is_req(s) or s.endswith("る。")):
        # 列挙の後ろの「等」「など」「ほか」は曖昧語ではなく「列挙が閉じていない」指摘にする（重ねない）
        word = oe.group(0)[:-1] or oe.group(0)
        found = [f for f in found if not (f["rule"] in ("RD.AMBIGUOUS", "REQ.AMBIGUOUS_TERM") and f"「{word}」" in f["message"])]
        found.append(_finding("REQ.OPEN_ENDED", "minor", "unambiguous", "曖昧さ",
                              f"「{word}」で列挙が閉じていません。対象をすべて挙げてください。",
                              p, s[:80], "推定"))
    if not _is_req(s):
        return found
    un = _UNIVERSAL.search(s)
    if un:
        found.append(_finding("REQ.UNIVERSAL", "minor", "verifiable", "検証可能性",
                              f"「{un.group(0)}」は例外の無いことを求めます。例外の有無と範囲を書いてください。",
                              p, s[:80], "推定"))
    if _AND_OR.search(s):
        found.append(_finding("REQ.AND_OR", "minor", "unambiguous", "曖昧さ",
                              "「および/または」はどちらを求めるかが定まりません。片方に決めて書いてください。",
                              p, s[:80], "推定"))
    q = _VAGUE_QUANT.search(s) or (_QUANT.search(s) if not _NUM.search(s) else None)
    if q and not tbd:  # 未決定（TBD・XXX）は完全性の指摘に任せ、検証可能性と重ねない
        found.append(_finding("REQ.MEASURABILITY", "critical" if crit else "major", "verifiable", "検証可能性",
                              f"「{q.group(0)}」に数値がありません。合否を判定できる値を書いてください。",
                              p, s[:80], "推定"))
    if len(_REQ_CORE.findall(s)) >= 3 or _MULTI.search(s) and len(s) > 60 or (_MULTI_CLAUSE.search(s) and not (_MEANS.search(s) and len(_REQ_CORE.findall(s)) < 2)):
        found.append(_finding("REQ.MULTIPLE_REQUIREMENTS", "minor", "singular", "単一性",
                              "1 文に複数の要求があります。要求ごとに分けてください。", p, s[:80], "推定"))
    return found


def _check_passage(p: dict) -> list[dict]:
    found = []
    for s in _sentences(p.get("text") or ""):
        if not _is_noise(s):
            found.extend(_check_sentence(p, s))
    return found


def candidates(passages: list[dict], *, apply_disabled: bool = True) -> list[dict]:
    """規則の候補。apply_disabled=False は精度の測定用（既定で無効の規則も出す。無効化の判断を測定に混ぜない）。"""
    from web.services.docverify.accuracy import disabled_rules
    _disabled = disabled_rules() if apply_disabled else frozenset()
    seen: set[tuple[str, str, str]] = set()
    result = []
    for p in passages:
        for f in _check_passage(p):
            if f["rule"] in _disabled:
                continue  # 適合率 0.7 未満の規則は既定で無効（FR-06-170）
            key = (f["passage_id"], f["rule"] if f["rule"] not in ("RD.AMBIGUOUS", "REQ.AMBIGUOUS_TERM") else "A",
                   f["message"] + f["quote"])
            if key in seen:
                continue
            seen.add(key)
            result.append({"id": f"F{len(result) + 1}", **f})
    return result
