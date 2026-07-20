"""Application factory."""
import logging
import os

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import get_config
from .extensions import csrf, db, limiter, login_manager, migrate


def create_app(config_object=None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object or get_config())

    logging.basicConfig(
        level=app.config.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    # Trust one proxy hop (load balancer / ngrok) for correct scheme & host.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Load voice scripts once at startup (read-only at request time).
    import json
    scripts_path = os.environ.get("CALL_SCRIPTS_PATH", "call_scripts.json")
    if os.path.exists(scripts_path):
        with open(scripts_path) as fh:
            app.config["CALL_SCRIPTS"] = json.load(fh)
    else:
        app.config["CALL_SCRIPTS"] = {
            "default": "Hello, this is an automated call from our service."
        }

    _init_extensions(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    register_health(app)

    return app


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)

    # Import models so Alembic/`flask db` can see them.
    from . import models  # noqa: F401

    from .models import User

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))


def _register_blueprints(app: Flask) -> None:
    from .auth.routes import auth_bp
    from .web.dashboard import dashboard_bp
    from .web.api import api_bp
    from .web.webhooks import webhooks_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(webhooks_bp, url_prefix="/webhooks")

    # Twilio posts to webhooks without a CSRF token; we verify those
    # requests via X-Twilio-Signature instead (see webhooks blueprint).
    csrf.exempt(webhooks_bp)


def _register_error_handlers(app: Flask) -> None:
    from flask import jsonify

    @app.errorhandler(429)
    def ratelimit_handler(_e):
        return jsonify(error="Rate limit exceeded. Try again later."), 429

    @app.errorhandler(413)
    def too_large(_e):
        return jsonify(error="Uploaded file too large."), 413


# Health endpoints live on the bare app so they don't require auth.
def register_health(app: Flask) -> None:
    from flask import jsonify
    from sqlalchemy import text

    @app.get("/healthz")
    def healthz():
        return jsonify(status="ok"), 200

    @app.get("/readyz")
    def readyz():
        try:
            db.session.execute(text("SELECT 1"))
            return jsonify(status="ready"), 200
        except Exception:
            return jsonify(status="not-ready"), 503
