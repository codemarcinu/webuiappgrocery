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

@router.get("/mapowanie/", response_model=List[Produkt])
async def get_mapping_products(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get products that need mapping"""
    try:
        log_to_db(
            PoziomLogu.INFO,
            "routes.mapowanie",
            "get_mapping_products",
            "Pobieranie produktów do mapowania",
            json.dumps({
                "skip": skip,
                "limit": limit,
                "status": "started"
            })
        )
        
        products = db.query(Produkt).filter(Produkt.status_mapowania == StatusMapowania.OCZEKUJE).offset(skip).limit(limit).all()
        
        log_to_db(
            PoziomLogu.INFO,
            "routes.mapowanie",
            "get_mapping_products",
            "Produkty do mapowania pobrane pomyślnie",
            json.dumps({
                "skip": skip,
                "limit": limit,
                "count": len(products),
                "status": "completed"
            })
        )
        
        return products
        
    except Exception as e:
        log_to_db(
            PoziomLogu.ERROR,
            "routes.mapowanie",
            "get_mapping_products",
            "Błąd pobierania produktów do mapowania",
            json.dumps({
                "skip": skip,
                "limit": limit,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": str(e.__traceback__)
            })
        )
        raise

@router.post("/mapowanie/{product_id}", response_model=Produkt)
async def map_product(
    product_id: int,
    mapping: ProduktMapping,
    db: Session = Depends(get_db)
):
    """Map a product to a category"""
    try:
        log_to_db(
            PoziomLogu.INFO,
            "routes.mapowanie",
            "map_product",
            f"Mapowanie produktu: {product_id}",
            json.dumps({
                "product_id": product_id,
                "mapping_data": mapping.dict(),
                "status": "started"
            })
        )
        
        product = db.query(Produkt).get(product_id)
        if not product:
            log_to_db(
                PoziomLogu.ERROR,
                "routes.mapowanie",
                "map_product",
                f"Produkt nie znaleziony: {product_id}",
                json.dumps({
                    "product_id": product_id,
                    "error_type": "NotFoundError"
                })
            )
            raise HTTPException(status_code=404, detail="Product not found")
        
        product.kategoria = mapping.kategoria
        product.status_mapowania = StatusMapowania.ZMAPOWANY
        db.commit()
        db.refresh(product)
        
        log_to_db(
            PoziomLogu.INFO,
            "routes.mapowanie",
            "map_product",
            f"Produkt zmapowany pomyślnie: {product_id}",
            json.dumps({
                "product_id": product_id,
                "category": mapping.kategoria,
                "status": "completed"
            })
        )
        
        return product
        
    except Exception as e:
        log_to_db(
            PoziomLogu.ERROR,
            "routes.mapowanie",
            "map_product",
            f"Błąd mapowania produktu: {product_id}",
            json.dumps({
                "product_id": product_id,
                "mapping_data": mapping.dict(),
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": str(e.__traceback__)
            })
        )
        raise 