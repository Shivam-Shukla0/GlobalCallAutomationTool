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
