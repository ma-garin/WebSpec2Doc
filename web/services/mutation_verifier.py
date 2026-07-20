"""AutoRun 自己検証: 生成したテストが実際に欠陥検出能力を持つかを、
実行のたびに自動で確認する（ミューテーションテスト）。

背景: 監査（2026-07-20）で、生成テストが expect(body).toBeVisible() のみで
実質的な検証を行わず、対象サイトを完全に破壊してもテストが全件PASSする
（ミューテーションスコア0%）ことが判明した。人が変異体サーバを別途立てて
初めて発覚しており、AutoRun自身にはこれを検出する機構が無かった。

ここでは「対象への一切のアクセスを発生させずに」検証する。生成済みspec.ts
の各テストの先頭に、全リクエストを合成の壊れた応答（500・空ボディ）へ
差し替える page.route を注入した「変異体版」を作り、同じアサーションを
壊れた応答に対して実行する。本来なら全滅するはずのテストが「合格」して
しまった場合、そのテストは実質的な検証をしていない（弱いテスト）と判定する。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from web.services.playwright_executor import run_playwright

MUTATION_SUBDIR = "mutation_check"
MUTANT_SPEC_NAME = "mutant.spec.ts"

# 変異体応答（対象サイトへは一切アクセスしない。完全にローカルな合成応答）。
_MUTANT_ROUTE_SNIPPET = (
    "  await page.route('**/*', (route) => route.fulfill({\n"
    "    status: 500,\n"
    "    contentType: 'text/html',\n"
    "    body: '<html><body>MUTATED_BY_AUTORUN_SELF_CHECK</body></html>',\n"
    "  }));\n"
)

_TEST_OPEN_PATTERN = re.compile(
    r"(test(?:\.skip)?\('[^']*',\s*async\s*\(\{\s*page\s*\}\)\s*=>\s*\{\n)"
)


def build_mutant_spec(spec_path: Path, mutant_path: Path) -> int:
    """spec.ts の各テストへ、変異体ルートを注入した版を書き出す。

    test.skip(...) はそもそも実行されないため素通しする。
    戻り値は注入したテスト数（= 自己検証の対象件数）。
    """
    content = spec_path.read_text(encoding="utf-8")
    injected = 0

    def _inject(match: re.Match[str]) -> str:
        nonlocal injected
        header = match.group(1)
        if ".skip(" in header:
            return header
        injected += 1
        return header + _MUTANT_ROUTE_SNIPPET

    mutated = _TEST_OPEN_PATTERN.sub(_inject, content)
    mutant_path.parent.mkdir(parents=True, exist_ok=True)
    mutant_path.write_text(mutated, encoding="utf-8")
    return injected


def run_self_check(
    spec_path: Path,
    work_dir: Path,
    per_test_timeout_sec: int = 5,
    add_log: Any = None,
) -> dict[str, Any]:
    """生成済み spec.ts の自己検証（ミューテーションテスト）を実行する。

    対象サイトへは一切アクセスしない（page.route で全リクエストをローカル応答に
    差し替えるため）。戻り値の survivors は「本来失敗すべきなのに合格した」
    テスト＝弱いテストの一覧。
    """
    mutation_dir = work_dir / MUTATION_SUBDIR
    mutant_spec = mutation_dir / MUTANT_SPEC_NAME

    injected = build_mutant_spec(spec_path, mutant_spec)
    if injected == 0:
        return {
            "ok": True,
            "applicable": False,
            "note": "実操作を持つテストが無いため、自己検証の対象がありません。",
        }

    # 変異体は対象へ一切アクセスしない（ローカルの合成応答のみ）。
    # これは従来「そうなっているはず」という**未証明の主張**だった（自己レッドチーミング #9）。
    # K1 送信ゲートウェイを block_all で動かすことで、
    #   1. 万一の送信を機構として遮断し
    #   2. 送信が 0 件であることを記録で実証する
    # 並列数を上げてよいのは、対象へ触れないことがこれで保証されるため。
    from web.services.egress_gateway import EgressPolicy

    result = run_playwright(
        mutant_spec,
        mutation_dir,
        per_test_timeout_sec=per_test_timeout_sec,
        add_log=add_log,
        workers=8,
        egress_policy=EgressPolicy(workers=8, block_all=True),
    )

    if not result.get("tests") and result.get("error"):
        return {
            "ok": False,
            "applicable": True,
            "error": result["error"],
        }

    tests = result.get("tests") or []
    survivors = [t["title"] for t in tests if t["status"] == "passed"]
    total = len(tests)
    detected = sum(1 for t in tests if t["status"] == "failed")
    score = round(100 * detected / total, 1) if total else 0.0

    egress = result.get("egress") or {}
    return {
        "ok": True,
        "applicable": True,
        "total": total,
        "detected": detected,
        "survivors": survivors,
        "survivor_count": len(survivors),
        "score": score,
        "duration_ms": result.get("duration_ms", 0),
        # 「対象へ一切アクセスしない」の実証（allowed が 0 であること）
        "egress": egress,
        "no_egress_proven": egress.get("allowed") == 0,
    }
