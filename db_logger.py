from models import LogBledow, PoziomLogu
from datetime import datetime
import pytz

def log_to_db(poziom: PoziomLogu, modul: str, funkcja: str, komunikat: str, szczegoly: str = None):
    """Helper function to log to database"""
    from database import SessionLocal
    
    # Get current time in Warsaw timezone
    warsaw_tz = pytz.timezone('Europe/Warsaw')
    current_time = datetime.now(warsaw_tz)
    
    with SessionLocal() as db:
        log = LogBledow(
            poziom=poziom,
            modul_aplikacji=modul,
            funkcja=funkcja,
            komunikat_bledu=komunikat,
            szczegoly_techniczne=szczegoly,
            data_utworzenia=current_time
        )
        db.add(log)
        db.commit() 