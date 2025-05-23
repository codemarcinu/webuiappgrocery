from celery_app import celery_app
from database import SessionLocal
from models import Paragon, StatusParagonu
from receipt_processor import ReceiptProcessor
from datetime import datetime
from logging_config import logger
from pathlib import Path

receipt_processor = ReceiptProcessor()

@celery_app.task(bind=True, name='process_receipt')
def process_receipt_task(self, paragon_id: int):
    """Celery task for processing a receipt"""
    db = SessionLocal()
    try:
        paragon = db.query(Paragon).get(paragon_id)
        if not paragon:
            logger.error(f"Paragon {paragon_id} not found")
            return
        
        # Update status to processing
        paragon.status_przetwarzania = StatusParagonu.PRZETWARZANY_OCR
        db.commit()
        
        try:
            # Process the receipt using ReceiptProcessor
            result = receipt_processor.process_receipt(Path(paragon.sciezka_pliku_na_serwerze))
            
            # Update status to success
            paragon.status_przetwarzania = StatusParagonu.PRZETWORZONY_OK
            paragon.data_przetworzenia = datetime.now()
            db.commit()
            
            return {"status": "success", "paragon_id": paragon_id}
            
        except Exception as e:
            # Update status to error
            paragon.status_przetwarzania = StatusParagonu.PRZETWORZONY_BLAD
            paragon.blad_przetwarzania = str(e)
            paragon.data_przetworzenia = datetime.now()
            db.commit()
            logger.error(f"Error processing receipt {paragon_id}: {str(e)}", exc_info=True)
            raise
            
    except Exception as e:
        logger.error(f"Unexpected error in Celery task: {str(e)}", exc_info=True)
        raise
    finally:
        db.close() 