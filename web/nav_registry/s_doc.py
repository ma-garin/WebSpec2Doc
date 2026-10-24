"""System 01 ドキュメント作成のナビ定義。href は現行 URL のまま。"""

ITEMS: list[dict] = [
    {"key": "dashboard", "label": "ダッシュボード", "href": "/dashboard", "disabled": False,
     "icon": '<path d="M3 11.5L12 4l9 7.5"/><path d="M5.5 10v10h13V10M9.5 20v-6h5v6"/>'},
    {"key": "run-history", "label": "実行履歴", "href": "/run-history", "disabled": False,
     "icon": '<circle cx="12" cy="12" r="9"/><path d="M12 8v5l3 2"/>'},
    {"key": "qa-quality", "label": "品質観点", "href": "/qa-quality", "disabled": False,
     "icon": '<path d="M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6l7-3z"/><path d="M9 12l2 2 4-5"/>'},
    {"key": "viewpoints", "label": "観点管理", "href": "/viewpoints", "disabled": False,
     "icon": '<path d="M5 4h14v16H5z"/><path d="M8 8h8M8 12h8M8 16h5"/>'},
]
