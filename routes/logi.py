from fastapi import APIRouter, Request, Query, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select
from typing import Optional, List
from database import get_session, SessionLocal
from models import LogBledow, PoziomLogu
import json

router = APIRouter(prefix="/logi", tags=["logi"])
templates = Jinja2Templates(directory="templates")

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

@router.get("/", response_class=HTMLResponse)
def lista_logow(request: Request, 
                poziom: Optional[str] = Query(None),
                page: int = Query(1, ge=1),
                per_page: int = Query(30, ge=1, le=100)):
    with get_session() as db:
        query = db.query(LogBledow)
        if poziom:
            query = query.filter(LogBledow.poziom == poziom)
        total = query.count()
        logs = query.order_by(LogBledow.timestamp.desc()) \
                    .offset((page-1)*per_page).limit(per_page).all()
        poziomy = [p.value for p in PoziomLogu]
        return templates.TemplateResponse(
            "logi/lista.html",
            {
                "request": request,
                "logs": logs,
                "poziomy": poziomy,
                "selected_poziom": poziom,
                "page": page,
                "per_page": per_page,
                "total": total
            }
        )

@router.get("/logi/", response_model=List[LogBledow])
async def get_logs(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_session)
):
    """Get logs"""
    try:
        log_to_db(
            PoziomLogu.INFO,
            "routes.logi",
            "get_logs",
            "Pobieranie logów",
            json.dumps({
                "skip": skip,
                "limit": limit,
                "status": "started"
            })
        )
        
        logs = db.query(LogBledow).offset(skip).limit(limit).all()
        
        log_to_db(
            PoziomLogu.INFO,
            "routes.logi",
            "get_logs",
            "Logi pobrane pomyślnie",
            json.dumps({
                "skip": skip,
                "limit": limit,
                "count": len(logs),
                "status": "completed"
            })
        )
        
        return logs
        
    except Exception as e:
        log_to_db(
            PoziomLogu.ERROR,
            "routes.logi",
            "get_logs",
            "Błąd pobierania logów",
            json.dumps({
                "skip": skip,
                "limit": limit,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": str(e.__traceback__)
            })
        )
        raise

@router.get("/logi/{log_id}", response_model=LogBledow)
async def get_log(
    log_id: int,
    db: Session = Depends(get_session)
):
    """Get log by ID"""
    try:
        log_to_db(
            PoziomLogu.INFO,
            "routes.logi",
            "get_log",
            f"Pobieranie logu: {log_id}",
            json.dumps({
                "log_id": log_id,
                "status": "started"
            })
        )
        
        log = db.query(LogBledow).get(log_id)
        if not log:
            log_to_db(
                PoziomLogu.ERROR,
                "routes.logi",
                "get_log",
                f"Log nie znaleziony: {log_id}",
                json.dumps({
                    "log_id": log_id,
                    "error_type": "NotFoundError"
                })
            )
            raise HTTPException(status_code=404, detail="Log not found")
        
        log_to_db(
            PoziomLogu.INFO,
            "routes.logi",
            "get_log",
            f"Log pobrany pomyślnie: {log_id}",
            json.dumps({
                "log_id": log_id,
                "status": "completed"
            })
        )
        
        return log
        
    except Exception as e:
        log_to_db(
            PoziomLogu.ERROR,
            "routes.logi",
            "get_log",
            f"Błąd pobierania logu: {log_id}",
            json.dumps({
                "log_id": log_id,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": str(e.__traceback__)
            })
        )
        raise 