from __future__ import annotations

import sys
import time
from pathlib import Path

from flask import Flask

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def create_app() -> Flask:
    from web.routes import (
        api_v1,
        auth,
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
        usage,
        viewpoints,
    )
    from web.security import add_security_headers, csrf_guard, localhost_guard

    app = Flask(
        __name__,
        template_folder=str(_ROOT / "templates"),
        static_folder=str(_ROOT / "static"),
    )
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    _ver = str(int(time.time()))
    app.jinja_env.globals["_ver"] = _ver

    # 利用者認証（メール自己申告 ＋ テナント選択）。既定 OFF で現行挙動を維持。
    from pathlib import Path as _Path

    from web.auth import auth_enabled
    from web.auth.guard import auth_guard
    from web.auth.store import load_or_create_secret_key

    app.secret_key = load_or_create_secret_key(_Path(app.instance_path) / "auth")

    @app.context_processor
    def _inject_auth_context() -> dict[str, object]:
        """テンプレートへ認証状態を注入する（アバター表示制御に使用）。

        認証 OFF（既定）では current_user_email=None となり、topbar のアバターは
        テンプレート側で描画されない（現行の見た目を維持）。
        """
        from web.auth import auth_enabled as _enabled
        from web.auth.session import current_user_email

        enabled = _enabled()
        return {
            "auth_enabled": enabled,
            "current_user_email": current_user_email() if enabled else None,
        }

    app.before_request(localhost_guard)
    app.before_request(csrf_guard)
    if auth_enabled():
        app.before_request(auth_guard)
    app.after_request(add_security_headers)
    app.register_blueprint(auth.bp)
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
    app.register_blueprint(usage.bp)
    app.register_blueprint(viewpoints.bp)

    from web.services.viewpoint_store import get_viewpoint_store

    get_viewpoint_store()

    from web.services.scheduler import start_scheduler

    start_scheduler()
    return app
