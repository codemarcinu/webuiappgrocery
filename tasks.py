import logging.config
from logging_config import LOGGING_CONFIG
logging.config.dictConfig(LOGGING_CONFIG)

import multiprocessing
# Set multiprocessing start method to 'spawn' for CUDA compatibility
multiprocessing.set_start_method('spawn', force=True)

from celery import Celery, shared_task
from db_logger import log_to_db
from database import SessionLocal, engine, create_db_and_tables
from models import Paragon, StatusParagonu, Produkt, KategoriaProduktu, StatusMapowania, LogBledow, PoziomLogu
from receipt_processor import ReceiptProcessor
from datetime import datetime
import logging
logger = logging.getLogger(__name__)
from pathlib import Path
from decimal import Decimal
from product_mapper import ProductMapper
from ollama_client import OllamaError, OllamaTimeoutError, OllamaConnectionError, OllamaModelError
from config import get_settings
from user_activity_logger import user_activity_logger
import json
import asyncio
from celery.signals import worker_process_init
from sqlmodel import SQLModel
from sqlalchemy.orm import Session
from contextlib import contextmanager

settings = get_settings()

# Initialize Celery
celery_app = Celery('tasks',
                    broker=settings.CELERY_BROKER_URL,
                    backend=settings.CELERY_RESULT_BACKEND)

# Configure Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Europe/Warsaw',
    enable_utc=True,
)

receipt_processor = ReceiptProcessor()

@worker_process_init.connect
def init_worker(**kwargs):
    """Initialize worker process"""
    try:
        # Create database tables in worker process
        create_db_and_tables()
        logger.info("Database tables created in worker process")
    except Exception as e:
        logger.error(f"Error initializing worker: {str(e)}", exc_info=True)
        raise

@contextmanager
def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def log_to_db(poziom: PoziomLogu, modul: str, funkcja: str, komunikat: str, szczegoly: str = None):
    """Helper function to log to database"""
    try:
        with get_db() as db:
            log = LogBledow(
                poziom=poziom,
                modul_aplikacji=modul,
                funkcja=funkcja,
                komunikat_bledu=komunikat,
                szczegoly_techniczne=szczegoly
            )
            db.add(log)
            db.commit()
    except Exception as e:
        logger.error(f"Failed to log to database: {str(e)}", exc_info=True)

@shared_task(name='process_receipt', bind=True)
def process_receipt_task(self, paragon_id: int):
    """Celery task for processing a receipt"""
    try:
        # Initialize database session
        from database import SessionLocal, create_db_and_tables
        create_db_and_tables()  # Ensure tables exist
        
        with SessionLocal() as db:
            # Get receipt
            paragon = db.query(Paragon).filter(Paragon.id == paragon_id).first()
            if not paragon:
                logger.error(f"Receipt {paragon_id} not found")
                return {"status": "error", "message": "Receipt not found"}

            try:
                # Process receipt
                result = asyncio.run(receipt_processor.process_receipt(Path(paragon.sciezka_pliku_na_serwerze)))
                
                # Update receipt status
                paragon.status_przetwarzania = StatusParagonu.PRZETWORZONY
                paragon.status_szczegolowy = "Paragon przetworzony pomyślnie"
                paragon.data_przetworzenia = datetime.now()
                db.commit()
                
                return {"status": "success", "paragon_id": paragon_id, "message": "Receipt processed successfully"}
                
            except Exception as e:
                # Log error and update receipt status
                logger.error(f"Error processing receipt {paragon_id}: {str(e)}", exc_info=True)
                paragon.status_przetwarzania = StatusParagonu.PRZETWORZONY_BLAD
                paragon.status_szczegolowy = f"Błąd przetwarzania: {str(e)}"
                paragon.blad_przetwarzania = str(e)
                paragon.data_przetworzenia = datetime.now()
                db.commit()
                
                return {"status": "error", "paragon_id": paragon_id, "message": str(e)}
                
    except Exception as e:
        logger.error(f"Unexpected error in process_receipt_task: {str(e)}", exc_info=True)
        return {"status": "error", "message": f"Unexpected error: {str(e)}"} 