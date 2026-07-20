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
