import os

class Config:
    """Configuration class for the application"""
    
    # Flask configuration
    SECRET_KEY = os.environ.get("SESSION_SECRET", "fallback-secret-key-for-development")
    
    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///call_automation.db")
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    
    # Twilio configuration
    TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
    TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")
    
    # Google Sheets configuration
    GOOGLE_SHEETS_CREDENTIALS = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
    
    # Call automation settings
    CALL_RETRY_LIMIT = int(os.environ.get("CALL_RETRY_LIMIT", "3"))
    CALL_INTERVAL_SECONDS = int(os.environ.get("CALL_INTERVAL_SECONDS", "5"))
    
    # Logging configuration
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "DEBUG")
    
    @staticmethod
    def validate_environment():
        """Validate that required environment variables are set"""
        required_vars = [
            "TWILIO_ACCOUNT_SID",
            "TWILIO_AUTH_TOKEN", 
            "TWILIO_PHONE_NUMBER"
        ]
        
        missing_vars = []
        for var in required_vars:
            if not os.environ.get(var):
                missing_vars.append(var)
        
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        return True
