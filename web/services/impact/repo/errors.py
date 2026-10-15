"""影響度分析のリポジトリ層が投げる利用者向けエラー。"""


class ImpactError(Exception):
    """message は利用者向けの日本語＋次の行動。status は 400/403/404/409。"""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status
