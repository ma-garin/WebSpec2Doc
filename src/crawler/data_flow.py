"""画面間データ依存の追跡（Black Widow, S&P 2021 の inter-state dependency）。

「ある画面で入力した値が、別の画面のテキストに反映されているか」を観測する。
検索語・登録名などがどの画面へ伝播したかを可視化し、本システムに欠けていた
「入力→反映」の依存関係を補う。

**送信を伴わない範囲**で行う。第3弾の実測バリデーションが入力した値（安全な
合成値）をマーカーとし、後続クロール画面のテキストへの出現を突合するだけ。

主張境界: 観測できた反映のみ。全依存の網羅は主張しない
（クロールで踏まなかった画面・非同期反映は観測できないため）。
"""

from __future__ import annotations

from typing import Any

CLAIM_SCOPE = "observed_reflection_only"

CLAIM_NOTICE = (
    "本結果はクロール中に観測できた値の反映のみの記録であり、"
    "画面間データ依存の網羅を主張するものではない。"
)

# 反映として扱う最小の値の長さ（短すぎる値は偶然の一致が多いため除外）
MIN_MARKER_LENGTH = 3


def track_reflections(report: dict[str, Any]) -> dict[str, Any]:
    """入力値マーカーの他画面への反映を追跡する。

    各画面の validation_observations（実測入力値）をマーカーとして集め、
    別画面の title/headings/buttons テキストへの出現を検出する。
    """
    screens = [s for s in report.get("screens", []) if isinstance(s, dict)]
    markers = _collect_markers(screens)
    texts_by_page = {str(s.get("page_id", "")): _page_text(s) for s in screens}

    flows: list[dict[str, Any]] = []
    for marker in markers:
        value = marker["value"]
        source = marker["source_page"]
        sink_pages = [
            page_id
            for page_id, text in sorted(texts_by_page.items())
            if page_id and page_id != source and value in text
        ]
        if sink_pages:
            flows.append(
                {
                    "value": value,
                    "field_name": marker["field_name"],
                    "source_page": source,
                    "sink_pages": sink_pages,
                }
            )

    return {
        "meta": {"claim_scope": CLAIM_SCOPE, "claim_notice": CLAIM_NOTICE},
        "flows": flows,
        "summary": {"flows": len(flows)},
    }


def _collect_markers(screens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """各画面の実測入力値（送信していない合成値）をマーカーとして集める。"""
    markers: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for screen in screens:
        page_id = str(screen.get("page_id", ""))
        for observation in screen.get("validation_observations", []):
            if not isinstance(observation, dict):
                continue
            value = str(observation.get("attempted_value") or observation.get("value") or "")
            field_name = str(observation.get("field_name", ""))
            if len(value) < MIN_MARKER_LENGTH:
                continue
            key = (page_id, value)
            if key in seen:
                continue
            seen.add(key)
            markers.append({"value": value, "field_name": field_name, "source_page": page_id})
    return markers


def _page_text(screen: dict[str, Any]) -> str:
    parts: list[str] = [str(screen.get("title", ""))]
    parts.extend(str(h) for h in screen.get("headings", []))
    parts.extend(str(b) for b in screen.get("buttons", []))
    return " ".join(parts)
