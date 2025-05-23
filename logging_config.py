import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
import os

# Create logs directory if it doesn't exist
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

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

    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

# Create logger instance
logger = setup_logging() 