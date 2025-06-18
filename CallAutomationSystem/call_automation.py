import os
import logging
import json
import csv
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from twilio.rest import Client
from twilio.base.exceptions import TwilioException

class CallAutomationSystem:
    """Main class for handling call automation"""
    
    def __init__(self):
        self.twilio_client = None
        self.is_automation_running = False
        self.current_call = None
        self.call_queue = []
        self.call_scripts = {}
        self.automation_thread = None
        
        # Initialize Twilio client
        self._init_twilio_client()
        
        # Load call scripts
        self._load_call_scripts()
    
    def _init_twilio_client(self):
        """Initialize Twilio client with credentials from environment"""
        try:
            account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
            auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
            
            if not account_sid or not auth_token:
                logging.error("Twilio credentials not found in environment variables")
                return
            
            self.twilio_client = Client(account_sid, auth_token)
            self.twilio_phone_number = os.environ.get("TWILIO_PHONE_NUMBER")
            
            if not self.twilio_phone_number:
                logging.error("Twilio phone number not found in environment variables")
            
            logging.info("Twilio client initialized successfully")
            
        except Exception as e:
            logging.error(f"Error initializing Twilio client: {str(e)}")
    
    def _load_call_scripts(self):
        """Load call scripts from JSON file"""
        try:
            with open('call_scripts.json', 'r') as f:
                self.call_scripts = json.load(f)
            logging.info("Call scripts loaded successfully")
        except FileNotFoundError:
            logging.warning("Call scripts file not found, using default script")
            self.call_scripts = {
                "default": "Hello, this is an automated call from our service. Please press 1 to accept or 2 to forward this call."
            }
        except Exception as e:
            logging.error(f"Error loading call scripts: {str(e)}")
            self.call_scripts = {
                "default": "Hello, this is an automated call from our service. Please press 1 to accept or 2 to forward this call."
            }
    
    def _convert_priority(self, priority):
        """Convert priority to integer"""
        if isinstance(priority, str):
            priority_map = {
                'high': 3, 'medium': 2, 'low': 1,
                'High': 3, 'Medium': 2, 'Low': 1,
                'HIGH': 3, 'MEDIUM': 2, 'LOW': 1
            }
            return priority_map.get(priority, 1)
        try:
            return int(priority)
        except (ValueError, TypeError):
            return 1
    
    def load_queue_from_csv(self, csv_file: str):
        """Load call queue from CSV file"""
        try:
            from app import app, db
            from models import CallQueue
            
            with app.app_context():
                with open(csv_file, 'r') as f:
                    reader = csv.DictReader(f)
                    
                    # Clear existing queue
                    CallQueue.query.delete()
                    
                    for row in reader:
                        queue_item = CallQueue(
                            phone_number=row.get('phone_number', ''),
                            caller_name=row.get('caller_name', ''),
                            priority=self._convert_priority(row.get('priority', '1')),
                            assigned_script=row.get('script', 'default')
                        )
                        db.session.add(queue_item)
                    
                    db.session.commit()
                    logging.info(f"Loaded {CallQueue.query.count()} calls from CSV")
                
        except Exception as e:
            logging.error(f"Error loading queue from CSV: {str(e)}")
            raise
    
    def load_queue_from_google_sheets(self, sheet_url: str):
        """Load call queue from Google Sheets"""
        try:
            from app import db
            from models import CallQueue
            from google_sheets_handler import GoogleSheetsHandler
            
            sheets_handler = GoogleSheetsHandler()
            data = sheets_handler.read_call_queue(sheet_url)
            
            # Clear existing queue
            CallQueue.query.delete()
            
            for row in data:
                queue_item = CallQueue(
                    phone_number=row.get('phone_number', ''),
                    caller_name=row.get('caller_name', ''),
                    priority=int(row.get('priority', 1)),
                    assigned_script=row.get('script', 'default')
                )
                db.session.add(queue_item)
            
            db.session.commit()
            logging.info(f"Loaded {len(data)} calls from Google Sheets")
            
        except Exception as e:
            logging.error(f"Error loading queue from Google Sheets: {str(e)}")
            raise
    
    def make_call(self, phone_number: str, script: str = "default") -> Optional[Dict]:
        """Make a call using Twilio"""
        if not self.twilio_client or not self.twilio_phone_number:
            logging.error("Twilio client not properly initialized")
            return None
        
        try:
            # Get script content
            script_content = self.call_scripts.get(script, self.call_scripts.get("default", ""))
            
            # Create TwiML for the call
            twiml_url = self._create_twiml_url(script_content)
            
            call = self.twilio_client.calls.create(
                to=phone_number,
                from_=self.twilio_phone_number,
                url=twiml_url,
                method='GET'
            )
            
            logging.info(f"Call initiated to {phone_number}, SID: {call.sid}")
            
            return {
                'call_sid': call.sid,
                'status': call.status,
                'to': call.to,
                'from': str(call.from_)
            }
            
        except TwilioException as e:
            logging.error(f"Twilio error making call to {phone_number}: {str(e)}")
            return None
        except Exception as e:
            logging.error(f"Error making call to {phone_number}: {str(e)}")
            return None
    
    def _create_twiml_url(self, script_content: str) -> str:
        """Create TwiML URL for call script"""
        # In a production environment, you would create a webhook endpoint
        # For now, we'll use a simple TwiML instruction
        from urllib.parse import quote
        
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="alice">{script_content}</Say>
            <Gather input="dtmf" timeout="10" numDigits="1" action="/webhook/call-response" method="POST">
                <Say voice="alice">Press 1 to accept or 2 to forward this call.</Say>
            </Gather>
            <Say voice="alice">No input received. Goodbye.</Say>
        </Response>"""
        
        # In a real implementation, you would serve this TwiML from a webhook endpoint
        # For now, we'll return a placeholder URL
        return f"data:text/xml,{quote(twiml)}"
    
    def start_automation(self):
        """Start the call automation process"""
        if self.is_automation_running:
            logging.warning("Automation is already running")
            return
        
        self.is_automation_running = True
        logging.info("Starting call automation")
        
        try:
            from app import app, db
            from models import CallQueue, CallLog
            
            with app.app_context():
                while self.is_automation_running:
                    # Get next call from queue
                    next_call = CallQueue.query.filter_by(status='Not Called').order_by(CallQueue.priority.desc(), CallQueue.created_at.asc()).first()
                    
                    if not next_call:
                        logging.info("No more calls in queue")
                        self.is_automation_running = False
                        break
                    
                    # Update status to calling
                    next_call.status = 'Calling'
                    next_call.attempts += 1
                    db.session.commit()
                    
                    # Make the call
                    call_result = self.make_call(next_call.phone_number, next_call.assigned_script)
                    
                    if call_result:
                        # Create call log
                        call_log = CallLog(
                            phone_number=next_call.phone_number,
                            caller_name=next_call.caller_name,
                            call_status='Connected',
                            call_sid=call_result['call_sid'],
                            start_time=datetime.utcnow()
                        )
                        db.session.add(call_log)
                        
                        # Update queue status
                        next_call.status = 'Connected'
                        
                    else:
                        # Call failed
                        call_log = CallLog(
                            phone_number=next_call.phone_number,
                            caller_name=next_call.caller_name,
                            call_status='Failed',
                            start_time=datetime.utcnow(),
                            end_time=datetime.utcnow()
                        )
                        db.session.add(call_log)
                        
                        # Check if we should retry
                        if next_call.attempts < next_call.max_attempts:
                            next_call.status = 'Retry Scheduled'
                        else:
                            next_call.status = 'Failed'
                    
                    db.session.commit()
                    
                    # Wait between calls
                    time.sleep(5)
        
        except Exception as e:
            logging.error(f"Error in automation loop: {str(e)}")
        finally:
            self.is_automation_running = False
            logging.info("Call automation stopped")
    
    def stop_automation(self):
        """Stop the call automation process"""
        self.is_automation_running = False
        logging.info("Stopping call automation")
    
    def is_running(self) -> bool:
        """Check if automation is currently running"""
        return self.is_automation_running
    
    def handle_call_response(self, call_id: str, response: str) -> Dict:
        """Handle response from call recipient"""
        try:
            from app import db
            from models import CallLog, CallQueue
            
            call_log = CallLog.query.filter_by(call_sid=call_id).first()
            
            if not call_log:
                return {"error": "Call not found"}
            
            if response == "1":
                # Accept call
                call_log.response = "Accepted"
                call_log.call_status = "Accepted"
                call_log.end_time = datetime.utcnow()
                
                # Update queue status
                queue_item = CallQueue.query.filter_by(phone_number=call_log.phone_number).first()
                if queue_item:
                    queue_item.status = "Accepted"
                
            elif response == "2":
                # Forward call
                call_log.response = "Forwarded"
                call_log.call_status = "Forwarded"
                call_log.end_time = datetime.utcnow()
                
                # Update queue status
                queue_item = CallQueue.query.filter_by(phone_number=call_log.phone_number).first()
                if queue_item:
                    queue_item.status = "Forwarded"
            
            # Calculate duration
            if call_log.start_time and call_log.end_time:
                duration = (call_log.end_time - call_log.start_time).total_seconds()
                call_log.duration = int(duration)
            
            db.session.commit()
            
            return {"success": True, "response": call_log.response}
            
        except Exception as e:
            logging.error(f"Error handling call response: {str(e)}")
            return {"error": str(e)}
    
    def get_queue_statistics(self) -> Dict:
        """Get current queue statistics"""
        try:
            from models import CallQueue
            
            total_calls = CallQueue.query.count()
            not_called = CallQueue.query.filter_by(status='Not Called').count()
            connected = CallQueue.query.filter_by(status='Connected').count()
            accepted = CallQueue.query.filter_by(status='Accepted').count()
            forwarded = CallQueue.query.filter_by(status='Forwarded').count()
            failed = CallQueue.query.filter_by(status='Failed').count()
            
            return {
                'total_calls': total_calls,
                'not_called': not_called,
                'connected': connected,
                'accepted': accepted,
                'forwarded': forwarded,
                'failed': failed,
                'is_running': self.is_automation_running
            }
            
        except Exception as e:
            logging.error(f"Error getting queue statistics: {str(e)}")
            return {
                'total_calls': 0,
                'not_called': 0,
                'connected': 0,
                'accepted': 0,
                'forwarded': 0,
                'failed': 0,
                'is_running': False
            }
    
    def get_recent_calls(self, limit: int = 10) -> List[Dict]:
        """Get recent call logs"""
        try:
            from models import CallLog
            
            recent_calls = CallLog.query.order_by(CallLog.created_at.desc()).limit(limit).all()
            return [call.to_dict() for call in recent_calls]
            
        except Exception as e:
            logging.error(f"Error getting recent calls: {str(e)}")
            return []
    
    def get_call_logs(self, page: int = 1, per_page: int = 50) -> List[Dict]:
        """Get paginated call logs"""
        try:
            from models import CallLog
            
            calls = CallLog.query.order_by(CallLog.created_at.desc()).offset((page-1)*per_page).limit(per_page).all()
            return [call.to_dict() for call in calls]
            
        except Exception as e:
            logging.error(f"Error getting call logs: {str(e)}")
            return []
