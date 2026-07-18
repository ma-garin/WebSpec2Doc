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
TEST_DESIGN_SETTINGS_FILE = Path(
    os.environ.get("TEST_DESIGN_SETTINGS_FILE", "instance/test_design_settings.json")
)
SCREEN_ROW_RE = re.compile(r"^\|\s*\d+\s*\|")
ENV_FILE = Path(".env")
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
DISCOVER_TIMEOUT_SEC = 180
LOGIN_FINISH_TIMEOUT_SEC = 60

ALLOWED_FORMATS = ("md", "html", "excel", "pdf", "json")
DOMAIN_RE = re.compile(r"^[A-Za-z0-9._:\[\]-]{1,253}$")
ENV_KEY_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
MAX_DEPTH = 5
MAX_PAGES_LIMIT = 300

_PREVIEW_MIME = {
    ".html": "text/html; charset=utf-8",
    ".pdf": "application/pdf",
    ".json": "application/json; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".mmd": "text/plain; charset=utf-8",
    ".png": "image/png",
}

PORT = int(os.environ.get("WEBSPEC2DOC_PORT", "8765"))
