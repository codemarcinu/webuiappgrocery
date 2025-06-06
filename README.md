# Webowy Asystent Spiżarni

Aplikacja do zarządzania produktami w spiżarni, z funkcją automatycznego przetwarzania paragonów.

## Instalacja

1. Sklonuj repozytorium:
```bash
git clone <url-repozytorium>
cd webuiappgrocery
```

2. Utwórz i aktywuj wirtualne środowisko:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# lub
.\venv\Scripts\activate  # Windows
```

3. Zainstaluj zależności systemowe:
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y poppler-utils redis-server

# Fedora
sudo dnf install -y poppler-utils redis

# macOS
brew install poppler redis
```

4. Zainstaluj zależności Pythona:
```bash
pip install -r requirements.txt
```

5. Skonfiguruj zmienne środowiskowe:
   - Utwórz plik `.env` w głównym katalogu projektu
   - Skopiuj zawartość z `.env.example` i dostosuj wartości

## Inicjalizacja Bazy Danych

Po zainstalowaniu zależności i skonfigurowaniu zmiennych środowiskowych, należy zainicjalizować bazę danych:

```bash
flask init-db
```

Ta komenda utworzy wszystkie niezbędne tabele w bazie danych. Możesz ją uruchomić ponownie w dowolnym momencie, jeśli potrzebujesz odtworzyć strukturę bazy danych.

## Uruchomienie Aplikacji

1. Upewnij się, że Redis jest uruchomiony:
```bash
# Ubuntu/Debian
sudo systemctl start redis-server

# Fedora
sudo systemctl start redis

# macOS
brew services start redis
```

2. Uruchom serwer deweloperski:
```bash
uvicorn main:app --reload
```

3. Otwórz przeglądarkę i przejdź pod adres:
```
http://localhost:8000
```

## Funkcje

- Automatyczne przetwarzanie paragonów (obsługa plików PDF i obrazów)
- Zarządzanie produktami w spiżarni
- Śledzenie dat ważności produktów
- Kategoryzacja produktów
- Interfejs webowy

## Wymagania Systemowe

- Python 3.8+
- SQLite (domyślnie) lub PostgreSQL
- Ollama (dla przetwarzania paragonów)
- Redis (dla Celery - przetwarzania w tle)
- Poppler-utils (dla obsługi plików PDF)

## Licencja

MIT 