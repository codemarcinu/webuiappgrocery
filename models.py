from datetime import datetime
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship, select
from enum import Enum
from pydantic import validator, constr
from decimal import Decimal
from sqlalchemy import Column, ForeignKey, Integer

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

class KategoriaProduktu(str, Enum):
    SPOZYWCZE = "Spożywcze"
    CHEMIA = "Chemia"
    KOSMETYKI = "Kosmetyki"
    NAPOJE = "Napoje"
    SLODYCZE = "Słodycze"
    PIECZYWO = "Pieczywo"
    WARZYWA = "Warzywa"
    OWOCE = "Owoce"
    INNE = "Inne"

class StatusMapowania(str, Enum):
    OCZEKUJE = "oczekuje"
    ZMAPOWANY = "zmapowany"
    NOWY = "nowy"
    IGNOROWANY = "ignorowany"

class Produkt(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    nazwa: constr(min_length=1, max_length=100)
    kategoria: KategoriaProduktu
    cena: Decimal = Field(max_digits=10, decimal_places=2)
    data_waznosci: Optional[datetime] = None
    paragon_id: Optional[int] = Field(foreign_key="paragon.id", index=True, default=None)
    data_dodania: datetime = Field(default_factory=datetime.utcnow, index=True)
    
    # Quantity fields
    ilosc_na_paragonie: Optional[int] = Field(default=1)  # Quantity on receipt
    aktualna_ilosc: Optional[int] = Field(default=1)  # Current quantity in pantry
    
    # Mapping fields
    status_mapowania: StatusMapowania = Field(default=StatusMapowania.OCZEKUJE)
    sugestie_mapowania: Optional[str] = Field(default=None)  # JSON string with mapping suggestions
    zmapowany_do_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("produkt.id", ondelete="SET NULL"), nullable=True)
    )
    
    # Relationships
    paragon: "Paragon" = Relationship(back_populates="produkty")
    zmapowany_do: Optional["Produkt"] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Produkt.zmapowany_do_id == Produkt.id",
            "remote_side": "Produkt.id"
        }
    )
    
    @validator('cena')
    def validate_cena(cls, v):
        if v < 0:
            raise ValueError('Cena nie może być ujemna')
        return v
    
    @validator('data_waznosci')
    def validate_data_waznosci(cls, v):
        if v and v < datetime.utcnow():
            raise ValueError('Data ważności nie może być z przeszłości')
        return v
        
    @validator('ilosc_na_paragonie', 'aktualna_ilosc')
    def validate_ilosc(cls, v):
        if v is not None and v < 0:
            raise ValueError('Ilość nie może być ujemna')
        return v

class Paragon(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    nazwa_pliku_oryginalnego: constr(min_length=1, max_length=255)
    sciezka_pliku_na_serwerze: constr(min_length=1, max_length=255)
    mime_type_pliku: constr(min_length=1, max_length=100)
    sciezka_miniatury: Optional[str] = None
    status_przetwarzania: StatusParagonu = Field(index=True)
    data_wyslania: datetime = Field(default_factory=datetime.utcnow, index=True)
    data_przetworzenia: Optional[datetime] = None
    blad_przetwarzania: Optional[str] = None
    
    # Relationships
    produkty: List[Produkt] = Relationship(back_populates="paragon")
    
    @validator('mime_type_pliku')
    def validate_mime_type(cls, v):
        allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'application/pdf']
        if v not in allowed_types:
            raise ValueError(f'Niedozwolony typ pliku. Dozwolone typy: {", ".join(allowed_types)}')
        return v

class LogBledow(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
    poziom: PoziomLogu
    modul_aplikacji: constr(min_length=1, max_length=100)
    funkcja: constr(min_length=1, max_length=100)
    komunikat_bledu: constr(min_length=1, max_length=500)
    szczegoly_techniczne: Optional[str] = None 