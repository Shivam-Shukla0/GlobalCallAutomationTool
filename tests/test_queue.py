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
