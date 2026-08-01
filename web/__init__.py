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


class _DevVersion:
    """テンプレートに埋め込むたびに現在時刻を返す（開発時のキャッシュ破棄用）。

    `?v={{ _ver }}` は文字列化して埋め込まれるので、__str__ を毎回変えれば
    リロードのたびに別 URL になり、ブラウザが古い JS/CSS を使い続けなくなる。
    """

    def __str__(self) -> str:
        return str(int(time.time()))


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
        app.jinja_env.auto_reload = True
        app.jinja_env.globals["_ver"] = _DevVersion()
    else:
        app.jinja_env.globals["_ver"] = str(int(time.time()))
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
