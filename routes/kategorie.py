from models import LogBledow, PoziomLogu
from db_logger import log_to_db
import json

@router.get("/kategorie/", response_model=List[KategoriaProduktu])
async def get_categories(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get categories"""
    try:
        log_to_db(
            PoziomLogu.INFO,
            "routes.kategorie",
            "get_categories",
            "Pobieranie kategorii",
            json.dumps({
                "skip": skip,
                "limit": limit,
                "status": "started"
            })
        )
        
        categories = db.query(KategoriaProduktu).offset(skip).limit(limit).all()
        
        log_to_db(
            PoziomLogu.INFO,
            "routes.kategorie",
            "get_categories",
            "Kategorie pobrane pomyślnie",
            json.dumps({
                "skip": skip,
                "limit": limit,
                "count": len(categories),
                "status": "completed"
            })
        )
        
        return categories
        
    except Exception as e:
        log_to_db(
            PoziomLogu.ERROR,
            "routes.kategorie",
            "get_categories",
            "Błąd pobierania kategorii",
            json.dumps({
                "skip": skip,
                "limit": limit,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": str(e.__traceback__)
            })
        )
        raise

@router.get("/kategorie/{category_id}", response_model=KategoriaProduktu)
async def get_category(
    category_id: int,
    db: Session = Depends(get_db)
):
    """Get category by ID"""
    try:
        log_to_db(
            PoziomLogu.INFO,
            "routes.kategorie",
            "get_category",
            f"Pobieranie kategorii: {category_id}",
            json.dumps({
                "category_id": category_id,
                "status": "started"
            })
        )
        
        category = db.query(KategoriaProduktu).get(category_id)
        if not category:
            log_to_db(
                PoziomLogu.ERROR,
                "routes.kategorie",
                "get_category",
                f"Kategoria nie znaleziona: {category_id}",
                json.dumps({
                    "category_id": category_id,
                    "error_type": "NotFoundError"
                })
            )
            raise HTTPException(status_code=404, detail="Category not found")
        
        log_to_db(
            PoziomLogu.INFO,
            "routes.kategorie",
            "get_category",
            f"Kategoria pobrana pomyślnie: {category_id}",
            json.dumps({
                "category_id": category_id,
                "status": "completed"
            })
        )
        
        return category
        
    except Exception as e:
        log_to_db(
            PoziomLogu.ERROR,
            "routes.kategorie",
            "get_category",
            f"Błąd pobierania kategorii: {category_id}",
            json.dumps({
                "category_id": category_id,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": str(e.__traceback__)
            })
        )
        raise

@router.post("/kategorie/", response_model=KategoriaProduktu)
async def create_category(
    category: KategoriaProduktuCreate,
    db: Session = Depends(get_db)
):
    """Create a new category"""
    try:
        log_to_db(
            PoziomLogu.INFO,
            "routes.kategorie",
            "create_category",
            "Tworzenie nowej kategorii",
            json.dumps({
                "category_data": category.dict(),
                "status": "started"
            })
        )
        
        db_category = KategoriaProduktu(**category.dict())
        db.add(db_category)
        db.commit()
        db.refresh(db_category)
        
        log_to_db(
            PoziomLogu.INFO,
            "routes.kategorie",
            "create_category",
            f"Kategoria utworzona pomyślnie: {db_category.id}",
            json.dumps({
                "category_id": db_category.id,
                "status": "completed"
            })
        )
        
        return db_category
        
    except Exception as e:
        log_to_db(
            PoziomLogu.ERROR,
            "routes.kategorie",
            "create_category",
            "Błąd tworzenia kategorii",
            json.dumps({
                "category_data": category.dict(),
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": str(e.__traceback__)
            })
        )
        raise

@router.put("/kategorie/{category_id}", response_model=KategoriaProduktu)
async def update_category(
    category_id: int,
    category: KategoriaProduktuUpdate,
    db: Session = Depends(get_db)
):
    """Update a category"""
    try:
        log_to_db(
            PoziomLogu.INFO,
            "routes.kategorie",
            "update_category",
            f"Aktualizacja kategorii: {category_id}",
            json.dumps({
                "category_id": category_id,
                "category_data": category.dict(),
                "status": "started"
            })
        )
        
        db_category = db.query(KategoriaProduktu).get(category_id)
        if not db_category:
            log_to_db(
                PoziomLogu.ERROR,
                "routes.kategorie",
                "update_category",
                f"Kategoria nie znaleziona: {category_id}",
                json.dumps({
                    "category_id": category_id,
                    "error_type": "NotFoundError"
                })
            )
            raise HTTPException(status_code=404, detail="Category not found")
        
        for key, value in category.dict(exclude_unset=True).items():
            setattr(db_category, key, value)
        
        db.commit()
        db.refresh(db_category)
        
        log_to_db(
            PoziomLogu.INFO,
            "routes.kategorie",
            "update_category",
            f"Kategoria zaktualizowana pomyślnie: {category_id}",
            json.dumps({
                "category_id": category_id,
                "status": "completed"
            })
        )
        
        return db_category
        
    except Exception as e:
        log_to_db(
            PoziomLogu.ERROR,
            "routes.kategorie",
            "update_category",
            f"Błąd aktualizacji kategorii: {category_id}",
            json.dumps({
                "category_id": category_id,
                "category_data": category.dict(),
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": str(e.__traceback__)
            })
        )
        raise

@router.delete("/kategorie/{category_id}")
async def delete_category(
    category_id: int,
    db: Session = Depends(get_db)
):
    """Delete a category"""
    try:
        log_to_db(
            PoziomLogu.INFO,
            "routes.kategorie",
            "delete_category",
            f"Usuwanie kategorii: {category_id}",
            json.dumps({
                "category_id": category_id,
                "status": "started"
            })
        )
        
        db_category = db.query(KategoriaProduktu).get(category_id)
        if not db_category:
            log_to_db(
                PoziomLogu.ERROR,
                "routes.kategorie",
                "delete_category",
                f"Kategoria nie znaleziona: {category_id}",
                json.dumps({
                    "category_id": category_id,
                    "error_type": "NotFoundError"
                })
            )
            raise HTTPException(status_code=404, detail="Category not found")
        
        db.delete(db_category)
        db.commit()
        
        log_to_db(
            PoziomLogu.INFO,
            "routes.kategorie",
            "delete_category",
            f"Kategoria usunięta pomyślnie: {category_id}",
            json.dumps({
                "category_id": category_id,
                "status": "completed"
            })
        )
        
        return {"message": "Category deleted successfully"}
        
    except Exception as e:
        log_to_db(
            PoziomLogu.ERROR,
            "routes.kategorie",
            "delete_category",
            f"Błąd usuwania kategorii: {category_id}",
            json.dumps({
                "category_id": category_id,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": str(e.__traceback__)
            })
        )
        raise 