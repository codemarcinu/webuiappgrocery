from fastapi import APIRouter, Request, Query, Depends, HTTPException, Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from sqlmodel import Session, select
from typing import Optional, List
from database import get_session
from db_logger import log_to_db
from models import LogBledow, PoziomLogu
import json
from datetime import datetime
from pathlib import Path
import os
import subprocess

router = APIRouter(prefix="/logi", tags=["logi"])
templates = Jinja2Templates(directory="templates")

def log_to_db(poziom: PoziomLogu, modul: str, funkcja: str, komunikat: str, szczegoly: str = None):
    """Helper function to log to database"""
    with get_session() as db:
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

@router.post("/clear")
def clear_logs(request: Request):
    with get_session() as db:
        logs = db.query(LogBledow).order_by(LogBledow.timestamp.asc()).all()
        if logs:
            # Archiwizacja do pliku
            archive_dir = Path("logs")
            archive_dir.mkdir(exist_ok=True)
            archive_file = archive_dir / f"logs_archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(archive_file, "w", encoding="utf-8") as f:
                json.dump([
                    {
                        "timestamp": log.timestamp.isoformat(),
                        "poziom": log.poziom,
                        "modul_aplikacji": log.modul_aplikacji,
                        "funkcja": log.funkcja,
                        "komunikat_bledu": log.komunikat_bledu,
                        "szczegoly_techniczne": log.szczegoly_techniczne
                    } for log in logs
                ], f, ensure_ascii=False, indent=2)
            # Usuń logi z bazy
            db.query(LogBledow).delete()
            db.commit()
    # Przekierowanie z komunikatem
    response = RedirectResponse(url="/logi", status_code=303)
    response.set_cookie('flash_msg', 'Logi zostaly wyczyszczone i zarchiwizowane!')
    return response 

@router.get("/celery", response_class=PlainTextResponse)
@router.get("/celery/", response_class=PlainTextResponse)
async def get_celery_logs():
    log_path = os.path.join("logs", "celery.log")
    try:
        with open(log_path, "r") as f:
            lines = f.readlines()
        # Zwróć ostatnie 100 linii
        return "".join(lines[-100:])
    except Exception as e:
        return f"Błąd odczytu logów Celery: {e}"

@router.post("/celery/start", response_class=PlainTextResponse)
def start_celery_worker():
    pid_file = "logs/celery_worker.pid"
    # Sprawdź czy worker już działa
    if os.path.exists(pid_file):
        try:
            with open(pid_file, "r") as f:
                pid = int(f.read().strip())
            # Sprawdź czy proces żyje
            os.kill(pid, 0)
            return "Celery worker już działa (PID: %d)" % pid
        except Exception:
            os.remove(pid_file)  # Uszkodzony PID, usuwamy
    # Uruchom Celery workera
    try:
        proc = subprocess.Popen([
            "celery", "-A", "tasks", "worker", "--loglevel=info", "--logfile=logs/celery.log"
        ])
        with open(pid_file, "w") as f:
            f.write(str(proc.pid))
        return f"Celery worker uruchomiony (PID: {proc.pid})"
    except Exception as e:
        return f"Błąd uruchamiania Celery: {e}"

@router.post("/celery/stop", response_class=PlainTextResponse)
def stop_celery_worker():
    pid_file = "logs/celery_worker.pid"
    if not os.path.exists(pid_file):
        return "Celery worker nie jest uruchomiony."
    try:
        with open(pid_file, "r") as f:
            pid = int(f.read().strip())
        os.kill(pid, 15)  # SIGTERM
        os.remove(pid_file)
        return f"Celery worker zatrzymany (PID: {pid})"
    except Exception as e:
        return f"Błąd zatrzymywania Celery: {e}" 