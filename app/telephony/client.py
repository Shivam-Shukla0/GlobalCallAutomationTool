"""Thin wrapper around the Twilio REST client."""
import logging

from flask import current_app
from twilio.rest import Client

logger = logging.getLogger(__name__)


def get_twilio_client() -> Client:
    sid = current_app.config["TWILIO_ACCOUNT_SID"]
    token = current_app.config["TWILIO_AUTH_TOKEN"]
    if not sid or not token:
        raise RuntimeError("Twilio credentials are not configured")
    return Client(sid, token)
