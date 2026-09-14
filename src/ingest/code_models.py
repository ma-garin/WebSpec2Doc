"""ソースコード由来仕様の正規化モデル（Code Fusion の契約）。

文書由来（ingest/models.py の DocumentEvidence）と同じ思想で、
すべてのコード由来データは CodeEvidence（ファイル・行・引用）を持ち、
実測 evidence（SourceEvidence）と出所を区別できるようにする。

主張境界: ここで扱うのは**ソースに定義が存在するという事実**のみ。
定義があることは到達可能・実装済みを意味しないため、
未到達ルートを欠陥として断定しない（デッドコードと未到達は区別できない）。
"""

from __future__ import annotations

from dataclasses import dataclass

#: 画面遷移の対象になりうるルート種別
KIND_PAGE = "page"
#: API エンドポイント（画面として到達しないため未到達判定の母数から外す）
KIND_API = "api"

CLAIM_NOTICE = (
    "本結果はソース上のルート定義とクロール実測の突合である。"
    "定義があることは到達可能を意味せず、未到達は欠陥ではなく調査対象として扱う。"
)


@dataclass(frozen=True)
class CodeEvidence:
    """ソース上の出所（実測 evidence と対をなすコード側の根拠）。"""

    file: str  # 走査ルートからの相対パス
    line: int  # 1 始まり
    quote: str = ""


@dataclass(frozen=True)
class CodeRoute:
    """ソースに定義されたルート 1 件。

    path はフレームワーク記法のまま保持する（"/report/<run_id>" 等）。
    実測 URL との突合時に route_matcher が正規化する。
    """

    path: str
    methods: tuple[str, ...] = ("GET",)
    framework: str = ""  # "flask" / "fastapi" / "django" / "express" / "nextjs"
    handler: str = ""
    kind: str = KIND_PAGE
    prefix: str = ""  # Blueprint / APIRouter の url_prefix（解決済みなら ""）
    evidence: CodeEvidence | None = None


@dataclass(frozen=True)
class CodeBundle:
    """走査したソースツリー一式の正規化結果。"""

    root: str
    routes: tuple[CodeRoute, ...] = ()
    source_files: tuple[str, ...] = ()
    frameworks: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()  # 走査できなかったファイルと理由


def code_evidence_to_dict(evidence: CodeEvidence | None) -> dict[str, object] | None:
    """CodeEvidence を JSON シリアライズ可能な dict に変換する。"""
    if evidence is None:
        return None
    return {"file": evidence.file, "line": evidence.line, "quote": evidence.quote}


def code_route_to_dict(route: CodeRoute) -> dict[str, object]:
    """CodeRoute を JSON シリアライズ可能な dict に変換する。"""
    return {
        "path": route.path,
        "methods": list(route.methods),
        "framework": route.framework,
        "handler": route.handler,
        "kind": route.kind,
        "prefix": route.prefix,
        "evidence": code_evidence_to_dict(route.evidence),
    }
