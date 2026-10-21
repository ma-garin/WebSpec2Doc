"""`doc` サブコマンド（verify / requirements / conflicts / trace）。決定論の分析を直接呼び、API を要しない。"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import tempfile
from pathlib import Path

EXIT_OK, EXIT_INPUT, EXIT_BLOCKED = 0, 1, 2
_PLAIN = {".md", ".txt"}
_RANK = {"BLOCKED": 2, "CONDITIONALLY_READY": 1}


class InputError(Exception):
    pass


def _read(path: Path) -> str:
    if not path.is_file():
        raise InputError(f"ファイルが見つかりません: {path.name}。パスを確かめて再実行してください。")
    if path.suffix.lower() in _PLAIN:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            raise InputError(f"{path.name} を UTF-8 として読めません。UTF-8 で保存し直してください。") from None
    else:
        from web.services.docverify import ingest
        try:
            with tempfile.TemporaryDirectory() as tmp:
                _, passages = ingest.ingest(path.name, path.read_bytes(), Path(tmp))
        except ingest.IngestError as exc:
            raise InputError(f"{exc} 対応形式は md / txt / docx / xlsx / pdf です。") from None
        except OSError:
            raise InputError(f"{path.name} を読めません。権限とパスを確かめてください。") from None
        text = "\n".join(p["text"] for p in passages)
    if not text.strip():
        raise InputError(f"{path.name} が空です。中身のある文書を指定してください。")
    return text


def _analyze(paths: list[str], profile: str) -> dict:
    from web.services.docassure import pipeline
    docs = [{"id": f"D{i}", "name": Path(p).name, "type": "other", "text": _read(Path(p))}
            for i, p in enumerate(paths, 1)]
    return pipeline.analyze(docs, profile=profile)


def _csv(rows: list[dict], cols: list[str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for r in rows:
        cells = [r.get(c) for c in cols]
        w.writerow([("'" + c) if isinstance(c, str) and c[:1] in "=+-@" else c for c in cells])
    return buf.getvalue()


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, default=str)


def _render(cmd: str, r: dict, fmt: str) -> str:
    from web.services.docassure import report
    if cmd == "verify":
        return {"json": report.as_json, "md": report.markdown, "csv": report.issues_csv}[fmt](r)
    if cmd == "requirements":
        reqs = r.get("requirements") or []
        if fmt == "json":
            return _dump(reqs)
        if fmt == "csv":
            return _csv(reqs, ["document_id", "requirement_id", "text", "kind"])
        return "# 要件一覧\n\n" + ("\n".join(
            f"- {q.get('document_id')}:{q.get('requirement_id')} {str(q.get('text') or q.get('title') or '')[:120]}"
            for q in reqs) or "- 抽出された要件なし") + "\n"
    if cmd == "conflicts":
        cf = r.get("conflicts") or []
        if fmt == "json":
            return _dump(cf)
        if fmt == "csv":
            return _csv([{**c, "question": c.get("question")} for c in cf], ["conflict_id", "topic", "status", "question"])
        return "# 矛盾候補（どちらが正しいかは未確定）\n\n" + ("\n".join(
            f"- {c.get('conflict_id')} {c.get('topic')} [{c.get('status')}] {c.get('question', '')}"
            for c in cf) or "- 検出なし（矛盾が無いことの証明ではない）") + "\n"
    tr = r.get("trace") or {}
    cov = tr.get("coverage") or {}
    g = tr.get("graph") or {}
    summary = {"coverage": cov, "linked_ratio": tr.get("linked_ratio"),
               "nodes": len(g.get("nodes") or []), "edges": len(g.get("edges") or [])}
    if fmt == "json":
        return _dump(summary)
    if fmt == "csv":
        return _csv([{"metric": k, "value": v} for k, v in {**cov, "linked_ratio": summary["linked_ratio"],
                    "nodes": summary["nodes"], "edges": summary["edges"]}.items() if k != "note"], ["metric", "value"])
    return "# トレース要約\n\n" + "\n".join(
        f"- {k}: {v}" for k, v in {**cov, "linked_ratio": summary["linked_ratio"],
                                   "nodes": summary["nodes"], "edges": summary["edges"]}.items() if k != "note") + "\n"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="webspec2doc doc", description="文書の品質検証（決定論の分析。API 不要）")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, h in (("verify", "検証レポート"), ("requirements", "要件一覧"),
                    ("conflicts", "矛盾候補"), ("trace", "トレース要約と coverage")):
        s = sub.add_parser(name, help=h)
        s.add_argument("files", nargs="+", help="md / txt / docx / xlsx / pdf")
        s.add_argument("--format", choices=("json", "md", "csv"), default="md")
        s.add_argument("--out", type=Path, help="出力ファイル（未指定は標準出力）")
        s.add_argument("--profile", default="default")
        s.add_argument("--fail-on", choices=("blocked", "conditional"), default="blocked",
                       help="終了コード 2 にする準備状態のしきい値")
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:
        return EXIT_INPUT if e.code else EXIT_OK
    try:
        result = _analyze(args.files, args.profile)
    except InputError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return EXIT_INPUT
    except Exception as exc:  # 本文は出さず型名だけ
        print(f"エラー: 分析に失敗しました（{type(exc).__name__}）。入力文書を確かめて再実行してください。", file=sys.stderr)
        return EXIT_INPUT
    out = _render(args.cmd, result, args.format)
    if args.out:
        try:
            args.out.write_text(out, encoding="utf-8")
        except OSError:
            print("エラー: 出力先に書き込めません。パスと権限を確かめてください。", file=sys.stderr)
            return EXIT_INPUT
    else:
        sys.stdout.write(out)
    state = (result.get("readiness") or {}).get("state")
    limit = 2 if args.fail_on == "blocked" else 1
    return EXIT_BLOCKED if _RANK.get(state, 0) >= limit else EXIT_OK
