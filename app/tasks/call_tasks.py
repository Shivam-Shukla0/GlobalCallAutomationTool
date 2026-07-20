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
