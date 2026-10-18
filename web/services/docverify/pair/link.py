"""要件定義書の単位と基本設計書の単位を対応付け（追跡リンク）、
設計に反映の無い要件（MISSING_IN_DESIGN）と、要件に根拠の無い設計（EXTRA_IN_DESIGN）を出す。

手法（標準ライブラリだけ）:
1. 設計書は「同じ見出しの下の単位のまとまり」（節）を比較の単位にする。
2. 要件 ID（REQ-nnn）が節の本文か見出しに現れれば、最優先でリンクする。
3. それ以外は文字 2〜3-gram の TF-IDF コサインで類似度を出し、
   絶対閾値と「その要件の最良スコアに対する比」の両方を超えた節をリンクする。
4. 要件の注記（「背景:」等）・表題・章の導入文は要件として扱わない。
5. 概要の章・用語・画面一覧のような索引の表は、リンクにも EXTRA にも使わない。
6. 固有語の大半が設計書に無く類似度も低い要件だけを未反映とし、他は最良の節へリンクする。
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

from .segment import ID_RE, Unit

# 閾値（開発用の組で決めた汎用値。組ごとの固有値は持たない）
LINK_MIN = 0.13      # これ未満の類似度ではリンクしない
LINK_REL = 0.50      # 要件ごとの最良スコアに対する比
ID_SCORE = 1.0       # ID 一致のスコア
EXTRA_MAX = 0.12     # どの要件ともこの類似度未満の節を根拠なしとみなす
LINE_W = 0.8         # 行単位の類似度にかける重み（短い行どうしは高く出やすい）
USE_SCORE = 0.5
HEAD_COVER = 0.6     # 見出しの 2-gram がこの割合以上 1 つの要件に現れる節は根拠ありとみなす
GAP_RATIO = 0.2      # 要件の固有語のうち設計書に無い割合がこれを超え、
GAP_SIM = 0.15       # かつ最良の類似度がこれ未満なら、未反映とみなす
_TERM = re.compile(r"[一-龥々]{2,}|[ァ-ヴー]{2,}|[A-Za-z]{2,}")      # 使用性の要件と操作性の節の対応に与えるスコア
_FUNC_CHAPTER = ("機能", "画面")   # EXTRA を探す章（データ・外部 IF・非機能は対象外）
_NONFUNC = "非機能"
# ISO/IEC 25010 の使用性: 主観語だけの要件は、語彙が重ならない「操作性」等の節で実現される
_USABILITY_REQ = re.compile(r"使いやす|分かりやす|わかりやす|迷わず|快適に操作|操作性|使用性|利用性")
_USABILITY_SEC = re.compile(r"操作性|使いやす|分かりやす|利用性|使用性|ユーザビリティ|共通")
_CODE = re.compile(r"\b[A-Z]{1,5}-?\d{1,4}\b")

_NOTE = re.compile(r"^(?:[-*+]|\d+[.)])\s*(?:背景|理由|補足|備考|根拠|目的|注記?|出典|例)\s*[:：]")
_CAPTION = re.compile(r"^(?:表|図)\s*[\d０-９]")
_INTRO = re.compile(r"(?:に関する|向けの|の)要件(?:を定める|である|とする)。?$")
_OVERVIEW = ("概要", "はじめに", "目的", "用語", "改訂", "変更履歴", "前提", "範囲",
             "位置づけ", "システム構成", "設計方針", "参照", "文書")
_INDEX = ("一覧",)
_HEAD_STRIP = re.compile(r"^[\d.\s]+|[（(][^)）]*[)）]?|\[[^\]]*\]?")
_DROP = re.compile(r"[\s\W_]+", re.UNICODE)


def _is_target(u: Unit) -> bool:
    """要件として追跡すべき単位か（注記・表題・章の導入文を除く）。"""
    text = u.text.strip()
    if u.kind == "item" and _NOTE.match(text):
        return False
    if u.kind == "para" and not u.ids:
        if _CAPTION.match(text):
            return False
        if len(text) <= 40 and _INTRO.search(text):
            return False
    return True


def targets(req_units: list[Unit]) -> list[Unit]:
    """要件の単位から、追跡の対象になる要件だけを返す。"""
    return [u for u in req_units if _is_target(u)]


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = ID_RE.sub(" ", unicodedata.normalize("NFKC", text).upper()).lower()
    return _DROP.sub("", text)


def _grams(text: str) -> Counter:
    s = _norm(text)
    return Counter(s[i:i + n] for n in (2, 3) for i in range(len(s) - n + 1))


def _section_unit(units: list[Unit]) -> Unit:
    head = units[0].heading
    text = "\n".join(u.text for u in units)
    ids = tuple(dict.fromkeys(i for u in units for i in u.ids))
    head_ids = tuple(ID_RE.findall(head[-1])) if head else ()
    ids = tuple(dict.fromkeys(ids + head_ids))
    return Unit("section", units[0].start, units[-1].end, text, head, ids)


def sections(design_units: list[Unit]) -> list[Unit]:
    """設計の単位を、同じ見出しの下の連続したまとまり（節）にまとめる。"""
    groups: list[list[Unit]] = []
    for u in design_units:
        if groups and groups[-1][0].heading == u.heading:
            groups[-1].append(u)
        else:
            groups.append([u])
    return [_section_unit(g) for g in groups]


def _is_overview(sec: Unit) -> bool:
    """概要の章・用語・索引の表など、要件と対応しなくて当然の節か。"""
    heads = sec.heading
    if not heads:
        return True
    if any(k in h for h in heads[1:2] for k in _OVERVIEW):
        return True
    if any(k in heads[-1] for k in _OVERVIEW):
        return True
    only_rows = all(line.lstrip().startswith("|") for line in sec.text.splitlines())
    return only_rows and any(k in heads[-1] for k in _INDEX)


class _Index:
    """節と要件の文字 n-gram を TF-IDF ベクトルにする。"""

    def __init__(self, docs: list[str]):
        grams = [_grams(d) for d in docs]
        df = Counter(g for c in grams for g in c)
        n = len(docs)
        self.idf = {g: math.log((n + 1) / (k + 1)) + 1.0 for g, k in df.items()}

    def vec(self, text: str) -> dict[str, float]:
        c = _grams(text)
        v = {g: (1.0 + math.log(k)) * self.idf.get(g, 1.0) for g, k in c.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {g: x / norm for g, x in v.items()}


def _cos(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(g, 0.0) for g, x in a.items())


def _sec_text(sec: Unit) -> str:
    return (sec.heading[-1] if sec.heading else "") + "\n" + sec.text


def _line_vecs(index: "_Index", sec: Unit) -> list[dict[str, float]]:
    """節の各行（見出し付き）のベクトル。長い節で類似度が薄まるのを防ぐ。"""
    head = sec.heading[-1] if sec.heading else ""
    lines = [ln for ln in sec.text.splitlines() if _norm(ln)] or [""]
    return [index.vec(head + "\n" + ln) for ln in lines]


def _usability(r: Unit, s: Unit) -> bool:
    head = s.heading[-1] if s.heading else ""
    return bool(_USABILITY_REQ.search(r.text) and _USABILITY_SEC.search(head))


def _sim(rv, sv, lvs) -> float:
    return max([_cos(rv, sv)] + [LINE_W * _cos(rv, lv) for lv in lvs])


def _scores(reqs: list[Unit], secs: list[Unit]) -> list[list[float]]:
    """要件 × 節 の類似度の行列（ID 一致は ID_SCORE）。"""
    index = _Index([_sec_text(s) for s in secs] + [r.text for r in reqs])
    svecs = [index.vec(_sec_text(s)) for s in secs]
    lvecs = [_line_vecs(index, s) for s in secs]
    table = []
    for r in reqs:
        rv = index.vec(r.text)
        row = []
        for s, sv, lvs in zip(secs, svecs, lvecs):
            sc = _sim(rv, sv, lvs)
            if _usability(r, s):
                sc = max(sc, USE_SCORE)
            row.append(ID_SCORE + sc if set(r.ids) & set(s.ids) else sc)
        table.append(row)
    return table


def _bridge(all_secs: list[Unit]) -> dict[str, set[str]]:
    """索引の表（画面一覧など）の行から、画面 ID 等の符号 → 要件 ID の対応を作る。"""
    out: dict[str, set[str]] = {}
    for sec in all_secs:
        if not _is_overview(sec):
            continue
        for line in sec.text.splitlines():
            ids = set(ID_RE.findall(line))
            for code in set(_CODE.findall(ID_RE.sub(" ", line))) if ids else ():
                out.setdefault(code, set()).update(ids)
    return out


def _candidates(design_units: list[Unit]) -> list[Unit]:
    """リンク候補の節。索引の表の ID は、見出しに同じ符号を持つ節へ引き継ぐ。"""
    all_secs = sections(design_units)
    bridge = _bridge(all_secs)
    out = []
    for s in all_secs:
        if _is_overview(s):
            continue
        codes = set(_CODE.findall(ID_RE.sub(" ", s.heading[-1]))) if s.heading else set()
        add = tuple(sorted(set().union(*(bridge.get(c, set()) for c in codes))))
        out.append(s if not add else Unit(s.kind, s.start, s.end, s.text, s.heading,
                                          tuple(dict.fromkeys(s.ids + add))))
    return out


def _corpus(units: list[Unit]) -> str:
    heads = {h for u in units for h in u.heading}
    return unicodedata.normalize("NFKC", "\n".join([u.text for u in units] + sorted(heads)))


def _absent(text: str, corpus: str) -> float:
    """要件の固有語（漢字・カタカナ・英字の連なり）のうち、設計書全体に現れない割合。"""
    terms = _TERM.findall(ID_RE.sub(" ", unicodedata.normalize("NFKC", text)))
    return sum(t not in corpus for t in terms) / len(terms) if terms else 0.0


def _pick(row: list[float]) -> list[int]:
    best = max(row)
    out = []
    for j, sc in enumerate(row):
        if sc >= ID_SCORE or (sc >= LINK_MIN and sc >= best * LINK_REL and best < ID_SCORE):
            out.append(j)
        elif best >= ID_SCORE and sc >= max(LINK_MIN, (best - ID_SCORE) * LINK_REL):
            out.append(j)
    return out


def link(req_units: list[Unit], design_units: list[Unit]) -> list[tuple[Unit, Unit, float]]:
    """要件単位と設計の節の対応（スコア付き）。

    要件の固有語が設計書に無く（GAP_RATIO 超）類似度も低い（GAP_SIM 未満）要件だけを
    未反映として残し、それ以外は閾値に届かなくても最良の節へリンクする
    （言い換えの多い短い要件で、語の重なりが少ないだけの取り逃しを防ぐ）。
    """
    reqs = targets(req_units)
    secs = _candidates(design_units)
    if not reqs or not secs:
        return []
    corpus = _corpus(design_units)
    out: list[tuple[Unit, Unit, float]] = []
    for r, row in zip(reqs, _scores(reqs, secs)):
        best = max(row)
        if best < GAP_SIM and _absent(r.text, corpus) > GAP_RATIO:
            continue
        picked = _pick(row) or [row.index(best)]
        out.extend((r, secs[j], round(row[j], 4)) for j in picked)
    return out


def missing(req_units: list[Unit], links: list[tuple[Unit, Unit, float]]) -> list[Unit]:
    """設計に対応の無い要件。"""
    linked = {(r.start, r.end) for r, _, _ in links}
    return [u for u in targets(req_units) if (u.start, u.end) not in linked]


def _head_cover(sec: Unit, req_norms: list[str]) -> float:
    """節の見出し（番号・符号・括弧書きを除く）の文字 2-gram が、1 つの要件に含まれる割合の最大。"""
    head = _CODE.sub(" ", unicodedata.normalize("NFKC", sec.heading[-1]).upper())
    h = _norm(_HEAD_STRIP.sub(" ", head))
    grams = {h[i:i + 2] for i in range(len(h) - 1)}
    if len(grams) < 2:
        return 0.0
    return max((sum(g in r for g in grams) / len(grams) for r in req_norms), default=0.0)


def _table_only(sec: Unit) -> bool:
    """表題と表の行だけの節（一覧表）。機能の設計ではないので EXTRA にしない。"""
    lines = [ln.strip() for ln in sec.text.splitlines() if ln.strip()]
    return bool(lines) and all(ln.startswith("|") or _CAPTION.match(ln) for ln in lines)


def _extra_candidate(s: Unit, req_ids: set[str], req_norms: list[str]) -> bool:
    return (len(s.heading) > 1 and _NONFUNC not in s.heading[1]
            and any(k in s.heading[1] for k in _FUNC_CHAPTER)
            and not set(s.ids) & req_ids and not _table_only(s)
            and _head_cover(s, req_norms) < HEAD_COVER)


def extra(design_units: list[Unit], req_units: list[Unit],
          links: list[tuple[Unit, Unit, float]]) -> list[Unit]:
    """要件に根拠の無い設計の節（概要・用語・索引の表・見出しが要件に現れる節は除く）。"""
    linked = {(s.start, s.end) for _, s, _ in links}
    reqs = targets(req_units)
    req_ids = {i for r in req_units for i in r.ids}
    req_norms = [_norm(r.text) for r in reqs]
    secs = [s for s in _candidates(design_units) if (s.start, s.end) not in linked
            and _extra_candidate(s, req_ids, req_norms)]
    if not secs or not reqs:
        return secs
    allsecs = _candidates(design_units)
    table = _scores(reqs, allsecs)
    pos = {(s.start, s.end): j for j, s in enumerate(allsecs)}
    return [s for s in secs if max(row[pos[(s.start, s.end)]] for row in table) < EXTRA_MAX]
