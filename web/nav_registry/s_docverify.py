"""System 06 ドキュメント検証のナビ定義。href は現行のハッシュ遷移のまま（docverify-sidebar.html）。"""

ITEMS: list[dict] = [
    {"key": "cases", "label": "レビュー一覧", "href": "/docverify#cases", "disabled": False,
     "icon": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'},
    {"key": "checklists", "label": "観点", "href": "/docverify#checklists", "disabled": False,
     "icon": '<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4 6h.01M4 12h.01M4 18h.01"/>'},
    {"key": "metrics", "label": "履歴", "href": "/docverify#metrics", "disabled": False,
     "icon": '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l3 2"/>'},
    {"key": "settings", "label": "設定", "href": "/docverify#settings", "disabled": False,
     "icon": '<circle cx="12" cy="12" r="3"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6L7 7M17 17l1.4 1.4M18.4 5.6L17 7M7 17l-1.4 1.4"/>'},
]
