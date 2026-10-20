#!/usr/bin/env python3
"""C. テスト観点の生成の評価。

製品が生成したテスト（output/<domain>/ta2/tests.json）を画面ごとに 10 個の標準カテゴリへ寄せ、
quality/commercial_eval/viewpoints/expected.json の required_viewpoints と照合する。
カテゴリへの寄せ方（下の CATEGORY_RULES）は評価側で定義したもので、正解データからも製品の生成規則からも作っていない。
使い方: venv/bin/python scripts/commercial_eval/viewpoints_eval.py output/<domain> [<expected.json>]
"""
from __future__ import annotations

import json
import posixpath
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import prf  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = ROOT / "quality" / "commercial_eval" / "viewpoints" / "expected.json"

# (カテゴリ, テスト技法の正規表現, テスト名の正規表現)。どちらかに当たればそのカテゴリを含むとみなす
CATEGORY_RULES = (
    ("normal", r"画面表示確認", r"正常|有効値|入力あり|ちょうど"),
    ("abnormal", r"^$", r"無効値|不正|文字種不足|超過|未満|拒否|異常"),
    ("boundary", r"境界値分析", r"上限|下限|境界|[+＋-]1|ちょうど"),
    ("required", r"^$", r"必須|未入力|空欄|空文字"),
    ("format", r"^$", r"形式|フォーマット|文字種|メール|うるう年|日付|書式"),
    ("state_transition", r"状態遷移テスト", r"状態|ステータス"),
    ("permission", r"^$", r"権限|管理者|ロール|ログインしていない|未ログイン"),
    ("error", r"^$", r"エラー|メッセージ"),
    ("api", r"^$", r"API|送信|通信|サーバ"),
    ("persistence", r"^$", r"保存|再表示|リロード|永続|再読み込み"),
)


def categories(test: dict) -> set[str]:
    tech, name = test.get("technique") or "", test.get("name") or ""
    return {c for c, t, n in CATEGORY_RULES if (t != "^$" and re.search(t, tech)) or re.search(n, name)}


def evaluate(out_dir: Path, expected: dict) -> dict:
    report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    tests = json.loads((out_dir / "ta2" / "tests.json").read_text(encoding="utf-8"))
    tests = tests.get("tests") if isinstance(tests, dict) else tests
    name_of = {s["page_id"]: posixpath.basename(urlparse(s["url"]).path) or "index.html" for s in report["screens"]}
    got: dict[str, set[str]] = {}
    for t in tests:
        got.setdefault(name_of.get(t.get("screen"), ""), set()).update(categories(t))
    tp = fp = fn = 0
    per_cat: dict[str, list[int]] = {}
    missing_screens = []
    for screen, spec in expected["screens"].items():
        want, have = set(spec["required_viewpoints"]), got.get(screen, set())
        if screen not in name_of.values():
            missing_screens.append(screen)
        for c in want | have:
            k = per_cat.setdefault(c, [0, 0, 0])
            if c in want and c in have:
                tp += 1
                k[0] += 1
            elif c in have:
                fp += 1
                k[1] += 1
            else:
                fn += 1
                k[2] += 1
    return {"n_screens": len(expected["screens"]), "all": prf(tp, fp, fn),
            "by_category": {c: prf(*v) for c, v in sorted(per_cat.items())}, "missing_screens": missing_screens}


if __name__ == "__main__":
    expected = Path(sys.argv[2]) if len(sys.argv) > 2 else EXPECTED
    print(json.dumps(evaluate(Path(sys.argv[1]), json.loads(expected.read_text(encoding="utf-8"))),
                     ensure_ascii=False, indent=1))
