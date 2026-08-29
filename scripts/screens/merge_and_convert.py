"""撮影結果の manifest を統合し、PNG を docs/screens/shots/ へ WebP 変換する。

引数: 撮影用スクリプトの出力先ディレクトリ（PNG と manifest*.json が入っている）。
出力: <shots>/merged.json（掲載順・重複解決済み）と docs/screens/shots/*.webp
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

# 走査の起点として撮り直した足場。同じ画面が本編にあるので掲載しない。
SCAFFOLD_IDS = {"D07-tabs", "D04-tabs"}
# 後から撮った manifest の同一 ID が勝つ（例: A04 はログイン後に撮り直している）。
MANIFESTS = ["manifest.json", "manifest2.json", "manifest3.json", "manifest4.json", "manifest5.json"]
DEST = Path("docs/screens/shots")
MAX_WIDTH = 1440


def main() -> int:
    shots = Path(sys.argv[1])
    recs: dict[str, dict] = {}
    order: list[str] = []
    for name in MANIFESTS:
        path = shots / name
        if not path.is_file():
            print(f"警告: {path} がありません（この段の撮影を飛ばした場合は正常）")
            continue
        for rec in json.loads(path.read_text(encoding="utf-8")):
            if rec["id"] in SCAFFOLD_IDS:
                continue
            if rec["id"] not in recs:
                order.append(rec["id"])
            recs[rec["id"]] = rec

    merged = [recs[i] for i in order]
    (shots / "merged.json").write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    DEST.mkdir(parents=True, exist_ok=True)
    keep = {r["id"] for r in merged if r.get("ok")}
    size_in = size_out = 0
    for rec in merged:
        if not rec.get("ok"):
            continue
        src = shots / f"{rec['id']}.png"
        if not src.is_file():
            print(f"警告: PNG がありません: {src}")
            continue
        image = Image.open(src).convert("RGB")
        width, height = image.size
        if width > MAX_WIDTH:
            image = image.resize((MAX_WIDTH, int(height * MAX_WIDTH / width)), Image.LANCZOS)
        out = DEST / f"{rec['id']}.webp"
        image.save(out, "WEBP", quality=82, method=5)
        size_in += src.stat().st_size
        size_out += out.stat().st_size

    # 前回の生成物で今回掲載しないものを残さない（消えた画面が居座らないように）。
    for stale in DEST.glob("*.webp"):
        if stale.stem not in keep:
            stale.unlink()
            print("削除:", stale.name)

    failed = [r["id"] for r in merged if not r.get("ok")]
    print(f"掲載 {len(merged)} 件 / 撮影失敗 {len(failed)} 件 {failed}")
    print(f"画像 {size_in / 1e6:.1f}MB -> {size_out / 1e6:.1f}MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
