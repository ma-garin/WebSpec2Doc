"""技術スタック・API エンドポイント情報から Mermaid アーキテクチャ図を生成する。

ベテランエンジニアが参画初日に描く「フロントエンド → API → バックエンド」層構造を
クロール結果から自動再現する。検出情報が不足している場合は推定として明示する。
"""

from __future__ import annotations

import html
from collections import Counter

from analyzer.stack_detector import StackInfo
from crawler.page_crawler import ApiEndpoint

MAX_ENDPOINT_LABELS = 8
UNKNOWN = "不明"


def generate_architecture_mermaid(
    domain: str,
    stack: StackInfo | None,
    api_endpoints: tuple[ApiEndpoint, ...],
) -> str:
    """Mermaid graph TD でシステムアーキテクチャ図を生成する。

    stack / api_endpoints が空の場合は最小構成のダイアグラムを返す。
    """
    lines: list[str] = ["graph TD"]
    lines.append('    User(["👤 ユーザー"])')

    fe_label = _frontend_label(stack)
    lines.append(f'    FE["{fe_label}"]')

    api_paths = _representative_paths(api_endpoints)
    if api_paths:
        lines.append('    subgraph APIGROUP["🔌 API エンドポイント（観測）"]')
        for path in api_paths:
            node_id = "ep_" + _safe_node_id(path)
            lines.append(f'        {node_id}["{html.escape(path)}"]')
        lines.append("    end")

    be_label = _backend_label(stack)
    lines.append(f'    BE["{be_label}"]')
    lines.append('    DB[("💾 データストア\\n（推定）")]')

    if stack and stack.css_framework != UNKNOWN:
        css_id = "UI_" + _safe_node_id(stack.css_framework)
        lines.append(f'    {css_id}[/"🎨 {html.escape(stack.css_framework)}"/]')
        lines.append(f"    FE --- {css_id}")

    lines.append('    User -->|"操作"| FE')
    if api_paths:
        ep_label = _edge_label(api_endpoints)
        lines.append(f'    FE -->|"XHR/fetch\\n{html.escape(ep_label)}"| APIGROUP')
        lines.append("    APIGROUP --> BE")
    else:
        lines.append('    FE -->|"HTTP"| BE')
    lines.append("    BE --> DB")

    lines += [
        "    classDef frontend fill:#EDF5FF,stroke:#0F62FE,color:#0043CE",
        "    classDef backend fill:#DEFBE6,stroke:#198038,color:#0e6027",
        "    classDef db fill:#FFF8E1,stroke:#F59E0B,color:#92400e",
        "    classDef user fill:#F4F4F4,stroke:#525252",
        "    class FE frontend",
        "    class BE backend",
        "    class DB db",
        "    class User user",
    ]

    return "\n".join(lines)


def merge_stack_infos(stacks: list[StackInfo]) -> StackInfo | None:
    """複数ページの StackInfo を統合して最も情報量の多い 1 つを返す。"""
    if not stacks:
        return None

    def score(s: StackInfo) -> int:
        return sum(
            1
            for v in (s.frontend_framework, s.rendering_mode, s.css_framework, s.state_management)
            if v != UNKNOWN
        ) + len(s.backend_hints)

    return max(stacks, key=score)


def merge_api_endpoints(
    all_endpoints: list[tuple[ApiEndpoint, ...]],
) -> tuple[ApiEndpoint, ...]:
    """複数ページの ApiEndpoint を統合して重複除去する。"""
    seen: dict[tuple[str, str], ApiEndpoint] = {}
    for endpoints in all_endpoints:
        for ep in endpoints:
            key = (ep.method, ep.path)
            if key not in seen:
                seen[key] = ep
    return tuple(seen.values())


def _frontend_label(stack: StackInfo | None) -> str:
    if stack is None or stack.frontend_framework == UNKNOWN:
        return "🖥 フロントエンド\\n（フレームワーク不明）"
    parts = [f"🖥 {html.escape(stack.frontend_framework)}"]
    if stack.rendering_mode != UNKNOWN:
        parts.append(f"({html.escape(stack.rendering_mode)})")
    return "\\n".join(parts)


def _backend_label(stack: StackInfo | None) -> str:
    base = "⚙ バックエンド"
    if not stack or not stack.backend_hints:
        return f"{base}\\n（推定）"
    hint = stack.backend_hints[0]
    short = hint.replace("Server: ", "").replace("X-Powered-By: ", "")[:30]
    return f"{base}\\n({html.escape(short)})"


def _representative_paths(endpoints: tuple[ApiEndpoint, ...]) -> list[str]:
    """上位 MAX_ENDPOINT_LABELS パスを頻度順で返す。"""
    counter: Counter[str] = Counter(ep.path for ep in endpoints)
    return [path for path, _ in counter.most_common(MAX_ENDPOINT_LABELS)]


def _edge_label(endpoints: tuple[ApiEndpoint, ...]) -> str:
    if not endpoints:
        return ""
    methods = sorted({ep.method for ep in endpoints})
    return f"{len(endpoints)} calls ({', '.join(methods)})"


def _safe_node_id(text: str) -> str:
    """Mermaid ノード ID として使える文字列に変換する。"""
    return "".join(c if c.isalnum() else "_" for c in text)[:24]
