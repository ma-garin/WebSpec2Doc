#!/usr/bin/env python3
"""全 System の画面を headless Chrome で撮る（LLM 不使用・ウィンドウを開かない）。

使い方: venv/bin/python scripts/shots_all.py http://127.0.0.1:8766 <出力ディレクトリ> [--widths 1280,1440]
出力: <dir>/<key>-<width>.jpg。終了時に 1 行ずつ「key width status url」を出す。
"""
import argparse
import asyncio
import pathlib
import sys

from playwright.async_api import async_playwright

PAGES = [
    ("cond", "/orchestration"), ("01doc", "/dashboard"), ("02test", "/test-automation"),
    ("03autorun", "/auto-run"), ("04cli", "/cli"), ("05heal", "/healing"),
    ("06docverify", "/docverify"), ("07batch", "/batch-test"), ("08backend", "/backend-test"),
    ("09impact", "/impact"), ("systems", "/systems"),
]


async def main(base: str, out: pathlib.Path, widths: list[int]) -> int:
    out.mkdir(parents=True, exist_ok=True)
    failures = 0
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chrome")
        for width in widths:
            ctx = await browser.new_context(viewport={"width": width, "height": 900}, device_scale_factor=1)
            page = await ctx.new_page()
            for key, path in PAGES:
                try:
                    resp = await page.goto(base + path, wait_until="networkidle", timeout=20000)
                    await page.wait_for_timeout(600)
                    await page.screenshot(path=str(out / f"{key}-{width}.jpg"), type="jpeg", quality=70)
                    print(key, width, resp.status if resp else "-", page.url.replace(base, ""))
                except Exception as exc:  # noqa: BLE001 — 1 画面の失敗で全体を止めない
                    failures += 1
                    print(key, width, "ERR", str(exc)[:80])
            await ctx.close()
        await browser.close()
    return 1 if failures else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("out")
    ap.add_argument("--widths", default="1280,1440")
    a = ap.parse_args()
    sys.exit(asyncio.run(main(a.base.rstrip("/"), pathlib.Path(a.out), [int(w) for w in a.widths.split(",")])))
