"""ドキュメント作成(app) のモック実行系。

対象が ``https://app.<package>`` のとき、画面解析（/api/discover-stream）と実行（/run）を
実クローラの代わりにここで肩代わりし、実物と同じイベント語彙・同じ成果物の置き方で返す。
画面側（wizard.js / execution.js / results.js）は一切分岐しない。これがモックである根拠は
この 1 ファイルに閉じ込め、実装時はここを uiautomator2 / WebDriverAgent のアダプタに差し替える。
"""

from __future__ import annotations

import json
import shutil
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from urllib.parse import urlsplit

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "demo" / "sample_report_app"

# 発見する画面（demo/sample_report_app/report.json の P001〜P006 と同じ順・同じ URL）
SCREENS: tuple[tuple[str, str, str], ...] = (
    ("P001", "HomeActivity", "SampleShop - ホーム"),
    ("P002", "ProductListActivity", "SampleShop - 商品一覧"),
    ("P003", "CheckoutActivity", "SampleShop - お支払い・決済"),
    ("P004", "ContactActivity", "SampleShop - お問い合わせ"),
    ("P005", "MyPageActivity", "SampleShop - マイページ"),
    ("P006", "CampaignActivity", "SampleShop - キャンペーン"),
)


def is_app_target(url: str) -> bool:
    """``https://app.<package>`` を「スマホアプリ対象」とみなす（モックの取り決め）。"""
    try:
        host = urlsplit(url.strip()).hostname or ""
    except ValueError:
        return False
    return host.startswith("app.")


def _base(url: str) -> str:
    parts = urlsplit(url.strip())
    return f"{parts.scheme}://{parts.hostname}"


def discover_sse(url: str, run_id: str, sleep: Callable[[float], None] = time.sleep) -> Iterator[str]:
    """/api/discover-stream と同じ SSE 行を返す（run_id → 進行イベント → page → done）。"""
    base = _base(url)
    yield f"data: {json.dumps({'run_id': run_id})}\n\n"
    yield f"data: {json.dumps({'crawl_event': {'event': 'discover_started'}})}\n\n"
    sleep(0.6)
    yield f"data: {json.dumps({'crawl_event': {'event': 'browser_ready'}})}\n\n"
    for _pid, activity, title in SCREENS:
        sleep(0.45)
        page = {"url": f"{base}/{activity}", "title": title, "login_required": False}
        yield f"data: {json.dumps({'page': page}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'done': True, 'total': len(SCREENS)})}\n\n"


def run_stream(
    run_id: str,
    domain: str,
    out_dir: Path,
    urls: str,
    summary_for_domain: Callable[[str, Path], dict],
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[str]:
    """/run と同じ text/plain 行を返す。RUN_ID → ログ/CRAWL_EVENT → REPORT_PATH → SUMMARY。

    スクリーンショットは画面ごとに成果物ディレクトリへ置いていくので、実物と同じ
    /api/live-screenshot の仕組みでライブプレビューが動く。
    """
    domain_dir = out_dir / domain
    shots_dir = domain_dir / "screenshots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    targets = [u for u in urls.split(",") if u]
    wanted = {u.rstrip("/").rsplit("/", 1)[-1] for u in targets}
    screens = [s for s in SCREENS if s[1] in wanted] or list(SCREENS)
    base = _base(targets[0]) if targets else "https://app.sampleshop"
    total = len(screens)

    def ev(payload: dict) -> str:
        return "CRAWL_EVENT:" + json.dumps(payload, ensure_ascii=False) + "\n"

    yield f"RUN_ID:{run_id}\n"
    yield f"対象アプリ: {domain[4:]}（エミュレータ）\n"
    yield "アプリをインストールしています…\n"
    sleep(0.8)
    yield "起動して初期画面を取得しました\n"
    yield ev({"event": "crawl_started", "total": total, "parallelism": 1})
    for index, (pid, activity, _title) in enumerate(screens, start=1):
        url = f"{base}/{activity}"
        yield ev({"event": "page_started", "index": index, "url": url, "total": total})
        yield f"[{index}/{total}] クロール中: {url}\n"
        for name in (f"{pid}.png", f"{pid}_full.png"):
            src = FIXTURE_DIR / "screenshots" / name
            if src.is_file():
                shutil.copyfile(src, shots_dir / name)
        sleep(0.9)
        yield ev({"event": "page_completed", "index": index, "url": url, "total": total, "elapsed_sec": 0.9})
        # execution.js は saved_count で保存数を数える（0 件だと「取得できた画面がありません」になる）
        yield ev({"event": "checkpoint_saved", "saved_count": index, "total": total})
    # 生成フェーズも実物と同じイベント（generate_started → generate_completed × n）で進捗を出す
    steps = ("フォーム項目を抽出", "遷移と状態を確定", "テスト条件を組み立て", "文書を書き出し")
    yield ev({"event": "generate_started", "total_steps": len(steps)})
    yield "解析中: フォーム項目・遷移・テスト条件を組み立てています\n"
    for index, label in enumerate(steps, start=1):
        sleep(0.5)
        if index == len(steps):
            shutil.copytree(FIXTURE_DIR, domain_dir, dirs_exist_ok=True)
        yield ev({"event": "generate_completed", "index": index, "label": label, "total_steps": len(steps)})
    yield "出力: report.html / report.json / spec.xlsx / transition.mmd\n"
    yield "完了\n"
    report = domain_dir / "report.html"
    if report.is_file():
        yield f"REPORT_PATH:{report.resolve()}\n"
    yield f"SUMMARY:{json.dumps(summary_for_domain(domain, out_dir))}\n"
