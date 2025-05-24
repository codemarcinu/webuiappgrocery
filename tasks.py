from celery_app import celery_app
from database import SessionLocal
from models import Paragon, StatusParagonu, Produkt, KategoriaProduktu, StatusMapowania
from receipt_processor import ReceiptProcessor
from datetime import datetime
from logging_config import logger
from pathlib import Path
from decimal import Decimal
from product_mapper import ProductMapper
import json
import asyncio

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
            # Process the receipt using ReceiptProcessor (now async)
            result = asyncio.run(receipt_processor.process_receipt(Path(paragon.sciezka_pliku_na_serwerze)))
            
            # Clear existing products for this receipt
            existing_products = db.query(Produkt).filter(Produkt.paragon_id == paragon.id).all()
            for prod in existing_products:
                db.delete(prod)
            db.commit()
            
            # Add new products from LLM result
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
            paragon.data_przetworzenia = datetime.now()
            db.commit()
            
            return {"status": "success", "paragon_id": paragon_id, "message": "Receipt processed successfully with local OCR and LLM"}
            
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