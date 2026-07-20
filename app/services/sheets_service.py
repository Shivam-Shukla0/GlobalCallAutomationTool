"""Optional Google Sheets queue source."""
import json
import logging

from flask import current_app

logger = logging.getLogger(__name__)


def _client():
    creds_json = current_app.config.get("GOOGLE_SHEETS_CREDENTIALS")
    if not creds_json:
        raise RuntimeError("Google Sheets credentials not configured")
    import gspread
    from google.oauth2.service_account import Credentials

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    return gspread.authorize(creds)


def read_queue(sheet_url: str, worksheet_name: str | None = None) -> list[dict]:
    sheet = _client().open_by_url(sheet_url)
    ws = sheet.worksheet(worksheet_name) if worksheet_name else sheet.get_worksheet(0)
    records = ws.get_all_records()
    return [r for r in records if str(r.get("phone_number", "")).strip()]
