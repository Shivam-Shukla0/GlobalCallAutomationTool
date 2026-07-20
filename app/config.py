"""Configuration objects. Production fails fast if secrets are missing."""
import os

# Load .env BEFORE any config is read, so the app behaves the same
# whether launched via flask run, gunicorn, celery or pytest.
from dotenv import load_dotenv

load_dotenv()


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
