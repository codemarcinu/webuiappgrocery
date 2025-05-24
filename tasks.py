import logging.config
from logging_config import LOGGING_CONFIG
logging.config.dictConfig(LOGGING_CONFIG)

import multiprocessing
# Set multiprocessing start method to 'spawn' for CUDA compatibility
multiprocessing.set_start_method('spawn', force=True)

from celery import Celery, shared_task
from db_logger import log_to_db
from database import SessionLocal
from models import Paragon, StatusParagonu, Produkt, KategoriaProduktu, StatusMapowania, LogBledow, PoziomLogu
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

@shared_task(name='process_receipt', bind=True)
def process_receipt_task(self, paragon_id: int):
    """Celery task for processing a receipt"""
    db = SessionLocal()
    try:
        paragon = db.query(Paragon).get(paragon_id)
        if not paragon:
            log_to_db(
                PoziomLogu.ERROR,
                "tasks",
                "process_receipt_task",
                f"Paragon {paragon_id} not found",
                json.dumps({"paragon_id": paragon_id})
            )
            return
        
        # Update status to OCR processing
        paragon.status_przetwarzania = StatusParagonu.PRZETWARZANY_OCR
        paragon.status_szczegolowy = "Rozpoczęto przetwarzanie OCR..."
        db.commit()
        
        log_to_db(
            PoziomLogu.INFO,
            "tasks",
            "process_receipt_task",
            f"Rozpoczęto OCR dla paragonu {paragon_id}",
            json.dumps({
                "paragon_id": paragon_id,
                "file_path": paragon.sciezka_pliku_na_serwerze,
                "status": "started"
            })
        )
        
        try:
            # Process the receipt using ReceiptProcessor (now async)
            paragon.status_szczegolowy = "Wykonywanie OCR i ekstrakcja tekstu..."
            db.commit()
            
            log_to_db(
                PoziomLogu.INFO,
                "tasks",
                "process_receipt_task",
                f"Wykonywanie OCR dla paragonu {paragon_id}",
                json.dumps({
                    "paragon_id": paragon_id,
                    "stage": "text_extraction",
                    "status": "processing"
                })
            )
            
            result = asyncio.run(receipt_processor.process_receipt(Path(paragon.sciezka_pliku_na_serwerze)))
            
            # Update status to AI processing
            paragon.status_przetwarzania = StatusParagonu.PRZETWARZANY_AI
            paragon.status_szczegolowy = "Strukturyzacja danych z OCR zakończona, przygotowywanie produktów..."
            db.commit()
            
            log_to_db(
                PoziomLogu.INFO,
                "tasks",
                "process_receipt_task",
                f"OCR zakończony dla paragonu {paragon_id}, rozpoczynam analizę AI",
                json.dumps({
                    "paragon_id": paragon_id,
                    "items_found": len(result.get("items", [])),
                    "status": "completed"
                })
            )
            
            # Clear existing products for this receipt
            existing_products = db.query(Produkt).filter(Produkt.paragon_id == paragon.id).all()
            for prod in existing_products:
                db.delete(prod)
            db.commit()
            
            # Add new products from LLM result
            paragon.status_szczegolowy = "Dodawanie wykrytych produktów do bazy danych..."
            db.commit()
            
            log_to_db(
                PoziomLogu.INFO,
                "tasks",
                "process_receipt_task",
                f"Dodawanie produktów do bazy dla paragonu {paragon_id}",
                json.dumps({
                    "paragon_id": paragon_id,
                    "stage": "adding_products",
                    "status": "processing"
                })
            )
            
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
                            log_to_db(
                                PoziomLogu.WARNING,
                                "tasks",
                                "process_receipt_task",
                                f"Nieznana kategoria '{kategoria_str}' dla produktu '{item_data['name']}'",
                                json.dumps({
                                    "paragon_id": paragon_id,
                                    "product_name": item_data['name'],
                                    "category": kategoria_str
                                })
                            )
                
                new_product = Produkt(
                    nazwa=item_data['name'],
                    kategoria=produkt_kategoria,
                    cena=Decimal(str(item_data['price'])),
                    paragon_id=paragon.id,
                    ilosc_na_paragonie=int(item_data.get('quantity', 1)),
                    aktualna_ilosc=0,
                    status_mapowania=StatusMapowania.OCZEKUJE
                )
                db.add(new_product)
                all_new_products.append(new_product)
            db.commit()
            
            # Call ProductMapper for mapping suggestions
            paragon.status_szczegolowy = "Generowanie sugestii mapowania produktów i kategorii..."
            db.commit()
            
            log_to_db(
                PoziomLogu.INFO,
                "tasks",
                "process_receipt_task",
                f"Generowanie sugestii mapowania dla paragonu {paragon_id}",
                json.dumps({
                    "paragon_id": paragon_id,
                    "stage": "mapping_suggestions",
                    "status": "processing",
                    "products_count": len(all_new_products)
                })
            )
            
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
            
            log_to_db(
                PoziomLogu.INFO,
                "tasks",
                "process_receipt_task",
                f"Paragon {paragon_id} przetworzony pomyślnie",
                json.dumps({
                    "paragon_id": paragon_id,
                    "status": "success",
                    "products_count": len(all_new_products),
                    "store_name": result.get("store_name"),
                    "total_amount": str(result.get("total_amount"))
                })
            )
            
            return {"status": "success", "paragon_id": paragon_id, "message": "Receipt processed successfully with local OCR and LLM"}
            
        except OllamaConnectionError as e:
            paragon.status_przetwarzania = StatusParagonu.PRZETWORZONY_BLAD
            paragon.status_szczegolowy = "Błąd połączenia z usługą Ollama. Sprawdź, czy usługa jest uruchomiona."
            paragon.blad_przetwarzania = str(e)
            paragon.data_przetworzenia = datetime.now()
            db.commit()
            
            log_to_db(
                PoziomLogu.ERROR,
                "tasks",
                "process_receipt_task",
                f"Błąd połączenia z Ollama dla paragonu {paragon_id}",
                json.dumps({
                    "paragon_id": paragon_id,
                    "error_type": "OllamaConnectionError",
                    "error_message": str(e),
                    "traceback": str(e.__traceback__)
                })
            )
            raise
            
        except OllamaModelError as e:
            paragon.status_przetwarzania = StatusParagonu.PRZETWORZONY_BLAD
            paragon.status_szczegolowy = "Błąd modelu Ollama. Sprawdź konfigurację i dostępność modelu."
            paragon.blad_przetwarzania = str(e)
            paragon.data_przetworzenia = datetime.now()
            db.commit()
            
            log_to_db(
                PoziomLogu.ERROR,
                "tasks",
                "process_receipt_task",
                f"Błąd modelu Ollama dla paragonu {paragon_id}",
                json.dumps({
                    "paragon_id": paragon_id,
                    "error_type": "OllamaModelError",
                    "error_message": str(e),
                    "traceback": str(e.__traceback__)
                })
            )
            raise
            
        except OllamaTimeoutError as e:
            paragon.status_przetwarzania = StatusParagonu.PRZETWORZONY_BLAD
            paragon.status_szczegolowy = "Przekroczono czas oczekiwania na odpowiedź Ollama. Spróbuj ponownie później."
            paragon.blad_przetwarzania = str(e)
            paragon.data_przetworzenia = datetime.now()
            db.commit()
            
            log_to_db(
                PoziomLogu.ERROR,
                "tasks",
                "process_receipt_task",
                f"Timeout Ollama dla paragonu {paragon_id}",
                json.dumps({
                    "paragon_id": paragon_id,
                    "error_type": "OllamaTimeoutError",
                    "error_message": str(e),
                    "traceback": str(e.__traceback__)
                })
            )
            raise
            
        except OllamaError as e:
            paragon.status_przetwarzania = StatusParagonu.PRZETWORZONY_BLAD
            paragon.status_szczegolowy = "Wystąpił błąd podczas komunikacji z Ollama."
            paragon.blad_przetwarzania = str(e)
            paragon.data_przetworzenia = datetime.now()
            db.commit()
            
            log_to_db(
                PoziomLogu.ERROR,
                "tasks",
                "process_receipt_task",
                f"Błąd Ollama dla paragonu {paragon_id}",
                json.dumps({
                    "paragon_id": paragon_id,
                    "error_type": "OllamaError",
                    "error_message": str(e),
                    "traceback": str(e.__traceback__)
                })
            )
            raise
            
        except Exception as e:
            paragon.status_przetwarzania = StatusParagonu.PRZETWORZONY_BLAD
            paragon.status_szczegolowy = f"Wystąpił nieoczekiwany błąd podczas przetwarzania."
            paragon.blad_przetwarzania = str(e)
            paragon.data_przetworzenia = datetime.now()
            db.commit()
            
            log_to_db(
                PoziomLogu.ERROR,
                "tasks",
                "process_receipt_task",
                f"Nieoczekiwany błąd przetwarzania paragonu {paragon_id}",
                json.dumps({
                    "paragon_id": paragon_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "traceback": str(e.__traceback__)
                })
            )
            raise
            
    except Exception as e:
        log_to_db(
            PoziomLogu.ERROR,
            "tasks",
            "process_receipt_task",
            f"Błąd w zadaniu Celery dla paragonu {paragon_id}",
            json.dumps({
                "paragon_id": paragon_id,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": str(e.__traceback__)
            })
        )
        raise
    finally:
        db.close() 