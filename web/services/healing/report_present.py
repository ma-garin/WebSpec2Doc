"""保守対応報告書を「顧客に出せる形」へ直す層。

保存と表示を分ける。ここで作り直したものはディスクへ書かない
（report_doc.save_report は保存形式をそのまま書く）。証跡としての
保存物を守りつつ、古い報告書でも出すときには読める形にするための層。

report_doc からのみ使う。report_doc を import しない（循環を避けるため、
報告書は属性アクセスだけで扱う）。
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from typing import Any

#: 原因の説明に載せる上限。長い説明をそのまま顧客に出さない。
CAUSE_MAX_CHARS = 200
#: 対応の説明の上限。担当者が書き足すことがあるので原因より広く取る。
ACTION_MAX_CHARS = 400
#: 件名の上限。一覧の 1 行に収める。
TITLE_MAX_CHARS = 80
#: 折りたたみに置く「AI の説明（原文）」の上限。
ORIGINAL_MAX_CHARS = 1200

#: AI が「検証していない」と書いたことを示す言い回し。和文・英文の両方。
#: これが本文に載ると、同じ報告書の検証結果と食い違って信頼を失う（実測）。
_UNVERIFIED_MARKERS_JA = (
    "未実行",
    "実行できなかった",
    "実行できませんでした",
    "承認待ち",
    "実行していません",
    "実行せず",
)
_UNVERIFIED_MARKERS_EN = (
    "unverified",
    "not run",
    "could not run",
    "couldn't run",
    "did not run",
    "denied",
    "approval gate",
    "skipped",
    "not executed",
    "pending approval",
)

#: 「未実行」が何についての話かを見分ける語。検証の話でなければ矛盾の合図にしない。
_VERIFY_CONTEXT = ("検証", "テスト", "実行", "test", "pytest", "verif")

#: 食い違いを知らせる「確認が必要な点」の見出し。重複追加の判定にも使う。
CONTRADICTION_LABEL = "AI の説明と検証結果が食い違っています"

#: 英文の自己申告を顧客向けに置き換える定型文。原文は折りたたみに残す。
FALLBACK_ACTION = "上記の原因に対する修正を適用しました。"

#: 対応が書かれていないときの定型文。画面・書き出し・API で同じ文を出すため、
#: 文言はここだけに置く（3 か所に別の文があると読み手には別の話に見える）。
UNRESOLVED_ACTION = "自動では直せませんでした。対応は担当者が記入してください。"

#: 文の切れ目。和文の句点は常に区切り、欧文の `.` は空白か終端が続くときだけ。
#: これを分けないと `demo_calc.py` の途中で本文が切れる（実測）。
_SENTENCE_END = re.compile(r"(?<=[。！？])|(?<=[.!?])(?=\s)")

#: 文の終わりとして認めてよい文字。これで終わっていなければ言い切らせる。
_TERMINATORS = "。！？.!?」』）)】〕…:："


# ─────────────────────────── 文字列を整える ───────────────────────────


def strip_markup(text: str) -> str:
    """エージェントが混ぜてくる Markdown の装飾を落とす。

    報告書は節の構造を報告書側が持つ。本文に **見出し:** やコードフェンスが
    入ると二重の構造になり、顧客に出す様式として崩れる（実測で混入した）。
    """
    body = text or ""
    body = re.sub(r"```[\s\S]*?```", " ", body)  # コードフェンスごと落とす
    # 表は報告書側が組む。1 行に潰れた表も落とす（行頭の | だけでは残る・実測）。
    kept: list[str] = []
    for line in body.splitlines():
        if line.lstrip().startswith("|"):
            continue
        table = re.search(r"\|[^|\n]*\|", line)  # `|` が 2 本以上並べば表の断片
        kept.append(line[: table.start()].rstrip() if table else line)
    body = "\n".join(kept)
    body = re.sub(r"\*\*([^*]+)\*\*", r"\1", body)  # 太字を平文へ
    body = re.sub(r"`([^`]+)`", r"\1", body)  # インラインコードを平文へ
    body = re.sub(r"^\s*[-*+]\s+", "", body, flags=re.MULTILINE)  # 箇条書きの記号
    body = re.sub(r"^#{1,6}\s*", "", body, flags=re.MULTILINE)
    return body


def close_backticks(text: str) -> str:
    """閉じていない ` の内側では切らない。開いた位置まで戻して「…」を付ける。

    保存済みの本文には、古い実装が字数で切ったせいで ` が開いたまま残っている
    ものがある（実測 1 件）。そのまま出すと語の途中で終わって読めない。
    """
    body = text or ""
    if body.count("`") % 2 == 0:
        return body.replace("`", "")
    head = body[: body.rfind("`")].rstrip(" 　、,:：-—/")
    return f"{head}…" if head else ""


def truncate_sentences(text: str, limit: int) -> str:
    """文の途中で切らずに limit 字以内へ収める。和文・英文の両方を区切る。"""
    body = " ".join(strip_markup(text).split())
    if len(body) <= limit:
        return body
    out = ""
    for sentence in _SENTENCE_END.split(body):
        if len(out) + len(sentence.strip()) > limit:
            break
        out += sentence
    if out.strip():
        return f"{out.strip()}…"  # 落とした文があることを読み手に見せる
    # 1 文が上限より長い。語の途中で切らないよう英数の切れ端を落とし、印を付ける。
    head = body[:limit]
    tail = re.search(r"[A-Za-z0-9_./:\-]+$", head)
    if tail and tail.start() > 0 and len(tail.group(0)) <= 40:
        head = head[: tail.start()]
    head = head.rstrip(" 、,")
    return f"{head}…" if head else ""


def clean_text(text: str, limit: int) -> str:
    """装飾を落とし、字数に収め、開いた ` を残さない。"""
    return close_backticks(truncate_sentences(text, limit))


def clean_block(text: str) -> str:
    """改行を残したまま装飾だけ落とす。事象のログのように行の形が意味を持つ欄用。"""
    lines = [" ".join(line.split()) for line in strip_markup(text or "").splitlines()]
    return "\n".join(line for line in lines if line).strip()


def finish_sentence(text: str) -> str:
    """言い切りで終わっていない和文に句点を足す。

    識別子や英単語で終わる文には足さない。`demo_calc.py。` の句点はパスの
    一部に見えて読み違える（実測）。終止符（`。！？…` や `.` `)` `」` `）`）で
    終わっていれば、その文はもう閉じている。
    """
    body = text or ""
    if not body or body[-1] in _TERMINATORS:
        return body
    if re.search(r"[A-Za-z0-9_]$", body):
        return body  # 識別子・英単語の直後に和文の句点を置かない
    return f"{body}。"


def is_english_heavy(text: str) -> bool:
    """英字が 6 割以上か。AI が英語で書いた自己申告を顧客向けに出さないための判定。"""
    body = re.sub(r"\s+", "", strip_markup(text or ""))
    if len(body) < 20:
        return False
    letters = sum(1 for ch in body if "a" <= ch.lower() <= "z")
    return letters >= len(body) * 0.6


#: 本文に残った表。区切り行（`|---|`）か、1 行に `|` が 2 本以上並ぶ断片。
#: 表は報告書側が組むので、本文に混ざっていれば AI が様式を壊している合図。
_TABLE_FRAGMENT = re.compile(r"\|\s*:?-{2,}|\|[^|\n]*\|")


def has_table_fragment(text: str) -> bool:
    """本文が表の断片を含むか。装飾を落とす前の保存値に対して見る。"""
    return bool(_TABLE_FRAGMENT.search(text or ""))


def looks_cut(text: str, limit: int) -> bool:
    """保存値が上限で切られたまま残っているか（言い切りで終わっていない）。

    古い実装が字数で切った保存値がある（実測）。切られた文はそのまま出せない。
    """
    body = " ".join((text or "").split())
    return len(body) >= limit and bool(body) and body[-1] not in _TERMINATORS


def claims_unverified(text: str) -> bool:
    """「検証していない」と読める文言が、検証の話として書かれているか。

    文ごとに見る。同じ文に検証・テスト・pytest・実行の語が無ければ数えない。
    別の話題の「未実行」（未実行の設定、未実行の手順など）で誤爆すると、
    正しく書かれた原文が本体の事実で置き換えられて情報が落ちる（実測）。
    """
    for sentence in _SENTENCE_END.split(text or ""):
        lowered = sentence.lower()
        hits = [m for m in _UNVERIFIED_MARKERS_JA if m in sentence]
        hits += [m for m in _UNVERIFIED_MARKERS_EN if m in lowered]
        for marker in hits:
            # 「未実行」自身が「実行」を含むので、言い回しを除いた残りで文脈を見る。
            rest = lowered.replace(marker.lower(), " ")
            if any(word in rest for word in _VERIFY_CONTEXT):
                return True
    return False


def title_from_test_id(test_id: str, message: str = "") -> str:
    """`path::TestCalc::test_add[1-2]` から件名を作る。作れなければ空。

    ID をそのまま出すと報告書がテストの実装記録に見える。関数名だけを残し、
    無理に日本語へ訳さない（訳すと毎回揺れて一覧で探せなくなる）。
    """
    parts = [x for x in (test_id or "").split("::") if x]
    if len(parts) < 2:
        return ""
    match = re.match(r"^([^\[]+)(?:\[(.+)\])?$", parts[-1].strip())
    name = (match.group(1) if match else parts[-1]).strip()
    param = (match.group(2) if match else "") or ""
    if name.startswith("test_") and len(name) > 5:
        name = name[5:]
    if not name:
        return ""
    subject = " の ".join([*parts[1:-1], name])
    title = f"{subject} のテストが失敗する"
    if param:
        title += f"（{param}）"
    cond = re.search(r"assert\s+(.+?==.+?)(?:\n|$)", message or "")
    if cond:
        extra = f"（{' '.join(cond.group(1).split())} が成り立たない）"
        if len(title) + len(extra) <= TITLE_MAX_CHARS:
            title += extra
    return title[:TITLE_MAX_CHARS]


# ─────────────────────────── 確認が必要な点 ───────────────────────────


def contradiction_note(
    text: str, after: str, after_ok: bool | None
) -> dict[str, Any] | None:
    """AI の説明と検証結果が食い違うときだけ、確認が必要な点を 1 件返す。"""
    if after_ok is not True or not claims_unverified(text):
        return None
    detail = (
        f"AI の説明は検証を「未実行」と書いていますが、修正後の検証は {after} でした。"
        "検証結果のほうが実測です。説明の原文は「該当箇所の根拠と、AI の説明」で読めます"
    )
    return {"severity": "medium", "label": CONTRADICTION_LABEL, "detail": detail}


def with_note(
    items: Sequence[Mapping[str, Any]], note: dict[str, Any] | None
) -> tuple[dict[str, Any], ...]:
    """確認が必要な点を 1 件足す。同じ見出しが既にあれば足さない。"""
    current = tuple(dict(item) for item in items)
    if note is None or any(str(x.get("label") or "") == note["label"] for x in current):
        return current
    return current + (note,)


def _clean_attention(
    items: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """見出しと説明にも装飾を残さない。ここも顧客が読む欄である。"""
    cleaned: list[dict[str, Any]] = []
    for item in items:
        row = dict(item)
        for key in ("label", "detail"):
            if row.get(key):
                row[key] = clean_text(str(row[key]), 300)
        cleaned.append(row)
    return tuple(cleaned)


# ─────────────────────────── 原因欄の作り直し ───────────────────────────


def display_location(location: str) -> str:
    """箇所の表示。行番号 0 は「差分が無い」の意味なので出さない（原因に見える）。"""
    return re.sub(r"\s*(?<![\d〜])0\s*行$", "", location or "").strip()


def cause_from_report(report: Any) -> str:
    """保存済みの報告書だけで原因を言い直す。差分は手元に無いので箇所と規模で言う。"""
    location = display_location(report.cause_location)
    if not location:
        return "原因を特定できませんでした。検証ログを確認してください。"
    stats = f"（{report.action_diff_stats}）" if report.action_diff_stats else ""
    return f"{location} の実装が期待と異なっていました{stats}。"


def action_when_empty(report: Any) -> str:
    """対応が書かれていないときの文。本体の事実（差分の有無）だけで決める。

    空欄のまま出すと、報告書として何をしたのかが読み手に分からない。作り話は
    しないので、直したかどうかだけを言う。文言は画面・書き出し・API で共通。
    """
    if (report.action_diff_stats or "").strip():
        return FALLBACK_ACTION
    return UNRESOLVED_ACTION


# ─────────────────────────── 表示用へ ───────────────────────────


def rewrite_reason(raw: str, cleaned: str, limit: int, after_ok: bool | None) -> str:
    """保存値をそのまま顧客に出せない理由。出せるなら空文字を返す。

    ここに当たらない限り、**保存されている説明をそのまま使う**。本体の事実から
    作り直した文は、書いた人が残した情報（関数名・何が誤りか・どう直したか）を
    落とすので、最後の手段として扱う（実測: 日本語の原文が 64 字の汎用文に
    格下げされ、編集欄もその汎用文で初期化されていた）。

    「検証は未実行」と書いてあること自体は理由にしない。実際に未実行なら説明は
    正しい。顧客に出せないのは、同じ報告書の検証欄が「通過」なのに本文が
    「未実行」と言っている場合（after_ok is True）だけ。この矛盾は本文から外し、
    原文を残したうえで「確認が必要な点」にも出す。
    """
    if not (raw or "").strip():
        return ""  # 書かれていない。作り話で埋めない
    if not cleaned.strip():
        return "本文が表や記号だけで、文が残りませんでした"
    if is_english_heavy(raw):
        return "英語で書かれていました"
    if after_ok is True and claims_unverified(raw):
        return "検証欄と食い違う自己申告でした"
    if has_table_fragment(raw) or raw.count("`") % 2 == 1:
        return "表の断片や閉じていない記号が混ざっていました"
    if looks_cut(raw, limit) and not cleaned.endswith("…"):
        return "文の途中で切れていました"
    return ""


def _field_text(
    raw: str,
    limit: int,
    fallback: str,
    key: str,
    extras: dict[str, str],
    after_ok: bool | None,
) -> str:
    """保存値を優先し、そのまま出せないときだけ本体の事実で言い直す。

    長さで詰めたときも原文を extras に残す。編集欄はこの原文で初期化されるので、
    人が 1 文字直して保存しても書かれていた内容が消えない。
    """
    cleaned = clean_text(raw, limit)
    original = clean_text(raw, ORIGINAL_MAX_CHARS)
    if rewrite_reason(raw, cleaned, limit, after_ok):
        extras[key] = original
        return fallback
    if original != cleaned:  # 上限で詰めた。落とした分は折りたたみに残す
        extras[key] = original
    return cleaned


def present(report: Any) -> tuple[Any, dict[str, str]]:
    """表示用の報告書と、折りたたみに置く原文を返す。保存には使わない。

    既定は「保存値をそのまま出す」。英語の自己申告・表の断片・途中で切れた文
    だけを、本体が持つ事実（箇所・差分の規模）から書き直す。外した文は捨てずに
    原文として残す。
    """
    raw_cause = report.cause_text or ""
    raw_action = report.action_text or ""
    extras: dict[str, str] = {}

    after_ok = report.verify_after_ok
    cause = _field_text(
        raw_cause,
        CAUSE_MAX_CHARS,
        cause_from_report(report),
        "cause_text_original",
        extras,
        after_ok,
    )
    action = _field_text(
        raw_action,
        ACTION_MAX_CHARS,
        FALLBACK_ACTION,
        "action_text_original",
        extras,
        after_ok,
    )
    if not action.strip():  # 書かれていない欄は本体の事実で埋める（空欄では出さない）
        action = action_when_empty(report)

    title = report.title or ""
    test_id = report.incident_test_id or ""
    if "::" in test_id and ("::" in title or test_id in title):
        title = title_from_test_id(test_id, report.incident_text) or title

    note = contradiction_note(
        f"{raw_cause}\n{raw_action}", report.verify_after, report.verify_after_ok
    )
    view = replace(
        report,
        title=clean_text(title, TITLE_MAX_CHARS),
        incident_text=clean_block(report.incident_text),
        cause_text=finish_sentence(cause),
        cause_location=display_location(report.cause_location),
        action_text=finish_sentence(action),
        verify_before=clean_text(report.verify_before, 80),
        verify_after=clean_text(report.verify_after, 80),
        spec_match=clean_text(report.spec_match, 200),
        attention=with_note(_clean_attention(report.attention), note),
    )
    return view, extras


def display_report(report: Any) -> Any:
    """顧客に出せる形へ直した報告書。Markdown の組み立てはこれを使う。"""
    return present(report)[0]


def to_view_dict(report: Any) -> dict[str, Any]:
    """画面・API・書き出しが受け取る形。保存形式ではない。"""
    view, extras = present(report)
    data = asdict(view)
    data["attention"] = [dict(a) for a in view.attention]
    data["approvals"] = [dict(a) for a in view.approvals]
    data["cause_text_original"] = extras.get("cause_text_original", "")
    data["action_text_original"] = extras.get("action_text_original", "")
    # 対応欄が保存されていない（表示文をこちらで足した）ことを画面へ渡す。
    # 編集欄をこの定型文で初期化すると、担当者が消し忘れたまま保存してしまう。
    data["action_text_generated"] = not (report.action_text or "").strip()
    return data
