"""axe-core（同梱・オフライン実行）を用いた WCAG 違反検査。

同梱ファイルは ``src/ux/assets/axe.min.js``（MPL-2.0、ASSET.md 参照）で、
CDN からの取得は一切行わない（AC-2: オフライン完結）。
検出した違反は実測（rules 層）のため confidence 1.0 固定で、
セレクタ・bbox・スクリーンショットパスを SourceEvidence として付与する。
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

from crawler.page_crawler import SourceEvidence

logger = logging.getLogger(__name__)

# axe.run が返らない場合に打ち切るまでの猶予（ミリ秒）。長時間ブロックしてクロール全体を
# 遅延させないための安全弁（このタスク固有の罠 §8）。
AXE_RUN_TIMEOUT_MS = 15_000

_ASSETS_DIR = Path(__file__).parent / "assets"
_AXE_ASSET_PATH = _ASSETS_DIR / "axe.min.js"

# ASSET.md に記載された SHA-256。資産更新時は両方を同時に更新すること。
AXE_ASSET_SHA256 = "b511cd9dec01c76f4b2ad1723b66b6db37d4c2eb4ed199076e1829d9ee7b75e3"

_INJECT_CHECK_JS = "() => typeof window.axe !== 'undefined'"
_RUN_AXE_JS = """(timeoutMs) => Promise.race([
    axe.run(document, { resultTypes: ['violations'] }),
    new Promise((_, reject) => {
        setTimeout(() => reject(new Error('axe 実行がタイムアウトしました')), timeoutMs);
    }),
])"""
_BBOX_JS = (
    "(el) => { const r = el.getBoundingClientRect();"
    " return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]; }"
)


class AxeAssetError(RuntimeError):
    """同梱 axe-core 資産が欠落・改竄されている場合の例外（AC-2, §5-4）。

    ux-review 開始前に検出し、黙って無検査で継続させないためのガード。
    """


@dataclass(frozen=True)
class AxeViolation:
    """axe-core が検出した WCAG 違反 1 件（対象ノード 1 件につき 1 レコード）。

    rule_id: axe のルール ID（例: "image-alt"）
    impact: "critical" / "serious" / "moderate" / "minor"
    description: axe 原文の説明（翻訳しない。翻訳は幻覚リスクのため §8）
    wcag_tags: 例: ("wcag2a", "wcag111")
    evidence: selector=違反ノードの target 先頭、bbox は取得できれば付与（失敗時 None）
    confidence: 実測（rules 層）のため 1.0 固定
    """

    rule_id: str
    impact: str
    description: str
    wcag_tags: tuple[str, ...]
    evidence: SourceEvidence
    help_url: str = ""
    confidence: float = 1.0


def axe_violation_to_dict(violation: AxeViolation) -> dict[str, Any]:
    """AxeViolation を JSON シリアライズ可能な dict に変換する。"""
    from crawler.page_crawler import evidence_to_dict

    return {
        "rule_id": violation.rule_id,
        "impact": violation.impact,
        "description": violation.description,
        "wcag_tags": list(violation.wcag_tags),
        "evidence": evidence_to_dict(violation.evidence),
        "help_url": violation.help_url,
        "confidence": violation.confidence,
    }


def verify_axe_asset() -> None:
    """同梱 axe.min.js の存在と SHA-256 一致を検証する。

    欠落・改竄時は AxeAssetError を送出する（黙って無検査にしない・AC-2）。
    """
    if not _AXE_ASSET_PATH.is_file():
        raise AxeAssetError(f"axe 資産が見つかりません: {_AXE_ASSET_PATH}")
    actual = hashlib.sha256(_AXE_ASSET_PATH.read_bytes()).hexdigest()
    if actual != AXE_ASSET_SHA256:
        raise AxeAssetError(
            "axe 資産が見つからないか破損しています"
            f"（SHA-256 不一致: 期待={AXE_ASSET_SHA256} 実際={actual}）"
        )


def _load_axe_source() -> str:
    """同梱 axe.min.js のソースを読み込む（encoding 明示。§8 の罠）。"""
    return _AXE_ASSET_PATH.read_text(encoding="utf-8")


def run_axe(page: Page, screenshot_path: str | None = None) -> tuple[AxeViolation, ...]:
    """axe-core を注入・実行し、violations を AxeViolation のタプルへ変換する。

    既に window.axe が存在する場合は再注入しない。
    注入・実行の失敗やタイムアウト時は空タプルを返し警告ログを出す（AC-3）。
    3-1 で対応済みの shadow DOM 対応により、axe は open shadow root も標準機能で検査する。
    """
    try:
        already_injected = bool(page.evaluate(_INJECT_CHECK_JS))
        if not already_injected:
            page.evaluate(_load_axe_source())
        result = page.evaluate(_RUN_AXE_JS, AXE_RUN_TIMEOUT_MS)
    except Exception as exc:  # noqa: BLE001 - axe 実行失敗は検査未実施として継続する
        logger.warning("axe 検査に失敗しました（未実施として継続します）: %s", exc)
        return ()

    violations_raw = result.get("violations") if isinstance(result, dict) else None
    if not isinstance(violations_raw, list):
        return ()

    collected: list[AxeViolation] = []
    for violation in violations_raw:
        if not isinstance(violation, dict):
            continue
        rule_id = str(violation.get("id") or "")
        impact = str(violation.get("impact") or "")
        description = str(violation.get("description") or "")
        help_url = str(violation.get("helpUrl") or "")
        wcag_tags = tuple(
            str(tag) for tag in (violation.get("tags") or []) if str(tag).startswith("wcag")
        )
        for node in violation.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            selector = _selector_from_target(node.get("target"))
            if not selector:
                continue
            bbox = _try_bounding_box(page, selector)
            collected.append(
                AxeViolation(
                    rule_id=rule_id,
                    impact=impact,
                    description=description,
                    wcag_tags=wcag_tags,
                    evidence=SourceEvidence(
                        selector=selector,
                        screenshot_path=screenshot_path,
                        bbox=bbox,
                    ),
                    help_url=help_url,
                )
            )
    return tuple(collected)


def _selector_from_target(target: Any) -> str:
    """violation.nodes[].target の先頭要素からセレクタ文字列を取り出す。"""
    if isinstance(target, str):
        return target
    if isinstance(target, list) and target:
        first = target[0]
        if isinstance(first, str):
            return first
        if isinstance(first, list) and first and isinstance(first[0], str):
            return first[0]
    return ""


def _try_bounding_box(page: Page, selector: str) -> tuple[int, int, int, int] | None:
    """selector の bounding box 取得を試みる。取得不能時は None（未取得と明示）。"""
    try:
        box: Any = page.eval_on_selector(selector, _BBOX_JS)
    except Exception:  # noqa: BLE001 - bbox は evidence の必須要素ではない
        return None
    if isinstance(box, list) and len(box) == 4:
        try:
            return (int(box[0]), int(box[1]), int(box[2]), int(box[3]))
        except (TypeError, ValueError):
            return None
    return None
