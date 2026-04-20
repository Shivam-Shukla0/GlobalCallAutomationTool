# Global Call Automation Tool

> **Automate mass outbound voice calls with custom scripts, real-time tracking, and dual logging — powered by Twilio.**

A Python-Flask web application that enables automated voice call campaigns at scale. Upload a CSV of phone numbers, define call scripts, and the system handles dialing, status tracking, and result logging — all from a web dashboard.

---

## What It Does

Instead of manually calling hundreds of numbers, this tool lets you:
- Upload a list of phone numbers via CSV
- Assign automated voice scripts to each call
- Track live call status (queued / in-progress / completed / failed)
- Log all results automatically to both a local database and Google Sheets

---

## Features

- **Automated Voice Calls** — Uses Twilio API to place real outbound calls with custom voice scripts
- **CSV Upload** — Bulk import phone numbers and call metadata in one step
- **Real-Time Status Tracking** — Monitor each call's progress live on the dashboard
- **Dual Logging** — Results stored in SQLite (local) and Google Sheets (cloud) simultaneously
- **Web Dashboard** — Browser-based interface to manage and view all call logs
- **Customizable Scripts** — Define different messages for different call campaigns via `call_scripts.json`

---

## How It Works

```
User uploads CSV (phone numbers + metadata)
        ↓
call_automation.py → reads queue, prepares call scripts
        ↓
Twilio API → places actual voice calls
        ↓
Call status returned (completed / failed / busy)
        ↓
models.py → saves result to SQLite DB
        ↓
Google Sheets API → mirrors the result to cloud sheet
        ↓
Web dashboard → displays all logs in real-time
```

---

## Project Structure

```
GlobalCallAutomationTool/
├── CallAutomationSystem/
│   ├── app.py                  # Flask server and routes
│   ├── call_automation.py      # Twilio call logic
│   ├── config.py               # Configuration and environment variables
│   ├── main.py                 # Entry point
│   ├── models.py               # SQLite database models
│   ├── call_scripts.json       # Voice script templates
│   ├── templates/              # HTML dashboard
│   └── static/                 # CSS and JS
├── instance/
│   └── call_automation.db      # Local SQLite database
├── .env.example                # Environment variable template
├── requirements.txt
└── uploaded_call_queue.csv     # Sample call queue CSV
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask |
| Voice Calls | Twilio API |
| Database | SQLite (via SQLAlchemy) |
| Cloud Logging | Google Sheets API |
| Frontend | HTML, CSS, JavaScript |
| Config | python-dotenv |

---

## Getting Started

### 1. Clone the repository
```bash
git clone https://github.com/Shivam-Shukla0/GlobalCallAutomationTool.git
cd GlobalCallAutomationTool/CallAutomationSystem
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set up environment variables
Copy `.env.example` to `.env` and fill in your credentials:
```env
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=your_twilio_number
GOOGLE_SHEETS_CREDENTIALS=path_to_your_credentials.json
GOOGLE_SHEET_ID=your_sheet_id
```

### 4. Run the app
```bash
python app.py
```

### 5. Open dashboard
```
http://127.0.0.1:5000
```

---

## CSV Format for Call Queue

```csv
name,phone_number,script_key
John Doe,+919876543210,reminder
Jane Smith,+918765432109,announcement
```

---

## Use Cases

- **Mass Announcements** — Notify hundreds of contacts about events or alerts
- **Appointment Reminders** — Automated reminder calls for clinics, schools
- **Survey Calls** — Collect responses via automated voice prompts
- **Emergency Alerts** — Rapid outbound calling for critical notifications

---

## License

MIT License — free to use, modify, and distribute.
