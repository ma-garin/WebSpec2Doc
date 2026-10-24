"""共通（設定・ガイド・組織・ユーザー・アカウント）のナビ定義。System 01 の配下に置かない。"""

ITEMS: list[dict] = [
    {"key": "settings", "label": "AI の接続先", "href": "/settings", "disabled": False,
     "icon": '<circle cx="12" cy="12" r="3"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6L7 7M17 17l1.4 1.4M18.4 5.6L17 7M7 17l-1.4 1.4"/>'},
    {"key": "user-guide", "label": "ユーザーガイド", "href": "/user-guide", "disabled": False,
     "icon": '<path d="M4 4h7v16H4zM13 4h7v16h-7z"/>'},
    {"key": "references", "label": "参考", "href": "/references", "disabled": False,
     "icon": '<path d="M4 5a2 2 0 0 1 2-2h5v18H6a2 2 0 0 1-2-2z"/><path d="M11 3h7a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-7"/>'},
    {"key": "tenant-management", "label": "組織管理", "href": "/tenant-management", "disabled": False,
     "icon": '<path d="M3 21V8l9-5 9 5v13"/><path d="M9 21v-6h6v6"/>'},
    {"key": "user-management", "label": "ユーザー管理", "href": "/user-management", "disabled": False,
     "icon": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 5a3.5 3.5 0 0 1 0 7M18 14a6 6 0 0 1 3.5 6"/>'},
    {"key": "account", "label": "アカウント", "href": "/account", "disabled": False,
     "icon": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>'},
]
