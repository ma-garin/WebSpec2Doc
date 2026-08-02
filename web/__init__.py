from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from flask import Flask

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def create_app() -> Flask:
    from web.auth import auth_guard, ensure_secret_key
    from web.routes import (
        account,
        admin,
        api_v1,
        api_v1_schedule,
        auto_run,
        autorun_report,
        autorun_stages,
        crawl,
        discover,
        history,
        llm_chat,
        login,
        pages,
        qa_process,
        report,
        review,
        runs,
        schedule,
        settings,
        site,
        traceability,
        usage,
        viewpoints,
    )
    from web.routes import (
        metrics as metrics_routes,
    )
    from web.routes import (
        oidc as oidc_routes,
    )
    from web.security import add_security_headers, csrf_guard, localhost_guard

    app = Flask(
        __name__,
        template_folder=str(_ROOT / "templates"),
        static_folder=str(_ROOT / "static"),
    )
    app.config["TESTING"] = os.environ.get("FLASK_TESTING", "").strip() == "1"
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    ensure_secret_key(app, _ROOT / "instance")
    # 開発時はテンプレートと静的ファイルのキャッシュを外す。
    # 既定（本番）は起動時に固定した _ver を配り、ブラウザにキャッシュさせる。
    # 開発時は毎リクエストで _ver を作り直し、サーバを再起動せずに JS/CSS の
    # 変更が反映されるようにする（再起動待ちが実測で 1 回 1〜2 分かかるため）。
    dev_reload = os.environ.get("WEBSPEC2DOC_TEMPLATES_AUTO_RELOAD", "").strip() == "1"
    app.config["TEMPLATES_AUTO_RELOAD"] = dev_reload
    if dev_reload:
        # 観点カタログ（JSON）も読み直す。Jinja2 テンプレートだけを再読込して
        # 観点定義を固定したままにすると、JSON を編集しても画面が変わらず、
        # 変数名から「観点も再読込される」と誤解したまま原因を探すことになる。
        @app.before_request
        def _reload_viewpoint_catalogs() -> None:
            from web.services.viewpoint_blueprints import reload_catalogs

            reload_catalogs()
    app.jinja_env.auto_reload = dev_reload
    app.jinja_env.globals["_ver"] = str(int(time.time()))
    if dev_reload:
        # 開発時はレンダリングのたびに値を差し替える。Jinja のグローバルは
        # 起動時に固定されるため、context_processor で毎回上書きする。
        @app.context_processor
        def _dev_cache_buster() -> dict:
            return {"_ver": str(int(time.time()))}
    app.before_request(localhost_guard)
    app.before_request(csrf_guard)
    app.before_request(auth_guard)
    app.after_request(add_security_headers)

    @app.context_processor
    def _auth_template_context() -> dict:
        from flask import g

        return {"auth_user": getattr(g, "auth_user", None)}

    app.register_blueprint(account.bp)
    app.register_blueprint(admin.bp)
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
    app.register_blueprint(runs.bp)
    app.register_blueprint(schedule.bp)
    app.register_blueprint(api_v1.bp)
    app.register_blueprint(api_v1_schedule.bp)
    app.register_blueprint(metrics_routes.bp)
    app.register_blueprint(oidc_routes.bp)
    app.register_blueprint(traceability.traceability_bp)
    app.register_blueprint(usage.bp)
    app.register_blueprint(llm_chat.bp)
    app.register_blueprint(autorun_stages.bp)
    app.register_blueprint(autorun_report.bp)
    app.register_blueprint(viewpoints.bp)

    from web.services.viewpoint_store import get_viewpoint_store

    get_viewpoint_store()

    from web.services.scheduler import start_scheduler

    start_scheduler()
    return app
