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
