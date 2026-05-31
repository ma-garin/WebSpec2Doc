"""サイトのクロール設定（SiteConfig）を永続化するレジストリ。

再クロールが前回と同じ設定を忠実に再現できるよう、設定を
`{base_dir}/{domain}/site.json` に保存・復元する。base_dir を注入できる
ようにしてテスト可能に保つ（本番では output/ を渡す）。
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

SITE_CONFIG_FILENAME = "site.json"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SiteConfig:
    domain: str
    urls: tuple[str, ...]
    crawl_mode: str
    depth: int
    max_pages: int
    formats: tuple[str, ...]
    auth_path: str = ""


def save_site(config: SiteConfig, base_dir: Path) -> Path:
    target = base_dir / config.domain / SITE_CONFIG_FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_site(domain: str, base_dir: Path) -> SiteConfig | None:
    path = base_dir / domain / SITE_CONFIG_FILENAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return _to_config(data)
    except (OSError, json.JSONDecodeError, TypeError, KeyError) as exc:
        logger.warning("site.json の読み込みに失敗しました: %s (%s)", path, exc)
        return None


def list_sites(base_dir: Path) -> list[SiteConfig]:
    if not base_dir.is_dir():
        return []
    sites = [load_site(child.name, base_dir) for child in base_dir.iterdir() if child.is_dir()]
    return [site for site in sites if site is not None]


def _to_config(data: dict[str, object]) -> SiteConfig:
    return SiteConfig(
        domain=str(data["domain"]),
        urls=tuple(data.get("urls", ()) or ()),  # type: ignore[arg-type]
        crawl_mode=str(data.get("crawl_mode", "")),
        depth=int(str(data.get("depth", 0))),
        max_pages=int(str(data.get("max_pages", 0))),
        formats=tuple(data.get("formats", ()) or ()),  # type: ignore[arg-type]
        auth_path=str(data.get("auth_path", "")),
    )
