from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Depends
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from typing import List
import os
import shutil
from datetime import datetime
from pathlib import Path
import uuid
from PIL import Image
import io
from ollama_client import ollama_generate
import easyocr
from models import Paragon, StatusParagonu, Produkt
from database import get_session
from logging_config import logger
import pdf2image
from fastapi import Request
from fastapi.templating import Jinja2Templates
import re

router = APIRouter(prefix="/paragony", tags=["paragony"])
templates = Jinja2Templates(directory="templates")

# Create necessary directories
UPLOAD_DIR = Path("uploads")
THUMBNAIL_DIR = Path("static/thumbnails")
UPLOAD_DIR.mkdir(exist_ok=True)
THUMBNAIL_DIR.mkdir(exist_ok=True)

KATEGORIE = [
    "Nabiał", "Pieczywo", "Mięso", "Warzywa", "Owoce", "Słodycze", "Napoje", "Inne"
]

@router.post("/wyslij_plik")
async def upload_receipt(
    file: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    """Upload a receipt file and create a preview"""
    try:
        # Walidacja typu pliku
        allowed_types = ["application/pdf", "image/jpeg", "image/png", "image/jpg", "image/webp"]
        if file.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="Nieobsługiwany typ pliku. Dozwolone: PDF, JPG, PNG, WEBP.")
        # Walidacja rozmiaru pliku (max 5 MB)
        file.file.seek(0, 2)  # Przesuń na koniec
        size = file.file.tell()
        file.file.seek(0)
        if size > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Plik jest za duży (max 5 MB)")

        # Generate unique filename
        file_ext = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = UPLOAD_DIR / unique_filename

        # Save file
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Create thumbnail for images and PDFs
        thumbnail_path = None
        if file.content_type.startswith("image/"):
            thumbnail_path = THUMBNAIL_DIR / f"{unique_filename}.jpg"
            with Image.open(file_path) as img:
                img.thumbnail((800, 800))
                img.save(thumbnail_path, "JPEG")
        elif file.content_type == "application/pdf":
            try:
                images = pdf2image.convert_from_path(file_path, first_page=1, last_page=1)
                if images:
                    thumbnail_path = THUMBNAIL_DIR / f"{unique_filename}.jpg"
                    images[0].thumbnail((800, 800))
                    images[0].save(thumbnail_path, "JPEG")
            except Exception as e:
                logger.error(f"Błąd generowania miniatury PDF: {e}", exc_info=True)
                thumbnail_path = None

        # Create receipt record
        receipt = Paragon(
            nazwa_pliku_oryginalnego=file.filename,
            sciezka_pliku_na_serwerze=str(file_path),
            mime_type_pliku=file.content_type,
            status_przetwarzania=StatusParagonu.OCZEKUJE_NA_PODGLAD,
            sciezka_miniatury=str(thumbnail_path) if thumbnail_path else None
        )
        session.add(receipt)
        session.commit()
        session.refresh(receipt)

        return JSONResponse({
            "id_sesji": receipt.id,
            "message": "Plik został pomyślnie przesłany"
        })

    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Błąd podczas przesyłania pliku")

@router.get("/podglad/{receipt_id}", response_class=HTMLResponse)
async def preview_receipt(
    request: Request,
    receipt_id: int,
    session: Session = Depends(get_session)
):
    """Get receipt preview page"""
    receipt = session.get(Paragon, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Paragon nie znaleziony")
    # Automatyczna zmiana statusu po podglądzie
    if receipt.status_przetwarzania == StatusParagonu.OCZEKUJE_NA_PODGLAD:
        receipt.status_przetwarzania = StatusParagonu.PODGLADNIETY_OCZEKUJE_NA_PRZETWORZENIE
        session.commit()
    return templates.TemplateResponse(
        "paragony/podglad.html",
        {"request": request, "paragon": receipt}
    )

@router.post("/{receipt_id}/rozpocznij_przetwarzanie")
async def start_processing(
    receipt_id: int,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    """Start processing the receipt"""
    receipt = session.get(Paragon, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Paragon nie znaleziony")

    if receipt.status_przetwarzania != StatusParagonu.PODGLADNIETY_OCZEKUJE_NA_PRZETWORZENIE:
        raise HTTPException(status_code=400, detail="Nieprawidłowy status paragonu")

    # Update status
    receipt.status_przetwarzania = StatusParagonu.PRZETWARZANY_OCR
    session.commit()

    # Start background processing
    background_tasks.add_task(process_receipt, receipt_id, session)

    return JSONResponse({
        "message": "Rozpoczęto przetwarzanie paragonu",
        "receipt_id": receipt_id
    })

@router.get("/{receipt_id}/status")
async def get_processing_status(
    receipt_id: int,
    session: Session = Depends(get_session)
):
    """Get current processing status"""
    receipt = session.get(Paragon, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Paragon nie znaleziony")

    # Calculate progress percentage based on status
    progress_percentage = 0
    status_message = ""

    if receipt.status_przetwarzania == StatusParagonu.PRZETWARZANY_OCR:
        progress_percentage = 0.3
        status_message = "Przetwarzanie OCR..."
    elif receipt.status_przetwarzania == StatusParagonu.PRZETWARZANY_AI:
        progress_percentage = 0.6
        status_message = "Analiza AI..."
    elif receipt.status_przetwarzania == StatusParagonu.PRZETWORZONY_OK:
        progress_percentage = 1.0
        status_message = "Przetwarzanie zakończone pomyślnie"
    elif receipt.status_przetwarzania == StatusParagonu.PRZETWORZONY_BLAD:
        progress_percentage = 1.0
        status_message = "Wystąpił błąd podczas przetwarzania"

    return {
        "status": receipt.status_przetwarzania,
        "progress_percentage": progress_percentage,
        "status_message": status_message
    }

async def process_receipt(receipt_id: int, session: Session):
    """Background task for processing receipt"""
    try:
        receipt = session.get(Paragon, receipt_id)
        if not receipt:
            logger.error(f"Receipt {receipt_id} not found during processing")
            return

        import asyncio
        await asyncio.sleep(1)  # Simulate waiting
        receipt.status_przetwarzania = StatusParagonu.PRZETWARZANY_OCR
        session.commit()

        # OCR dla obrazów i PDF
        ocr_text = None
        if receipt.mime_type_pliku.startswith("image/"):
            try:
                reader = easyocr.Reader(['pl', 'en'], gpu=False)
                ocr_result = reader.readtext(receipt.sciezka_pliku_na_serwerze, detail=0, paragraph=True)
                ocr_text = "\n".join(ocr_result)
                logger.info(f"OCR result for receipt {receipt_id}: {ocr_text}")
            except Exception as ocr_exc:
                logger.error(f"Błąd OCR: {ocr_exc}", exc_info=True)
                receipt.status_przetwarzania = StatusParagonu.PRZETWORZONY_BLAD
                session.commit()
                return
        elif receipt.mime_type_pliku == "application/pdf":
            try:
                # Konwersja PDF na obrazy
                images = pdf2image.convert_from_path(receipt.sciezka_pliku_na_serwerze)
                reader = easyocr.Reader(['pl', 'en'], gpu=False)
                ocr_texts = []
                for i, img in enumerate(images):
                    img_path = f"/tmp/receipt_{receipt_id}_page_{i}.jpg"
                    img.save(img_path, "JPEG")
                    ocr_result = reader.readtext(img_path, detail=0, paragraph=True)
                    ocr_texts.append("\n".join(ocr_result))
                ocr_text = "\n".join(ocr_texts)
                logger.info(f"OCR (PDF) result for receipt {receipt_id}: {ocr_text}")
            except Exception as ocr_exc:
                logger.error(f"Błąd OCR PDF: {ocr_exc}", exc_info=True)
                receipt.status_przetwarzania = StatusParagonu.PRZETWORZONY_BLAD
                session.commit()
                return
        else:
            ocr_text = receipt.nazwa_pliku_oryginalnego  # fallback

        await asyncio.sleep(1)  # Simulate waiting
        receipt.status_przetwarzania = StatusParagonu.PRZETWARZANY_AI
        session.commit()

        # Wywołanie modelu Bielik
        prompt = f"Wypisz produkty z poniższego tekstu paragonu, każdy w osobnej linii w formacie: NAZWA;KATEGORIA;CENA;DATA_WAZNOSCI (jeśli brak daty, zostaw puste):\n{ocr_text}"
        try:
            odpowiedz = await ollama_generate(prompt)
            logger.info(f"Odpowiedź modelu Bielik: {odpowiedz}")
            # Parsowanie odpowiedzi i zapis produktów
            produkty = []
            for line in odpowiedz.strip().split('\n'):
                parts = [p.strip() for p in line.split(';')]
                if len(parts) < 3:
                    logger.warning(f"Pominięto linię (za mało pól): {line}")
                    continue
                nazwa = parts[0]
                kategoria = parts[1] if len(parts) > 1 else "Inne"
                cena_raw = parts[2]
                cena_match = re.search(r"[\d,.]+", cena_raw)
                if not cena_match:
                    logger.warning(f"Pominięto linię (brak ceny): {line}")
                    continue
                try:
                    cena = float(cena_match.group(0).replace(',', '.'))
                except Exception:
                    logger.warning(f"Pominięto linię (nieprawidłowa cena): {line}")
                    continue
                produkt = Produkt(
                    nazwa=nazwa,
                    kategoria=kategoria,
                    cena=cena,
                    data_waznosci=None,
                    paragon_id=receipt.id
                )
                produkty.append(produkt)
            if produkty:
                session.add_all(produkty)
                session.commit()
        except Exception as ollama_exc:
            logger.error(f"Błąd podczas wywołania modelu Bielik: {ollama_exc}", exc_info=True)
            receipt.status_przetwarzania = StatusParagonu.PRZETWORZONY_BLAD
            session.commit()
            return

        await asyncio.sleep(1)  # Simulate waiting
        receipt.status_przetwarzania = StatusParagonu.PRZETWORZONY_OK
        session.commit()

    except Exception as e:
        logger.error(f"Error processing receipt {receipt_id}: {str(e)}", exc_info=True)
        receipt.status_przetwarzania = StatusParagonu.PRZETWORZONY_BLAD
        session.commit()

@router.get("/dodaj", response_class=HTMLResponse)
async def dodaj_paragon(request: Request):
    return templates.TemplateResponse("paragony/dodaj.html", {"request": request})

@router.get("/{paragon_id}/import", response_class=HTMLResponse)
async def import_products_get(request: Request, paragon_id: int, session: Session = Depends(get_session)):
    paragon = session.get(Paragon, paragon_id)
    if not paragon:
        raise HTTPException(status_code=404, detail="Paragon nie znaleziony")
    produkty = session.exec(select(Produkt).where(Produkt.paragon_id == paragon_id)).all()
    return templates.TemplateResponse(
        "paragony/import.html",
        {"request": request, "paragon": paragon, "produkty": produkty, "kategorie": KATEGORIE}
    )

@router.post("/{paragon_id}/import")
async def import_products_post(request: Request, paragon_id: int, session: Session = Depends(get_session)):
    form = await request.form()
    selected_ids = form.getlist("selected_products[]")
    produkty = session.exec(select(Produkt).where(Produkt.paragon_id == paragon_id)).all()
    for produkt in produkty:
        if str(produkt.id) in selected_ids:
            produkt.nazwa = form.get(f"nazwa_{produkt.id}", produkt.nazwa)
            produkt.kategoria = form.get(f"kategoria_{produkt.id}", produkt.kategoria)
            produkt.cena = float(form.get(f"cena_{produkt.id}", produkt.cena))
            data_waznosci = form.get(f"data_waznosci_{produkt.id}")
            produkt.data_waznosci = data_waznosci if data_waznosci else None
        else:
            session.delete(produkt)
    session.commit()
    return RedirectResponse(url="/spizarnia", status_code=303) 