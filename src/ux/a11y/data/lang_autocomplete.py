"""言語タグ（BCP47）と autocomplete 属性の語彙データ（自社同梱・実行時取得なし）。

出典と更新手順:
- 言語: IANA Language Subtag Registry（RFC 5646）のうち、頻出分だけの部分スナップショット。
  ISO 639-1 の 2 文字コードは網羅（登録簿上 deprecated のものを含む）。3 文字言語・文字種・
  地域の一部・extlang は網羅していないため、未収載は「無効」ではなく「不明」と返す
  （呼び出し側が cant_tell にする）。更新時は IANA の登録簿から集合を作り直し、
  ``REGISTRY_SNAPSHOT_DATE`` を更新する。
- autocomplete: WHATWG HTML Standard 4.10.18.7（autofill detail tokens）。
"""
from __future__ import annotations

import re

REGISTRY_SNAPSHOT_DATE = "2026-10-20"

LANG_2 = frozenset(
    "aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs ca ce ch co cr cs cu cv cy "
    "da de dv dz ee el en eo es et eu fa ff fi fj fo fr fy ga gd gl gn gu gv ha he hi ho hr ht hu "
    "hy hz ia id ie ig ii ik io is it iu ja jv ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb "
    "lg li ln lo lt lu lv mg mh mi mk ml mn mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om "
    "or os pa pi pl ps pt qu rm rn ro ru rw sa sc sd se sg si sk sl sm sn so sq sr ss st su sv sw "
    "ta te tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi vo wa wo xh yi yo za zh zu "
    "iw in ji jw mo sh".split()
)

# 頻出の 3 文字言語（部分）。ここに無い 3 文字コードは「不明」。
LANG_3 = frozenset(
    "fil haw yue cmn zho jpn kor eng fra deu spa ita por rus ara hin ben ind msa tha vie nld pol "
    "tur ukr heb ell swe nor dan fin ces hun ron bul hrv srp slk slv lit lav est cat eus glg "
    "ceb ilo war hmn mri smo ton fij lao khm mya sin nep urd pan guj mar tam tel kan mal ain".split()
)

REGIONS_2 = frozenset(
    "AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR "
    "BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ "
    "EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW "
    "GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY "
    "KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV "
    "MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY "
    "QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG "
    "TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM "
    "ZW AC CP DG EA EU EZ FX IC TA UN BU CS DD NT SU TP YD YU ZR".split()
)

SCRIPTS = frozenset(
    "latn cyrl arab hans hant hira kana jpan kore hang hebr grek deva thai beng taml telu armn "
    "geor ethi khmr laoo mymr sinh tibt mong hani brai cher zzzz zyyy zinh gujr guru knda mlym orya".split()
)

EXTLANGS = frozenset("yue cmn gan wuu hak nan arb apc arz ary ajp".split())

GRANDFATHERED = frozenset(
    "en-gb-oed i-ami i-bnn i-default i-enochian i-hak i-klingon i-lux i-mingo i-navajo i-pwn "
    "i-tao i-tay i-tsu sgn-be-fr sgn-be-nl sgn-ch-de art-lojban cel-gaulish no-bok no-nyn "
    "zh-guoyu zh-hakka zh-min zh-min-nan zh-xiang".split()
)

DEFAULT_REGISTRY = {
    "lang2": LANG_2, "lang3": LANG_3, "regions": REGIONS_2, "scripts": SCRIPTS,
    "extlangs": EXTLANGS, "grandfathered": GRANDFATHERED,
}

VALID, INVALID, UNKNOWN = "valid", "invalid", "unknown"

_ALNUM = re.compile(r"^[a-z0-9]+$")


def validate_lang(value: str, registry: dict | None = None) -> tuple[str, str]:
    """言語タグを検証する。(valid|invalid|unknown, 理由)。

    invalid は「確実に誤り」のときだけ（構文違反、または網羅済みの ISO 639-1 に無い 2 文字言語など）。
    登録簿が部分スナップショットのため確認できないものは unknown。
    registry が空・None 以外の空 dict のときは unknown（登録簿を参照できない）。
    """
    reg = DEFAULT_REGISTRY if registry is None else registry
    if not reg or not reg.get("lang2"):
        return UNKNOWN, "言語サブタグ登録簿を参照できない"
    raw = (value or "").strip().lower()
    if not raw:
        return INVALID, "空の lang"
    if raw in reg.get("grandfathered", ()):
        return VALID, "grandfathered タグ"
    parts = raw.split("-")
    if any(not p or not _ALNUM.match(p) for p in parts):
        return INVALID, "BCP47 の構文に合わない（区切りは - のみ、英数字のみ）"
    if parts[0] == "x":
        ok = len(parts) > 1 and all(1 <= len(p) <= 8 for p in parts[1:])
        return (VALID, "私用タグ") if ok else (INVALID, "私用タグの構文違反")
    lang = parts[0]
    if not lang.isalpha() or not (2 <= len(lang) <= 8) or len(lang) == 4:
        # 4 文字は将来予約。構文上は許されるが登録簿に無いので不明扱い
        if lang.isalpha() and len(lang) == 4:
            return UNKNOWN, "4 文字の言語サブタグ（予約）を確認できない"
        return INVALID, "言語サブタグの長さ・文字種が不正"
    unknown_reason = ""
    if len(lang) == 2:
        if lang not in reg["lang2"]:
            return INVALID, f"言語サブタグ {lang!r} は登録簿に無い"
    elif len(lang) == 3:
        if lang not in reg["lang3"] and not ("qaa" <= lang <= "qtz"):
            unknown_reason = f"3 文字言語 {lang!r} を同梱スナップショットで確認できない"
    else:
        unknown_reason = f"{lang!r} を同梱スナップショットで確認できない"
    i = 1
    # extlang（3 文字の英字）
    ext = 0
    while i < len(parts) and len(parts[i]) == 3 and parts[i].isalpha() and ext < 3:
        if parts[i] not in reg.get("extlangs", ()):
            unknown_reason = unknown_reason or f"extlang {parts[i]!r} を確認できない"
        ext += 1
        i += 1
    if i < len(parts) and len(parts[i]) == 4 and parts[i].isalpha():
        if parts[i] not in reg.get("scripts", ()):
            unknown_reason = unknown_reason or f"文字種 {parts[i]!r} を確認できない"
        i += 1
    if i < len(parts):
        p = parts[i]
        if len(p) == 2 and p.isalpha():
            if p.upper() not in reg.get("regions", ()):
                unknown_reason = unknown_reason or f"地域 {p!r} を確認できない"
            i += 1
        elif len(p) == 3 and p.isdigit():
            unknown_reason = unknown_reason or f"UN M.49 地域 {p!r} を確認できない"
            i += 1
    while i < len(parts):
        p = parts[i]
        if p == "x":
            if i + 1 >= len(parts) or any(not (1 <= len(q) <= 8) for q in parts[i + 1:]):
                return INVALID, "私用部の構文違反"
            return (UNKNOWN, unknown_reason) if unknown_reason else (VALID, "")
        if len(p) == 1:  # 拡張（singleton）
            j = i + 1
            if j >= len(parts) or not (2 <= len(parts[j]) <= 8):
                return INVALID, "拡張サブタグの構文違反"
            while j < len(parts) and 2 <= len(parts[j]) <= 8:
                j += 1
            i = j
            continue
        if (5 <= len(p) <= 8) or (len(p) == 4 and p[0].isdigit()):
            unknown_reason = unknown_reason or f"バリアント {p!r} を確認できない"
            i += 1
            continue
        return INVALID, f"サブタグ {p!r} の位置・形が不正"
    return (UNKNOWN, unknown_reason) if unknown_reason else (VALID, "")


# ------------------------------------------------------------ autocomplete
AUTOCOMPLETE_CONTACT_FIELDS = frozenset(
    "tel tel-country-code tel-national tel-area-code tel-local tel-local-prefix tel-local-suffix "
    "tel-extension email impp".split()
)
AUTOCOMPLETE_FIELDS = frozenset(
    "name honorific-prefix given-name additional-name family-name honorific-suffix nickname "
    "username new-password current-password one-time-code organization-title organization "
    "street-address address-line1 address-line2 address-line3 address-level4 address-level3 "
    "address-level2 address-level1 country country-name postal-code cc-name cc-given-name "
    "cc-additional-name cc-family-name cc-number cc-exp cc-exp-month cc-exp-year cc-csc cc-type "
    "transaction-currency transaction-amount language bday bday-day bday-month bday-year sex url "
    "photo".split()
) | AUTOCOMPLETE_CONTACT_FIELDS
AUTOCOMPLETE_ADDRESS_MODES = frozenset({"shipping", "billing"})
AUTOCOMPLETE_CONTACT_MODIFIERS = frozenset({"home", "work", "mobile", "fax", "pager"})
AUTOCOMPLETE_TOGGLES = frozenset({"on", "off"})

_WS = re.compile(r"[ \t\n\f\r]+")


def validate_autocomplete(value: str) -> tuple[bool, str]:
    """WHATWG の autofill detail tokens 構文で検証する。(有効か, 理由)。

    順序: [section-*] [shipping|billing] [home|work|mobile|fax|pager] フィールド名 [webauthn]
    contact 修飾子は tel*/email/impp のときだけ許される。on/off は単独のときだけ。
    """
    toks = [t for t in _WS.split((value or "").strip().lower()) if t]
    if not toks:
        return False, "空の autocomplete"
    if len(toks) == 1 and toks[0] in AUTOCOMPLETE_TOGGLES:
        return True, ""
    if toks[-1] == "webauthn":
        toks = toks[:-1]
        if not toks:
            return False, "webauthn だけでフィールド名がない"
    i = 0
    if toks[i].startswith("section-"):
        if len(toks[i]) <= len("section-"):
            return False, "section- の後ろが空"
        i += 1
    if i < len(toks) and toks[i] in AUTOCOMPLETE_ADDRESS_MODES:
        i += 1
    modifier = False
    if i < len(toks) and toks[i] in AUTOCOMPLETE_CONTACT_MODIFIERS:
        modifier = True
        i += 1
    rest = toks[i:]
    if len(rest) != 1:
        return False, "フィールド名がちょうど 1 つ必要（余分または不足のトークン）"
    name = rest[0]
    if name in AUTOCOMPLETE_TOGGLES:
        return False, "on/off は他のトークンと併用できない"
    if name not in AUTOCOMPLETE_FIELDS:
        return False, f"未定義のフィールド名 {name!r}"
    if modifier and name not in AUTOCOMPLETE_CONTACT_FIELDS:
        return False, "home/work 等の修飾子は連絡先フィールド（tel/email/impp）でのみ使える"
    return True, ""
