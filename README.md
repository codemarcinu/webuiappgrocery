# Webowy Asystent Spiżarni

Aplikacja webowa do zarządzania produktami w spiżarni, z funkcją przetwarzania paragonów.

## Funkcjonalności

- Przesyłanie i przetwarzanie paragonów
- Automatyczne rozpoznawanie produktów z paragonów
- Zarządzanie produktami w spiżarni
- Śledzenie dat ważności produktów
- Interfejs użytkownika w Material Design
- Tryb ciemny

## Wymagania

- Python 3.8+
- SQLite (lub inna baza danych SQL)
- Przeglądarka internetowa z obsługą JavaScript

## Instalacja

1. Sklonuj repozytorium:
```bash
git clone https://github.com/twoj-username/webowy-asystent-spizarni.git
cd webowy-asystent-spizarni
```

2. Utwórz i aktywuj wirtualne środowisko:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# lub
venv\Scripts\activate  # Windows
```

3. Zainstaluj zależności:
```bash
pip install -r requirements.txt
```

4. Uruchom aplikację:
```bash
python main.py
```

Aplikacja będzie dostępna pod adresem http://localhost:8000

## Struktura projektu

```
webowy-asystent-spizarni/
├── main.py              # Główny plik aplikacji
├── models.py            # Modele danych
├── database.py          # Konfiguracja bazy danych
├── logging_config.py    # Konfiguracja logowania
├── requirements.txt     # Zależności projektu
├── static/             # Pliki statyczne (CSS, JS, obrazy)
├── templates/          # Szablony HTML
│   └── paragony/      # Szablony dla funkcjonalności paragonów
├── uploads/           # Katalog na przesłane pliki
└── logs/              # Katalog na pliki logów
```

## Rozwój

1. Utwórz nową gałąź dla swojej funkcjonalności:
```bash
git checkout -b feature/nazwa-funkcjonalnosci
```

2. Wprowadź zmiany i zatwierdź je:
```bash
git add .
git commit -m "Dodano nową funkcjonalność"
```

3. Wypchnij zmiany do repozytorium:
```bash
git push origin feature/nazwa-funkcjonalnosci
```

## Licencja

Ten projekt jest udostępniany na licencji MIT. Szczegóły znajdują się w pliku LICENSE. 