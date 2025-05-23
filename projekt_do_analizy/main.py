from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pathlib import Path
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import Response
from typing import Optional

from database import create_db_and_tables, SessionLocal
from routes import paragony
from logging_config import logger
from models import Paragon, Produkt

# Create FastAPI app
app = FastAPI(
    title="Webowy Asystent Spiżarni",
    description="Aplikacja do zarządzania produktami w spiżarni",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configure templates
templates = Jinja2Templates(directory="templates")

# Include routers
app.include_router(paragony.router)

@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    try:
        # Create database tables
        create_db_and_tables()
        logger.info("Application started successfully")
    except Exception as e:
        logger.error(f"Error during startup: {str(e)}", exc_info=True)
        raise

@app.get("/")
async def root(request: Request):
    """Root endpoint - shows list of receipts"""
    db = SessionLocal()
    try:
        paragony = db.query(Paragon).order_by(Paragon.data_wyslania.desc()).all()
        return templates.TemplateResponse(
            "paragony/lista.html",
            {
                "request": request,
                "paragony": paragony
            }
        )
    finally:
        db.close()

@app.get("/spizarnia", response_class=HTMLResponse)
async def spizarnia(request: Request, nazwa: str = '', kategoria: str = '', data_waznosci: str = '', msg: Optional[str] = None):
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
            {"request": request, "produkty": produkty, "kategorie": kategorie, "f_nazwa": nazwa, "f_kategoria": kategoria, "f_data_waznosci": data_waznosci, "flash_msg": flash_msg}
        )
        # Skasuj flash message po odczytaniu
        if flash_msg:
            response.delete_cookie('flash_msg')
        return response
    finally:
        db.close()

@app.get("/spizarnia/edytuj/{produkt_id}", response_class=HTMLResponse)
async def edytuj_produkt_get(request: Request, produkt_id: int):
    db = SessionLocal()
    try:
        produkt = db.query(Produkt).get(produkt_id)
        if not produkt:
            return templates.TemplateResponse("spizarnia.html", {"request": request, "produkty": db.query(Produkt).all(), "error": "Produkt nie znaleziony"})
        kategorie = ["Nabiał", "Pieczywo", "Mięso", "Warzywa", "Owoce", "Słodycze", "Napoje", "Inne"]
        return templates.TemplateResponse("edytuj_produkt.html", {"request": request, "produkt": produkt, "kategorie": kategorie})
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
        data_waznosci = form.get("data_waznosci")
        produkt.data_waznosci = data_waznosci if data_waznosci else None
        db.commit()
        response = RedirectResponse(url="/spizarnia", status_code=303)
        response.set_cookie('flash_msg', 'Produkt został zaktualizowany!')
        return response
    finally:
        db.close()

@app.post("/spizarnia/usun/{produkt_id}")
async def usun_produkt(produkt_id: int):
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

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True  # Enable auto-reload during development
    ) 