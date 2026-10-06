"""確度の規則・曖昧語検査・根拠検査・要確認事項の起こし（DD-007）。

確度は出所（origin）と根拠（evidence）で決める（REQ-F-021-01 の付与表 = CERTAINTY_BY_ORIGIN）。優先順:
  1. 出所が answer → 事実
  2. 曖昧語を含む → 要確認（REQ-F-010-04）
  3. 根拠（evidence）が無い → 要確認
  4. 出所が document・llm・test → 推定（REQ-F-021-02: LLM の生成を事実にしない。テストケースも上限は推定。DD-057）
  5. 生成時に「要確認」と明示された記述（理由・説明が読み取れない／テスト文書の食い違い）→ 要確認のまま（出所を問わない）
  6. それ以外（code・screen で根拠あり）→ 事実
確度は CONFIDENCES の 3 値だけを取る（「意図」などは Statement が拒否する）。
origin が既定（code）のままで source が static 以外なら source から写す（llm→llm、human→answer）。
docstring・コメントの転記（「概要（docstring）」で始まる記述）は書かれた主張なので、出所が code のままでも document として扱う。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Iterator

from web.vendor.reverse_doc.models import Confidence, Evidence, Origin, Question, Requirement, Spec, Statement, UsdmDocument, replace

from web.vendor.reverse_doc.ambiguity import WORDS as AMBIGUOUS_WORDS, ambiguous_words   # 語彙と語単位の照合は ambiguity.py（REQ-F-010-04 の 12 語）
QUESTION_REASON = "どの利用者が・なぜ使いますか"
QUESTION_DESCRIPTION = "利用者にとって何をする機能ですか"
QUESTION_CONSTRAINT = "に文字数の上限や、使える文字・形式の制限はありますか（コードでは空でないことだけを確かめています）"
QUESTION_HANDLING = "利用者への見せ方を含め、この扱いで正しいですか"
QUESTION_UNREAD = "業務上どういう場合で、そのときシステムは何をしますか"
CHOICES_CONSTRAINT = ("制限なし", "上限あり（文字数を記入）", "形式の制限あり（内容を記入）")
CHOICES_HANDLING = ("この扱いで正しい", "別の扱いにする（内容を記入）")
REJECTION_GROUPS = ("<異常時>", "<入力検証>")
VALIDATION_GROUP = "<入力検証>"
SUMMARY_GROUPS = ("<データ更新>", "<データ参照>", "<処理>", "<応答>")
SUMMARY_MAX = 2
SUMMARY_TEXT_MAX = 80
SYSTEM_PREFIX = "システムは"
UNREAD_MARK = "（内容は根拠を参照）"       # usdm.UNREAD_MARK と同じ（usdm を読み込まずに判定する）
RAW_CONDITION_PREFIX = "条件 `"           # usdm.RAW_CONDITION_PREFIX と同じ
EMPTY_CHECK = re.compile(r"^`(\w+)` が空のとき")
REASON_SUFFIX = "(理由)"
DESCRIPTION_SUFFIX = "(説明)"
DEFAULT_ORIGIN: Origin = "code"
DOCSTRING_PREFIXES = ("概要（docstring）", "概要（コメント）")   # gen_detailed_design_parts が付ける docstring 転記の見出し
ORIGIN_BY_SOURCE: dict[str, Origin] = {"static": "code", "llm": "llm", "human": "answer"}
CERTAINTY_BY_ORIGIN: dict[str, Confidence] = {
    "code": "事実", "screen": "事実", "answer": "事実", "document": "推定", "llm": "推定",
    "test": "推定"}   # テストケース = 推定（REQ-F-021 の付与表。事実を返さない）
UNSURE: Confidence = "要確認"
URL_FORM = re.compile(r"^https?://[^\s/?#]+[^\s]*$")      # 画面由来の根拠: file=URL・行 0・snippet=画面要素
TEST_INPUT_DIR = "inputs/tests/"                          # テスト文書の原本の置き場所（DD-057）
TEXT_TEST_SUFFIXES = (".csv", ".md", ".txt")              # 行番号で範囲を確かめられる形式（xlsx・docx は存在だけ）
DOC_PAGE_FORM = re.compile(r"^\S.*#\d+頁$")               # 文書由来の根拠: file="文書名#3頁"・snippet 空でよい
DYNAMIC_PATH = re.compile(r"要確認[:：]\s*([^`]*)")       # 解析器が静的に決められなかったルートのパス
QUESTION_DYNAMIC_PATH = "実行時にどの URL になりますか"

StatementMapper = Callable[[str, Statement], Statement]


def origin_of(st: Statement) -> Origin:
    """出所。origin が既定のままで source が static 以外なら source から写す。docstring 転記は document。"""
    if st.origin == DEFAULT_ORIGIN and st.source != "static":
        return ORIGIN_BY_SOURCE.get(st.source, DEFAULT_ORIGIN)
    if st.origin == DEFAULT_ORIGIN and st.text.startswith(DOCSTRING_PREFIXES):
        return "document"
    return st.origin


def decide(st: Statement) -> Confidence:
    """記述 1 件の確度を出所と根拠で決める。"""
    origin = origin_of(st)
    table_value = CERTAINTY_BY_ORIGIN[origin]
    if origin == "answer":
        return table_value
    if ambiguous_words(st.text) or not st.evidence:
        return UNSURE
    if st.confidence == UNSURE:       # 生成側の「要確認」は付与表の上限（推定）で上書きしない（REQ-F-021: 食い違い・読めないケースの警告を残す）
        return UNSURE
    return table_value


def iter_statements(doc: UsdmDocument) -> Iterator[tuple[str, Statement, Requirement]]:
    """(記述 ID, Statement, 所属する要求)。ID の付け方は UsdmDocument.all_statements と同じ。"""
    for r in doc.requirements:
        yield r.id, r.requirement, r
        yield f"{r.id}{REASON_SUFFIX}", r.reason, r
        yield f"{r.id}{DESCRIPTION_SUFFIX}", r.description, r
        for s in r.specs:
            yield s.id, s.statement, r


def map_statements(doc: UsdmDocument, fn: StatementMapper) -> UsdmDocument:
    """全記述に fn(ID, Statement) を適用した新しい文書を返す。"""
    def map_req(r: Requirement) -> Requirement:
        return replace(
            r,
            requirement=fn(r.id, r.requirement),
            reason=fn(f"{r.id}{REASON_SUFFIX}", r.reason),
            description=fn(f"{r.id}{DESCRIPTION_SUFFIX}", r.description),
            specs=tuple(replace(s, statement=fn(s.id, s.statement)) for s in r.specs),
        )
    return replace(doc, requirements=tuple(map_req(r) for r in doc.requirements))


def _apply_rule(_sid: str, st: Statement) -> Statement:
    decided, origin = decide(st), origin_of(st)
    if decided == st.confidence and origin == st.origin:
        return st
    return replace(st, confidence=decided, origin=origin)


def finalize(doc: UsdmDocument) -> UsdmDocument:
    """規則を適用して新しい文書を返す（入力は変更しない）。"""
    return map_statements(doc, _apply_rule)


# ── 根拠検査（REQ-N-003） ─────────────────────────────────────────────────────

def _line_count(root: Path, rel: str, cache: dict[str, int | None]) -> int | None:
    if rel not in cache:
        path = (root / rel).resolve()
        ok = path.is_relative_to(root) and path.is_file()
        cache[rel] = len(path.read_text(encoding="utf-8", errors="replace").splitlines()) if ok else None
    return cache[rel]


def _is_screen_evidence(origin: str, ev: Evidence) -> bool:
    return origin == "screen" or ev.file.startswith(("http://", "https://"))


def _is_test_evidence(origin: str, ev: Evidence) -> bool:
    return origin == "test" or ev.file.startswith(TEST_INPUT_DIR)


def _test_evidence_problem(ev: Evidence, root: Path, cache: dict[str, int | None]) -> str | None:
    """テスト文書の根拠: `inputs/tests/<名前>`（後ろに `#位置` が付いてよい）の実在と、行の範囲（行で数えられる形式だけ）。"""
    rel = ev.file.split("#", 1)[0]
    if not rel.startswith(TEST_INPUT_DIR) or rel == TEST_INPUT_DIR:
        return f"{ev.file} がテスト文書の置き場所（{TEST_INPUT_DIR}）の下でない"
    total = _line_count(root, rel, cache)
    if total is None:
        return f"{ev.label()} のファイルが無い"
    if ev.line_start < 1 or ev.line_end < ev.line_start:
        return f"{ev.label()} の位置が不正"
    if Path(rel).suffix.lower() in TEXT_TEST_SUFFIXES and ev.line_end > total:
        return f"{ev.label()} の行が範囲外（全 {total} 行）"
    return None


def _evidence_problem(origin: str, ev: Evidence, root: Path, cache: dict[str, int | None]) -> str | None:
    """根拠 1 件の問題（無ければ None）。画面は URL と画面要素、文書は「文書名#N頁」、テストは inputs/tests/ の実在、コードはファイルと行を見る。"""
    if _is_test_evidence(origin, ev):
        return _test_evidence_problem(ev, root, cache)
    if _is_screen_evidence(origin, ev):
        if not URL_FORM.match(ev.file):
            return f"{ev.file} が URL の形でない"
        return None if ev.snippet.strip() else f"{ev.file} の画面要素が空"
    if DOC_PAGE_FORM.match(ev.file):
        return None
    total = _line_count(root, ev.file, cache)
    if total is None:
        return f"{ev.label()} のファイルが無い"
    if not 1 <= ev.line_start <= ev.line_end <= total:
        return f"{ev.label()} の行が範囲外（全 {total} 行）"
    return None


def check_evidence(doc: UsdmDocument, src_root: Path) -> list[str]:
    """「事実」で根拠が無い・根拠が実在しないものを列挙する（空なら合格）。

    根拠の形は出所で異なる: コードは「ファイルと行」、画面は「URL と画面要素」（行 0）、文書は「文書名#N頁」。
    """
    root = Path(src_root).resolve()
    cache: dict[str, int | None] = {}
    problems: list[str] = []
    for sid, st, _ in iter_statements(doc):
        if st.confidence != "事実":
            continue
        if not st.evidence:
            problems.append(f"{sid}: 根拠がない")
        problems += [f"{sid}: {p}" for ev in st.evidence
                     if (p := _evidence_problem(origin_of(st), ev, root, cache)) is not None]
    return problems


# ── 要確認事項 ───────────────────────────────────────────────────────────────

def _labels(st: Statement) -> str:
    return "、".join(ev.label() for ev in st.evidence) or "根拠なし"


def _clip(text: str) -> str:
    text = text.rstrip("。")
    return text if len(text) <= SUMMARY_TEXT_MAX else text[:SUMMARY_TEXT_MAX] + "…"


def _facts(req: Requirement) -> str:
    """要求が実際に行うこと（事実の仕様から要約）。無ければ要求文。"""
    picks = [s for s in req.specs if s.group in SUMMARY_GROUPS and s.statement.confidence == "事実"][:SUMMARY_MAX]
    if not picks:
        return _clip(req.requirement.text)
    return "、".join(_clip(s.statement.text.removeprefix(SYSTEM_PREFIX).strip()) for s in picks)


def _summary(req: Requirement) -> str:
    """質問に入れる機能の要約: 説明（docstring 等）が読めればそれ、無ければ事実の仕様から。"""
    desc = req.description
    if desc.confidence != UNSURE and desc.text.strip():
        return _clip(desc.text)
    return _facts(req)


def _question_text(sid: str, st: Statement, req: Requirement) -> str:
    context = f"（{req.id} {req.title}）"
    if sid.endswith(REASON_SUFFIX):
        return f"「{_summary(req)}」機能{context}は、{QUESTION_REASON}"
    words = ambiguous_words(st.text)
    if words:
        return f"「{st.text}」の「{words[0]}」を具体的な値・条件にすると何か{context}"
    if sid.endswith(DESCRIPTION_SUFFIX):
        return f"{req.id} {req.title} は{QUESTION_DESCRIPTION}（コードでは「{_facts(req)}」を行っています）"
    if (m := DYNAMIC_PATH.search(st.text)) is not None:
        return f"{req.id} {req.title} の URL「{m.group(1).strip()}」は{QUESTION_DYNAMIC_PATH}。根拠: {_labels(st)}"
    if not st.evidence:
        return f"「{st.text}」の根拠（ファイル・行）はどこか{context}"
    return f"「{st.text}」は正しいか{context}"


def _empty_check_field(spec: Spec) -> str | None:
    m = EMPTY_CHECK.match(spec.statement.text) if spec.group == VALIDATION_GROUP else None
    return m.group(1) if m else None


def _constraint_targets(doc: UsdmDocument) -> dict[str, list[Spec]]:
    """入力項目名 → 「空でないこと」だけを確かめている仕様（同じ要求に他の検証が無いもの）。"""
    out: dict[str, list[Spec]] = {}
    for r in doc.requirements:
        others = [s.statement.text for s in r.specs if s.group == VALIDATION_GROUP and _empty_check_field(s) is None]
        for s in r.specs:
            field = _empty_check_field(s)
            if field and not any(f"`{field}`" in t for t in others):
                out.setdefault(field, []).append(s)
    return out


def _constraint_question(field: str, specs: list[Spec]) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    where = "、".join(f"{s.id} {_labels(s.statement)}" for s in specs)
    return f"{field} {QUESTION_CONSTRAINT}。根拠: {where}", tuple(s.id for s in specs), CHOICES_CONSTRAINT


def _spec_question(spec: Spec, req: Requirement) -> tuple[str, tuple[str, ...], tuple[str, ...]] | None:
    """仕様 1 件から起こす問い（読めない条件 → 業務上の意味、拒否・例外 → 扱いの確認）。"""
    text, where = spec.statement.text, f"{spec.id} {_labels(spec.statement)}"
    if UNREAD_MARK in text or RAW_CONDITION_PREFIX in text:
        cond = re.split(r"の?とき、", text, maxsplit=1)[0].rstrip("。")
        return (f"{req.id} {req.title} で「{cond}」の場合とは、{QUESTION_UNREAD}。根拠: {where}", (spec.id,), ())
    if spec.group in REJECTION_GROUPS and _empty_check_field(spec) is None:
        return (f"{req.id} {req.title} では「{text.rstrip('。')}」としていますが、{QUESTION_HANDLING}。根拠: {where}",
                (spec.id,), CHOICES_HANDLING)
    return None


def _raw_questions(doc: UsdmDocument) -> list[tuple[str, tuple[str, ...], tuple[str, ...]]]:
    """(質問文, 関係する記述, 選択肢)。要確認の記述に加え、コード側の曖昧な点（入力の上限・拒否の扱い・読めない条件）。"""
    constraints = _constraint_targets(doc)
    first_spec = {specs[0].id: field for field, specs in constraints.items()}
    out: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []
    for r in doc.requirements:
        for sid, st in ((r.id, r.requirement), (f"{r.id}{REASON_SUFFIX}", r.reason),
                        (f"{r.id}{DESCRIPTION_SUFFIX}", r.description)):
            if st.confidence == UNSURE:
                out.append((_question_text(sid, st, r), (sid,), ()))
        for s in r.specs:
            if s.statement.confidence == UNSURE:
                out.append((_question_text(s.id, s.statement, r), (s.id,), ()))
            elif s.id in first_spec:
                out.append(_constraint_question(first_spec[s.id], constraints[first_spec[s.id]]))
            elif (q := _spec_question(s, r)) is not None:
                out.append(q)
    return out


def build_questions(doc: UsdmDocument) -> tuple[Question, ...]:
    """要確認の記述 1 件 = 質問 1 件に、コードの内容に基づく問いを足す（Q-001…。同じ文は 1 件にまとめる）。"""
    seen: dict[str, int] = {}
    merged: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []
    for text, related, choices in _raw_questions(doc):
        if text in seen:
            i = seen[text]
            merged[i] = (text, merged[i][1] + tuple(r for r in related if r not in merged[i][1]), merged[i][2])
        else:
            seen[text] = len(merged)
            merged.append((text, related, choices))
    return tuple(Question(id=f"Q-{i:03d}", text=t, related_ids=rel, choices=ch)
                 for i, (t, rel, ch) in enumerate(merged, 1))


__all__ = ["AMBIGUOUS_WORDS", "CERTAINTY_BY_ORIGIN", "QUESTION_REASON", "ambiguous_words", "decide", "origin_of", "finalize", "check_evidence",
           "build_questions", "map_statements", "iter_statements"]
