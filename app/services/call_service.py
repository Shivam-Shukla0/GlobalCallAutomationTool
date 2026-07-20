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
