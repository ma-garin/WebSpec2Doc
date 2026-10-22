"""Document Assurance Report（Markdown / CSV / JSON）。保存済み分析結果から作る。評価不能は数値にしない。"""
from __future__ import annotations

import csv
import io
import json

_STATE = {"READY": "準備完了", "CONDITIONALLY_READY": "条件付き", "REVIEWABLE": "レビュー可能",
          "DRAFT": "ドラフト", "BLOCKED": "ブロック"}
_SEV = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _score_line(name: str, s: dict) -> str:
    cov = round(100 * (s.get("coverage") or 0))
    if s.get("value") is None:
        return f"- {name}: 評価不能（評価できた範囲 {cov}%）"
    return f"- {name}: {round(s['value'])}/100（評価できた範囲 {cov}%）"


def _top(findings: list[dict], n: int = 10) -> list[dict]:
    return sorted(findings, key=lambda f: _SEV.get(f.get("severity"), 9))[:n]


def markdown(r: dict) -> str:
    g = r.get("readiness") or {}
    sc = r.get("scores") or {}
    f = r.get("findings") or []
    cf = r.get("conflicts") or []
    tests = r.get("testability") or {}
    cnt = lambda sev: sum(1 for x in f if x.get("severity") == sev)  # noqa: E731
    nt = [k for k, v in tests.items() if v.get("verdict") == "NOT_TESTABLE"]
    dec = r.get("decisions") or []
    waivers = [d for d in dec if d.get("decision") == "waived"]
    cov = ((r.get("trace") or {}).get("coverage")) or {}
    out = ["# Document Assurance Report", "",
           "## 1. 要約（Executive Summary）",
           f"- 準備状態: **{_STATE.get(g.get('state'), g.get('state'))}**（{g.get('state')}）",
           *[f"  - {x}" for x in g.get("reasons") or []],
           f"- 対象: 文書 {len(r.get('documents') or [])} 件・要件 {len(r.get('requirements') or [])} 件",
           f"- 指摘: critical {cnt('critical')} / high {cnt('high')} / medium {cnt('medium')} / low {cnt('low')}",
           f"- 未解決の矛盾候補: {sum(1 for c in cf if c.get('status') == 'UNRESOLVED')} 件",
           f"- テスト不可の要件: {len(nt)} 件", "",
           "## 2. 品質スコア"]
    out += [_score_line(k, v) for k, v in sc.items()] or ["- 評価なし"]
    out += ["", "## 3. 重要な指摘（上位 10 件。すべて候補で、人が確定するまで事実ではない）"]
    out += [f"- [{x.get('severity')}] {x.get('title')} — {x.get('location', {}).get('document_id')}:"
            f"{x.get('location', {}).get('line_start')} 「{x.get('location', {}).get('snippet', '')[:60]}」" for x in _top(f)] or ["- なし"]
    out += ["", "## 4. 矛盾候補（どちらが正しいかは未確定）"]
    for c in cf:
        ev = " / ".join(f"{e.get('document_id')}:{e.get('quote', '')[:30]}" for e in c.get("evidence") or [])
        out.append(f"- {c.get('conflict_id')} {c.get('topic')}: {ev} — {c.get('question', '')}")
    if not cf:
        out.append("- 検出なし（検出できる範囲の候補。矛盾が無いことの証明ではない）")
    out += ["", "## 5. テスト可能性", f"- テスト不可: {', '.join(nt) or 'なし'}", "",
            "## 6. トレーサビリティ（件数。テスト案が存在しても実行済みとは数えない）"]
    out += [f"- {k}: {v}" for k, v in cov.items() if k not in ("note",)] or ["- 未算出"]
    out += ["", "## 7. 人の判断と waiver"]
    out += [f"- {d.get('decision')} {d.get('target')}（{d.get('by')}）: {d.get('reason')}"
            + (f" 期限 {d.get('expiry')}" if d.get("expiry") else "") for d in dec] or ["- なし"]
    out += ["", "## 8. 限界",
            f"- 分析モード: {r.get('mode')}（AI レビューが未実行のときは決定論の検出のみ）",
            "- 検出できなかったことは、存在しないことを意味しない",
            "- 評価不能の次元は点数にしていない",
            *[f"- 失敗した分析段階: {e.get('stage')}" for e in r.get("errors") or []],
            "", "## 9. 次の一手"]
    nxt = [f"- 矛盾の確認: {c.get('topic')}" for c in cf[:3]] + [f"- 定義の追加: {k}" for k in nt[:3]]
    out += nxt or ["- 重要な指摘から順に確認する"]
    return "\n".join(out) + "\n"


def issues_csv(r: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["finding_id", "severity", "rule_id", "title", "document", "line", "requirement", "status", "source", "reason"])
    for x in r.get("findings") or []:
        loc = x.get("location") or {}
        cells = [x.get("finding_id"), x.get("severity"), x.get("rule_id"), x.get("title"), loc.get("document_id"),
                 loc.get("line_start"), x.get("requirement_id"), x.get("status"), x.get("source"), x.get("reason")]
        # 表計算ソフトの数式として解釈される先頭文字を無効化する
        w.writerow([("'" + c) if isinstance(c, str) and c[:1] in "=+-@" else c for c in cells])
    return buf.getvalue()


def as_json(r: dict) -> str:
    return json.dumps({k: v for k, v in r.items() if k != "source_texts"}, ensure_ascii=False, indent=1)
