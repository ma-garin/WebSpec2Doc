"""再クロール時のセッション期限切れ検出（ADR-0001 の方式を踏襲）。

認証付きクロール中に認証ページへ弾かれた場合、保存セッションが失効している。
これを検出して中断することで、到達ページ激減による「大量削除」ドリフトの
偽陽性を防ぐ。判定は #4 の detect_login_wall を再利用する。
"""
from __future__ import annotations

import logging
from pathlib import Path

from analyzer.login_wall import PageAuthSignals, detect_login_wall

logger = logging.getLogger(__name__)


class SessionExpiredError(Exception):
    """認証付きクロール中にセッション失効（login wall）を検出した。"""


def is_session_expired(auth_state: Path | None, signals: PageAuthSignals) -> bool:
    """auth_state を指定したクロールで login wall に当たったら True。
    認証なしクロールでは login wall でも期限切れとは見なさない。"""
    if auth_state is None:
        return False
    return detect_login_wall(signals).is_login_required
