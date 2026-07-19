"""観測に使うビューポートの定義。

幅は「よくある実機」ではなく**レスポンシブの分岐が起きやすい代表値**を選ぶ。
機種名で語ると実機保証と誤解されるため、識別子は用途名（desktop/tablet/mobile）にする。
"""

from __future__ import annotations

from dataclasses import dataclass

DESKTOP = "desktop"
TABLET = "tablet"
MOBILE = "mobile"

# UA を分けるのは、UA スニッフでレイアウトを変えるサイトが実在するため。
_DESKTOP_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


@dataclass(frozen=True)
class ViewportProfile:
    """1つの観測条件。"""

    name: str
    width: int
    height: int
    user_agent: str
    is_mobile: bool
    label: str

    @property
    def size(self) -> dict[str, int]:
        return {"width": self.width, "height": self.height}


PROFILES: dict[str, ViewportProfile] = {
    DESKTOP: ViewportProfile(
        name=DESKTOP,
        width=1366,
        height=768,
        user_agent=_DESKTOP_UA,
        is_mobile=False,
        label="PC（1366×768）",
    ),
    TABLET: ViewportProfile(
        name=TABLET,
        width=768,
        height=1024,
        user_agent=_DESKTOP_UA,
        is_mobile=False,
        label="タブレット（768×1024）",
    ),
    MOBILE: ViewportProfile(
        name=MOBILE,
        width=390,
        height=844,
        user_agent=_MOBILE_UA,
        is_mobile=True,
        label="スマートフォン（390×844）",
    ),
}

DEFAULT_PROFILE_NAMES = (DESKTOP, TABLET, MOBILE)


def get_profile(name: str) -> ViewportProfile:
    """名前からプロファイルを引く。未知の名前は明示的に拒否する。"""
    try:
        return PROFILES[name]
    except KeyError:
        known = ", ".join(sorted(PROFILES))
        raise ValueError(f"未知のビューポート: {name}（利用可能: {known}）") from None


def resolve_profiles(names: list[str] | tuple[str, ...] | None) -> list[ViewportProfile]:
    """指定名（未指定なら既定3種）をプロファイルへ解決する。順序は指定順を保つ。"""
    selected = tuple(names) if names else DEFAULT_PROFILE_NAMES
    seen: set[str] = set()
    profiles: list[ViewportProfile] = []
    for name in selected:
        key = str(name).strip()
        if key in seen:
            continue
        seen.add(key)
        profiles.append(get_profile(key))
    return profiles
