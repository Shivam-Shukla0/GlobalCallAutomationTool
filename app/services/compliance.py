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
