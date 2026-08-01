"""観点定義と領域プロファイルから、領域別の観点を生成する。

領域ごとに観点表を手書きすると、60領域 × 約43観点 = 約2,600件を人手で維持することになり、
観点定義を1つ直すたびに60箇所を直す羽目になる。移植元（kanten）は最初この形（固定直積）で
14,400件を生成し、その後に廃止している。

ここでは掛け算した表を持たず、次の2つだけを入力として持つ:

- 観点定義（blueprint）51件 ─ テスト技法・品質特性・根拠・適用レベルを持つ抽象定義。
  対象は `{primary_object}` のようなプレースホルダで書かれている。
- 領域プロファイル 60件 ─ 領域固有の語彙（主対象・主業務フロー・データ資産など）と、
  その領域が持つ能力・リスクタグ。

適用判定は「観点定義が要求する能力タグ ⊆ 領域が持つ能力タグ」。満たさない定義は
除外理由として記録し、件数合わせのために生成しない。
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from web.config import DATA_DIR

BLUEPRINTS_FILE = "viewpoint_blueprints.json"
DOMAINS_FILE = "viewpoint_domains.json"
EVIDENCE_FILE = "viewpoint_evidence.json"

# 優先度から観点の重み(1-5)へ。移植元は P0/P1 の2値しか持たないため、
# 存在しない粒度を作らずそのまま2値で写す。
PRIORITY_WEIGHT = {"P0": 5, "P1": 4, "P2": 3, "P3": 2}
DEFAULT_WEIGHT = 3


class ViewpointGeneratorError(Exception):
    """観点生成に必要なカタログが読めない・領域が存在しない。"""


def _load(filename: str) -> dict[str, Any]:
    path = DATA_DIR / filename
    if not path.is_file():
        raise ViewpointGeneratorError(f"観点カタログが見つかりません: {filename}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ViewpointGeneratorError(f"観点カタログの読み込みに失敗しました: {filename}") from exc


@lru_cache(maxsize=1)
def _blueprints() -> dict[str, Any]:
    return _load(BLUEPRINTS_FILE)


@lru_cache(maxsize=1)
def _domains_by_key() -> dict[str, dict[str, Any]]:
    return {str(d["key"]): d for d in _load(DOMAINS_FILE)["domains"]}


@lru_cache(maxsize=1)
def _evidence_by_id() -> dict[str, dict[str, Any]]:
    return {str(s["id"]): s for s in _load(EVIDENCE_FILE)["sources"]}


def _applicable(domain: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """領域に適用できる観点定義と、除外した定義IDを返す。"""
    caps = set(domain.get("capabilities", []))
    applied: list[dict[str, Any]] = []
    excluded: list[str] = []
    for blueprint in _blueprints()["blueprints"]:
        if set(blueprint["capabilities"]).issubset(caps):
            applied.append(blueprint)
        else:
            excluded.append(str(blueprint["identifier"]))
    return applied, excluded


def list_domains() -> list[dict[str, Any]]:
    """選択できる領域の一覧。件数は実際に生成される観点数と一致する。"""
    catalog = _blueprints()
    total = len(catalog["blueprints"])
    result = []
    for domain in _domains_by_key().values():
        applied, excluded = _applicable(domain)
        result.append(
            {
                "key": domain["key"],
                "name": domain["name"],
                "category": domain["category"],
                "critical_risk": domain.get("critical_risk", ""),
                "capabilities": domain.get("capabilities", []),
                "applied_definitions": len(applied),
                "excluded_definitions": len(excluded),
                "total_definitions": total,
                "item_count": sum(len(b["levels"]) for b in applied),
            }
        )
    return result


def get_domain(domain_key: str) -> dict[str, Any]:
    domain = _domains_by_key().get(domain_key)
    if domain is None:
        raise ViewpointGeneratorError(f"領域が見つかりません: {domain_key}")
    return domain


def _standards_of(blueprint: dict[str, Any]) -> str:
    """観点の根拠となる文書名。複数ある場合は先頭を代表として使う。"""
    by_id = _evidence_by_id()
    for source_id in blueprint.get("sources", []):
        source = by_id.get(str(source_id))
        if source:
            return str(source.get("document", ""))
    return ""


def _checks_of(
    blueprint: dict[str, Any], context: dict[str, Any], target: str, level: str
) -> str:
    """確認内容・操作・期待結果・証跡を1つの手順テキストにまとめる。

    観点は「何を見るか」だけでは実行できない。判定点と期待結果と、
    合否の根拠になる証跡まで揃って初めてテスト設計に使える。
    """
    fmt = lambda value: str(value).format(**context)  # noqa: E731
    return "\n".join(
        [
            f"確認内容: {context['domain']}の「{target}」に対し、"
            f"{fmt(blueprint['condition'])}場合の「{blueprint['kind']}」を{level}で確認する。",
            f"操作: {fmt(blueprint['operation'])}",
            f"判定点: {fmt(blueprint['point'])}",
            f"期待結果: {fmt(blueprint['expected'])}",
            f"証跡: {fmt(blueprint['proof'])}",
        ]
    )


def generate(domain_key: str) -> dict[str, Any]:
    """領域に対応する観点フォルダとアイテムを生成する。

    フォルダはテストタイプ（機能テスト・性能テスト等）で切る。移植元の
    分類1〜8のうち、利用者が最初に絞り込むのはテストタイプであるため。
    """
    domain = get_domain(domain_key)
    catalog = _blueprints()
    level_scope = catalog["level_scope"]
    applied, excluded = _applicable(domain)

    folders: list[str] = []
    items: list[dict[str, Any]] = []
    for blueprint in applied:
        test_type = str(blueprint["test_type"])
        if test_type not in folders:
            folders.append(test_type)
        target = str(domain[blueprint["target"]])
        for level in blueprint["levels"]:
            context = dict(domain, domain=domain["name"], level=level, level_scope=level_scope[level])
            items.append(
                {
                    "folder": test_type,
                    "name": f"{blueprint['theme']}：{blueprint['kind']}（{level}）",
                    "category": test_type,
                    "purpose": (
                        f"{blueprint['technique']}で「{blueprint['kind']}」を判定し、"
                        f"{blueprint['quality']}と{domain['critical_risk']}の未検出を防ぐため。"
                    ),
                    "recommended_checks": _checks_of(blueprint, context, target, level),
                    "risk_weight": PRIORITY_WEIGHT.get(str(blueprint["priority"]), DEFAULT_WEIGHT),
                    "automation": "semi_automated",
                    "standards": _standards_of(blueprint),
                    "tags": [
                        str(blueprint["series"]),
                        level,
                        test_type,
                        str(blueprint["quality"]),
                    ],
                }
            )

    return {
        "domain": {
            "key": domain["key"],
            "name": domain["name"],
            "category": domain["category"],
            "critical_risk": domain.get("critical_risk", ""),
        },
        "folders": folders,
        "items": items,
        "excluded_definitions": excluded,
    }
