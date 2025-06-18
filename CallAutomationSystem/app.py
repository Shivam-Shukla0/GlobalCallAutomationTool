import os
import logging
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime
import json
import csv
import threading
from call_automation import CallAutomationSystem
from google_sheets_handler import GoogleSheetsHandler

# Set up logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# Create the Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "fallback-secret-key-for-development")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///call_automation.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Initialize extensions
db.init_app(app)

# Global automation system instance
automation_system = None
google_sheets_handler = None

with app.app_context():
    import models
    db.create_all()

@app.route('/')
def dashboard():
    """Main dashboard route"""
    global automation_system
    if not automation_system:
        automation_system = CallAutomationSystem()
    
    # Get current queue status
    queue_stats = automation_system.get_queue_statistics()
    recent_calls = automation_system.get_recent_calls(limit=10)
    
    return render_template('dashboard.html', 
                         queue_stats=queue_stats, 
                         recent_calls=recent_calls)

@app.route('/api/queue-status')
def api_queue_status():
    """API endpoint for real-time queue status"""
    global automation_system
    if not automation_system:
        automation_system = CallAutomationSystem()
    
    return jsonify(automation_system.get_queue_statistics())

@app.route('/api/recent-calls')
def api_recent_calls():
    """API endpoint for recent call logs"""
    global automation_system
    if not automation_system:
        automation_system = CallAutomationSystem()
    
    limit = request.args.get('limit', 20, type=int)
    calls = automation_system.get_recent_calls(limit=limit)
    return jsonify(calls)

@app.route('/start-automation', methods=['POST'])
def start_automation():
    """Start the call automation process"""
    global automation_system
    if not automation_system:
        automation_system = CallAutomationSystem()
    
    try:
        # Check if automation is already running
        if automation_system.is_running():
            flash("Call automation is already running!", "warning")
            return redirect(url_for('dashboard'))
        
        # Load call queue from source
        data_source = request.form.get('data_source', 'csv')
        if data_source == 'google_sheets':
            sheet_url = request.form.get('sheet_url', '')
            if not sheet_url:
                flash("Google Sheets URL is required!", "error")
                return redirect(url_for('dashboard'))
            automation_system.load_queue_from_google_sheets(sheet_url)
        else:
            # Use uploaded file if available, otherwise use sample
            csv_file = 'uploaded_call_queue.csv' if os.path.exists('uploaded_call_queue.csv') else 'sample_call_queue.csv'
            automation_system.load_queue_from_csv(csv_file)
        
        # Start automation in background thread
        automation_thread = threading.Thread(target=automation_system.start_automation)
        automation_thread.daemon = True
        automation_thread.start()
        
        flash("Call automation started successfully!", "success")
        
    except Exception as e:
        logging.error(f"Error starting automation: {str(e)}")
        flash(f"Error starting automation: {str(e)}", "error")
    
    return redirect(url_for('dashboard'))

@app.route('/stop-automation', methods=['POST'])
def stop_automation():
    """Stop the call automation process"""
    global automation_system
    if automation_system:
        automation_system.stop_automation()
        flash("Call automation stopped!", "info")
    
    return redirect(url_for('dashboard'))

@app.route('/upload-queue', methods=['POST'])
def upload_queue():
    """Upload a new call queue CSV file"""
    global automation_system
    if not automation_system:
        automation_system = CallAutomationSystem()
    
    try:
        if 'queue_file' not in request.files:
            flash("No file selected!", "error")
            return redirect(url_for('dashboard'))
        
        file = request.files['queue_file']
        if file.filename == '':
            flash("No file selected!", "error")
            return redirect(url_for('dashboard'))
        
        if file and file.filename.endswith('.csv'):
            # Save uploaded file
            filename = 'uploaded_call_queue.csv'
            file.save(filename)
            
            # Load the new queue
            automation_system.load_queue_from_csv(filename)
            flash("Call queue uploaded successfully!", "success")
        else:
            flash("Please upload a valid CSV file!", "error")
            
    except Exception as e:
        logging.error(f"Error uploading queue: {str(e)}")
        flash(f"Error uploading queue: {str(e)}", "error")
    
    return redirect(url_for('dashboard'))

@app.route('/call-logs')
def call_logs():
    """View detailed call logs"""
    global automation_system
    if not automation_system:
        automation_system = CallAutomationSystem()
    
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Get paginated call logs
    calls = automation_system.get_call_logs(page=page, per_page=per_page)
    
    return render_template('call_logs.html', calls=calls, page=page)

@app.route('/api/call-response', methods=['POST'])
def api_call_response():
    """Handle call response (Accept/Forward)"""
    global automation_system
    if not automation_system:
        return jsonify({"error": "Automation system not initialized"}), 400
    
    try:
        data = request.get_json()
        call_id = data.get('call_id')
        response = data.get('response')  # 1 for Accept, 2 for Forward
        
        if not call_id or not response:
            return jsonify({"error": "Missing call_id or response"}), 400
        
        result = automation_system.handle_call_response(call_id, response)
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"Error handling call response: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/update-script', methods=['POST'])
def api_update_script():
    """Update call script"""
    try:
        data = request.get_json()
        script_type = data.get('script_type', 'default')
        script_content = data.get('script_content', '')
        
        # Load existing scripts
        try:
            with open('call_scripts.json', 'r') as f:
                scripts = json.load(f)
        except FileNotFoundError:
            scripts = {}
        
        # Update script
        scripts[script_type] = script_content
        
        # Save scripts
        with open('call_scripts.json', 'w') as f:
            json.dump(scripts, f, indent=2)
        
        return jsonify({"success": True, "message": "Script updated successfully"})
        
    except Exception as e:
        logging.error(f"Error updating script: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
