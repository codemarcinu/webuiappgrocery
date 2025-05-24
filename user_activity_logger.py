import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler
import json
from datetime import datetime
from typing import Any, Dict, Optional
from models import LogBledow, PoziomLogu
from database import SessionLocal
import traceback
import sys

def log_to_db(poziom: PoziomLogu, modul: str, funkcja: str, komunikat: str, szczegoly: str = None):
    """Helper function to log to database"""
    with SessionLocal() as db:
        log = LogBledow(
            poziom=poziom,
            modul_aplikacji=modul,
            funkcja=funkcja,
            komunikat_bledu=komunikat,
            szczegoly_techniczne=szczegoly
        )
        db.add(log)
        db.commit()

class UserActivityLogger:
    def __init__(self):
        self.logger = logging.getLogger("user_activity")
        self.logger.setLevel(logging.INFO)
        
        # Create logs directory if it doesn't exist
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Configure file handler for user activity
        activity_handler = RotatingFileHandler(
            log_dir / "user_activity.log",
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        activity_handler.setLevel(logging.INFO)
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        activity_handler.setFormatter(formatter)
        
        # Add handler to logger
        self.logger.addHandler(activity_handler)
        
        # Configure file handler for backend operations
        backend_handler = RotatingFileHandler(
            log_dir / "backend_operations.log",
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        backend_handler.setLevel(logging.INFO)
        backend_handler.setFormatter(formatter)
        
        # Add handler to logger
        self.logger.addHandler(backend_handler)

    def log_user_action(self, action: str, details: Dict[str, Any], user_id: Optional[int] = None):
        """Log user actions with details"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "user_id": user_id,
            "details": details
        }
        self.logger.info(f"User Action: {json.dumps(log_data)}")

    def log_backend_operation(self, operation: str, details: Dict[str, Any], status: str = "success"):
        """Log backend operations with details"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "status": status,
            "details": details
        }
        self.logger.info(f"Backend Operation: {json.dumps(log_data)}")

    def log_error(self, error: Exception, context: Dict[str, Any], level: PoziomLogu = PoziomLogu.ERROR):
        """Log errors with full context and stack trace"""
        error_data = {
            "timestamp": datetime.now().isoformat(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "stack_trace": traceback.format_exc(),
            "context": context
        }
        
        # Log to file
        self.logger.error(f"Error: {json.dumps(error_data)}")
        
        # Log to database
        try:
            log_to_db(
                level,
                "user_activity_logger",
                "log_error",
                f"Błąd: {str(error)}",
                json.dumps(error_data)
            )
        except Exception as e:
            self.logger.error(f"Failed to log error to database: {str(e)}")

    def log_receipt_processing(self, receipt_id: int, stage: str, details: Dict[str, Any]):
        """Log receipt processing stages"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "receipt_id": receipt_id,
            "stage": stage,
            "details": details
        }
        self.logger.info(f"Receipt Processing: {json.dumps(log_data)}")

    def log_ollama_operation(self, operation: str, details: Dict[str, Any], status: str = "success"):
        """Log Ollama model operations"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "status": status,
            "details": details
        }
        self.logger.info(f"Ollama Operation: {json.dumps(log_data)}")

# Create singleton instance
user_activity_logger = UserActivityLogger() 