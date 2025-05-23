from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from sqlmodel import Session, select
from typing import List
import os
import shutil
from datetime import datetime
from pathlib import Path
import uuid
from PIL import Image
import io

from models import Paragon, StatusParagonu
from database import get_session
from logging_config import logger

router = APIRouter(prefix="/paragony", tags=["paragony"])

# Create necessary directories
UPLOAD_DIR = Path("uploads")
THUMBNAIL_DIR = Path("static/thumbnails")
UPLOAD_DIR.mkdir(exist_ok=True)
THUMBNAIL_DIR.mkdir(exist_ok=True)

@router.post("/wyslij_plik")
async def upload_receipt(
    file: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    """Upload a receipt file and create a preview"""
    try:
        # Generate unique filename
        file_ext = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = UPLOAD_DIR / unique_filename

        # Save file
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Create thumbnail for images
        thumbnail_path = None
        if file.content_type.startswith("image/"):
            thumbnail_path = THUMBNAIL_DIR / f"{unique_filename}"
            with Image.open(file_path) as img:
                # Resize image maintaining aspect ratio
                img.thumbnail((800, 800))
                img.save(thumbnail_path, "JPEG")

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

@router.get("/podglad/{receipt_id}")
async def preview_receipt(
    receipt_id: int,
    session: Session = Depends(get_session)
):
    """Get receipt preview page"""
    receipt = session.get(Paragon, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Paragon nie znaleziony")

    return {
        "paragon": receipt
    }

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

        # TODO: Implement OCR processing
        # For now, just simulate processing
        import asyncio
        await asyncio.sleep(2)  # Simulate OCR processing
        receipt.status_przetwarzania = StatusParagonu.PRZETWARZANY_AI
        session.commit()

        await asyncio.sleep(2)  # Simulate AI processing
        receipt.status_przetwarzania = StatusParagonu.PRZETWORZONY_OK
        session.commit()

    except Exception as e:
        logger.error(f"Error processing receipt {receipt_id}: {str(e)}", exc_info=True)
        receipt.status_przetwarzania = StatusParagonu.PRZETWORZONY_BLAD
        session.commit() 