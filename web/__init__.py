from __future__ import annotations

import sys
from pathlib import Path

from flask import Flask

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def create_app() -> Flask:
    from web.routes import pages
    from web.security import csrf_guard

    app = Flask(
        __name__,
        template_folder=str(_ROOT / "templates"),
        static_folder=str(_ROOT / "static"),
    )
    app.before_request(csrf_guard)
    app.register_blueprint(pages.bp)
    return app
