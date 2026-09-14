"""ソース由来ルート定義とクロール実測結果の突合（Code Fusion の中核）。

主役は**未到達ルート**である。コードにルート定義があるのに実測クロールが
一度も踏んでいない画面を洗い出し、「なぜ踏めていないか」の候補を添えて出す。

主張境界（重要）:
ここで扱えるのは「ソースに定義がある」という事実と「クロールが踏んだ／踏まなかった」
という事実だけである。未到達はデッドコードとも、権限・パラメータ不足による
クロール側の限界とも区別できないため、**欠陥として断定しない**。
reason には必ず「可能性」「疑い」の語を残す。

reached_ratio も同様に「踏んだ範囲の事実」であって品質指標ではない
（``src/apispec/coverage_map.py`` の CLAIM_SCOPE と同じ思想）。
踏んだことは検証したことを意味しないため、この割合を品質保証の指標に使わない。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from analyzer.canonicalizer import group_canonical_screens
from analyzer.html_analyzer import AnalyzedPage
from ingest.code_models import CLAIM_NOTICE, KIND_API, KIND_PAGE, CodeBundle, CodeRoute

#: 正規化後のパラメータ表現（フレームワーク記法をすべてこれに潰す）
PARAM_TOKEN = "{}"

#: 未到達の判定理由（いずれも断定を避けた文言に固定する）
REASON_API = "APIエンドポイント（画面遷移の対象外）"
REASON_AUTH = "権限により未到達の可能性"
REASON_PARAM = "パラメータ必須のため入口URLから到達できない可能性"
REASON_NO_LINK = "未到達（クロール導線なし、またはデッドコード）"
REASON_NON_GET = "GET 以外のメソッドのみのため、画面遷移では到達しない可能性"
REASON_DUPLICATE = "同一パスの別定義が既に実測と対応済み（重複定義）"

HINT_AUTH = "管理者アカウントで再クロールする"
HINT_PARAM = "具体値を含む URL をシードに追加する"
HINT_NO_LINK = "リンク元の有無を確認する。到達できなければ実装が使われていない疑い"
HINT_NON_GET = "フォーム送信後の画面かどうかを確認する"
HINT_DUPLICATE = "どちらの定義が実際に配線されているか確認する"

#: 権限で弾かれた可能性を示唆するパス片
_PRIVILEGED_SEGMENTS = ("admin", "manage")
#: 残り全部を飲み込む記法（Flask <path:>, Next.js [...slug], Express *）
_HAS_CATCH_ALL_RE = re.compile(r"<path:|\[\.\.\.|\*")

#: フレームワーク各記法のパラメータ。順序が意味を持つ（catch-all を先に見る）。
_PARAM_RE = re.compile(
    r"<(?P<flask>[^<>]*)>"  # Flask/Django: <id> <int:id> <path:sub>
    r"|\[\[?\.\.\.(?P<next_catch>[^\]]*)\]?\]"  # Next.js: [...slug] [[...slug]]
    r"|\[(?P<next>[^\]]*)\]"  # Next.js: [id]
    r"|\{(?P<brace>[^{}]*)\}"  # FastAPI/Spring: {id} {id:path} {*rest} {}
    r"|:(?P<colon>[A-Za-z_][A-Za-z0-9_]*)(?P<colon_star>\*)?"  # Express: :id :rest*
)


@dataclass(frozen=True)
class RouteMatch:
    """ソース上のルートと実測ページの対応 1 件。"""

    route: CodeRoute
    page_id: str
    page_url: str
    method: str  # "exact"（正規化パス完全一致）/ "pattern"（パラメータ展開一致）


@dataclass(frozen=True)
class UnreachedRoute:
    """ソースにあるが実測で踏めていないルートと、その理由の候補。"""

    route: CodeRoute
    reason: str  # 断定しない文言（「可能性」「疑い」を残す）
    hint: str = ""  # 利用者への次アクション 1 行


@dataclass(frozen=True)
class CodeFusionResult:
    """コード×実測の突合結果一式。

    reached_ratio は踏んだ範囲の事実であり、品質指標ではない。
    API ルートは画面遷移の対象外なので母数（page_route_total）から外す。
    """

    matches: tuple[RouteMatch, ...]
    unreached: tuple[UnreachedRoute, ...]  # コードのみ = 未到達
    crawl_only_page_ids: tuple[str, ...]  # 実測のみ = ソースに定義が見つからない
    page_route_total: int  # kind=page のルート総数（母数）
    reached_ratio: float  # kind=page の到達割合。0 除算は 0.0
    claim_notice: str = CLAIM_NOTICE


def _scan_pattern(path: str) -> list[tuple[str, object]]:
    """パスを [("lit", 文字列) | ("param", catch_all か否か)] の並びへ分解する。"""
    tokens: list[tuple[str, object]] = []
    cursor = 0
    for found in _PARAM_RE.finditer(path):
        if found.start() > cursor:
            tokens.append(("lit", path[cursor : found.start()]))
        tokens.append(("param", _is_catch_all(found)))
        cursor = found.end()
    if cursor < len(path):
        tokens.append(("lit", path[cursor:]))
    return tokens


def _is_catch_all(found: re.Match[str]) -> bool:
    """マッチしたパラメータが複数セグメントを飲み込む記法かを判定する。"""
    if found.group("next_catch") is not None:
        return True
    if found.group("colon_star"):
        return True
    flask = found.group("flask")
    if flask is not None and flask.split(":", 1)[0].strip() == "path":
        return True
    brace = found.group("brace")
    if brace is not None:
        body = brace.strip()
        if body.startswith("*"):
            return True
        if body.endswith(":path"):
            return True
    return False


def _strip_trailing_slash(path: str) -> str:
    """ルート "/" を除き、末尾スラッシュを落とす。"""
    if len(path) > 1 and path.endswith("/"):
        return path.rstrip("/") or "/"
    return path


def normalize_route_pattern(path: str) -> str:
    """フレームワーク記法のパラメータを共通表現 "{}" に潰す。

    "/r/<int:id>" "/r/<id>" "/r/:id" "/r/[id]" "/r/[...slug]" "/r/{id}" → "/r/{}"
    末尾スラッシュは（ルート "/" を除き）落として正規化する。
    """
    if not path:
        return "/"
    normalized = "".join(
        PARAM_TOKEN if kind == "param" else str(value) for kind, value in _scan_pattern(path)
    )
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    normalized = re.sub(r"/{2,}", "/", normalized)
    return _strip_trailing_slash(normalized)


def route_to_regex(path: str) -> re.Pattern[str]:
    """実効パスを URL パス突合用の正規表現にする。

    パラメータ部は 1 セグメント（``[^/]+``）、catch-all 記法は複数セグメント（``.+``）。
    末尾スラッシュの有無は吸収する。
    """
    source = _strip_trailing_slash(re.sub(r"/{2,}", "/", path or "/"))
    if not source.startswith("/"):
        source = "/" + source
    parts: list[str] = []
    for kind, value in _scan_pattern(source):
        if kind == "param":
            parts.append(".+" if value else "[^/]+")
        else:
            parts.append(re.escape(str(value)))
    return re.compile("".join(parts) + "/?")


def effective_path(route: CodeRoute) -> str:
    """prefix + path を結合した実効パス（二重スラッシュは潰す）。"""
    joined = f"{route.prefix or ''}/{route.path or ''}"
    joined = re.sub(r"/{2,}", "/", joined)
    if not joined.startswith("/"):
        joined = "/" + joined
    return _strip_trailing_slash(joined)


def _path_of(url: str) -> str:
    """URL/パスをパス部分へ正規化する。末尾スラッシュの揺れを吸収する。

    ``ingest/matcher.py`` の同名関数と同じ流儀（パス比較は case-sensitive）。
    """
    parsed = urlparse(url)
    path = parsed.path or "/"
    return _strip_trailing_slash(path)


def _reason_for(
    route: CodeRoute, pattern_reached: bool, *, exact_duplicate: bool = False
) -> tuple[str, str]:
    """未到達ルートの理由と次アクションを返す（欠陥と断定しない）。"""
    if route.kind == KIND_API:
        return REASON_API, ""
    if exact_duplicate:
        return REASON_DUPLICATE, HINT_DUPLICATE
    effective = effective_path(route).lower()
    if any(segment in effective for segment in _PRIVILEGED_SEGMENTS):
        return REASON_AUTH, HINT_AUTH
    if PARAM_TOKEN in normalize_route_pattern(effective_path(route)) and not pattern_reached:
        return REASON_PARAM, HINT_PARAM
    methods = tuple(m.upper() for m in route.methods)
    if "GET" in methods:
        return REASON_NO_LINK, HINT_NO_LINK
    return REASON_NON_GET, HINT_NON_GET


def _specificity_key(route: CodeRoute) -> tuple[int, int, int, int]:
    """パターン照合の優先順位（小さいほど優先＝より具体的なルート）。

    ソース定義順のまま照合すると、catch-all（``/<path:name>`` 等）が
    先に現れただけで具体的なルート（``/healing/reports/<report_id>``）の
    実測を横取りしてしまう。静的セグメントが多くパラメータが少ないものを先に当てる。
    """
    normalized = normalize_route_pattern(effective_path(route))
    segments = [seg for seg in normalized.split("/") if seg]
    param_count = sum(1 for seg in segments if PARAM_TOKEN in seg)
    static_count = len(segments) - param_count
    catch_all = 1 if _HAS_CATCH_ALL_RE.search(effective_path(route)) else 0
    return (catch_all, param_count, -static_count, -len(normalized))


def fuse_code(pages: list[AnalyzedPage], bundle: CodeBundle) -> CodeFusionResult:
    """実測ページ一覧とソース由来ルート一式を突合し、未到達ルートを出す。

    1. ``group_canonical_screens`` で正準画面に絞る（matcher.fuse と同じ流儀）。
    2. 正規化パスの完全一致（method="exact"）を先に取る。
    3. 残りを ``route_to_regex`` の ``fullmatch`` で照合（method="pattern"）。
       このとき catch-all が具体ルートの実測を横取りしないよう具体度順に当てる。
    4. どのルートにも当たらなかったページが crawl_only_page_ids。

    1 ページは最大 1 ルートにしか対応づけない（先着順・exact 優先）。
    これをしないと catch-all ルート（``/<view_name>`` 等）が実測済みページを吸い、
    到達率が水増しされて本来未到達のルートが「到達済み」に化ける。
    """
    canonical_info = group_canonical_screens(pages)
    canonical_pages = [page for page in pages if canonical_info[page.page_id].is_canonical]
    page_paths = [
        (page.page_id, page.page_data.url, _path_of(page.page_data.url))
        for page in canonical_pages
    ]

    matches: list[RouteMatch] = []
    matched_page_ids: set[str] = set()
    matched_routes: set[int] = set()

    # 1 周目: 正規化パスの完全一致（大文字小文字は区別する）
    for route in bundle.routes:
        normalized = normalize_route_pattern(effective_path(route))
        if PARAM_TOKEN in normalized:
            continue
        for page_id, page_url, path in page_paths:
            if page_id in matched_page_ids:
                continue
            if path == normalized:
                matches.append(
                    RouteMatch(route=route, page_id=page_id, page_url=page_url, method="exact")
                )
                matched_routes.add(id(route))
                matched_page_ids.add(page_id)
                break

    # 2 周目: パラメータ展開一致（具体的なルートから順に当てる）
    for route in sorted(bundle.routes, key=_specificity_key):
        if id(route) in matched_routes:
            continue
        regex = route_to_regex(effective_path(route))
        for page_id, page_url, path in page_paths:
            if page_id in matched_page_ids:
                continue
            if regex.fullmatch(path):
                matches.append(
                    RouteMatch(route=route, page_id=page_id, page_url=page_url, method="pattern")
                )
                matched_routes.add(id(route))
                matched_page_ids.add(page_id)
                break

    # 同一の正規化パターンを持つ仲間のうち 1 本でも実測があるか
    reached_patterns = {normalize_route_pattern(effective_path(m.route)) for m in matches}
    # 完全一致で対応が取れたパス（同一パスの重複定義を「導線なし」と誤報しないため）
    reached_exact_paths = {
        normalize_route_pattern(effective_path(m.route)) for m in matches if m.method == "exact"
    }

    unreached: list[UnreachedRoute] = []
    for route in bundle.routes:
        if id(route) in matched_routes:
            continue
        normalized = normalize_route_pattern(effective_path(route))
        pattern_reached = normalized in reached_patterns
        exact_duplicate = PARAM_TOKEN not in normalized and normalized in reached_exact_paths
        reason, hint = _reason_for(route, pattern_reached, exact_duplicate=exact_duplicate)
        unreached.append(UnreachedRoute(route=route, reason=reason, hint=hint))

    crawl_only = tuple(
        page_id for page_id, _url, _path in page_paths if page_id not in matched_page_ids
    )

    page_route_total = sum(1 for route in bundle.routes if route.kind == KIND_PAGE)
    page_matched = sum(1 for match in matches if match.route.kind == KIND_PAGE)
    reached_ratio = round(page_matched / page_route_total, 4) if page_route_total else 0.0

    return CodeFusionResult(
        matches=tuple(matches),
        unreached=tuple(unreached),
        crawl_only_page_ids=crawl_only,
        page_route_total=page_route_total,
        reached_ratio=reached_ratio,
        claim_notice=CLAIM_NOTICE,
    )
