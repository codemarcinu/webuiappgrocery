import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
import os
from models import LogBledow, PoziomLogu
from database import SessionLocal
import json

# Create logs directory if it doesn't exist
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

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

class DatabaseHandler(logging.Handler):
    """Custom logging handler that writes to database"""
    def emit(self, record):
        try:
            # Map logging levels to PoziomLogu
            level_map = {
                logging.DEBUG: PoziomLogu.DEBUG,
                logging.INFO: PoziomLogu.INFO,
                logging.WARNING: PoziomLogu.WARNING,
                logging.ERROR: PoziomLogu.ERROR,
                logging.CRITICAL: PoziomLogu.CRITICAL
            }
            
            poziom = level_map.get(record.levelno, PoziomLogu.INFO)
            
            log_to_db(
                poziom,
                record.module,
                record.funcName,
                record.getMessage(),
                json.dumps({
                    "level": record.levelname,
                    "pathname": record.pathname,
                    "lineno": record.lineno,
                    "exc_info": str(record.exc_info) if record.exc_info else None,
                    "args": str(record.args) if record.args else None
                })
            )
        except Exception as e:
            # If logging fails, at least print to console
            print(f"Failed to log to database: {str(e)}")

# Configure logging
def setup_logging():
    # Create logger
    logger = logging.getLogger("spizarnia")
    logger.setLevel(logging.INFO)

    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_formatter = logging.Formatter(
        '%(levelname)s: %(message)s'
    )

    # Create and configure file handler
    file_handler = RotatingFileHandler(
        log_dir / "spizarnia.log",
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(file_formatter)

    # Create and configure console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)

    # Add database handler
    db_handler = DatabaseHandler()
    db_handler.setLevel(logging.INFO)
    logger.addHandler(db_handler)

    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

# Create logger instance
logger = setup_logging() 