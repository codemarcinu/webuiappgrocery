from models import LogBledow, PoziomLogu
from db_logger import log_to_db
import json

@router.get("/produkty/", response_model=List[Produkt])
async def get_products(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get products"""
    try:
        log_to_db(
            PoziomLogu.INFO,
            "routes.produkty",
            "get_products",
            "Pobieranie produktów",
            json.dumps({
                "skip": skip,
                "limit": limit,
                "status": "started"
            })
        )
        
        products = db.query(Produkt).offset(skip).limit(limit).all()
        
        log_to_db(
            PoziomLogu.INFO,
            "routes.produkty",
            "get_products",
            "Produkty pobrane pomyślnie",
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
            "routes.produkty",
            "get_products",
            "Błąd pobierania produktów",
            json.dumps({
                "skip": skip,
                "limit": limit,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": str(e.__traceback__)
            })
        )
        raise

@router.get("/produkty/{product_id}", response_model=Produkt)
async def get_product(
    product_id: int,
    db: Session = Depends(get_db)
):
    """Get product by ID"""
    try:
        log_to_db(
            PoziomLogu.INFO,
            "routes.produkty",
            "get_product",
            f"Pobieranie produktu: {product_id}",
            json.dumps({
                "product_id": product_id,
                "status": "started"
            })
        )
        
        product = db.query(Produkt).get(product_id)
        if not product:
            log_to_db(
                PoziomLogu.ERROR,
                "routes.produkty",
                "get_product",
                f"Produkt nie znaleziony: {product_id}",
                json.dumps({
                    "product_id": product_id,
                    "error_type": "NotFoundError"
                })
            )
            raise HTTPException(status_code=404, detail="Product not found")
        
        log_to_db(
            PoziomLogu.INFO,
            "routes.produkty",
            "get_product",
            f"Produkt pobrany pomyślnie: {product_id}",
            json.dumps({
                "product_id": product_id,
                "status": "completed"
            })
        )
        
        return product
        
    except Exception as e:
        log_to_db(
            PoziomLogu.ERROR,
            "routes.produkty",
            "get_product",
            f"Błąd pobierania produktu: {product_id}",
            json.dumps({
                "product_id": product_id,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": str(e.__traceback__)
            })
        )
        raise

@router.post("/produkty/", response_model=Produkt)
async def create_product(
    product: ProduktCreate,
    db: Session = Depends(get_db)
):
    """Create a new product"""
    try:
        log_to_db(
            PoziomLogu.INFO,
            "routes.produkty",
            "create_product",
            "Tworzenie nowego produktu",
            json.dumps({
                "product_data": product.dict(),
                "status": "started"
            })
        )
        
        db_product = Produkt(**product.dict())
        db.add(db_product)
        db.commit()
        db.refresh(db_product)
        
        log_to_db(
            PoziomLogu.INFO,
            "routes.produkty",
            "create_product",
            f"Produkt utworzony pomyślnie: {db_product.id}",
            json.dumps({
                "product_id": db_product.id,
                "status": "completed"
            })
        )
        
        return db_product
        
    except Exception as e:
        log_to_db(
            PoziomLogu.ERROR,
            "routes.produkty",
            "create_product",
            "Błąd tworzenia produktu",
            json.dumps({
                "product_data": product.dict(),
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": str(e.__traceback__)
            })
        )
        raise

@router.put("/produkty/{product_id}", response_model=Produkt)
async def update_product(
    product_id: int,
    product: ProduktUpdate,
    db: Session = Depends(get_db)
):
    """Update a product"""
    try:
        log_to_db(
            PoziomLogu.INFO,
            "routes.produkty",
            "update_product",
            f"Aktualizacja produktu: {product_id}",
            json.dumps({
                "product_id": product_id,
                "product_data": product.dict(),
                "status": "started"
            })
        )
        
        db_product = db.query(Produkt).get(product_id)
        if not db_product:
            log_to_db(
                PoziomLogu.ERROR,
                "routes.produkty",
                "update_product",
                f"Produkt nie znaleziony: {product_id}",
                json.dumps({
                    "product_id": product_id,
                    "error_type": "NotFoundError"
                })
            )
            raise HTTPException(status_code=404, detail="Product not found")
        
        for key, value in product.dict(exclude_unset=True).items():
            setattr(db_product, key, value)
        
        db.commit()
        db.refresh(db_product)
        
        log_to_db(
            PoziomLogu.INFO,
            "routes.produkty",
            "update_product",
            f"Produkt zaktualizowany pomyślnie: {product_id}",
            json.dumps({
                "product_id": product_id,
                "status": "completed"
            })
        )
        
        return db_product
        
    except Exception as e:
        log_to_db(
            PoziomLogu.ERROR,
            "routes.produkty",
            "update_product",
            f"Błąd aktualizacji produktu: {product_id}",
            json.dumps({
                "product_id": product_id,
                "product_data": product.dict(),
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": str(e.__traceback__)
            })
        )
        raise

@router.delete("/produkty/{product_id}")
async def delete_product(
    product_id: int,
    db: Session = Depends(get_db)
):
    """Delete a product"""
    try:
        log_to_db(
            PoziomLogu.INFO,
            "routes.produkty",
            "delete_product",
            f"Usuwanie produktu: {product_id}",
            json.dumps({
                "product_id": product_id,
                "status": "started"
            })
        )
        
        db_product = db.query(Produkt).get(product_id)
        if not db_product:
            log_to_db(
                PoziomLogu.ERROR,
                "routes.produkty",
                "delete_product",
                f"Produkt nie znaleziony: {product_id}",
                json.dumps({
                    "product_id": product_id,
                    "error_type": "NotFoundError"
                })
            )
            raise HTTPException(status_code=404, detail="Product not found")
        
        db.delete(db_product)
        db.commit()
        
        log_to_db(
            PoziomLogu.INFO,
            "routes.produkty",
            "delete_product",
            f"Produkt usunięty pomyślnie: {product_id}",
            json.dumps({
                "product_id": product_id,
                "status": "completed"
            })
        )
        
        return {"message": "Product deleted successfully"}
        
    except Exception as e:
        log_to_db(
            PoziomLogu.ERROR,
            "routes.produkty",
            "delete_product",
            f"Błąd usuwania produktu: {product_id}",
            json.dumps({
                "product_id": product_id,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": str(e.__traceback__)
            })
        )
        raise 