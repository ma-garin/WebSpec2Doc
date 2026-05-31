"""手渡しログインで取得したセッション（storage_state＝auth.json）の管理。

セッションはサイト単位で `{base_dir}/{domain}/auth.json` に保存する。base_dir を
注入できるようにしてテスト可能に保つ（本番では output/ を渡す）。ログイン完了の
合図には同ディレクトリのシグナルファイル（.login_done）を使う（ADR-0001 参照）。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

SESSION_FILENAME = "auth.json"
SIGNAL_FILENAME = ".login_done"

logger = logging.getLogger(__name__)


def session_path(domain: str, base_dir: Path) -> Path:
    return base_dir / domain / SESSION_FILENAME


def signal_path(domain: str, base_dir: Path) -> Path:
    return base_dir / domain / SIGNAL_FILENAME


def has_session(domain: str, base_dir: Path) -> bool:
    return session_path(domain, base_dir).is_file()


def session_age_seconds(domain: str, base_dir: Path) -> float | None:
    path = session_path(domain, base_dir)
    if not path.is_file():
        return None
    return max(0.0, time.time() - path.stat().st_mtime)
