from fastapi import FastAPI, Request, HTTPException, Depends, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import uvicorn
from pathlib import Path
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import Response
from typing import Optional, Dict, Any
import os
from contextlib import asynccontextmanager
import json
from datetime import datetime
from fastapi_csrf_jinja.middleware import FastAPICSRFJinjaMiddleware
from fastapi_csrf_jinja.jinja_processor import csrf_token_processor
from sqlalchemy.orm import Session
from sqlmodel import Session, select
from urllib.parse import unquote, quote

from database import create_db_and_tables, SessionLocal, get_session
from routes import paragony
from logging_config import setup_logging, logger
from models import Paragon, Produkt, StatusParagonu
from config import get_settings

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize logging configuration
    setup_logging()
    logger.info("Application started successfully")
    
    # Initialize database
    create_db_and_tables()
    logger.info("Database initialized successfully")
    
    yield

# Create FastAPI app
app = FastAPI(
    title="Webowy Asystent Spiżarni",
    description="Aplikacja do zarządzania produktami w spiżarni",
    version="1.0.0",
    lifespan=lifespan
)

# Configure security middleware
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["*"]
)

# Configure CORS with more restrictive settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],  # Only these domains!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Gzip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Set up templates
templates = Jinja2Templates(directory="templates")

# Custom Jinja2 filters
def from_json(value):
    try:
        return json.loads(value)
    except:
        return []

templates.env.filters["from_json"] = from_json

# Template context dependency
async def get_template_context(request: Request) -> Dict[str, Any]:
    """Get common template context"""
    flash_msg_raw = request.cookies.get('flash_msg')
    flash_msg = unquote(flash_msg_raw) if flash_msg_raw else None
    return {
        "request": request,
        "today": datetime.now().strftime('%Y-%m-%d'),
        "flash_msg": flash_msg
    }

# Include routers
app.include_router(paragony.router)

@app.get("/")
async def root(request: Request, context: Dict[str, Any] = Depends(get_template_context)):
    """Root endpoint - shows list of receipts"""
    db = SessionLocal()
    try:
        paragony = db.query(Paragon).order_by(Paragon.data_wyslania.desc()).all()
        return templates.TemplateResponse(
            "paragony/lista.html",
            {**context, "paragony": paragony}
        )
    finally:
        db.close()

@app.get("/spizarnia", response_class=HTMLResponse)
async def spizarnia(
    request: Request, 
    context: Dict[str, Any] = Depends(get_template_context),
    msg: Optional[str] = None,
    nazwa: str = '', 
    kategoria: str = '', 
    data_waznosci: str = ''
):
    db = SessionLocal()
    try:
        query = db.query(Produkt)
        if nazwa:
            query = query.filter(Produkt.nazwa.ilike(f"%{nazwa}%"))
        if kategoria:
            query = query.filter(Produkt.kategoria == kategoria)
        if data_waznosci:
            query = query.filter(Produkt.data_waznosci == data_waznosci)
        produkty = query.all()
        kategorie = ["Nabiał", "Pieczywo", "Mięso", "Warzywa", "Owoce", "Słodycze", "Napoje", "Inne"]
        # Odczytaj flash message z cookies
        flash_msg = request.cookies.get('flash_msg')
        response = templates.TemplateResponse(
            "spizarnia.html",
            {
                **context,
                "produkty": produkty,
                "kategorie": kategorie,
                "f_nazwa": nazwa,
                "f_kategoria": kategoria,
                "f_data_waznosci": data_waznosci,
                "flash_msg": flash_msg
            }
        )
        # Skasuj flash message po odczytaniu
        if flash_msg:
            response.delete_cookie('flash_msg')
        return response
    finally:
        db.close()

@app.get("/spizarnia/edytuj/{produkt_id}", response_class=HTMLResponse)
async def edytuj_produkt_get(
    request: Request,
    produkt_id: int,
    context: Dict[str, Any] = Depends(get_template_context)
):
    db = SessionLocal()
    try:
        produkt = db.query(Produkt).get(produkt_id)
        if not produkt:
            return templates.TemplateResponse(
                "spizarnia.html",
                {**context, "produkty": db.query(Produkt).all(), "error": "Produkt nie znaleziony"}
            )
        kategorie = ["Nabiał", "Pieczywo", "Mięso", "Warzywa", "Owoce", "Słodycze", "Napoje", "Inne"]
        return templates.TemplateResponse(
            "edytuj_produkt.html",
            {**context, "produkt": produkt, "kategorie": kategorie}
        )
    finally:
        db.close()

@app.post("/spizarnia/edytuj/{produkt_id}")
async def edytuj_produkt_post(request: Request, produkt_id: int):
    db = SessionLocal()
    try:
        produkt = db.query(Produkt).get(produkt_id)
        if not produkt:
            response = RedirectResponse(url="/spizarnia", status_code=303)
            response.set_cookie('flash_msg', 'Produkt nie znaleziony!')
            return response
        form = await request.form()
        produkt.nazwa = form.get("nazwa", produkt.nazwa)
        produkt.kategoria = form.get("kategoria", produkt.kategoria)
        produkt.cena = float(form.get("cena", produkt.cena))
        produkt.aktualna_ilosc = int(form.get("ilosc", produkt.aktualna_ilosc))
        data_waznosci = form.get("data_waznosci")
        produkt.data_waznosci = data_waznosci if data_waznosci else None
        db.commit()
        response = RedirectResponse(url="/spizarnia", status_code=303)
        response.set_cookie('flash_msg', 'Produkt został zaktualizowany!')
        return response
    finally:
        db.close()

@app.post("/spizarnia/usun/{produkt_id}")
async def usun_produkt(request: Request, produkt_id: int):
    db = SessionLocal()
    try:
        produkt = db.query(Produkt).get(produkt_id)
        response = RedirectResponse(url="/spizarnia", status_code=303)
        if produkt:
            db.delete(produkt)
            db.commit()
            response.set_cookie('flash_msg', 'Produkt został usunięty!')
        else:
            response.set_cookie('flash_msg', 'Produkt nie znaleziony!')
        return response
    finally:
        db.close()

@app.get("/spizarnia/dodaj/{paragon_id}", response_class=HTMLResponse)
async def dodaj_do_spizarni(request: Request, paragon_id: int):
    db = SessionLocal()
    try:
        paragon = db.query(Paragon).get(paragon_id)
        if not paragon:
            response = RedirectResponse(url="/spizarnia", status_code=303)
            response.set_cookie('flash_msg', quote('Paragon nie znaleziony!'))
            return response
            
        if paragon.status_przetwarzania != StatusParagonu.PRZETWORZONY_OK:
            response = RedirectResponse(url="/spizarnia", status_code=303)
            response.set_cookie('flash_msg', quote('Paragon nie został jeszcze przetworzony!'))
            return response
            
        # Get products from the receipt
        produkty = db.query(Produkt).filter(Produkt.paragon_id == paragon_id).all()
        
        # Add products to pantry
        for produkt in produkty:
            # Check if product already exists in pantry
            existing_product = db.query(Produkt).filter(
                Produkt.nazwa == produkt.nazwa,
                Produkt.paragon_id.is_(None)
            ).first()
            
            if existing_product:
                # Update quantity of existing product
                existing_product.aktualna_ilosc += produkt.ilosc_na_paragonie
                db.delete(produkt)  # Remove the receipt product
            else:
                # Add as new product to pantry
                produkt.paragon_id = None  # Remove reference to receipt
                produkt.aktualna_ilosc = produkt.ilosc_na_paragonie
                db.add(produkt)
        
        db.commit()
        
        response = RedirectResponse(url="/spizarnia", status_code=303)
        response.set_cookie('flash_msg', quote('Produkty zostały dodane do spiżarni!'))
        return response
    finally:
        db.close()

@app.get("/sugestie", response_class=HTMLResponse)
async def sugestie(
    request: Request,
    context: Dict[str, Any] = Depends(get_template_context)
):
    """Show suggestions page"""
    return templates.TemplateResponse(
        "sugestie.html",
        {**context}
    )

@app.get("/statystyki", response_class=HTMLResponse)
async def statystyki(
    request: Request,
    context: Dict[str, Any] = Depends(get_template_context)
):
    """Show statistics page"""
    return templates.TemplateResponse(
        "statystyki.html",
        {**context}
    )

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True  # Enable auto-reload during development
    ) 