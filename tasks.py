import multiprocessing
# Set multiprocessing start method to 'spawn' for CUDA compatibility
multiprocessing.set_start_method('spawn', force=True)

from celery import Celery, shared_task
from database import SessionLocal
from models import Paragon, StatusParagonu, Produkt, KategoriaProduktu, StatusMapowania
from receipt_processor import ReceiptProcessor
from datetime import datetime
from logging_config import logger
from pathlib import Path
from decimal import Decimal
from product_mapper import ProductMapper
from ollama_client import OllamaError, OllamaTimeoutError, OllamaConnectionError, OllamaModelError
from config import get_settings
from user_activity_logger import user_activity_logger
import json
import asyncio

settings = get_settings()

# Initialize Celery
celery = Celery('tasks',
                broker=settings.CELERY_BROKER_URL,
                backend=settings.CELERY_RESULT_BACKEND)

# Configure Celery
celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Europe/Warsaw',
    enable_utc=True,
)

receipt_processor = ReceiptProcessor()

@shared_task(name='process_receipt', bind=True)
def process_receipt_task(self, paragon_id: int):
    """Celery task for processing a receipt"""
    db = SessionLocal()
    try:
        paragon = db.query(Paragon).get(paragon_id)
        if not paragon:
            logger.error(f"Paragon {paragon_id} not found")
            user_activity_logger.log_error(
                Exception(f"Paragon {paragon_id} not found"),
                {"module": "tasks", "function": "process_receipt_task", "paragon_id": paragon_id}
            )
            return
        
        # Update status to OCR processing
        paragon.status_przetwarzania = StatusParagonu.PRZETWARZANY_OCR
        paragon.status_szczegolowy = "Rozpoczęto przetwarzanie OCR..."
        db.commit()
        logger.info(f"Rozpoczęto OCR dla paragonu {paragon_id}")
        user_activity_logger.log_receipt_processing(
            paragon_id,
            "OCR_START",
            {"status": "started", "file_path": paragon.sciezka_pliku_na_serwerze}
        )
        
        try:
            # Process the receipt using ReceiptProcessor (now async)
            paragon.status_szczegolowy = "Wykonywanie OCR i ekstrakcja tekstu..."
            db.commit()
            user_activity_logger.log_receipt_processing(
                paragon_id,
                "OCR_IN_PROGRESS",
                {"status": "processing", "stage": "text_extraction"}
            )
            
            result = asyncio.run(receipt_processor.process_receipt(Path(paragon.sciezka_pliku_na_serwerze)))
            
            # Update status to AI processing
            paragon.status_przetwarzania = StatusParagonu.PRZETWARZANY_AI
            paragon.status_szczegolowy = "Strukturyzacja danych z OCR zakończona, przygotowywanie produktów..."
            db.commit()
            logger.info(f"OCR zakończony dla paragonu {paragon_id}, rozpoczynam analizę AI")
            user_activity_logger.log_receipt_processing(
                paragon_id,
                "OCR_COMPLETE",
                {"status": "completed", "items_found": len(result.get("items", []))}
            )
            
            # Clear existing products for this receipt
            existing_products = db.query(Produkt).filter(Produkt.paragon_id == paragon.id).all()
            for prod in existing_products:
                db.delete(prod)
            db.commit()
            
            # Add new products from LLM result
            paragon.status_szczegolowy = "Dodawanie wykrytych produktów do bazy danych..."
            db.commit()
            all_new_products = []
            for item_data in result.get("items", []):
                kategoria_str = item_data.get("category")
                produkt_kategoria = KategoriaProduktu.INNE
                if kategoria_str:
                    try:
                        # Try to match the category string to enum values
                        temp_kategoria_str = kategoria_str.strip().upper().replace(" ", "_")
                        produkt_kategoria = KategoriaProduktu[temp_kategoria_str] if temp_kategoria_str in KategoriaProduktu.__members__ else KategoriaProduktu(kategoria_str)
                    except ValueError:
                        # Try more flexible matching
                        found_category = False
                        for enum_member in KategoriaProduktu:
                            if enum_member.value.lower() == kategoria_str.strip().lower():
                                produkt_kategoria = enum_member
                                found_category = True
                                break
                        if not found_category:
                            logger.warning(f"Unknown category '{kategoria_str}' from LLM for product '{item_data['name']}'. Defaulting to INNE.")
                
                new_product = Produkt(
                    nazwa=item_data['name'],
                    kategoria=produkt_kategoria,
                    cena=Decimal(str(item_data['price'])),
                    paragon_id=paragon.id,
                    ilosc_na_paragonie=int(item_data.get('quantity', 1)),  # Default to 1 if not specified
                    aktualna_ilosc=0,
                    status_mapowania=StatusMapowania.OCZEKUJE
                )
                db.add(new_product)
                all_new_products.append(new_product)
            db.commit()
            
            # Call ProductMapper for mapping suggestions
            paragon.status_szczegolowy = "Generowanie sugestii mapowania produktów i kategorii..."
            db.commit()
            product_mapper = ProductMapper(session=db)
            product_mapper.process_receipt_products(all_new_products)
            
            # Update receipt metadata if available
            if result.get("store_name"):
                paragon.sklep = result["store_name"]
            if result.get("date"):
                paragon.data_zakupu = datetime.strptime(result["date"], "%Y-%m-%d").date()
            if result.get("total_amount"):
                paragon.suma_calkowita = Decimal(str(result["total_amount"]))
            
            # Update status to success
            paragon.status_przetwarzania = StatusParagonu.PRZETWORZONY_OK
            paragon.status_szczegolowy = "Przetwarzanie zakończone pomyślnie. Wszystkie produkty zostały wykryte i skategoryzowane."
            paragon.data_przetworzenia = datetime.now()
            db.commit()
            logger.info(f"Paragon {paragon_id} przetworzony pomyślnie")
            user_activity_logger.log_receipt_processing(
                paragon_id,
                "PROCESSING_COMPLETE",
                {
                    "status": "success",
                    "products_count": len(all_new_products),
                    "store_name": result.get("store_name"),
                    "total_amount": str(result.get("total_amount"))
                }
            )
            
            return {"status": "success", "paragon_id": paragon_id, "message": "Receipt processed successfully with local OCR and LLM"}
            
        except OllamaConnectionError as e:
            # Handle Ollama connection issues
            paragon.status_przetwarzania = StatusParagonu.PRZETWORZONY_BLAD
            paragon.status_szczegolowy = "Błąd połączenia z usługą Ollama. Sprawdź, czy usługa jest uruchomiona."
            paragon.blad_przetwarzania = str(e)
            paragon.data_przetworzenia = datetime.now()
            db.commit()
            logger.error(f"Ollama connection error for receipt {paragon_id}: {str(e)}", exc_info=True)
            user_activity_logger.log_error(
                e,
                {
                    "module": "tasks",
                    "function": "process_receipt_task",
                    "paragon_id": paragon_id,
                    "error_type": "OllamaConnectionError"
                }
            )
            raise
            
        except OllamaModelError as e:
            # Handle model availability issues
            paragon.status_przetwarzania = StatusParagonu.PRZETWORZONY_BLAD
            paragon.status_szczegolowy = "Błąd modelu Ollama. Sprawdź konfigurację i dostępność modelu."
            paragon.blad_przetwarzania = str(e)
            paragon.data_przetworzenia = datetime.now()
            db.commit()
            logger.error(f"Ollama model error for receipt {paragon_id}: {str(e)}", exc_info=True)
            user_activity_logger.log_error(
                e,
                {
                    "module": "tasks",
                    "function": "process_receipt_task",
                    "paragon_id": paragon_id,
                    "error_type": "OllamaModelError"
                }
            )
            raise
            
        except OllamaTimeoutError as e:
            # Handle timeout issues
            paragon.status_przetwarzania = StatusParagonu.PRZETWORZONY_BLAD
            paragon.status_szczegolowy = "Przekroczono czas oczekiwania na odpowiedź Ollama. Spróbuj ponownie później."
            paragon.blad_przetwarzania = str(e)
            paragon.data_przetworzenia = datetime.now()
            db.commit()
            logger.error(f"Ollama timeout error for receipt {paragon_id}: {str(e)}", exc_info=True)
            user_activity_logger.log_error(
                e,
                {
                    "module": "tasks",
                    "function": "process_receipt_task",
                    "paragon_id": paragon_id,
                    "error_type": "OllamaTimeoutError"
                }
            )
            raise
            
        except OllamaError as e:
            # Handle other Ollama-related errors
            paragon.status_przetwarzania = StatusParagonu.PRZETWORZONY_BLAD
            paragon.status_szczegolowy = "Wystąpił błąd podczas komunikacji z Ollama."
            paragon.blad_przetwarzania = str(e)
            paragon.data_przetworzenia = datetime.now()
            db.commit()
            logger.error(f"Ollama error for receipt {paragon_id}: {str(e)}", exc_info=True)
            user_activity_logger.log_error(
                e,
                {
                    "module": "tasks",
                    "function": "process_receipt_task",
                    "paragon_id": paragon_id,
                    "error_type": "OllamaError"
                }
            )
            raise
            
        except Exception as e:
            # Handle all other errors
            paragon.status_przetwarzania = StatusParagonu.PRZETWORZONY_BLAD
            paragon.status_szczegolowy = f"Wystąpił nieoczekiwany błąd podczas przetwarzania."
            paragon.blad_przetwarzania = str(e)
            paragon.data_przetworzenia = datetime.now()
            db.commit()
            logger.error(f"Error processing receipt {paragon_id}: {str(e)}", exc_info=True)
            user_activity_logger.log_error(
                e,
                {
                    "module": "tasks",
                    "function": "process_receipt_task",
                    "paragon_id": paragon_id,
                    "error_type": "UnexpectedError"
                }
            )
            raise
            
    except Exception as e:
        logger.error(f"Unexpected error in Celery task: {str(e)}", exc_info=True)
        user_activity_logger.log_error(
            e,
            {
                "module": "tasks",
                "function": "process_receipt_task",
                "paragon_id": paragon_id,
                "error_type": "CeleryTaskError"
            }
        )
        raise
    finally:
        db.close() 