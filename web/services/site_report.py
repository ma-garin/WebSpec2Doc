"""単体 HTML の報告書を組み立てる純関数（C2）。

稟議・監査に添付できる 1 枚の HTML を返す。**この配布物は外部読み込みを一切持たない**
（`<link>` / `<script src>` を含めない。CSS はトークンの実値をリテラルで埋める）。
そのためスタイルシートに `var(--…)` を使わない。受け取った人はブラウザで開くだけで読める。

I/O を行わない。呼び出し側（`web/routes/ta2.py`）が読み出したデータをそのまま渡す。
値が無い節は「捏造しない」。件数 0 や未実行はその旨を文章で出す。
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

__all__ = ["ALL_SECTIONS", "build_site_report_html"]

# ---------------------------------------------------------------- トークン実値
# static/css/ta2.css の :root と同じ値。配布物では var() が使えないため写している。
_BG = "#F6F7F9"
_SF = "#FFFFFF"
_LINE = "#E4E7EC"
_TX = "#101828"
_TX2 = "#475467"
# 白地 2.58:1 では WCAG 1.4.3（AA・4.5:1）を満たさないため #667085（4.97:1）にする
_TX3 = "#667085"
_AC = "#2563EB"
_OK_TX = "#067647"
_NG_TX = "#B42318"
_SANS = "'Inter','Noto Sans JP',system-ui,sans-serif"
_MONO = "'JetBrains Mono',ui-monospace,monospace"

#: `sections` で選べる節。UI のチェックボックスと 1 対 1 で対応する。
ALL_SECTIONS: tuple[str, ...] = ("runs", "failures", "coverage", "drift", "roi")

_KIND_LABEL = {
    "element": "要素が変わった",
    "selector": "要素が変わった",
    "ng": "要素が変わった",
    "screen": "画面が増えた",
    "new_screen": "画面が増えた",
    "added": "画面が増えた",
    "info": "画面が増えた",
    "text": "文言が変わった",
    "copy": "文言が変わった",
    "mute": "文言が変わった",
    "removed": "画面が消えた",
    "transition": "遷移が変わった",
}

_EMPTY = "—"


# 実行ログには端末の色付け（ANSI エスケープ）がそのまま混じる。
# HTML に出すと "[31m" のような文字列が読み手に見えるだけなので落とす。
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\[(?:3[0-9]|9[0-9]|0)m")


def _plain(value: Any) -> str:
    """端末制御文字を除いた素のテキスト。"""
    return _ANSI_RE.sub("", str(value if value is not None else ""))


def _e(value: Any) -> str:
    """None と数値も含めてエスケープする（テンプレートに素の値を通さない）。"""
    if value is None:
        return ""
    return html.escape(_plain(value), quote=True)


def _items(value: Any) -> list[Any]:
    if isinstance(value, Mapping):
        value = value.get("items")
    if isinstance(value, str) or not isinstance(value, Iterable):
        return []
    return [x for x in value if x is not None]


def _dicts(value: Any) -> list[Mapping[str, Any]]:
    return [x for x in _items(value) if isinstance(x, Mapping)]


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _num(value: Any) -> str:
    """件数・整数を桁区切りで返す（1702500 → 1,702,500）。"""
    return f"{_int(value):,}"


def _fmt_hours(value: Any) -> str | None:
    """時間を桁区切り・小数第 1 位で返す。数値でなければ None。"""
    try:
        return f"{float(value):,.1f}"
    except (TypeError, ValueError):
        return None


def _fmt_yen(value: Any) -> str | None:
    """金額を ¥ 付き・桁区切り・整数で返す（¥5000.0 → ¥5,000）。数値でなければ None。"""
    try:
        return f"¥{round(float(value)):,}"
    except (TypeError, ValueError):
        return None


def _duration(ms: Any) -> str:
    value = _int(ms)
    if value <= 0:
        return _EMPTY
    seconds = value // 1000
    return f"{seconds // 60}:{seconds % 60:02d}"


def _note(text: str) -> str:
    return f'<p class="note">{_e(text)}</p>'


def _style() -> str:
    return (
        "<style>\n"
        "*{box-sizing:border-box;margin:0;padding:0}\n"
        f"body{{background:{_BG};color:{_TX};font-family:{_SANS};font-size:13px;"
        "line-height:1.6;padding:28px 20px}\n"
        f"main{{max-width:900px;margin:0 auto;background:{_SF};border:1px solid {_LINE};"
        "border-radius:12px;padding:26px 30px}\n"
        ".sub{color:#667085;font-size:10.5px;font-family:'JetBrains Mono',monospace}\nh1{font-size:20px;font-weight:700;letter-spacing:-.02em;margin-bottom:4px}\n"
        f".meta{{color:{_TX3};font-size:11.5px;margin-bottom:18px;font-family:{_MONO};"
        "word-break:break-all}\n"
        f"h2{{font-size:12px;letter-spacing:.06em;color:{_TX3};font-weight:700;"
        f"margin:20px 0 8px;border-top:1px solid {_LINE};padding-top:14px}}\n"
        "h2:first-of-type{border:0;padding-top:0;margin-top:0}\n"
        ".kpi{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}\n"
        f".kpi div{{border:1px solid {_LINE};border-radius:9px;padding:10px 12px}}\n"
        ".kpi b{display:block;font-size:20px;font-weight:700;font-variant-numeric:tabular-nums}\n"
        f".kpi span{{font-size:10.5px;color:{_TX3}}}\n"
        ".ok{color:" + _OK_TX + "}\n"
        ".ng{color:" + _NG_TX + "}\n"
        "table{width:100%;border-collapse:collapse;font-size:11.5px;table-layout:fixed}\n"
        f"td,th{{padding:6px 8px;border-bottom:1px solid {_LINE};text-align:left;"
        "vertical-align:top;overflow-wrap:anywhere}\n"
        f"th{{color:{_TX3};font-size:10.5px;font-weight:600}}\n"
        f"a{{color:{_AC}}}\n"
        f"p.note{{font-size:12px;color:{_TX2};line-height:1.8}}\n"
        f"footer{{max-width:900px;margin:14px auto 0;color:{_TX3};font-size:11px}}\n"
        "</style>"
    )


# ------------------------------------------------------------------ 各セクション
def _section_runs(runs: Sequence[Mapping[str, Any]], registered: int = 0) -> str:
    head = "<h2>直近の実行</h2>"
    if not runs:
        return head + _note("このサイトではまだテストを実行していません（実行の記録が 0 件）。")
    last = runs[0]
    passed, failed = _int(last.get("passed")), _int(last.get("failed"))
    total = _int(last.get("total")) or (passed + failed)
    at = _str(last.get("at")) or "（記録なし）"
    # 一覧（登録済み全件の最新状態）と数字が食い違って見えるため、母数を明記する。
    scope = f"この節が数えているのは、直近の実行（{at}）で流した {_num(total)} 件だけです。"
    if registered:
        scope += (
            f"登録済みのテストは {_num(registered)} 件あり、一覧に出る成功・失敗の内訳は"
            "「登録済み全件の最新状態」なので、母数が違います。"
        )
    return (
        head
        + '<div class="kpi">'
        + f'<div><b class="ok">{_num(passed)}</b><span>この実行の成功</span></div>'
        + f'<div><b class="ng">{_num(failed)}</b><span>この実行の失敗</span></div>'
        + f"<div><b>{_num(total)}</b><span>この実行で流した件数</span></div>"
        + f'<div><b>{_e(_duration(last.get("duration_ms")))}</b><span>所要</span></div>'
        + "</div>"
        + _note(f'実行日時 {at} · 実行 ID {_str(last.get("run_id")) or "（記録なし）"}')
        + _note(scope)
    )


def _str(value: Any) -> str:
    return "" if value is None else str(value)


def _artifact_link(base_url: str, domain: str, test_id: str, kind: str, label: str) -> str:
    from urllib.parse import quote

    url = (
        f"{base_url}/api/ta2/artifact?domain={quote(domain, safe='')}"
        f"&id={quote(test_id, safe='')}&kind={quote(kind, safe='')}"
    )
    return f'<a href="{_e(url)}">{_e(label)}</a>'


def _section_failures(
    tests: Sequence[Mapping[str, Any]],
    screen_names: Mapping[str, str],
    *,
    domain: str,
    base_url: str,
) -> str:
    head = "<h2>失敗したテスト</h2>"
    failed = [t for t in tests if _str(t.get("status")) == "fail"]
    if not failed:
        if not tests:
            return head + _note("テストがまだ 1 件も作られていません。")
        return head + _note("直近の記録では失敗したテストはありません。")
    rows = []
    for test in failed:
        test_id = _str(test.get("id"))
        last = test.get("last") if isinstance(test.get("last"), Mapping) else {}
        # 失敗理由は 1 行目だけを載せる。スタックトレース全文は読み手（稟議・監査）には
        # ノイズで、表を横に破壊する。詳細は証跡リンクの Trace 側にある。
        error = _str(last.get("error")).strip().splitlines()[0] if last.get("error") else ""
        if len(error) > 200:
            error = error[:200] + "…"
        screen = _str(test.get("screen"))
        screen_label = screen_names.get(screen) or screen or _EMPTY
        detail = f'<br><span class="ng">{_e(error)}</span>' if error else ""
        links = " / ".join(
            [
                _artifact_link(base_url, domain, test_id, "screenshot", "スクショ"),
                _artifact_link(base_url, domain, test_id, "trace", "Trace"),
            ]
        )
        rows.append(
            f"<tr><td>{_e(test_id)}</td><td>{_e(_str(test.get('name')))}{detail}</td>"
            f"<td>{_e(screen_label)}</td><td>{links}</td></tr>"
        )
    return (
        head
        + '<table><thead><tr><th style="width:90px">ID</th><th>テスト</th>'
        + '<th style="width:120px">画面</th><th style="width:130px">証跡</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
        + _note("証跡のリンクはこのツールが動いている環境でのみ開けます。")
    )


def _section_coverage(screens: Sequence[Mapping[str, Any]]) -> str:
    head = "<h2>画面ごとのカバレッジ</h2>"
    if not screens:
        return head + _note("画面の解析結果がありません。")
    rows: list[str] = []
    seen: set[str] = set()
    dropped = 0
    for screen in screens:
        # 同じ page_id が 2 度来ることがある（地図の payload 側の重複）。
        # 同名の別画面（P001 / P002）は ID 列で区別できるので消さない。
        key = _str(screen.get("id")) or _str(screen.get("name"))
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        tests = _int(screen.get("tests"))
        coverage = f'{_int(screen.get("coverage"))}%' if tests else "未着手"
        fails = _num(screen.get("fails")) if tests else _EMPTY
        # 画面名はサイトによっては全画面で同じことがある（<title> が共通）。
        # 名前だけでは見分けられないので、分かるときはパスを添える。
        path = _str(screen.get("path")) or _str(screen.get("url"))
        label = _e(_str(screen.get("name")) or _str(screen.get("id")))
        if path:
            label += f'<br><span class="sub">{_e(path)}</span>'
        rows.append(
            f"<tr><td>{_e(_str(screen.get('id')) or _EMPTY)}</td>"
            f"<td>{label}</td>"
            f"<td>{_num(tests)}</td><td>{_e(fails)}</td><td>{_e(coverage)}</td></tr>"
        )
    note = (
        _note(f"同じ画面 ID の行が {_num(dropped)} 件重複していたため、最初の 1 行だけを残しました。")
        if dropped
        else ""
    )
    return (
        head
        + '<table><thead><tr><th style="width:76px">画面ID</th><th>画面</th>'
        + '<th style="width:70px">テスト</th><th style="width:70px">失敗</th>'
        + '<th style="width:90px">カバレッジ</th>'
        + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
        + note
    )


def _section_drift(drift: Any) -> str:
    meta = drift if isinstance(drift, Mapping) else {}
    items = _dicts(drift)
    open_items = [d for d in items if _str(d.get("state") or "open") == "open"]
    baseline = _str(meta.get("baseline_at"))
    reason = _str(meta.get("reason"))
    if not open_items:
        head = "<h2>検出した変更</h2>"
        if reason or (isinstance(drift, Mapping) and not baseline):
            # 比較していないことを「変更 0 件」と書かない（最も誤解を生む表現）。
            return head + _note(
                (reason or "比較の基準となる前回のクロールがありません。")
                + "変更が 0 件なのではなく、まだ比較していません。"
            )
        if not isinstance(drift, Mapping) and not items:
            return head + _note(
                "変更の記録がありません（比較した結果 0 件なのか、まだ比較していないのかを判定できません）。"
            )
        base_label = f"前回の解析（{baseline}）と比べて、" if baseline else "直近の比較では、"
        return "<h2>検出した変更（未対応 0 件）</h2>" + _note(f"{base_label}未対応の変更はありません。")
    rows = []
    for item in open_items:
        kind = _KIND_LABEL.get(_str(item.get("kind")), _str(item.get("kind")) or "変更")
        impact = _items(item.get("impact"))
        impact_label = f"テスト {_num(len(impact))} 件" if impact else "影響なし"
        rows.append(
            f"<tr><td>{_e(kind)}</td><td>{_e(_str(item.get('title')))}</td>"
            f"<td>{_e(impact_label)}</td></tr>"
        )
    return (
        f"<h2>検出した変更（未対応 {_num(len(open_items))} 件）</h2>"
        + '<table><thead><tr><th style="width:120px">種類</th><th>内容</th>'
        + '<th style="width:110px">影響</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
    )


def _section_roi(usage: Mapping[str, Any] | None, *, domain: str = "") -> str:
    """削減工数。`usage["domain"]` がこのサイトなら「このサイトのみ」と明示する。

    絞り込みは呼び出し側（usage_log.jsonl の domain 列で絞る）が行う。
    絞られていない値をサイト名義の見出しの下に黙って出さない。
    """
    site = _str(domain)
    scoped = isinstance(usage, Mapping) and site != "" and _str(usage.get("domain")) == site
    head = (
        f"<h2>削減できた工数（推定・{_e(site)} のみ）</h2>"
        if scoped
        else "<h2>削減できた工数（推定・ワークスペース全体）</h2>"
    )
    if not isinstance(usage, Mapping) or not usage:
        return head + _note("利用実績が記録されていないため、推定できません。")
    hours = _fmt_hours(usage.get("estimated_saved_hours"))
    yen = _fmt_yen(usage.get("estimated_saved_yen"))
    if hours is None and yen is None:
        return head + _note("利用実績に削減工数の項目がないため、推定できません。")
    coefficients = usage.get("coefficients")
    rate = ""
    if isinstance(coefficients, Mapping):
        rate_text = _fmt_yen(coefficients.get("hourly_rate_yen"))
        if rate_text:
            rate = f"・単価 {rate_text}/h"
    scope_label = (
        f"{site} の利用実績" if scoped else "ワークスペース全体（他のサイトを含む）の利用実績"
    )
    caveat = "" if scoped else f"この数字は{site or 'このサイト'}単体の実績ではありません。"
    return head + _note(
        f"{scope_label} 解析 {_num(usage.get('total_crawls'))} 回・"
        f"画面 {_num(usage.get('total_screens'))} 枚・"
        f"テスト条件 {_num(usage.get('total_test_conditions'))} 件から "
        f"{hours or _EMPTY} 時間（{yen or _EMPTY} 相当{rate}）。"
        + caveat
        + "この値は係数による推定であり、実測ではありません。"
    )


# ------------------------------------------------------------------ エントリポイント
def build_site_report_html(
    domain: str,
    *,
    report: Mapping[str, Any] | None = None,
    tests: Sequence[Mapping[str, Any]] | None = None,
    runs: Sequence[Mapping[str, Any]] | None = None,
    drift: Any = None,
    map_screens: Sequence[Mapping[str, Any]] | None = None,
    usage: Mapping[str, Any] | None = None,
    base_url: str = "",
    generated_at: str | None = None,
    sections: Sequence[str] | None = None,
) -> str:
    """単体 HTML の報告書を返す。純関数（ファイル・ネットワークに触れない）。

    `sections` で節を絞れる（既定は全節）。未知の名前は無視する。
    """
    wanted = (
        ALL_SECTIONS
        if sections is None
        else tuple(s for s in ALL_SECTIONS if s in set(sections))
    )
    report = report if isinstance(report, Mapping) else {}
    test_rows = _dicts(tests)
    run_rows = _dicts(runs)
    screens = _dicts(map_screens)
    screen_names = {
        _str(s.get("id")): _str(s.get("name")) or _str(s.get("id")) for s in screens
    }
    base = _str(base_url).rstrip("/")

    meta = report.get("meta") if isinstance(report.get("meta"), Mapping) else {}
    target_url = _str(meta.get("target_url")) or _str(report.get("site_url"))
    crawled_at = _str(meta.get("crawled_at")) or _str(report.get("generated_at"))
    stamp = generated_at or datetime.now().strftime("%Y-%m-%d %H:%M")

    body: list[str] = []
    if "runs" in wanted:
        body.append(_section_runs(run_rows, len(test_rows)))
    if "failures" in wanted:
        body.append(
            _section_failures(test_rows, screen_names, domain=_str(domain), base_url=base)
        )
    if "coverage" in wanted:
        body.append(_section_coverage(screens))
    if "drift" in wanted:
        body.append(_section_drift(drift))
    if "roi" in wanted:
        body.append(_section_roi(usage, domain=_str(domain)))
    if not body:
        body.append(_note("出力する節が 1 つも選ばれていません。"))

    title = f"{_e(domain)} — テスト自動化レポート"
    meta_line = " · ".join(
        [
            _e(target_url or "対象 URL の記録なし"),
            f"生成 {_e(stamp)}",
            f'最終解析 {_e(crawled_at or "記録なし")}',
        ]
    )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{title}</title>\n{_style()}\n</head><body>\n"
        f'<main><h1>{title}</h1><div class="meta">{meta_line}</div>\n'
        + "\n".join(body)
        + "\n</main>\n"
        '<footer>WebSpec2Doc が生成した単体 HTML です。外部の CSS・スクリプトを読み込みません。</footer>\n'
        "</body></html>\n"
    )
