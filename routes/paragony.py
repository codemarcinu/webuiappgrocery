from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Depends, Request, Form
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse, FileResponse
from sqlmodel import Session, select
from typing import List, Optional, Tuple, Dict, Any
import os
import shutil
from datetime import datetime
from pathlib import Path
import uuid
from PIL import Image
import io
from ollama_client import ollama_generate
import easyocr
from models import Paragon, StatusParagonu, Produkt, KategoriaProduktu
from database import get_session
from logging_config import logger
import pdf2image
from fastapi.templating import Jinja2Templates
import re
from receipt_processor import ReceiptProcessor
from config import get_settings
from tasks import process_receipt_task
from forms import DodajParagonForm, EdytujProduktForm
from wtforms import ValidationError
from product_mapper import ProductMapper

router = APIRouter(prefix="/paragony", tags=["paragony"])
templates = Jinja2Templates(directory="templates")
settings = get_settings()

receipt_processor = ReceiptProcessor()

# Create necessary directories
UPLOAD_DIR = Path("uploads")
THUMBNAIL_DIR = Path("static/thumbnails")
UPLOAD_DIR.mkdir(exist_ok=True)
THUMBNAIL_DIR.mkdir(exist_ok=True)

KATEGORIE = [k.value for k in KategoriaProduktu]

# === Helper Functions ===

async def _get_paragon_or_404(db: Session, paragon_id: int) -> Paragon:
    """Get paragon by ID or raise 404"""
    paragon = db.query(Paragon).get(paragon_id)
    if not paragon:
        raise HTTPException(status_code=404, detail="Paragon nie znaleziony")
    return paragon

async def _create_paragon_record(
    db: Session,
    filename: str,
    saved_path: str,
    mime_type: str,
    komentarz: Optional[str] = None
) -> Tuple[Paragon, int]:
    """Create a new paragon record in database"""
    paragon = Paragon(
        nazwa_pliku_oryginalnego=filename,
        sciezka_pliku_na_serwerze=saved_path,
        mime_type_pliku=mime_type,
        komentarz=komentarz,
        status_przetwarzania=StatusParagonu.OCZEKUJE_NA_PODGLAD
    )
    db.add(paragon)
    db.commit()
    db.refresh(paragon)
    return paragon, paragon.id

async def _delete_paragon_file(file_path: Path) -> None:
    """Delete paragon file from filesystem"""
    try:
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Successfully deleted receipt file: {file_path}")
    except FileNotFoundError:
        logger.warning(f"File not found during deletion attempt: {file_path}")
    except OSError as e:
        logger.error(f"Error deleting receipt file {file_path}: {str(e)}")

async def _validate_product_form(
    form_data: Dict[str, Any],
    produkt_id: int
) -> Tuple[bool, Optional[EdytujProduktForm], Optional[Dict[str, Any]]]:
    """Validate product form data"""
    product_form = EdytujProduktForm()
    product_form.nazwa.data = form_data.get(f"nazwa_{produkt_id}")
    product_form.kategoria.data = form_data.get(f"kategoria_{produkt_id}")
    product_form.cena.data = form_data.get(f"cena_{produkt_id}")
    product_form.ilosc_na_paragonie.data = form_data.get(f"ilosc_{produkt_id}")
    product_form.data_waznosci.data = form_data.get(f"data_waznosci_{produkt_id}")
    
    if not product_form.validate():
        return False, product_form, product_form.errors
    return True, product_form, None

async def _update_product_from_form(
    produkt: Produkt,
    form: EdytujProduktForm
) -> None:
    """Update product with validated form data"""
    produkt.nazwa = form.nazwa.data
    produkt.kategoria = form.kategoria.data
    produkt.cena = float(form.cena.data)
    produkt.ilosc_na_paragonie = int(form.ilosc_na_paragonie.data)
    produkt.data_waznosci = form.data_waznosci.data

# === Route Handlers ===

@router.get("/", response_class=HTMLResponse)
async def lista_paragonow(request: Request):
    """Show list of receipts"""
    with get_session() as db:
        paragony = db.query(Paragon).order_by(Paragon.data_wyslania.desc()).all()
        return templates.TemplateResponse(
            "paragony/lista.html",
            {
                "request": request,
                "paragony": paragony
            }
        )

@router.get("/dodaj", response_class=HTMLResponse)
async def dodaj_paragon_form(request: Request):
    """Show form for adding new receipt"""
    form = DodajParagonForm()
    return templates.TemplateResponse(
        "paragony/dodaj.html",
        {
            "request": request,
            "form": form
        }
    )

@router.post("/dodaj", response_class=HTMLResponse)
async def dodaj_paragon(request: Request, file: UploadFile = File(...), komentarz: Optional[str] = Form(None)):
    try:
        form = DodajParagonForm()
        form.file.data = file
        form.komentarz.data = komentarz

        if not form.validate():
            return templates.TemplateResponse(
                "paragony/dodaj.html",
                {
                    "request": request,
                    "form": form,
                    "errors": form.errors
                },
                status_code=400
            )

        # Validate and save the file
        saved_path = await receipt_processor.validate_and_save_file(file)
        
        # Create receipt record with transaction
        with get_session() as db:
            try:
                paragon, paragon_id = await _create_paragon_record(
                    db, file.filename, saved_path, file.content_type, komentarz
                )
                db.commit()
            except Exception as e:
                db.rollback()
                # Clean up saved file if database operation fails
                try:
                    Path(saved_path).unlink()
                except OSError:
                    pass
                raise HTTPException(status_code=500, detail="Error creating receipt record")
        
        # Start Celery task for processing
        process_receipt_task.delay(paragon_id)
        
        # Set flash message
        response = RedirectResponse(url="/paragony", status_code=303)
        response.set_cookie('flash_msg', 'Paragon został dodany i jest przetwarzany w tle.')
        return response
        
    except Exception as e:
        logger.error(f"Unexpected error adding receipt: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/podglad/{paragon_id}", response_class=HTMLResponse)
async def podglad_paragonu(request: Request, paragon_id: int):
    """Show receipt details and processing status"""
    with get_session() as db:
        paragon = await _get_paragon_or_404(db, paragon_id)
        
        # Update status if it's waiting for preview
        if paragon.status_przetwarzania == StatusParagonu.OCZEKUJE_NA_PODGLAD:
            paragon.status_przetwarzania = StatusParagonu.PODGLADNIETY_OCZEKUJE_NA_PRZETWORZENIE
            db.commit()
        
        return templates.TemplateResponse(
            "paragony/podglad.html",
            {
                "request": request,
                "paragon": paragon
            }
        )

@router.get("/status/{paragon_id}")
async def status_przetwarzania(paragon_id: int):
    """Get receipt processing status"""
    with get_session() as db:
        paragon = await _get_paragon_or_404(db, paragon_id)
        return {
            "status": paragon.status_przetwarzania,
            "data_przetworzenia": paragon.data_przetworzenia,
            "blad": paragon.blad_przetwarzania
        }

@router.get("/{paragon_id}/import", response_class=HTMLResponse)
async def import_products_get(request: Request, paragon_id: int, session: Session = Depends(get_session)):
    paragon = await _get_paragon_or_404(session, paragon_id)
    produkty = session.exec(select(Produkt).where(Produkt.paragon_id == paragon_id)).all()
    return templates.TemplateResponse(
        "paragony/import.html",
        {
            "request": request,
            "paragon": paragon,
            "produkty": produkty,
            "kategorie": KATEGORIE,
            "form": EdytujProduktForm()
        }
    )

@router.post("/{paragon_id}/import")
async def import_products_post(request: Request, paragon_id: int, session: Session = Depends(get_session)):
    form = await request.form()
    selected_ids = form.getlist("selected_products[]")
    produkty = session.exec(select(Produkt).where(Produkt.paragon_id == paragon_id)).all()
    
    for produkt in produkty:
        if str(produkt.id) in selected_ids:
            is_valid, product_form, errors = await _validate_product_form(form, produkt.id)
            if not is_valid:
                return templates.TemplateResponse(
                    "paragony/import.html",
                    {
                        "request": request,
                        "paragon": session.get(Paragon, paragon_id),
                        "produkty": produkty,
                        "kategorie": KATEGORIE,
                        "form": product_form,
                        "errors": errors
                    },
                    status_code=400
                )
            
            await _update_product_from_form(produkt, product_form)
        else:
            session.delete(produkt)
    
    session.commit()
    return RedirectResponse(url="/spizarnia", status_code=303)

@router.get("/uploads/{filename}")
async def serve_receipt_file(filename: str):
    """Serve uploaded receipt files securely"""
    # Prevent path traversal
    if '..' in filename or filename.startswith('/'):
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    # Validate file extension
    ext = filename.split('.')[-1].lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid file type")
    
    file_path = Path(settings.UPLOAD_FOLDER) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Verify file is within upload directory
    try:
        file_path.resolve().relative_to(Path(settings.UPLOAD_FOLDER).resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path")
    
    return FileResponse(file_path)

@router.post("/usun/{paragon_id}", response_class=RedirectResponse)
async def usun_paragon(request: Request, paragon_id: int):
    """Delete receipt and its associated file"""
    with get_session() as db:
        paragon = await _get_paragon_or_404(db, paragon_id)
        
        # Get file path before deleting from database
        file_path = Path(paragon.sciezka_pliku_na_serwerze)
        
        # Delete from database first
        db.delete(paragon)
        db.commit()
        
        # Try to delete the physical file
        await _delete_paragon_file(file_path)
        
        response = RedirectResponse(url="/paragony", status_code=303)
        response.set_cookie('flash_msg', 'Paragon został usunięty!')
        return response

@router.get("/{paragon_id}/mapowanie", response_class=HTMLResponse)
async def mapowanie_produktow(
    request: Request,
    paragon_id: int,
    session: Session = Depends(get_session)
):
    paragon = await _get_paragon_or_404(session, paragon_id)
        
    if paragon.status_przetwarzania != StatusParagonu.PRZETWORZONY_OK:
        raise HTTPException(status_code=400, detail="Paragon nie został jeszcze przetworzony")
    
    return templates.TemplateResponse(
        "paragony/mapowanie.html",
        {
            "request": request,
            "paragon": paragon
        }
    )

@router.post("/api/produkty/mapuj/{produkt_id}")
async def mapuj_produkt(
    request: Request,
    produkt_id: int,
    data: dict,
    session: Session = Depends(get_session)
):
    produkt = session.get(Produkt, produkt_id)
    if not produkt:
        raise HTTPException(status_code=404, detail="Produkt nie znaleziony")
    
    produkt.nazwa = data.get("nazwa", produkt.nazwa)
    produkt.kategoria = data.get("kategoria", produkt.kategoria)
    session.commit()
    
    return {"status": "success"}

@router.post("/api/produkty/ignoruj/{produkt_id}")
async def ignoruj_produkt(
    request: Request,
    produkt_id: int,
    session: Session = Depends(get_session)
):
    produkt = session.get(Produkt, produkt_id)
    if not produkt:
        raise HTTPException(status_code=404, detail="Produkt nie znaleziony")
    
    session.delete(produkt)
    session.commit()
    
    return {"status": "success"} 