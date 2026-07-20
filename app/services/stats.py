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
