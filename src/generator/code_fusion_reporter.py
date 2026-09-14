"""Code Fusion（ソースコード×実測突合）結果の出力。

code_fusion.json（機械可読）と code_fusion.md（人が読む作業リスト）を出力する。
主役は「未到達ルート一覧」であり、QA がそのままテスト対象の作業リストとして
使えるよう、Markdown では未到達ルートを最上位の節に置く。

主張境界: ここで扱うのは**ソースに定義が存在する**という事実と、
**今回のクロールで踏んだ**という事実の突合だけである。
未到達は欠陥ではなく調査対象であり、到達率を品質指標として扱わない。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from ingest.code_models import (
    CLAIM_NOTICE,
    KIND_API,
    CodeBundle,
    CodeRoute,
    code_route_to_dict,
)
from ingest.route_matcher import effective_path

if TYPE_CHECKING:  # pragma: no cover - 型参照のみ
    from ingest.route_matcher import CodeFusionResult

logger = logging.getLogger(__name__)

CODE_FUSION_JSON_NAME = "code_fusion.json"
CODE_FUSION_MD_NAME = "code_fusion.md"
_JSON_INDENT = 2
#: 「対応が取れたルート」表に載せる最大件数（超過分は件数のみ示す）
_MATCH_TABLE_LIMIT = 50
_EMPTY_CELL = "-"


def _cell(value: object) -> str:
    """Markdown 表のセル用に値を整形する（空なら "-"、"|" はエスケープ）。"""
    text = "" if value is None else str(value).strip()
    if not text:
        return _EMPTY_CELL
    return text.replace("|", "\\|")


def _evidence_location(route: CodeRoute) -> str:
    """ルート定義箇所を "file:line" 形式で返す（無ければ空文字）。"""
    evidence = getattr(route, "evidence", None)
    if evidence is None:
        return ""
    return f"{evidence.file}:{evidence.line}"


def _methods_text(route: CodeRoute) -> str:
    """HTTP メソッドをカンマ区切りの文字列にする。"""
    return ", ".join(route.methods or ())


def _api_route_total(bundle: CodeBundle) -> int:
    """バンドル内の API 種別ルート件数を数える。"""
    return sum(1 for route in bundle.routes if route.kind == KIND_API)


def _claim_notice(result: "CodeFusionResult") -> str:
    """突合結果の主張境界注記を取り出す（未設定なら既定文言）。"""
    return str(getattr(result, "claim_notice", "") or CLAIM_NOTICE)


def build_code_fusion_payload(
    result: "CodeFusionResult", bundle: CodeBundle
) -> dict[str, object]:
    """突合結果を JSON シリアライズ可能な dict に変換する。"""
    matches = tuple(result.matches or ())
    unreached = tuple(result.unreached or ())
    crawl_only = list(result.crawl_only_page_ids or ())
    return {
        "claim_scope": "defined_routes_vs_crawled_only",
        "claim_notice": _claim_notice(result),
        "root": bundle.root,
        "frameworks": list(bundle.frameworks or ()),
        "summary": {
            "page_route_total": result.page_route_total,
            "api_route_total": _api_route_total(bundle),
            "matched": len(matches),
            "unreached": len(unreached),
            "crawl_only": len(crawl_only),
            "reached_ratio": result.reached_ratio,
        },
        "unreached": [
            {
                "route": code_route_to_dict(item.route),
                "reason": item.reason,
                "hint": getattr(item, "hint", "") or "",
            }
            for item in unreached
        ],
        "matches": [
            {
                "route": code_route_to_dict(item.route),
                "page_id": item.page_id,
                "page_url": item.page_url,
                "match_method": item.method,
            }
            for item in matches
        ],
        "crawl_only_page_ids": crawl_only,
        "source_files": list(bundle.source_files or ()),
        "skipped": list(bundle.skipped or ()),
    }


def _render_summary(result: "CodeFusionResult", bundle: CodeBundle) -> list[str]:
    """サマリー節（表 1 個）を組み立てる。"""
    frameworks = ", ".join(bundle.frameworks or ()) or _EMPTY_CELL
    ratio = f"{result.reached_ratio:.1%}"
    rows = [
        ("走査ルート", _cell(bundle.root)),
        ("検出フレームワーク", _cell(frameworks)),
        (
            "ルート定義数",
            _cell(
                f"画面 {result.page_route_total} 件 / API {_api_route_total(bundle)} 件"
            ),
        ),
        ("実測と対応", _cell(f"{len(tuple(result.matches or ()))} 件")),
        ("未到達", _cell(f"{len(tuple(result.unreached or ()))} 件")),
        ("実測のみ", _cell(f"{len(tuple(result.crawl_only_page_ids or ()))} 件")),
        ("到達率", _cell(f"{ratio}（今回踏んだ範囲の事実。品質指標ではない）")),
    ]
    lines = ["## サマリー", "", "| 項目 | 値 |", "|---|---|"]
    lines += [f"| {label} | {value} |" for label, value in rows]
    lines.append("")
    return lines


def _render_unreached_table(items: Iterable[Any]) -> list[str]:
    """未到達ルートの表本体を組み立てる。"""
    lines = [
        "| ルート | メソッド | 判定 | 次の手 | 定義箇所 |",
        "|---|---|---|---|---|",
    ]
    for item in items:
        route = item.route
        lines.append(
            f"| {_cell(effective_path(route))} "
            f"| {_cell(_methods_text(route))} "
            f"| {_cell(item.reason)} "
            f"| {_cell(getattr(item, 'hint', ''))} "
            f"| {_cell(_evidence_location(route))} |"
        )
    lines.append("")
    return lines


def _render_unreached(result: "CodeFusionResult") -> list[str]:
    """未到達ルート節（作業リスト本体）を組み立てる。"""
    unreached = tuple(result.unreached or ())
    lines = ["## 未到達ルート", ""]
    if not unreached:
        lines += ["すべてのルートに実測が対応している。", ""]
        return lines
    lines += [
        "今回のクロールで踏めなかったルート。未実装と断定せず、",
        "テスト未実施箇所の候補としてここから確認する。",
        "",
    ]
    page_items = [i for i in unreached if i.route.kind != KIND_API]
    api_items = [i for i in unreached if i.route.kind == KIND_API]
    if page_items:
        lines += _render_unreached_table(page_items)
    else:
        lines += ["画面ルートの未到達は無い。", ""]
    if api_items:
        lines += ["### API エンドポイント（画面遷移の対象外）", ""]
        lines += _render_unreached_table(api_items)
    return lines


def _render_crawl_only(result: "CodeFusionResult") -> list[str]:
    """実測のみの画面節を組み立てる。"""
    page_ids = tuple(result.crawl_only_page_ids or ())
    lines = ["## 実測にあるがソースに定義が無い画面", ""]
    if not page_ids:
        lines += ["実測のみの画面は無い。", ""]
        return lines
    lines += [f"- {page_id}" for page_id in page_ids]
    lines += [
        "",
        "外部サイト・動的生成・未対応フレームワークの可能性がある。走査対象の漏れを先に疑う。",
        "",
    ]
    return lines


def _render_matches(result: "CodeFusionResult") -> list[str]:
    """対応が取れたルート節を組み立てる。"""
    matches = tuple(result.matches or ())
    lines = ["## 対応が取れたルート", ""]
    if not matches:
        lines += ["実測と対応づいたルートは無い。", ""]
        return lines
    lines += [
        "定義箇所は同一パスの候補のうち先着 1 件であり、"
        "実際に配線された定義である保証は無い。",
        "同一パスが複数箇所で定義されている場合は"
        "「未到達ルート」節の重複定義も併せて確認する。",
        "",
    ]
    lines += [
        "| ルート | 実測URL | 一致方法 | 定義箇所 |",
        "|---|---|---|---|",
    ]
    for item in matches[:_MATCH_TABLE_LIMIT]:
        route = item.route
        lines.append(
            f"| {_cell(effective_path(route))} "
            f"| {_cell(item.page_url)} "
            f"| {_cell(item.method)} "
            f"| {_cell(_evidence_location(route))} |"
        )
    lines.append("")
    if len(matches) > _MATCH_TABLE_LIMIT:
        lines += [f"他 {len(matches) - _MATCH_TABLE_LIMIT} 件", ""]
    return lines


def build_code_fusion_markdown(result: "CodeFusionResult", bundle: CodeBundle) -> str:
    """突合結果を人が読む Markdown レポートに変換する。"""
    lines: list[str] = [
        "# ソースコード × 実測 突合レポート",
        "",
        f"> {_claim_notice(result)}",
        "> 到達率はクロールが踏んだ範囲を示す事実であり、"
        "カバレッジ率を品質指標として掲げない。",
        "",
    ]
    lines += _render_summary(result, bundle)
    lines += _render_unreached(result)
    lines += _render_crawl_only(result)
    lines += _render_matches(result)
    skipped = tuple(bundle.skipped or ())
    if skipped:
        lines += [
            "## 走査できなかった箇所",
            "",
            "この一覧は網羅ではない。下記は走査できず、ルート一覧に含まれていない。",
            "",
        ]
        lines += [f"- {item}" for item in skipped]
        lines.append("")
    return "\n".join(lines)


def save_code_fusion_outputs(
    result: "CodeFusionResult", bundle: CodeBundle, output_dir: Path
) -> None:
    """code_fusion.md / code_fusion.json を output_dir に出力する。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_code_fusion_payload(result, bundle)
    (output_dir / CODE_FUSION_JSON_NAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=_JSON_INDENT), encoding="utf-8"
    )
    (output_dir / CODE_FUSION_MD_NAME).write_text(
        build_code_fusion_markdown(result, bundle), encoding="utf-8"
    )
    logger.info(
        "code_fusion 出力: %s（未到達 %d 件 / 対応 %d 件）",
        output_dir,
        len(tuple(result.unreached or ())),
        len(tuple(result.matches or ())),
    )
