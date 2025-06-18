from app import db
from datetime import datetime

class CallLog(db.Model):
    """Model for storing call logs"""
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), nullable=False)
    caller_name = db.Column(db.String(100))
    call_status = db.Column(db.String(20), nullable=False)  # Not Called, Connected, Disconnected, Forwarded, Accepted
    call_sid = db.Column(db.String(100))  # Twilio Call SID
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime)
    duration = db.Column(db.Integer)  # Duration in seconds
    response = db.Column(db.String(20))  # Accept, Forward, Reject
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<CallLog {self.phone_number}: {self.call_status}>'

    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'phone_number': self.phone_number,
            'caller_name': self.caller_name,
            'call_status': self.call_status,
            'call_sid': self.call_sid,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration': self.duration,
            'response': self.response,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class CallQueue(db.Model):
    """Model for storing call queue"""
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), nullable=False)
    caller_name = db.Column(db.String(100))
    priority = db.Column(db.Integer, default=1)
    status = db.Column(db.String(20), default='Not Called')
    assigned_script = db.Column(db.String(50), default='default')
    scheduled_time = db.Column(db.DateTime)
    attempts = db.Column(db.Integer, default=0)
    max_attempts = db.Column(db.Integer, default=3)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<CallQueue {self.phone_number}: {self.status}>'

    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'phone_number': self.phone_number,
            'caller_name': self.caller_name,
            'priority': self.priority,
            'status': self.status,
            'assigned_script': self.assigned_script,
            'scheduled_time': self.scheduled_time.isoformat() if self.scheduled_time else None,
            'attempts': self.attempts,
            'max_attempts': self.max_attempts,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
