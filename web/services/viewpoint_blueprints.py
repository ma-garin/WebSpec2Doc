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

# 追加分は接尾辞付きのファイルとして置く（例: viewpoint_blueprints_web.json）。
# ファイル名を定数で列挙すると、カテゴリを1つ増やすたびに定数・ループ・docstring の
# 3箇所を直すことになる。命名規約で拾えば、ファイルを置くだけで増える。
EXTRA_SUFFIX = "_*.json"

# 優先度から観点の重み(1-5)へ。移植元は P0/P1 の2値しか持たないため、
# 存在しない粒度を作らずそのまま2値で写す。
PRIORITY_WEIGHT = {"P0": 5, "P1": 4, "P2": 3, "P3": 2}
DEFAULT_WEIGHT = 3

# 自動化区分。観点定義は automation_level に明示する。
# かつて自由文の automation から日本語の部分一致で推測していたが、
# 言い回しを変えるだけで分類が変わる。推測させず、定義に書かせる。
AUTOMATION_LEVELS = {"manual", "semi_automated", "automated"}
# この製品自身では証跡を取れない観点。リポジトリ参照など外部の手段が要る。
UNVERIFIABLE_LEVEL = "manual"


class ViewpointGeneratorError(Exception):
    """観点生成に必要なカタログが読めない・領域が存在しない。"""


def _automation_of(blueprint: dict[str, Any]) -> str:
    """観点定義が宣言した自動化区分を返す。

    未宣言や不正値はカタログの不備として扱い、黙って既定値へ倒さない。
    実際には手作業が要るものを「自動」と表示するほうが、逆より害が大きく、
    その誤りは表示を見ただけでは気づけないため。
    """
    level = str(blueprint.get("automation_level", ""))
    if level not in AUTOMATION_LEVELS:
        raise ViewpointGeneratorError(
            f"観点定義 {blueprint.get('identifier', '?')} の automation_level が不正です: "
            f"{level!r}（{sorted(AUTOMATION_LEVELS)} のいずれか）"
        )
    return level


def _load(filename: str) -> dict[str, Any]:
    path = DATA_DIR / filename
    if not path.is_file():
        raise ViewpointGeneratorError(f"観点カタログが見つかりません: {filename}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ViewpointGeneratorError(f"観点カタログの読み込みに失敗しました: {filename}") from exc


def _load_merged(base_file: str, key: str) -> dict[str, Any]:
    """基本ファイルと、同じ接頭辞を持つ追加ファイルの中身を合わせて返す。

    ファイルを分けているのは出どころを混ぜないため。観点定義なら

    - 汎用: 業務システム一般の定義（移植元は対象システムを知らない）
    - Web固有: クロールした実画面と、この製品が生成する成果物
      （画面遷移図・テスト設計・テストケース・実行結果・レポート）に対応する定義
    - 品質保証: 品質マネジメント・要求工学・検証と妥当性確認・レビュー・
      リスクマネジメントの体系。汎用分は製品品質とテスト技法に寄っており、
      「正しいものを作ったか」を問う観点を持たない
    - 品質モデル: 内部品質（静的な作り）と、要求を満たすことが満足に
      結び付くかの分類

    出どころは分けたいが、使う側は1つの束として扱いたい。ここで合わせる。
    """
    base = _load(base_file)
    merged = list(base[key])
    stem = base_file.removesuffix(".json")
    for path in sorted(DATA_DIR.glob(stem + EXTRA_SUFFIX)):
        merged += _load(path.name).get(key, [])
    return {**base, key: merged}


_CATALOG_STAMP: tuple[tuple[str, float], ...] = ()


def _catalog_stamp() -> tuple[tuple[str, float], ...]:
    """カタログJSONの更新時刻の一覧。中身が変わったかの判定に使う。"""
    return tuple(
        sorted(
            (path.name, path.stat().st_mtime)
            for path in DATA_DIR.glob("viewpoint_*.json")
            if path.is_file()
        )
    )


def reload_catalogs(*, force: bool = False) -> bool:
    """カタログJSONが変わっていればキャッシュを捨てる。捨てたら True。

    毎回無条件に捨てると、キャッシュを置いた意味が消える（開発モードでは
    リクエストのたびに101定義 × 60領域の適用判定を回すことになる）。
    更新時刻を見て、実際に編集されたときだけ捨てる。
    """
    global _CATALOG_STAMP
    stamp = _catalog_stamp()
    if not force and stamp == _CATALOG_STAMP:
        return False
    _CATALOG_STAMP = stamp
    for cached in (_blueprints, _domains_by_key, _evidence_by_id):
        cached.cache_clear()
    return True


@lru_cache(maxsize=1)
def _blueprints() -> dict[str, Any]:
    return _load_merged(BLUEPRINTS_FILE, "blueprints")


@lru_cache(maxsize=1)
def _domains_by_key() -> dict[str, dict[str, Any]]:
    return {str(d["key"]): d for d in _load(DOMAINS_FILE)["domains"]}


@lru_cache(maxsize=1)
def _evidence_by_id() -> dict[str, dict[str, Any]]:
    return {str(s["id"]): s for s in _load_merged(EVIDENCE_FILE, "sources")["sources"]}


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


def _fill(template: str, context: dict[str, Any]) -> str:
    """観点定義のプレースホルダを領域の語彙で埋める。

    観点定義は `{primary_object}` のように対象を伏せて書かれている。
    領域プロファイルの語彙（金融なら「口座・契約・取引残高」）で埋めて
    初めて、何を見るのか読める文になる。
    """
    return str(template).format(**context)


def _checks_of(
    blueprint: dict[str, Any], context: dict[str, Any], target: str, level: str
) -> str:
    """確認内容・操作・判定点を、実施手順のテキストにまとめる。

    期待結果と証跡はここに含めない。合否の判定に使う値なので、
    手順の中に埋めると機械的に取り出せず、CSV でも1セルに混ざる。
    それぞれ独立した列に持つ。
    """
    return "\n".join(
        [
            f"確認内容: {context['domain']}の「{target}」に対し、"
            f"{_fill(blueprint['condition'], context)}場合の"
            f"「{blueprint['kind']}」を{level}で確認する。",
            f"操作: {_fill(blueprint['operation'], context)}",
            f"判定点: {_fill(blueprint['point'], context)}",
            f"実施手段: {blueprint.get('automation', '')}",
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
                    "expected_result": _fill(blueprint["expected"], context),
                    "evidence": _fill(blueprint["proof"], context),
                    "technique": str(blueprint["technique"]),
                    "test_level": level,
                    # 品質領域は品質特性そのもの。分類名（テストタイプ）を
                    # 領域として流用すると、分類の文字列が内部の予約語と
                    # 衝突したときに領域が消える。値として持たせる。
                    "quality_area": str(blueprint["quality"]),
                    "risk_weight": PRIORITY_WEIGHT.get(str(blueprint["priority"]), DEFAULT_WEIGHT),
                    "automation": _automation_of(blueprint),
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
        "applied_definitions": [str(b["identifier"]) for b in applied],
        "excluded_definitions": excluded,
        # この製品はクロールしかしない。リポジトリ参照など外部の手段が要る
        # 観点は、生成しても自分では証跡を取れない。件数を隠さず数える。
        # 「観点がある」ことと「この製品で確かめられる」ことは別である。
        "unverifiable_by_product": [
            str(b["identifier"]) for b in applied if _automation_of(b) == UNVERIFIABLE_LEVEL
        ],
    }
