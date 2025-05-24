from pydantic_settings import BaseSettings
from typing import List
import os
import secrets
from functools import lru_cache
import json
import logging

# Set up logging first
logger = logging.getLogger(__name__)

# Import database and models after logging is set up
from database import create_db_and_tables
from models import LogBledow, PoziomLogu
from db_logger import log_to_db

# Create database tables after logging is set up
create_db_and_tables()

class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Webowy Asystent Spiżarni"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
    ALLOWED_HOSTS: List[str] = ["*"] if os.getenv("ENVIRONMENT") == "development" else ["yourdomain.com"]
    ALLOWED_ORIGINS: List[str] = ["http://localhost:8000"]
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./spizarnia.db")
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    DB_POOL_TIMEOUT: float = float(os.getenv("DB_POOL_TIMEOUT", "30"))
    DB_POOL_RECYCLE: float = float(os.getenv("DB_POOL_RECYCLE", "1800"))
    SQL_ECHO: bool = os.getenv("SQL_ECHO", "false").lower() == "true"
    
    # File Upload
    UPLOAD_FOLDER: str = "uploads"
    MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024  # 16MB
    ALLOWED_EXTENSIONS: List[str] = ["jpg", "jpeg", "png", "gif", "pdf"]
    
    # Ollama
    OLLAMA_API_URL: str = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "bielik-local-q8")
    OLLAMA_TIMEOUT: int = int(os.getenv("OLLAMA_TIMEOUT", "30"))
    
    # Celery
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_FILE: str = "logs/app.log"
    
    def __init__(self, **kwargs):
        try:
            log_to_db(
                PoziomLogu.INFO,
                "config",
                "Settings.__init__",
                "Inicjalizacja konfiguracji aplikacji",
                json.dumps({"status": "started"})
            )
            
            super().__init__(**kwargs)
            
            log_to_db(
                PoziomLogu.INFO,
                "config",
                "Settings.__init__",
                "Konfiguracja aplikacji zainicjalizowana pomyślnie",
                json.dumps({
                    "status": "completed",
                    "settings": {
                        "OLLAMA_API_URL": self.OLLAMA_API_URL,
                        "OLLAMA_MODEL": self.OLLAMA_MODEL,
                        "UPLOAD_FOLDER": self.UPLOAD_FOLDER,
                        "MAX_CONTENT_LENGTH": self.MAX_CONTENT_LENGTH
                    }
                })
            )
            
        except Exception as e:
            log_to_db(
                PoziomLogu.ERROR,
                "config",
                "Settings.__init__",
                "Błąd inicjalizacji konfiguracji aplikacji",
                json.dumps({
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "traceback": str(e.__traceback__)
                })
            )
            raise

@lru_cache()
def get_settings() -> Settings:
    """Get application settings"""
    return Settings() 