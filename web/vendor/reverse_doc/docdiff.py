"""前の版との差分（REQ-F-041）。再生成した要求仕様書と前の版を比べ、追加・削除・変更を区別して出す。

仕様 ID は再生成でずれるため ID だけでは突き合わせない。対応付けの決まり:
  (1) 根拠のファイルと関数（画面は URL と要素）が重なり、文の正規化後が一致 → 変更なし
      （行だけ動いていれば「根拠の位置だけ」、確度だけ違えば「確度」）
  (2) 根拠が重なり、文が違う → 変更（種類は「文言」）
  (3) どちらにも当たらない → 追加／削除
LLM は使わない。入力は変更しない。
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass

from .models import Evidence, Statement, UsdmDocument

KIND_REQ = "要求"
KIND_SPEC = "仕様"
CHANGE_TEXT = "文言"
CHANGE_MOVED = "根拠の位置だけ"
CHANGE_CONF = "確度"

_DEF_RE = re.compile(r"^\s*(?:async\s+)?(?:def|function)\s+(\w+)", re.MULTILINE)
_MIN_SIMILARITY = 0.4      # 関数が分からない根拠（ファイル単位）で文言違いを同じ仕様とみなす下限


@dataclass(frozen=True)
class DiffItem:
    kind: str                 # 要求 / 仕様
    id: str                   # 追加・変更は新しい版の ID、削除は前の版の ID
    old_id: str
    old_text: str
    new_text: str
    old_evidence: str
    new_evidence: str
    change: str = ""          # 変更の種類（文言 / 根拠の位置だけ / 確度）。追加・削除は空
    old_confidence: str = ""
    new_confidence: str = ""


@dataclass(frozen=True)
class DocDiff:
    added: tuple[DiffItem, ...]
    removed: tuple[DiffItem, ...]
    changed: tuple[DiffItem, ...]      # 文言・確度の変更（振る舞いが変わりうるもの）
    moved: tuple[DiffItem, ...]        # 根拠の位置だけ動いたもの（変更に数えない）
    unchanged: int = 0


@dataclass(frozen=True)
class _Entry:
    kind: str
    id: str
    stmt: Statement
    norm: str
    keys: frozenset[tuple[str, str]]
    lines: tuple[tuple[str, int, int], ...]


def normalize_text(text: str) -> str:
    """比較用の正規化（全半角・空白・末尾の句点を吸収）。"""
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r"\s+", " ", t).strip()
    return t.rstrip("。.").strip()


def _anchor(ev: Evidence) -> str:
    """根拠の関数名（def 行が snippet にあるとき）。画面（URL）は要素＝snippet 先頭行。"""
    if ev.file.startswith(("/", "http://", "https://")):
        return normalize_text(ev.snippet.splitlines()[0]) if ev.snippet.strip() else ""
    m = _DEF_RE.search(ev.snippet)
    return m.group(1) if m else ""


def _keys(item_id: str, evidence: tuple[Evidence, ...]) -> frozenset[tuple[str, str]]:
    if not evidence:
        return frozenset({("", "#" + item_id)})     # 根拠が無いものは ID で対応付ける
    return frozenset((e.file, _anchor(e)) for e in evidence)


def _entries(doc: UsdmDocument) -> list[_Entry]:
    if not isinstance(doc, UsdmDocument):
        raise TypeError("UsdmDocument を渡してください")
    out: list[_Entry] = []
    for r in doc.requirements:
        pairs = [(KIND_REQ, r.id, r.requirement)] + [(KIND_SPEC, s.id, s.statement) for s in r.specs]
        for kind, i, st in pairs:
            out.append(_Entry(kind, i, st, normalize_text(st.text), _keys(i, st.evidence),
                              tuple((e.file, e.line_start, e.line_end) for e in st.evidence)))
    return out


def _evidence_label(e: _Entry) -> str:
    return " / ".join(ev.label() for ev in e.stmt.evidence) or "（根拠なし）"


def _anchored(a: _Entry, b: _Entry) -> bool:
    return any(k[1] for k in a.keys & b.keys)


def _item(old: _Entry | None, new: _Entry | None, change: str = "") -> DiffItem:
    ref = new or old
    assert ref is not None
    return DiffItem(
        kind=ref.kind, id=ref.id, old_id=old.id if old else "",
        old_text=old.stmt.text if old else "", new_text=new.stmt.text if new else "",
        old_evidence=_evidence_label(old) if old else "", new_evidence=_evidence_label(new) if new else "",
        change=change,
        old_confidence=old.stmt.confidence if old else "", new_confidence=new.stmt.confidence if new else "")


def _pair_same_text(old: list[_Entry], new: list[_Entry]) -> list[tuple[_Entry, _Entry]]:
    """手順 (1): 根拠が重なり、正規化後の文が同じもの。位置・確度・ID まで同じものを優先して対にする。"""
    pairs: list[tuple[_Entry, _Entry]] = []
    used: set[int] = set()
    for o in old:
        cands = [(i, n) for i, n in enumerate(new)
                 if i not in used and n.kind == o.kind and n.norm == o.norm and (n.keys & o.keys)]
        if not cands:
            continue
        i, n = max(cands, key=lambda c: (c[1].lines == o.lines, c[1].stmt.confidence == o.stmt.confidence,
                                         c[1].id == o.id))
        used.add(i)
        pairs.append((o, n))
    return pairs


def _pair_changed(old: list[_Entry], new: list[_Entry]) -> list[tuple[_Entry, _Entry]]:
    """手順 (2): 根拠が重なり、文が違うもの。似ている順に 1 対 1 で対にする。"""
    cands: list[tuple[float, int, int]] = []
    for oi, o in enumerate(old):
        for ni, n in enumerate(new):
            if n.kind != o.kind or not (n.keys & o.keys):
                continue
            ratio = difflib.SequenceMatcher(None, o.norm, n.norm).ratio()
            if _anchored(o, n) or ratio >= _MIN_SIMILARITY:
                cands.append((ratio, oi, ni))
    cands.sort(key=lambda c: (-c[0], c[1], c[2]))
    used_o: set[int] = set()
    used_n: set[int] = set()
    pairs: list[tuple[_Entry, _Entry]] = []
    for _, oi, ni in cands:
        if oi in used_o or ni in used_n:
            continue
        used_o.add(oi)
        used_n.add(ni)
        pairs.append((old[oi], new[ni]))
    return pairs


def _classify_same_text(o: _Entry, n: _Entry) -> str:
    if o.stmt.confidence != n.stmt.confidence:
        return CHANGE_CONF
    if sorted(o.lines) != sorted(n.lines):
        return CHANGE_MOVED
    return ""


def diff_documents(old: UsdmDocument, new: UsdmDocument) -> DocDiff:
    """前の版（old）と再生成した版（new）の差分。要求と仕様を対象にする。"""
    old_e, new_e = _entries(old), _entries(new)
    changed: list[DiffItem] = []
    moved: list[DiffItem] = []
    unchanged = 0

    same = _pair_same_text(old_e, new_e)
    gone_o = {id(o) for o, _ in same}
    gone_n = {id(n) for _, n in same}
    for o, n in same:
        kind = _classify_same_text(o, n)
        if kind == CHANGE_MOVED:
            moved.append(_item(o, n, kind))
        elif kind:
            changed.append(_item(o, n, kind))
        else:
            unchanged += 1

    old_rest = [e for e in old_e if id(e) not in gone_o]
    new_rest = [e for e in new_e if id(e) not in gone_n]
    edits = _pair_changed(old_rest, new_rest)
    for o, n in edits:
        changed.append(_item(o, n, CHANGE_TEXT))
    seen_o = {id(o) for o, _ in edits}
    seen_n = {id(n) for _, n in edits}
    removed = tuple(_item(e, None) for e in old_rest if id(e) not in seen_o)
    added = tuple(_item(None, e) for e in new_rest if id(e) not in seen_n)
    return DocDiff(added=added, removed=removed, changed=tuple(changed), moved=tuple(moved), unchanged=unchanged)


def summary(diff: DocDiff) -> dict[str, int]:
    """区分ごとの件数。「根拠の位置だけ」は「変更」に数えない。"""
    return {"追加": len(diff.added), "削除": len(diff.removed), "変更": len(diff.changed),
            "根拠の位置だけ": len(diff.moved), "変更なし": diff.unchanged}


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip() or "—"


def _table(title: str, items: tuple[DiffItem, ...], header: tuple[str, ...], row) -> list[str]:
    lines = [f"## {title}（{len(items)} 件）", ""]
    if not items:
        return lines + ["なし", ""]
    lines += ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(_cell(c) for c in row(i)) + " |" for i in items]
    return lines + [""]


def render_markdown(diff: DocDiff) -> str:
    """冒頭に件数、続けて 追加／削除／変更／根拠の位置だけ の表。"""
    if not isinstance(diff, DocDiff):
        raise TypeError("DocDiff を渡してください")
    s = summary(diff)
    out = ["# 前の版との差分", "",
           "追加 {追加} 件 / 削除 {削除} 件 / 変更 {変更} 件 / 根拠の位置だけ {根拠の位置だけ} 件 / 変更なし {変更なし} 件".format(**s), ""]
    out += _table("追加", diff.added, ("区分", "ID", "文", "根拠", "確度"),
                  lambda i: (i.kind, i.id, i.new_text, i.new_evidence, i.new_confidence))
    out += _table("削除", diff.removed, ("区分", "ID", "文", "根拠", "確度"),
                  lambda i: (i.kind, i.id, i.old_text, i.old_evidence, i.old_confidence))
    out += _table("変更", diff.changed, ("区分", "ID（旧→新）", "種類", "旧文", "新文", "旧根拠", "新根拠", "確度（旧→新）"),
                  lambda i: (i.kind, f"{i.old_id}→{i.id}", i.change, i.old_text, i.new_text, i.old_evidence,
                             i.new_evidence, f"{i.old_confidence}→{i.new_confidence}"))
    out += _table("根拠の位置だけ（振る舞いの変更ではない）", diff.moved, ("区分", "ID（旧→新）", "文", "旧根拠", "新根拠"),
                  lambda i: (i.kind, f"{i.old_id}→{i.id}", i.new_text, i.old_evidence, i.new_evidence))
    return "\n".join(out).rstrip() + "\n"


__all__ = ["DiffItem", "DocDiff", "diff_documents", "render_markdown", "summary", "normalize_text",
           "CHANGE_TEXT", "CHANGE_MOVED", "CHANGE_CONF"]
