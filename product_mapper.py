from typing import List, Dict, Any, Optional
import json
from thefuzz import process
from sqlmodel import Session, select
from models import Produkt, StatusMapowania, LogBledow, PoziomLogu
from db_logger import log_to_db
from database import SessionLocal

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

class ProductMapper:
    def __init__(self, session=None):
        self.session = session or SessionLocal()
        self.fuzzy_threshold = 80  # Minimum similarity score to consider a match

    def find_suggestions(self, product_name: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Find similar products in the pantry using fuzzy matching"""
        # Get all products from pantry (those without paragon_id)
        pantry_products = self.session.exec(
            select(Produkt).where(Produkt.paragon_id.is_(None))
        ).all()
        
        # Get product names for fuzzy matching
        product_names = [p.nazwa for p in pantry_products]
        
        # Find matches using fuzzy matching
        matches = process.extract(
            product_name,
            product_names,
            limit=limit,
            score_cutoff=self.fuzzy_threshold
        )
        
        # Convert matches to product objects with similarity scores
        suggestions = []
        for name, score in matches:
            product = next(p for p in pantry_products if p.nazwa == name)
            suggestions.append({
                "id": product.id,
                "nazwa": product.nazwa,
                "kategoria": product.kategoria,
                "podobienstwo": score
            })
        
        return suggestions

    def update_product_mapping(self, receipt_product_id: int, pantry_product_id: Optional[int] = None) -> None:
        """Update product mapping status and relationship"""
        receipt_product = self.session.get(Produkt, receipt_product_id)
        if not receipt_product:
            raise ValueError("Receipt product not found")
            
        if pantry_product_id:
            pantry_product = self.session.get(Produkt, pantry_product_id)
            if not pantry_product:
                raise ValueError("Pantry product not found")
                
            receipt_product.zmapowany_do_id = pantry_product_id
            receipt_product.status_mapowania = StatusMapowania.ZMAPOWANY
        else:
            receipt_product.zmapowany_do_id = None
            receipt_product.status_mapowania = StatusMapowania.NOWY
            
        self.session.add(receipt_product)
        self.session.commit()

    def ignore_product(self, receipt_product_id: int) -> None:
        """Mark a product as ignored"""
        receipt_product = self.session.get(Produkt, receipt_product_id)
        if not receipt_product:
            raise ValueError("Receipt product not found")
            
        receipt_product.status_mapowania = StatusMapowania.IGNOROWANY
        receipt_product.zmapowany_do_id = None
        self.session.add(receipt_product)
        self.session.commit()

    def process_receipt_products(self, receipt_products: List[Produkt]) -> None:
        """Process all products from a receipt and find mapping suggestions"""
        try:
            log_to_db(
                PoziomLogu.INFO,
                "product_mapper",
                "process_receipt_products",
                "Rozpoczęcie mapowania produktów z paragonu",
                json.dumps({
                    "products_count": len(receipt_products),
                    "status": "started"
                })
            )
            
            for product in receipt_products:
                suggestions = self.find_suggestions(product.nazwa)
                product.sugestie_mapowania = json.dumps(suggestions)
                self.session.add(product)
            
            self.session.commit()
            
            log_to_db(
                PoziomLogu.INFO,
                "product_mapper",
                "process_receipt_products",
                "Mapowanie produktów zakończone pomyślnie",
                json.dumps({
                    "products_count": len(receipt_products),
                    "status": "completed"
                })
            )
            
        except Exception as e:
            log_to_db(
                PoziomLogu.ERROR,
                "product_mapper",
                "process_receipt_products",
                "Błąd mapowania produktów",
                json.dumps({
                    "products_count": len(receipt_products),
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "traceback": str(e.__traceback__)
                })
            )
            raise 