"""入力の間の食い違い検出（REQ-F-006, REQ-F-006-01〜03）。

コード・画面・文書に由来する記述から「主題」と「値」を正規表現で抜き（LLM 無し）、
主題が一致して値が異なる組を食い違い（Conflict）とする。
  - 各記述の確度は付与表のまま変えない（Statement は一切書き換えない。REQ-F-006-01）
  - 文書とコード（または画面）: コード側を現行の振る舞いとし、文書側を並記する。どちらも消さない（REQ-F-006-02）
  - 文書どうし: Tier の数字が小さい方を採り、下位は採らずに台帳へ。同じ Tier・不明なら両方を台帳へ（REQ-F-006-03）
主題・値を抜けない記述は対象外として analyze() の skipped に理由つきで返す（黙って捨てない）。
限界: 「100 未満」と「99 以下」は境界の含み方が違うため食い違いとして扱う。主題の語順が違う記述は一致しない。
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable, Literal

from web.vendor.reverse_doc.confidence import origin_of
from web.vendor.reverse_doc.models import Question, Statement

ConflictKind = Literal["値", "条件", "項目の有無"]
TierOf = Callable[[Statement], "int | None"]

TARGET_ORIGINS = ("code", "screen", "document", "test")
FACT_ORIGINS = ("code", "screen")
SOFT_ORIGINS = ("document", "test")     # 書かれた主張の側。コードを採り並記する（優先 code > screen > document = test。Tier は無し）
ORIGIN_LABEL = {"code": "コード", "screen": "画面", "document": "文書", "test": "テスト"}
TIER_RANGE = range(1, 5)

_SIZE = {"B": 1, "バイト": 1, "KB": 1024, "KIB": 1024, "キロバイト": 1024,
         "MB": 1024 ** 2, "MIB": 1024 ** 2, "メガバイト": 1024 ** 2,
         "GB": 1024 ** 3, "GIB": 1024 ** 3, "ギガバイト": 1024 ** 3}
_TIME = {"ミリ秒": Fraction(1, 1000), "MS": Fraction(1, 1000), "秒": 1, "分": 60, "時間": 3600, "日": 86400}
_COUNT = ("文字", "字", "件", "個", "回", "桁", "行", "円", "%", "人", "ページ", "頁")
_UNITS = sorted([*_SIZE, *_TIME, *_COUNT], key=len, reverse=True)
_NUM_RE = re.compile(r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(" + "|".join(map(re.escape, _UNITS)) + r")?",
                     re.IGNORECASE)
_LT_RE = re.compile(r"未満")
_LE_RE = re.compile(r"以下|以内|まで|上限|最大|最長|超え(?:る|た)?(?:と|場合|とき|なら)|超過")
_GT_RE = re.compile(r"超|より大きい")
_GE_RE = re.compile(r"以上|下限|最小|最短|最低")
_REQUIRED_RE = re.compile(r"必須|任意|省略可能?|省略できる")
_ENUM_RE = re.compile(r"^(?P<subj>.+?)(?:は|が|:)\s*(?P<items>.+?)\s*の\s*(?:いずれか|どれか)")
_STRIP_WORDS = sorted(
    ("上限値", "下限値", "最大値", "最小値", "最大長", "最小長", "文字列長", "上限", "下限", "最大", "最小",
     "最長", "最短", "最低", "文字数", "字数", "サイズ", "容量", "件数", "個数", "回数", "桁数", "長さ",
     "時間", "入力", "値", "以下", "以内", "以上", "未満", "まで"), key=len, reverse=True)
_PUNCT_RE = re.compile(r"[\s:;,.、。・「」『』()\[\]{}<>\"'`=]+")
_PARTICLE_RE = re.compile(r"[のはがをも]")


@dataclass(frozen=True)
class Claim:
    """記述 1 件から抜いた主張。key が一致して value が異なれば食い違い。"""
    subject: str                       # 正規化した主題
    aspect: str                        # max / min / eq / required / enum
    dimension: str                     # size / time / 単位そのもの / ""
    value: object                      # 比較に使う正規化値
    display: str                       # 台帳に載せる値の表記
    kind: ConflictKind

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.subject, self.aspect, self.dimension)


@dataclass(frozen=True)
class Conflict:
    subject: str                       # 対象（項目名・主題。正規化後）
    kind: ConflictKind                 # 値／条件／項目の有無
    first: Statement                   # 採る側（採る側が無いときはコード側・上位側・先に現れた側）
    second: Statement
    first_value: str
    second_value: str
    adopted: Statement | None          # 採る側。None は決められない（同じ Tier・コードと画面）


@dataclass(frozen=True)
class Detection:
    conflicts: tuple[Conflict, ...]
    skipped: tuple[tuple[Statement, str], ...]   # (記述, 対象外の理由)


def normalize_subject(text: str) -> str:
    """全角半角・空白・記号・「の」「は」等の助詞・上限/文字数等の語を除いた主題。"""
    s = unicodedata.normalize("NFKC", text)
    for w in _STRIP_WORDS:
        s = s.replace(w, "")
    s = _PUNCT_RE.sub("", s)
    return _PARTICLE_RE.sub("", s).lower()


def _bound(text: str) -> tuple[str, bool]:
    if _LT_RE.search(text):
        return "max", False
    if _LE_RE.search(text):
        return "max", True
    if _GT_RE.search(text):
        return "min", False
    if _GE_RE.search(text):
        return "min", True
    return "eq", True


def _scaled(number: str, unit: str | None) -> tuple[str, Fraction]:
    n = Fraction(number.replace(",", ""))
    if not unit:
        return "", n
    up = unit.upper()
    if up in _SIZE:
        return "size", n * _SIZE[up]
    if up in _TIME:
        return "time", n * Fraction(_TIME[up])
    return unit, n


def _numeric_claim(text: str) -> Claim | None:
    """主題を前に持つ最初の数値を値とする（「1 ページの表示件数は 30 件」の 1 は主題の一部）。"""
    found = [(m, normalize_subject(text[:m.start()])) for m in _NUM_RE.finditer(text)]
    found = [(m, s) for m, s in found if s]
    if not found:
        return None
    m, subject = found[0]
    aspect, inclusive = _bound(text)
    if not m.group(2) and aspect == "eq":
        return None  # 単位も上限下限の語も無い数字は値と断定しない
    dimension, scaled = _scaled(m.group(1), m.group(2))
    mark = {("max", True): "以下", ("max", False): "未満", ("min", True): "以上",
            ("min", False): "超", ("eq", True): ""}[(aspect, inclusive)]
    display = f"{m.group(1)}{m.group(2) or ''}{mark}"
    return Claim(subject, aspect, dimension, (scaled, inclusive), display, "値")


def _required_claim(text: str) -> Claim | None:
    m = _REQUIRED_RE.search(text)
    subject = normalize_subject(text[:m.start()]) if m else ""
    if not m or not subject:
        return None
    value = "必須" if m.group(0) == "必須" else "任意"
    return Claim(subject, "required", "", value, value, "条件")


def _enum_claim(text: str) -> Claim | None:
    m = _ENUM_RE.search(text)
    if not m:
        return None
    raw = m.group("items")
    items = re.findall(r"「(.+?)」", raw) or re.split(r"[・、,/]", raw)
    values = frozenset(i.strip() for i in items if i.strip())
    subject = normalize_subject(m.group("subj"))
    if len(values) < 2 or not subject:
        return None
    return Claim(subject, "enum", "", values, "・".join(sorted(values)), "項目の有無")


def extract(statement: Statement) -> Claim | None:
    """記述から主題と値を抜く。抜けなければ None。"""
    text = unicodedata.normalize("NFKC", statement.text)
    for fn in (_numeric_claim, _required_claim, _enum_claim):
        claim = fn(text)
        if claim is not None:
            return claim
    return None


def _no_tier(_st: Statement) -> int | None:
    return None


def _checked_tier(tier_of: TierOf, st: Statement) -> int | None:
    tier = tier_of(st)
    if tier is not None and (not isinstance(tier, int) or tier not in TIER_RANGE):
        raise ValueError(f"Tier の値が不正: {tier!r}（1〜4 の整数か None）")
    return tier


def _order(a: Statement, b: Statement, tier_of: TierOf) -> tuple[Statement, Statement, Statement | None]:
    """(先に並べる側, 後に並べる側, 採る側)。"""
    oa, ob = origin_of(a), origin_of(b)
    if oa in SOFT_ORIGINS and ob in FACT_ORIGINS:
        return b, a, b
    if ob in SOFT_ORIGINS and oa in FACT_ORIGINS:
        return a, b, a
    if oa in SOFT_ORIGINS and ob in SOFT_ORIGINS and not (oa == ob == "document"):
        return a, b, None       # 文書とテスト・テストどうしは優先を付けず両方を並べる
    if oa == "document" and ob == "document":
        ta, tb = _checked_tier(tier_of, a), _checked_tier(tier_of, b)
        if ta is not None and tb is not None and ta != tb:
            return (a, b, a) if ta < tb else (b, a, b)
        return a, b, None
    return (a, b, None) if oa == "code" else (b, a, None)


def _comparable(a: Statement, b: Statement) -> bool:
    oa, ob = origin_of(a), origin_of(b)
    return oa != ob or oa == "document"   # 同じ出所のテストどうしの食い違いは testdocs 側で扱う（DD-055）


def _validate(statements: list[Statement]) -> None:
    if not isinstance(statements, (list, tuple)):
        raise TypeError("statements は Statement の list で渡す")
    bad = [type(s).__name__ for s in statements if not isinstance(s, Statement)]
    if bad:
        raise TypeError(f"Statement 以外が含まれる: {', '.join(sorted(set(bad)))}")


def _classify(statements: list[Statement]) -> tuple[list[tuple[Statement, Claim]], list[tuple[Statement, str]]]:
    claims: list[tuple[Statement, Claim]] = []
    skipped: list[tuple[Statement, str]] = []
    for st in statements:
        if origin_of(st) not in TARGET_ORIGINS:
            skipped.append((st, f"出所が突き合わせの対象外（{origin_of(st)}）"))
            continue
        claim = extract(st)
        if claim is None:
            skipped.append((st, "主題か値を抜けない"))
        else:
            claims.append((st, claim))
    return claims, skipped


def analyze(statements: list[Statement], *, tier_of: TierOf = _no_tier) -> Detection:
    """食い違いと対象外の記述（理由つき）を返す。入力の Statement は変更しない。"""
    _validate(statements)
    claims, skipped = _classify(statements)
    conflicts: list[Conflict] = []
    for i, (sa, ca) in enumerate(claims):
        for sb, cb in claims[i + 1:]:
            if ca.key != cb.key or ca.value == cb.value or not _comparable(sa, sb):
                continue
            first, second, adopted = _order(sa, sb, tier_of)
            fv, sv = (ca.display, cb.display) if first is sa else (cb.display, ca.display)
            conflicts.append(Conflict(ca.subject, ca.kind, first, second, fv, sv, adopted))
    return Detection(tuple(conflicts), tuple(skipped))


def detect(statements: list[Statement], *, tier_of: TierOf = _no_tier) -> list[Conflict]:
    """食い違いの一覧。対象外の件数が要るときは analyze() を使う。"""
    return list(analyze(statements, tier_of=tier_of).conflicts)


def _side(st: Statement, value: str) -> str:
    origin = origin_of(st)
    label = ORIGIN_LABEL.get(origin, origin)
    refs = "、".join(ev.label() for ev in st.evidence) or "根拠なし"
    return f"{label}「{st.text}」＝{value}（確度: {st.confidence}、根拠: {refs}）"


def to_questions(conflicts: list[Conflict], *, start: int = 1) -> list[Question]:
    """食い違い 1 件を台帳の 1 件にする。双方の根拠を並べる。ID は Q-NNN（start から連番）。"""
    if start < 1:
        raise ValueError("start は 1 以上")
    questions: list[Question] = []
    for n, c in enumerate(conflicts, start=start):
        text = (f"「{c.subject}」の{c.kind}が入力の間で食い違う。どちらが正しいか。"
                f" {_side(c.first, c.first_value)} ／ {_side(c.second, c.second_value)}")
        choices = (f"{c.first_value}（{ORIGIN_LABEL.get(origin_of(c.first), origin_of(c.first))}）",
                   f"{c.second_value}（{ORIGIN_LABEL.get(origin_of(c.second), origin_of(c.second))}）")
        questions.append(Question(id=f"Q-{n:03d}", text=text, related_ids=(), choices=choices))
    return questions


def resolve_view(conflict: Conflict) -> tuple[Statement, Statement | None]:
    """(生成物に載せる記述, 並記する記述)。下位 Tier の文書は載せない（台帳にだけ残す）。"""
    adopted = conflict.adopted
    if adopted is None:
        return conflict.first, conflict.second
    other = conflict.second if adopted is conflict.first else conflict.first
    if origin_of(adopted) == "document" and origin_of(other) == "document":
        return adopted, None
    return adopted, other
