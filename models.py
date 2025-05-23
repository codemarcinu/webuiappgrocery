from datetime import datetime
from typing import Optional, List
from sqlmodel import SQLModel, Field
from enum import Enum

class StatusParagonu(str, Enum):
    OCZEKUJE_NA_PODGLAD = "OCZEKUJE_NA_PODGLAD"
    PODGLADNIETY_OCZEKUJE_NA_PRZETWORZENIE = "PODGLADNIETY_OCZEKUJE_NA_PRZETWORZENIE"
    PRZETWARZANY_OCR = "PRZETWARZANY_OCR"
    PRZETWARZANY_AI = "PRZETWARZANY_AI"
    PRZETWORZONY_OK = "PRZETWORZONY_OK"
    PRZETWORZONY_BLAD = "PRZETWORZONY_BLAD"

class PoziomLogu(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"

class Produkt(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    nazwa: str
    kategoria: str
    cena: float
    data_waznosci: Optional[datetime] = None
    paragon_id: int = Field(foreign_key="paragon.id")
    data_dodania: datetime = Field(default_factory=datetime.utcnow)

class Paragon(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    nazwa_pliku_oryginalnego: str
    sciezka_pliku_na_serwerze: str
    mime_type_pliku: str
    sciezka_miniatury: Optional[str] = None
    status_przetwarzania: StatusParagonu
    data_wyslania: datetime = Field(default_factory=datetime.utcnow)
    data_przetworzenia: Optional[datetime] = None
    blad_przetwarzania: Optional[str] = None

class LogBledow(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    poziom: PoziomLogu
    modul_aplikacji: str
    funkcja: str
    komunikat_bledu: str
    szczegoly_techniczne: Optional[str] = None 