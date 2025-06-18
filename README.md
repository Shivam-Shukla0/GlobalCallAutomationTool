# Global Call Automation Tool 📞

The **Global Call Automation Tool** is a Python-Flask based system that automates outbound calling using the Twilio API. It allows users to queue, track, and manage automated voice calls with custom scripts, and logs the results in both a local database and Google Sheets.

## 🔧 Features
- 🔁 **Automated Voice Calls** using Twilio
- 📄 **Upload Call Queue** via CSV
- 📋 **Track Call Status** in real-time
- 🧾 **Logs Stored** in both SQLite and Google Sheets
- 🌐 Web dashboard for viewing call logs

## 📁 Folder Structure
CallAutomationSystem/
├── app.py
├── call_automation.py
├── config.py
├── main.py
├── models.py
├── templates/
├── static/
├── call_scripts.json
├── instance/
│ └── call_automation.db
└── attached_assets/


## 🧪 Running Locally

1. Clone the repository:
   ```bash
   git clone https://github.com/Shivam-Shukla0/GlobalCallAutomationTool.git
   cd GlobalCallAutomationTool/CallAutomationSystem
2. Install dependencies:
   pip install -r requirements.txt
3. Set up .env file with your Twilio and Google credentials:
   TWILIO_ACCOUNT_SID=your_sid
   TWILIO_AUTH_TOKEN=your_token
   TWILIO_PHONE_NUMBER=your_number
4. Run the Flask app:
   python app.py
   
