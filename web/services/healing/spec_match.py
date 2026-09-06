"""修正差分を、01 が作った画面仕様と突き合わせる。

テストが通ったことは、正しく直ったことを意味しない。
落ちたテストを黙らせる修正——ボタンを消す、文言を変える、遷移先を差し替える——
でも検証は緑になる。緑になった時点で人の目に触れなくなるのが最悪の経路で、
これは自動修正で最も起きやすい失敗でもある。

そこで「画面はこうあるはず」という独立した記録と照らす。
01 が生成した report.json の screens[] がそれにあたる。
テストとは別の出どころなので、テストを黙らせる修正では辻褄が合わない。

ここで出すのは判断ではなく、人が見るべき差異だけ。
「仕様と違う＝間違い」ではない（仕様のほうが古いこともある）。
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from web.services.healing import risk
from web.services.healing.risk import RiskSignal
from web.services.healing.types import FixProposal

#: 画面の要素を表すタグ。文言が「変わった」のか「消えた」のかは、
#: 同じ種類のタグが追加行に残っているかで見分ける。
_TAG_RE = re.compile(r"<\s*(button|a|h[1-6]|label|input|option|summary|th|td)\b", re.I)
#: 遷移先を表す属性。
_LINK_RE = re.compile(r"""(?:href|action)\s*=\s*['"]([^'"]+)['"]""")

#: 照合に使う文言の長さ。実データ（P001・304 件）では 3 文字以下に
#: 「実行」「保存」「削除」「設定」が 48 件あり、コメント 1 行の変更でも
#: high の兆候が出てしまう。短い語は捨てて、当たったものの確度を上げる。
_MIN_TEXT = 4
_MAX_TEXT = 80

#: 文言の照合をかける拡張子。画面を描くファイルに限る。
#: このリポジトリはコメントが日本語なので、.py まで対象にすると
#: コメントの書き換えが「画面の要素が消えた」として出る。
_MARKUP_SUFFIXES: frozenset[str] = frozenset(
    {
        ".html",
        ".htm",
        ".jinja",
        ".jinja2",
        ".tsx",
        ".jsx",
        ".vue",
        ".svelte",
        ".js",
        ".ts",
        ".erb",
        ".php",
        ".hbs",
        ".ejs",
    }
)
#: 1 修正案あたりに出す兆候の上限。多すぎると人が読まなくなる。
_MAX_SIGNALS = 12
_MAX_LINK_SIGNALS = 3


@dataclass(frozen=True)
class ScreenSpec:
    """1 画面ぶんの「こうあるはず」。report.json の screens[] 1 件に対応する。"""

    page_id: str
    title: str
    url: str
    headings: tuple[str, ...]
    buttons: tuple[str, ...]
    form_labels: tuple[str, ...]
    #: 遷移先は report.json では画面 ID で記録されている。
    #: diff の href と比べるため、ここでは URL に解決して持つ。
    transitions_to: tuple[str, ...]

    def texts(self) -> tuple[str, ...]:
        """照合に使う文言。重複は落とし、出現順を保つ。"""
        seen: dict[str, None] = {}
        for value in self.buttons + self.headings + self.form_labels:
            text = str(value).strip()
            if _MIN_TEXT <= len(text) <= _MAX_TEXT:
                seen.setdefault(text, None)
        return tuple(seen)


# ─────────────────────────────────────────────────────────────────────────
# 読み込み
# ─────────────────────────────────────────────────────────────────────────


def _load_report(out_dir: Path, domain: str) -> dict[str, Any] | None:
    """壊れた JSON や未生成で照合を落とさない。読めなければ None。"""
    try:
        data = json.loads((Path(out_dir) / domain / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _form_labels(screen: Mapping[str, Any]) -> tuple[str, ...]:
    """入力欄の見分けに使える文字列を集める。

    report.json の fields は label を持たないことがあるため、
    name / element_id / placeholder を順に拾う。どれもソース側に
    そのまま書かれている値なので、差分との一致に使える。
    """
    labels: list[str] = []
    for form in screen.get("forms") or []:
        if not isinstance(form, Mapping):
            continue
        for field in form.get("fields") or []:
            if not isinstance(field, Mapping):
                continue
            for key in ("label", "name", "element_id", "placeholder"):
                value = str(field.get(key) or "").strip()
                if value:
                    labels.append(value)
    return tuple(labels)


def _transition_urls(report: Mapping[str, Any], screen: Mapping[str, Any]) -> tuple[str, ...]:
    """遷移先の画面 ID を URL に解決する。"""
    by_id: dict[str, str] = {}
    for other in report.get("screens") or []:
        if isinstance(other, Mapping):
            page_id = str(other.get("page_id") or "")
            if page_id:
                by_id[page_id] = str(other.get("url") or "")
    transitions = screen.get("transitions")
    targets = transitions.get("to") if isinstance(transitions, Mapping) else None
    urls = [by_id.get(str(t), "") for t in (targets or [])]
    return tuple(u for u in urls if u)


def load_screen_spec(out_dir: Path, domain: str, page_id: str) -> ScreenSpec | None:
    """01 が作った画面仕様から 1 画面ぶんを読む。無ければ None。"""
    if not domain or not page_id:
        return None
    report = _load_report(out_dir, domain)
    if report is None:
        return None
    for screen in report.get("screens") or []:
        if not isinstance(screen, Mapping):
            continue
        if str(screen.get("page_id") or "") != page_id:
            continue
        return ScreenSpec(
            page_id=page_id,
            title=str(screen.get("title") or ""),
            url=str(screen.get("url") or ""),
            headings=tuple(str(h) for h in (screen.get("headings") or [])),
            buttons=tuple(str(b) for b in (screen.get("buttons") or [])),
            form_labels=_form_labels(screen),
            transitions_to=_transition_urls(report, screen),
        )
    return None


# ─────────────────────────────────────────────────────────────────────────
# 照合
# ─────────────────────────────────────────────────────────────────────────


def _tags(lines: Sequence[str]) -> set[str]:
    """行の集合に出てくる要素タグ名。"""
    found: set[str] = set()
    for line in lines:
        for match in _TAG_RE.finditer(line):
            found.add(match.group(1).lower())
    return found


def _links(lines: Sequence[str]) -> set[str]:
    """行の集合に出てくる遷移先。"""
    found: set[str] = set()
    for line in lines:
        for match in _LINK_RE.finditer(line):
            found.add(match.group(1))
    return found


def _same_target(link: str, url: str) -> bool:
    """href が、画面仕様の遷移先 URL と同じ先を指すか（path で比べる）。"""
    if not link or not url:
        return False
    try:
        spec_path = urlparse(url).path or "/"
    except ValueError:
        return False
    link_path = link.split("?", 1)[0].split("#", 1)[0]
    return bool(link_path) and link_path.rstrip("/") == spec_path.rstrip("/")


def _text_signals(files: Sequence[Any], spec: ScreenSpec) -> list[RiskSignal]:
    """仕様にある文言が、差分で消えていないかを見る。"""
    signals: list[RiskSignal] = []
    targets = [f for f in files if Path(f.path).suffix.lower() in _MARKUP_SUFFIXES]
    for text in spec.texts():
        for file_diff in targets:
            removed = [line for line in file_diff.removed if text in line]
            if not removed:
                continue
            if any(text in line for line in file_diff.added):
                continue  # 別の行へ移っただけ
            # 同じ種類のタグが追加行に残っていれば、消えたのではなく
            # 文言が置き換わったとみる。
            if _tags(removed) & _tags(file_diff.added):
                signals.append(
                    RiskSignal(
                        code="spec-text-changed",
                        label=f"画面仕様の「{text}」が別の文言に変わっています",
                        detail=f"{file_diff.path}（{spec.page_id} {spec.title}）",
                        severity="medium",
                    )
                )
            else:
                signals.append(
                    RiskSignal(
                        code="spec-element-removed",
                        label=f"画面仕様にある「{text}」が無くなっています",
                        detail=f"{file_diff.path}（{spec.page_id} {spec.title}）",
                        severity="high",
                    )
                )
            break  # 1 文言につき 1 件
    return signals


def _link_signals(files: Sequence[Any], spec: ScreenSpec) -> list[RiskSignal]:
    """遷移先が差し替わっていないかを見る。"""
    signals: list[RiskSignal] = []
    for file_diff in files:
        if Path(file_diff.path).suffix.lower() not in _MARKUP_SUFFIXES:
            continue
        gone = _links(file_diff.removed) - _links(file_diff.added)
        added = _links(file_diff.added) - _links(file_diff.removed)
        if not gone or not added:
            continue
        for old in sorted(gone):
            if len(signals) >= _MAX_LINK_SIGNALS:
                return signals
            new = sorted(added)[0]
            known = any(_same_target(old, url) for url in spec.transitions_to)
            detail = f"{file_diff.path}（{spec.page_id} {spec.title}）"
            if known:
                detail = f"{detail}・画面仕様に記録された遷移先です"
            signals.append(
                RiskSignal(
                    code="spec-transition-changed",
                    label=f"遷移先が変わっています（{old} → {new}）",
                    detail=detail,
                    severity="medium",
                )
            )
    return signals


def assess_spec(proposal: FixProposal, spec: ScreenSpec | None) -> tuple[RiskSignal, ...]:
    """修正差分と画面仕様の食い違いを挙げる。判断はしない。"""
    if spec is None or not proposal or not (proposal.diff or ""):
        return ()
    files = risk._parse_file_diffs(proposal.diff)
    signals = _text_signals(files, spec) + _link_signals(files, spec)
    return tuple(signals[:_MAX_SIGNALS])


def summarize(proposal: FixProposal, spec: ScreenSpec | None, signals: Sequence[RiskSignal]) -> str:
    """報告書の「画面仕様との照合」欄に出す 1 行。

    照合していないことと、照合して不一致が無かったことは別物なので、
    区別できる文言にする。
    """
    if spec is None:
        return "未照合"
    count = len(spec.texts())
    if not signals:
        return f"照合対象 {count} 件・不一致なし"
    return f"不一致 {len(signals)} 件（要確認）"
