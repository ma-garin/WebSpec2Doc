from __future__ import annotations

import sys
from pathlib import Path

from flask import Flask

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def create_app() -> Flask:
    from web.routes import crawl, discover, history, login, pages, report, settings, site
    from web.security import csrf_guard

    app = Flask(
        __name__,
        template_folder=str(_ROOT / "templates"),
        static_folder=str(_ROOT / "static"),
    )
    app.before_request(csrf_guard)
    app.register_blueprint(pages.bp)
    app.register_blueprint(discover.bp)
    app.register_blueprint(site.bp)
    app.register_blueprint(login.bp)
    app.register_blueprint(report.bp)
    app.register_blueprint(history.bp)
    app.register_blueprint(settings.bp)
    app.register_blueprint(crawl.bp)
    return app
