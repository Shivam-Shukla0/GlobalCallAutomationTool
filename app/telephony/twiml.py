"""TwiML generation. These XML docs are served from real HTTP endpoints
(see web/webhooks.py) so Twilio can fetch them — the old data: URL approach
never worked because Twilio fetches call instructions over HTTP."""
from flask import current_app, url_for
from twilio.twiml.voice_response import Gather, VoiceResponse


def build_greeting_twiml(script_text: str, log_id: int) -> str:
    """Greeting + DTMF gather. Action posts back to our webhook with the log id."""
    response = VoiceResponse()
    gather = Gather(
        input="dtmf",
        num_digits=1,
        timeout=8,
        action=url_for("webhooks.call_response", log_id=log_id, _external=True),
        method="POST",
    )
    gather.say(script_text, voice="alice")
    gather.say("Press 1 to accept, or 2 to be forwarded to an agent.", voice="alice")
    response.append(gather)
    # If no input, repeat once by redirecting back to the greeting.
    response.say("We did not receive any input. Goodbye.", voice="alice")
    response.hangup()
    return str(response)


def build_accept_twiml() -> str:
    response = VoiceResponse()
    response.say("Thank you. Your call has been accepted. Goodbye.", voice="alice")
    response.hangup()
    return str(response)


def build_forward_twiml() -> str:
    response = VoiceResponse()
    forward_to = current_app.config.get("FORWARD_TO_NUMBER")
    if forward_to:
        response.say("Connecting you to an agent now.", voice="alice")
        response.dial(forward_to)
    else:
        response.say("Forwarding is not configured. Goodbye.", voice="alice")
        response.hangup()
    return str(response)
