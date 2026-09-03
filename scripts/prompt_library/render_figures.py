"""図版 SVG を note へアップロードできる PNG として書き出す。"""
import sys
from pathlib import Path

sys.path.insert(0, "scripts/prompt_library")
from figures import FIGURES  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

OUT = Path("docs/prompt-library/figures")
OUT.mkdir(parents=True, exist_ok=True)

# 記事中の登場順。ファイル名の連番がそのまま挿入位置になる。
ORDER = [
    ("attrs", "01_属性からテスト条件"),
    ("pipeline", "02_パイプライン全体"),
    ("coverage", "03_確認できる範囲"),
    ("guard", "04_データと指示の分離"),
    ("promptmap", "05_プロンプトの依存関係"),
    ("handson", "06_30分ハンズオン"),
    ("bvaline", "07_境界値の数直線"),
    ("dt", "08_デシジョンテーブル"),
    ("pairwise", "09_全数とペアワイズ"),
    ("switch", "10_0switchと1switch"),
    ("technique", "11_技法の選択"),
    ("ladder", "12_画面種別の判定"),
]

PAGE = """<!doctype html><meta charset="utf-8">
<style>
 html,body{{margin:0;padding:0;background:#FFFFFF}}
 /* note は白背景なので、light 側のトークンだけを固定値で与える */
 #f{{--accent:#0E6B4C;--signal:#A94D17;color:#151E1A;padding:28px;display:inline-block;background:#fff}}
 svg{{display:block}}
</style>
<div id="f">{svg}</div>"""

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
    page = browser.new_page(device_scale_factor=2)
    for key, name in ORDER:
        page.set_content(PAGE.format(svg=FIGURES[key]))
        # SVG は max-width:100% / height:auto なので、単独描画では実寸が 0 になる。
        # viewBox から実寸（2倍）を与えてからスクリーンショットを撮る。
        page.evaluate("""() => {
          const svg = document.querySelector('#f svg');
          const vb = svg.getAttribute('viewBox').split(' ').map(Number);
          svg.style.maxWidth = 'none';
          svg.setAttribute('width', vb[2] * 1.4);
          svg.setAttribute('height', vb[3] * 1.4);
        }""")
        page.wait_for_timeout(150)
        path = OUT / f"{name}.png"
        page.locator("#f").screenshot(path=str(path))
        print(f"{path}  {path.stat().st_size // 1024} KB")
    browser.close()
