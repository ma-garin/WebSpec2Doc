from __future__ import annotations

import sys
from pathlib import Path

from flask import Flask

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def create_app() -> Flask:
    from web.routes import (
        api_v1,
        auto_run,
        crawl,
        discover,
        history,
        login,
        pages,
        qa_process,
        report,
        review,
        schedule,
        settings,
        site,
        traceability,
    )
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
    app.register_blueprint(qa_process.bp)
    app.register_blueprint(history.bp)
    app.register_blueprint(settings.bp)
    app.register_blueprint(crawl.bp)
    app.register_blueprint(auto_run.bp)
    app.register_blueprint(review.bp)
    app.register_blueprint(schedule.bp)
    app.register_blueprint(api_v1.bp)
    app.register_blueprint(traceability.traceability_bp)

    from web.services.scheduler import start_scheduler

    start_scheduler()
    return app
