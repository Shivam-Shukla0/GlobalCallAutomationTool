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
