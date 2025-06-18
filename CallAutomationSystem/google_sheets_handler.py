import os
import logging
from typing import List, Dict, Optional
import gspread
from google.oauth2.service_account import Credentials

class GoogleSheetsHandler:
    """Handler for Google Sheets integration"""
    
    def __init__(self):
        self.client = None
        self._init_client()
    
    def _init_client(self):
        """Initialize Google Sheets client"""
        try:
            # Try to get credentials from environment variable
            creds_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
            
            if creds_json:
                import json
                creds_dict = json.loads(creds_json)
                
                # Define the scope
                scope = [
                    'https://spreadsheets.google.com/feeds',
                    'https://www.googleapis.com/auth/drive'
                ]
                
                # Create credentials object
                credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
                
                # Initialize the client
                self.client = gspread.authorize(credentials)
                logging.info("Google Sheets client initialized successfully")
            else:
                logging.warning("Google Sheets credentials not found in environment variables")
                
        except Exception as e:
            logging.error(f"Error initializing Google Sheets client: {str(e)}")
    
    def read_call_queue(self, sheet_url: str, worksheet_name: str = None) -> List[Dict]:
        """Read call queue data from Google Sheets"""
        if not self.client:
            raise Exception("Google Sheets client not initialized")
        
        try:
            # Open the spreadsheet
            sheet = self.client.open_by_url(sheet_url)
            
            # Get the worksheet
            if worksheet_name:
                worksheet = sheet.worksheet(worksheet_name)
            else:
                worksheet = sheet.get_worksheet(0)  # First worksheet
            
            # Get all records
            records = worksheet.get_all_records()
            
            # Validate and format data
            formatted_records = []
            for record in records:
                formatted_record = {
                    'phone_number': str(record.get('phone_number', '')).strip(),
                    'caller_name': str(record.get('caller_name', '')).strip(),
                    'priority': self._safe_int(record.get('priority', 1)),
                    'script': str(record.get('script', 'default')).strip()
                }
                
                # Only add records with valid phone numbers
                if formatted_record['phone_number']:
                    formatted_records.append(formatted_record)
            
            logging.info(f"Read {len(formatted_records)} records from Google Sheets")
            return formatted_records
            
        except Exception as e:
            logging.error(f"Error reading from Google Sheets: {str(e)}")
            raise
    
    def update_call_status(self, sheet_url: str, phone_number: str, status: str, 
                          response: str = None, timestamp: str = None, 
                          worksheet_name: str = None):
        """Update call status in Google Sheets"""
        if not self.client:
            logging.warning("Google Sheets client not initialized, skipping update")
            return
        
        try:
            # Open the spreadsheet
            sheet = self.client.open_by_url(sheet_url)
            
            # Get the worksheet
            if worksheet_name:
                worksheet = sheet.worksheet(worksheet_name)
            else:
                worksheet = sheet.get_worksheet(0)
            
            # Find the row with the phone number
            all_values = worksheet.get_all_values()
            headers = all_values[0] if all_values else []
            
            # Find column indices
            phone_col = None
            status_col = None
            response_col = None
            timestamp_col = None
            
            for i, header in enumerate(headers):
                if header.lower() in ['phone_number', 'phone']:
                    phone_col = i + 1
                elif header.lower() in ['status', 'call_status']:
                    status_col = i + 1
                elif header.lower() in ['response', 'call_response']:
                    response_col = i + 1
                elif header.lower() in ['timestamp', 'last_updated']:
                    timestamp_col = i + 1
            
            # Find the row to update
            for row_idx, row in enumerate(all_values[1:], start=2):
                if len(row) > phone_col - 1 and row[phone_col - 1] == phone_number:
                    # Update status
                    if status_col:
                        worksheet.update_cell(row_idx, status_col, status)
                    
                    # Update response if provided
                    if response and response_col:
                        worksheet.update_cell(row_idx, response_col, response)
                    
                    # Update timestamp if provided
                    if timestamp and timestamp_col:
                        worksheet.update_cell(row_idx, timestamp_col, timestamp)
                    
                    logging.info(f"Updated status for {phone_number} to {status}")
                    break
            
        except Exception as e:
            logging.error(f"Error updating Google Sheets: {str(e)}")
    
    def add_call_log(self, sheet_url: str, call_data: Dict, worksheet_name: str = "Call_Logs"):
        """Add call log entry to Google Sheets"""
        if not self.client:
            logging.warning("Google Sheets client not initialized, skipping log")
            return
        
        try:
            # Open the spreadsheet
            sheet = self.client.open_by_url(sheet_url)
            
            # Try to get the call logs worksheet
            try:
                worksheet = sheet.worksheet(worksheet_name)
            except gspread.WorksheetNotFound:
                # Create the worksheet if it doesn't exist
                worksheet = sheet.add_worksheet(title=worksheet_name, rows="1000", cols="10")
                
                # Add headers
                headers = [
                    'Phone Number', 'Caller Name', 'Call Status', 'Call SID',
                    'Start Time', 'End Time', 'Duration', 'Response', 'Notes'
                ]
                worksheet.append_row(headers)
            
            # Prepare row data
            row_data = [
                call_data.get('phone_number', ''),
                call_data.get('caller_name', ''),
                call_data.get('call_status', ''),
                call_data.get('call_sid', ''),
                call_data.get('start_time', ''),
                call_data.get('end_time', ''),
                call_data.get('duration', ''),
                call_data.get('response', ''),
                call_data.get('notes', '')
            ]
            
            # Append the row
            worksheet.append_row(row_data)
            logging.info(f"Added call log for {call_data.get('phone_number')}")
            
        except Exception as e:
            logging.error(f"Error adding call log to Google Sheets: {str(e)}")
    
    def _safe_int(self, value, default=1):
        """Safely convert value to integer"""
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
