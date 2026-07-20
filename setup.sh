#!/usr/bin/env bash
# setup.sh — scaffolds the production-grade Call Automation project.
# Run ONCE from inside your cloned repo:   bash setup.sh
set -euo pipefail
echo ">> Writing project files..."
mkdir -p ".github/workflows"
mkdir -p "app"
mkdir -p "app/auth"
mkdir -p "app/services"
mkdir -p "app/static/css"
mkdir -p "app/static/js"
mkdir -p "app/tasks"
mkdir -p "app/telephony"
mkdir -p "app/templates"
mkdir -p "app/web"
mkdir -p "tests"
cat > ".env.example" << '__CAS_FILE_EOF_9f3a__'
# ── Flask ─────────────────────────────────────────────
FLASK_CONFIG=production            # development | production | testing
SECRET_KEY=change-me-use-openssl-rand-hex-32

# ── Database (use Postgres in prod) ───────────────────
DATABASE_URL=postgresql+psycopg2://cas:cas@localhost:5432/call_automation
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20

# ── Redis (Celery broker + rate-limit + cache) ────────
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# ── Twilio ────────────────────────────────────────────
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+1234567890
# Public base URL Twilio can reach (ngrok in dev, real domain in prod)
PUBLIC_BASE_URL=https://your-domain.example.com
# Number to bridge to when recipient presses 2 (forward)
FORWARD_TO_NUMBER=+1987654321

# ── Google Sheets (service-account JSON, single line) ─
GOOGLE_SHEETS_CREDENTIALS={"type":"service_account",...}

# ── Calling policy / compliance ───────────────────────
CALL_INTERVAL_SECONDS=5
CALLING_WINDOW_START=09:00          # local time, no calls before
CALLING_WINDOW_END=20:00            # local time, no calls after
CALLING_TIMEZONE=Asia/Kolkata

# ── Bootstrap admin (created on first migrate) ────────
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-me-strong
__CAS_FILE_EOF_9f3a__
cat > ".github/workflows/ci.yml" << '__CAS_FILE_EOF_9f3a__'
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: pytest -q
        env:
          FLASK_CONFIG: testing
__CAS_FILE_EOF_9f3a__
cat > ".gitignore" << '__CAS_FILE_EOF_9f3a__'
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/

# Env & secrets
.env
*.env
!.env.example
service_account*.json

# Databases / instance
instance/
*.db
*.sqlite3

# Uploads
uploads/

# Test / coverage
.pytest_cache/
.coverage
htmlcov/

# OS / editor
.DS_Store
.idea/
.vscode/
__CAS_FILE_EOF_9f3a__
cat > "Dockerfile" << '__CAS_FILE_EOF_9f3a__'
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[postgres]"

COPY . .

EXPOSE 8000
CMD ["gunicorn", "wsgi:app", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
__CAS_FILE_EOF_9f3a__
cat > "app/__init__.py" << '__CAS_FILE_EOF_9f3a__'
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
__CAS_FILE_EOF_9f3a__
cat > "app/auth/__init__.py" << '__CAS_FILE_EOF_9f3a__'

__CAS_FILE_EOF_9f3a__
cat > "app/auth/forms.py" << '__CAS_FILE_EOF_9f3a__'
from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Length


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(max=80)])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Log in")
__CAS_FILE_EOF_9f3a__
cat > "app/auth/routes.py" << '__CAS_FILE_EOF_9f3a__'
"""Authentication blueprint."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db, limiter
from ..models import User
from .forms import LoginForm

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.scalar(
            db.select(User).filter_by(username=form.username.data)
        )
        if user and user.check_password(form.password.data) and user.is_active:
            login_user(user)
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard.index"))
        flash("Invalid username or password.", "error")

    return render_template("login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("auth.login"))
__CAS_FILE_EOF_9f3a__
cat > "app/cli.py" << '__CAS_FILE_EOF_9f3a__'
"""Custom flask CLI commands: create admin, load scripts."""
import json
import os

import click
from flask import Flask

from .extensions import db
from .models import User


def register_cli(app: Flask) -> None:
    @app.cli.command("create-admin")
    def create_admin():
        """Create the bootstrap admin from ADMIN_USERNAME / ADMIN_PASSWORD."""
        username = os.environ.get("ADMIN_USERNAME", "admin")
        password = os.environ.get("ADMIN_PASSWORD")
        if not password:
            raise click.ClickException("Set ADMIN_PASSWORD in the environment first.")
        if db.session.scalar(db.select(User).filter_by(username=username)):
            click.echo(f"User '{username}' already exists.")
            return
        user = User(username=username, role="admin")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Created admin '{username}'.")
__CAS_FILE_EOF_9f3a__
cat > "app/config.py" << '__CAS_FILE_EOF_9f3a__'
"""Configuration objects. Production fails fast if secrets are missing."""
import os


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable '{name}' is not set")
    return value


class BaseConfig:
    # --- Flask ---
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key")
    WTF_CSRF_ENABLED = True

    # --- Database ---
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///instance/call_automation.db"
    )
    # Connection-pool tuning only applies to real servers (Postgres), not SQLite.
    if SQLALCHEMY_DATABASE_URI.startswith("postgresql"):
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_size": int(os.environ.get("DB_POOL_SIZE", 10)),
            "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", 20)),
            "pool_recycle": 300,
            "pool_pre_ping": True,
        }
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # --- Redis / rate limiting ---
    REDIS_URL = os.environ.get("REDIS_URL")
    RATELIMIT_STORAGE_URI = REDIS_URL or "memory://"

    # --- Twilio ---
    TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
    TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")
    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")
    FORWARD_TO_NUMBER = os.environ.get("FORWARD_TO_NUMBER", "")

    # --- Google Sheets ---
    GOOGLE_SHEETS_CREDENTIALS = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")

    # --- Calling policy ---
    CALL_INTERVAL_SECONDS = int(os.environ.get("CALL_INTERVAL_SECONDS", 5))
    CALLING_WINDOW_START = os.environ.get("CALLING_WINDOW_START", "09:00")
    CALLING_WINDOW_END = os.environ.get("CALLING_WINDOW_END", "20:00")
    CALLING_TIMEZONE = os.environ.get("CALLING_TIMEZONE", "Asia/Kolkata")

    # --- Uploads ---
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB cap on uploads
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "uploads")

    # --- Celery ---
    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
    CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)

    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    LOG_LEVEL = "DEBUG"


class TestingConfig(BaseConfig):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    RATELIMIT_ENABLED = False


class ProductionConfig(BaseConfig):
    DEBUG = False

    def __init__(self):
        # Fail fast: never run prod with insecure defaults.
        self.SECRET_KEY = _require("SECRET_KEY")
        self.SQLALCHEMY_DATABASE_URI = _require("DATABASE_URL")
        self.TWILIO_ACCOUNT_SID = _require("TWILIO_ACCOUNT_SID")
        self.TWILIO_AUTH_TOKEN = _require("TWILIO_AUTH_TOKEN")
        self.TWILIO_PHONE_NUMBER = _require("TWILIO_PHONE_NUMBER")
        self.PUBLIC_BASE_URL = _require("PUBLIC_BASE_URL")


_CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config():
    name = os.environ.get("FLASK_CONFIG", "development").lower()
    cfg = _CONFIG_MAP.get(name, DevelopmentConfig)
    return cfg() if isinstance(cfg, type) and name == "production" else cfg
__CAS_FILE_EOF_9f3a__
cat > "app/extensions.py" << '__CAS_FILE_EOF_9f3a__'
"""Shared extension instances, initialised in the app factory."""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf import CSRFProtect
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
csrf = CSRFProtect()
login_manager = LoginManager()
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day", "50 per hour"])

login_manager.login_view = "auth.login"
login_manager.login_message_category = "warning"
__CAS_FILE_EOF_9f3a__
cat > "app/models.py" << '__CAS_FILE_EOF_9f3a__'
"""Database models."""
from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import Index
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow() -> datetime:
    """Timezone-aware UTC now (utcnow() is deprecated in 3.12+)."""
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="operator")  # operator | admin
    is_active_flag = db.Column(db.Boolean, default=True)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self) -> bool:  # used by Flask-Login
        return bool(self.is_active_flag)


class CallQueue(TimestampMixin, db.Model):
    __tablename__ = "call_queue"
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), nullable=False, index=True)
    caller_name = db.Column(db.String(100))
    priority = db.Column(db.Integer, default=1)
    # queued | dialing | in_progress | completed | failed | retry | skipped
    status = db.Column(db.String(20), default="queued", index=True)
    assigned_script = db.Column(db.String(50), default="default")
    attempts = db.Column(db.Integer, default=0)
    max_attempts = db.Column(db.Integer, default=3)
    next_attempt_at = db.Column(db.DateTime(timezone=True))

    logs = db.relationship("CallLog", back_populates="queue_item", lazy="dynamic")

    __table_args__ = (
        Index("idx_queue_dialable", "status", "priority", "next_attempt_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "phone_number": self.phone_number,
            "caller_name": self.caller_name,
            "priority": self.priority,
            "status": self.status,
            "assigned_script": self.assigned_script,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
        }


class CallLog(TimestampMixin, db.Model):
    __tablename__ = "call_logs"
    id = db.Column(db.Integer, primary_key=True)
    queue_item_id = db.Column(
        db.Integer, db.ForeignKey("call_queue.id", ondelete="SET NULL"), index=True
    )
    phone_number = db.Column(db.String(20), nullable=False, index=True)
    caller_name = db.Column(db.String(100))
    call_sid = db.Column(db.String(64), unique=True, index=True)
    # Mirrors Twilio statuses: queued|ringing|in-progress|completed|busy|no-answer|failed|canceled
    call_status = db.Column(db.String(20), nullable=False, default="queued")
    response = db.Column(db.String(20))  # accepted | forwarded | none
    start_time = db.Column(db.DateTime(timezone=True))
    end_time = db.Column(db.DateTime(timezone=True))
    duration = db.Column(db.Integer)
    notes = db.Column(db.Text)

    queue_item = db.relationship("CallQueue", back_populates="logs")

    __table_args__ = (
        Index("idx_log_phone_created", "phone_number", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "queue_item_id": self.queue_item_id,
            "phone_number": self.phone_number,
            "caller_name": self.caller_name,
            "call_sid": self.call_sid,
            "call_status": self.call_status,
            "response": self.response,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration": self.duration,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DNCEntry(TimestampMixin, db.Model):
    """Do-Not-Call list. Numbers here are never dialed."""
    __tablename__ = "dnc_list"
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    reason = db.Column(db.String(120))
__CAS_FILE_EOF_9f3a__
cat > "app/services/__init__.py" << '__CAS_FILE_EOF_9f3a__'

__CAS_FILE_EOF_9f3a__
cat > "app/services/call_service.py" << '__CAS_FILE_EOF_9f3a__'
"""Placing calls + reacting to Twilio status callbacks."""
import logging
from datetime import datetime, timezone

from flask import current_app, url_for

from ..extensions import db
from ..models import CallLog, CallQueue
from ..telephony.client import get_twilio_client
from .compliance import can_call

logger = logging.getLogger(__name__)


def place_call(item: CallQueue) -> CallLog | None:
    """Place one outbound call for a claimed queue item.
    Creates the CallLog first so the webhook URLs can reference its id."""
    allowed, reason = can_call(item.phone_number)
    if not allowed:
        item.status = "skipped"
        db.session.add(
            CallLog(
                queue_item_id=item.id,
                phone_number=item.phone_number,
                caller_name=item.caller_name,
                call_status="skipped",
                notes=reason,
            )
        )
        db.session.commit()
        logger.info("Skipped %s: %s", item.phone_number, reason)
        return None

    log = CallLog(
        queue_item_id=item.id,
        phone_number=item.phone_number,
        caller_name=item.caller_name,
        call_status="queued",
    )
    db.session.add(log)
    db.session.commit()

    try:
        client = get_twilio_client()
        call = client.calls.create(
            to=item.phone_number,
            from_=current_app.config["TWILIO_PHONE_NUMBER"],
            url=url_for("webhooks.voice_greeting", log_id=log.id,
                        script=item.assigned_script, _external=True),
            method="POST",
            status_callback=url_for("webhooks.status_callback", log_id=log.id,
                                    _external=True),
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            status_callback_method="POST",
        )
        log.call_sid = call.sid
        log.call_status = call.status  # real Twilio status, not a fake "Connected"
        log.start_time = datetime.now(timezone.utc)
        item.status = "in_progress"
        db.session.commit()
        logger.info("Call placed to %s sid=%s", item.phone_number, call.sid)
        return log
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to place call to %s: %s", item.phone_number, exc)
        log.call_status = "failed"
        log.notes = str(exc)[:500]
        _handle_failure(item)
        db.session.commit()
        return None


def _handle_failure(item: CallQueue) -> None:
    from datetime import timedelta
    if item.attempts < item.max_attempts:
        item.status = "retry"
        item.next_attempt_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    else:
        item.status = "failed"


# Twilio call statuses that mean "the attempt is over".
_TERMINAL = {"completed", "busy", "no-answer", "failed", "canceled"}


def apply_status_callback(log: CallLog, twilio_status: str, duration: int | None) -> None:
    log.call_status = twilio_status
    if duration is not None:
        log.duration = duration
    if twilio_status in _TERMINAL:
        log.end_time = datetime.now(timezone.utc)
        item = log.queue_item
        if item and item.status not in ("completed",):
            if twilio_status == "completed":
                item.status = "completed"
            else:
                _handle_failure(item)
    db.session.commit()


def apply_dtmf_response(log: CallLog, digit: str) -> str:
    """Record what the recipient pressed. Returns 'accept'|'forward'|'none'."""
    if digit == "1":
        log.response = "accepted"
        if log.queue_item:
            log.queue_item.status = "completed"
        db.session.commit()
        return "accept"
    if digit == "2":
        log.response = "forwarded"
        if log.queue_item:
            log.queue_item.status = "completed"
        db.session.commit()
        return "forward"
    log.response = "none"
    db.session.commit()
    return "none"
__CAS_FILE_EOF_9f3a__
cat > "app/services/compliance.py" << '__CAS_FILE_EOF_9f3a__'
"""Compliance checks: DNC list + calling-window enforcement.
Real telephony (TCPA in US, TRAI/DLT in India) requires these."""
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

import phonenumbers
from flask import current_app

from ..extensions import db
from ..models import DNCEntry

logger = logging.getLogger(__name__)


def normalize_number(raw: str, default_region: str = "IN") -> str | None:
    """Return E.164 (+9199...) or None if invalid."""
    try:
        parsed = phonenumbers.parse(raw, default_region)
        if not phonenumbers.is_valid_number(parsed):
            return None
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        return None


def is_dnc(phone_number: str) -> bool:
    return db.session.scalar(
        db.select(DNCEntry.id).filter_by(phone_number=phone_number)
    ) is not None


def add_to_dnc(phone_number: str, reason: str = "user opt-out") -> None:
    if not is_dnc(phone_number):
        db.session.add(DNCEntry(phone_number=phone_number, reason=reason))
        db.session.commit()


def _parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


def within_calling_window(now: datetime | None = None) -> bool:
    tz = ZoneInfo(current_app.config["CALLING_TIMEZONE"])
    now = now or datetime.now(tz)
    start = _parse_hhmm(current_app.config["CALLING_WINDOW_START"])
    end = _parse_hhmm(current_app.config["CALLING_WINDOW_END"])
    return start <= now.timetz().replace(tzinfo=None) <= end


def can_call(phone_number: str) -> tuple[bool, str]:
    """Single gate the dialer must pass before placing a call."""
    if is_dnc(phone_number):
        return False, "number on do-not-call list"
    if not within_calling_window():
        return False, "outside calling window"
    return True, "ok"
__CAS_FILE_EOF_9f3a__
cat > "app/services/queue_service.py" << '__CAS_FILE_EOF_9f3a__'
"""Queue loading + atomic claim of the next dialable row."""
import csv
import logging
from datetime import datetime, timezone

from sqlalchemy import or_

from ..extensions import db
from ..models import CallQueue
from .compliance import normalize_number

logger = logging.getLogger(__name__)

_PRIORITY_MAP = {"high": 3, "medium": 2, "low": 1}


def _to_priority(value) -> int:
    if isinstance(value, str):
        mapped = _PRIORITY_MAP.get(value.strip().lower())
        if mapped:
            return mapped
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def load_from_rows(rows: list[dict]) -> int:
    """Insert validated rows. Invalid phone numbers are skipped, not dialed."""
    inserted = 0
    for row in rows:
        number = normalize_number(str(row.get("phone_number", "")))
        if not number:
            logger.warning("Skipping invalid phone number: %r", row.get("phone_number"))
            continue
        db.session.add(
            CallQueue(
                phone_number=number,
                caller_name=str(row.get("caller_name", "")).strip(),
                priority=_to_priority(row.get("priority", 1)),
                assigned_script=str(row.get("script", "default")).strip() or "default",
            )
        )
        inserted += 1
    db.session.commit()
    logger.info("Loaded %d valid rows into queue", inserted)
    return inserted


def load_from_csv(path: str) -> int:
    with open(path, newline="") as f:
        return load_from_rows(list(csv.DictReader(f)))


def claim_next() -> CallQueue | None:
    """Atomically claim the next dialable row so two workers never grab the same one.
    Uses SELECT ... FOR UPDATE SKIP LOCKED on Postgres; falls back gracefully on SQLite."""
    now = datetime.now(timezone.utc)
    query = (
        db.select(CallQueue)
        .where(
            CallQueue.status.in_(["queued", "retry"]),
            or_(CallQueue.next_attempt_at.is_(None), CallQueue.next_attempt_at <= now),
        )
        .order_by(CallQueue.priority.desc(), CallQueue.created_at.asc())
        .limit(1)
    )
    if db.engine.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)

    item = db.session.scalar(query)
    if item is None:
        return None

    item.status = "dialing"
    item.attempts += 1
    db.session.commit()
    return item
__CAS_FILE_EOF_9f3a__
cat > "app/services/sheets_service.py" << '__CAS_FILE_EOF_9f3a__'
"""Optional Google Sheets queue source."""
import json
import logging

from flask import current_app

logger = logging.getLogger(__name__)


def _client():
    creds_json = current_app.config.get("GOOGLE_SHEETS_CREDENTIALS")
    if not creds_json:
        raise RuntimeError("Google Sheets credentials not configured")
    import gspread
    from google.oauth2.service_account import Credentials

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    return gspread.authorize(creds)


def read_queue(sheet_url: str, worksheet_name: str | None = None) -> list[dict]:
    sheet = _client().open_by_url(sheet_url)
    ws = sheet.worksheet(worksheet_name) if worksheet_name else sheet.get_worksheet(0)
    records = ws.get_all_records()
    return [r for r in records if str(r.get("phone_number", "")).strip()]
__CAS_FILE_EOF_9f3a__
cat > "app/services/stats.py" << '__CAS_FILE_EOF_9f3a__'
"""Read-only aggregates for the dashboard."""
from sqlalchemy import func

from ..extensions import db
from ..models import CallLog, CallQueue


def queue_statistics() -> dict:
    rows = db.session.execute(
        db.select(CallQueue.status, func.count(CallQueue.id)).group_by(CallQueue.status)
    ).all()
    by_status = {status: count for status, count in rows}
    total = sum(by_status.values())
    return {
        "total": total,
        "queued": by_status.get("queued", 0),
        "dialing": by_status.get("dialing", 0),
        "in_progress": by_status.get("in_progress", 0),
        "completed": by_status.get("completed", 0),
        "failed": by_status.get("failed", 0),
        "retry": by_status.get("retry", 0),
        "skipped": by_status.get("skipped", 0),
    }


def recent_calls(limit: int = 10) -> list[dict]:
    logs = db.session.scalars(
        db.select(CallLog).order_by(CallLog.created_at.desc()).limit(limit)
    ).all()
    return [log.to_dict() for log in logs]
__CAS_FILE_EOF_9f3a__
cat > "app/static/css/dashboard.css" << '__CAS_FILE_EOF_9f3a__'
:root{--bg:#0f172a;--card:#1e293b;--ink:#e2e8f0;--accent:#6366f1;--ok:#22c55e;--err:#ef4444}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,sans-serif;background:var(--bg);color:var(--ink)}
.topbar{display:flex;justify-content:space-between;align-items:center;padding:1rem 1.5rem;background:#111827}
.topbar a{color:var(--ink)}.brand{font-weight:700}
.container{max-width:960px;margin:0 auto;padding:1.5rem}
.card{background:var(--card);border-radius:12px;padding:1rem;margin-bottom:1rem}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:1rem}
.stat{text-align:center}.stat-num{display:block;font-size:1.8rem;font-weight:700}
.stat-label{font-size:.85rem;opacity:.7}
.btn{padding:.5rem 1rem;border:0;border-radius:8px;background:#334155;color:var(--ink);cursor:pointer}
.btn-primary{background:var(--accent)}.input{display:block;width:100%;margin:.4rem 0;padding:.5rem}
.table{width:100%;border-collapse:collapse}.table th,.table td{padding:.5rem;border-bottom:1px solid #334155;text-align:left}
.flash{padding:.6rem 1rem;border-radius:8px;margin-bottom:.6rem}
.flash-success{background:rgba(34,197,94,.15)}.flash-error{background:rgba(239,68,68,.15)}
.flash-info,.flash-warning{background:rgba(99,102,241,.15)}
.actions{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
__CAS_FILE_EOF_9f3a__
cat > "app/static/js/dashboard.js" << '__CAS_FILE_EOF_9f3a__'
// Poll queue status every 5s and update the stat cards.
async function refresh() {
  try {
    const res = await fetch("/api/queue-status");
    if (!res.ok) return;
    const s = await res.json();
    for (const key of Object.keys(s)) {
      const el = document.getElementById("stat-" + key);
      if (el) el.textContent = s[key];
    }
  } catch (_) { /* ignore transient errors */ }
}
if (document.getElementById("stat-total")) setInterval(refresh, 5000);
__CAS_FILE_EOF_9f3a__
cat > "app/tasks/__init__.py" << '__CAS_FILE_EOF_9f3a__'

__CAS_FILE_EOF_9f3a__
cat > "app/tasks/call_tasks.py" << '__CAS_FILE_EOF_9f3a__'
"""Background dialing — replaces the in-worker daemon thread.
A single beat-scheduled task drains the queue one call at a time,
so two web workers can never start duplicate dialers."""
import logging

from ..extensions import db
from ..models import CallQueue
from ..services.call_service import place_call
from ..services.queue_service import claim_next
from .celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="tasks.dial_next")
def dial_next() -> str:
    item = claim_next()
    if item is None:
        return "queue empty"
    place_call(item)
    return f"dialed {item.phone_number}"


@celery.task(name="tasks.drain_queue")
def drain_queue() -> str:
    """Kick a dial for every currently-dialable row."""
    pending = db.session.scalar(
        db.select(db.func.count(CallQueue.id)).where(
            CallQueue.status.in_(["queued", "retry"])
        )
    )
    for _ in range(pending or 0):
        dial_next.delay()
    return f"queued {pending or 0} dials"
__CAS_FILE_EOF_9f3a__
cat > "app/tasks/celery_app.py" << '__CAS_FILE_EOF_9f3a__'
"""Celery app bound to the Flask app context."""
from celery import Celery

from .. import create_app


def make_celery() -> Celery:
    flask_app = create_app()
    celery = Celery(
        flask_app.import_name,
        broker=flask_app.config["CELERY_BROKER_URL"],
        backend=flask_app.config["CELERY_RESULT_BACKEND"],
    )

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    celery.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
    )
    return celery


celery = make_celery()
__CAS_FILE_EOF_9f3a__
cat > "app/telephony/__init__.py" << '__CAS_FILE_EOF_9f3a__'

__CAS_FILE_EOF_9f3a__
cat > "app/telephony/client.py" << '__CAS_FILE_EOF_9f3a__'
"""Thin wrapper around the Twilio REST client."""
import logging

from flask import current_app
from twilio.rest import Client

logger = logging.getLogger(__name__)


def get_twilio_client() -> Client:
    sid = current_app.config["TWILIO_ACCOUNT_SID"]
    token = current_app.config["TWILIO_AUTH_TOKEN"]
    if not sid or not token:
        raise RuntimeError("Twilio credentials are not configured")
    return Client(sid, token)
__CAS_FILE_EOF_9f3a__
cat > "app/telephony/twiml.py" << '__CAS_FILE_EOF_9f3a__'
"""TwiML generation. These XML docs are served from real HTTP endpoints
(see web/webhooks.py) so Twilio can fetch them — the old data: URL approach
never worked because Twilio fetches call instructions over HTTP."""
from flask import current_app, url_for
from twilio.twiml.voice_response import Gather, VoiceResponse


def build_greeting_twiml(script_text: str, log_id: int) -> str:
    """Greeting + DTMF gather. Action posts back to our webhook with the log id."""
    response = VoiceResponse()
    gather = Gather(
        input="dtmf",
        num_digits=1,
        timeout=8,
        action=url_for("webhooks.call_response", log_id=log_id, _external=True),
        method="POST",
    )
    gather.say(script_text, voice="alice")
    gather.say("Press 1 to accept, or 2 to be forwarded to an agent.", voice="alice")
    response.append(gather)
    # If no input, repeat once by redirecting back to the greeting.
    response.say("We did not receive any input. Goodbye.", voice="alice")
    response.hangup()
    return str(response)


def build_accept_twiml() -> str:
    response = VoiceResponse()
    response.say("Thank you. Your call has been accepted. Goodbye.", voice="alice")
    response.hangup()
    return str(response)


def build_forward_twiml() -> str:
    response = VoiceResponse()
    forward_to = current_app.config.get("FORWARD_TO_NUMBER")
    if forward_to:
        response.say("Connecting you to an agent now.", voice="alice")
        response.dial(forward_to)
    else:
        response.say("Forwarding is not configured. Goodbye.", voice="alice")
        response.hangup()
    return str(response)
__CAS_FILE_EOF_9f3a__
cat > "app/templates/base.html" << '__CAS_FILE_EOF_9f3a__'
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Call Automation{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='css/dashboard.css') }}">
</head>
<body>
  <nav class="topbar">
    <span class="brand">Call Automation</span>
    {% if current_user.is_authenticated %}
      <a href="{{ url_for('auth.logout') }}">Logout</a>
    {% endif %}
  </nav>
  <main class="container">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% for category, message in messages %}
        <div class="flash flash-{{ category }}">{{ message }}</div>
      {% endfor %}
    {% endwith %}
    {% block content %}{% endblock %}
  </main>
  <script src="{{ url_for('static', filename='js/dashboard.js') }}"></script>
</body>
</html>
__CAS_FILE_EOF_9f3a__
cat > "app/templates/dashboard.html" << '__CAS_FILE_EOF_9f3a__'
{% extends "base.html" %}
{% block content %}
<h1>Dashboard</h1>
<section class="stats-grid">
  {% for label, key in [("Total","total"),("Queued","queued"),("In progress","in_progress"),
                        ("Completed","completed"),("Failed","failed"),("Retry","retry"),
                        ("Skipped","skipped")] %}
  <div class="card stat"><span class="stat-num" id="stat-{{ key }}">{{ stats[key] }}</span>
    <span class="stat-label">{{ label }}</span></div>
  {% endfor %}
</section>

<div class="actions">
  <form method="post" action="{{ url_for('dashboard.upload_queue') }}"
        enctype="multipart/form-data" class="card">
    {{ upload_form.hidden_tag() }}
    {{ upload_form.queue_file() }}
    {{ upload_form.submit(class="btn") }}
  </form>
  <form method="post" action="{{ url_for('dashboard.start_automation') }}" class="card">
    {{ upload_form.hidden_tag() }}
    <button class="btn btn-primary" type="submit">Start dialing</button>
  </form>
</div>

<h2>Recent calls</h2>
<table class="table">
  <thead><tr><th>Number</th><th>Name</th><th>Status</th><th>Response</th></tr></thead>
  <tbody id="recent-calls">
    {% for c in recent_calls %}
    <tr><td>{{ c.phone_number }}</td><td>{{ c.caller_name }}</td>
        <td>{{ c.call_status }}</td><td>{{ c.response or '-' }}</td></tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
__CAS_FILE_EOF_9f3a__
cat > "app/templates/login.html" << '__CAS_FILE_EOF_9f3a__'
{% extends "base.html" %}
{% block title %}Login{% endblock %}
{% block content %}
<h1>Sign in</h1>
<form method="post" class="card" style="max-width:360px">
  {{ form.hidden_tag() }}
  <label>{{ form.username.label }}{{ form.username(class="input") }}</label>
  <label>{{ form.password.label }}{{ form.password(class="input") }}</label>
  {{ form.submit(class="btn btn-primary") }}
</form>
{% endblock %}
__CAS_FILE_EOF_9f3a__
cat > "app/web/__init__.py" << '__CAS_FILE_EOF_9f3a__'

__CAS_FILE_EOF_9f3a__
cat > "app/web/api.py" << '__CAS_FILE_EOF_9f3a__'
"""JSON API for the dashboard front-end."""
from flask import Blueprint, jsonify, request
from flask_login import login_required

from ..extensions import limiter
from ..services.stats import queue_statistics, recent_calls

api_bp = Blueprint("api", __name__)


@api_bp.route("/queue-status")
@login_required
@limiter.limit("60 per minute")
def queue_status():
    return jsonify(queue_statistics())


@api_bp.route("/recent-calls")
@login_required
@limiter.limit("60 per minute")
def api_recent_calls():
    limit = request.args.get("limit", 20, type=int)
    return jsonify(recent_calls(limit))
__CAS_FILE_EOF_9f3a__
cat > "app/web/dashboard.py" << '__CAS_FILE_EOF_9f3a__'
"""Dashboard + queue control. Every route requires login."""
import logging
import os

from flask import (
    Blueprint, current_app, flash, redirect, render_template, url_for,
)
from flask_login import login_required
from werkzeug.utils import secure_filename

from ..extensions import limiter
from ..services import queue_service
from ..services.stats import queue_statistics, recent_calls
from .forms import UploadQueueForm

logger = logging.getLogger(__name__)
dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    return render_template(
        "dashboard.html",
        stats=queue_statistics(),
        recent_calls=recent_calls(10),
        upload_form=UploadQueueForm(),
    )


@dashboard_bp.route("/upload-queue", methods=["POST"])
@login_required
@limiter.limit("10 per minute")
def upload_queue():
    form = UploadQueueForm()
    if not form.validate_on_submit():
        flash("Please choose a valid CSV file.", "error")
        return redirect(url_for("dashboard.index"))

    file = form.queue_file.data
    filename = secure_filename(file.filename)
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    file.save(path)
    try:
        count = queue_service.load_from_csv(path)
        flash(f"Loaded {count} valid numbers into the queue.", "success")
    except Exception as exc:  # noqa: BLE001
        logger.error("Queue upload failed: %s", exc)
        flash("Failed to parse the uploaded file.", "error")
    return redirect(url_for("dashboard.index"))


@dashboard_bp.route("/start-automation", methods=["POST"])
@login_required
@limiter.limit("5 per minute")
def start_automation():
    from ..tasks.call_tasks import drain_queue  # lazy import avoids circular load
    drain_queue.delay()
    flash("Dialing started in the background.", "success")
    return redirect(url_for("dashboard.index"))
__CAS_FILE_EOF_9f3a__
cat > "app/web/forms.py" << '__CAS_FILE_EOF_9f3a__'
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import SubmitField


class UploadQueueForm(FlaskForm):
    queue_file = FileField(
        "Queue CSV",
        validators=[FileRequired(), FileAllowed(["csv"], "CSV files only.")],
    )
    submit = SubmitField("Upload")
__CAS_FILE_EOF_9f3a__
cat > "app/web/webhooks.py" << '__CAS_FILE_EOF_9f3a__'
"""Twilio-facing webhooks. Every request is verified via X-Twilio-Signature
so nobody can spoof call events. CSRF is exempted for this blueprint
(see app factory) because Twilio cannot send a CSRF token."""
import logging
from functools import wraps

from flask import Blueprint, Response, abort, current_app, request, url_for
from twilio.request_validator import RequestValidator

from ..extensions import db
from ..models import CallLog
from ..services.call_service import apply_dtmf_response, apply_status_callback
from ..telephony.twiml import (
    build_accept_twiml,
    build_forward_twiml,
    build_greeting_twiml,
)

logger = logging.getLogger(__name__)
webhooks_bp = Blueprint("webhooks", __name__)


def validate_twilio(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        validator = RequestValidator(current_app.config["TWILIO_AUTH_TOKEN"])
        signature = request.headers.get("X-Twilio-Signature", "")
        if not validator.validate(request.url, request.form, signature):
            logger.warning("Rejected webhook with bad Twilio signature: %s", request.url)
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def _xml(body: str) -> Response:
    return Response(body, mimetype="text/xml")


@webhooks_bp.route("/voice/greeting", methods=["POST"])
@validate_twilio
def voice_greeting():
    log_id = request.args.get("log_id", type=int)
    script = request.args.get("script", "default")
    scripts = current_app.config.get("CALL_SCRIPTS", {})
    text = scripts.get(script, "Hello, this is an automated call from our service.")
    return _xml(build_greeting_twiml(text, log_id))


@webhooks_bp.route("/call-response/<int:log_id>", methods=["POST"])
@validate_twilio
def call_response(log_id: int):
    log = db.session.get(CallLog, log_id)
    if not log:
        abort(404)
    digit = request.form.get("Digits", "")
    outcome = apply_dtmf_response(log, digit)
    if outcome == "accept":
        return _xml(build_accept_twiml())
    if outcome == "forward":
        return _xml(build_forward_twiml())
    return _xml(build_accept_twiml())


@webhooks_bp.route("/status/<int:log_id>", methods=["POST"])
@validate_twilio
def status_callback(log_id: int):
    log = db.session.get(CallLog, log_id)
    if log:
        status = request.form.get("CallStatus", "")
        duration = request.form.get("CallDuration", type=int)
        apply_status_callback(log, status, duration)
    return ("", 204)
__CAS_FILE_EOF_9f3a__
cat > "call_scripts.json" << '__CAS_FILE_EOF_9f3a__'
{
  "default": "Hello, this is an automated call from our service.",
  "reminder": "Hello, this is a friendly reminder about your upcoming appointment."
}
__CAS_FILE_EOF_9f3a__
cat > "docker-compose.yml" << '__CAS_FILE_EOF_9f3a__'
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: cas
      POSTGRES_PASSWORD: cas
      POSTGRES_DB: call_automation
    volumes: ["pgdata:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U cas"]
      interval: 5s
      retries: 5

  redis:
    image: redis:7-alpine

  web:
    build: .
    env_file: .env
    depends_on: { db: { condition: service_healthy }, redis: { condition: service_started } }
    ports: ["8000:8000"]
    command: >
      sh -c "flask db upgrade && flask create-admin || true &&
             gunicorn wsgi:app --bind 0.0.0.0:8000 --workers 3 --timeout 120"

  worker:
    build: .
    env_file: .env
    depends_on: [db, redis]
    command: celery -A worker.celery worker --beat --loglevel=info

volumes:
  pgdata:
__CAS_FILE_EOF_9f3a__
cat > "pyproject.toml" << '__CAS_FILE_EOF_9f3a__'
[project]
name = "call-automation"
version = "1.0.0"
description = "Production-grade outbound call automation built on Flask + Twilio + Celery"
requires-python = ">=3.11"
dependencies = [
    "Flask==3.0.3",
    "Flask-SQLAlchemy==3.1.1",
    "Flask-Migrate==4.0.7",
    "Flask-Limiter==3.7.0",
    "Flask-WTF==1.2.1",
    "Flask-Login==0.6.3",
    "SQLAlchemy==2.0.31",
    "twilio==9.2.3",
    "celery[redis]==5.4.0",
    "redis==5.0.7",
    "gspread==6.1.2",
    "google-auth==2.32.0",
    "python-dotenv==1.0.1",
    "phonenumbers==8.13.40",
    "gunicorn==22.0.0",
]

[project.optional-dependencies]
dev = ["pytest==8.2.2", "pytest-flask==1.3.0", "pytest-mock==3.14.0", "ruff==0.5.1"]
postgres = ["psycopg2-binary==2.9.9"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
packages = ["app"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pytest.ini_options]
testpaths = ["tests"]
__CAS_FILE_EOF_9f3a__
cat > "tests/__init__.py" << '__CAS_FILE_EOF_9f3a__'

__CAS_FILE_EOF_9f3a__
cat > "tests/conftest.py" << '__CAS_FILE_EOF_9f3a__'
import pytest

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.models import User


@pytest.fixture
def app():
    app = create_app(TestingConfig)
    with app.app_context():
        db.create_all()
        user = User(username="tester", role="admin")
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(app, client):
    client.post("/login", data={"username": "tester", "password": "secret"})
    return client
__CAS_FILE_EOF_9f3a__
cat > "tests/test_auth.py" << '__CAS_FILE_EOF_9f3a__'
def test_dashboard_requires_login(client):
    res = client.get("/")
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]


def test_login_then_dashboard(auth_client):
    res = auth_client.get("/")
    assert res.status_code == 200


def test_bad_password_rejected(client):
    res = client.post("/login", data={"username": "tester", "password": "wrong"})
    assert b"Invalid username or password" in res.data


def test_health(client):
    assert client.get("/healthz").status_code == 200
__CAS_FILE_EOF_9f3a__
cat > "tests/test_compliance.py" << '__CAS_FILE_EOF_9f3a__'
from app.services.compliance import add_to_dnc, can_call, is_dnc, normalize_number


def test_normalize_valid_indian_number(app):
    with app.app_context():
        assert normalize_number("9123456780", "IN").startswith("+91")


def test_normalize_invalid(app):
    with app.app_context():
        assert normalize_number("123", "IN") is None


def test_dnc_blocks_calling(app):
    with app.app_context():
        num = normalize_number("9123456780", "IN")
        add_to_dnc(num)
        assert is_dnc(num) is True
        allowed, reason = can_call(num)
        assert allowed is False
        assert "do-not-call" in reason
__CAS_FILE_EOF_9f3a__
cat > "tests/test_queue.py" << '__CAS_FILE_EOF_9f3a__'
from app.models import CallQueue
from app.services.queue_service import claim_next, load_from_rows


def test_load_skips_invalid_numbers(app):
    with app.app_context():
        count = load_from_rows([
            {"phone_number": "9123456780", "caller_name": "A", "priority": "high"},
            {"phone_number": "garbage", "caller_name": "B"},
        ])
        assert count == 1
        assert CallQueue.query.count() == 1


def test_claim_next_marks_dialing(app):
    with app.app_context():
        load_from_rows([{"phone_number": "9123456780", "priority": "low"}])
        item = claim_next()
        assert item.status == "dialing"
        assert item.attempts == 1
        assert claim_next() is None  # nothing else dialable
__CAS_FILE_EOF_9f3a__
cat > "worker.py" << '__CAS_FILE_EOF_9f3a__'
"""Celery entrypoint:  celery -A worker.celery worker --beat --loglevel=info"""
from app.tasks.celery_app import celery  # noqa: F401
import app.tasks.call_tasks  # noqa: F401  (register tasks)
__CAS_FILE_EOF_9f3a__
cat > "wsgi.py" << '__CAS_FILE_EOF_9f3a__'
"""Gunicorn / flask entrypoint:  gunicorn wsgi:app"""
from app import create_app
from app.cli import register_cli

app = create_app()
register_cli(app)
__CAS_FILE_EOF_9f3a__

echo ">> Creating virtual environment..."
python3 -m venv .venv
source .venv/bin/activate
echo ">> Installing dependencies (1-2 min)..."
pip install --quiet --upgrade pip
pip install --quiet -e ".[dev]"
if [ ! -f .env ]; then
  cp .env.example .env
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  python3 - "$SECRET" << 'PYENV'
import sys, pathlib, re
secret=sys.argv[1]; p=pathlib.Path(".env"); t=p.read_text()
t=t.replace("change-me-use-openssl-rand-hex-32", secret)
t=t.replace("FLASK_CONFIG=production","FLASK_CONFIG=development")
abs_db=pathlib.Path("instance/call_automation.db").resolve()
t=re.sub(r"^DATABASE_URL=.*$", f"DATABASE_URL=sqlite:////{abs_db}", t, flags=re.M)
t=t.replace("change-me-strong","admin12345")
p.write_text(t); print(">> .env created (development, sqlite, auto SECRET_KEY)")
PYENV
fi
set -a; source .env; set +a
export FLASK_APP=wsgi:app
mkdir -p instance uploads
echo ">> Database migrations..."
[ -d migrations ] || flask db init
flask db migrate -m "initial schema"
flask db upgrade
echo ">> Creating admin user..."
flask create-admin || true
echo ""
echo "============================================================"
echo " Setup complete."
echo " Start app:   source .venv/bin/activate && flask run"
echo " Login:       admin / admin12345   (change in .env)"
echo " Run tests:   FLASK_CONFIG=testing pytest -q"
echo "============================================================"

