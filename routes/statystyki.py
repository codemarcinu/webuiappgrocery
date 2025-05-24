from models import LogBledow, PoziomLogu
from database import SessionLocal
import json

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

@router.get("/statystyki/", response_model=Statystyki)
async def get_statistics(
    db: Session = Depends(get_db)
):
    """Get application statistics"""
    try:
        log_to_db(
            PoziomLogu.INFO,
            "routes.statystyki",
            "get_statistics",
            "Pobieranie statystyk aplikacji",
            json.dumps({
                "status": "started"
            })
        )
        
        total_products = db.query(Produkt).count()
        mapped_products = db.query(Produkt).filter(Produkt.status_mapowania == StatusMapowania.ZMAPOWANY).count()
        total_categories = db.query(Kategoria).count()
        total_receipts = db.query(Paragon).count()
        processed_receipts = db.query(Paragon).filter(Paragon.status == StatusParagonu.PRZETWORZONY).count()
        
        stats = Statystyki(
            laczna_liczba_produktow=total_products,
            liczba_zmapowanych_produktow=mapped_products,
            liczba_kategorii=total_categories,
            laczna_liczba_paragonow=total_receipts,
            liczba_przetworzonych_paragonow=processed_receipts
        )
        
        log_to_db(
            PoziomLogu.INFO,
            "routes.statystyki",
            "get_statistics",
            "Statystyki aplikacji pobrane pomyślnie",
            json.dumps({
                "total_products": total_products,
                "mapped_products": mapped_products,
                "total_categories": total_categories,
                "total_receipts": total_receipts,
                "processed_receipts": processed_receipts,
                "status": "completed"
            })
        )
        
        return stats
        
    except Exception as e:
        log_to_db(
            PoziomLogu.ERROR,
            "routes.statystyki",
            "get_statistics",
            "Błąd pobierania statystyk aplikacji",
            json.dumps({
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": str(e.__traceback__)
            })
        )
        raise

@router.get("/statystyki/kategorie/", response_model=List[StatystykiKategorii])
async def get_category_statistics(
    db: Session = Depends(get_db)
):
    """Get statistics for each category"""
    try:
        log_to_db(
            PoziomLogu.INFO,
            "routes.statystyki",
            "get_category_statistics",
            "Pobieranie statystyk kategorii",
            json.dumps({
                "status": "started"
            })
        )
        
        categories = db.query(Kategoria).all()
        stats = []
        
        for category in categories:
            product_count = db.query(Produkt).filter(Produkt.kategoria == category.nazwa).count()
            stats.append(StatystykiKategorii(
                kategoria=category.nazwa,
                liczba_produktow=product_count
            ))
        
        log_to_db(
            PoziomLogu.INFO,
            "routes.statystyki",
            "get_category_statistics",
            "Statystyki kategorii pobrane pomyślnie",
            json.dumps({
                "category_count": len(categories),
                "status": "completed"
            })
        )
        
        return stats
        
    except Exception as e:
        log_to_db(
            PoziomLogu.ERROR,
            "routes.statystyki",
            "get_category_statistics",
            "Błąd pobierania statystyk kategorii",
            json.dumps({
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": str(e.__traceback__)
            })
        )
        raise 