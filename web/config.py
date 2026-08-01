from __future__ import annotations

import os
import re
from pathlib import Path

OUTPUT_DIR = Path("output")
QA_VIEWPOINTS_CSV = Path(os.environ.get("QA_VIEWPOINTS_CSV", "data/qa_viewpoints_summary.csv"))
VIEWPOINTS_DB = Path(os.environ.get("VIEWPOINTS_DB", "instance/viewpoints.db"))
VIEWPOINT_TEMPLATES_DIR = Path(
    os.environ.get("VIEWPOINT_TEMPLATES_DIR", "data/viewpoint_templates")
)
DATA_DIR = Path(os.environ.get("WEBSPEC2DOC_DATA_DIR", "data"))
TEST_DESIGN_SETTINGS_FILE = Path(
    os.environ.get("TEST_DESIGN_SETTINGS_FILE", "instance/test_design_settings.json")
)
SCREEN_ROW_RE = re.compile(r"^\|\s*\d+\s*\|")
ENV_FILE = Path(".env")
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
DISCOVER_TIMEOUT_SEC = 180
LOGIN_FINISH_TIMEOUT_SEC = 60

#: 同梱サンプルレポート（P3-1 ゼロ待ちサンプル）の実体。同梱デモサイトを解析した
#: 事前生成の成果物で、クロールを待たずにレポートの仕上がりを見せるために使う。
SAMPLE_REPORT_DIR = Path("demo/sample_report")
#: サンプルを開いたときに使う予約ドメイン。利用者自身の解析結果と混ざらないよう、
#: 解析履歴の一覧からは除外する（web/routes/history.py）。
SAMPLE_DOMAIN = "sample.webspec2doc.local"

ALLOWED_FORMATS = ("md", "html", "excel", "pdf", "json")
DOMAIN_RE = re.compile(r"^[A-Za-z0-9._:\[\]-]{1,253}$")
ENV_KEY_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
MAX_DEPTH = 10
MAX_PAGES_LIMIT = 500
#: クロールの並列数の上限。src/main.py の MAX_PARALLELISM と同じ値にする
#: （GUI は subprocess で CLI を呼ぶため、片方だけ上げても実効値は上がらない）。
MAX_PARALLELISM = 8

_PREVIEW_MIME = {
    ".html": "text/html; charset=utf-8",
    ".pdf": "application/pdf",
    ".json": "application/json; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".mmd": "text/plain; charset=utf-8",
    ".png": "image/png",
}

PORT = int(os.environ.get("WEBSPEC2DOC_PORT", "8765"))
